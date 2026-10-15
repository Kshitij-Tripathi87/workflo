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
    {
        "user": (
            "Module: app/text/wrap.py\n"
            "Function: wrap_words(text: str, width: int) -> list[str]\n"
            "Behavior: splits text into lines of at most width characters, "
            "breaking on spaces; a single word longer than width is placed "
            "on its own line unbroken. width must be >= 1, otherwise "
            "ValueError. Empty text returns []."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_wrap_words.py",
            "content": (
                '"""Generated tests for word wrapping."""\n'
                "import pytest\n"
                "\n"
                "from app.text.wrap import wrap_words\n"
                "\n"
                "\n"
                "def test_wraps_at_width():\n"
                "    assert wrap_words(\"a b c\", 3) == [\"a b\", \"c\"]\n"
                "\n"
                "\n"
                "def test_long_word_gets_own_line():\n"
                "    assert wrap_words(\"abcdefgh x\", 4) == [\n"
                "        \"abcdefgh\",\n"
                "        \"x\",\n"
                "    ]\n"
                "\n"
                "\n"
                "def test_empty_text_returns_empty_list():\n"
                "    assert wrap_words(\"\", 10) == []\n"
                "\n"
                "\n"
                "def test_zero_width_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        wrap_words(\"a\", 0)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the width boundary, the unbreakable-word rule, and "
                "the empty and invalid inputs."
            ),
        },
    },
    {
        "user": (
            "Module: app/config/merge.py\n"
            "Function: merge_defaults(overrides: dict, defaults: dict) -> dict\n"
            "Behavior: returns a new dict where values from overrides take "
            "precedence over defaults for matching keys; keys present only "
            "in either input are preserved. Neither input is mutated. "
            "Nested dicts are not merged recursively."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_merge_defaults.py",
            "content": (
                '"""Generated tests for shallow config merging."""\n'
                "from app.config.merge import merge_defaults\n"
                "\n"
                "\n"
                "def test_override_wins_on_conflict():\n"
                "    assert merge_defaults({\"a\": 2}, {\"a\": 1}) == {\"a\": 2}\n"
                "\n"
                "\n"
                "def test_union_of_keys_is_preserved():\n"
                "    result = merge_defaults({\"b\": 2}, {\"a\": 1})\n"
                "    assert result == {\"a\": 1, \"b\": 2}\n"
                "\n"
                "\n"
                "def test_inputs_are_not_mutated():\n"
                "    overrides = {\"a\": 2}\n"
                "    defaults = {\"a\": 1, \"b\": 3}\n"
                "    merge_defaults(overrides, defaults)\n"
                "    assert overrides == {\"a\": 2}\n"
                "    assert defaults == {\"a\": 1, \"b\": 3}\n"
                "\n"
                "\n"
                "def test_none_override_still_wins():\n"
                "    assert merge_defaults({\"a\": None}, {\"a\": 1})[\"a\"] is None\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers precedence, key union, immutability of inputs, and "
                "the None-wins subtlety."
            ),
        },
    },
    {
        "user": (
            "Module: app/search/bisect.py\n"
            "Function: insertion_point(sorted_items: list[int], target: int) "
            "-> int\n"
            "Behavior: returns the index at which target should be inserted "
            "to keep sorted_items sorted; if target already exists, returns "
            "the index of its first occurrence. Works on an empty list by "
            "returning 0."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_insertion_point.py",
            "content": (
                '"""Generated tests for sorted insertion point."""\n'
                "from app.search.bisect import insertion_point\n"
                "\n"
                "\n"
                "def test_middle_insertion():\n"
                "    assert insertion_point([1, 3, 5], 4) == 2\n"
                "\n"
                "\n"
                "def test_existing_target_returns_first_occurrence():\n"
                "    assert insertion_point([1, 2, 2, 3], 2) == 1\n"
                "\n"
                "\n"
                "def test_target_before_all():\n"
                "    assert insertion_point([5, 6], 1) == 0\n"
                "\n"
                "\n"
                "def test_target_after_all():\n"
                "    assert insertion_point([5, 6], 9) == 2\n"
                "\n"
                "\n"
                "def test_empty_list_returns_zero():\n"
                "    assert insertion_point([], 7) == 0\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers interior insertion, first-occurrence semantics, "
                "both extremes, and the empty-list contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/text/csv.py\n"
            "Function: split_csv_line(line: str) -> list[str]\n"
            "Behavior: splits a single CSV line on commas; a field wrapped "
            "in double quotes may contain commas and escaped double quotes "
            "(\"\") are unescaped to a single quote character. Returns an "
            "empty list for an empty line."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_split_csv_line.py",
            "content": (
                '"""Generated tests for CSV field splitting."""\n'
                "from app.text.csv import split_csv_line\n"
                "\n"
                "\n"
                "def test_plain_fields_split_on_commas():\n"
                "    assert split_csv_line(\"a,b,c\") == [\"a\", \"b\", \"c\"]\n"
                "\n"
                "\n"
                "def test_quoted_field_keeps_comma():\n"
                "    assert split_csv_line(\"a,\\\"b,c\\\"\") == [\"a\", \"b,c\"]\n"
                "\n"
                "\n"
                "def test_escaped_quotes_are_unescaped():\n"
                "    assert split_csv_line(\"\\\"say \\\"\\\"hi\\\"\\\"\") == [\n"
                "        'say \"hi\"'\n"
                "    ]\n"
                "\n"
                "\n"
                "def test_empty_line_returns_empty_list():\n"
                "    assert split_csv_line(\"\") == []\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers plain splitting, quoted commas, escaped-quote "
                "unescaping, and the empty-line contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/auth/strength.py\n"
            "Function: score_password(password: str) -> int\n"
            "Behavior: returns 0-4. One point each for: length >= 8, "
            "contains a digit, contains an uppercase letter, contains a "
            "non-alphanumeric character. Empty string scores 0."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_score_password.py",
            "content": (
                '"""Generated tests for password strength scoring."""\n'
                "from app.auth.strength import score_password\n"
                "\n"
                "\n"
                "def test_empty_scores_zero():\n"
                "    assert score_password(\"\") == 0\n"
                "\n"
                "\n"
                "def test_short_lowercase_scores_zero():\n"
                "    assert score_password(\"abc\") == 0\n"
                "\n"
                "\n"
                "def test_long_lowercase_scores_one():\n"
                "    assert score_password(\"abcdefgh\") == 1\n"
                "\n"
                "\n"
                "def test_all_criteria_scores_four():\n"
                "    assert score_password(\"Abcdefg1!\") == 4\n"
                "\n"
                "\n"
                "def test_length_and_digit_only_scores_two():\n"
                "    assert score_password(\"abcd1234\") == 2\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins each scoring criterion and the boundary at length 8."
            ),
        },
    },
    {
        "user": (
            "Module: app/money/format.py\n"
            "Function: format_cents(amount_cents: int, symbol: str = \"$\") "
            "-> str\n"
            "Behavior: renders cents as a currency string with a decimal "
            "point, e.g. 123456 -> \"$1234.56\". Negative amounts prefix a "
            "minus sign before the symbol, e.g. -5 -> \"$-0.05\". Zero "
            "renders as \"$0.00\"."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_format_cents.py",
            "content": (
                '"""Generated tests for cents formatting."""\n'
                "from app.money.format import format_cents\n"
                "\n"
                "\n"
                "def test_positive_amount():\n"
                "    assert format_cents(123456) == \"$1234.56\"\n"
                "\n"
                "\n"
                "def test_zero_amount():\n"
                "    assert format_cents(0) == \"$0.00\"\n"
                "\n"
                "\n"
                "def test_negative_amount_prefixes_minus():\n"
                "    assert format_cents(-5) == \"$-0.05\"\n"
                "\n"
                "\n"
                "def test_custom_symbol():\n"
                "    assert format_cents(100, symbol=\"EUR \") == \"EUR 1.00\"\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers positive, zero, negative, and custom-symbol "
                "rendering including the minus-before-symbol rule."
            ),
        },
    },
    {
        "user": (
            "Module: app/text/brackets.py\n"
            "Function: is_balanced(text: str) -> bool\n"
            "Behavior: returns True when every bracket in text — () [], {} "
            "— is closed in the correct order. Non-bracket characters are "
            "ignored. An empty string returns True. A closer without a "
            "matching opener returns False."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_is_balanced.py",
            "content": (
                '"""Generated tests for bracket balancing."""\n'
                "from app.text.brackets import is_balanced\n"
                "\n"
                "\n"
                "def test_simple_pairs_balance():\n"
                "    assert is_balanced(\"(a[b]{c})\") is True\n"
                "\n"
                "\n"
                "def test_wrong_order_is_unbalanced():\n"
                "    assert is_balanced(\"([)]\") is False\n"
                "\n"
                "\n"
                "def test_unclosed_opener_is_unbalanced():\n"
                "    assert is_balanced(\"(\") is False\n"
                "\n"
                "\n"
                "def test_stray_closer_is_unbalanced():\n"
                "    assert is_balanced(\")\") is False\n"
                "\n"
                "\n"
                "def test_empty_string_is_balanced():\n"
                "    assert is_balanced(\"\") is True\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers nesting order, both unmatched directions, "
                "non-bracket noise, and the empty contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/numerals/roman.py\n"
            "Function: to_roman(number: int) -> str\n"
            "Behavior: converts 1..3999 to uppercase Roman numerals using "
            "subtractive notation (IV, IX, XL, XC, CD, CM). 0 or values "
            "above 3999 raise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_to_roman.py",
            "content": (
                '"""Generated tests for Roman numeral conversion."""\n'
                "import pytest\n"
                "\n"
                "from app.numerals.roman import to_roman\n"
                "\n"
                "\n"
                "def test_single_digits():\n"
                "    assert to_roman(1) == \"I\"\n"
                "    assert to_roman(4) == \"IV\"\n"
                "    assert to_roman(9) == \"IX\"\n"
                "\n"
                "\n"
                "def test_tens_use_subtractive_notation():\n"
                "    assert to_roman(40) == \"XL\"\n"
                "    assert to_roman(90) == \"XC\"\n"
                "\n"
                "\n"
                "def test_large_value():\n"
                "    assert to_roman(1994) == \"MCMXCIV\"\n"
                "\n"
                "\n"
                "def test_out_of_range_raises():\n"
                "    for bad in (0, 4000):\n"
                "        with pytest.raises(ValueError):\n"
                "            to_roman(bad)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins subtractive pairs, a known composite vector, and both "
                "range violations."
            ),
        },
    },
    {
        "user": (
            "Module: app/tree/depth.py\n"
            "Function: flatten_depth(node: list, max_depth: int) -> list\n"
            "Behavior: flattens nested lists up to max_depth levels; "
            "elements deeper than max_depth are kept as nested lists. "
            "Non-list elements are kept as-is. max_depth must be >= 0, "
            "otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_flatten_depth.py",
            "content": (
                '"""Generated tests for depth-limited flattening."""\n'
                "import pytest\n"
                "\n"
                "from app.tree.depth import flatten_depth\n"
                "\n"
                "\n"
                "def test_full_flatten_within_depth():\n"
                "    assert flatten_depth([1, [2, [3]]], 2) == [1, 2, 3]\n"
                "\n"
                "\n"
                "def test_deeper_levels_are_preserved():\n"
                "    assert flatten_depth([1, [2, [3]]], 1) == [1, 2, [3]]\n"
                "\n"
                "\n"
                "def test_zero_depth_is_identity():\n"
                "    assert flatten_depth([1, [2]], 0) == [1, [2]]\n"
                "\n"
                "\n"
                "def test_negative_depth_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        flatten_depth([1], -1)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers exact depth boundaries, identity at zero, and the "
                "validation error."
            ),
        },
    },
    {
        "user": (
            "Module: app/stats/window.py\n"
            "Function: window_max(values: list[int], size: int) -> list[int]\n"
            "Behavior: returns the maximum of each contiguous window of "
            "length size, in order. Returns [] when values is shorter than "
            "size. size must be >= 1, otherwise ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_window_max.py",
            "content": (
                '"""Generated tests for sliding-window maximum."""\n'
                "import pytest\n"
                "\n"
                "from app.stats.window import window_max\n"
                "\n"
                "\n"
                "def test_basic_windows():\n"
                "    assert window_max([1, 3, 2, 5], 2) == [3, 3, 5]\n"
                "\n"
                "\n"
                "def test_size_one_returns_input():\n"
                "    assert window_max([4, 1, 7], 1) == [4, 1, 7]\n"
                "\n"
                "\n"
                "def test_short_input_returns_empty():\n"
                "    assert window_max([1], 2) == []\n"
                "\n"
                "\n"
                "def test_non_positive_size_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        window_max([1, 2], 0)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers window sliding, the size-1 identity, the "
                "short-input empty contract, and validation."
            ),
        },
    },
    {
        "user": (
            "Module: app/utils/chunk.py\n"
            "Function: chunk(items: list, size: int) -> list[list]\n"
            "Behavior: splits items into consecutive lists of at most size "
            "elements; the final chunk may be smaller. size must be >= 1, "
            "otherwise ValueError. An empty list returns []."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_chunk.py",
            "content": (
                '"""Generated tests for list chunking."""\n'
                "import pytest\n"
                "\n"
                "from app.utils.chunk import chunk\n"
                "\n"
                "\n"
                "def test_even_split():\n"
                "    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]\n"
                "\n"
                "\n"
                "def test_uneven_final_chunk():\n"
                "    assert chunk([1, 2, 3], 2) == [[1, 2], [3]]\n"
                "\n"
                "\n"
                "def test_empty_input_returns_empty():\n"
                "    assert chunk([], 3) == []\n"
                "\n"
                "\n"
                "def test_non_positive_size_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        chunk([1], 0)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers even and ragged splits, the empty contract, and "
                "size validation."
            ),
        },
    },
    {
        "user": (
            "Module: app/text/initials.py\n"
            "Function: initials_of(full_name: str) -> str\n"
            "Behavior: returns uppercase initials of each whitespace-"
            "separated word, joined without separators. Extra whitespace "
            "is ignored; an empty or whitespace-only string returns \"\"."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_initials_of.py",
            "content": (
                '"""Generated tests for name initials."""\n'
                "from app.text.initials import initials_of\n"
                "\n"
                "\n"
                "def test_two_word_name():\n"
                "    assert initials_of(\"Ada Lovelace\") == \"AL\"\n"
                "\n"
                "\n"
                "def test_extra_whitespace_is_ignored():\n"
                "    assert initials_of(\"  ada   lovelace \") == \"AL\"\n"
                "\n"
                "\n"
                "def test_lowercase_input_is_uppercased():\n"
                "    assert initials_of(\"grace hopper\") == \"GH\"\n"
                "\n"
                "\n"
                "def test_empty_string_returns_empty():\n"
                "    assert initials_of(\"\") == \"\"\n"
                "    assert initials_of(\"   \") == \"\"\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers joining, whitespace tolerance, case "
                "normalization, and both empty forms."
            ),
        },
    },
    {
        "user": (
            "Module: app/text/ellipsize.py\n"
            "Function: ellipsize_middle(text: str, max_len: int) -> str\n"
            "Behavior: when len(text) <= max_len returns text unchanged; "
            "otherwise keeps the first and last characters around \"...\" "
            "such that the total length is exactly max_len (max_len >= 4, "
            "otherwise ValueError)."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_ellipsize_middle.py",
            "content": (
                '"""Generated tests for middle ellipsis."""\n'
                "import pytest\n"
                "\n"
                "from app.text.ellipsize import ellipsize_middle\n"
                "\n"
                "\n"
                "def test_short_text_unchanged():\n"
                "    assert ellipsize_middle(\"abc\", 5) == \"abc\"\n"
                "\n"
                "\n"
                "def test_exact_length_unchanged():\n"
                "    assert ellipsize_middle(\"abcde\", 5) == \"abcde\"\n"
                "\n"
                "\n"
                "def test_long_text_keeps_edges():\n"
                "    result = ellipsize_middle(\"abcdefgh\", 7)\n"
                "    assert len(result) == 7\n"
                "    assert result.startswith(\"a\")\n"
                "    assert result.endswith(\"h\")\n"
                "    assert \"...\" in result\n"
                "\n"
                "\n"
                "def test_too_small_max_len_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        ellipsize_middle(\"abcdef\", 3)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the unchanged boundary, edge preservation, exact "
                "output length, and the minimum max_len."
            ),
        },
    },
    {
        "user": (
            "Module: app/stats/frequent.py\n"
            "Function: top_frequent(items: list[str], k: int) -> list[str]\n"
            "Behavior: returns the k most frequent items, most frequent "
            "first; ties break alphabetically. Returns fewer items when "
            "there are fewer distinct values. k must be >= 0; a negative k "
            "raises ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_top_frequent.py",
            "content": (
                '"""Generated tests for top-k frequent items."""\n'
                "import pytest\n"
                "\n"
                "from app.stats.frequent import top_frequent\n"
                "\n"
                "\n"
                "def test_orders_by_frequency():\n"
                "    assert top_frequent([\"a\", \"b\", \"a\"], 2) == [\"a\", \"b\"]\n"
                "\n"
                "\n"
                "def test_ties_break_alphabetically():\n"
                "    assert top_frequent([\"b\", \"a\"], 2) == [\"a\", \"b\"]\n"
                "\n"
                "\n"
                "def test_k_larger_than_distinct_returns_all():\n"
                "    assert top_frequent([\"x\"], 5) == [\"x\"]\n"
                "\n"
                "\n"
                "def test_negative_k_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        top_frequent([\"a\"], -1)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers frequency ordering, alphabetical tie-breaking, "
                "oversized k, and validation."
            ),
        },
    },
    {
        "user": (
            "Module: app/math/digital.py\n"
            "Function: digital_root(n: int) -> int\n"
            "Behavior: repeatedly sums the digits of n until a single digit "
            "remains and returns it. n must be >= 0, otherwise ValueError. "
            "A single-digit input returns itself."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_digital_root.py",
            "content": (
                '"""Generated tests for digital root."""\n'
                "import pytest\n"
                "\n"
                "from app.math.digital import digital_root\n"
                "\n"
                "\n"
                "def test_single_digit_is_identity():\n"
                "    assert digital_root(7) == 7\n"
                "\n"
                "\n"
                "def test_multi_step_reduction():\n"
                "    assert digital_root(9875) == 2\n"
                "\n"
                "\n"
                "def test_zero_returns_zero():\n"
                "    assert digital_root(0) == 0\n"
                "\n"
                "\n"
                "def test_negative_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        digital_root(-3)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers the identity, multi-step reduction, the zero "
                "case, and the validation error."
            ),
        },
    },
    {
        "user": (
            "Module: app/net/ip.py\n"
            "Function: is_valid_ipv4(value: str) -> bool\n"
            "Behavior: returns True only for exactly four decimal octets "
            "0-255 separated by dots, with no leading zeros (\"01\" is "
            "invalid). Non-string or malformed input returns False, never "
            "raises."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_is_valid_ipv4.py",
            "content": (
                '"""Generated tests for IPv4 validation."""\n'
                "from app.net.ip import is_valid_ipv4\n"
                "\n"
                "\n"
                "def test_valid_address():\n"
                "    assert is_valid_ipv4(\"192.168.0.1\") is True\n"
                "\n"
                "\n"
                "def test_octet_above_255_is_invalid():\n"
                "    assert is_valid_ipv4(\"256.1.1.1\") is False\n"
                "\n"
                "\n"
                "def test_leading_zero_is_invalid():\n"
                "    assert is_valid_ipv4(\"192.168.01.1\") is False\n"
                "\n"
                "\n"
                "def test_wrong_octet_count_is_invalid():\n"
                "    assert is_valid_ipv4(\"1.2.3\") is False\n"
                "\n"
                "\n"
                "def test_non_digit_octet_is_invalid():\n"
                "    assert is_valid_ipv4(\"1.2.3.a\") is False\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the four-octet range, the no-leading-zero rule, and "
                "fail-closed handling of malformed input."
            ),
        },
    },
    {
        "user": (
            "Module: app/text/rle.py\n"
            "Function: encode_rle(text: str) -> str\n"
            "Behavior: run-length encodes text as character followed by "
            "count, e.g. \"aaabb\" -> \"a3b2\". Counts of 1 are included. "
            "Empty string returns \"\"."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_encode_rle.py",
            "content": (
                '"""Generated tests for run-length encoding."""\n'
                "from app.text.rle import encode_rle\n"
                "\n"
                "\n"
                "def test_basic_encoding():\n"
                "    assert encode_rle(\"aaabb\") == \"a3b2\"\n"
                "\n"
                "\n"
                "def test_single_counts_are_included():\n"
                "    assert encode_rle(\"ab\") == \"a1b1\"\n"
                "\n"
                "\n"
                "def test_single_character():\n"
                "    assert encode_rle(\"z\") == \"z1\"\n"
                "\n"
                "\n"
                "def test_empty_string_returns_empty():\n"
                "    assert encode_rle(\"\") == \"\"\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Pins the always-include-counts rule and the empty "
                "contract."
            ),
        },
    },
    {
        "user": (
            "Module: app/matrix/transpose.py\n"
            "Function: transpose(matrix: list[list[int]]) -> list[list[int]]\n"
            "Behavior: returns the transpose of a rectangular matrix; rows "
            "become columns in order. An empty matrix or a matrix of empty "
            "rows returns []."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_transpose.py",
            "content": (
                '"""Generated tests for matrix transposition."""\n'
                "from app.matrix.transpose import transpose\n"
                "\n"
                "\n"
                "def test_rectangular_transpose():\n"
                "    assert transpose([[1, 2, 3], [4, 5, 6]]) == [\n"
                "        [1, 4],\n"
                "        [2, 5],\n"
                "        [3, 6],\n"
                "    ]\n"
                "\n"
                "\n"
                "def test_single_row_becomes_single_column():\n"
                "    assert transpose([[1, 2]]) == [[1], [2]]\n"
                "\n"
                "\n"
                "def test_empty_matrix_returns_empty():\n"
                "    assert transpose([]) == []\n"
                "\n"
                "\n"
                "def test_empty_rows_return_empty():\n"
                "    assert transpose([[], []]) == []\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers row-column swap, orientation extremes, and both "
                "empty shapes."
            ),
        },
    },
    {
        "user": (
            "Module: app/time/convert.py\n"
            "Function: seconds_to_hms(total_seconds: int) -> str\n"
            "Behavior: converts a non-negative number of seconds to "
            "\"HH:MM:SS\" with zero padding (hours may exceed two digits). "
            "Negative input raises ValueError."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_seconds_to_hms.py",
            "content": (
                '"""Generated tests for seconds to HH:MM:SS."""\n'
                "import pytest\n"
                "\n"
                "from app.time.convert import seconds_to_hms\n"
                "\n"
                "\n"
                "def test_zero_is_midnight():\n"
                "    assert seconds_to_hms(0) == \"00:00:00\"\n"
                "\n"
                "\n"
                "def test_within_one_hour_is_padded():\n"
                "    assert seconds_to_hms(3661) == \"01:01:01\"\n"
                "\n"
                "\n"
                "def test_hours_exceed_two_digits():\n"
                "    assert seconds_to_hms(90061) == \"25:01:01\"\n"
                "\n"
                "\n"
                "def test_negative_raises():\n"
                "    with pytest.raises(ValueError):\n"
                "        seconds_to_hms(-1)\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers zero padding, rollover past 24 hours, and the "
                "negative-input error."
            ),
        },
    },
    {
        "user": (
            "Module: app/stats/cumulative.py\n"
            "Function: cumulative_sums(values: list[int]) -> list[int]\n"
            "Behavior: returns the running totals of values, where element "
            "i is the sum of values[0..i]. An empty list returns []."
        ),
        "assistant": {
            "path": "workflo_generated_tests/test_cumulative_sums.py",
            "content": (
                '"""Generated tests for running totals."""\n'
                "from app.stats.cumulative import cumulative_sums\n"
                "\n"
                "\n"
                "def test_positive_values_accumulate():\n"
                "    assert cumulative_sums([1, 2, 3]) == [1, 3, 6]\n"
                "\n"
                "\n"
                "def test_negatives_are_included():\n"
                "    assert cumulative_sums([5, -2, 1]) == [5, 3, 4]\n"
                "\n"
                "\n"
                "def test_single_element_is_identity():\n"
                "    assert cumulative_sums([9]) == [9]\n"
                "\n"
                "\n"
                "def test_empty_returns_empty():\n"
                "    assert cumulative_sums([]) == []\n"
            ),
            "framework": "pytest",
            "rationale": (
                "Covers accumulation, negative contributions, the "
                "single-element identity, and the empty contract."
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
    {
        "user": (
            "Function under analysis: app.projects.get_project(project_id: "
            "str, tenant_id: str) -> Project | None\n"
            "Projects live in a shared table. Propose the tenant isolation "
            "invariant for project fetches."
        ),
        "assistant": {
            "description": (
                "A project may only be returned when its owning tenant "
                "matches the requesting tenant; cross-tenant ids must "
                "behave exactly like missing projects."
            ),
            "target": "app.projects.get_project",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.tuples(st.text(min_size=1, max_size=16), "
                "st.text(min_size=1, max_size=16))"
            ),
            "property_check": (
                "project is None or project.tenant_id == tenant_id"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.search.page_offset(page: int, "
            "page_size: int) -> int\n"
            "page is 1-based. Propose the invariant linking page, page_size, "
            "and the produced offset."
        ),
        "assistant": {
            "description": (
                "The offset must always be the zero-based start of the "
                "requested page and must never be negative, whatever "
                "page/page_size pair is supplied."
            ),
            "target": "app.search.page_offset",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=1, max_value=10_000), "
                "st.integers(min_value=1, max_value=100))"
            ),
            "property_check": "offset == (page - 1) * page_size and offset >= 0",
        },
    },
    {
        "user": (
            "Function under analysis: app.billing.prorate(amount_cents: "
            "int, days_used: int, days_total: int) -> int\n"
            "Propose the invariant that protects customers from over-"
            "charging during partial-period billing."
        ),
        "assistant": {
            "description": (
                "The prorated amount must never be negative and must never "
                "exceed the full amount, with a zero-length period yielding "
                "zero."
            ),
            "target": "app.billing.prorate",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=10**7), "
                "st.integers(min_value=0, max_value=31), "
                "st.integers(min_value=1, max_value=31))"
            ),
            "property_check": (
                "0 <= prorated <= amount_cents"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.auth.api_keys.is_valid(key: str, "
            "stored_hash: str) -> bool\n"
            "Propose the invariant guaranteeing the validator is a pure "
            "predicate."
        ),
        "assistant": {
            "description": (
                "Validation must be a pure boolean decision: it never "
                "raises for arbitrary string inputs and its result does "
                "not depend on call order or shared state."
            ),
            "target": "app.auth.api_keys.is_valid",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples(st.text(max_size=64), st.text(max_size=64))"
            ),
            "property_check": (
                "isinstance(is_valid(key, stored_hash), bool)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.rate_limit.token_bucket.take"
            "(bucket: TokenBucket, amount: int = 1) -> bool\n"
            "Propose the capacity invariant for the token bucket."
        ),
        "assistant": {
            "description": (
                "A take that succeeds must reduce the token count, and the "
                "token count must never exceed the bucket capacity no "
                "matter how many refill/take pairs are applied."
            ),
            "target": "app.rate_limit.token_bucket.take",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.lists(st.integers(min_value=1, max_value=5), "
                "min_size=1, max_size=20)"
            ),
            "property_check": (
                "0 <= bucket.tokens <= bucket.capacity"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.tenants.delete_workspace"
            "(workspace_id: str, actor_tenant: str) -> int\n"
            "Returns the number of rows deleted. Propose the isolation "
            "invariant for destructive fan-out deletes."
        ),
        "assistant": {
            "description": (
                "A delete issued by one tenant must never remove rows "
                "belonging to another tenant, even when workspace ids "
                "collide across tenants."
            ),
            "target": "app.tenants.delete_workspace",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.tuples(st.text(min_size=1, max_size=12), "
                "st.text(min_size=1, max_size=12))"
            ),
            "property_check": (
                "all(row.tenant_id == actor_tenant for row in deleted_rows)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.money.split_evenly(total_cents: "
            "int, parts: int) -> list[int]\n"
            "Propose the conservation invariant for splitting an amount."
        ),
        "assistant": {
            "description": (
                "The shares must sum to exactly the original total, every "
                "share must be non-negative, and no two shares may differ "
                "by more than one cent."
            ),
            "target": "app.money.split_evenly",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=10**6), "
                "st.integers(min_value=1, max_value=12))"
            ),
            "property_check": (
                "sum(shares) == total_cents and max(shares) - min(shares) <= 1"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.pagination.cursor_roundtrip\n"
            "encode_cursor(position: int) -> str and "
            "decode_cursor(cursor: str) -> int. Propose the round-trip "
            "invariant."
        ),
        "assistant": {
            "description": (
                "Decoding an encoded position must return the original "
                "position for every non-negative integer."
            ),
            "target": "app.pagination.cursor_roundtrip",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.integers(min_value=0, max_value=10**9)"
            ),
            "property_check": (
                "decode_cursor(encode_cursor(position)) == position"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.cache.ttl.get(key: str) -> object "
            "| None\n"
            "Entries expire after their ttl. Propose the expiry invariant."
        ),
        "assistant": {
            "description": (
                "A key whose ttl has elapsed must behave exactly like a "
                "missing key, and a key within its ttl must return the "
                "value that was stored."
            ),
            "target": "app.cache.ttl.get",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.text(min_size=1, max_size=8), "
                "st.integers(min_value=0, max_value=120))"
            ),
            "property_check": (
                "(result is None) == (elapsed >= ttl)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.rbac.bulk_check(roles: "
            "list[str], action: str) -> list[bool]\n"
            "Propose the invariant connecting bulk checks to single checks."
        ),
        "assistant": {
            "description": (
                "Bulk checking a list of roles must return exactly one "
                "boolean per role, in order, equal to checking each role "
                "individually."
            ),
            "target": "app.rbac.bulk_check",
            "category": "auth",
            "hypothesis_strategy": (
                "st.lists(st.sampled_from([\"admin\", \"editor\", \"viewer\", "
                "\"ghost\"]), max_size=10)"
            ),
            "property_check": (
                "len(results) == len(roles)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.audit.redact_pii(record: dict) -> "
            "dict\n"
            "Records may contain email fields at the top level. Propose "
            "the privacy invariant."
        ),
        "assistant": {
            "description": (
                "No top-level field of an exported record may retain a "
                "value shaped like an email address after redaction."
            ),
            "target": "app.audit.redact_pii",
            "category": "tenant_isolation",
            "hypothesis_strategy": (
                "st.dictionaries(st.sampled_from([\"name\", \"email\", "
                "\"note\"]), st.text(max_size=16), max_size=4)"
            ),
            "property_check": (
                "all(\"@\" not in str(v) for k, v in redacted.items() if k == \"email\")"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.orders.total_with_tax(subtotal_"
            "cents: int, tax_bps: int) -> int\n"
            "tax_bps is basis points (0-10000). Propose the monotonicity "
            "invariant."
        ),
        "assistant": {
            "description": (
                "Tax-inclusive totals must be at least the subtotal, never "
                "exceed subtotal plus the full tax rate, and must be "
                "monotonic in the subtotal for a fixed rate."
            ),
            "target": "app.orders.total_with_tax",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=10**7), "
                "st.integers(min_value=0, max_value=10000))"
            ),
            "property_check": (
                "subtotal_cents <= total <= subtotal_cents + (subtotal_cents * tax_bps) // 10000"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.sessions.refresh(session: "
            "Session, now: int) -> Session\n"
            "Propose the invariant for session lifetime extension."
        ),
        "assistant": {
            "description": (
                "Refreshing a live session must strictly extend its expiry "
                "beyond both the old expiry and the refresh time."
            ),
            "target": "app.sessions.refresh",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=2**31), "
                "st.integers(min_value=1, max_value=86400))"
            ),
            "property_check": (
                "refreshed.expires_at > session.expires_at and refreshed.expires_at > now"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.export.export_rows(rows: list, "
            "limit: int) -> list\n"
            "Propose the export bound invariant."
        ),
        "assistant": {
            "description": (
                "Exports must never return more rows than the limit, and "
                "the exported prefix must be identical to the first "
                "limit rows of the input."
            ),
            "target": "app.export.export_rows",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples(st.lists(st.integers(), max_size=50), "
                "st.integers(min_value=0, max_value=50))"
            ),
            "property_check": (
                "len(exported) <= limit and exported == rows[:len(exported)]"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.inventory.reserve(sku: str, "
            "quantity: int) -> bool\n"
            "Available stock must never go negative. Propose the "
            "conservation invariant."
        ),
        "assistant": {
            "description": (
                "A reservation either succeeds and reduces availability by "
                "exactly the requested quantity, or fails and leaves "
                "availability unchanged; availability never becomes "
                "negative."
            ),
            "target": "app.inventory.reserve",
            "category": "business_logic",
            "hypothesis_strategy": (
                "st.tuples(st.text(min_size=1, max_size=6), "
                "st.integers(min_value=1, max_value=50))"
            ),
            "property_check": (
                "availability >= 0 and (granted or availability == before)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.webhooks.verify_timestamp(ts: "
            "int, now: int, tolerance_sec: int = 300) -> bool\n"
            "Propose the freshness invariant for webhook replay defense."
        ),
        "assistant": {
            "description": (
                "Verification must accept exactly those timestamps within "
                "tolerance of now, and reject everything else, "
                "symmetrically on both sides of the window."
            ),
            "target": "app.webhooks.verify_timestamp",
            "category": "auth",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=2**31), "
                "st.integers(min_value=0, max_value=3600))"
            ),
            "property_check": (
                "accepted == (abs(ts - now) <= tolerance_sec)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.search.highlight(text: str, "
            "terms: list[str]) -> str\n"
            "Propose the content-preservation invariant for highlighting."
        ),
        "assistant": {
            "description": (
                "Highlighting must never change the character content of "
                "the text once markup is stripped, and must never invent "
                "occurrences of terms that were absent."
            ),
            "target": "app.search.highlight",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples(st.text(max_size=40), "
                "st.lists(st.text(min_size=1, max_size=4, alphabet=st."
                "characters(min_codepoint=97, max_codepoint=99)), max_size=3))"
            ),
            "property_check": (
                "strip_markup(highlighted) == text"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.users.assert_active(user: User) "
            "-> None\n"
            "Deactivated users must be denied everything. Propose the "
            "deny-by-default invariant."
        ),
        "assistant": {
            "description": (
                "Every action check for a deactivated user must fail, and "
                "deactivation must be sticky: no subsequent operation may "
                "reactivate without an explicit admin action."
            ),
            "target": "app.users.assert_active",
            "category": "auth",
            "hypothesis_strategy": (
                "st.sampled_from([\"read\", \"write\", \"delete\", \"admin\"])"
            ),
            "property_check": (
                "user.active or allowed is False"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.ledger.apply(entry: Entry) -> int\n"
            "Entries are credits or debits. Propose the balance "
            "conservation invariant."
        ),
        "assistant": {
            "description": (
                "After any sequence of applies, the reported balance must "
                "equal the sum of credits minus the sum of debits, with no "
                "entry double-counted or dropped."
            ),
            "target": "app.ledger.apply",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.lists(st.tuples(st.sampled_from([\"credit\", \"debit\"]), "
                "st.integers(min_value=0, max_value=1000)), max_size=20)"
            ),
            "property_check": (
                "balance == sum(c for c in credits) - sum(d for d in debits)"
            ),
        },
    },
    {
        "user": (
            "Function under analysis: app.api.pagination.total_pages"
            "(total_items: int, page_size: int) -> int\n"
            "Propose the pagination invariant including the empty case."
        ),
        "assistant": {
            "description": (
                "Total pages must be exactly ceil(total_items / page_size), "
                "so any non-empty collection yields at least one page and "
                "an empty collection yields exactly one page."
            ),
            "target": "app.api.pagination.total_pages",
            "category": "data_integrity",
            "hypothesis_strategy": (
                "st.tuples(st.integers(min_value=0, max_value=10_000), "
                "st.integers(min_value=1, max_value=100))"
            ),
            "property_check": (
                "total_pages >= 1 and total_pages == (total_items + page_size - 1) // page_size"
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
    {
        "user": (
            '{"run_id": "run-a1f0", "totals": {"passed": 0, "failed": 5, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 22050, '
            '"failures": ['
            '{"test": "test_db_connect", "outcome": "FAILED", "duration_ms": 4400}, '
            '{"test": "test_db_migrate", "outcome": "FAILED", "duration_ms": 4400}, '
            '{"test": "test_db_seed", "outcome": "FAILED", "duration_ms": 4400}, '
            '{"test": "test_db_query", "outcome": "FAILED", "duration_ms": 4400}, '
            '{"test": "test_db_close", "outcome": "FAILED", "duration_ms": 4400}]}'
        ),
        "assistant": {
            "summary": (
                "Every test in the run failed, and all five failures sit "
                "on the database surface with nearly identical durations. "
                "This pattern points to a shared connection or "
                "configuration failure rather than five independent "
                "regressions."
            ),
            "findings": [
                {
                    "root_cause": (
                        "database unavailable or misconfigured for the "
                        "whole suite"
                    ),
                    "affected_tests": [
                        "test_db_connect",
                        "test_db_migrate",
                        "test_db_seed",
                        "test_db_query",
                        "test_db_close",
                    ],
                    "severity": "high",
                    "explanation": (
                        "A total failure with uniform durations on one "
                        "surface indicates the tests never reached the "
                        "code under test; fix the database dependency "
                        "before reading individual failures."
                    ),
                }
            ],
            "priority_order": [
                "database unavailable or misconfigured for the whole suite"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-b2e1", "totals": {"passed": 88, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 30100, '
            '"failures": ['
            '{"test": "test_help_text_mentions_flag", "outcome": "FAILED", '
            '"duration_ms": 210}]}'
        ),
        "assistant": {
            "summary": (
                "88 of 89 tests passed. The single failure checks help "
                "text wording and is cosmetic rather than functional. It "
                "does not block merge but should be reconciled with the "
                "intended copy."
            ),
            "findings": [
                {
                    "root_cause": (
                        "help text no longer mentions the expected flag"
                    ),
                    "affected_tests": ["test_help_text_mentions_flag"],
                    "severity": "low",
                    "explanation": (
                        "Documentation-string drift is the only failure; "
                        "no behavioral test regressed."
                    ),
                }
            ],
            "priority_order": [
                "help text no longer mentions the expected flag"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-c3d2", "totals": {"passed": 31, "failed": 2, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 44800, '
            '"failures": ['
            '{"test": "test_export_row_order", "outcome": "FAILED", '
            '"duration_ms": 3200}, '
            '{"test": "test_export_row_count", "outcome": "FAILED", '
            '"duration_ms": 3150}], '
            '"notes": "both failures reproduce on rerun (2/2)"}'
        ),
        "assistant": {
            "summary": (
                "31 of 33 tests passed. Both failures are on the export "
                "path and reproduce deterministically across reruns, so "
                "this is a real regression in export behavior rather than "
                "flakiness."
            ),
            "findings": [
                {
                    "root_cause": (
                        "export output changed in both ordering and count"
                    ),
                    "affected_tests": [
                        "test_export_row_order",
                        "test_export_row_count",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "Deterministic reproduction across reruns rules "
                        "out environment noise; the export transformation "
                        "likely changed upstream."
                    ),
                }
            ],
            "priority_order": [
                "export output changed in both ordering and count"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-d4c3", "totals": {"passed": 20, "failed": 0, '
            '"error": 0, "timeout": 4, "not_run": 0}, "duration_ms": 241000, '
            '"failures": ['
            '{"test": "test_render_large_document", "outcome": "TIMEOUT", '
            '"duration_ms": 60000}, '
            '{"test": "test_render_large_table", "outcome": "TIMEOUT", '
            '"duration_ms": 60000}, '
            '{"test": "test_render_many_pages", "outcome": "TIMEOUT", '
            '"duration_ms": 60000}, '
            '{"test": "test_render_deep_nesting", "outcome": "TIMEOUT", '
            '"duration_ms": 60000}]}'
        ),
        "assistant": {
            "summary": (
                "20 functional tests passed but all four large-document "
                "render tests hit the 60-second timeout. The renderer "
                "appears to scale poorly with input size rather than "
                "producing wrong output."
            ),
            "findings": [
                {
                    "root_cause": (
                        "renderer does not complete large inputs within "
                        "60 seconds"
                    ),
                    "affected_tests": [
                        "test_render_large_document",
                        "test_render_large_table",
                        "test_render_many_pages",
                        "test_render_deep_nesting",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Uniform 60-second timeouts on every large-input "
                        "case suggest algorithmic scaling trouble, not "
                        "sporadic hangs."
                    ),
                }
            ],
            "priority_order": [
                "renderer does not complete large inputs within 60 seconds"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-e5b4", "totals": {"passed": 44, "failed": 1, '
            '"error": 2, "timeout": 0, "not_run": 0}, "duration_ms": 51200, '
            '"failures": ['
            '{"test": "test_invoice_total_rounding", "outcome": "FAILED", '
            '"duration_ms": 180}, '
            '{"test": "test_tax_engine_loads", "outcome": "ERROR", '
            '"duration_ms": 95}, '
            '{"test": "test_tax_engine_unloads", "outcome": "ERROR", '
            '"duration_ms": 91}]}'
        ),
        "assistant": {
            "summary": (
                "44 of 47 tests passed. Two tax-engine tests errored "
                "around fixture setup while one rounding test failed with "
                "a real assertion mismatch. Treat the errors and the "
                "failure as separate work items."
            ),
            "findings": [
                {
                    "root_cause": (
                        "tax engine fixture fails to initialize"
                    ),
                    "affected_tests": [
                        "test_tax_engine_loads",
                        "test_tax_engine_unloads",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "Errors at near-identical short durations indicate "
                        "a setup problem shared by both tests, not logic "
                        "regressions."
                    ),
                },
                {
                    "root_cause": (
                        "invoice total rounds differently than expected"
                    ),
                    "affected_tests": ["test_invoice_total_rounding"],
                    "severity": "medium",
                    "explanation": (
                        "A genuine assertion failure on rounding "
                        "semantics; verify the intended half-up versus "
                        "banker's rounding contract."
                    ),
                },
            ],
            "priority_order": [
                "tax engine fixture fails to initialize",
                "invoice total rounds differently than expected",
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-f6a5", "totals": {"passed": 0, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 12}, "duration_ms": 300, '
            '"failures": [], '
            '"notes": "selection skipped: marker \'slow\' excluded all tests"}'
        ),
        "assistant": {
            "summary": (
                "No tests ran: all 12 were excluded by the slow marker "
                "selection. The run completed in under a second and "
                "provides no coverage signal either way."
            ),
            "findings": [
                {
                    "root_cause": (
                        "marker selection excluded the entire suite"
                    ),
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": (
                        "An empty run is not a green run; re-run without "
                        "the exclusion or with a broader marker set to "
                        "get real coverage."
                    ),
                }
            ],
            "priority_order": [
                "marker selection excluded the entire suite"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-a7b6", "totals": {"passed": 51, "failed": 2, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 61500, '
            '"failures": ['
            '{"test": "test_admin_delete_other_tenant", "outcome": "FAILED", '
            '"duration_ms": 240}, '
            '{"test": "test_cosmetic_label_typo", "outcome": "FAILED", '
            '"duration_ms": 60}]}'
        ),
        "assistant": {
            "summary": (
                "51 of 53 tests passed. The two failures differ sharply in "
                "importance: one is a cross-tenant delete authorization "
                "gap and the other is a label typo. The tenant issue must "
                "be fixed and verified first."
            ),
            "findings": [
                {
                    "root_cause": (
                        "admin delete succeeds across tenant boundary"
                    ),
                    "affected_tests": ["test_admin_delete_other_tenant"],
                    "severity": "high",
                    "explanation": (
                        "A successful cross-tenant delete is a tenant "
                        "isolation violation with data-loss potential."
                    ),
                },
                {
                    "root_cause": "cosmetic label contains a typo",
                    "affected_tests": ["test_cosmetic_label_typo"],
                    "severity": "low",
                    "explanation": (
                        "String-content drift only; no functional risk."
                    ),
                },
            ],
            "priority_order": [
                "admin delete succeeds across tenant boundary",
                "cosmetic label contains a typo",
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-b8c7", "totals": {"passed": 40, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 12000, '
            '"failures": [], '
            '"notes": "14 deprecation warnings emitted from legacy_client"}'
        ),
        "assistant": {
            "summary": (
                "All 40 tests passed cleanly with no failures or errors. "
                "The only signal is 14 deprecation warnings traced to "
                "legacy_client, which is healthy code with an aging "
                "dependency."
            ),
            "findings": [
                {
                    "root_cause": (
                        "legacy_client emits repeated deprecation warnings"
                    ),
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": (
                        "Warnings do not affect this run but indicate an "
                        "upgrade task; tracking them now avoids a hard "
                        "breakage later."
                    ),
                }
            ],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-c9d8", "totals": {"passed": 1, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 900, '
            '"failures": ['
            '{"test": "test_minimal_probe", "outcome": "FAILED", '
            '"duration_ms": 400}]}'
        ),
        "assistant": {
            "summary": (
                "The smoke probe failed while its single companion passed, "
                "on a very short run. With only two tests executed this "
                "signals a broken environment or an early exit, not a "
                "broad regression."
            ),
            "findings": [
                {
                    "root_cause": (
                        "smoke probe failed in a two-test run"
                    ),
                    "affected_tests": ["test_minimal_probe"],
                    "severity": "medium",
                    "explanation": (
                        "Coverage this thin means the failure is likely "
                        "environmental; re-run the full suite before "
                        "assigning blame to recent changes."
                    ),
                }
            ],
            "priority_order": [
                "smoke probe failed in a two-test run"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-d0e9", "totals": {"passed": 25, "failed": 3, '
            '"error": 0, "timeout": 0, "not_run": 3}, "duration_ms": 38400, '
            '"failures": ['
            '{"test": "test_worker_claim_atomic", "outcome": "FAILED", '
            '"duration_ms": 520}, '
            '{"test": "test_worker_claim_no_double", "outcome": "FAILED", '
            '"duration_ms": 540}, '
            '{"test": "test_worker_release", "outcome": "FAILED", '
            '"duration_ms": 510}], '
            '"notes": "3 not_run: depend on worker claim tests via fixture"}'
        ),
        "assistant": {
            "summary": (
                "25 tests passed while three worker claim-path tests "
                "failed and three more could not run because they depend "
                "on those same claim fixtures. Fixing the claim "
                "regression should unlock the dependent tests too."
            ),
            "findings": [
                {
                    "root_cause": (
                        "worker job claiming is no longer atomic"
                    ),
                    "affected_tests": [
                        "test_worker_claim_atomic",
                        "test_worker_claim_no_double",
                        "test_worker_release",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Atomicity and double-claim guarantees failing "
                        "together indicate the claim transaction changed "
                        "behavior."
                    ),
                }
            ],
            "priority_order": [
                "worker job claiming is no longer atomic"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-e1f0", "totals": {"passed": 33, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 98000, '
            '"failures": [], '
            '"notes": "shard 2 of 3; wall clock up 40 percent vs last run"}'
        ),
        "assistant": {
            "summary": (
                "All 33 tests on this shard passed with no failures. The "
                "only anomaly is wall-clock time up 40 percent against the "
                "previous run, worth watching but not actionable from "
                "outcomes alone."
            ),
            "findings": [
                {
                    "root_cause": (
                        "suite duration increased 40 percent run-over-run"
                    ),
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": (
                        "A passing run with a large duration delta "
                        "suggests resource contention or added work; "
                        "confirm against the next few runs before "
                        "optimizing."
                    ),
                }
            ],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-f2a1", "totals": {"passed": 18, "failed": 2, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 15600, '
            '"failures": ['
            '{"test": "test_login_rejects_bad_password", "outcome": "FAILED", '
            '"duration_ms": 120}, '
            '{"test": "test_login_lockout_after_5", "outcome": "FAILED", '
            '"duration_ms": 130}], '
            '"notes": "security-labeled suite"}'
        ),
        "assistant": {
            "summary": (
                "18 tests passed but two login-security tests failed "
                "together: rejection of a bad password and lockout after "
                "five attempts. Failures in this labeled suite are "
                "release-blocking regardless of count."
            ),
            "findings": [
                {
                    "root_cause": (
                        "login rejection and lockout logic regressed"
                    ),
                    "affected_tests": [
                        "test_login_rejects_bad_password",
                        "test_login_lockout_after_5",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Authentication path accepting what it must "
                        "reject is a direct security regression; both "
                        "failures likely share one root cause in the "
                        "login handler."
                    ),
                }
            ],
            "priority_order": [
                "login rejection and lockout logic regressed"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-a3b2", "totals": {"passed": 60, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 44300, '
            '"failures": ['
            '{"test": "test_webhook_signature_constant_time", "outcome": '
            '"FAILED", "duration_ms": 90}], '
            '"notes": "failure: signature comparison reported as not '
            'constant-time"}'
        ),
        "assistant": {
            "summary": (
                "60 of 61 tests passed. The failure alleges the webhook "
                "signature comparison is not constant-time, which is a "
                "timing-attack surface even though no functional test "
                "regressed."
            ),
            "findings": [
                {
                    "root_cause": (
                        "signature comparison is not constant-time"
                    ),
                    "affected_tests": [
                        "test_webhook_signature_constant_time"
                    ],
                    "severity": "high",
                    "explanation": (
                        "Non-constant-time secret comparison leaks "
                        "timing information; replace with a "
                        "constant-time primitive rather than adjusting "
                        "the test."
                    ),
                }
            ],
            "priority_order": [
                "signature comparison is not constant-time"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-b4c3", "totals": {"passed": 22, "failed": 0, '
            '"error": 1, "timeout": 0, "not_run": 1}, "duration_ms": 7700, '
            '"failures": ['
            '{"test": "test_report_pdf_render", "outcome": "ERROR", '
            '"duration_ms": 210}], '
            '"notes": "error: Required library libpdfgen not found on PATH"}'
        ),
        "assistant": {
            "summary": (
                "22 tests passed; the PDF render test errored at setup "
                "because a system library is missing, and one dependent "
                "test did not run. This is an environment provisioning "
                "gap, not a code regression."
            ),
            "findings": [
                {
                    "root_cause": (
                        "libpdfgen missing from the test environment"
                    ),
                    "affected_tests": ["test_report_pdf_render"],
                    "severity": "medium",
                    "explanation": (
                        "Install the documented system dependency in the "
                        "runner image; the test code itself never "
                        "executed."
                    ),
                }
            ],
            "priority_order": [
                "libpdfgen missing from the test environment"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-c5d4", "totals": {"passed": 30, "failed": 4, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 50200, '
            '"failures": ['
            '{"test": "test_int_overflow_edge", "outcome": "FAILED", '
            '"duration_ms": 70}, '
            '{"test": "test_int_underflow_edge", "outcome": "FAILED", '
            '"duration_ms": 72}, '
            '{"test": "test_str_unicode_edge", "outcome": "FAILED", '
            '"duration_ms": 68}, '
            '{"test": "test_str_empty_edge", "outcome": "FAILED", '
            '"duration_ms": 66}]}'
        ),
        "assistant": {
            "summary": (
                "30 of 34 tests passed. All four failures are boundary-"
                "condition probes spanning integer and string edges, "
                "which suggests input validation was loosened rather "
                "than four unrelated bugs."
            ),
            "findings": [
                {
                    "root_cause": (
                        "input validation no longer rejects boundary "
                        "values"
                    ),
                    "affected_tests": [
                        "test_int_overflow_edge",
                        "test_int_underflow_edge",
                        "test_str_unicode_edge",
                        "test_str_empty_edge",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "Edge probes failing across unrelated types "
                        "points to a shared validation layer change; "
                        "review the latest validator edits first."
                    ),
                }
            ],
            "priority_order": [
                "input validation no longer rejects boundary values"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-d6e5", "totals": {"passed": 27, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 18900, '
            '"failures": ['
            '{"test": "test_concurrent_writes_serialize", "outcome": '
            '"FAILED", "duration_ms": 3200}], '
            '"notes": "reproduces 1/3 attempts"}'
        ),
        "assistant": {
            "summary": (
                "27 of 28 tests passed. The concurrency serialization "
                "test failed once in three attempts, which is "
                "characteristic of a race rather than deterministic "
                "logic breakage."
            ),
            "findings": [
                {
                    "root_cause": (
                        "intermittent race in concurrent write path"
                    ),
                    "affected_tests": [
                        "test_concurrent_writes_serialize"
                    ],
                    "severity": "medium",
                    "explanation": (
                        "Flaky reproduction on a locking test deserves a "
                        "root-cause pass now; races get rarer and harder "
                        "to diagnose over time."
                    ),
                }
            ],
            "priority_order": [
                "intermittent race in concurrent write path"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-e7f6", "totals": {"passed": 41, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 33200, '
            '"failures": [], '
            '"notes": "3 tests passed only on second internal retry"}'
        ),
        "assistant": {
            "summary": (
                "All 41 tests passed, but three needed a second internal "
                "retry to get there. The run is green while hiding "
                "recoverable instability that will resurface as flakes."
            ),
            "findings": [
                {
                    "root_cause": (
                        "three tests pass only after an internal retry"
                    ),
                    "affected_tests": [],
                    "severity": "low",
                    "explanation": (
                        "Retry-masked instability usually indicates "
                        "timing or ordering assumptions; capture the "
                        "retrying test names for a stability pass."
                    ),
                }
            ],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-f8a7", "totals": {"passed": 15, "failed": 2, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 22100, '
            '"failures": ['
            '{"test": "test_balance_after_credit", "outcome": "FAILED", '
            '"duration_ms": 140}, '
            '{"test": "test_balance_after_debit", "outcome": "FAILED", '
            '"duration_ms": 150}]}'
        ),
        "assistant": {
            "summary": (
                "15 of 17 tests passed. Both ledger balance tests failed "
                "in the data-integrity suite, meaning recorded balances "
                "diverge from their expected values after basic "
                "operations."
            ),
            "findings": [
                {
                    "root_cause": (
                        "ledger balance computation diverges after "
                        "credits and debits"
                    ),
                    "affected_tests": [
                        "test_balance_after_credit",
                        "test_balance_after_debit",
                    ],
                    "severity": "high",
                    "explanation": (
                        "Money arithmetic drifting on the two most basic "
                        "ledger operations is a correctness risk for "
                        "every downstream report."
                    ),
                }
            ],
            "priority_order": [
                "ledger balance computation diverges after credits and debits"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-a9b8", "totals": {"passed": 48, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 51000, '
            '"failures": [], '
            '"notes": "teardown warning: temp workspace removed with 2 "'
            'stray files"}'
        ),
        "assistant": {
            "summary": (
                "All 48 tests passed with no failures, errors, or "
                "timeouts. One teardown warning notes two stray files "
                "left in a temp workspace, which is hygiene rather than "
                "correctness."
            ),
            "findings": [
                {
                    "root_cause": (
                        "teardown leaves two stray temp files behind"
                    ),
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": (
                        "Stray artifacts can accumulate across runs and "
                        "eventually interfere with stateful tests; clean "
                        "up the teardown hook when convenient."
                    ),
                }
            ],
            "priority_order": [],
        },
    },
    {
        "user": (
            '{"run_id": "run-b0c9", "totals": {"passed": 36, "failed": 1, '
            '"error": 0, "timeout": 1, "not_run": 0}, "duration_ms": 92500, '
            '"failures": ['
            '{"test": "test_query_timeout_respected", "outcome": "TIMEOUT", '
            '"duration_ms": 30000}, '
            '{"test": "test_slow_query_logs_warning", "outcome": "FAILED", '
            '"duration_ms": 150}]}'
        ),
        "assistant": {
            "summary": (
                "36 of 38 tests passed. The query-path tests failed "
                "around timeout handling: one test itself timed out and "
                "the warning-logging test failed outright, so timeout "
                "enforcement and its observability regressed together."
            ),
            "findings": [
                {
                    "root_cause": (
                        "query timeout enforcement and warning logging "
                        "both broken"
                    ),
                    "affected_tests": [
                        "test_query_timeout_respected",
                        "test_slow_query_logs_warning",
                    ],
                    "severity": "medium",
                    "explanation": (
                        "The enforcement test hanging plus the logging "
                        "test failing suggests the timeout path was "
                        "rewired without updating its logging side "
                        "effects."
                    ),
                }
            ],
            "priority_order": [
                "query timeout enforcement and warning logging both broken"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-c1d0", "totals": {"passed": 29, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 16800, '
            '"failures": ['
            '{"test": "test_redacted_export_contains_no_secrets", '
            '"outcome": "FAILED", "duration_ms": 110}]}'
        ),
        "assistant": {
            "summary": (
                "29 of 30 tests passed. The single failure is the export "
                "redaction guard, meaning exported records may still "
                "contain secret values. This blocks any export feature "
                "release until resolved."
            ),
            "findings": [
                {
                    "root_cause": (
                        "export redaction misses secret values"
                    ),
                    "affected_tests": [
                        "test_redacted_export_contains_no_secrets"
                    ],
                    "severity": "high",
                    "explanation": (
                        "Redaction failing its dedicated guard test "
                        "means real payloads may leak; treat as a "
                        "privacy incident risk, not a normal bug."
                    ),
                }
            ],
            "priority_order": [
                "export redaction misses secret values"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-d2e1", "totals": {"passed": 52, "failed": 1, '
            '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 47600, '
            '"failures": ['
            '{"test": "test_pagination_last_page_empty", "outcome": '
            '"FAILED", "duration_ms": 130}], '
            '"notes": "introduced with new cursor pagination rollout"}'
        ),
        "assistant": {
            "summary": (
                "52 of 53 tests passed. The last-page boundary test "
                "failed and the run notes tie it to the new cursor "
                "pagination rollout, so this is a fresh regression with "
                "a known blast radius."
            ),
            "findings": [
                {
                    "root_cause": (
                        "cursor pagination returns a row on the page "
                        "after the end"
                    ),
                    "affected_tests": ["test_pagination_last_page_empty"],
                    "severity": "medium",
                    "explanation": (
                        "Off-by-one at the final cursor boundary matches "
                        "the rollout notes; verify the cursor advance "
                        "logic against the documented boundary."
                    ),
                }
            ],
            "priority_order": [
                "cursor pagination returns a row on the page after the end"
            ],
        },
    },
    {
        "user": (
            '{"run_id": "run-e3f2", "totals": {"passed": 21, "failed": 0, '
            '"error": 0, "timeout": 0, "not_run": 6}, "duration_ms": 6400, '
            '"failures": [], '
            '"notes": "6 not_run: upstream suite aborted before these '
            'shards were scheduled"}'
        ),
        "assistant": {
            "summary": (
                "All 21 scheduled tests passed. Six shards never ran "
                "because an upstream suite aborted first, so coverage is "
                "incomplete and this green result must not be read as a "
                "full-suite pass."
            ),
            "findings": [
                {
                    "root_cause": (
                        "upstream abort left six shards unscheduled"
                    ),
                    "affected_tests": [],
                    "severity": "medium",
                    "explanation": (
                        "Partial coverage from an upstream failure needs "
                        "a follow-up run; the passing shard says nothing "
                        "about the missing ones."
                    ),
                }
            ],
            "priority_order": [
                "upstream abort left six shards unscheduled"
            ],
        },
    },
]
