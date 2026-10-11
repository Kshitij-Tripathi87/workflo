from workflo_ai_integration.safety_gate import compile_check, property_expr_check


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


def test_disallowed_from_os_import_fails():
    result = compile_check("from os import system\ndef test_x():\n    assert True\n")
    assert not result.ok
    assert "os" in result.reason


def test_disallowed_builtin_exec_fails():
    result = compile_check("def test_x():\n    exec('assert True')\n")
    assert not result.ok
    assert "exec" in result.reason


def test_disallowed_attribute_call_fails():
    result = compile_check("def test_x(tmp_path):\n    tmp_path.unlink()\n")
    assert not result.ok
    assert "unlink" in result.reason


def test_property_expression_rejects_process_calls():
    result = property_expr_check("runner.system('id')")
    assert not result.ok
    assert "system" in result.reason
