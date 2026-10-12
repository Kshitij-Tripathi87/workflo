"""Authoritative training examples for the three Workflo task adapters.

Each example is a ChatML-shaped record:
    {"system": ..., "user": ..., "assistant": {...schema payload...}}

The assistant payloads MUST validate against
``workflo_ai_integration.schemas`` and MUST pass
``workflo_ai_integration.safety_gate`` (compile_check for test bodies,
property_expr_check for strategy/property expressions). validate_datasets.py
enforces exactly that, so the training data can never drift from the
fail-closed serving contract.

Rules for authoring:
  - Generated test bodies must be self-contained, compile, and may import
    only modules allowed by safety_gate (no os/socket/subprocess/open/eval...).
  - Paths use the workflo_generated_tests/ prefix and POSIX separators.
  - Reporting inputs contain ONLY structured outcomes, never source code.
  - No customer source, no secrets, no real hostnames in any example.
"""

from __future__ import annotations

TEST_GEN_SYSTEM = (
    "You generate pytest test files for a repository change. You receive the "
    "module under test, its function signatures, and a behavior description. "
    "Respond with a single JSON object matching the WriteTestCall schema: "
    "path (relative POSIX path under workflo_generated_tests/ ending in .py), "
    "content (full Python source of the test file), framework (pytest), and "
    "rationale (one sentence). Tests must be self-contained, deterministic, "
    "and must not touch the filesystem, network, or subprocesses."
)

REASONING_SYSTEM = (
    "You propose a property-based invariant for one function, route, or "
    "module. Respond with a single JSON object matching the "
    "ProposeInvariantCall schema: description (plain-English invariant), "
    "target (function, route, or module), category (tenant_isolation, "
    "business_logic, data_integrity, or auth), hypothesis_strategy (a "
    "Hypothesis @given strategy expression), and property_check (a Python "
    "assertion expression). Expressions must be pure: no imports, no "
    "filesystem, network, or process access."
)

REPORTING_SYSTEM = (
    "You summarize automated test results. You will only ever receive "
    "structured JSON test outcomes, never source code. Respond with a single "
    "JSON object matching the ReportNarrative schema: summary (2-3 plain "
    "English sentences), findings (list of root_cause, affected_tests, "
    "severity, explanation), and priority_order (finding root_causes ordered "
    "by what to fix first). Never invent test names that are not in the input."
)

TEST_GEN: list[dict] = [
    {
        "user": (
            "Module: app/services/cart.py\n"
            "Function: compute_total(lines: list[tuple[str, int, int]]) -> int\n"
            "Behavior: each line is (sku, quantity, unit_price_cents). Returns "
            "the summed quantity * unit_price_cents in cents. Empty cart "
            "returns 0. A negative quantity or a non-positive unit price "
            "raises ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_cart_total.py",
            "content": (
                '"""Generated tests for cart total computation."""\n'
                "import pytest\n"
                "\n"
                "from app.services.cart import compute_total\n"
                "\n"
                "\n"
                "def test_compute_total_sums_line_items():\n"
                "    lines = [(\"sku-1\", 2, 500), (\"sku-2\", 1, 1250)]\n"
                "    assert compute_total(lines) == 2250\n"
                "\n"
                "\n"
                "def test_compute_total_empty_cart_returns_zero():\n"
                "    assert compute_total([]) == 0\n"
                "\n"
                "\n"
                "def test_compute_total_rejects_negative_quantity():\n"
                "    with pytest.raises(ValueError):\n"
                "        compute_total([(\"sku-1\", -1, 500)])\n"
                "\n"
                "\n"
                "def test_compute_total_rejects_non_positive_unit_price():\n"
                "    with pytest.raises(ValueError):\n"
                "        compute_total([(\"sku-1\", 1, 0)])\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers the summation path, the empty-cart edge, and both "
                "documented ValueError branches."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/slug.py\n"
            "Function: slugify(text: str, *, max_len: int = 60) -> str\n"
            "Behavior: lowercases ASCII, replaces runs of non-alphanumeric "
            "characters with a single hyphen, strips leading/trailing hyphens, "
            "truncates to max_len without leaving a trailing hyphen. Empty or "
            "fully non-alphanumeric input returns an empty string."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_slugify.py",
            "content": (
                '"""Generated tests for slugify."""\n'
                "from app.utils.slug import slugify\n"
                "\n"
                "\n"
                "def test_slugify_lowercases_and_collapses_separators():\n"
                "    assert slugify(\"Hello,  World!\") == \"hello-world\"\n"
                "\n"
                "\n"
                "def test_slugify_strips_edge_hyphens():\n"
                "    assert slugify(\"--lead and trail--\") == \"lead-and-trail\"\n"
                "\n"
                "\n"
                "def test_slugify_truncates_without_trailing_hyphen():\n"
                "    result = slugify(\"abcdefghij\" * 10, max_len=25)\n"
                "    assert len(result) <= 25\n"
                "    assert not result.endswith(\"-\")\n"
                "\n"
                "\n"
                "def test_slugify_non_alphanumeric_only_is_empty():\n"
                "    assert slugify(\"!!! ###\") == \"\"\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Exercises separator collapsing, edge trimming, safe "
                "truncation, and the empty-input contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/billing/discount.py\n"
            "Function: apply_discount(subtotal_cents: int, percent: int) -> int\n"
            "Behavior: returns subtotal_cents minus floor(subtotal_cents * "
            "percent / 100). percent must be between 0 and 100 inclusive, "
            "otherwise ValueError. subtotal_cents must be non-negative, "
            "otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_apply_discount.py",
            "content": (
                '"""Generated tests for apply_discount."""\n'
                "import pytest\n"
                "\n"
                "from app.billing.discount import apply_discount\n"
                "\n"
                "\n"
                "def test_zero_percent_returns_subtotal():\n"
                "    assert apply_discount(1000, 0) == 1000\n"
                "\n"
                "\n"
                "def test_full_discount_returns_zero():\n"
                "    assert apply_discount(1000, 100) == 0\n"
                "\n"
                "\n"
                "def test_discount_floors_fractional_cents():\n"
                "    assert apply_discount(999, 10) == 899\n"
                "\n"
                "\n"
                "def test_percent_out_of_range_raises():\n"
                "    for bad in (-1, 101):\n"
                "        with pytest.raises(ValueError):\n"
                "            apply_discount(1000, bad)\n"
                "\n"
                "\n"
                "def test_negative_subtotal_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        apply_discount(-1, 10)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the boundary percents, the floor behavior on odd "
                "subtotals, and both validation errors."
            ),
        },
    },
    {
        "user": (
            "Module: app/auth/tokens.py\n"
            "Function: is_expired(expires_at: int, now: int) -> bool\n"
            "Behavior: returns True when now is greater than or equal to "
            "expires_at, False otherwise. Both arguments are Unix epoch "
            "seconds."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_token_expiry.py",
            "content": (
                '"""Generated tests for token expiry boundary."""\n'
                "from app.auth.tokens import is_expired\n"
                "\n"
                "\n"
                "def test_token_valid_before_expiry():\n"
                "    assert is_expired(expires_at=2000, now=1999) is False\n"
                "\n"
                "\n"
                "def test_token_expired_at_exact_boundary():\n"
                "    assert is_expired(expires_at=2000, now=2000) is True\n"
                "\n"
                "\n"
                "def test_token_expired_after_expiry():\n"
                "    assert is_expired(expires_at=2000, now=2001) is True\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Locks the >= boundary semantics that session invalidation "
                "depends on."
            ),
        },
    },
    {
        "user": (
            "Module: app/search/pagination.py\n"
            "Function: clamp_page_size(requested: int, *, default: int = 25, "
            "max_size: int = 100) -> int\n"
            "Behavior: non-positive or missing input maps to default; values "
            "above max_size are clamped to max_size; everything else passes "
            "through unchanged."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_clamp_page_size.py",
            "content": (
                '"""Generated tests for page size clamping."""\n'
                "from app.search.pagination import clamp_page_size\n"
                "\n"
                "\n"
                "def test_non_positive_maps_to_default():\n"
                "    for bad in (0, -5):\n"
                "        assert clamp_page_size(bad) == 25\n"
                "\n"
                "\n"
                "def test_oversized_clamps_to_max():\n"
                "    assert clamp_page_size(500, max_size=100) == 100\n"
                "\n"
                "\n"
                "def test_in_range_passes_through():\n"
                "    assert clamp_page_size(40) == 40\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers default fallback, upper clamp, and pass-through in "
                "one focused file."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/retry.py\n"
            "Function: backoff_ms(attempt: int, *, base_ms: int = 100, "
            "factor: float = 2.0, max_ms: int = 30_000) -> int\n"
            "Behavior: returns min(base_ms * factor ** attempt, max_ms) "
            "rounded down to whole milliseconds. attempt starts at 0."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_backoff_ms.py",
            "content": (
                '"""Generated tests for retry backoff computation."""\n'
                "from app.utils.retry import backoff_ms\n"
                "\n"
                "\n"
                "def test_first_attempt_uses_base():\n"
                "    assert backoff_ms(0) == 100\n"
                "\n"
                "\n"
                "def test_exponential_growth():\n"
                "    assert backoff_ms(2, base_ms=100, factor=2.0) == 400\n"
                "\n"
                "\n"
                "def test_caps_at_max():\n"
                "    assert backoff_ms(20) == 30_000\n"
                "\n"
                "\n"
                "def test_never_exceeds_max_for_any_attempt():\n"
                "    assert all(backoff_ms(a) <= 30_000 for a in range(30))\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Verifies base, growth, cap, and an invariant sweep across "
                "attempts."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/ids.py\n"
            "Function: idempotency_key(tenant_id: str, route: str, "
            "body_hash: str) -> str\n"
            "Behavior: returns \"<tenant_id>:<route>:<body_hash>\". Raises "
            "ValueError if any component is empty or contains the \":\" "
            "separator."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_idempotency_key.py",
            "content": (
                '"""Generated tests for idempotency key composition."""\n'
                "import pytest\n"
                "\n"
                "from app.utils.ids import idempotency_key\n"
                "\n"
                "\n"
                "def test_key_joins_components_in_order():\n"
                "    assert (\n"
                "        idempotency_key(\"t1\", \"POST /orders\", \"abc\")\n"
                "        == \"t1:POST /orders:abc\"\n"
                "    )\n"
                "\n"
                "\n"
                "def test_empty_component_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        idempotency_key(\"\", \"route\", \"abc\")\n"
                "\n"
                "\n"
                "def test_separator_in_component_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        idempotency_key(\"t:1\", \"route\", \"abc\")\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Guards the join format and the collision-preventing "
                "validation of the separator."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/text.py\n"
            "Function: truncate_chars(text: str, limit: int) -> str\n"
            "Behavior: returns text unchanged when len(text) <= limit; "
            "otherwise returns the first (limit - 1) characters followed by "
            "the ellipsis character. limit must be >= 1, otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_truncate_chars.py",
            "content": (
                '"""Generated tests for character truncation."""\n'
                "import pytest\n"
                "\n"
                "from app.utils.text import truncate_chars\n"
                "\n"
                "\n"
                "def test_short_text_unchanged():\n"
                "    assert truncate_chars(\"abc\", 5) == \"abc\"\n"
                "\n"
                "\n"
                "def test_exact_limit_unchanged():\n"
                "    assert truncate_chars(\"abcde\", 5) == \"abcde\"\n"
                "\n"
                "\n"
                "def test_long_text_gets_ellipsis():\n"
                "    result = truncate_chars(\"abcdef\", 5)\n"
                "    assert result == \"abcd\\u2026\"\n"
                "\n"
                "\n"
                "def test_limit_below_one_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        truncate_chars(\"abc\", 0)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the boundary at exactly limit and the ellipsis "
                "replacement rule."
            ),
        },
    },
    {
        "user": (
            "Module: app/metrics/rate_limit.py\n"
            "Function: requests_allowed(timestamps: list[int], now: int, *, "
            "window_sec: int = 60, limit: int = 5) -> bool\n"
            "Behavior: returns True when the number of timestamps within the "
            "last window_sec seconds (inclusive of now - window_sec) is "
            "strictly below limit."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_requests_allowed.py",
            "content": (
                '"""Generated tests for sliding-window rate limiting."""\n'
                "from app.metrics.rate_limit import requests_allowed\n"
                "\n"
                "\n"
                "def test_allows_when_window_empty():\n"
                "    assert requests_allowed([], now=1000) is True\n"
                "\n"
                "\n"
                "def test_allows_below_limit():\n"
                "    stamps = [950, 960, 970, 980]\n"
                "    assert requests_allowed(stamps, now=1000, limit=5) is True\n"
                "\n"
                "\n"
                "def test_blocks_at_limit():\n"
                "    stamps = [950, 960, 970, 980, 990]\n"
                "    assert requests_allowed(stamps, now=1000, limit=5) is False\n"
                "\n"
                "\n"
                "def test_old_timestamps_leave_the_window():\n"
                "    stamps = [900, 1000, 1000, 1000, 1000]\n"
                "    assert (\n"
                "        requests_allowed(stamps, now=1000, window_sec=60, limit=5)\n"
                "        is True\n"
                "    )\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Verifies the inclusive window boundary and the strict "
                "below-limit rule."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/dates.py\n"
            "Function: parse_iso_date(value: str) -> \"date\"\n"
            "Behavior: parses a strict YYYY-MM-DD string into a datetime.date. "
            "Anything else (including datetimes with time components and "
            "non-padded months) raises ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_parse_iso_date.py",
            "content": (
                '"""Generated tests for strict ISO date parsing."""\n'
                "import datetime\n"
                "\n"
                "import pytest\n"
                "\n"
                "from app.utils.dates import parse_iso_date\n"
                "\n"
                "\n"
                "def test_parses_valid_date():\n"
                "    assert parse_iso_date(\"2026-02-14\") == datetime.date(\n"
                "        2026, 2, 14\n"
                "    )\n"
                "\n"
                "\n"
                "def test_rejects_datetime_with_time_component():\n"
                "    with pytest.raises(ValueError):\n"
                "        parse_iso_date(\"2026-02-14T10:00:00\")\n"
                "\n"
                "\n"
                "def test_rejects_non_padded_month():\n"
                "    with pytest.raises(ValueError):\n"
                "        parse_iso_date(\"2026-2-14\")\n"
                "\n"
                "\n"
                "def test_rejects_empty_string():\n"
                "    with pytest.raises(ValueError):\n"
                "        parse_iso_date(\"\")\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Locks the strict-format contract against lenient datetime "
                "parsing regressions."
            ),
        },
    },
    {
        "user": (
            "Module: app/rbac/permissions.py\n"
            "Function: can_write(roles: frozenset[str]) -> bool\n"
            "Behavior: returns True only when roles contains \"admin\" or "
            "\"editor\". Empty frozenset and viewer-only sets return False."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_can_write.py",
            "content": (
                '"""Generated tests for write-permission role check."""\n'
                "from app.rbac.permissions import can_write\n"
                "\n"
                "\n"
                "def test_admin_can_write():\n"
                "    assert can_write(frozenset({\"admin\"})) is True\n"
                "\n"
                "\n"
                "def test_editor_can_write():\n"
                "    assert can_write(frozenset({\"editor\"})) is True\n"
                "\n"
                "\n"
                "def test_viewer_cannot_write():\n"
                "    assert can_write(frozenset({\"viewer\"})) is False\n"
                "\n"
                "\n"
                "def test_empty_roles_cannot_write():\n"
                "    assert can_write(frozenset()) is False\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers each allowed role plus the two deny paths."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/luhn.py\n"
            "Function: luhn_valid(digits: str) -> bool\n"
            "Behavior: implements the Luhn checksum over a string of ASCII "
            "digits. Any non-digit character returns False. Empty string "
            "returns False."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_luhn_valid.py",
            "content": (
                '"""Generated tests for the Luhn checksum."""\n'
                "from app.utils.luhn import luhn_valid\n"
                "\n"
                "\n"
                "def test_known_valid_number():\n"
                "    assert luhn_valid(\"4532015112830366\") is True\n"
                "\n"
                "\n"
                "def test_checksum_digit_failure():\n"
                "    assert luhn_valid(\"4532015112830367\") is False\n"
                "\n"
                "\n"
                "def test_non_digit_rejected():\n"
                "    assert luhn_valid(\"4532a153\") is False\n"
                "\n"
                "\n"
                "def test_empty_rejected():\n"
                "    assert luhn_valid(\"\") is False\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Uses a standard test vector plus the failure and "
                "input-validation paths."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/rounding.py\n"
            "Function: round_half_up(value: float, places: int = 0) -> float\n"
            "Behavior: rounds away from zero on exact .5 boundaries at the "
            "given number of decimal places (never banker's rounding)."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_round_half_up.py",
            "content": (
                '"""Generated tests for half-up rounding."""\n'
                "from decimal import Decimal\n"
                "\n"
                "from app.utils.rounding import round_half_up\n"
                "\n"
                "\n"
                "def test_positive_half_rounds_up():\n"
                "    assert round_half_up(2.5) == 3.0\n"
                "\n"
                "\n"
                "def test_negative_half_rounds_away_from_zero():\n"
                "    assert round_half_up(-2.5) == -3.0\n"
                "\n"
                "\n"
                "def test_decimal_places():\n"
                "    assert round_half_up(1.005, 2) == 1.01\n"
                "\n"
                "\n"
                "def test_agrees_with_decimal_half_up():\n"
                "    value = Decimal(\"7.5\")\n"
                "    expected = float(value.quantize(Decimal(\"1\"), "
                "rounding=\"ROUND_HALF_UP\"))\n"
                "    assert round_half_up(7.5) == expected\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Distinguishes half-up from banker's rounding on both signs "
                "and at fractional precision."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/normalize.py\n"
            "Function: normalize_email(address: str) -> str\n"
            "Behavior: trims whitespace, lowercases the full address, and "
            "raises ValueError when the address contains no \"@\" or any "
            "whitespace after trimming."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_normalize_email.py",
            "content": (
                '"""Generated tests for email normalization."""\n'
                "import pytest\n"
                "\n"
                "from app.utils.normalize import normalize_email\n"
                "\n"
                "\n"
                "def test_trims_and_lowercases():\n"
                "    assert normalize_email(\"  User@Example.COM \") == (\n"
                "        \"user@example.com\"\n"
                "    )\n"
                "\n"
                "\n"
                "def test_missing_at_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        normalize_email(\"user.example.com\")\n"
                "\n"
                "\n"
                "def test_internal_whitespace_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        normalize_email(\"us er@example.com\")\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the normalization contract and both rejection rules "
                "used by account deduplication."
            ),
        },
    },
    {
        "user": (
            "Module: app/schedule/intervals.py\n"
            "Function: overlaps(start_a: int, end_a: int, start_b: int, "
            "end_b: int) -> bool\n"
            "Behavior: half-open interval overlap on integer timestamps. "
            "Touching intervals (end_a == start_b) do NOT overlap. Each end "
            "must be greater than its start, otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_interval_overlap.py",
            "content": (
                '"""Generated tests for half-open interval overlap."""\n'
                "import pytest\n"
                "\n"
                "from app.schedule.intervals import overlaps\n"
                "\n"
                "\n"
                "def test_disjoint_intervals():\n"
                "    assert overlaps(0, 10, 20, 30) is False\n"
                "\n"
                "\n"
                "def test_partial_overlap():\n"
                "    assert overlaps(0, 10, 5, 15) is True\n"
                "\n"
                "\n"
                "def test_containment():\n"
                "    assert overlaps(0, 10, 2, 8) is True\n"
                "\n"
                "\n"
                "def test_touching_edges_do_not_overlap():\n"
                "    assert overlaps(0, 10, 10, 20) is False\n"
                "\n"
                "\n"
                "def test_invalid_interval_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        overlaps(10, 0, 0, 5)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers disjoint, partial, containment, the touching-edge "
                "boundary, and malformed input."
            ),
        },
    },
    {
        "user": (
            "Module: app/tree/flatten.py\n"
            "Function: flatten_leaves(node: dict) -> list\n"
            "Behavior: given a nested dict of dicts and lists, returns all "
            "leaf values (non-dict, non-list) in depth-first order. An empty "
            "container returns []."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_flatten_leaves.py",
            "content": (
                '"""Generated tests for nested-container flattening."""\n'
                "from app.tree.flatten import flatten_leaves\n"
                "\n"
                "\n"
                "def test_flat_dict_is_its_own_leaves():\n"
                "    assert flatten_leaves({\"a\": 1, \"b\": 2}) == [1, 2]\n"
                "\n"
                "\n"
                "def test_nested_dicts_depth_first():\n"
                "    node = {\"a\": {\"b\": 1, \"c\": {\"d\": 2}}, \"e\": 3}\n"
                "    assert flatten_leaves(node) == [1, 2, 3]\n"
                "\n"
                "\n"
                "def test_lists_are_traversed_in_order():\n"
                "    node = {\"a\": [1, {\"b\": 2}, 3]}\n"
                "    assert flatten_leaves(node) == [1, 2, 3]\n"
                "\n"
                "\n"
                "def test_empty_containers_return_empty():\n"
                "    assert flatten_leaves({}) == []\n"
                "    assert flatten_leaves({\"a\": []}) == []\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Locks depth-first ordering across dict and list nesting and "
                "the empty-container contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/money/convert.py\n"
            "Function: convert_cents(amount_cents: int, rate: float) -> int\n"
            "Behavior: converts an amount between currencies using a "
            "multiplicative rate, rounding half up to whole cents. rate must "
            "be positive and finite, otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_convert_cents.py",
            "content": (
                '"""Generated tests for currency conversion rounding."""\n'
                "import pytest\n"
                "\n"
                "from app.money.convert import convert_cents\n"
                "\n"
                "\n"
                "def test_identity_rate_is_exact():\n"
                "    assert convert_cents(12345, 1.0) == 12345\n"
                "\n"
                "\n"
                "def test_fractional_result_rounds_half_up():\n"
                "    assert convert_cents(101, 0.5) == 51\n"
                "\n"
                "\n"
                "def test_zero_amount_stays_zero():\n"
                "    assert convert_cents(0, 2.5) == 0\n"
                "\n"
                "\n"
                "def test_non_positive_rate_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        convert_cents(100, 0.0)\n"
                "\n"
                "\n"
                "def test_infinite_rate_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        convert_cents(100, float(\"inf\"))\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers exact identity, half-up rounding of fractional "
                "cents, and rate validation including infinity."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/version.py\n"
            "Function: compare_versions(a: str, b: str) -> int\n"
            "Behavior: compares dotted numeric version strings. Returns -1, "
            "0, or 1. Missing components count as 0, so \"1.2\" equals "
            "\"1.2.0\". Non-numeric components raise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_compare_versions.py",
            "content": (
                '"""Generated tests for dotted version comparison."""\n'
                "import pytest\n"
                "\n"
                "from app.utils.version import compare_versions\n"
                "\n"
                "\n"
                "def test_equal_versions():\n"
                "    assert compare_versions(\"1.2.0\", \"1.2.0\") == 0\n"
                "\n"
                "\n"
                "def test_missing_components_are_zero():\n"
                "    assert compare_versions(\"1.2\", \"1.2.0\") == 0\n"
                "\n"
                "\n"
                "def test_older_and_newer():\n"
                "    assert compare_versions(\"1.9.9\", \"1.10.0\") == -1\n"
                "    assert compare_versions(\"2.0.0\", \"1.9.9\") == 1\n"
                "\n"
                "\n"
                "def test_non_numeric_component_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        compare_versions(\"1.2.beta\", \"1.2.0\")\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins numeric (not lexicographic) ordering, zero-padding of "
                "missing parts, and the validation error."
            ),
        },
    },
    {
        "user": (
            "Module: app/webhooks/signature.py\n"
            "Function: signature_matches(secret: str, payload: bytes, "
            "expected_hex: str) -> bool\n"
            "Behavior: computes HMAC-SHA256 of payload with secret, compares "
            "against expected_hex using a constant-time comparison, returns "
            "bool. expected_hex must be 64 hex characters or the result is "
            "False (no exception)."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_signature_matches.py",
            "content": (
                '"""Generated tests for webhook signature verification."""\n'
                "import hashlib\n"
                "import hmac\n"
                "\n"
                "from app.webhooks.signature import signature_matches\n"
                "\n"
                "\n"
                "def _expected(secret: str, payload: bytes) -> str:\n"
                "    return hmac.new(\n"
                "        secret.encode(), payload, hashlib.sha256\n"
                "    ).hexdigest()\n"
                "\n"
                "\n"
                "def test_valid_signature_matches():\n"
                "    payload = b'{\"order\": 1}'\n"
                "    assert (\n"
                "        signature_matches(\"s3cret\", payload, "
                "_expected(\"s3cret\", payload))\n"
                "        is True\n"
                "    )\n"
                "\n"
                "\n"
                "def test_wrong_secret_fails():\n"
                "    payload = b'{\"order\": 1}'\n"
                "    assert (\n"
                "        signature_matches(\"s3cret\", payload, "
                "_expected(\"other\", payload))\n"
                "        is False\n"
                "    )\n"
                "\n"
                "\n"
                "def test_short_hex_is_false_not_error():\n"
                "    assert signature_matches(\"s3cret\", b\"x\", \"abcd\") is False\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Verifies the HMAC contract, mismatch detection, and the "
                "fail-closed handling of malformed hex."
            ),
        },
    },
    {
        "user": (
            "Module: app/queue/priority.py\n"
            "Function: next_task(queue: list[tuple[int, str]]) -> str | None\n"
            "Behavior: returns the label of the task with the lowest priority "
            "number (ties broken by earliest list position), removing it from "
            "the queue. Returns None for an empty queue without mutating it."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_next_task.py",
            "content": (
                '"""Generated tests for priority queue selection."""\n'
                "from app.queue.priority import next_task\n"
                "\n"
                "\n"
                "def test_empty_queue_returns_none_and_is_unchanged():\n"
                "    queue: list = []\n"
                "    assert next_task(queue) is None\n"
                "    assert queue == []\n"
                "\n"
                "\n"
                "def test_lowest_number_wins():\n"
                "    queue = [(5, \"low\"), (1, \"urgent\"), (3, \"mid\")]\n"
                "    assert next_task(queue) == \"urgent\"\n"
                "\n"
                "\n"
                "def test_tie_breaks_on_earliest_position():\n"
                "    queue = [(2, \"first\"), (2, \"second\")]\n"
                "    assert next_task(queue) == \"first\"\n"
                "\n"
                "\n"
                "def test_selected_task_is_removed():\n"
                "    queue = [(1, \"a\"), (2, \"b\")]\n"
                "    next_task(queue)\n"
                "    assert queue == [(2, \"b\")]\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers empty-queue semantics, ordering, tie-breaking, and "
                "the mutation contract."
            ),
        },
    },
]

REASONING: list[dict] = [
    {
        "user": (
            "Function under analysis: app.services.orders.list_orders"
            "(tenant_id: str, page: int) -> list[OrderRow]\n"
            "Each OrderRow carries a tenant_id field. Propose the core "
            "multi-tenant invariant for this query path."
        ),
        "assistant": {
            "description": (
                "Every order row returned for a given tenant_id must belong "
                "to that tenant, regardless of paging depth."
            ),
            "target": "app.services.orders.list_orders",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.tuples("
                "st.text(min_size=1, max_size=16, alphabet=st.characters("
                "min_codepoint=97, max_codepoint=122)), "
                "st.integers(min_value=1, max_value=500))"
            ),
            "property_check": (
                "all(row.tenant_id == tenant_id for row in rows)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.billing.discount.apply_discount"
            "(subtotal_cents: int, percent: int) -> int\n"
            "Propose the invariant that protects revenue from discount bugs."
        ),
        "assistant": {
            "description": (
                "The discounted total must always stay between zero and the "
                "original subtotal, and applying a 0 percent discount must "
                "be an identity."
            ),
            "target": "app.billing.discount.apply_discount",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=10**9), "
                "st.integers(min_value=0, max_value=100))"
            ),
            "property_check": (
                "0 <= apply_discount(subtotal, percent) <= subtotal"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.auth.sessions.validate(token: str, "
            "now: int) -> Session | None\n"
            "Propose the invariant governing expiry handling."
        ),
        "assistant": {
            "description": (
                "A session returned by validate must always have "
                "expires_at strictly greater than the now value passed in; "
                "boundary equality means expired and must return None."
            ),
            "target": "app.auth.sessions.validate",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=2**31), "
                "st.integers(min_value=0, max_value=3600))"
            ),
            "property_check": (
                "session is None or session.expires_at > now"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.search.pagination.paginate(items: "
            "list, page: int, page_size: int) -> list\n"
            "Propose the invariant linking page, page_size, and output size."
        ),
        "assistant": {
            "description": (
                "Slicing by the paginator must never return more items than "
                "page_size, and concatenating all pages must reproduce the "
                "original list in order."
            ),
            "target": "app.search.pagination.paginate",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples("
                "st.lists(st.integers(), max_size=200), "
                "st.integers(min_value=1, max_value=50), "
                "st.integers(min_value=1, max_value=50))"
            ),
            "property_check": (
                "len(result) <= page_size"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.rbac.enforce(role: str, action: "
            "str) -> bool\n"
            "Role hierarchy: admin > editor > viewer; unknown roles deny "
            "everything. Propose the deny-by-default invariant."
        ),
        "assistant": {
            "description": (
                "Any role not present in the known role table must be denied "
                "for every action, including actions viewers may perform."
            ),
            "target": "app.rbac.enforce",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples("
                "st.text(min_size=1, max_size=24), "
                "st.sampled_from([\"read\", \"write\", \"delete\"]))"
            ),
            "property_check": (
                "(role in KNOWN_ROLES) or (not enforce(role, action))"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.utils.ids.idempotency_key(tenant_id, "
            "route, body_hash) -> str\n"
            "Propose the collision-freedom invariant."
        ),
        "assistant": {
            "description": (
                "Two calls with identical components must produce identical "
                "keys, and two calls differing in any single component must "
                "produce different keys."
            ),
            "target": "app.utils.ids.idempotency_key",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples("
                "st.text(min_size=1, max_size=8, alphabet=st.characters("
                "min_codepoint=97, max_codepoint=122)), "
                "st.text(min_size=1, max_size=8, alphabet=st.characters("
                "min_codepoint=97, max_codepoint=122)))"
            ),
            "property_check": (
                "idempotency_key(a, route, h) == idempotency_key(a, route, h) "
                "and idempotency_key(a, route, h) != idempotency_key(b, route, h)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.metrics.rate_limit.requests_allowed"
            "(timestamps, now, window_sec, limit) -> bool\n"
            "Propose the invariant connecting the limit and window semantics."
        ),
        "assistant": {
            "description": (
                "After a denial, removing any one timestamp from the window "
                "must flip the decision back to allowed, and timestamps "
                "outside the window must never influence the result."
            ),
            "target": "app.metrics.rate_limit.requests_allowed",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.lists(st.integers(min_value=0, max_value=1000), "
                "min_size=0, max_size=10)"
            ),
            "property_check": (
                "requests_allowed(stamps, now, window_sec, limit) == "
                "(sum(1 for t in stamps if now - window_sec <= t <= now) < limit)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.money.convert.convert_cents(amount, "
            "rate) -> int\n"
            "Propose the rounding-consistency invariant."
        ),
        "assistant": {
            "description": (
                "Conversion must be exactly the identity at rate 1.0 and "
                "monotonic in the amount for a fixed positive rate."
            ),
            "target": "app.money.convert.convert_cents",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples("
                "st.integers(min_value=0, max_value=10**7), "
                "st.floats(min_value=1.0001, max_value=1000.0, "
                "allow_nan=False, allow_infinity=False))"
            ),
            "property_check": (
                "convert_cents(0, rate) == 0 and "
                "convert_cents(amount, 1.0) == amount"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.export.redact(record: dict) -> dict\n"
            "record may contain a \"secret\" key at any nesting depth. Propose "
            "the privacy invariant."
        ),
        "assistant": {
            "description": (
                "No exported record may contain any value that was stored "
                "under a key named secret, at any nesting depth."
            ),
            "target": "app.export.redact",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.dictionaries("
                "st.sampled_from([\"name\", \"secret\", \"note\"]), "
                "st.text(max_size=12), max_size=5)"
            ),
            "property_check": (
                "\"secret\" not in redacted and "
                "all(isinstance(v, dict) is False or \"secret\" not in v "
                "for v in redacted.values())"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.utils.slug.slugify(text, max_len=60) "
            "-> str\n"
            "Propose the format invariant of the output."
        ),
        "assistant": {
            "description": (
                "The slug must contain only lowercase ASCII letters, digits, "
                "and hyphens, must not begin or end with a hyphen, and must "
                "never exceed max_len."
            ),
            "target": "app.utils.slug.slugify",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.text(max_size=120), "
                "st.integers(min_value=5, max_value=80))"
            ),
            "property_check": (
                "len(result) <= max_len and not result.startswith(\"-\") "
                "and not result.endswith(\"-\")"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.workflows.transition(run: RunState, "
            "event: str) -> RunState\n"
            "Legal transitions form a fixed table. Propose the state-machine "
            "integrity invariant."
        ),
        "assistant": {
            "description": (
                "A run that has reached a terminal state (succeeded, failed, "
                "cancelled) must reject every event, and no transition may "
                "ever emit a state absent from the table."
            ),
            "target": "app.workflows.transition",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples("
                "st.sampled_from([\"succeeded\", \"failed\", \"cancelled\"]), "
                "st.sampled_from([\"start\", \"complete\", \"fail\", \"cancel\"]))"
            ),
            "property_check": (
                "transition(terminal_state, event) == terminal_state"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.audit.append(ledger: list[dict], "
            "entry: dict) -> int\n"
            "Entries get a monotonically increasing sequence number. Propose "
            "the ordering invariant."
        ),
        "assistant": {
            "description": (
                "Sequence numbers in the ledger must be strictly increasing "
                "by one per append, starting at 1, and appends must not "
                "reorder existing entries."
            ),
            "target": "app.audit.append",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.lists(st.fixed_dictionaries({\"kind\": st.sampled_from("
                "[\"a\", \"b\"])}), min_size=1, max_size=25)"
            ),
            "property_check": (
                "[e[\"seq\"] for e in ledger] == list(range(1, len(ledger) + 1))"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.search.filter_allowed(fields: "
            "list[str], requested: list[str]) -> list[str]\n"
            "Only fields in the allowlist may be returned. Propose the "
            "allowlist invariant."
        ),
        "assistant": {
            "description": (
                "The result must be a subset of the allowlist regardless of "
                "the requested list, and duplicate requests must not produce "
                "duplicate outputs."
            ),
            "target": "app.search.filter_allowed",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples("
                "st.lists(st.sampled_from([\"id\", \"name\", \"email\", "
                "\"secret_note\"]), max_size=10), "
                "st.lists(st.sampled_from([\"id\", \"name\", \"email\"]), "
                "max_size=5))"
            ),
            "property_check": (
                "set(result) <= set(allowlist) and "
                "len(result) == len(set(result))"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.cache.memo.get(key: str) -> object | "
            "None\n"
            "The cache has max_size entries with LRU eviction. Propose the "
            "eviction invariant."
        ),
        "assistant": {
            "description": (
                "The cache size must never exceed max_size, and the most "
                "recently touched key must always still be present."
            ),
            "target": "app.cache.memo",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.lists(st.text(min_size=1, max_size=6, alphabet=st."
                "characters(min_codepoint=97, max_codepoint=99)), "
                "min_size=1, max_size=40)"
            ),
            "property_check": (
                "len(cache) <= max_size and last_key in cache"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.tenants.scope(query, tenant_id)\n"
            "query is a select over a shared table; scope must add a tenant "
            "filter. Propose the isolation invariant for composed queries."
        ),
        "assistant": {
            "description": (
                "Scoping must be idempotent: applying it twice adds no "
                "additional filter beyond the single tenant predicate, and "
                "the tenant predicate must be present after one application."
            ),
            "target": "app.tenants.scope",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.text(min_size=1, max_size=12, alphabet=st.characters("
                "min_codepoint=97, max_codepoint=122))"
            ),
            "property_check": (
                "has_tenant_predicate(scope(query, tenant_id)) and "
                "str(scope(scope(query, tenant_id), tenant_id)) == "
                "str(scope(query, tenant_id))"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.stats.percentile(values: list[float], "
            "p: float) -> float\n"
            "p is in [0, 100]. Propose the order-statistics invariant."
        ),
        "assistant": {
            "description": (
                "The returned percentile must lie between the minimum and "
                "maximum of the input values inclusive, and the 50th "
                "percentile of a single-element list is that element."
            ),
            "target": "app.stats.percentile",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples("
                "st.lists(st.floats(allow_nan=False, allow_infinity=False), "
                "min_size=1, max_size=30), "
                "st.floats(min_value=0.0, max_value=100.0))"
            ),
            "property_check": (
                "min(values) <= result <= max(values)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.users.deactivate(user_id: str, "
            "actor: str) -> None\n"
            "Admins may deactivate anyone; users may deactivate only "
            "themselves. Propose the authorization invariant."
        ),
        "assistant": {
            "description": (
                "Deactivation must occur only when the actor is an admin or "
                "the actor equals the target user id; any other combination "
                "must raise PermissionError and leave state untouched."
            ),
            "target": "app.users.deactivate",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples("
                "st.text(min_size=1, max_size=10, alphabet=st.characters("
                "min_codepoint=97, max_codepoint=102)), "
                "st.sampled_from([\"admin\", \"self\", \"other\"]))"
            ),
            "property_check": (
                "(actor == \"admin\" or actor == user_id) or "
                "raises_permission_error(deactivate, user_id, actor)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.exports.csv_escape(field: str) -> "
            "str\n"
            "Propose the injection-safety invariant for CSV output."
        ),
        "assistant": {
            "description": (
                "A field beginning with a formula trigger character (=, +, "
                "-, @) must be emitted prefixed with a single quote so "
                "spreadsheet formula injection is impossible, and embedded "
                "quotes must always be doubled."
            ),
            "target": "app.exports.csv_escape",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.text(alphabet=st.sampled_from([\"=\", \"+\", \"-\", \"@\", "
                "\"a\", '\"', \",\"]), min_size=1, max_size=20)"
            ),
            "property_check": (
                "(field[0] not in \"=+-@\") or (result[0] == \"'\" and "
                "result[1] == field[0])"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.audit.verify_chain(entries: "
            "list[dict]) -> bool\n"
            "Each entry stores prev_hash and hash. Propose the tamper-"
            "evidence invariant."
        ),
        "assistant": {
            "description": (
                "Verification must accept the original chain and reject any "
                "single-entry mutation: changing any entry's payload, hash, "
                "or prev_hash flips the result to False."
            ),
            "target": "app.audit.verify_chain",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.integers(min_value=0, max_value=9)"
            ),
            "property_check": (
                "verify_chain(original) and not verify_chain(mutate(original, "
                "index))"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.api.errors.safe_message(exc: "
            "Exception) -> str\n"
            "Internal exceptions may embed SQL or paths. Propose the leak-"
            "prevention invariant."
        ),
        "assistant": {
            "description": (
                "The safe message must be drawn only from the fixed mapping "
                "of exception classes to public strings and must never "
                "contain the original exception text, file paths, or SQL "
                "fragments."
            ),
            "target": "app.api.errors.safe_message",
            "category": "auth",
            "hypothesis_strategy": (
                "st.sampled_from([\"ValueError\", \"KeyError\", "
                "\"PermissionError\", \"TimeoutError\"])"
            ),
            "property_check": (
                "result in PUBLIC_MESSAGES.values() and "
                "secret_marker not in result"
            ),
        },
    },
]

REPORTING: list[dict] = [
    {
        "user": (
            '{"run_id": "run-3f2a", "totals": {"passed": 42, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 81234, '
            '"failures": []}'
        ),
        "assistant": {
            "summary": (
                "All 42 tests passed with no failures, errors, or timeouts. "
                "The run completed in about 81 seconds. No issues require "
                "attention before merge."
            ),
            "findings": [],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-9b1c", "totals": {"passed": 30, "failed": 3, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 95200, '
            '"failures": ['
            '{"test": "test_checkout_gateway_timeout", "outcome": "FAILED", '
            '"duration_ms": 30500}, '
            '{"test": "test_checkout_gateway_retries", "outcome": "FAILED", '
            '"duration_ms": 30400}, '
            '{"test": "test_checkout_gateway_circuit_open", "outcome": '
            '"FAILED", "duration_ms": 30100}]}'
        ),
        "assistant": {
            "summary": (
                "30 of 33 tests passed. The three failures share the "
                "checkout gateway surface and each took around 30 seconds, "
                "which points to timeouts against an unreachable or slow "
                "gateway rather than logic errors. Investigate gateway "
                "connectivity from the test environment first."
            ),
            "findings": [
                {
                    "root_cause": (
                        "checkout gateway calls time out at roughly 30 "
                        "seconds"
                    ),
                    "affected_tests": [
                        "test_checkout_gateway_timeout",
                        "test_checkout_gateway_retries",
                        "test_checkout_gateway_circuit_open",
                    ],
                    "severity": "high",
                    "explanation": (
                        "All three failures cluster on the checkout gateway "
                        "path with nearly identical 30-second durations, "
                        "consistent with a network or dependency outage "
                        "rather than code regressions."
                    ),
                }
            ],
            "priority_order": [
                "checkout gateway calls time out at roughly 30 seconds"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-c4d7", "totals": {"passed": 12, "failed": 0, '
            '"error": 6, "timeout": 0, "not_run": 4}, "duration_ms": 40100, '
            '"failures": ['
            '{"test": "test_ingestor_load", "outcome": "ERROR", '
            '"duration_ms": 120}, '
            '{"test": "test_ingestor_pin", "outcome": "ERROR", '
            '"duration_ms": 118}, '
            '{"test": "test_ingestor_detect_node", "outcome": "ERROR", '
            '"duration_ms": 119}, '
            '{"test": "test_ingestor_detect_python", "outcome": "ERROR", '
            '"duration_ms": 117}, '
            '{"test": "test_ingestor_reject_unknown_ref", "outcome": '
            '"ERROR", "duration_ms": 121}, '
            '{"test": "test_ingestor_tree_verification", "outcome": '
            '"ERROR", "duration_ms": 116}], '
            '"notes": "collection error: missing module ingestor_support in '
            'conftest"}'
        ),
        "assistant": {
            "summary": (
                "Six ingestor tests errored during collection and four "
                "tests could not run because a shared support module is "
                "missing from the test configuration. The 12 tests that "
                "collected successfully all passed. Fix the missing module "
                "to unlock the blocked suite."
            ),
            "findings": [
                {
                    "root_cause": (
                        "missing ingestor_support module breaks test "
                        "collection"
                    ),
                    "affected_tests": [
                        "test_ingestor_load",
                        "test_ingestor_pin",
                        "test_ingestor_detect_node",
                        "test_ingestor_detect_python",
                        "test_ingestor_reject_unknown_ref",
                        "test_ingestor_tree_verification",
                    ],
                    "severity": "high",
                    "explanation": (
                        "A collection-time import failure prevents six "
                        "ingestor tests from running and leaves four more "
                        "unexecuted; the passing 12 tests confirm the rest "
                        "of the suite is healthy."
                    ),
                }
            ],
            "priority_order": [
                "missing ingestor_support module breaks test collection"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-7e55", "totals": {"passed": 19, "failed": 2, '
            '"error": 0, "timeout": 1, "not_run": 0}, "duration_ms": 240000, '
            '"failures": ['
            '{"test": "test_report_render_large_table", "outcome": '
            '"TIMEOUT", "duration_ms": 120000}, '
            '{"test": "test_report_totals_alignment", "outcome": "FAILED", '
            '"duration_ms": 2100}, '
            '{"test": "test_report_empty_state", "outcome": "FAILED", '
            '"duration_ms": 1800}]}'
        ),
        "assistant": {
            "summary": (
                "19 of 22 tests passed. One report-rendering test timed out "
                "at two minutes and two smaller report tests failed "
                "outright. The timeout dominates the run duration and "
                "should be investigated first."
            ),
            "findings": [
                {
                    "root_cause": (
                        "large-table rendering exceeds the two-minute test "
                        "budget"
                    ),
                    "affected_tests": ["test_report_render_large_table"],
                    "severity": "high",
                    "explanation": (
                        "The timeout consumed half the total run duration, "
                        "suggesting either a performance regression or an "
                        "unrealistically large fixture."
                    ),
                },
                {
                    "root_cause": (
                        "report totals and empty-state output drifted from "
                        "expected format"
                    ),
                    "affected_tests": [
                        "test_report_totals_alignment",
                        "test_report_empty_state",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "Both failures are fast and confined to report "
                        "formatting, consistent with a recent template or "
                        "formatting change."
                    ),
                },
            ],
            "priority_order": [
                "large-table rendering exceeds the two-minute test budget",
                "report totals and empty-state output drifted from expected "
                "format",
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-a01f", "totals": {"passed": 8, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 15300, '
            '"failures": ['
            '{"test": "test_receipt_tamper_rejection", "outcome": "FAILED", '
            '"duration_ms": 940}]}'
        ),
        "assistant": {
            "summary": (
                "8 of 9 tests passed. The receipt tamper-rejection test "
                "failed, which is a security-relevant regression: modified "
                "receipts must never verify. Treat this as a release "
                "blocker."
            ),
            "findings": [
                {
                    "root_cause": (
                        "tampered receipts are no longer rejected by the "
                        "verifier"
                    ),
                    "affected_tests": ["test_receipt_tamper_rejection"],
                    "severity": "high",
                    "explanation": (
                        "The integrity guarantee depends on rejecting "
                        "modified receipts; a failure here undermines the "
                        "core trust model and must be fixed before any "
                        "release."
                    ),
                }
            ],
            "priority_order": [
                "tampered receipts are no longer rejected by the verifier"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-5d2e", "totals": {"passed": 0, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 27}, "duration_ms": 1200, '
            '"failures": [], "notes": "no tests collected"}'
        ),
        "assistant": {
            "summary": (
                "No tests were collected, so the run produced no evidence "
                "either way. 27 expected tests were not executed in about "
                "one second. Check the test discovery configuration before "
                "trusting this result."
            ),
            "findings": [
                {
                    "root_cause": (
                        "test discovery collected nothing"
                    ),
                    "affected_tests": [],
                    "severity": "high",
                    "explanation": (
                        "A zero-collection run usually means a wrong test "
                        "path, a broken conftest, or a misconfigured "
                        "runner; the absence of failures is not a pass."
                    ),
                }
            ],
            "priority_order": ["test discovery collected nothing"],
        },
    },
    {
        "user": (
            '{"run_id": "run-2c9b", "totals": {"passed": 25, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 61000, '
            '"failures": ['
            '{"test": "test_rbac_viewer_denied_write", "outcome": "FAILED", '
            '"duration_ms": 300}]}'
        ),
        "assistant": {
            "summary": (
                "25 of 26 tests passed. The single failure is an "
                "authorization test asserting that viewers cannot write, "
                "meaning a deny path regressed. Authorization regressions "
                "take priority over unrelated cleanup."
            ),
            "findings": [
                {
                    "root_cause": (
                        "viewer role is no longer denied write access"
                    ),
                    "affected_tests": ["test_rbac_viewer_denied_write"],
                    "severity": "high",
                    "explanation": (
                        "A failing deny-path test indicates the permission "
                        "matrix changed unintentionally or the check was "
                        "bypassed during refactoring."
                    ),
                }
            ],
            "priority_order": [
                "viewer role is no longer denied write access"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-ff10", "totals": {"passed": 21, "failed": 4, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 47800, '
            '"failures": ['
            '{"test": "test_slug_unicode_input", "outcome": "FAILED", '
            '"duration_ms": 210}, '
            '{"test": "test_slug_emoji_input", "outcome": "FAILED", '
            '"duration_ms": 190}, '
            '{"test": "test_slug_mixed_script", "outcome": "FAILED", '
            '"duration_ms": 205}, '
            '{"test": "test_slug_empty_after_strip", "outcome": "FAILED", '
            '"duration_ms": 185}]}'
        ),
        "assistant": {
            "summary": (
                "21 of 25 tests passed. All four failures are slugify tests "
                "involving unicode, emoji, mixed scripts, and "
                "empty-after-strip inputs, suggesting the normalization "
                "step changed for non-ASCII text. The failures are fast and "
                "isolated to one module."
            ),
            "findings": [
                {
                    "root_cause": (
                        "slugify mishandles non-ASCII and edge-case inputs"
                    ),
                    "affected_tests": [
                        "test_slug_unicode_input",
                        "test_slug_emoji_input",
                        "test_slug_mixed_script",
                        "test_slug_empty_after_strip",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "The failure set is confined to unicode-family "
                        "inputs across one function, pointing at a single "
                        "normalization or encoding regression rather than "
                        "widespread breakage."
                    ),
                }
            ],
            "priority_order": [
                "slugify mishandles non-ASCII and edge-case inputs"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-31ab", "totals": {"passed": 33, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 3}, "duration_ms": 70400, '
            '"failures": [], "notes": "3 tests deselected by marker '
            'slow"}'
        ),
        "assistant": {
            "summary": (
                "All 33 executed tests passed and 3 tests marked slow were "
                "deselected by configuration, not by failure. The run is "
                "healthy for the selected scope. Note the coverage gap from "
                "the deselected tests before signing off."
            ),
            "findings": [],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-88cc", "totals": {"passed": 14, "failed": 6, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 52900, '
            '"failures": ['
            '{"test": "test_ledger_append_sequence", "outcome": "FAILED", '
            '"duration_ms": 410}, '
            '{"test": "test_ledger_prev_hash_binding", "outcome": "FAILED", '
            '"duration_ms": 405}, '
            '{"test": "test_ledger_verify_full_chain", "outcome": "FAILED", '
            '"duration_ms": 420}, '
            '{"test": "test_ledger_reject_duplicate_seq", "outcome": '
            '"FAILED", "duration_ms": 398}, '
            '{"test": "test_ledger_genesis_hash", "outcome": "FAILED", '
            '"duration_ms": 401}, '
            '{"test": "test_ledger_concurrent_append", "outcome": '
            '"FAILED", "duration_ms": 415}]}'
        ),
        "assistant": {
            "summary": (
                "14 of 20 tests passed, but every ledger test failed across "
                "sequence numbering, hash binding, verification, and "
                "concurrency. A systemic ledger regression such as a changed "
                "hash canonicalization is more likely than six independent "
                "bugs. Treat the ledger subsystem as broken until the "
                "common cause is found."
            ),
            "findings": [
                {
                    "root_cause": (
                        "systemic ledger regression across all hash and "
                        "sequence behavior"
                    ),
                    "affected_tests": [
                        "test_ledger_append_sequence",
                        "test_ledger_prev_hash_binding",
                        "test_ledger_verify_full_chain",
                        "test_ledger_reject_duplicate_seq",
                        "test_ledger_genesis_hash",
                        "test_ledger_concurrent_append",
                    ],
                    "severity": "high",
                    "explanation": (
                        "The entire ledger test group failing together "
                        "points to one shared root cause, most plausibly a "
                        "canonical-serialization or hashing change, rather "
                        "than six independent defects."
                    ),
                }
            ],
            "priority_order": [
                "systemic ledger regression across all hash and sequence "
                "behavior"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-b7d3", "totals": {"passed": 17, "failed": 1, '
            '"error": 1, "timeout": 0, "not_run": 0}, "duration_ms": 36500, '
            '"failures": ['
            '{"test": "test_health_probe_ready", "outcome": "FAILED", '
            '"duration_ms": 520}, '
            '{"test": "test_health_probe_socket_cleanup", "outcome": '
            '"ERROR", "duration_ms": 810}]}'
        ),
        "assistant": {
            "summary": (
                "17 of 19 tests passed. One health-probe test failed and "
                "another errored during socket cleanup, suggesting the "
                "probe now leaks a bound port between checks. Fix the "
                "cleanup path and re-verify the readiness determination "
                "together."
            ),
            "findings": [
                {
                    "root_cause": (
                        "health probe leaks a bound socket between checks"
                    ),
                    "affected_tests": [
                        "test_health_probe_ready",
                        "test_health_probe_socket_cleanup",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "A readiness failure paired with a teardown error "
                        "on the same probe indicates resource cleanup is "
                        "interfering with subsequent checks."
                    ),
                }
            ],
            "priority_order": [
                "health probe leaks a bound socket between checks"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-40e9", "totals": {"passed": 11, "failed": 0, '
            '"error": 0, "timeout": 2, "not_run": 1}, "duration_ms": 305000, '
            '"failures": ['
            '{"test": "test_model_server_startup", "outcome": "TIMEOUT", '
            '"duration_ms": 120000}, '
            '{"test": "test_model_server_readiness_poll", "outcome": '
            '"TIMEOUT", "duration_ms": 120000}, '
            '{"test": "test_model_server_teardown", "outcome": "NOT_RUN", '
            '"duration_ms": 0}]}'
        ),
        "assistant": {
            "summary": (
                "11 tests passed, but both model-server startup tests "
                "timed out at two minutes each and the teardown test never "
                "ran as a result. The dominating cost is startup, so "
                "validate that the runtime binary and configuration load "
                "within budget before rerunning the suite."
            ),
            "findings": [
                {
                    "root_cause": (
                        "model server startup exceeds the two-minute "
                        "readiness budget"
                    ),
                    "affected_tests": [
                        "test_model_server_startup",
                        "test_model_server_readiness_poll",
                        "test_model_server_teardown",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Two back-to-back startup timeouts consumed four "
                        "minutes and left the teardown test unexecuted; the "
                        "downstream not-run status is a consequence, not an "
                        "independent failure."
                    ),
                }
            ],
            "priority_order": [
                "model server startup exceeds the two-minute readiness "
                "budget"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-6a77", "totals": {"passed": 28, "failed": 2, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 44900, '
            '"failures": ['
            '{"test": "test_rls_cross_tenant_read_blocked", "outcome": '
            '"FAILED", "duration_ms": 640}, '
            '{"test": "test_rls_cross_tenant_write_blocked", "outcome": '
            '"FAILED", "duration_ms": 610}]}'
        ),
        "assistant": {
            "summary": (
                "28 of 30 tests passed. Both failures are row-level "
                "security tests asserting cross-tenant reads and writes are "
                "blocked, which means tenant isolation is currently "
                "breached in the tested configuration. This is a "
                "highest-severity data-isolation regression."
            ),
            "findings": [
                {
                    "root_cause": (
                        "row-level security no longer blocks cross-tenant "
                        "access"
                    ),
                    "affected_tests": [
                        "test_rls_cross_tenant_read_blocked",
                        "test_rls_cross_tenant_write_blocked",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Both isolation directions failing together "
                        "suggests the RLS policy was dropped, disabled, or "
                        "bypassed by a new query path; all tenants are "
                        "potentially affected."
                    ),
                }
            ],
            "priority_order": [
                "row-level security no longer blocks cross-tenant access"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-d508", "totals": {"passed": 22, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 38200, '
            '"failures": ['
            '{"test": "test_env_policy_denies_dangerous_vars", "outcome": '
            '"FAILED", "duration_ms": 240}]}'
        ),
        "assistant": {
            "summary": (
                "22 of 23 tests passed. The environment-policy denylist "
                "test failed, meaning at least one dangerous variable is no "
                "longer stripped from the execution environment. Restore "
                "the denylist before any further sandboxed runs."
            ),
            "findings": [
                {
                    "root_cause": (
                        "environment policy denylist is missing a dangerous "
                        "variable"
                    ),
                    "affected_tests": ["test_env_policy_denies_dangerous_vars"],
                    "severity": "high",
                    "explanation": (
                        "A denylist gap can leak credentials or host "
                        "configuration into sandboxed processes, so this "
                        "failure has direct security impact."
                    ),
                }
            ],
            "priority_order": [
                "environment policy denylist is missing a dangerous variable"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-1b4f", "totals": {"passed": 36, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 112000, '
            '"failures": []}'
        ),
        "assistant": {
            "summary": (
                "All 36 tests passed in about 112 seconds with no errors or "
                "timeouts. The suite is fully green across its current "
                "scope. Nothing blocks merge on the basis of this run."
            ),
            "findings": [],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-c9e2", "totals": {"passed": 9, "failed": 5, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 27600, '
            '"failures": ['
            '{"test": "test_gateway_missing_key_rejected", "outcome": '
            '"FAILED", "duration_ms": 310}, '
            '{"test": "test_gateway_wrong_key_rejected", "outcome": '
            '"FAILED", "duration_ms": 305}, '
            '{"test": "test_gateway_source_bearing_rejected", "outcome": '
            '"FAILED", "duration_ms": 320}, '
            '{"test": "test_gateway_rate_limited", "outcome": "FAILED", '
            '"duration_ms": 300}, '
            '{"test": "test_gateway_observation_only_ok", "outcome": '
            '"FAILED", "duration_ms": 290}]}'
        ),
        "assistant": {
            "summary": (
                "9 of 14 tests passed, and all five gateway "
                "authorization tests failed as a group, including the "
                "positive control. When even the expected-success case "
                "fails, the gateway is most likely unreachable or returning "
                "an error for every request. Check service availability "
                "before debugging individual rejection rules."
            ),
            "findings": [
                {
                    "root_cause": (
                        "gateway rejects every request including the valid "
                        "control case"
                    ),
                    "affected_tests": [
                        "test_gateway_missing_key_rejected",
                        "test_gateway_wrong_key_rejected",
                        "test_gateway_source_bearing_rejected",
                        "test_gateway_rate_limited",
                        "test_gateway_observation_only_ok",
                    ],
                    "severity": "high",
                    "explanation": (
                        "A uniform failure across negative and positive "
                        "tests indicates the gateway itself is down or "
                        "misconfigured, since correct rejections and the "
                        "valid request should not fail the same way."
                    ),
                }
            ],
            "priority_order": [
                "gateway rejects every request including the valid control "
                "case"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-e3b6", "totals": {"passed": 20, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 33400, '
            '"failures": ['
            '{"test": "test_pipeline_teardown_verified", "outcome": '
            '"FAILED", "duration_ms": 1100}]}'
        ),
        "assistant": {
            "summary": (
                "20 of 21 tests passed. The teardown-verification test "
                "failed, so the pipeline is not provably cleaning up its "
                "processes and filesystem state. An unverifiable teardown "
                "is treated as a failed teardown by the acceptance rules."
            ),
            "findings": [
                {
                    "root_cause": (
                        "pipeline teardown cannot be verified after the run"
                    ),
                    "affected_tests": ["test_pipeline_teardown_verified"],
                    "severity": "medium",
                    "explanation": (
                        "The acceptance contract requires positive proof of "
                        "cleanup; a failed verification blocks reuse of the "
                        "environment even if processes appear gone."
                    ),
                }
            ],
            "priority_order": [
                "pipeline teardown cannot be verified after the run"
            ],
        },
    },
]
