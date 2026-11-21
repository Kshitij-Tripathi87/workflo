"""Tests for the authenticated Workflo voice-command and provider endpoints."""

from fastapi.testclient import TestClient


def create_key(client: TestClient, scopes: list[str]) -> dict[str, str]:
    response = client.post(
        "/v1/keys",
        json={"label": "voice-agent-test", "scopes": scopes},
    )
    assert response.status_code == 200, response.text
    return {"X-TenantShield-Key": response.json()["raw_key"]}


def test_voice_provider_catalog_requires_auth(client):
    response = client.get("/v1/voice/providers")
    assert response.status_code == 401


def test_voice_provider_catalog_reports_readiness_without_disclosing_keys(client, monkeypatch):
    from app.core.config import settings

    secret = "sarvam-test-key-never-return-this"
    monkeypatch.setattr(settings, "sarvam_api_key", secret)
    headers = create_key(client, ["run_tests"])

    response = client.get("/v1/voice/providers", headers=headers)
    assert response.status_code == 200, response.text
    assert secret not in response.text

    providers = {item["provider"]: item for item in response.json()["providers"]}
    assert providers["sarvam"]["configured"] is True
    assert providers["sarvam"]["speech_to_text"] is True
    assert providers["sarvam"]["text_to_speech"] is True
    assert providers["sarvam"]["key_source"] == "server"
    assert providers["fish"]["configured"] is False
    assert providers["elevenlabs"]["configured"] is False


def test_voice_command_resolver_creates_preview_from_text_or_transcript(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={
            "command": "Run QA including security checks",
            "repo_url": "https://github.com/acme/service.git",
            "commit_sha": "a" * 40,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ready"
    assert data["run_request"]["repo_url"] == "https://github.com/acme/service.git"
    assert data["run_request"]["commit_sha"] == "a" * 40
    assert data["run_request"]["probe_groups"] == ["test", "security"]
    assert "Nothing has been submitted" in data["message"]


def test_voice_command_resolver_asks_for_repository_and_pinned_commit(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={"command": "Run QA on my latest branch"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "needs_clarification"
    assert data["run_request"] is None
    assert any("repository" in item.lower() for item in data["clarifications"])
    assert any("commit" in item.lower() for item in data["clarifications"])


def test_voice_command_resolver_rejects_unapproved_url_shapes(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={
            "command": "Run QA",
            "repo_url": "http://localhost/private.git",
            "commit_sha": "b" * 40,
        },
    )
    assert response.status_code == 422


def test_voice_command_resolver_rejects_unknown_profile(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={
            "command": "Run QA",
            "repo_url": "https://github.com/acme/service.git",
            "commit_sha": "c" * 40,
            "probe_groups": ["test", "arbitrary-command"],
        },
    )
    assert response.status_code == 422


def test_voice_command_resolver_requires_web_start_command_and_port(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={
            "command": "Run browser QA",
            "repo_url": "https://github.com/acme/service.git",
            "commit_sha": "d" * 40,
            "probe_groups": ["web"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "needs_clarification"
    assert any("start command" in item.lower() for item in data["clarifications"])
    assert any("port" in item.lower() for item in data["clarifications"])


def test_voice_command_resolver_does_not_turn_general_chat_into_a_run(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={"command": "Hello, can you explain what you do?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["run_request"] is None


def test_voice_transcription_requires_authentication(client):
    response = client.post(
        "/v1/voice/transcribe",
        data={"provider": "sarvam", "language_code": "unknown"},
        files={"audio": ("sample.wav", b"fake-audio", "audio/wav")},
    )
    assert response.status_code == 401


def test_voice_provider_key_management_requires_admin_scope(client):
    headers = create_key(client, ["run_tests"])
    response = client.put(
        "/v1/voice/providers/sarvam",
        headers=headers,
        json={"api_key": "a-sample-provider-api-key"},
    )
    assert response.status_code == 403


def test_project_voice_credentials_are_excluded_from_org_export_config():
    from app.api.v1.orgs import _exportable_project_config

    secret_config = {
        "environment": "production",
        "_voice_provider_credentials": {
            "sarvam": {"api_key": "wfenc1:v1:encrypted-ciphertext"},
            "elevenlabs": {"api_key": "wfenc1:v1:another-ciphertext"},
        },
    }
    exported = _exportable_project_config(secret_config)
    assert exported == {"environment": "production"}
    assert "wfenc1" not in str(exported)


def test_project_voice_key_storage_fails_closed_without_a_kek(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "master_kek_hex", "")
    headers = create_key(client, ["admin"])
    response = client.put(
        "/v1/voice/providers/sarvam",
        headers=headers,
        json={"api_key": "a-sample-provider-api-key"},
    )
    assert response.status_code == 503
    assert "MASTER_KEK_HEX" in response.json()["detail"]


def test_voice_command_merges_spoken_profiles_with_ui_selection(client):
    headers = create_key(client, ["run_tests"])
    response = client.post(
        "/v1/voice/resolve",
        headers=headers,
        json={
            "command": "Run QA including security and browser checks",
            "repo_url": "https://github.com/acme/service.git",
            "commit_sha": "e" * 40,
            "probe_groups": ["test"],
            "start_command": "npm run start",
            "port": 3000,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ready"
    assert data["run_request"]["probe_groups"] == ["test", "security", "web"]
