"""Static fail-closed checks for model-proposed executable content.

These checks reduce obviously dangerous or malformed output before the code is
placed in the disposable sandbox. They do not replace sandbox isolation or the
actual pytest run.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

DISALLOWED_MODULE_ROOTS = {
    "ctypes",
    "ftplib",
    "http",
    "os",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "telnetlib",
    "urllib",
}
DISALLOWED_CALL_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
DISALLOWED_ATTRIBUTE_CALLS = {
    "chmod",
    "chown",
    "connect",
    "execv",
    "execve",
    "popen",
    "remove",
    "removedirs",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "system",
    "unlink",
    "urlopen",
}


@dataclass(frozen=True)
class CompileCheckResult:
    ok: bool
    reason: str = ""


def _module_is_disallowed(name: str) -> bool:
    return name.split(".", 1)[0] in DISALLOWED_MODULE_ROOTS


def _unsafe_node_reason(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if _module_is_disallowed(alias.name):
                return f"disallowed import in generated test: {alias.name}"
    elif isinstance(node, ast.ImportFrom):
        if node.module and _module_is_disallowed(node.module):
            return f"disallowed import in generated test: {node.module}"
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_CALL_NAMES:
            return f"disallowed call in generated test: {node.func.id}"
        if isinstance(node.func, ast.Attribute) and node.func.attr in DISALLOWED_ATTRIBUTE_CALLS:
            return f"disallowed call in generated test: {node.func.attr}"
    return None


def compile_check(code: str) -> CompileCheckResult:
    """Parse Python and reject obvious filesystem, process, and network access."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError) as exc:
        return CompileCheckResult(ok=False, reason=f"SyntaxError: {exc}")

    for node in ast.walk(tree):
        reason = _unsafe_node_reason(node)
        if reason:
            return CompileCheckResult(ok=False, reason=reason)
    return CompileCheckResult(ok=True)


def property_expr_check(expr: str) -> CompileCheckResult:
    """Validate a reasoning-adapter expression without executing it."""
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        return CompileCheckResult(ok=False, reason=f"SyntaxError in expression: {exc}")

    for node in ast.walk(tree):
        reason = _unsafe_node_reason(node)
        if reason:
            return CompileCheckResult(ok=False, reason=reason)
    return CompileCheckResult(ok=True)
