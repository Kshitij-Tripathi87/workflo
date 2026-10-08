"""
Tests the routing/validation logic against a mocked llama-server.

Deliberately does not require a GPU or a real model — these prove the
plumbing (flag -> adapter discovery -> lora field -> validated output) is
correct. Model quality is evaluated separately against held-out sets once
real GGUF adapters exist.
"""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from model_router import (  # noqa: E402
    ADAPTER_REGISTRY,
    AdapterLoadError,
    FLAG_TASK_MAP,
    GenerationValidationError,
    ModelRouter,
    RouterConfig,
)


DEFAULT_ADAPTERS = [
    {"id": 0, "path": "/adapters/test-gen.gguf", "scale": 0.0},
    {"id": 1, "path": "/adapters/reasoning.gguf", "scale": 0.0},
    {"id": 2, "path": "/adapters/reporting.gguf", "scale": 0.0},
]


def make_router(handler) -> ModelRouter:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://fake-llama")
    return ModelRouter(config=RouterConfig(base_url="http://fake-llama"), client=client)


def _write_test_payload(**overrides):
    base = {
        "path": "tests/test_pagination_edge.py",
        "content": "def test_pagination_zero_limit():\n    assert True\n",
        "framework": "pytest",
        "rationale": "pagination limit=0 is an untested boundary",
    }
    base.update(overrides)
    return json.dumps(base)


def _invariant_payload(**overrides):
    base = {
        "description": "tenant B cannot read tenant A's project data",
        "target": "GET /api/projects/{id}",
        "category": "tenant_isolation",
        "hypothesis_strategy": "st.integers(min_value=1)",
        "property_check": "response.tenant_id == requesting_tenant_id",
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Flag -> task mapping
# ---------------------------------------------------------------------------

def test_flag_task_mapping_is_explicit():
    assert FLAG_TASK_MAP["--deep-test"] == "test-gen"
    assert FLAG_TASK_MAP["--security"] == "reasoning"
    assert FLAG_TASK_MAP["--aggressive-test"] == "reasoning"


def test_unmapped_flag_raises():
    router = make_router(lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="no adapter mapping"):
        router.task_for_flag("--web")


def test_legacy_vllm_base_url_alias_still_works():
    cfg = RouterConfig(vllm_base_url="http://legacy:8000")
    assert cfg.base_url == "http://legacy:8000"


# ---------------------------------------------------------------------------
# Adapter discovery (defensive — match by filename substring, not hardcoded id)
# ---------------------------------------------------------------------------

def test_discover_adapters_matches_by_filename_substring():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        return httpx.Response(404)

    router = make_router(handler)
    ids = router.discover_adapters()
    assert ids["test-gen"] == 0
    assert ids["reasoning"] == 1
    assert ids["reporting"] == 2


def test_discover_adapters_survives_reordered_listing():
    """IDs are not assumed stable — a reordered /lora-adapters response must
    still map each task to the adapter whose path contains the match string."""
    reordered = [
        {"id": 7, "path": "/models/reporting-v2.gguf", "scale": 0.0},
        {"id": 3, "path": "/models/test-gen-rank16.gguf", "scale": 0.0},
        {"id": 9, "path": "/models/reasoning-sec.gguf", "scale": 0.0},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=reordered)
        return httpx.Response(404)

    router = make_router(handler)
    ids = router.discover_adapters()
    assert ids == {"test-gen": 3, "reasoning": 9, "reporting": 7}


def test_discover_adapters_caches_until_forced():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            calls["n"] += 1
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        return httpx.Response(404)

    router = make_router(handler)
    router.discover_adapters()
    router.discover_adapters()
    assert calls["n"] == 1
    router.discover_adapters(force=True)
    assert calls["n"] == 2


def test_discover_adapters_missing_match_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=[
                {"id": 0, "path": "/adapters/only-test-gen.gguf", "scale": 0.0},
            ])
        return httpx.Response(404)

    router = make_router(handler)
    with pytest.raises(AdapterLoadError, match="no LoRA adapter matching"):
        router.discover_adapters()


def test_ensure_adapter_loaded_is_compat_alias():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        return httpx.Response(404)

    router = make_router(handler)
    router.ensure_adapter_loaded("test-gen")  # must not raise


# ---------------------------------------------------------------------------
# End-to-end generation + validation
# ---------------------------------------------------------------------------

def test_generate_for_flag_deep_test_valid_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            body = json.loads(request.content)
            seen["lora"] = body["lora"]
            seen["json_schema"] = body.get("json_schema")
            seen["prompt"] = body["prompt"]
            return httpx.Response(200, json={"content": _write_test_payload()})
        return httpx.Response(404)

    router = make_router(handler)
    result = router.generate_for_flag("--deep-test", "system", "generate an edge case test")
    assert result.path == "tests/test_pagination_edge.py"
    assert "def test_pagination_zero_limit" in result.content
    # Exactly one adapter activated, at the discovered id for test-gen.
    assert seen["lora"] == [{"id": 0, "scale": 1.0}]
    assert seen["json_schema"] is not None
    assert "path" in seen["json_schema"].get("properties", {})
    # ChatML placeholder wraps the turns.
    assert "<|im_start|>system" in seen["prompt"]
    assert "<|im_start|>user" in seen["prompt"]
    assert seen["prompt"].endswith("<|im_start|>assistant\n")


def test_generate_sends_json_schema_even_though_pydantic_is_load_bearing():
    """Sampler constraint is present; Pydantic still validates (see #19051)."""
    schemas_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            body = json.loads(request.content)
            schemas_seen.append(body["json_schema"])
            # Deliberately return schema-violating content — sampler "failed"
            # open (simulating #19051). Pydantic must still reject.
            return httpx.Response(200, json={"content": json.dumps({"not": "a WriteTestCall"})})
        return httpx.Response(404)

    router = make_router(handler)
    with pytest.raises(GenerationValidationError, match="schema validation failed"):
        router.generate_for_flag("--deep-test", "system", "generate a test")
    assert schemas_seen, "json_schema must be sent to the sampler"


def test_generate_for_flag_rejects_path_outside_sandbox():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            return httpx.Response(200, json={"content": _write_test_payload(
                path="/etc/test_malicious.py",
                content="def test_x():\n    assert True\n",
                rationale="x",
            )})
        return httpx.Response(404)

    router = make_router(handler)
    with pytest.raises(GenerationValidationError, match="schema validation failed"):
        router.generate_for_flag("--deep-test", "system", "generate a test")


def test_generate_for_flag_rejects_disallowed_import():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            return httpx.Response(200, json={"content": _write_test_payload(
                path="test_exfil.py",
                content="import socket\ndef test_x():\n    assert True\n",
                rationale="x",
            )})
        return httpx.Response(404)

    router = make_router(handler)
    with pytest.raises(GenerationValidationError, match="compile-check failed"):
        router.generate_for_flag("--deep-test", "system", "generate a test")


def test_generate_for_flag_security_maps_to_reasoning_adapter():
    seen_lora = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            body = json.loads(request.content)
            seen_lora.append(body["lora"])
            return httpx.Response(200, json={"content": _invariant_payload()})
        return httpx.Response(404)

    router = make_router(handler)
    result = router.generate_for_flag("--security", "system", "propose an isolation probe")
    assert result.category == "tenant_isolation"
    assert seen_lora == [[{"id": 1, "scale": 1.0}]]  # reasoning id under DEFAULT_ADAPTERS


def test_generate_for_flag_rejects_malformed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            return httpx.Response(200, json={"content": "not json at all"})
        return httpx.Response(404)

    router = make_router(handler)
    with pytest.raises(GenerationValidationError, match="did not return valid JSON"):
        router.generate_for_flag("--deep-test", "system", "generate a test")


def test_generate_report_uses_reporting_adapter_and_only_structured_input():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=DEFAULT_ADAPTERS)
        if request.url.path == "/completion":
            body = json.loads(request.content)
            assert body["lora"] == [{"id": 2, "scale": 1.0}]
            # confirm no source-code-shaped content leaked into the prompt
            assert "def " not in body["prompt"]
            content = json.dumps({
                "summary": "3 tests failed, all in the billing module.",
                "findings": [],
                "priority_order": [],
            })
            return httpx.Response(200, json={"content": content})
        return httpx.Response(404)

    router = make_router(handler)
    report = router.generate_report({"passed": 97, "failed": 3, "failing_tests": ["test_billing_x"]})
    assert "billing" in report.summary


def test_lora_activation_uses_discovered_id_not_registry_order():
    """Even if reporting is listed first on the server, activating the
    reporting task must use that entry's id — not assume id==2."""
    reordered = [
        {"id": 5, "path": "/a/reporting.gguf", "scale": 0.0},
        {"id": 1, "path": "/a/test-gen.gguf", "scale": 0.0},
        {"id": 8, "path": "/a/reasoning.gguf", "scale": 0.0},
    ]
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lora-adapters":
            return httpx.Response(200, json=reordered)
        if request.url.path == "/completion":
            body = json.loads(request.content)
            seen["lora"] = body["lora"]
            content = json.dumps({
                "summary": "ok",
                "findings": [],
                "priority_order": [],
            })
            return httpx.Response(200, json={"content": content})
        return httpx.Response(404)

    router = make_router(handler)
    router.generate_report({"passed": 1, "failed": 0})
    assert seen["lora"] == [{"id": 5, "scale": 1.0}]


def test_adapter_registry_path_hints_are_gguf():
    """PEFT/Unsloth adapters need a GGUF conversion step before llama-server
    can load them — registry hints must point at .gguf paths, not PEFT dirs."""
    for meta in ADAPTER_REGISTRY.values():
        assert meta["path_hint"].endswith(".gguf")
