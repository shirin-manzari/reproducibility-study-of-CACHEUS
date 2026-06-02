# CACHEUS CloudVPS Reproduction Deep Dive

This document explains this repository from the outside in: what it is, what
CACHEUS is, how this implementation works, how traces move through the
pipeline, how the simulator is structured, and what algorithms are implemented.
It is written to let a reader understand the project without re-reading the
source code.

## Executive Summary

This repository is a reduced, offline reproduction workflow for evaluating
cache-replacement algorithms on CloudVPS block I/O traces. It contains:

- `cloudvps_pipeline.py`, the end-to-end CloudVPS pipeline.
- `code/run.py`, the original simulator runner.
- `code/algs/`, cache-replacement algorithm implementations.
- `code/algs/lib/`, shared data structures, trace readers, progress reporting,
  pollution tracking, and visualization helpers.
- Ignored local `data/` and `work/` trees for raw traces and intermediate
  files, plus a curated tracked subset under `results/cloudvps/`.

The active user workflow is intentionally narrow: local CloudVPS trace archives
are decoded with `blkparse`, converted into the simulator's `.blk` trace format,
replayed through several cache algorithms, aggregated into CSV reports, and
plotted as PNG figures. No network downloads, notebooks, databases, containers,
or web UI are part of the active workflow.

The default experiment runs these algorithms:

- `lru`
- `lfu`
- `arc`
- `lirs`
- `lecar`
- `cacheus`

against these cache-size fractions:

- `0.001`
- `0.005`
- `0.01`
- `0.05`
- `0.1`

The cache-size fractions are interpreted relative to the number of unique
page-level requests in each converted trace. For example, `0.01` means
`floor(0.01 * unique_page_count)`.

## What CACHEUS Is

CACHEUS is a machine-learned cache-replacement framework introduced in the
FAST '21 paper "Learning Cache Replacement with Cacheus" by Rodriguez et al.
The paper starts from the observation that no single cache-replacement policy is
best across all storage workloads or all cache sizes. Storage workloads can
contain different cache-relevant primitive patterns:

- LRU-friendly reuse, where recent items are likely to be reused soon.
- LFU-friendly reuse, where frequently used items should be protected.
- Scans, where many items are read or written once and should not evict useful
  resident data.
- Churn, where a working set larger than cache is accessed in a way that causes
  simple recency policies to repeatedly evict soon-needed data.

CACHEUS generalizes the earlier LeCaR approach. LeCaR chooses dynamically
between LRU and LFU using regret minimization. CACHEUS keeps the two-expert
learning structure but improves the experts and the learning-rate behavior.
The key ideas are:

- Use exactly two complementary experts.
- Keep a probability weight for each expert.
- Choose an eviction expert randomly according to those weights.
- Maintain eviction histories, so a later miss can reveal which expert made a
  bad eviction.
- Penalize the expert whose past eviction caused a later miss.
- Adapt the learning rate online, using hit-rate behavior over cache-sized
  windows.

In the paper, the strongest variant is CACHEUS with two lightweight experts:

- SR-LRU, a scan-resistant LRU expert.
- CR-LFU, a churn-resistant LFU expert.

This repository's `code/algs/cacheus.py` implements that SR-LRU plus CR-LFU
variant directly, not a fully generic plugin framework where arbitrary expert
classes can be supplied at runtime.

## What This Repository Is

This checkout is not the full original research artifact with every dataset and
workflow exposed. It is a CloudVPS-only reproduction wrapper around the original
simulator and algorithms. The README explicitly says the old generic JSON
workflow has been hidden from normal use, but the runner still exists and the
pipeline still drives it through an internal generated JSON config.

The repository has two layers:

1. A user-facing CloudVPS pipeline.
2. A lower-level simulator that can replay converted traces through cache
   algorithm classes.

The CloudVPS pipeline handles practical experiment orchestration:

- find local archives or extracted trace directories;
- safely extract `.tar.gz` archives;
- locate `.blktrace.0` files;
- run `blkparse`;
- filter decoded block events;
- convert events into the simulator's `.blk` format;
- generate a runner config;
- run the simulator;
- normalize raw simulator CSV output;
- compute summaries and CACHEUS deltas;
- generate result figures.

The simulator handles policy evaluation:

- identify trace type;
- read and expand trace requests;
- instantiate a chosen algorithm with cache size and window size;
- replay every request in order;
- count hits, misses, writes, and filtered operations;
- optionally write a CSV row per experiment.

## Repository Structure

```text
.
|-- README.md
|-- PROJECT_DEEP_DIVE.md
|-- cloudvps_pipeline.py
|-- fast21-rodriguez.pdf
|-- code/
|   |-- run.py
|   `-- algs/
|       |-- get_algorithm.py
|       |-- lru.py
|       |-- lfu.py
|       |-- mru.py
|       |-- arc.py
|       |-- lirs.py
|       |-- dlirs.py
|       |-- lecar.py
|       |-- alecar6.py
|       |-- cacheus.py
|       |-- arcalecar.py
|       |-- lirsalecar.py
|       |-- min.py
|       `-- lib/
|           |-- cacheop.py
|           |-- dequedict.py
|           |-- heapdict.py
|           |-- optional_args.py
|           |-- pollutionator.py
|           |-- progress_bar.py
|           |-- traces.py
|           `-- visualizinator.py
|-- data/      ignored local raw input tree
|-- work/      ignored generated intermediate tree
`-- results/   generated outputs; curated CloudVPS summaries are tracked
```

### Tracked Files

`README.md`

The user-facing guide. It documents the CloudVPS-only workflow, required local
inputs, defaults, outputs, and preserved behavior.

`PROJECT_DEEP_DIVE.md`

This explanatory companion document. It gives a code-level and workflow-level
map of the reduced reproduction so readers can understand the project without
opening every source file first.

`cloudvps_pipeline.py`

The active orchestration entrypoint. It is a standalone Python script with no
package structure. It owns path handling, archive extraction, trace decoding,
conversion, simulator invocation, result normalization, summary generation, and
plotting.

`code/run.py`

The original simulator runner. It consumes JSON config, calculates concrete
cache sizes, enumerates trace files and algorithm configurations, replays traces,
and writes raw result rows.

`code/algs/get_algorithm.py`

Maps algorithm names from config to implementation classes.

`code/algs/*.py`

Individual cache algorithms. Some are used by the default CloudVPS pipeline,
while others remain available through the lower-level runner.

`code/algs/lib/*.py`

Shared utility classes.

`fast21-rodriguez.pdf`

A local PDF copy of the FAST '21 CACHEUS paper, when present. Papers and
presentation PDFs are useful background for understanding the algorithm family,
but they are not required by the code path and are usually ignored unless they
are intentionally force-added.

### Runtime and Result Trees

`.gitignore` excludes `data/` and `work/`. Those directories are expected to
contain large local traces and generated intermediates, not source code.

Most generated result files are ignored by default. A small curated CloudVPS
result set is explicitly allowed back into git for the report and
reproducibility summary:

- `results/cloudvps/README.md`
- `results/cloudvps/conversion_summary.csv`
- `results/cloudvps/summary_by_algorithm.csv`
- `results/cloudvps/summary_by_cache_size.csv`
- `results/cloudvps/cacheus_vs_baselines.csv`
- `results/cloudvps/cacheus_delta_summary.csv`
- `results/cloudvps/figures/*.png`

In the local experiment workspace, a full run also produced ignored raw outputs
such as `cloudvps_results.csv`, `cloudvps_results_raw.csv`, and
`cloudvps_runner.log`.

The local run used:

- 18 raw archives under `data/cloudvps_raw/`.
- 18 converted `.blk` files under `work/cloudvps/converted/`.
- 18 decoded `blkparse` text files under `work/cloudvps/decoded/`.
- CSV summaries and PNG figures under `results/cloudvps/`.

## External Requirements

The README states these prerequisites:

- Python 3 with needed packages already installed.
- Linux `blktrace` / `blkparse` installed.
- Local CloudVPS archives or extracted CloudVPS trace directories.

The code imports these non-stdlib packages:

- `numpy`, used by algorithms and result statistics.
- `matplotlib`, used by `cloudvps_pipeline.py` for figures and imported by
  `visualizinator.py`.

There is no `requirements.txt`, lockfile, or package metadata in this reduced
repo.

## Data Model

### Raw CloudVPS Input

The pipeline expects archives such as:

```text
data/cloudvps_raw/vps26020.tar.gz
data/cloudvps_raw/vps26107.tar.gz
```

or already-extracted directories such as:

```text
data/cloudvps_raw/vps26020/
  vps26020.blktrace.0
  vps26020.blktrace.1
```

The pipeline invokes `blkparse -i <path-to-.blktrace.0>`. `blkparse` uses paired
files such as `.blktrace.1` automatically when present.

### Decoded `blkparse` Input

A decoded line looks like this:

```text
253,941  1  1  0.000000000 30387  Q  W 104160 + 8 [blkback.9.xvda1]
```

Important fields:

- field 3: timestamp, such as `0.000000000`;
- field 5: action, such as `Q`;
- field 6: operation, such as `W`;
- field 7: logical block address;
- field 8: plus sign separator;
- field 9: request size in sectors.

By default only action `Q` is kept. Completion events and other non-queue events
are skipped to avoid double-counting the same I/O.

### Converted Simulator Input

The pipeline converts each kept decoded line into:

```text
timestamp 0 0 0 lba size op
```

Example:

```text
0.000000000 0 0 0 104160 8 W
```

The three zero fields are placeholders because `VisaTrace` expects the LBA at
field index 4, size at index 5, and operation at index 6.

### Page-Level Request Expansion

The simulator does not use raw request extents directly. `VisaTrace.readLine()`
expands each converted block I/O event into page-aligned requests:

- `blocks_per_page = 8`;
- compute `align = lba % 8`;
- shift the starting LBA down by `align`;
- add `align` to the request size;
- emit one request for each offset in `range(0, size, 8)`;
- the emitted logical block address is page-aligned.

That means one converted `.blk` line can become one or more simulator requests.
All algorithm hit/miss accounting happens at this expanded page granularity.

`VisaTrace` also records:

- total expanded request count;
- unique page count;
- reused page count;
- whether each request is a write;
- a coarse time tick derived from timestamp deltas.

## End-to-End Pipeline

The active command is:

```bash
python3 cloudvps_pipeline.py
```

Optional path overrides:

```bash
python3 cloudvps_pipeline.py \
  --raw-dir ./data/cloudvps_raw \
  --work-dir ./work/cloudvps \
  --out-dir ./results/cloudvps
```

### Stage 1: Parse Arguments and Resolve Paths

`parse_args()` accepts:

- `--raw-dir`, default `data/cloudvps_raw`;
- `--work-dir`, default `work/cloudvps`;
- `--out-dir`, default `results/cloudvps`.

Relative paths are resolved against the repository root, determined from the
location of `cloudvps_pipeline.py`.

The pipeline creates these directories if needed:

- raw dir;
- `work/cloudvps/extracted`;
- `work/cloudvps/decoded`;
- `work/cloudvps/converted`;
- output dir.

### Stage 2: Prepare Inputs

`prepare_inputs(raw_dir, extracted_dir)`:

1. Finds `vps*.tar.gz` archives in the raw directory.
2. Extracts each archive into `work/cloudvps/extracted`.
3. Searches both raw and extracted trees for directories whose names start with
   `vps`.
4. For each trace directory, locates a `.blktrace.0` file.
5. Skips directories where there is no unique `.blktrace.0`.
6. Fails if no usable trace targets are found.

Archive extraction is guarded by `safe_extract()`:

- symlinks and hardlinks are rejected;
- every target path must stay inside the intended destination directory.

This prevents path traversal or archive link surprises during extraction.

### Stage 3: Decode With `blkparse`

`decode_traces(targets, decoded_dir)`:

1. Finds `blkparse` on `PATH`.
2. For each target `.blktrace.0`, writes decoded text to
   `work/cloudvps/decoded/<trace>.blkparse.txt`.
3. Runs:

   ```bash
   blkparse -i <blktrace0>
   ```

4. Captures stdout to the decoded file.
5. Captures stderr and reports it if `blkparse` fails.

If `blkparse` is missing, the pipeline stops with a clear `PipelineError`.

### Stage 4: Convert Decoded Lines

`convert_traces(decoded, converted_dir, out_dir)`:

1. Opens `results/cloudvps/conversion_summary.csv`.
2. For each decoded file, creates `work/cloudvps/converted/<trace>.blk`.
3. Reads every decoded line in order.
4. Calls `parse_blkparse_line(line)`.
5. Writes valid queue events into simulator format.
6. Counts total decoded lines, kept queue events, and skipped lines.
7. Excludes conversions with zero kept events from simulation.

`parse_blkparse_line()` rejects a line if:

- it has fewer than 10 whitespace-separated fields;
- the action is not `Q`;
- the separator is not `+`;
- operation is empty;
- timestamp, LBA, or size are not parseable;
- timestamp is not finite;
- LBA is negative;
- size is not positive.

Input order is preserved. There is no sorting or deduplication.

### Stage 5: Write Internal Runner Config

`write_runner_config(converted, work_dir, raw_results)` creates:

```text
work/cloudvps/.cacheus_cloudvps_runner.config.json
```

The generated config contains:

```json
{
  "output_csv": "results/cloudvps/cloudvps_results_raw.csv",
  "cache_sizes": [0.001, 0.005, 0.01, 0.05, 0.1],
  "traces": ["work/cloudvps/converted/..."],
  "request_count_type": "unique",
  "algorithms": ["lru", "lfu", "arc", "lirs", "lecar", "cacheus"]
}
```

This hidden config exists only to drive `code/run.py`. The normal user is not
expected to edit it.

### Stage 6: Run the Simulator

`run_simulator(config_path, raw_results, work_dir)`:

1. Removes an existing raw result CSV if present.
2. Creates `work/cloudvps/matplotlib`.
3. Sets `MPLCONFIGDIR` to that local work directory.
4. Launches:

   ```bash
   python3 code/run.py work/cloudvps/.cacheus_cloudvps_runner.config.json
   ```

5. Streams runner output live to the terminal.
6. Writes the same output to `results/cloudvps/cloudvps_runner.log`.
7. Fails if the runner exits nonzero.
8. Fails if the raw result CSV is missing or empty.

### Stage 7: Normalize Raw Results

`read_results(raw_results, out_dir)` reads raw rows from the simulator and writes
a headered CSV to:

```text
results/cloudvps/cloudvps_results.csv
```

The fixed columns are:

- `trace_file`
- `trace_type`
- `algorithm`
- `hits`
- `misses`
- `writes`
- `filters`
- `cache_size`
- `cache_size_label`
- `cache_size_label_type`
- `hit_rate`
- `avg_pollution`
- `runtime_sec`

If algorithm-specific extra fields are present, they are named `extra_1`,
`extra_2`, and so on. The default CloudVPS algorithms do not rely on these
extra columns for the later summaries.

### Stage 8: Analyze Results

`analyze(rows, out_dir)` creates four CSV summaries.

`summary_by_algorithm.csv`

Groups by algorithm and computes:

- mean hit rate;
- median hit rate;
- min hit rate;
- max hit rate;
- run count;
- total runtime.

`summary_by_cache_size.csv`

Groups by algorithm and cache-size label and computes mean hit rate.

`cacheus_vs_baselines.csv`

For every `(trace_file, cache_size_label, cache_size_label_type)` group that has
a `cacheus` row, computes hit-rate deltas against every other algorithm.

`cacheus_delta_summary.csv`

Aggregates those deltas by baseline algorithm and cache size, and also includes
the baseline's overall mean delta.

### Stage 9: Plot Figures

`plot(rows, deltas, out_dir)` uses matplotlib's non-interactive `Agg` backend and
writes the main pipeline figures:

- `figures/hit_rate_vs_cache_size.png`
- `figures/cacheus_delta_vs_baselines.png`
- `figures/runtime_by_algorithm.png`

The curated result artifact set also includes additional presentation/report
figures generated from the same CSV outputs:

- `figures/mean_hit_rate_bar.png`
- `figures/hit_rate_heatmap.png`
- `figures/cacheus_delta_heatmap.png`
- `figures/runtime_vs_hit_rate.png`
- `figures/cacheus_vs_lirs.png`
- `figures/cacheus_delta_boxplot.png`

The first two figures use a logarithmic x-axis because cache sizes are fractions
spanning two orders of magnitude.

## Simulator Runner Internals

`code/run.py` is generic relative to the CloudVPS wrapper. It does not know about
tar archives or `blkparse`; it only knows about trace files, algorithms, cache
sizes, and output rows.

### Main Config Fields

The runner expects JSON with at least:

- `traces`: files or directories to replay;
- `cache_sizes`: integer sizes or floating fractions;
- `algorithms`: algorithm names supported by `get_algorithm()`.

Common optional fields:

- `output_csv`: append raw result rows here;
- `request_count_type`: `unique` or `reuse`;
- algorithm-specific parameter grids, keyed by algorithm name;
- visualization and pollution flags accepted by algorithm constructors.

### Request Counting

Before running algorithms for a trace, `code/run.py` may replay the entire trace
once to calculate the concrete cache size.

If any configured cache size is a float:

1. `request_count_type` selects a counter:
   - `unique`: use `reader.num_unique()`;
   - `reuse`: use `reader.num_reuse()`.
2. The runner also gets total request count.
3. It sets `window_size = int(0.01 * total)`.
4. For each float cache size, calculates:

   ```text
   concrete_cache_size = floor(cache_size_fraction * count)
   ```

If all cache sizes are integers:

- no pre-count is required for sizing;
- `window_size` defaults to `100`.

For CloudVPS, the pipeline always uses `request_count_type = "unique"`, so
cache size is a fraction of the unique expanded page footprint.

### Skip Rule for Tiny Caches

The runner skips any concrete cache size below `10`:

```text
Cache size < 10 -> skip experiment
```

This prevents running algorithms with invalid or unhelpfully small structures.

### Algorithm Test Loop

For each trace file, concrete cache size, and algorithm:

1. Instantiate `AlgorithmTest`.
2. Build an algorithm instance using:

   ```python
   get_algorithm(name)(cache_size, window_size, **alg_args)
   ```

3. Iterate over `reader.read()`.
4. Call:

   ```python
   op, evicted = alg.request(lba, ts)
   ```

5. Update counters according to `op` and whether the trace request is a write.
6. Print progress.
7. Compute hits as `ios - misses`.
8. Append a CSV row.

### Hit, Miss, Write, and Filter Accounting

The runner recognizes three operation types from `CacheOp`:

- `HIT`
- `INSERT`
- `FILTER`

Accounting behavior:

- `INSERT`: counts as a miss and a write.
- `HIT` with trace write flag true: counts as a write.
- `FILTER`: counts as a miss and a filter.

All default CloudVPS algorithms return only `HIT` or `INSERT`; `FILTER` is
available in the common enum but not used by the default selected algorithms.

Important nuance: in this simulator, `writes` is not simply "number of input
write requests." It is incremented for every inserted block, and also for write
hits. Read misses therefore still increment `writes` because a cache insertion is
modeled as a cache write.

## Trace Reader Details

`code/algs/lib/traces.py` contains the trace abstraction.

`Trace`

- Generic base class.
- Opens the file to determine byte length for progress reporting.
- Maintains:
  - `unique`, a set of seen block IDs;
  - `reuse`, a set of block IDs seen at least twice;
  - `requests`, total emitted requests;
  - `progress`, percentage of file bytes consumed.
- `read()` yields `(lba, write, ts)` from `readLine()`.

`VisaTrace`

- The only supported trace type in this reduced repo.
- Used for `.blk` files.
- Parses converted lines in the `timestamp 0 0 0 lba size op` shape.
- Aligns LBAs to 8-block pages.
- Expands request extents into page-level requests.
- Sets write flag from operation first character: `W` means write.
- Computes a coarse timestamp tick with `tickHour()`.

`identify_trace(filename)`

- Returns `"visa"` for `.blk`.
- Raises for anything else.

`get_trace_reader(trace_type)`

- Returns `VisaTrace` for `"visa"`.
- Raises for anything else.

The README says this reduction intentionally supports only converted CloudVPS
`.blk` traces.

## Shared Utility Data Structures

### `CacheOp`

`code/algs/lib/cacheop.py` defines:

- `CacheOp.HIT`
- `CacheOp.INSERT`
- `CacheOp.FILTER`

Algorithm `request()` methods return one of these values plus an evicted block
identifier or `None`.

### `DequeDict`

`code/algs/lib/dequedict.py` implements an ordered dictionary backed by:

- a Python dict for O(1) key lookup;
- a doubly linked list for ordered head/tail operations.

It supports:

- membership by key;
- indexed get/set/delete by key;
- iteration from head to tail over values;
- `first()` / `popFirst()` for LRU-side access;
- `last()` / `popLast()` for MRU-side access;
- `pushFirst()` for explicit head insertion.

Normal assignment to an existing key removes and re-appends it at the tail. Most
algorithms therefore treat the head as least-recently-used and the tail as
most-recently-used.

### `HeapDict`

`code/algs/lib/heapdict.py` implements a keyed min-heap:

- dict maps key to heap entry;
- heap array stores entries;
- each entry tracks its current heap index.

It supports:

- membership by key;
- indexed get/set/delete by key;
- `min()` without removal;
- `popMin()` with removal.

The priority ordering is delegated to each algorithm's entry class through
`__lt__()`. This is important because LFU, LeCaR, and CACHEUS use different
tie-breaking semantics.

### `Pollutionator`

`code/algs/lib/pollutionator.py` optionally tracks cache pollution. It is off by
default unless `enable_pollution=True` is passed through config.

Conceptually:

- A cached block is marked with the current unique-miss count.
- Once a block has survived for at least `2 * period_length` unique misses
  without reuse, it is considered pollution.
- Pollution is sampled every `period_length` requests.

Algorithms call:

- `incrementUniqueCount()` on misses;
- `setUnique(oblock)` for the requested block;
- `remove(oblock)` when evicting a block;
- `update(time)` to sample pollution.

### `Visualizinator`

`code/algs/lib/visualizinator.py` optionally tracks algorithm internals such as:

- hit rate;
- CACHEUS weights;
- ARC `p`;
- LIRS/CACHEUS queue size.

It is off by default unless `enable_visual=True`. The CloudVPS pipeline does not
enable it; it computes summary figures from final CSV output instead.

### `ProgressBar`

`code/algs/lib/progress_bar.py` prints a simple text progress bar based on the
trace reader's file-byte progress.

## Algorithm Registry

`code/algs/get_algorithm.py` maps these names:

| Name | Class |
| --- | --- |
| `min` | `MIN` |
| `lru` | `LRU` |
| `lfu` | `LFU` |
| `mru` | `MRU` |
| `arc` | `ARC` |
| `lecar` | `LeCaR` |
| `alecar6` | `ALeCaR6` |
| `lirs` | `LIRS` |
| `dlirs` | `DLIRS` |
| `cacheus` | `Cacheus` |
| `arcalecar` | `ARCALeCaR` |
| `lirsalecar` | `LIRSALeCaR` |

If a name is unknown, `get_algorithm()` returns `None`; the runner does not add
an explicit friendly error around that case.

## Implemented Algorithms

### LRU

File: `code/algs/lru.py`

Data structure:

- one `DequeDict` named `lru`.

Behavior:

- Cache hit:
  - retrieve entry;
  - reassign it in `DequeDict`, moving it to MRU position.
- Cache miss:
  - if full, evict `popFirst()` from the LRU side;
  - insert new entry at MRU position.

Complexity:

- O(1) average membership, hit update, insert, and eviction.

Returned operation:

- `HIT` on hit;
- `INSERT` on miss.

### MRU

File: `code/algs/mru.py`

MRU is structurally similar to LRU, but evicts `popLast()` from the MRU side.
Hits still move an entry to MRU position. It is not part of the default
CloudVPS algorithm list but remains available through the runner.

### LFU

File: `code/algs/lfu.py`

Data structure:

- one `HeapDict` named `lfu`.

Entry priority:

- lower frequency is evicted first;
- for equal frequency, the more recent timestamp is considered smaller and is
  evicted first.

That tie-break makes this implementation closer to churn-resistant LFU behavior
than a classic LFU that evicts arbitrary or oldest among equal-frequency items.

Behavior:

- Cache hit:
  - increment frequency;
  - update timestamp;
  - update heap position.
- Cache miss:
  - if full, evict heap minimum;
  - insert with frequency `1`.

Complexity:

- O(log N) for heap updates and eviction.

### ARC

File: `code/algs/arc.py`

ARC, Adaptive Replacement Cache, keeps four LRU lists:

- `T1`: resident entries seen once recently.
- `T2`: resident entries seen at least twice or promoted from history.
- `B1`: nonresident history for entries evicted from `T1`.
- `B2`: nonresident history for entries evicted from `T2`.

It also maintains `p`, the target size for `T1`.

High-level behavior:

- Hit in `T1` or `T2`:
  - move entry into `T2`.
- Miss in `B1`:
  - increase `p`;
  - replace a resident entry;
  - move the requested history entry to `T2`.
- Miss in `B2`:
  - decrease `p`;
  - replace a resident entry;
  - move the requested history entry to `T2`.
- Miss outside all lists:
  - if full, evict according to ARC logic;
  - add new entry to `T1`.

Replacement:

- If `T1` is too large relative to `p`, evict from `T1` and record in `B1`.
- Otherwise evict from `T2` and record in `B2`.

This lets ARC adapt between recency-oriented and frequency-oriented behavior.

### LIRS

File: `code/algs/lirs.py`

LIRS, Low Inter-reference Recency Set, classifies pages as:

- LIR: low inter-reference recency, protected resident pages.
- HIR: high inter-reference recency, less protected pages.

This implementation uses:

- `s`: main recency stack;
- `nr_hirs`: nonresident HIR entries in `s`;
- `q`: resident HIR queue;
- fixed `hirs_ratio`, default `0.01`;
- `hirs_limit = max(2, int(cache_size * hirs_ratio))`;
- `lirs_limit = cache_size - hirs_limit`.

Behavior:

- LIR hit:
  - move to MRU of `s`;
  - prune non-LIR entries from stack bottom if needed.
- HIR hit in `s`:
  - promote to LIR;
  - demote an LIR to HIR if needed;
  - potentially evict a resident HIR if cache is full.
- HIR hit in `q` only:
  - refresh in `q`;
  - add/update in `s`.
- Full miss:
  - evict resident HIR from `q`;
  - insert new page as HIR unless warming up as initial LIR.

The stack is capped so that `len(s) <= 2 * cache_size` by removing old
nonresident HIRs.

### DLIRS

File: `code/algs/dlirs.py`

DLIRS is a dynamic variant of LIRS. It uses:

- `lirs`: a DequeDict containing LIRs and HIRs;
- `hirs`: a DequeDict to find HIRs quickly;
- `q`: resident HIR queue;
- adaptive `hirs_limit` and `lirs_limit`;
- counters for demoted and nonresident pages.

The important difference from basic LIRS is `adjustSize()`:

- if a nonresident HIR is hit, increase HIR space;
- if a demoted resident HIR is hit, increase LIR space.

DLIRS is not part of the default CloudVPS run, but it is available in the
registry.

### LeCaR

File: `code/algs/lecar.py`

LeCaR combines LRU and LFU with online learning.

Data structures:

- `lru`: DequeDict for recency.
- `lfu`: HeapDict for frequency.
- `lru_hist`: history of entries evicted by the LRU expert.
- `lfu_hist`: history of entries evicted by the LFU expert.

Parameters:

- `history_size = cache_size // 2`;
- `initial_weight = 0.5`;
- `learning_rate = 0.45`;
- `discount_rate = 0.005 ** (1 / cache_size)`.

Weights:

- `W[0]`: probability of choosing LRU expert.
- `W[1]`: probability of choosing LFU expert.

Eviction:

1. Candidate from LRU is `lru.first()`.
2. Candidate from LFU is `lfu.min()`.
3. Randomly select policy according to `W`.
4. If both candidates are the same object, evict it and do not blame either
   expert later (`policy = -1`).
5. Otherwise evict the selected candidate.
6. Store evicted metadata in the selected expert's history.

Learning:

- On a later miss to an item found in `lru_hist`, penalize LRU.
- On a later miss to an item found in `lfu_hist`, penalize LFU.
- Penalty magnitude decays with time since eviction:

  ```text
  -(discount_rate ** (current_time - evicted_time))
  ```

- Weights are updated multiplicatively:

  ```text
  W = W * exp(learning_rate * reward)
  W = W / sum(W)
  ```

- Weights are clamped to `[0.01, 0.99]`.

### ALeCaR6

File: `code/algs/alecar6.py`

ALeCaR6 is an adaptive-learning-rate LeCaR variant. It keeps the same broad
LRU/LFU two-expert model but replaces LeCaR's fixed learning rate and discount
reward with a dynamic learning-rate object.

Learning-rate initialization:

```text
sqrt((2 * log(2)) / cache_size)
```

The learning rate is bounded to `[0.001, 1]`.

Every `cache_size` requests:

- compute current hit rate over the last period;
- compare it with previous period hit rate;
- compare the direction of learning-rate change with hit-rate change;
- keep moving in the same direction if performance improved;
- reverse or reduce movement if performance worsened;
- randomly perturb if performance keeps degrading without clear gradient;
- reset after repeated zero or negative hit-rate changes.

This pattern is reused by `Cacheus`, `ARCALeCaR`, and `LIRSALeCaR`.

### CACHEUS

File: `code/algs/cacheus.py`

This is the core algorithm for the repository. It implements the CACHEUS
SR-LRU/CR-LFU style policy described in the paper.

#### Core State

Cache partitions:

- `s`: scan-resistant/reuse partition, a DequeDict.
- `q`: probationary or lower-protection partition, a DequeDict.

Frequency expert:

- `lfu`: HeapDict over all resident entries.

Histories:

- `lru_hist`: entries evicted by the SR-LRU/LRU-side expert.
- `lfu_hist`: entries evicted by the LFU-side expert.

Learning:

- `W[0]`: probability of selecting LRU/SR-LRU-side eviction.
- `W[1]`: probability of selecting LFU/CR-LFU-side eviction.
- `learning_rate`: adaptive `Cacheus_Learning_Rate`.

Partition sizing:

- `q_limit = max(1, int((0.01 * cache_size) + 0.5))`.
- `s_limit = cache_size - q_limit`.
- `q_size` and `s_size` track current resident counts.

Adaptation counters:

- `dem_count`: count of items demoted from `s` to `q`.
- `nor_count`: count of new items in LRU history.

Entry fields:

- `oblock`: page-aligned logical block ID.
- `freq`: access frequency.
- `time`: last access or insertion time.
- `evicted_time`: time of eviction.
- `is_demoted`: whether the item was demoted from `s` to `q`.
- `is_new`: whether the item was inserted as a new item.

#### CR-LFU Tie-Breaking

`Cacheus_Entry.__lt__()` compares entries for the LFU heap:

1. Lower frequency has higher eviction priority.
2. If frequencies are equal, larger `time` has higher eviction priority.

Because larger `time` means more recent, equal-frequency ties evict the most
recent item. This is the CR-LFU idea: when a churn pattern gives many entries the
same frequency, evicting the MRU among the least-frequent entries can lock a
stable subset in cache and reduce churn.

#### Hit in `s`

`hitinS(oblock)`:

1. Update entry time to current time.
2. Move entry to MRU of `s`.
3. Increment frequency.
4. Update LFU heap position.

This is a protected hit.

#### Hit in `q`

`hitinQ(oblock)`:

1. Update time.
2. Increment frequency and update LFU heap.
3. If the entry was demoted:
   - call `adjustSize(True)`;
   - clear `is_demoted`;
   - decrement `dem_count`.
4. Remove from `q`.
5. If `s` is at or above target size:
   - demote the LRU item from `s`;
   - mark it demoted;
   - move it to `q`.
6. Move the hit entry into MRU of `s`.

This means a reused item in the probationary partition earns promotion into the
protected partition. If a demoted item is hit, the algorithm treats that as
evidence that `s` was too small.

#### Adding to Cache

`addToS(oblock, freq, isNew=True)`:

- creates an entry;
- inserts into `s`;
- inserts into LFU heap;
- increments `s_size`.

`addToQ(oblock, freq, isNew=True)`:

- creates an entry;
- inserts into `q`;
- inserts into LFU heap;
- increments `q_size`.

New cold misses usually go to `q`. History hits go to `s`.

#### History Management

`addToHistory(x, policy)`:

- policy `0`: add to `lru_hist`;
- policy `1`: add to `lfu_hist`;
- policy `-1`: no history update.

Each history has capacity `history_size = cache_size // 2`.

If adding to `lru_hist` and `x.is_new`, `nor_count` increments. If an old
history entry is removed from `lru_hist` and it was new, `nor_count` decrements.

The distinction between new and non-new items feeds partition-size adaptation.

#### Eviction

`evict()` compares two eviction candidates:

- LRU/SR-LRU-side candidate: `getLRU(self.q)`, the LRU item in `q`.
- LFU/CR-LFU-side candidate: `getHeapMin()`, the heap minimum.

Then:

1. Choose policy `0` or `1` randomly according to weights `W`.
2. If both candidates are the same object, evict it with `policy = -1`.
3. If policy `0`, remove victim from `q`.
4. If policy `1`, remove victim from whichever partition contains it.
5. If victim was demoted, decrement `dem_count`.
6. Remove victim from LFU heap.
7. Record `evicted_time`.
8. Remove from pollution tracker.
9. Add to the selected history unless policy is `-1`.

This is where the two experts compete:

- SR-LRU says "evict the oldest item in the probationary scan-resistant area."
- CR-LFU says "evict the least frequent item, with MRU tie-break."

#### Weight Updates

`adjustWeights(rewardLRU, rewardLFU)`:

```text
reward = [rewardLRU, rewardLFU]
W = W * exp(learning_rate * reward)
W = W / sum(W)
```

Then clamp:

- if `W[0] >= 0.99`, set `[0.99, 0.01]`;
- if `W[1] >= 0.99`, set `[0.01, 0.99]`.

In this implementation, history hits apply a direct `-1` penalty to the expert
whose history contained the requested page. Unlike `LeCaR`, there is no discount
rate based on elapsed time.

#### Partition-Size Adaptation

`adjustSize(hit_in_Q)`:

If `hit_in_Q` is true:

- a demoted item in `q` was reused;
- infer that `s` should be larger;
- increase `s_limit` by roughly `nor_count / dem_count`;
- recompute `q_limit`.

If `hit_in_Q` is false:

- a new item was evicted into history and then reused;
- infer that `q` was too small for new items to survive until reuse;
- increase `q_limit` by roughly `dem_count / nor_count`;
- recompute `s_limit`.

Both updates use `max(1, ...)` and clamp the growing partition to at most
`cache_size - 1`, so neither partition can consume the entire cache.

`limitStack()` enforces the current target:

- while `s_size >= s_limit`, pop the LRU item from `s`;
- mark it demoted;
- move it into `q`.

#### Miss Handling

`miss(oblock)` has three main cases:

1. Warmup into `s`:
   - if `s` is below limit and `q` is empty, add to `s` as not new.
2. Fill `q`:
   - if total cache is not full and `q` is below limit, add to `q` as not new.
3. Normal full or near-full behavior:
   - evict if cache is full;
   - add new item to `q` with `is_new=True`;
   - call `limitStack()`.

The request method handles history hits before calling normal `miss()`:

- hit in `lru_hist`: penalize LRU/SR-LRU expert, possibly adjust `q`, insert
  into `s`.
- hit in `lfu_hist`: penalize LFU expert, insert into `s`.
- miss in both histories: normal cold miss.

Implementation note: both `hitinLRUHist()` and `hitinLFUHist()` compute
`freq = entry.freq + 1`, but then pass `entry.freq` to `addToS()`. The document
describes the code as written; the unused local `freq` looks like a leftover or
bug candidate.

#### Adaptive Learning Rate

`Cacheus_Learning_Rate` tracks hit rate over windows of length `cache_size`.

Initial value:

```text
sqrt((2 * log(2)) / cache_size)
```

At each period boundary:

1. `hitrate_curr = hits_in_period / cache_size`.
2. `hitrate_diff = hitrate_curr - previous_hitrate`.
3. `delta_LR = current_learning_rate - previous_learning_rate`.
4. If learning-rate movement and hit-rate movement have the same sign, continue
   in that direction.
5. If signs differ, move the learning rate in the opposite direction.
6. If no clear gradient and hit rate is flat or declining, count zero/negative
   periods.
7. After repeated bad periods, reset to the initial learning rate.
8. Otherwise sometimes perturb randomly up or down.

Bounds:

- minimum `0.001`;
- maximum `1`.

#### Request Flow

For each page request:

1. Increment logical time.
2. Optionally record weights and `q_size` for visualization.
3. Update adaptive learning rate.
4. If page is in `s`, process `hitinS()`.
5. Else if page is in `q`, process `hitinQ()`.
6. Else if page is in `lru_hist`, process `hitinLRUHist()`.
7. Else if page is in `lfu_hist`, process `hitinLFUHist()`.
8. Else process normal miss.
9. Record hit-rate window sample if visualization is enabled.
10. If hit, increment learning-rate period hit counter.
11. Update pollution tracker.
12. Return `HIT` or `INSERT`.

### ARCALeCaR

File: `code/algs/arcalecar.py`

This variant combines ARC and LFU under the ALeCaR-style adaptive learning
framework.

It wraps modified nested versions of:

- ARC, with methods to inspect next victim and evict a specific block;
- LFU, with methods to inspect next victim and force frequency on insertion.

It keeps a combined history to assign blame to ARC or LFU when an evicted item
returns. It is not selected by the default CloudVPS pipeline.

### LIRSALeCaR

File: `code/algs/lirsalecar.py`

This variant combines a custom nested LIRS implementation with LFU under an
adaptive learning framework.

It maintains:

- nested LIRS state (`SStack`, `QStack`, `nonresidentHIRsInS`);
- LFU heap;
- LFU eviction history;
- adaptive expert weights.

It is more complex than the main `lirs.py` and `cacheus.py` implementations and
is not part of the default CloudVPS pipeline.

### MIN

File: `code/algs/min.py`

This appears to be an attempt at Belady-style optimal replacement bookkeeping,
but it is not a conventional offline MIN implementation that precomputes future
references. It maintains request indices and counts to infer completeness. It is
available in the registry but not used by the CloudVPS pipeline.

## Current CloudVPS Result Artifacts

The curated `results/cloudvps/` artifacts summarize a full local run over 18
converted traces, 5 cache-size fractions, and 6 algorithms:

```text
18 traces * 5 cache sizes * 6 algorithms = 540 experiment rows
```

The full normalized result table, `cloudvps_results.csv`, has 541 lines
including header in the local generated output. That file is useful for
regeneration and inspection, but it is treated as a generated artifact rather
than part of the curated tracked set.

### Conversion Summary

The current conversion summary includes 18 traces. Examples:

| Trace | Decoded lines | Kept Q events | Skipped lines |
| --- | ---: | ---: | ---: |
| `vps26020` | 761,730 | 380,474 | 381,256 |
| `vps26107` | 12,919,516 | 6,451,272 | 6,468,244 |
| `vps26535` | 9,448,030 | 4,723,699 | 4,724,331 |

The kept/skipped split is close to half for these traces because both queue and
completion-style block events appear in the decoded files, and only queue events
are kept.

### Mean Hit Rate by Algorithm

Current `summary_by_algorithm.csv`:

| Algorithm | Mean hit rate | Median hit rate | Min | Max | Runs | Total runtime sec |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `arc` | 26.538778 | 22.015 | 2.64 | 82.85 | 90 | 2401.32 |
| `cacheus` | 28.060111 | 23.37 | 2.74 | 84.97 | 90 | 7619.93 |
| `lecar` | 25.439 | 19.79 | 2.46 | 84.2 | 90 | 6559.1 |
| `lfu` | 20.030889 | 17.065 | 1.1 | 58.96 | 90 | 6517.73 |
| `lirs` | 28.076889 | 22.445 | 1.65 | 84.84 | 90 | 2787.68 |
| `lru` | 22.128556 | 15.555 | 2.47 | 81.61 | 90 | 1655.76 |

In this run, CACHEUS and LIRS have nearly identical overall mean hit rates, with
LIRS ahead by about `0.016778` percentage points on average. CACHEUS is still
ahead of ARC, LeCaR, LFU, and LRU on mean hit rate.

### CACHEUS Delta Summary

Current `cacheus_delta_summary.csv` reports mean CACHEUS hit-rate differences in
percentage points:

| Baseline | Overall mean delta pp |
| --- | ---: |
| `arc` | 1.521333 |
| `lecar` | 2.621111 |
| `lfu` | 8.029222 |
| `lirs` | -0.016778 |
| `lru` | 5.931556 |

By cache size, CACHEUS beats LIRS at `0.001`, `0.005`, `0.01`, and `0.05`, but
trails LIRS at `0.1` by about `1.704444` percentage points in the current run.

### Runtime Interpretation

The runtime totals reflect Python implementation cost, not just algorithmic
complexity:

- LRU is fastest among default algorithms.
- ARC and LIRS are moderate.
- LFU, LeCaR, and CACHEUS are slower because they maintain heap and/or learning
  structures.
- CACHEUS is slowest in the current summary because it maintains SR-LRU-like
  partitions, LFU heap state, histories, adaptive weights, and learning-rate
  bookkeeping.

## Important Design Choices and Semantics

### CloudVPS Is the Only Supported Dataset in the Active Workflow

The trace reader now raises if a file is not `.blk`, and the README frames this
as a CloudVPS-only reproduction. The original simulator may have had broader
trace support historically, but this checkout has been reduced.

### Queue Events Only

The pipeline filters for `Q` events to avoid double-counting I/O completions.
This is a deliberate semantic choice and affects every downstream hit-rate.

### Cache Size Is Based on Expanded Unique Pages

The cache size fraction is not based on:

- archive size;
- decoded line count;
- kept queue-event count;
- raw sector footprint.

It is based on `VisaTrace.num_unique()`, after `.blk` events are expanded into
8-sector page-aligned requests.

### Algorithms Replay Traces in Original Order

The conversion stage preserves decoded event order. The simulator reads files
linearly and expands each request immediately. There is no shuffling,
parallel replay, sorting, or timestamp-based reordering.

### Randomness Is Seeded

Learning algorithms call `np.random.seed(123)` in their constructors. This makes
their random expert choices reproducible for a given run order.

### Visualization and Pollution Tracking Are Mostly Dormant

Most algorithms construct `Visualizinator` and `Pollutionator`, but both are
disabled by default unless config enables them. The CloudVPS pipeline does not
enable them. As a result:

- `avg_pollution` is normally blank;
- visual time-series are not emitted by the algorithms;
- pipeline figures are based on final CSV rows, not `Visualizinator`.

### Histories Store Metadata, Not Cached Data

ARC, LIRS, LeCaR, and CACHEUS all use some form of nonresident metadata. These
history entries do not represent cache hits. They are used to learn from misses:
if an item returns while still in history, the algorithm infers that the prior
eviction decision was bad or that a partition is incorrectly sized.

### The Simulator Models Cache Writes on Insertion

Every `INSERT` increments `writes`, even for read requests. This is consistent
with modeling a cache fill/write into cache storage, but it means the `writes`
column should not be interpreted as raw workload write count.

## Code-Level Quirks and Risks

These are not necessarily fatal, but they matter for future maintenance.

1. `visualizinator.py` imports matplotlib at module import time.

   Even if visualization is disabled, importing algorithms imports
   `Visualizinator`, which imports matplotlib. Environments without matplotlib
   will fail before reaching the pipeline's plotting stage.

2. `get_algorithm()` returns `None` for unknown names.

   The runner will later try to call `None` as a class. A clearer error would be
   easier to debug.

3. `Cacheus.hitinLRUHist()` and `Cacheus.hitinLFUHist()` compute an incremented
   `freq` but do not use it.

   The code currently reinserts with `entry.freq`, not `entry.freq + 1`. That
   may be an accidental difference from LeCaR/ALeCaR-style handling.

4. `Cacheus.limitStack()` demotes while `s_size >= s_limit`.

   This enforces `s_size < s_limit`, not `s_size <= s_limit`. It may be
   intentional for this code's target sizing, but it is worth knowing when
   reasoning about partition counts.

5. `LIRS.request()` suppresses repeated immediate requests to the same block.

   It uses `last_oblock` and only updates LIRS structures if the requested block
   differs from the previous block. Hit/miss accounting still treats repeated
   resident requests as hits, but internal recency updates are skipped for
   back-to-back identical page requests.

6. `MIN` is not a standard future-aware optimal algorithm implementation.

   Treat it cautiously if using it for comparisons.

7. There are no tests in this reduced repo.

   The generated results demonstrate that the pipeline has run in this checkout,
   but there is no automated test suite protecting behavior.

8. Generated bytecode exists in the workspace.

   `__pycache__` files are ignored and should not be committed.

## How to Reason About a Single Request in the Default Pipeline

Suppose a raw CloudVPS trace contains:

```text
253,941  1  1  0.000000000 30387  Q  W 104160 + 8 [blkback.9.xvda1]
```

The pipeline:

1. Parses it as a valid queue event.
2. Writes:

   ```text
   0.000000000 0 0 0 104160 8 W
   ```

The trace reader:

1. Reads timestamp `0.000000000`, LBA `104160`, size `8`, op `W`.
2. Aligns to an 8-sector page. This LBA is already aligned.
3. Emits one request:

   ```text
   (104160, True, ts_hour)
   ```

The runner:

1. Calls `alg.request(104160, ts_hour)`.
2. If algorithm returns `INSERT`, increments misses and writes.
3. If algorithm returns `HIT` and the write flag is true, increments writes.
4. Updates progress.

For CACHEUS:

1. If `104160` is in `s`, it is a protected hit and frequency increases.
2. Else if in `q`, it is promoted to `s`, possibly adjusting partition sizes.
3. Else if in `lru_hist`, CACHEUS penalizes the SR-LRU expert and reinserts into
   `s`.
4. Else if in `lfu_hist`, CACHEUS penalizes the CR-LFU expert and reinserts into
   `s`.
5. Else it is a cold miss and is inserted according to warmup/full-cache logic.

## How to Extend or Modify the Project

### Add a New Algorithm

1. Create `code/algs/<name>.py`.
2. Define a class with constructor:

   ```python
   def __init__(self, cache_size, window_size, **kwargs):
   ```

3. Define:

   ```python
   def request(self, oblock, ts):
       return CacheOp.HIT or CacheOp.INSERT or CacheOp.FILTER, evicted
   ```

4. Add the class to `code/algs/get_algorithm.py`.
5. Add the name to `ALGORITHMS` in `cloudvps_pipeline.py` if it should be part
   of the default CloudVPS reproduction.

### Add Algorithm Parameters

`code/run.py` supports simple parameter grids. If config contains a key matching
the algorithm name, and that key maps parameter names to lists of values, the
runner runs the Cartesian product of those values.

Example shape:

```json
{
  "algorithms": ["lirs"],
  "lirs": {
    "hirs_ratio": [0.01, 0.05]
  }
}
```

The CloudVPS pipeline currently writes a fixed internal config and does not
expose parameter-grid CLI flags.

### Add Another Dataset

This reduced repo would need more than a new path:

- `identify_trace()` and `get_trace_reader()` currently reject non-`.blk` input.
- The pipeline is CloudVPS-specific and assumes `vps*.tar.gz` or `vps*`
  directories.
- Conversion currently assumes `blkparse` output shape.
- README and result naming are CloudVPS-specific.

Adding a dataset cleanly would mean adding a separate pipeline or generalizing
the current one while preserving the CloudVPS defaults.

## Mental Model of the Whole System

The project is best understood as a trace-replay experiment harness:

```text
CloudVPS blktrace archives
        |
        v
safe extraction
        |
        v
blkparse decoded text
        |
        v
Q-event filter and .blk conversion
        |
        v
VisaTrace page-aligned request expansion
        |
        v
code/run.py experiment matrix
        |
        v
algorithm.request(page, timestamp)
        |
        v
hit/miss/write/filter counters
        |
        v
raw CSV rows
        |
        v
normalized CSV, summaries, CACHEUS deltas, figures
```

CACHEUS itself is best understood as a two-expert online learner:

```text
request page
   |
   +-- resident in protected S? hit, refresh recency/frequency
   |
   +-- resident in probationary Q? hit, promote, maybe resize S/Q
   |
   +-- nonresident but in LRU history? miss, penalize SR-LRU, maybe resize Q
   |
   +-- nonresident but in LFU history? miss, penalize CR-LFU
   |
   +-- cold miss? insert, evict if needed

eviction when full:
   |
   +-- SR-LRU candidate: LRU item in Q
   +-- CR-LFU candidate: least-frequent item, MRU tie-break
   +-- choose candidate according to learned weights
   +-- store evicted metadata in the chosen expert's history
```

The repository's purpose is therefore not to provide a production cache. It is a
research/simulation reproduction: decode storage traces, replay page requests
through cache policies, and compare hit-rate behavior across cache sizes.
