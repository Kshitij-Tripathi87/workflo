# Cortex Autopilot Benchmark 2026

**Source:** synthetic
**Total evaluations:** 10000
**Successful evaluations:** 10000
**Failed evaluations:** 0

## Latency

- p50: 0.02 ms
- p95: 0.06 ms
- p99: 0.10 ms
- mean: 0.03 ms
- n: 10000

## Severity Classification

- accuracy: 82.83%
- false-positive rate: 2.73%
- false-negative rate: 0.00%

Confusion matrix (rows = expected, cols = predicted):

| expected \ predicted | low | medium | high | critical |
|---|---|---|---|---|
| low | 596 | 1416 | 0 | 0 |
| medium | 0 | 718 | 265 | 8 |
| high | 0 | 0 | 4004 | 28 |
| critical | 0 | 0 | 0 | 2965 |

## Blast-Radius Accuracy

- mean Jaccard: 1.0000
- exact match rate: 100.00%
- n: 10000
