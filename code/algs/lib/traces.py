from .optional_args import process_kwargs


class Trace:
    def __init__(self, file, **kwargs):
        self.duration = 0
        process_kwargs(self, kwargs, acceptable_kws=["duration"])

        self.file = file
        self.unique = set()
        self.reuse = set()
        self.requests = 0
        self.start_time = 0
        self.start_tick = 0
        self.next_tick = 0
        self.last_line = None
        self.progress = 0

        f = open(self.file, "r")
        f.seek(0, 2)
        self.end = f.tell()
        f.close()

    def readLine(self, line):
        yield int(line), False, False

    def read(self):
        f = open(self.file, "r")
        try:
            while True:
                line = f.readline()
                if not line:
                    break
                self.last_line = line
                self.progress = round(100 * (f.tell() / self.end))
                for lba, write, ts in self.readLine(line):
                    if lba is None:
                        continue
                    self.requests += 1
                    if lba in self.unique:
                        self.reuse.add(lba)
                    self.unique.add(lba)
                    yield lba, write, ts
        except EOFError:
            pass
        f.close()

    def num_requests(self):
        return self.requests

    def num_unique(self):
        return len(self.unique)

    def num_reuse(self):
        return len(self.reuse)


class VisaTrace(Trace):
    def inDuration(self, time):
        if self.duration == 0:
            return True
        if self.start_time == 0:
            self.start_time = time
            self.end_time = time + (self.duration * 60 * 60)
        return time < self.end_time

    def tickHour(self, time):
        if self.start_tick == 0:
            self.start_tick = time
        self.next_tick += time - self.start_tick
        self.start_tick = time
        return int(self.next_tick / (3.6 * 10**3))

    def readLine(self, line):
        blocks_per_page = 8
        line = line.split(" ")
        ts = float(line[0])
        lba = int(line[4])
        size = int(line[5])
        write = line[6][0] == "W"
        align = lba % blocks_per_page
        lba -= align
        size += align

        ts_hour = self.tickHour(ts)

        for offset in range(0, size, blocks_per_page):
            yield lba + offset, write, ts_hour


def get_trace_reader(trace_type):
    if trace_type.lower() == "visa":
        return VisaTrace
    raise ValueError("CloudVPS reproduction only supports converted .blk traces")


def identify_trace(filename):
    if filename.endswith(".blk"):
        return "visa"
    raise ValueError("CloudVPS reproduction only supports converted .blk traces")


def read_trace_file(filename):
    trace_reader = get_trace_reader(identify_trace(filename))
    reader = trace_reader(filename)
    for lba, write, ts in reader.read():
        yield lba, write, ts
