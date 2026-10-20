#!/usr/bin/env python3
"""Task-functional accuracy checks for the adapter acceptance gate (v2).

Path A of the retrain plan: replace the teacher-forced token-exact-match
gate (saturated at ~0.75-0.81 regardless of data or recipe) with checks
that measure what "accurate for the task" actually means:

- test_gen:   the generated pytest file compiles, imports the module under
              test, exercises the documented function with real assertions,
              avoids prohibited APIs, and is collectable by pytest.
- reasoning:  the proposed invariant targets the analyzed function, the
              Hypothesis strategy is a well-formed, executable strategy
              expression, and the property assertion references the
              function and is falsifiable.
- reporting:  the narrative tells the truth about the run - no invented
              test names, every failing test covered by a finding,
              priority order consistent with the findings.

Every check is deterministic and objective. Failure reasons are returned
so eval output is auditable.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PROHIBITED_TEST_IMPORTS = {
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "httpx",
    "http",
    "ftplib",
    "telnetlib",
    "smtplib",
    "asyncio",
}

PROHIBITED_TEST_CALLS = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
}


@dataclass
class FunctionalResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _prompt_field(user: str, label: str) -> str | None:
    """Extract 'Label: value' from the first matching line of the prompt."""
    match = re.search(
        rf"^{re.escape(label)}:\s*(.+)$", user, flags=re.MULTILINE
    )
    return match.group(1).strip() if match else None


def _func_name_from_signature(signature: str) -> str | None:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", signature)
    return match.group(1) if match else None


def _ast_of(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# test_gen
# ---------------------------------------------------------------------------


def _iter_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _called_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in _iter_calls(tree):
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def check_test_gen(record: dict, payload: dict) -> FunctionalResult:
    """Generated test file is a real, runnable probe of the documented behavior."""
    reasons: list[str] = []
    content = payload["content"]
    tree = _ast_of(content)
    if tree is None:
        return FunctionalResult(False, ["test content does not parse as Python"])

    # 1. At least one pytest test function.
    test_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if not test_functions:
        reasons.append("no test_ functions defined")

    # 2. Real assertions inside test functions (assert or pytest.raises).
    has_assertion = False
    for func in test_functions:
        for node in ast.walk(func):
            if isinstance(node, ast.Assert):
                has_assertion = True
            elif isinstance(node, ast.With):
                for item in node.items:
                    ctx = item.context_expr
                    name = (
                        ctx.func.id if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Name) else None
                    )
                    if name == "raises":
                        has_assertion = True
    if not has_assertion:
        reasons.append("no assert or pytest.raises in test bodies")

    # 3. The test imports the documented module and calls the documented function.
    user = record.get("user", "")
    module_line = _prompt_field(user, "Module")
    function_line = _prompt_field(user, "Function")
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    if module_line:
        dotted = module_line.replace("/", ".").removesuffix(".py")
        if dotted not in imported_modules:
            reasons.append(f"module under test '{dotted}' is never imported")
    if function_line:
        func_name = _func_name_from_signature(function_line)
        if func_name and func_name not in _called_names(tree):
            reasons.append(f"function under test '{func_name}' is never called")

    # 4. Prohibited APIs absent (self-contained, deterministic, no I/O).
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                root = name.split(".")[0]
                if root in PROHIBITED_TEST_IMPORTS:
                    reasons.append(f"prohibited import: {root}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in PROHIBITED_TEST_CALLS:
                reasons.append(f"prohibited call: {func.id}()")
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in {"remove", "unlink", "rmtree", "system"}
                and isinstance(func.value, ast.Name)
                and func.value.id in {"os", "pathlib", "shutil"}
            ):
                reasons.append(f"prohibited filesystem call: {func.value.id}.{func.attr}")

    if reasons:
        return FunctionalResult(False, reasons)

    # 5. pytest must be able to collect the file (imports bind, structure valid).
    collect_reasons = pytest_collect_check(record, content)
    if collect_reasons:
        return FunctionalResult(False, collect_reasons)
    return FunctionalResult(True, [])


def pytest_collect_check(record: dict, content: str) -> list[str]:
    """Run 'pytest --collect-only' against a stub of the module under test.

    Collection imports the test module, so this proves the generated file
    is importable, references bind, and every test function is discoverable.
    The stub raises NotImplementedError if actually called - collection
    never calls it, so a collectable file proves structure, not behavior.
    """
    user = record.get("user", "")
    module_line = _prompt_field(user, "Module")
    if not module_line:
        return ["prompt has no Module line; cannot build collection sandbox"]

    try:
        import pytest  # noqa: F401
    except ImportError:
        return ["pytest not installed; collection check unavailable"]

    dotted = module_line.replace("/", ".").removesuffix(".py")
    parts = dotted.split(".")
    function_line = _prompt_field(user, "Function")
    function_name = (
        _func_name_from_signature(function_line) if function_line else None
    )
    try:
        with tempfile.TemporaryDirectory(prefix="wfl_eval_") as tmp:
            tmp_path = Path(tmp)
            stub = tmp_path.joinpath(*parts).with_suffix(".py")
            stub.parent.mkdir(parents=True, exist_ok=True)
            for depth in range(1, len(parts)):
                (tmp_path.joinpath(*parts[:depth]) / "__init__.py").write_text(
                    "", encoding="utf-8"
                )
            stub.write_text(
                _stub_source(function_name or parts[-1]),
                encoding="utf-8",
            )
            test_file = tmp_path / "workflo_generated_tests" / "generated_test.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(content, encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--collect-only",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    str(test_file),
                ],
                cwd=str(tmp_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                tail = (proc.stdout or proc.stderr).strip().splitlines()
                detail = tail[-1] if tail else "unknown collection error"
                return [f"pytest collection failed: {detail[:200]}"]
    except subprocess.TimeoutExpired:
        return ["pytest collection timed out"]
    return []


def _stub_source(function_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "", function_name) or "documented_function"
    return (
        f"def {safe}(*args, **kwargs):\n"
        "    raise NotImplementedError\n"
    )


# ---------------------------------------------------------------------------
# reasoning
# ---------------------------------------------------------------------------

_ALLOWED_STRATEGY_ROOTS = {"st"}


def check_reasoning(record: dict, payload: dict) -> FunctionalResult:
    """Invariant targets the analyzed function with an executable, falsifiable property."""
    reasons: list[str] = []
    user = record.get("user", "")

    # 1. Target matches the function under analysis.
    analysis_line = _prompt_field(user, "Function under analysis")
    target = payload["target"].strip()
    if analysis_line:
        analysis_path = analysis_line.split("(")[0].strip()
        prompt_func = analysis_path.split(".")[-1]
        target_final = target.split(".")[-1].strip()
        if prompt_func != target_final:
            reasons.append(
                f"target '{target}' does not match analyzed function '{analysis_path}'"
            )
    else:
        reasons.append("prompt has no 'Function under analysis' line")

    # 2. Hypothesis strategy is a well-formed expression over st.* only.
    strategy = payload["hypothesis_strategy"]
    strategy_ast = None
    try:
        strategy_ast = ast.parse(strategy, mode="eval")
    except SyntaxError:
        reasons.append("hypothesis_strategy does not parse as an expression")
    if strategy_ast is not None:
        bad_names = [
            node.id
            for node in ast.walk(strategy_ast)
            if isinstance(node, ast.Name) and node.id not in _ALLOWED_STRATEGY_ROOTS
        ]
        bad_calls = [
            node
            for node in ast.walk(strategy_ast)
            if isinstance(node, ast.Call)
            and not (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "st"
            )
        ]
        if bad_names:
            reasons.append(f"strategy references non-strategy names: {bad_names[:3]}")
        if bad_calls:
            reasons.append("strategy calls functions outside the st.* namespace")

        # 3. The strategy actually builds a Hypothesis SearchStrategy.
        try:
            import hypothesis.strategies as st  # noqa: PLC0415

            namespace = {"st": st}
            built = eval(compile(strategy_ast, "<strategy>", "eval"), {"__builtins__": {}}, namespace)  # noqa: S307
            if not isinstance(built, st.SearchStrategy):
                reasons.append("strategy expression does not build a SearchStrategy")
        except ImportError:
            pass  # AST-only verdict when hypothesis is unavailable
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"strategy execution failed: {type(exc).__name__}")

    # 4. Property is grounded in the analyzed context and falsifiable.
    #    Real invariants may reference the function's result, the state it
    #    maintains ("bucket.tokens"), or a snake_case subtoken of the
    #    function name ("password" for password_never_logged) - so require
    #    identifier overlap with the analysis line, not a literal call.
    prop = payload["property_check"]
    prop_ast = None
    try:
        prop_ast = ast.parse(prop, mode="eval")
    except SyntaxError:
        reasons.append("property_check does not parse as an expression")
    if prop_ast is not None and analysis_line:
        analysis_lower = analysis_line.lower()
        prop_identifiers = {
            node.id for node in ast.walk(prop_ast) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(prop_ast) if isinstance(node, ast.Attribute)
        }
        grounded = any(
            len(identifier) >= 4 and identifier in analysis_lower
            for identifier in prop_identifiers
        )
        if not grounded:
            reasons.append(
                "property_check shares no identifier with the analyzed function "
                "or its parameters (ungrounded invariant)"
            )
        has_comparison = any(
            isinstance(node, (ast.Compare, ast.BoolOp))
            for node in ast.walk(prop_ast)
        )
        if not has_comparison:
            reasons.append("property_check has no comparison or boolean operator (not falsifiable)")

    return FunctionalResult(not reasons, reasons)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def check_reporting(record: dict, payload: dict) -> FunctionalResult:
    """Narrative is truthful: no invented tests, full coverage, consistent priorities."""
    reasons: list[str] = []
    try:
        run = json.loads(record["user"])
    except json.JSONDecodeError:
        return FunctionalResult(False, ["input run payload is not valid JSON"])

    failing_tests = [
        failure["test"]
        for failure in run.get("failures", [])
        if failure.get("outcome") in {"FAILED", "ERROR", "TIMEOUT"}
    ]
    failing_set = set(failing_tests)

    findings = payload.get("findings", [])
    covered: set[str] = set()
    for finding in findings:
        for test_name in finding.get("affected_tests", []):
            if test_name not in failing_set:
                reasons.append(f"invented or non-failing test referenced: {test_name}")
            covered.add(test_name)

    # 1. Every failing test is explained by some finding.
    missing = failing_set - covered
    if missing:
        reasons.append(f"failing tests not covered by any finding: {sorted(missing)[:3]}")

    # 2. Findings on a green run are only legitimate as grounded info notes
    #    (e.g. warnings captured in the run's notes field) that touch no
    #    test names. Anything else invents problems the run does not have.
    if not failing_tests and findings:
        notes = str(run.get("notes", "") or "").lower()
        note_tokens = set(re.findall(r"[a-z][a-z0-9_]{3,}", notes))
        for finding in findings:
            finding_text = " ".join(
                [finding.get("root_cause", ""), finding.get("explanation", "")]
            ).lower()
            grounded = (
                finding.get("affected_tests") == []
                and finding.get("severity") == "info"
                and notes
                and (note_tokens & set(re.findall(r"[a-z][a-z0-9_]{3,}", finding_text)))
            )
            if not grounded:
                reasons.append(
                    "finding reported for a run with no failures and not grounded "
                    f"in input notes: {finding.get('root_cause', '')[:60]}"
                )
    if failing_tests and not findings:
        reasons.append("failures exist but no findings produced")

    # 3. priority_order entries must be root causes of actual findings.
    root_causes = {finding.get("root_cause") for finding in findings}
    for entry in payload.get("priority_order", []):
        if entry not in root_causes:
            reasons.append(f"priority_order entry is not a finding root_cause: {entry[:80]}")
    if findings and not payload.get("priority_order"):
        reasons.append("findings exist but priority_order is empty")

    # 4. Summary engages with the actual outcome.
    summary = payload.get("summary", "").lower()
    failed_total = run.get("totals", {}).get("failed", 0)
    mentions_failure = (
        any(test_name.lower() in summary for test_name in failing_tests)
        or (failed_total > 0 and str(failed_total) in summary)
        or ("fail" in summary)
    )
    if failing_tests and not mentions_failure:
        reasons.append("summary does not reference the failing outcome")

    return FunctionalResult(not reasons, reasons)


CHECK_BY_TASK = {
    "test_gen": check_test_gen,
    "reasoning": check_reasoning,
    "reporting": check_reporting,
}
