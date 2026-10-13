"""HTTP service tests against a deterministic fake router (no GPU, no llama-server)."""

import pytest
from fastapi.testclient import TestClient
from workflo_ai_integration.artifact_registry import ArtifactRegistry
from workflo_ai_integration.model_router import (
    AdapterLoadError,
    GenerationValidationError,
)
from workflo_ai_integration.schemas import ProposeInvariantCall, WriteTestCall
from workflo_ai_integration.service import create_app

from serving_fakes import FakeRouter, build_fake_registry


@pytest.fixture()
def client() -> TestClient:
    app = create_app(router=FakeRouter(), registry=build_fake_registry())
    return TestClient(app, raise_server_exceptions=False)


def test_health_ok_reports_adapter_ids_and_artifacts(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["adapter_ids"] == {"reporting": 2, "reasoning": 1, "test-gen": 0}
    assert body["artifacts"]["model"]["sha256"].startswith("594bc37d") or len(
        body["artifacts"]["model"]["sha256"]
    ) == 64
    assert set(body["artifacts"]["adapters"]) == {"test-gen", "reasoning", "reporting"}


def test_test_gen_happy_path_returns_validated_result_and_artifacts(client):
    resp = client.post(
        "/v1/test_gen",
        json={"user_prompt": "Module: app/x.py\nFunction: f() -> int\nBehavior: returns 1."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task"] == "test-gen"
    assert body["result"]["framework"] == "pytest"
    assert body["result"]["path"].startswith("workflo_generated_tests/")
    assert isinstance(body["latency_ms"], int)
    assert body["artifacts"]["llama_cpp_image"].startswith("ghcr.io/")
    # telemetry identities must be present on every response
    assert "sha256" in body["artifacts"]["adapters"]["test-gen"]


def test_default_system_prompts_are_serving_owned(client):
    """When system_prompt is omitted, the service injects the serving default
    (byte-identical to the training prompt — enforced elsewhere)."""
    seen = {}

    class PromptCapture(FakeRouter):
        def generate_for_task(self, task, system_prompt, user_prompt):
            seen["system"] = system_prompt
            return super().generate_for_task(task, system_prompt, user_prompt)

    from workflo_ai_integration.service import create_app as build

    c = TestClient(build(router=PromptCapture(), registry=build_fake_registry()))
    resp = c.post("/v1/test_gen", json={"user_prompt": "Function: f()\nBehavior: x"})
    assert resp.status_code == 200
    assert "WriteTestCall schema" in seen["system"]


def test_reasoning_rejects_unsafe_property_expression(client):
    class UnsafeRouter(FakeRouter):
        def generate_for_task(self, task, system_prompt, user_prompt):
            raise GenerationValidationError(
                "compile-check failed: disallowed import in generated test: socket"
            )

    app = create_app(router=UnsafeRouter(), registry=build_fake_registry())
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post(
        "/v1/reasoning",
        json={"user_prompt": "Function: f()\nPropose an invariant."},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "generation_validation_failed"


def test_adapter_load_failure_maps_to_503():
    class BrokenRouter(FakeRouter):
        def generate_for_task(self, task, system_prompt, user_prompt):
            raise AdapterLoadError("llama.cpp must expose exactly the three frozen adapters")

        def discover_adapters(self, force=False):
            raise AdapterLoadError("failed to list llama.cpp adapters")

    app = create_app(router=BrokenRouter(), registry=build_fake_registry())
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post("/v1/test_gen", json={"user_prompt": "x"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "adapter_load_failed"
    health = c.get("/v1/health")
    assert health.status_code == 503
    assert health.json()["status"] == "degraded"


def test_reporting_only_takes_structured_results(client):
    resp = client.post(
        "/v1/reporting",
        json={"results": {"passed": 97, "failed": 3, "failing_tests": ["test_billing_x"]}},
    )
    assert resp.status_code == 200
    assert resp.json()["task"] == "reporting"
    assert "summary" in resp.json()["result"]


def test_reporting_rejects_oversized_results(client):
    resp = client.post(
        "/v1/reporting",
        json={"results": {"blob": "x" * 300_000}},
    )
    assert resp.status_code == 413


def test_prompt_size_ceilings(client):
    resp = client.post("/v1/test_gen", json={"user_prompt": "x" * 40_000})
    assert resp.status_code == 422  # pydantic max_length
    resp = client.post("/v1/test_gen", json={"user_prompt": "   \n  "})
    assert resp.status_code == 422


def test_unknown_task_is_not_exposable(client):
    """There is no route for an unmapped task; hitting an unknown path 404s."""
    resp = client.post("/v1/unknown", json={"user_prompt": "x"})
    assert resp.status_code == 404


def test_production_create_app_without_injection_verifies_real_manifest():
    """Default construction path must verify the real on-disk manifest.
    In CI (no GGUFs committed) this must fail closed rather than start."""
    try:
        ArtifactRegistry()  # probe: does the local artifact set exist?
    except Exception:
        with pytest.raises(Exception):
            create_app()
        return
    app = create_app()
    assert app.state.registry.snapshot.model_id
