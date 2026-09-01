"""workflo probe engine — config-driven test probes.

Replaces the hardcoded `IsolationScenario` fixtures with a declarative
probe spec: instead of hardcoding `/api/v1/projects`, you write a YAML
config describing what to probe and how.

Example config:

    probes:
      - name: cross_tenant_read
        pattern: api_read
        path: /api/v1/projects
        method: GET
        expected_status: [403, 404]
      - name: cross_tenant_list
        pattern: api_list
        path: /api/v1/projects
        method: GET
        list_key: projects
        expect_resource_absent: true
      - name: positive_control
        pattern: positive_control
        path: /api/v1/projects
        method: GET
        expected_status: 200

This engine takes that config and a repo URL, and produces a config-driven
test spec for the worker — without any per-repo hand-coding.
"""

from probe_engine.models import (
    ProbeConfig,
    ProbeSpec,
    ProbeResult,
    ProbeRunSummary,
)
from probe_engine.runner import ProbeRunner
from probe_engine.generator import ProbeGenerator

__all__ = [
    "ProbeConfig",
    "ProbeSpec",
    "ProbeResult",
    "ProbeRunSummary",
    "ProbeRunner",
    "ProbeGenerator",
    "PROBE_GROUPS",
]

# Re-export class constants for convenience
from probe_engine.generator import ProbeGenerator
PROBE_GROUPS = ProbeGenerator.PROBE_GROUPS
