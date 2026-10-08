"""
Routes a flag (--deep-test, --aggressive-test, --security, reporting) to the
correct LoRA adapter on a single shared base model, and validates every
response against the schemas in schemas.py before returning it.

Default serving backend: llama.cpp llama-server (CPU-only, MIT licensed).
See serving/docker-compose.llamacpp.yml. The optional GPU path (vLLM) lives
under serving/.optional-gpu-path/ and is not required for MMVP.

Architecture this assumes:
  - One llama-server process, one base GGUF (Qwen3-Coder dense, smallest
    checkpoint that fits), started with all three adapters loaded via
    --lora / --lora-init-without-apply (scales default to 0.0).
  - Per request, exactly one adapter is activated via the `lora` field
    (id + scale). No shared mutable server state, no load/unload race.
  - Adapter IDs are discovered at runtime from GET /lora-adapters by
    matching the adapter path/filename substring — never hardcoded as
    "test-gen is always id 0".
  - Structured decoding uses json_schema at the sampler, then Pydantic +
    the compile-check gate. Pydantic stays load-bearing: llama.cpp can
    silently fall back to unconstrained output on malformed schemas
    (ggml-org/llama.cpp#19051).

Public interface (stable across backends):
  - generate_for_flag(flag, system_prompt, user_prompt)
  - generate_report(results_json)

This module talks only to the local llama-server (default
http://127.0.0.1:8080). It is meant to run *inside* the sandbox with
--network none. Enforcing that boundary — and P4/P5 teardown + signed
receipts — is the sandbox runtime's job; this file assumes it holds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from schemas import ProposeInvariantCall, ReportNarrative, WriteTestCall
from safety_gate import compile_check, property_expr_check

TaskType = Literal["test-gen", "reasoning", "reporting"]

FLAG_TASK_MAP: dict[str, TaskType] = {
    "--deep-test": "test-gen",
    "--aggressive-test": "reasoning",
    "--security": "reasoning",
}

# Substring matched against GET /lora-adapters[*].path (or .name).
# Training output must land as GGUF files whose filenames contain these.
ADAPTER_REGISTRY: dict[TaskType, dict[str, str]] = {
    "test-gen": {"match": "test-gen", "path_hint": "/adapters/test-gen.gguf"},
    "reasoning": {"match": "reasoning", "path_hint": "/adapters/reasoning.gguf"},
    "reporting": {"match": "reporting", "path_hint": "/adapters/reporting.gguf"},
}

SCHEMA_BY_TASK = {
    "test-gen": WriteTestCall,
    "reasoning": ProposeInvariantCall,
    "reporting": ReportNarrative,
}


class AdapterLoadError(RuntimeError):
    """Raised when adapter discovery fails (missing / mismatched LoRA)."""


class GenerationValidationError(RuntimeError):
    """Raised when the model's output fails schema validation or the compile-check gate."""


@dataclass
class RouterConfig:
    # llama-server default port is 8080 (vLLM used 8000; keep them distinct).
    base_url: str = "http://127.0.0.1:8080"
    timeout_sec: float = 60.0
    # Kept for callers that still pass the old name during the migration.
    vllm_base_url: str | None = None

    def __post_init__(self) -> None:
        if self.vllm_base_url:
            self.base_url = self.vllm_base_url


class ModelRouter:
    """
    Thin client over llama-server's completion + LoRA endpoints.

    Adapters are assumed already loaded at process start (scale 0.0). This
    client only discovers their IDs and activates exactly one per request.
    """

    def __init__(self, config: RouterConfig | None = None, client: httpx.Client | None = None):
        self.config = config or RouterConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url, timeout=self.config.timeout_sec
        )
        self._adapter_ids: dict[TaskType, int] | None = None

    def task_for_flag(self, flag: str) -> TaskType:
        if flag not in FLAG_TASK_MAP:
            raise ValueError(f"no adapter mapping for flag '{flag}' — is this flag AI-driven at all?")
        return FLAG_TASK_MAP[flag]

    def discover_adapters(self, force: bool = False) -> dict[TaskType, int]:
        """
        GET /lora-adapters once and map each task to an adapter id by
        filename substring. Cached for the life of the router unless force=True.
        """
        if self._adapter_ids is not None and not force:
            return self._adapter_ids

        resp = self._client.get("/lora-adapters")
        if resp.status_code >= 400:
            raise AdapterLoadError(
                f"failed to list adapters: {resp.status_code} {resp.text}"
            )
        try:
            listing = resp.json()
        except json.JSONDecodeError as e:
            raise AdapterLoadError(f"/lora-adapters returned non-JSON: {e}") from e
        if not isinstance(listing, list):
            raise AdapterLoadError(f"/lora-adapters expected a list, got {type(listing).__name__}")

        found: dict[TaskType, int] = {}
        for task, meta in ADAPTER_REGISTRY.items():
            needle = meta["match"].lower()
            for entry in listing:
                path = str(entry.get("path") or entry.get("name") or "")
                if needle in path.lower():
                    found[task] = int(entry["id"])
                    break
            if task not in found:
                raise AdapterLoadError(
                    f"no LoRA adapter matching '{needle}' in server listing "
                    f"(looked for substring in path/name). Got: {listing!r}"
                )

        self._adapter_ids = found
        return found

    # Back-compat alias — older call sites / tests used ensure_adapter_loaded.
    def ensure_adapter_loaded(self, task: TaskType) -> None:
        self.discover_adapters()
        if task not in (self._adapter_ids or {}):
            raise AdapterLoadError(f"adapter for task '{task}' not discovered")

    def _json_schema_for_task(self, task: TaskType) -> dict[str, Any]:
        """
        JSON Schema passed to llama-server's sampler.

        NOTE (llama.cpp#19051): a malformed or unsupported schema can cause
        llama-server to silently fall back to unconstrained sampling. The
        Pydantic validation + compile-check gate below are therefore
        load-bearing, not redundant — never remove them even if the sampler
        claims to enforce the schema.
        """
        schema_cls = SCHEMA_BY_TASK[task]
        return schema_cls.model_json_schema()

    def _build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """
        Chat template for the locked MMVP base model:
        qwen2.5-coder:7b-instruct-q4_K_m — same stack the live Ollama
        deep-test path already runs. Template taken from Ollama's
        Modelfile (ChatML <|im_start|>/<|im_end|> turns); full text in
        serving/CHAT_TEMPLATE.md. A wrong template will not crash — it
        will quietly generate worse output — so keep this in sync with
        `ollama show <model> --modelfile` if the base ever changes.
        """
        return (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _chat(self, task: TaskType, system_prompt: str, user_prompt: str) -> str:
        ids = self.discover_adapters()
        adapter_id = ids[task]
        # Activate exactly one adapter for this request; unspecified adapters
        # default to scale 0.0 on the server side.
        lora = [{"id": adapter_id, "scale": 1.0}]
        payload = {
            "prompt": self._build_prompt(system_prompt, user_prompt),
            "temperature": 0.2,
            "n_predict": 2048,
            "lora": lora,
            # Sampler-level constraint — see #19051 note above.
            "json_schema": self._json_schema_for_task(task),
        }
        resp = self._client.post("/completion", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # llama-server returns {"content": "..."}; tolerate OpenAI-shaped too.
        if "content" in data:
            return data["content"]
        return data["choices"][0]["message"]["content"]

    def generate_for_flag(self, flag: str, system_prompt: str, user_prompt: str):
        """
        Full pipeline: flag -> task -> adapter -> generation -> schema
        validation -> compile-check gate. Returns a validated schema object.
        Raises GenerationValidationError on anything that fails, which the
        caller should treat as "discard this candidate," not as a crash —
        a bad generation should cost a wasted call, never a false result.
        """
        task = self.task_for_flag(flag)
        raw = self._chat(task, system_prompt, user_prompt)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise GenerationValidationError(f"model did not return valid JSON: {e}") from e

        schema_cls = SCHEMA_BY_TASK[task]
        try:
            obj = schema_cls.model_validate(payload)
        except ValidationError as e:
            raise GenerationValidationError(f"schema validation failed: {e}") from e

        if isinstance(obj, WriteTestCall):
            result = compile_check(obj.content)
            if not result.ok:
                raise GenerationValidationError(f"compile-check failed: {result.reason}")
        elif isinstance(obj, ProposeInvariantCall):
            for expr in (obj.hypothesis_strategy, obj.property_check):
                result = property_expr_check(expr)
                if not result.ok:
                    raise GenerationValidationError(f"compile-check failed: {result.reason}")

        return obj

    def generate_report(self, results_json: dict) -> ReportNarrative:
        """Reporting adapter path — takes only structured results, never source."""
        system_prompt = (
            "You are summarizing automated test results. You will only ever "
            "receive structured JSON test outcomes, never source code. "
            "Respond with a single JSON object matching the ReportNarrative schema."
        )
        raw = self._chat("reporting", system_prompt, json.dumps(results_json))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise GenerationValidationError(f"model did not return valid JSON: {e}") from e
        try:
            return ReportNarrative.model_validate(payload)
        except ValidationError as e:
            raise GenerationValidationError(f"schema validation failed: {e}") from e

    def close(self):
        self._client.close()
