#!/usr/bin/env python3
"""Offline CloudVPS-only CACHEUS reproduction pipeline."""

import argparse
import csv
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ALGORITHMS = ["lru", "lfu", "arc", "lirs", "lecar", "cacheus"]
CACHE_SIZES = [0.001, 0.005, 0.01, 0.05, 0.1]
REQUEST_COUNT_TYPE = "unique"
EVENT_FILTER = "Q"

RESULT_COLUMNS = [
    "trace_file",
    "trace_type",
    "algorithm",
    "hits",
    "misses",
    "writes",
    "filters",
    "cache_size",
    "cache_size_label",
    "cache_size_label_type",
    "hit_rate",
    "avg_pollution",
    "runtime_sec",
]


class PipelineError(RuntimeError):
    pass


def repo_root():
    return Path(__file__).resolve().parent


def project_path(path):
    path = Path(path)
    return path if path.is_absolute() else repo_root() / path


def shown(path):
    try:
        return str(Path(path).resolve().relative_to(repo_root()))
    except ValueError:
        return str(path)


def rel_to_repo(path):
    return os.path.relpath(Path(path).resolve(), repo_root())


def parse_args():
    parser = argparse.ArgumentParser(description="Run the offline CloudVPS CACHEUS pipeline.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/cloudvps_raw"))
    parser.add_argument("--work-dir", type=Path, default=Path("work/cloudvps"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/cloudvps"))
    return parser.parse_args()


def safe_extract(archive, dest):
    dest = Path(dest)
    dest_root = dest.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                raise PipelineError(f"Refusing archive link member: {member.name}")
            target = (dest / member.name).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise PipelineError(f"Refusing archive path outside work dir: {member.name}")
        tar.extractall(dest)


def find_blktrace0(trace_dir):
    expected = trace_dir / f"{trace_dir.name}.blktrace.0"
    if expected.exists():
        return expected
    matches = sorted(trace_dir.glob("*.blktrace.0"))
    return matches[0] if len(matches) == 1 else None


def prepare_inputs(raw_dir, extracted_dir):
    archives = sorted(raw_dir.glob("vps*.tar.gz"))
    for archive in archives:
        print(f"Extracting {shown(archive)}")
        safe_extract(archive, extracted_dir)

    trace_dirs = {}
    for root in [raw_dir, extracted_dir]:
        if root.exists() and root.name.startswith("vps"):
            trace_dirs[root.name] = root
        if root.exists():
            for path in sorted(root.rglob("vps*")):
                if path.is_dir():
                    trace_dirs.setdefault(path.name, path)

    targets = []
    for name, trace_dir in sorted(trace_dirs.items()):
        blktrace0 = find_blktrace0(trace_dir)
        if blktrace0:
            targets.append((name, blktrace0))
        else:
            print(f"Skipping {shown(trace_dir)}: no unique .blktrace.0")

    if not targets:
        raise PipelineError(f"No local CloudVPS traces found under {shown(raw_dir)}")
    return targets


def decode_traces(targets, decoded_dir):
    blkparse = shutil.which("blkparse")
    if not blkparse:
        raise PipelineError("blkparse not found on PATH. Install blktrace/blkparse and rerun.")

    decoded = []
    for name, blktrace0 in targets:
        out_path = decoded_dir / f"{name}.blkparse.txt"
        print(f"Decoding {shown(blktrace0)}")
        with out_path.open("w", encoding="utf-8") as out:
            try:
                subprocess.run(
                    [blkparse, "-i", str(blktrace0)],
                    stdout=out,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                detail = f": {exc.stderr.strip()}" if exc.stderr else ""
                raise PipelineError(f"blkparse failed for {shown(blktrace0)}{detail}")
        decoded.append((name, out_path))

    print(f"Decoded {len(decoded)} trace(s).")
    return decoded


def parse_blkparse_line(line):
    fields = line.split()
    if len(fields) < 10:
        return None
    timestamp, action, op, lba, plus, size = fields[3], fields[5], fields[6], fields[7], fields[8], fields[9]
    if action != EVENT_FILTER or plus != "+" or not op:
        return None
    try:
        timestamp_value = float(timestamp)
        lba_value = int(lba)
        size_value = int(size)
    except ValueError:
        return None
    if not math.isfinite(timestamp_value) or lba_value < 0 or size_value <= 0:
        return None
    return timestamp, lba_value, size_value, op[0].upper()


def convert_traces(decoded, converted_dir, out_dir):
    converted = []
    summary_path = out_dir / "conversion_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as summary:
        writer = csv.DictWriter(
            summary,
            fieldnames=[
                "trace_name",
                "decoded_path",
                "converted_path",
                "total_decoded_lines",
                "kept_q_events",
                "skipped_lines",
            ],
        )
        writer.writeheader()

        for name, decoded_path in decoded:
            converted_path = converted_dir / f"{name}.blk"
            total = kept = 0
            with decoded_path.open("r", encoding="utf-8", errors="replace") as source:
                with converted_path.open("w", encoding="utf-8") as dest:
                    for line in source:
                        total += 1
                        parsed = parse_blkparse_line(line)
                        if not parsed:
                            continue
                        timestamp, lba, size, op = parsed
                        # VisaTrace expects: timestamp, three ignored fields, LBA, size, operation.
                        dest.write(f"{timestamp} 0 0 0 {lba} {size} {op}\n")
                        kept += 1

            writer.writerow(
                {
                    "trace_name": name,
                    "decoded_path": shown(decoded_path),
                    "converted_path": shown(converted_path),
                    "total_decoded_lines": total,
                    "kept_q_events": kept,
                    "skipped_lines": total - kept,
                }
            )
            if kept:
                converted.append(converted_path)

    if not converted:
        raise PipelineError("No converted .blk file contains valid Q events.")
    print(f"Converted {len(converted)} trace(s).")
    return converted


def write_runner_config(converted, work_dir, raw_results):
    config_path = work_dir / ".cacheus_cloudvps_runner.config.json"
    config = {
        "output_csv": rel_to_repo(raw_results),
        "cache_sizes": CACHE_SIZES,
        "traces": [rel_to_repo(path) for path in converted],
        "request_count_type": REQUEST_COUNT_TYPE,
        "algorithms": ALGORITHMS,
    }
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    return config_path


def run_simulator(config_path, raw_results, work_dir):
    if raw_results.exists():
        raw_results.unlink()
    log_path = raw_results.with_name("cloudvps_runner.log")
    mpl_config = work_dir / "matplotlib"
    mpl_config.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(mpl_config)

    print(f"Running existing CACHEUS simulator: code/run.py")
    print(f"Runner log: {shown(log_path)}")

    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "code/run.py", rel_to_repo(config_path)],
            cwd=repo_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        assert process.stdout is not None
        while True:
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            log.write(chunk)
            log.flush()

    return_code = process.wait()
    if return_code:
        raise PipelineError(f"Simulation failed with exit code {return_code}; see {shown(log_path)}")
    if not raw_results.exists() or raw_results.stat().st_size == 0:
        raise PipelineError(f"Simulator did not produce non-empty {shown(raw_results)}")


def read_results(raw_results, out_dir):
    with raw_results.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row]
    if not rows:
        raise PipelineError("Simulator result CSV is empty.")

    extra_count = max(len(row) for row in rows) - len(RESULT_COLUMNS)
    headers = RESULT_COLUMNS + [f"extra_{idx}" for idx in range(1, max(0, extra_count) + 1)]
    rows = [row + [""] * (len(headers) - len(row)) for row in rows]
    dict_rows = [dict(zip(headers, row)) for row in rows]

    out_path = out_dir / "cloudvps_results.csv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return dict_rows


def fnum(value):
    if value in ("", "None", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def grouped(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return groups


def mean(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else None


def write_dicts(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze(rows, out_dir):
    by_alg = []
    for (algorithm,), items in sorted(grouped(rows, ["algorithm"]).items()):
        hit_rates = [fnum(row["hit_rate"]) for row in items]
        runtimes = [fnum(row["runtime_sec"]) for row in items if fnum(row["runtime_sec"]) is not None]
        hit_rates = [value for value in hit_rates if value is not None]
        if hit_rates:
            by_alg.append(
                {
                    "algorithm": algorithm,
                    "mean_hit_rate": round(statistics.mean(hit_rates), 6),
                    "median_hit_rate": round(statistics.median(hit_rates), 6),
                    "min_hit_rate": round(min(hit_rates), 6),
                    "max_hit_rate": round(max(hit_rates), 6),
                    "run_count": len(hit_rates),
                    "total_runtime_sec": round(sum(runtimes), 6) if runtimes else "",
                }
            )
    write_dicts(
        out_dir / "summary_by_algorithm.csv",
        ["algorithm", "mean_hit_rate", "median_hit_rate", "min_hit_rate", "max_hit_rate", "run_count", "total_runtime_sec"],
        by_alg,
    )

    by_size = []
    size_groups = grouped(rows, ["algorithm", "cache_size_label", "cache_size_label_type"])
    for key, items in sorted(size_groups.items(), key=lambda item: (item[0][0], fnum(item[0][1]) or 0)):
        algorithm, label, label_type = key
        hit_rate = mean(fnum(row["hit_rate"]) for row in items)
        if hit_rate is not None:
            by_size.append(
                {
                    "algorithm": algorithm,
                    "cache_size_label": label,
                    "cache_size_label_type": label_type,
                    "mean_hit_rate": round(hit_rate, 6),
                    "run_count": len(items),
                }
            )
    write_dicts(
        out_dir / "summary_by_cache_size.csv",
        ["algorithm", "cache_size_label", "cache_size_label_type", "mean_hit_rate", "run_count"],
        by_size,
    )

    deltas = cacheus_deltas(rows)
    write_dicts(
        out_dir / "cacheus_vs_baselines.csv",
        [
            "trace_file",
            "cache_size",
            "cache_size_label",
            "cache_size_label_type",
            "baseline_algorithm",
            "cacheus_hit_rate",
            "baseline_hit_rate",
            "hit_rate_delta_pp",
        ],
        deltas,
    )

    overall = {
        baseline: mean(fnum(row["hit_rate_delta_pp"]) for row in items)
        for (baseline,), items in grouped(deltas, ["baseline_algorithm"]).items()
    }
    delta_summary = []
    delta_groups = grouped(deltas, ["baseline_algorithm", "cache_size_label", "cache_size_label_type"])
    for key, items in sorted(delta_groups.items(), key=lambda item: (item[0][0], fnum(item[0][1]) or 0)):
        baseline, label, label_type = key
        delta = mean(fnum(row["hit_rate_delta_pp"]) for row in items)
        if delta is not None:
            delta_summary.append(
                {
                    "baseline_algorithm": baseline,
                    "cache_size_label": label,
                    "cache_size_label_type": label_type,
                    "mean_delta_pp": round(delta, 6),
                    "run_count": len(items),
                    "overall_mean_delta_pp": round(overall[baseline], 6) if overall[baseline] is not None else "",
                }
            )
    write_dicts(
        out_dir / "cacheus_delta_summary.csv",
        ["baseline_algorithm", "cache_size_label", "cache_size_label_type", "mean_delta_pp", "run_count", "overall_mean_delta_pp"],
        delta_summary,
    )
    return deltas


def cacheus_deltas(rows):
    out = []
    for key, items in grouped(rows, ["trace_file", "cache_size_label", "cache_size_label_type"]).items():
        trace_file, label, label_type = key
        by_alg = {row["algorithm"].lower(): row for row in items}
        cacheus = by_alg.get("cacheus")
        cacheus_hit = fnum(cacheus["hit_rate"]) if cacheus else None
        if cacheus_hit is None:
            continue
        for algorithm, row in sorted(by_alg.items()):
            if algorithm == "cacheus":
                continue
            baseline_hit = fnum(row["hit_rate"])
            if baseline_hit is None:
                continue
            out.append(
                {
                    "trace_file": trace_file,
                    "cache_size": cacheus["cache_size"],
                    "cache_size_label": label,
                    "cache_size_label_type": label_type,
                    "baseline_algorithm": row["algorithm"],
                    "cacheus_hit_rate": round(cacheus_hit, 6),
                    "baseline_hit_rate": round(baseline_hit, 6),
                    "hit_rate_delta_pp": round(cacheus_hit - baseline_hit, 6),
                }
            )
    return out


def plot(rows, deltas, out_dir):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise PipelineError("matplotlib is required for figures.") from exc

    figures = out_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    plot_lines(
        plt,
        rows,
        ["algorithm", "cache_size_label"],
        "hit_rate",
        figures / "hit_rate_vs_cache_size.png",
        "Mean hit rate (%)",
        "CloudVPS hit rate vs cache size",
    )
    plot_lines(
        plt,
        deltas,
        ["baseline_algorithm", "cache_size_label"],
        "hit_rate_delta_pp",
        figures / "cacheus_delta_vs_baselines.png",
        "CACHEUS delta (percentage points)",
        "CACHEUS vs baselines on CloudVPS",
        zero_line=True,
    )
    plot_runtime(plt, rows, figures / "runtime_by_algorithm.png")
    plot_mean_hit_rate_bar(plt, rows, figures / "mean_hit_rate_bar.png")
    plot_hit_rate_heatmap(plt, rows, figures / "hit_rate_heatmap.png")
    plot_cacheus_delta_heatmap(plt, deltas, figures / "cacheus_delta_heatmap.png")
    plot_runtime_vs_hit_rate(plt, rows, figures / "runtime_vs_hit_rate.png")
    plot_cacheus_vs_lirs(plt, rows, figures / "cacheus_vs_lirs.png")
    plot_cacheus_delta_boxplot(plt, deltas, figures / "cacheus_delta_boxplot.png")


def plot_lines(plt, rows, keys, value_key, path, ylabel, title, zero_line=False):
    series = defaultdict(list)
    for key, items in grouped(rows, keys).items():
        name, label = key
        x = fnum(label)
        y = mean(fnum(row[value_key]) for row in items)
        if x is not None and y is not None:
            series[name].append((x, y))

    fig, ax = plt.subplots(figsize=(8, 5))
    if zero_line:
        ax.axhline(0, color="black", linewidth=0.8)
    for name in sorted(series):
        points = sorted(series[name])
        ax.plot([x for x, _ in points], [y for _, y in points], marker="o", label=name)
    ax.set_xscale("log")
    ax.set_xlabel("Cache size fraction")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, which="both", linestyle=":", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_runtime(plt, rows, path):
    totals = {}
    for (algorithm,), items in grouped(rows, ["algorithm"]).items():
        runtime = sum(fnum(row["runtime_sec"]) or 0 for row in items)
        if runtime:
            totals[algorithm] = runtime
    if not totals:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = sorted(totals)
    ax.bar(labels, [totals[label] for label in labels])
    ax.set_xlabel("Algorithm")
    ax.set_ylabel("Total runtime (sec)")
    ax.set_title("CloudVPS runtime by algorithm")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_mean_hit_rate_bar(plt, rows, path):
    values = {}
    for (algorithm,), items in grouped(rows, ["algorithm"]).items():
        hit_rate = mean(fnum(row["hit_rate"]) for row in items)
        if hit_rate is not None:
            values[algorithm] = hit_rate
    if not values:
        return

    labels = sorted(values, key=values.get, reverse=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, [values[label] for label in labels])
    ax.set_xlabel("Algorithm")
    ax.set_ylabel("Mean hit rate (%)")
    ax.set_title("CloudVPS mean hit rate by algorithm")
    ax.bar_label(bars, fmt="%.2f", padding=3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_hit_rate_heatmap(plt, rows, path):
    matrix, labels, columns = heatmap_matrix(rows, "algorithm", "cache_size_label", "hit_rate")
    if not matrix:
        return
    plot_heatmap(
        plt,
        matrix,
        labels,
        columns,
        path,
        "Cache size fraction",
        "Algorithm",
        "Mean hit rate (%)",
        "CloudVPS hit rate heatmap",
    )


def plot_cacheus_delta_heatmap(plt, deltas, path):
    matrix, labels, columns = heatmap_matrix(deltas, "baseline_algorithm", "cache_size_label", "hit_rate_delta_pp")
    if not matrix:
        return
    plot_heatmap(
        plt,
        matrix,
        labels,
        columns,
        path,
        "Cache size fraction",
        "Baseline algorithm",
        "CACHEUS delta (percentage points)",
        "CACHEUS delta heatmap",
        center_zero=True,
    )


def heatmap_matrix(rows, row_key, column_key, value_key):
    labels = sorted({row[row_key] for row in rows})
    columns = sorted({row[column_key] for row in rows}, key=lambda value: fnum(value) or 0)
    if not labels or not columns:
        return [], [], []

    values = {}
    for row_label in labels:
        for column_label in columns:
            cell_rows = [
                row
                for row in rows
                if row[row_key] == row_label and row[column_key] == column_label
            ]
            values[(row_label, column_label)] = mean(fnum(row[value_key]) for row in cell_rows)

    matrix = []
    for row_label in labels:
        matrix.append([values[(row_label, column_label)] for column_label in columns])
    return matrix, labels, columns


def plot_heatmap(plt, matrix, labels, columns, path, xlabel, ylabel, color_label, title, center_zero=False):
    import numpy as np

    data = np.array([[value if value is not None else np.nan for value in row] for row in matrix], dtype=float)
    cmap = "RdBu_r" if center_zero else "viridis"
    kwargs = {}
    if center_zero and np.isfinite(data).any():
        limit = np.nanmax(np.abs(data))
        kwargs = {"vmin": -limit, "vmax": limit}

    fig, ax = plt.subplots(figsize=(8, 5))
    image = ax.imshow(data, aspect="auto", cmap=cmap, **kwargs)
    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    for y, row in enumerate(data):
        for x, value in enumerate(row):
            if np.isfinite(value):
                ax.text(x, y, f"{value:.2f}", ha="center", va="center", color="white", fontsize=8)

    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label(color_label)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_runtime_vs_hit_rate(plt, rows, path):
    points = []
    for (algorithm,), items in grouped(rows, ["algorithm"]).items():
        hit_rate = mean(fnum(row["hit_rate"]) for row in items)
        runtime = sum(fnum(row["runtime_sec"]) or 0 for row in items)
        if hit_rate is not None and runtime:
            points.append((algorithm, runtime, hit_rate))
    if not points:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter([runtime for _, runtime, _ in points], [hit_rate for _, _, hit_rate in points], s=60)
    for algorithm, runtime, hit_rate in points:
        ax.annotate(algorithm, (runtime, hit_rate), textcoords="offset points", xytext=(5, 5))
    ax.set_xlabel("Total runtime (sec)")
    ax.set_ylabel("Mean hit rate (%)")
    ax.set_title("CloudVPS runtime vs hit rate")
    ax.grid(True, linestyle=":", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_cacheus_vs_lirs(plt, rows, path):
    selected = [row for row in rows if row["algorithm"].lower() in ("cacheus", "lirs")]
    if not selected:
        return
    plot_lines(
        plt,
        selected,
        ["algorithm", "cache_size_label"],
        "hit_rate",
        path,
        "Mean hit rate (%)",
        "CACHEUS vs LIRS on CloudVPS",
    )


def plot_cacheus_delta_boxplot(plt, deltas, path):
    series = []
    labels = []
    for (baseline,), items in sorted(grouped(deltas, ["baseline_algorithm"]).items()):
        values = [fnum(row["hit_rate_delta_pp"]) for row in items]
        values = [value for value in values if value is not None]
        if values:
            labels.append(baseline)
            series.append(values)
    if not series:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.boxplot(series, labels=labels, showmeans=True)
    ax.set_xlabel("Baseline algorithm")
    ax.set_ylabel("CACHEUS delta (percentage points)")
    ax.set_title("CACHEUS delta distribution by baseline")
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run():
    args = parse_args()
    raw_dir = project_path(args.raw_dir)
    work_dir = project_path(args.work_dir)
    out_dir = project_path(args.out_dir)
    extracted_dir = work_dir / "extracted"
    decoded_dir = work_dir / "decoded"
    converted_dir = work_dir / "converted"

    for path in [raw_dir, extracted_dir, decoded_dir, converted_dir, out_dir]:
        path.mkdir(parents=True, exist_ok=True)

    print("CACHEUS CloudVPS offline reproduction")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"Platform: {platform.platform()}")
    print(f"Raw: {shown(raw_dir)}")
    print(f"Work: {shown(work_dir)}")
    print(f"Output: {shown(out_dir)}")

    targets = prepare_inputs(raw_dir, extracted_dir)
    decoded = decode_traces(targets, decoded_dir)
    converted = convert_traces(decoded, converted_dir, out_dir)

    raw_results = out_dir / "cloudvps_results_raw.csv"
    config_path = write_runner_config(converted, work_dir, raw_results)
    print(f"Internal runner config: {shown(config_path)}")
    run_simulator(config_path, raw_results, work_dir)

    rows = read_results(raw_results, out_dir)
    deltas = analyze(rows, out_dir)
    plot(rows, deltas, out_dir)
    print(f"Done. Results: {shown(out_dir / 'cloudvps_results.csv')}")


def main():
    try:
        run()
    except PipelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
