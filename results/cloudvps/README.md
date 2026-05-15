# CloudVPS Result Artifacts

This directory contains the small, shareable result artifacts from the
CloudVPS-focused CACHEUS reproducibility run.

Included files:

- `conversion_summary.csv`: counts from converting decoded CloudVPS traces into
  simulator-readable `.blk` files.
- `summary_by_algorithm.csv`: aggregate hit-rate and runtime statistics by
  algorithm.
- `summary_by_cache_size.csv`: mean hit rate by algorithm and cache size.
- `cacheus_vs_baselines.csv`: per-trace CACHEUS hit-rate deltas against each
  baseline algorithm.
- `cacheus_delta_summary.csv`: grouped CACHEUS-vs-baseline delta summaries.
- `figures/*.png`: plots generated from the CSV results.

Large or machine-specific outputs are intentionally not tracked, including raw
trace data, decoded traces, converted `.blk` files, full simulator raw output,
and execution logs.
