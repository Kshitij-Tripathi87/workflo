"""
The one function standing between "the model said so" and "this runs in the
sandbox." Nothing produced by an adapter reaches pytest/Hypothesis without
going through here first.

This is deliberately dumb and cheap (ast.parse, not a sandboxed exec) — its
job is to catch syntactically broken or obviously unsafe generated code
before it wastes a sandbox run, not to be a full static analyzer. Real
validation of *correctness* still happens by actually running the test.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Anything importing these inside a *generated* test is treated as suspicious —
# a generated test's job is to exercise the target repo, not to reach outside
# the sandbox. This list is intentionally conservative; extend with care.
DISALLOWED_IMPORTS = {
    "socket", "subprocess", "os.system", "shutil.rmtree", "requests", "urllib",
}


@dataclass
class CompileCheckResult:
    ok: bool
    reason: str = ""


def compile_check(code: str) -> CompileCheckResult:
    """Syntax + coarse safety check for model-generated test code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return CompileCheckResult(ok=False, reason=f"SyntaxError: {e}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in DISALLOWED_IMPORTS or alias.name.split(".")[0] in DISALLOWED_IMPORTS:
                    return CompileCheckResult(
                        ok=False, reason=f"disallowed import in generated test: {alias.name}"
                    )
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module in DISALLOWED_IMPORTS or node.module.split(".")[0] in DISALLOWED_IMPORTS
            ):
                return CompileCheckResult(
                    ok=False, reason=f"disallowed import in generated test: {node.module}"
                )

    return CompileCheckResult(ok=True)


def property_expr_check(expr: str) -> CompileCheckResult:
    """
    Validate a Hypothesis strategy or assertion expression proposed by the
    reasoning adapter (ProposeInvariantCall). These are expressions, not full
    modules, so parsed in 'eval' mode.
    """
    try:
        ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return CompileCheckResult(ok=False, reason=f"SyntaxError in expression: {e}")
    return CompileCheckResult(ok=True)
