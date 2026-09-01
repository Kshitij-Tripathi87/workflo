"""Flag-handling tests.

Verify that:
  1. Flags are validated against VALID_FLAGS
  2. Each flag actually affects the rendered prompt
  3. Invalid flags cause CLI to exit with code 2
  4. CLI flag string parsing handles edge cases
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_phase2.orchestrator import render_prompt
from validate_phase2.cli import main, VALID_FLAGS, _parse_csv

# Locate the prompt template relative to the package
PROMPT_PATH = (
    Path(__file__).parent.parent / "validate_phase2" / "prompts" / "architecture_review.j2"
)


def _render(flags: list[str]) -> str:
    return render_prompt(
        PROMPT_PATH,
        repo="https://example.com/repo",
        baseline="abc123",
        head="def456",
        flags=flags,
        diff="",
        context_files=[],
    )


class TestFlagValidation:
    """Flag whitelist + CLI parsing."""

    def test_valid_flags_set(self):
        """The expected review flags must all be in VALID_FLAGS."""
        expected = {
            "architecture", "patterns", "oauth-correctness",
            "jwt", "async-patterns", "security",
        }
        assert expected.issubset(VALID_FLAGS), (
            f"Missing flags: {expected - VALID_FLAGS}"
        )

    def test_parse_csv_strips_whitespace(self):
        assert _parse_csv("a, b,c , d") == ["a", "b", "c", "d"]

    def test_parse_csv_drops_empty(self):
        assert _parse_csv("a,,b,") == ["a", "b"]
        assert _parse_csv("") == []
        assert _parse_csv(",,,") == []

    def test_unknown_flag_cli_exit_2(self):
        """An unknown flag must cause the CLI to exit with code 2
        (distinguishable from gate failures = 1, success = 0)."""
        with pytest.raises(SystemExit) as exc:
            main([
                "--repo", "https://example.com/x",
                "--model-endpoint", "http://localhost:9999",
                "--flags", "architecture,not-a-real-flag",
            ], standalone_mode=False)
        assert exc.value.code == 2


class TestFlagAffectsPrompt:
    """Each enabled flag must inject its review-scope section into the prompt."""

    def test_architecture_flag_adds_section(self):
        prompt_no_arch = _render(["jwt"])
        prompt_with_arch = _render(["architecture", "jwt"])
        assert "ARCHITECTURE & PATTERNS" not in prompt_no_arch
        assert "ARCHITECTURE & PATTERNS" in prompt_with_arch

    def test_oauth_flag_adds_section(self):
        prompt_no_oauth = _render(["architecture"])
        prompt_with_oauth = _render(["architecture", "oauth-correctness"])
        assert "RFC 8628" not in prompt_no_oauth
        assert "RFC 8628" in prompt_with_oauth

    def test_jwt_flag_adds_section(self):
        prompt_no_jwt = _render(["architecture"])
        prompt_with_jwt = _render(["architecture", "jwt"])
        assert "JWT CLAIM DESIGN" not in prompt_no_jwt
        assert "JWT CLAIM DESIGN" in prompt_with_jwt

    def test_async_flag_adds_section(self):
        prompt_no_async = _render(["architecture"])
        prompt_with_async = _render(["architecture", "async-patterns"])
        assert "ASYNC PATTERNS" not in prompt_no_async
        assert "ASYNC PATTERNS" in prompt_with_async

    def test_security_flag_adds_section(self):
        prompt_no_sec = _render(["architecture"])
        prompt_with_sec = _render(["architecture", "security"])
        assert "SHA-256" not in prompt_no_sec  # security section mentions Argon2 not SHA
        assert "SECURITY" in prompt_with_sec

    def test_flags_joined_in_prompt(self):
        """The flags list itself must appear in the rendered prompt."""
        prompt = _render(["architecture", "patterns", "security"])
        assert "architecture, patterns, security" in prompt

    def test_all_flags_combine(self):
        """When all flags are enabled, every review section appears."""
        prompt = _render([
            "architecture", "patterns", "oauth-correctness",
            "jwt", "async-patterns", "security",
        ])
        assert "ARCHITECTURE & PATTERNS" in prompt
        assert "RFC 8628" in prompt
        assert "JWT CLAIM DESIGN" in prompt
        assert "ASYNC PATTERNS" in prompt
        assert "SECURITY" in prompt

    def test_no_flags_renders_base_prompt(self):
        """With an empty flag list, none of the conditional sections appear."""
        prompt = _render([])
        assert "ARCHITECTURE & PATTERNS" not in prompt
        assert "RFC 8628" not in prompt
        assert "JWT CLAIM DESIGN" not in prompt
        assert "ASYNC PATTERNS" not in prompt
        assert "SECURITY" not in prompt
