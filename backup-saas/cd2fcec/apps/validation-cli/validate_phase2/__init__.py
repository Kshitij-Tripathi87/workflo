"""Sandboxed architecture-review pipeline (validate-phase2).

Provides a Click CLI that:
  1. Clones a GitHub repo at HEAD with a baseline (merge-base) reference
  2. Runs automated gates (typecheck, lint, tests, contract, live trace)
  3. Feeds the diff + key context to a fine-tuned Qwen LLM via vLLM
  4. Produces reports in Markdown, JSON, SARIF, and HTML formats
  5. Tears down the sandbox; returns only the reports + structured logs
"""

__version__ = "0.1.0"
