import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from safety_gate import compile_check, property_expr_check  # noqa: E402


def test_valid_code_passes():
    code = "def test_addition():\n    assert 1 + 1 == 2\n"
    result = compile_check(code)
    assert result.ok


def test_syntax_error_fails():
    code = "def test_broken(:\n    assert True\n"
    result = compile_check(code)
    assert not result.ok
    assert "SyntaxError" in result.reason


def test_disallowed_import_socket_fails():
    code = "import socket\ndef test_x():\n    assert True\n"
    result = compile_check(code)
    assert not result.ok
    assert "socket" in result.reason


def test_disallowed_import_from_fails():
    code = "from subprocess import Popen\ndef test_x():\n    assert True\n"
    result = compile_check(code)
    assert not result.ok
    assert "subprocess" in result.reason


def test_normal_test_imports_are_fine():
    code = "import pytest\nfrom myapp.models import Project\ndef test_x():\n    assert True\n"
    result = compile_check(code)
    assert result.ok


def test_valid_property_expression_passes():
    result = property_expr_check("st.integers(min_value=1, max_value=100)")
    assert result.ok


def test_invalid_property_expression_fails():
    result = property_expr_check("st.integers(min_value=1,")
    assert not result.ok
