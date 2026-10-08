"""Cloud LLM client — the hosted-model path for --deep-test / --aggressive-test.

Configured entirely by environment variables (injected into the sandbox by
the executor from `workflo config set-llm`):

    WORKFLO_LLM_BASE_URL   e.g. https://inference.example.com/v1
    WORKFLO_LLM_API_KEY    bearer token — never logged, never persisted
    WORKFLO_LLM_MODEL      e.g. qwen3-4b-4bit
    WORKFLO_LLM_TIMEOUT    per-request seconds (default 60)

The interface intentionally matches ModelServer.generate() so the worker's
model stage can swap local Ollama for the hosted endpoint without changing
callers:

    client = CloudLLMClient.from_env()
    if client is not None and client.is_usable():
        text = client.generate(prompt, system=sys_prompt)

Failure philosophy (this is what a demo audience sees):
  - Absent config      -> NOT "cloud mode" at all; worker falls back to the
                          embedded Ollama in the deep image. No error text.
  - Present but faked  -> load_llm_config-side placeholder detection in the
                          CLI; if a placeholder value still reaches the worker
                          (e.g. raw env injection), is_placeholder() catches it
                          here and returns a clear, named error.
  - Real but failing   -> short timeouts, no retries against a dead endpoint,
                          and the error string says exactly what was attempted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_MODEL = "qwen3-4b-4bit"
DEFAULT_TIMEOUT_SECONDS = 60.0

# Values that mean "still a placeholder", checked against the base URL.
# The CLI rejects these at set-llm time; this is the in-sandbox backstop.
_PLACEHOLDER_MARKERS = ("<", "placeholder", "example.com", "your-", "changeme")


class CloudLLMError(RuntimeError):
    """Raised when the cloud LLM call cannot complete."""


@dataclass
class CloudLLMConfig:
    base_url: str
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_placeholder(self) -> bool:
        b = (self.base_url or "").strip().lower()
        return not b or any(m in b for m in _PLACEHOLDER_MARKERS)


class CloudLLMClient:
    """OpenAI-compatible chat client with a generate(key word) surface.

    Deliberately minimal: one endpoint shape (/chat/completions), one retry
    policy (none — the caller's model stage already has a correction retry),
    and hard timeouts so a bad endpoint can never hang a sandboxed run.
    """

    def __init__(self, config: CloudLLMConfig):
        self.config = config

    # ---- construction ---------------------------------------------------

    @classmethod
    def from_env(cls) -> Optional["CloudLLMClient"]:
        """Build a client from WORKFLO_LLM_* env vars, or None if unset.

        "Unset" means the executor did not inject cloud-LLM settings — the
        worker then stays on the embedded-model path. Returning None (not a
        broken client) keeps that distinction clean.
        """
        base_url = (os.environ.get("WORKFLO_LLM_BASE_URL") or "").strip()
        api_key = (os.environ.get("WORKFLO_LLM_API_KEY") or "").strip()
        if not base_url or not api_key:
            return None
        return cls(
            CloudLLMConfig(
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=(os.environ.get("WORKFLO_LLM_MODEL") or DEFAULT_MODEL).strip(),
                timeout_seconds=float(os.environ.get("WORKFLO_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
            )
        )

    # ---- health / clarity ----------------------------------------------

    def usability_error(self) -> Optional[str]:
        """None if usable; otherwise a human-readable reason string."""
        if self.config.is_placeholder():
            return (
                f"WORKFLO_LLM_BASE_URL is still a placeholder "
                f"({self.config.base_url!r}) — run: "
                f"workflo config set-llm --base-url <url> --api-key <key>"
            )
        if not self.config.api_key:
            return "WORKFLO_LLM_API_KEY missing in sandbox env"
        return None

    # ---- inference ------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> str:
        """One-shot completion. Raises CloudLLMError with a clear message."""
        unusable = self.usability_error()
        if unusable:
            raise CloudLLMError(unusable)

        import json
        import urllib.error
        import urllib.request

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "temperature": 0.1,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        timeout = timeout_seconds or self.config.timeout_seconds
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise CloudLLMError(
                    f"model endpoint rejected the API key (HTTP {e.code}) — "
                    f"recreate the key and re-run workflo config set-llm"
                ) from e
            raise CloudLLMError(f"model endpoint HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise CloudLLMError(f"cannot reach {self.config.base_url}: {e.reason}") from e
        except TimeoutError as e:
            raise CloudLLMError(f"model call timed out after {timeout}s") from e
        except Exception as e:  # socket.timeout and friends don't all subclass TimeoutError
            raise CloudLLMError(f"model call failed: {type(e).__name__}: {e}") from e

        try:
            data = json.loads(payload)
        except ValueError as e:
            raise CloudLLMError(f"model endpoint returned non-JSON: {payload[:200]!r}") from e

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise CloudLLMError(f"model response missing choices: {payload[:200]!r}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise CloudLLMError("model returned empty content")
        return content


__all__ = [
    "CloudLLMClient",
    "CloudLLMConfig",
    "CloudLLMError",
    "DEFAULT_MODEL",
]
