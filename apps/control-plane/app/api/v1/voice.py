"""Provider-routed voice endpoints for Workflo's dashboard QA assistant.

Speech providers provide transcription/synthesis only. Workflo owns command
resolution, authorization, QA admission, execution and result interpretation.
"""
from __future__ import annotations

import base64
import re
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import envelope
from app.core.config import settings
from app.core.security import require_scope
from app.db.database import get_db
from app.db.models import ApiKey, Project
from app.services.audit_service import record_event

router = APIRouter(prefix="/voice", tags=["voice"])

VoiceProvider = Literal["sarvam", "fish", "elevenlabs"]
_ENV_KEY_FIELDS = {
    "sarvam": "sarvam_api_key",
    "fish": "fish_api_key",
    "elevenlabs": "elevenlabs_api_key",
}
_ALLOWED_PROFILES = {"test", "security", "deep-test", "aggressive-test", "web"}
_FUNCTIONAL_PROFILES = {"test", "deep-test", "aggressive-test", "web"}
_FULL_SHA = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_SHA_IN_TEXT = re.compile(r"\b(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\b")
_HTTPS_URL_IN_TEXT = re.compile(r"https://[^\s<>\"']+", re.IGNORECASE)
_MAX_AUDIO_BYTES = 10 * 1024 * 1024
_MAX_COMMAND_CHARS = 2000
_MAX_SPEECH_CHARS = 1800


class ProviderCredentialUpdate(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    speaker: str | None = Field(default=None, max_length=100)
    reference_id: str | None = Field(default=None, max_length=200)
    voice_id: str | None = Field(default=None, max_length=200)


class VoiceResolveRequest(BaseModel):
    command: str = Field(min_length=1, max_length=_MAX_COMMAND_CHARS)
    repo_url: str | None = Field(default=None, max_length=2048)
    commit_sha: str | None = Field(default=None, max_length=64)
    probe_groups: list[str] | None = None
    start_command: str | None = Field(default=None, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65535)


class VoiceSpeechRequest(BaseModel):
    provider: VoiceProvider
    text: str = Field(min_length=1, max_length=_MAX_SPEECH_CHARS)
    language_code: str = Field(default="en-IN", max_length=12)


async def _get_project(db: AsyncSession, api_key: ApiKey) -> Project:
    project = await db.get(Project, api_key.project_id)
    if project is None:
        raise HTTPException(status_code=401, detail="Project credentials are no longer valid.")
    return project


async def _provider_config(
    db: AsyncSession, api_key: ApiKey, provider: str
) -> tuple[str, dict, Project]:
    project = await _get_project(db, api_key)
    config = project.config_json if isinstance(project.config_json, dict) else {}
    credential_map = config.get("_voice_provider_credentials", {})
    entry = credential_map.get(provider, {}) if isinstance(credential_map, dict) else {}
    key = ""

    if isinstance(entry, dict) and entry.get("api_key"):
        try:
            key = await envelope.reveal_for_project(
                db, project.id, str(entry["api_key"])
            )
        except Exception as exc:  # noqa: BLE001 - don't expose crypto internals
            raise HTTPException(
                status_code=503,
                detail="Stored voice credentials could not be decrypted. Check the project's encryption-key configuration.",
            ) from exc

    if not key:
        key = str(getattr(settings, _ENV_KEY_FIELDS[provider], "") or "").strip()

    return key, entry if isinstance(entry, dict) else {}, project


def _provider_status(provider: str, key: str, entry: dict) -> dict:
    configured = bool(key)
    key_source = (
        "project" if entry.get("api_key")
        else "server" if configured
        else None
    )
    if provider == "sarvam":
        tts_ready = configured
    elif provider == "fish":
        tts_ready = configured and bool(
            entry.get("reference_id") or settings.fish_tts_reference_id
        )
    else:
        voice_id = entry.get("voice_id") or settings.elevenlabs_voice_id
        tts_ready = configured and bool(voice_id)

    return {
        "provider": provider,
        "configured": configured,
        "speech_to_text": configured,
        "text_to_speech": tts_ready,
        "key_source": key_source,
        "voice_configured": tts_ready,
    }


@router.get("/providers")
async def list_voice_providers(
    api_key: ApiKey = Depends(require_scope("run_tests")),
    db: AsyncSession = Depends(get_db),
):
    """Return readiness metadata only. Never return plaintext or ciphertext keys."""
    statuses = []
    for provider in ("sarvam", "fish", "elevenlabs"):
        key, entry, _ = await _provider_config(db, api_key, provider)
        statuses.append(_provider_status(provider, key, entry))
    return {"providers": statuses}


@router.put("/providers/{provider}")
async def configure_voice_provider(
    provider: VoiceProvider,
    body: ProviderCredentialUpdate,
    api_key: ApiKey = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Save a project BYOK key encrypted under the project's organization DEK."""
    project = await _get_project(db, api_key)
    if not project.org_id:
        raise HTTPException(
            status_code=409,
            detail="This project is not linked to an organization; project-level voice keys cannot be stored.",
        )
    if not envelope.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Encrypted provider-key storage is unavailable. Configure MASTER_KEK_HEX or a KMS-backed KEK provider first.",
        )

    voice_warning = None
    if provider == "fish" and not (
        body.reference_id or settings.fish_tts_reference_id
    ):
        voice_warning = "Fish speech recognition is configured. Add a Fish voice reference ID to enable speech output."
    elif provider == "elevenlabs" and not (
        body.voice_id or settings.elevenlabs_voice_id
    ):
        voice_warning = "ElevenLabs speech recognition is configured. Add a voice ID to enable speech output."

    try:
        encrypted_key = await envelope.protect_for_project(
            db, project.id, body.api_key.strip()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="The provider key could not be encrypted.",
        ) from exc

    config = dict(project.config_json or {})
    credential_map = dict(config.get("_voice_provider_credentials") or {})
    entry = dict(credential_map.get(provider) or {})
    entry["api_key"] = encrypted_key
    for field in ("speaker", "reference_id", "voice_id"):
        value = getattr(body, field)
        if value:
            entry[field] = value.strip()
    credential_map[provider] = entry
    config["_voice_provider_credentials"] = credential_map
    project.config_json = config
    await db.commit()

    await record_event(
        action="voice.provider.configure",
        outcome="success",
        actor_type="api_key",
        actor_id=api_key.id,
        project_id=api_key.project_id,
        resource_type="voice_provider",
        resource_id=provider,
        detail={"provider": provider, "key_rotated": True},
    )
    return {
        "provider": provider,
        "configured": True,
        "warning": voice_warning,
    }


@router.delete("/providers/{provider}")
async def remove_voice_provider(
    provider: VoiceProvider,
    api_key: ApiKey = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete the project BYOK credential; an operator-managed env key may remain."""
    project = await _get_project(db, api_key)
    config = dict(project.config_json or {})
    credential_map = dict(config.get("_voice_provider_credentials") or {})
    credential_map.pop(provider, None)
    config["_voice_provider_credentials"] = credential_map
    project.config_json = config
    await db.commit()

    await record_event(
        action="voice.provider.remove",
        outcome="success",
        actor_type="api_key",
        actor_id=api_key.id,
        project_id=api_key.project_id,
        resource_type="voice_provider",
        resource_id=provider,
        detail={"provider": provider},
    )
    return {
        "provider": provider,
        "removed": True,
        "server_key_available": bool(
            str(getattr(settings, _ENV_KEY_FIELDS[provider], "") or "").strip()
        ),
    }


@router.post("/transcribe")
async def transcribe_audio(
    provider: VoiceProvider = Form(...),
    audio: UploadFile = File(...),
    language_code: str = Form("unknown"),
    api_key: ApiKey = Depends(require_scope("run_tests")),
    db: AsyncSession = Depends(get_db),
):
    """Transcribe a short browser recording. Provider keys remain server-side."""
    payload = await audio.read(_MAX_AUDIO_BYTES + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    if len(payload) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The recording exceeds the 10 MB limit.")

    content_type = (audio.content_type or "application/octet-stream").lower()
    if not (
        content_type.startswith("audio/")
        or content_type in {
            "video/webm",
            "video/mp4",
            "application/octet-stream",
        }
    ):
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    filename = (audio.filename or "voice-command.wav")
    filename = filename.replace("/", "_").replace("\\", "_")[:120]
    key, _, _ = await _provider_config(db, api_key, provider)
    if not key:
        raise HTTPException(
            status_code=409,
            detail=f"{provider} is not configured for this project.",
        )

    timeout = httpx.Timeout(settings.voice_http_timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "sarvam":
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": key},
                    data={
                        "model": "saaras:v4",
                        "language_code": language_code or "unknown",
                        "mode": "transcribe",
                    },
                    files={"file": (filename, payload, content_type)},
                )
                response.raise_for_status()
                data = response.json()
                transcript = data.get("transcript", "")
                detected_language = data.get("language_code")
            elif provider == "fish":
                fish_data = {"ignore_timestamps": "true"}
                if language_code and language_code != "unknown":
                    fish_data["language"] = language_code
                response = await client.post(
                    "https://api.fish.audio/v1/asr",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "model": "transcribe-1-pro",
                    },
                    data=fish_data,
                    files={"audio": (filename, payload, content_type)},
                )
                response.raise_for_status()
                data = response.json()
                transcript = data.get("text", "")
                detected_language = data.get("language")
            else:
                response = await client.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={"xi-api-key": key},
                    data={"model_id": "scribe_v3"},
                    files={"file": (filename, payload, content_type)},
                )
                response.raise_for_status()
                data = response.json()
                transcript = data.get("text", "")
                detected_language = data.get("language_code")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            detail = f"{provider} rejected the configured API key."
        elif status == 429:
            detail = f"{provider} rate limit reached."
        else:
            detail = f"{provider} transcription failed (HTTP {status})."
        raise HTTPException(status_code=502, detail=detail) from exc
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{provider} transcription service is unreachable.",
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{provider} returned an invalid transcription response.",
        ) from exc

    transcript = str(transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="No speech was detected. Try a clearer or longer recording.",
        )
    return {
        "provider": provider,
        "transcript": transcript[:_MAX_COMMAND_CHARS],
        "language_code": detected_language,
    }


@router.post("/speak")
async def synthesize_speech(
    body: VoiceSpeechRequest,
    api_key: ApiKey = Depends(require_scope("run_tests")),
    db: AsyncSession = Depends(get_db),
):
    """Synthesize a short response using the selected provider."""
    key, entry, _ = await _provider_config(db, api_key, body.provider)
    if not key:
        raise HTTPException(
            status_code=409,
            detail=f"{body.provider} is not configured for this project.",
        )

    timeout = httpx.Timeout(settings.voice_http_timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if body.provider == "sarvam":
                response = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": key},
                    json={
                        "text": body.text,
                        "language_code": body.language_code,
                        "model": "bulbul:v4-flash",
                        "speaker": entry.get("speaker") or settings.sarvam_tts_speaker,
                        "output_audio_codec": "wav",
                    },
                )
                response.raise_for_status()
                data = response.json()
                audio_chunks = data.get("audios") or []
                if not audio_chunks:
                    raise HTTPException(
                        status_code=502,
                        detail="Sarvam returned no speech audio.",
                    )
                audio_bytes = b"".join(
                    base64.b64decode(chunk) for chunk in audio_chunks
                )
                media_type = "audio/wav"
            elif body.provider == "fish":
                reference_id = (
                    entry.get("reference_id") or settings.fish_tts_reference_id
                )
                if not reference_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Fish Audio TTS requires a voice reference ID. Add it in provider settings.",
                    )
                response = await client.post(
                    "https://api.fish.audio/v1/tts",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "model": "s2.1-pro-free",
                    },
                    json={
                        "text": body.text,
                        "reference_id": reference_id,
                        "format": "mp3",
                        "latency": "normal",
                    },
                )
                response.raise_for_status()
                audio_bytes = response.content
                media_type = "audio/mpeg"
            else:
                voice_id = entry.get("voice_id") or settings.elevenlabs_voice_id
                if not voice_id or not re.fullmatch(
                    r"[A-Za-z0-9_-]{6,200}", str(voice_id)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="ElevenLabs TTS requires a valid voice ID. Add it in provider settings.",
                    )
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": key},
                    json={
                        "text": body.text,
                        "model_id": "eleven_flash_v2_5",
                    },
                )
                response.raise_for_status()
                audio_bytes = response.content
                media_type = "audio/mpeg"
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            detail = f"{body.provider} rejected the configured API key."
        elif status == 429:
            detail = f"{body.provider} speech rate limit reached."
        else:
            detail = f"{body.provider} speech synthesis failed (HTTP {status})."
        raise HTTPException(status_code=502, detail=detail) from exc
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{body.provider} speech service is unreachable.",
        ) from exc

    if not audio_bytes:
        raise HTTPException(status_code=502, detail=f"{body.provider} returned empty speech audio.")
    return Response(content=audio_bytes, media_type=media_type)


@router.post("/resolve")
async def resolve_voice_command(
    body: VoiceResolveRequest,
    api_key: ApiKey = Depends(require_scope("run_tests")),
):
    """Create a safe, editable QA RunRequest preview; this endpoint never starts a run."""
    command = body.command.strip()
    lowered = command.lower()
    if not re.search(
        r"\b(run|start|execute|test|check|qa|regression|validate)\b",
        lowered,
    ):
        return {
            "status": "unsupported",
            "message": "This voice command composer currently handles QA run requests. Try a run/test/check instruction, or provide the repository and validation details.",
            "clarifications": [],
            "run_request": None,
        }

    repo_url = (body.repo_url or "").strip()
    if not repo_url:
        match = _HTTPS_URL_IN_TEXT.search(command)
        if match:
            repo_url = match.group(0).rstrip(".,;:)")

    if repo_url:
        parsed = urlparse(repo_url)
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise HTTPException(
                status_code=422,
                detail="Repository URL must be an HTTPS clone URL without embedded credentials or localhost.",
            )

    commit_sha = (body.commit_sha or "").strip()
    if not commit_sha:
        match_sha = _SHA_IN_TEXT.search(command)
        if match_sha:
            commit_sha = match_sha.group(0)
    if commit_sha and not _FULL_SHA.fullmatch(commit_sha):
        raise HTTPException(
            status_code=422,
            detail="Commit must be a full 40- or 64-character hexadecimal SHA.",
        )

    # Explicit UI selections are a baseline, not a reason to discard profiles
    # requested in the spoken/typed instruction. Merge both sources and keep
    # deterministic ordering so the preview exactly reflects the user's intent.
    groups: list[str] = []
    if body.probe_groups is not None:
        unknown = sorted(set(body.probe_groups) - _ALLOWED_PROFILES)
        if not body.probe_groups or unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid QA profile selection: {unknown or 'empty profile list'}.",
            )
        groups.extend(body.probe_groups)

    if "security" in lowered:
        groups.append("security")
    if "aggressive" in lowered:
        groups.append("aggressive-test")
    elif "deep" in lowered:
        groups.append("deep-test")
    if re.search(r"\b(browser|web|playwright)\b", lowered):
        groups.append("web")

    groups = list(dict.fromkeys(groups))
    if not set(groups) & _FUNCTIONAL_PROFILES:
        groups.insert(0, "test")

    clarifications = []
    if not repo_url:
        clarifications.append("Which repository should I test? Provide its HTTPS clone URL.")
    if not commit_sha:
        clarifications.append("Which exact commit should I test? Provide the full commit SHA; a moving branch will not be guessed.")
    if "web" in groups and not body.start_command:
        clarifications.append("What approved application start command should the browser profile use?")
    if "web" in groups and body.port is None:
        clarifications.append("Which local port will the application listen on?")

    if clarifications:
        return {
            "status": "needs_clarification",
            "message": "I prepared a QA request but need more details before it can be submitted.",
            "clarifications": clarifications,
            "run_request": None,
            "draft": {
                "repo_url": repo_url or None,
                "commit_sha": commit_sha or None,
                "probe_groups": groups,
            },
        }

    run_request = {
        "repo_url": repo_url,
        "commit_sha": commit_sha.lower(),
        "probe_groups": groups,
    }
    if "web" in groups:
        run_request["start_command"] = body.start_command
        run_request["port"] = body.port

    return {
        "status": "ready",
        "message": "The QA request is ready for review. Nothing has been submitted yet.",
        "clarifications": [],
        "run_request": run_request,
    }
