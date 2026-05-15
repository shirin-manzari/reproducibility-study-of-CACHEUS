# Reproducibility Study of CACHEUS on CloudVPS

This repository is an academic reproducibility study for the CACHEUS cache
replacement work from FAST 2021. It keeps the original simulator and algorithm
implementations, then adds an offline CloudVPS-only pipeline that prepares local
block traces, runs CACHEUS and baseline policies, and writes summary artifacts
for comparison.

The goal is not to publish a new cache policy. The goal is to make a focused,
repeatable experiment path that can be used for coursework, replication, and
analysis of the CACHEUS results on the public CloudVPS trace family.

## What Is Included

- `code/run.py`: the simulator entry point used to execute cache replacement
  algorithms over trace files.
- `code/algs/`: implementations of CACHEUS and baseline policies, including
  LRU, LFU, ARC, LIRS, LeCaR, and CACHEUS.
- `cloudvps_pipeline.py`: an offline pipeline for CloudVPS traces. It extracts
  local archives, decodes blktrace files with `blkparse`, converts them to the
  simulator's `.blk` format, runs experiments, and generates CSV summaries and
  figures.
- `code/algs/lib/traces.py`: simplified for this study so the simulator only
  accepts converted CloudVPS/VISA-style `.blk` traces.

Local datasets, generated work files, results, papers, and private notes are
ignored by git. This keeps the repository focused on reproducible code rather
than large trace archives or machine-specific outputs.

## Experiment Scope

The CloudVPS pipeline currently runs:

- Algorithms: `lru`, `lfu`, `arc`, `lirs`, `lecar`, `cacheus`
- Cache size fractions: `0.001`, `0.005`, `0.01`, `0.05`, `0.1`
- Cache size basis: unique request count
- Blktrace event filter: `Q` events
- Trace input format: CloudVPS `vps*.tar.gz` archives or extracted `vps*`
  directories containing a matching `.blktrace.0` file

This is a narrowed reproduction setup. Other original trace readers and the old
visualization entry points were removed from this version to keep the academic
study centered on CloudVPS.

## Requirements

- Python 3
- `numpy`
- `matplotlib`
- Linux `blkparse` from the `blktrace` tools

On Debian/Ubuntu systems, `blkparse` is usually provided by:

```bash
sudo apt-get install blktrace
```

Python dependencies can be installed in your preferred environment:

```bash
pip install numpy matplotlib
```

The pipeline can be launched from Windows, WSL, or Linux, but the trace decoding
step requires `blkparse` to be available on `PATH`.

## Preparing CloudVPS Traces

Download the CloudVPS traces from the public trace source referenced in the
CACHEUS paper, then place the archives under:

```text
data/cloudvps_raw/
```

Expected examples:

```text
data/cloudvps_raw/vps1.tar.gz
data/cloudvps_raw/vps2.tar.gz
```

The pipeline also accepts already extracted `vps*` directories if they contain a
single usable `.blktrace.0` file.

## Running the CloudVPS Pipeline

From the repository root, run:

```bash
python cloudvps_pipeline.py
```

Optional paths can be overridden:

```bash
python cloudvps_pipeline.py \
  --raw-dir data/cloudvps_raw \
  --work-dir work/cloudvps \
  --out-dir results/cloudvps
```

The pipeline performs these steps:

1. Finds local `vps*.tar.gz` archives or extracted `vps*` directories.
2. Safely extracts archives into the work directory.
3. Decodes `.blktrace.0` files using `blkparse`.
4. Converts decoded events into `.blk` files readable by the simulator.
5. Writes an internal JSON config for `code/run.py`.
6. Runs the selected algorithms and cache sizes.
7. Produces raw results, summaries, CACHEUS-vs-baseline deltas, and figures.

## Outputs

By default, results are written to:

```text
results/cloudvps/
```

Important outputs include:

- `conversion_summary.csv`: trace conversion counts and skipped-line totals.
- `cloudvps_runner.log`: full simulator output.
- `cloudvps_results_raw.csv`: raw simulator rows.
- `cloudvps_results.csv`: raw rows with explicit column headers.
- `summary_by_algorithm.csv`: aggregate hit-rate and runtime summary per
  algorithm.
- `summary_by_cache_size.csv`: mean hit rate per algorithm and cache size.
- `cacheus_vs_baselines.csv`: per-trace CACHEUS deltas against each baseline.
- `cacheus_delta_summary.csv`: mean CACHEUS deltas grouped by baseline and cache
  size.
- `figures/hit_rate_vs_cache_size.png`
- `figures/cacheus_delta_vs_baselines.png`
- `figures/runtime_by_algorithm.png`

## Academic Notes

For an academic report, describe this repository as a focused reproducibility
study of CACHEUS on the CloudVPS workload, not as a full reproduction of every
dataset in the original FAST 2021 paper. The current implementation depends on
locally obtained traces and reproduces the experiment workflow using public
CloudVPS data only.

When reporting results, include:

- the exact trace files used,
- the machine and Python environment,
- whether `blkparse` was run locally or inside WSL/Linux,
- the cache size fractions,
- the list of algorithms,
- and the generated CSV/figure artifacts used for analysis.

## References

The relevant paper to cite for CACHEUS is:

```bibtex
@inproceedings {cacheus-fast21,
author = {Liana V. Rodriguez and Farzana Yusuf and Steven Lyons and Eysler Paz and Raju Rangaswami and Jason Liu and Ming Zhao and Giri Narasimhan},
title = {Learning Cache Replacement with {CACHEUS}},
booktitle = {19th {USENIX} Conference on File and Storage Technologies ({FAST} 21)},
year = {2021},
url = {https://www.usenix.org/conference/fast21/presentation/valdes},
publisher = {{USENIX} Association},
month = February,
}
```

The relevant paper to cite for LeCaR is:

```bibtex
@inproceedings {lecar-hotstorage19,
author = {Giuseppe Vietri and Liana V. Rodriguez and Wendy A. Martinez and Steven Lyons and Jason Liu and Raju Rangaswami and Ming Zhao and Giri Narasimhan},
title = {Driving Cache Replacement with ML-based LeCaR},
booktitle = {10th {USENIX} Workshop on Hot Topics in Storage and File Systems (HotStorage 18)},
year = {2018},
address = {Boston, MA},
url = {https://www.usenix.org/conference/hotstorage18/presentation/vietri},
publisher = {{USENIX} Association},
month = July,
}
```

## Acknowledgments

This study builds on the CACHEUS project code and related cache replacement
algorithm implementations. The original project acknowledges Song Jiang for
sharing LIRS code that was adapted to Python for comparative evaluation.
