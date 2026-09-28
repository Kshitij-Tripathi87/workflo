"""Mission state — deterministic observation folding and prompt rendering."""

from __future__ import annotations

from sandbox_runtime.mission import MissionState, recent_observations_block


def _obs(description, detail, ok=True, tool="http_get", denied=False):
    return {
        "description": description,
        "detail": detail,
        "ok": ok,
        "tool": tool,
        "denied": denied,
    }


def test_builds_endpoint_map_from_observations():
    obs = [
        _obs("GET /", "HTTP 200"),
        _obs("GET /health", "HTTP 200"),
        _obs("POST /checkout", "HTTP 500", ok=False, tool="http_post"),
    ]
    state = MissionState.from_observations(obs, mission="Test checkout")
    assert state.endpoints["GET /"] == "HTTP 200"
    assert state.endpoints["POST /checkout"] == "HTTP 500"
    assert state.observations_total == 3


def test_failures_collected_once():
    obs = [
        _obs("POST /checkout", "HTTP 500", ok=False, tool="http_post"),
        _obs("POST /checkout", "HTTP 500", ok=False, tool="http_post"),
    ]
    state = MissionState.from_observations(obs)
    assert state.failures == ["POST /checkout: HTTP 500"]


def test_denied_attempts_are_visible_failures():
    obs = [_obs("GET http://evil.example/x", "denied: host not allowed",
                ok=False, denied=True)]
    state = MissionState.from_observations(obs)
    assert any("denied" in f for f in state.failures)


def test_prompt_block_is_bounded_and_structured():
    obs = [
        _obs(f"GET /r{i}", "HTTP 200") for i in range(60)
    ] + [_obs("POST /checkout", "HTTP 500", ok=False, tool="http_post")]
    state = MissionState.from_observations(obs, mission="m", tool_calls=61,
                                           denied_attempts=2)
    block = state.prompt_block()
    assert "mission: m" in block
    assert "observations: 61 total, 61 tool calls, 2 denied" in block
    assert "endpoints:" in block
    assert "open failures:" in block
    # Bounded regardless of observation volume
    assert len(block.splitlines()) <= 45


def test_recent_observations_caps_tail():
    obs = [{"n": i} for i in range(100)]
    tail = recent_observations_block(obs, keep=20)
    assert len(tail) == 20
    assert tail[-1]["n"] == 99


def test_empty_observations_render_cleanly():
    state = MissionState.from_observations([])
    block = state.prompt_block()
    assert "observations: 0 total" in block
    assert "endpoints:" not in block
