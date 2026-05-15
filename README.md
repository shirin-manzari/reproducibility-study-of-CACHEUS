# Reproducibility Study of CACHEUS on CloudVPS

This repository is an academic reproducibility study based on the original
[CACHEUS](https://github.com/sylab/cacheus) cache replacement project from FAST
2021. It keeps the original simulator and algorithms, then adds a focused
CloudVPS-only pipeline for preparing traces, running experiments, and generating
summary results.

## Scope

This study evaluates:

- Algorithms: `lru`, `lfu`, `arc`, `lirs`, `lecar`, `cacheus`
- Cache sizes: `0.001`, `0.005`, `0.01`, `0.05`, `0.1` of unique requests
- Dataset: public CloudVPS traces only

This is not a full reproduction of every dataset in the original paper. It is a
smaller academic reproduction focused on the CloudVPS workload.

## Repository Contents

- `code/run.py`: simulator entry point.
- `code/algs/`: CACHEUS and baseline cache replacement algorithms.
- `cloudvps_pipeline.py`: offline CloudVPS reproduction pipeline.
- `results/cloudvps/`: curated summary CSVs and figures from the reproduction.

Raw traces, decoded traces, intermediate work files, and full logs are not
tracked in git.

## Requirements

- Python 3
- `numpy`
- `matplotlib`
- `blkparse` from Linux `blktrace` tools

Install Python dependencies:

```bash
pip install numpy matplotlib
```

On Debian/Ubuntu:

```bash
sudo apt-get install blktrace
```

## Run

Place CloudVPS `vps*.tar.gz` archives, or extracted `vps*` directories, under:

```text
data/cloudvps_raw/
```

Then run:

```bash
python cloudvps_pipeline.py
```

Optional custom paths:

```bash
python cloudvps_pipeline.py --raw-dir data/cloudvps_raw --work-dir work/cloudvps --out-dir results/cloudvps
```

The pipeline extracts traces, decodes `.blktrace.0` files with `blkparse`,
converts them to `.blk`, runs the simulator, and writes CSV summaries and plots.

## Results

Curated results are stored in `results/cloudvps/`, including:

- `summary_by_algorithm.csv`
- `summary_by_cache_size.csv`
- `cacheus_vs_baselines.csv`
- `cacheus_delta_summary.csv`
- `conversion_summary.csv`
- `figures/*.png` for hit-rate, runtime, heatmap, and CACHEUS-vs-baseline plots

In this CloudVPS-only reproduction, CACHEUS performs strongly against LRU, LFU,
ARC, and LeCaR, and is nearly tied with LIRS overall.

## References

- Rodriguez et al., **Learning Cache Replacement with CACHEUS**, FAST 2021.
- Vietri et al., **Driving Cache Replacement with ML-based LeCaR**, HotStorage
  2018.
