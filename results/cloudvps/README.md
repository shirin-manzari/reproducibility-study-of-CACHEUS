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
- `cacheus_paired_t_tests.csv`: paired t-tests comparing CACHEUS with each
  baseline over matched trace/cache-size runs, plus per-cache-size tests.
- `run_metadata.txt`: platform, Python version, configured algorithms, cache
  sizes, and run notes for the curated result set.
- `figures/hit_rate_vs_cache_size.png`: mean hit rate by cache size.
- `figures/cacheus_delta_vs_baselines.png`: CACHEUS hit-rate delta against each
  baseline by cache size.
- `figures/runtime_by_algorithm.png`: total simulator runtime by algorithm.
- `figures/mean_hit_rate_bar.png`: overall mean hit rate comparison.
- `figures/hit_rate_heatmap.png`: algorithm/cache-size mean hit-rate heatmap.
- `figures/cacheus_delta_heatmap.png`: CACHEUS-vs-baseline delta heatmap.
- `figures/runtime_vs_hit_rate.png`: runtime and hit-rate tradeoff.
- `figures/cacheus_vs_lirs.png`: focused CACHEUS and LIRS comparison.
- `figures/cacheus_delta_boxplot.png`: distribution of CACHEUS deltas by
  baseline.
- `figures/cacheus_paired_t_tests.png`: overall paired t-test forest plot with
  mean CACHEUS deltas, 95% confidence intervals, and p-value labels.

Large or machine-specific outputs are intentionally not tracked, including raw
trace data, decoded traces, converted `.blk` files, full simulator raw output,
and execution logs.

The paired t-tests use hit-rate differences in percentage points. Positive
mean deltas indicate that CACHEUS had a higher hit rate than the named
baseline on the matched runs.
