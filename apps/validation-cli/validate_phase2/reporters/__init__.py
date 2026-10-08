"""Report generators: Markdown, JSON, SARIF, HTML.

Each reporter takes a ValidationResult and writes a file. All reporters
are deterministic given the same ValidationResult (no LLM calls).
"""

from .md import write as write_md
from .json import write as write_json
from .sarif import write as write_sarif
from .html import write as write_html

REPORTERS = {
    "md": write_md,
    "json": write_json,
    "sarif": write_sarif,
    "html": write_html,
}

__all__ = ["REPORTERS", "write_md", "write_json", "write_sarif", "write_html"]
