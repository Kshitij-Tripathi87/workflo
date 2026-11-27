# 03 — Inference Provider, Model Selection and Privacy Specification

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)  
**Core rule:** users choose their models; Workflo enforces what data each mode is permitted to send.

## 1. Product requirements

- A user can configure one or more provider profiles in CLI or dashboard Settings.
- A profile may target a local model server, a Workflo-pinned local runtime or a cloud API.
- The user selects an active profile at project or run level.
- All models must return a Workflo-normalized `InferencePlan`; no model provider owns tool execution.
- Cloud provider keys remain outside the guest and are called only through Workflo's privacy gateway.
- Hosted models never receive source code, raw file bodies, diffs, unfiltered logs or secrets.
- Local models may receive source context only when the user explicitly selects local mode and the endpoint is confirmed to be customer-controlled.
- Provider failure must not cause an automatic switch from local to cloud or cloud to local.
- Provider settings are part of an immutable run snapshot so the run's model, mode, version and privacy policy are auditable.

## 2. The fundamental design: provider vs transport vs privacy mode

Do not model “OpenAI”, “Ollama” or “OpenRouter” as a hard-coded agent mode. Separate three dimensions:

1. **Provider:** API vendor / local server adapter (OpenAI, Anthropic, Gemini, OpenRouter, Ollama, LM Studio, llama.cpp, vLLM, generic).
2. **Endpoint class:** `cloud` or `local_customer_controlled`.
3. **Data policy:** `metadata_only` or `local_source_context`.

Only these combinations are supported initially:

| Endpoint class | Data policy | Allowed? | Rules |
|---|---|---|---|
| Cloud | `metadata_only` | Yes | Must call Workflo gateway; strict typed allowlist; no source/raw content |
| Cloud | `local_source_context` | **No** | Hard rejected by schema and server-side policy |
| Local customer-controlled | `metadata_only` | Yes | May use same sanitized request for parity and privacy testing |
| Local customer-controlled | `local_source_context` | Yes, explicit opt-in | Source can be sent only to verified customer endpoint; never silently mirrored to cloud |

The system must not infer that a provider is local based only on provider name. A self-hosted OpenAI-compatible server could be remote. A cloud vendor may offer local models. The user must declare endpoint class, Workflo probes the connection, then applies a policy that can be stricter but cannot be weaker than organization policy.

## 3. Provider profile schema

Proposed shape (fields must be added to canonical Python models and JSON Schema, then mirrored into web types):

```yaml
api_version: workflo.dev/v1
kind: InferenceProfile
metadata:
  id: openai-prod
  name: OpenAI — metadata only
spec:
  provider: openai
  endpoint_class: cloud
  base_url: https://api.openai.com/v1
  model: <chosen model id>
  credential_ref: vault://tenant/provider/openai/key-id
  capabilities:
    structured_output: true
    streaming: true
    tool_calling: false
  privacy:
    data_policy: metadata_only
    allow_source: false
    allow_raw_logs: false
    allow_browser_text: false
  limits:
    request_timeout_seconds: 60
    max_input_bytes: 64000
    max_output_tokens: 2048
    max_requests_per_run: 100
  retry:
    max_attempts: 2
    backoff_ms: 500
```

`credential_ref` is an opaque pointer; never an actual secret. The endpoint and model may be included in reports/receipts as identifiers, subject to customer policy. The API key never is.

### 3.1 Profile precedence

1. Organization policy (hard upper bound; cannot be weakened by project/user).
2. Project default profile and privacy mode.
3. RunSpec explicit selection.
4. CLI convenience defaults.

A run snapshots the resolved effective profile, schema version, provider adapter version and policy digest. Later profile changes do not alter an admitted run.

## 4. Provider adapter contract

Implement an adapter protocol in the worker model package (or a narrowly scoped shared module) and have the control plane own a server-side cloud adapter registry. Keep common domain types in `packages/workflo-schema`.

```python
class ProviderAdapter(Protocol):
    provider_id: str

    def validate_config(self, config: ProviderConfig) -> ProviderValidation: ...
    async def health(self, config: ProviderConfig) -> ProviderHealth: ...
    def capabilities(self, config: ProviderConfig) -> ProviderCapabilities: ...
    async def create_plan(
        self,
        request: SanitizedInferenceRequest,
        config: ProviderConfig,
        budget: InferenceBudget,
    ) -> ProviderPlanResponse: ...
```

Adapter responsibilities:

- Provider-specific auth header/format.
- Model identifier and endpoint path normalization.
- Provider-native structured response/tool call mode where supported.
- Timeout, retries and streaming transport.
- Usage metadata extraction without storing prompt contents.
- Provider error mapping to stable Workflo error classes.
- Schema compatibility negotiation.

Adapter must **not** decide allowed tools, expand policy, sanitize arbitrary text or directly call a tool. Domain-level sanitization and policy enforcement occur before the adapter receives the request.

### 4.1 Normalized response

The adapter returns canonical `InferencePlan` only:

```json
{
  "done": false,
  "steps": [
    {
      "tool": "http_request",
      "args": {
        "method": "GET",
        "route_id": "health-check"
      },
      "reason_code": "check_app_health"
    }
  ]
}
```

Use a stable reason code and bounded rationale enum instead of arbitrary natural-language reasoning in the plan. The user-facing report can include a generated explanation, but model rationale text is not authoritative evidence.

Every response is validated against strict Pydantic schema; unknown fields, unknown tools, invalid arguments, too many steps, excessive response size, unrecognized enum or policy violation are rejected. For providers that support JSON-schema constrained output, supply the schema; still validate locally. For providers without exact schema support, request JSON and apply identical local validation.

## 5. Provider coverage plan

### 5.1 First-party cloud providers

| Adapter | Initial supported mode | Provider-specific work | Release requirement |
|---|---|---|---|
| OpenAI | Metadata-only cloud | Responses API or supported chat endpoint; strict structured output where available; request/usage id capture | Gateway request capture, schema validation, timeout and error tests |
| Anthropic | Metadata-only cloud | Messages API, content/tool-use block normalization, strict JSON schema or tool schema adapter | Same privacy and normalized-plan tests |
| Google Gemini | Metadata-only cloud | `generateContent`/supported structured output config; model ID mapping | Same privacy and normalized-plan tests |
| OpenRouter | Metadata-only cloud | Model selection, vendor routing metadata, structured-output support negotiation | Enforce allowed model list and do not send request to user-selected unsafe endpoints |
| Generic cloud OpenAI-compatible | Metadata-only cloud | Base URL allowlist, chat-completions compatible shape | Must explicitly configure cloud endpoint and use Workflo gateway; reject local-source policy |

Cloud API provider adapters run on Workflo's gateway service. The CLI and guest do not receive vendor API keys. The gateway uses an encrypted per-tenant credential reference. A user-provided provider is not automatically trusted: Workflo must know the provider endpoint and privacy mode. Customer-hosted cloud endpoint/private deployment can be categorized as customer-managed only after explicit confirmation and the customer's legal/security basis.

### 5.2 First-party local providers

| Adapter | Initial use | Guardrails |
|---|---|---|
| Workflo llama.cpp/GGUF | Workflo-controlled local model path and release acceptance | Preserve current pinned GGUF manifest/image/hash rules; only this route satisfies current P4 release model gate |
| Ollama | User local model endpoint | Default `http://127.0.0.1:11434`; provider name and actual endpoint class both checked; no hidden cloud fallback |
| LM Studio | User local model endpoint | Local server must be enabled by user; endpoint tested; model capability detection |
| Generic OpenAI-compatible local | Customer-managed model server | Loopback default; private LAN requires explicit opt-in and TLS/auth requirements |
| vLLM | User-managed local/private server | Require secure listener configuration and verify all exposed routes; the API key option does not automatically protect every endpoint, per upstream docs |

Local inference call flow:

```text
Guest observations / approved local source context
             |
             v
Local runner inference broker (outside guest or inside guest according to deployment)
             |
             v
Provider adapter ---> localhost / user-controlled private endpoint
             |
             v
Normalized InferencePlan
             |
             v
Guest ToolGateway -> policy -> tool execution
```

There are two deployment choices requiring explicit implementation decision:

- **Preferred for source privacy:** local model runs on customer host, and the trusted runner sends only selected local context to that local endpoint. Do not expose the local model port to guest/network. The guest emits typed observation requests; the host adapter performs a source-authorized local inference call and returns a bounded plan over the authenticated guest protocol.
- **Alternative:** local model process runs inside the guest. This gives the model source access without source crossing guest boundary but requires model artifacts/GPU resources inside the guest, process-level inference lifecycle, GPU/virtio strategy and teardown. Defer this until the host-brokered model route has been measured.

For the first prototype, use host-brokered local inference for the Workflo runner and metadata-only request from the guest. Do not send direct arbitrary file paths from guest to host; host must resolve file requests under the approved snapshot root and apply file-size/path rules before local model input.

## 6. Privacy Gateway

### 6.1 Current repository position

`apps/control-plane/app/api/v1/inference.py` already builds prompts server-side using bounded structured observations and validates the returned plan. `packages/workflo-schema/src/workflo_schema/inference.py` has `RuntimeObservation`, `InferenceGatewayRequest`, source-key screening and provenance fields.

However, `apps/workflo-cli/src/workflo_cli/llm_config.py` currently supports `mode="direct"` and can call a configured endpoint directly. `docs/reconciliation/PHASE_0_WORKFLO_TRUST.md` correctly flags this as a hosted privacy bypass risk. The implementation must close this path before adding more providers.

### 6.2 New gateway flow

```text
Guest -> host inference broker
  -> construct SanitizedInferenceRequest from allowlisted event types
  -> validate policy = cloud_metadata_only
  -> sign/attach run + attempt + profile identity
  -> control plane /v2 inference plan endpoint
  -> provider adapter (server-side BYOK secret)
  -> model output bounded and validated
  -> canonical InferencePlan
  -> host/guest ToolGateway executes authorized tool
```

The gateway should not accept:

- arbitrary `prompt` or `messages` arrays from caller;
- arbitrary `detail` text fields;
- `read_file` content, code snippets, source diffs or raw logs;
- unbounded observation arrays or arbitrary metadata dictionaries;
- user-controlled provider URL unless it passes a configured provider allowlist and SSRF policy.

### 6.3 Positive allowlist observation schema

Recommended typed observation classes:

| Type | Fields | Explicitly excluded |
|---|---|---|
| `RunPhaseObservation` | phase enum, elapsed ms, attempt number | raw event messages, command output |
| `TestSummaryObservation` | suite id, total/pass/fail/skip counts, duration, result digest | test file contents, test source, assertion body |
| `ApiObservation` | route id/template, method enum, status, latency, assertion enum | URL query values, auth headers, body text |
| `BrowserObservation` | action enum, origin id, success bool, assertion code, screenshot digest optional | DOM, page text, form values, cookies |
| `LogSummaryObservation` | source id, severity counts, safe error code list, redaction count | original log lines, stack traces |
| `ToolObservation` | approved tool id, allowed/denied, result class, duration | tool free-text arguments/results |
| `ResourceObservation` | CPU/memory/disk/network aggregates, limit hit enum | host paths, process command line with user data |
| `AgentBudgetObservation` | calls remaining, seconds remaining, batches remaining | chain-of-thought or hidden reasoning |

Mission field: user-authored text, short length cap and secret pattern filtering. Do not allow a source-provided file to set or override mission instructions.

### 6.4 Redaction and content inspection

Use a layered approach:

1. **Schema allowlist**: only known observation types and field names.
2. **Type constraints**: enums, bounded IDs, numeric metrics, fixed route ids, strict lengths.
3. **No free-form data where unnecessary**: replace text with error codes and digest values.
4. **Secret pattern scan**: detect common credentials in allowed mission and metadata fields.
5. **Source marker tests**: seed canary source strings/secrets and verify no captured upstream payload contains them.
6. **Request capture**: test adapter stores exact body in memory for assertion; never store body in production telemetry.
7. **Egress enforcement**: only gateway host can be called for cloud mode; direct provider egress from guest and runner is blocked by configuration/egress policy.

Regex filters must not be considered proof that arbitrary text is source-free. Remove arbitrary text from cloud schema instead.

## 7. Secret storage and lifecycle

### 7.1 Cloud BYOK

- User submits key through authenticated HTTPS; frontend sends it once and clears field immediately.
- API encrypts with envelope encryption; tenant-bound KMS key/reference. Store ciphertext and metadata only.
- Key decrypt permission restricted to gateway process identity and selected tenant/provider credential.
- Gateway injects key in-memory for one call; never log header, never return key, never pass to runner/guest.
- Key replacement/revocation audited; support per-project key if policy requires.
- Database backups hold ciphertext only. Key rotation and deletion are tested.

### 7.2 Local provider credential

- Local API key saved in OS credential store on runner machine.
- Local endpoint URL/model/profile metadata in config; secret value not persisted to plain file.
- For local model endpoints that do not require auth (e.g. loopback Ollama), no synthetic secret is required.
- LAN endpoints require secure transport and authentication; the runner warns about unencrypted HTTP beyond loopback.

### 7.3 CLI commands

```bash
workflo provider add openai --mode cloud --model <model-id>
# Key collected via hidden prompt, not argv.

workflo provider add ollama --mode local \
  --base-url http://127.0.0.1:11434 --model <local-model>

workflo provider test openai-main
workflo provider use openai-main
workflo provider profiles
workflo provider remove openai-main
```

For CI or automation, accept secrets through dedicated stdin/secret-file descriptor or platform secret manager; never `--api-key <literal>`.

## 8. Source-aware agent behavior

Cloud mode can still help with black-box app QA: it can decide which declared tests to run, which routes/flows to probe and what additional evidence to gather from typed summaries. It cannot inspect source directly. This is a product trade-off; show the mode distinction in user interface.

Local mode may inspect selected source files, tests and configuration to explain likely causes and create repair suggestions. Use these constraints:

- Source selection controlled by user project policy.
- Exclude secrets and sensitive file patterns by default.
- Limit maximum file bytes and total context bytes.
- Path resolution prevents escape from source snapshot.
- Source contents do not enter logs, gateway traces, analytics or receipt.
- Local endpoint identity is shown in run details.
- Local model request content is considered customer data and excluded from Workflo telemetry.

No data, code or user setting is moved to another provider without a separate user opt-in.

## 9. Failure handling and privacy-safe retries

| Failure | Required behavior |
|---|---|
| Provider timeout | bounded retry with same profile; no mode switch |
| Provider rate limit | retry-after/backoff if within run deadline; record error class |
| Provider returns malformed JSON | reject, optionally one repair-format retry; if still invalid, end agent planning with failure/inconclusive status |
| Unknown tool | deny and record; continue only if policy says safe |
| Unknown argument | reject entire step; do not coerce to a broader command |
| Token/context overflow | reduce observation batch using deterministic priority rules; never attach source to cloud request |
| Secret detector hit in cloud-bound field | suppress request, report blocked payload class, retain no raw text |
| Local server unavailable | pause/fail model stage; no cloud fallback |
| Cloud gateway unavailable | no direct provider bypass; fail model stage explicitly |
| User revokes credential | stop future inference calls; current run cannot silently use another key |
| Endpoint identity mismatch | fail closed; do not send request |
| User switches profile mid-run | apply only to next run unless explicit replan is separately versioned and approved |

## 10. Provider acceptance tests

Every provider adapter must pass the following common contract suite:

1. Valid configuration and invalid endpoint.
2. Health check success, auth failure, timeout and malformed health response.
3. Provider-native request correctly formed.
4. Canonical plan response parsed and validated.
5. Unknown tool rejected.
6. Unknown input field rejected.
7. Too many actions/oversized response rejected.
8. Provider refusal/safety response handled distinctly from timeout.
9. Rate limit and retry behavior bounded.
10. Streaming interruption handled without partial plan execution.
11. Usage/latency recorded without retaining prompt.
12. API key not present in logs/errors or returned DTO.
13. Canary source marker absent from captured cloud payload.
14. A local provider endpoint stays on local runner, no egress to cloud.
15. Cloud mode cannot select `local_source_context`.
16. Local mode can read permitted source but cannot write original checkout.
17. No provider failover changes privacy mode.

### 10.1 Live provider matrix

Use mocked endpoints in normal CI. Add protected/manual live tests with low-privilege API keys to confirm actual provider behavior. The test harness must scrub request/response contents and retain only status, schema verdict, token counters, latency and provider request id. Avoid hardcoding model availability or pricing: provider models change and should be selected by configuration.

## 11. Model and agent quality evaluation

Measure more than “valid JSON rate”:

- tool-plan schema validity;
- policy-violation proposal rate;
- correct tool selection against a known QA mission;
- useful probe coverage against a fixture application;
- missed-defect and false-positive rate on labeled cases;
- duplicate action rate;
- completion within step/time/token budget;
- provider failure recovery;
- cloud payload privacy violation count (must be zero);
- local model source-context usefulness vs cloud metadata-only mode.

Maintain a Workflo-owned evaluation set with intentionally vulnerable but non-dangerous test apps, seeded functional failures, API contract changes, auth edge cases, broken app startup and misleading logs. Store expected observations and acceptable tool plans. Never evaluate by simply executing a benchmark repository's README commands as shell instructions.

## 12. Current-code migration plan

1. Inventory every `requests`, `httpx`, `urllib`, SDK or subprocess call that targets an LLM endpoint.
2. Build a data-flow table: caller, endpoint, data fields, key source, guest/host location, profile mode.
3. Disable direct cloud calls from `packages/sandbox-runtime/src/sandbox_runtime/planner.py` and worker direct client paths; maintain local loopback support only.
4. Extend `workflo_schema.inference` with canonical provider settings and positive allowlist request types. Remove cloud `RuntimeObservation.detail` free text from request path or restrict it to fixed error enums.
5. Consolidate `workflo-ai-integration` router/safety gate into worker model adapters; preserve tests and P4 artifact verifier scripts.
6. Update `apps/control-plane/app/api/v1/inference.py` to call provider registry and tenant credential resolver, with a versioned endpoint where needed.
7. Add request capture and source-marker canary test before turning on provider selection in UI.
8. Migrate CLI `set-llm` to a provider profile; preserve alias for compatibility but disallow direct cloud mode.
9. Implement local model host broker; never pass local model API key into guest.
10. Add report and receipt provenance fields (provider/model/endpoint class/privacy policy digest, request count, token usage, request/prompt/response hashes only where safe). Do not place prompt content in receipt.

## 13. External references

- Ollama API: https://github.com/ollama/ollama/blob/main/docs/api/introduction.mdx
- Ollama auth: https://github.com/ollama/ollama/blob/main/docs/api/authentication.mdx
- Ollama OpenAI compatibility: https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx
- LM Studio local server: https://lmstudio.ai/docs/developer/core/server
- vLLM OpenAI-compatible server: https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Responses API: https://developers.openai.com/api/reference/responses/overview
- Gemini API: https://ai.google.dev/gemini-api/docs/get-started
- OWASP Agentic Applications 2026: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/