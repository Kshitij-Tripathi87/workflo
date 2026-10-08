"""Cortex Autopilot Benchmark 2026.

Provides:
  - repo_generator: synthetic dbt manifest.json files
  - run_benchmark: orchestrator that runs the engine against the corpus
  - metrics: aggregate statistics (latency percentiles, blast-radius
    accuracy, severity correlation, FP/FN rates)

See docs/benchmark.md for the methodology.
"""
