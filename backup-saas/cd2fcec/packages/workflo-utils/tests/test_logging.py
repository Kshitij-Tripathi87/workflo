import json
import logging
import io
import pytest
from datetime import datetime

from workflo_utils.logging import JsonFormatter, configure_logging, get_logger, add_run_context


class TestConfigureLogging:
    def test_json_mode_sets_json_formatter(self):
        configure_logging(level="DEBUG", json_output=True)
        root = logging.getLogger()
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    def test_non_json_mode_sets_plain_formatter(self):
        configure_logging(level="WARNING", json_output=False)
        root = logging.getLogger()
        handler = root.handlers[0]
        assert not isinstance(handler.formatter, JsonFormatter)

    def test_level_is_set(self):
        configure_logging(level="ERROR", json_output=True)
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_level_defaults_to_info_for_invalid_value(self):
        configure_logging(level="NONEXISTENT", json_output=True)
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_expected_name(self):
        logger = get_logger("myapp.service")
        assert logger.name == "myapp.service"

    def test_logger_propagates_by_default(self):
        logger = get_logger("some.name")
        assert logger.propagate is True


class TestJsonFormatter:
    def test_format_produces_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__,
            lineno=42, msg="hello %s", args=("world",), exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "hello world"
        assert parsed["module"] == "test_logging" or "module" in parsed
        assert "timestamp" in parsed

    def test_output_includes_extra_data(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=1, msg="msg", args=(), exc_info=None, pathname=__file__, lineno=1,
        )
        record.extra_data = {"run_id": "abc-123", "goal": "test"}
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["run_id"] == "abc-123"
        assert parsed["goal"] == "test"

    def test_output_includes_exception_when_exc_info_present(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, msg="err", args=(),
                exc_info=sys.exc_info(), pathname=__file__, lineno=1,
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestAddRunContext:
    def test_adapter_is_returned(self):
        adapter = add_run_context("run-1", "test goal")
        assert isinstance(adapter, logging.LoggerAdapter)

    def test_adapter_log_record_contains_run_context(self):
        adapter = add_run_context("run-42", "migration")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        root_logger = adapter.logger
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        adapter.info("starting task")
        output = json.loads(stream.getvalue())
        assert output["run_id"] == "run-42"
        assert output["goal"] == "migration"

    def test_adapter_accepts_extra_kwargs(self):
        adapter = add_run_context("r1", "g1", tenant="acme", region="us-east-1")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        root_logger = adapter.logger
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        adapter.info("regional work")
        output = json.loads(stream.getvalue())
        assert output["tenant"] == "acme"
        assert output["region"] == "us-east-1"