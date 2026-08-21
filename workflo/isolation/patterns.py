"""Named isolation patterns and their SOC 2 control mappings.

Users (and the report generator) refer to patterns by these names so that test
intent is declared once and reused across tests and audit evidence.
"""

from enum import Enum


class IsolationPattern(str, Enum):
    """The set of tenant-isolation patterns the framework can assert."""

    API_READ = "api_read"
    API_LIST = "api_list"
    API_MODIFY = "api_modify"
    API_DELETE = "api_delete"
    UI_VISIBILITY = "ui_visibility"
    UI_INVISIBILITY = "ui_invisibility"
    POSITIVE_CONTROL = "positive_control"

    @property
    def label(self) -> str:
        return _LABELS.get(self, self.value)

    @property
    def soc2_controls(self) -> list:
        return _SOC2_MAPPING.get(self, ["CC6.6"])


# Human-readable descriptions used in evidence reports.
_LABELS = {
    IsolationPattern.API_READ: "Cross-tenant resource read is denied",
    IsolationPattern.API_LIST: "Cross-tenant resources are excluded from list responses",
    IsolationPattern.API_MODIFY: "Cross-tenant resource modification is denied",
    IsolationPattern.API_DELETE: "Cross-tenant resource deletion is denied",
    IsolationPattern.UI_VISIBILITY: "UI shows only the authenticated tenant's data",
    IsolationPattern.UI_INVISIBILITY: "UI does not render other tenants' data",
    IsolationPattern.POSITIVE_CONTROL: "Same-tenant access succeeds (validates the test itself)",
}

# Each pattern maps to one or more AICPA TSC 2017 SOC 2 common criteria.
_SOC2_MAPPING = {
    IsolationPattern.API_READ: ["CC6.1", "CC6.6"],
    IsolationPattern.API_LIST: ["CC6.1", "CC6.6"],
    IsolationPattern.API_MODIFY: ["CC6.1", "CC6.6"],
    IsolationPattern.API_DELETE: ["CC6.1", "CC6.6"],
    IsolationPattern.UI_VISIBILITY: ["CC6.6"],
    IsolationPattern.UI_INVISIBILITY: ["CC6.6"],
    IsolationPattern.POSITIVE_CONTROL: ["CC6.1"],
}
