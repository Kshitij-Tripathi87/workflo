"""Tenant Shield reporting: results schema + compliance report generation.

The pytest plugin (`workflo.reporting.plugin`) captures per-test
outcomes together with any isolation evidence pushed by the isolation
library, and writes a JSON results file in the schema below. The compliance
report generator renders that JSON into a self-contained, auditor-readable
SOC 2 evidence report.
"""

from workflo.reporting.results import RunReport, TestResult

__all__ = ["RunReport", "TestResult"]
