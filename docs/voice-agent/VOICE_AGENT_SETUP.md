# Voice Agent — Provider Setup and Runtime

**Status:** Initial turn-based voice QA assistant  
**Scope:** Dashboard text and microphone input, provider-routed speech recognition/synthesis, explicit QA preview and run submission.

## 1. Runtime architecture

The first working path is a server-routed, turn-based voice agent:

    User
      |
      +-- Write command -------------------------------+
      |                                                |
      +-- Speak -> Browser microphone -> STT provider  |
                                                       v
                                      Workflo command resolver
                                                       |
                                      Clarify missing target details
                                                       |
                                      Typed QA request preview
                                                       |
                                          User confirms request
                                                       |
                                    Existing POST /v1/runs API
                                                       |
                                     Poll GET /v1/runs/{run_id}
                                                       |
                                        Result + signed receipt
                                                       |
                                             TTS provider
                                                       |
                                            Spoken response

Workflo remains the command authority and uses the existing QA run API. Voice providers handle speech conversion only. The initial resolver is deliberately bounded: it recognizes QA run requests, validates exact repository/commit/profile inputs and returns a typed, editable preview. It does not let a speech model invent shell commands or create a run without the user's separate confirmation.

### Text and voice are equal inputs

Both modes use the same POST /v1/voice/resolve endpoint. Voice mode records a short clip, transcribes it, and puts the transcript into an editable text field. The user can correct the transcript, add repository and commit information, choose registered QA profiles, inspect the preview and then click **Start QA run**.

A partial recording/transcript never triggers execution. Text mode does not need a microphone or speech provider, but still requires an authenticated project API key.

## 2. Provider routing

Speech recognition and speech output are selected independently. For example, a project can use Sarvam for recognition and ElevenLabs for spoken responses. Provider readiness is returned by GET /v1/voice/providers; the API returns status metadata only, never API keys.

| Provider | Speech recognition | Speech output | Provider configuration |
|---|---|---|---|
| Sarvam | Saaras v4 via POST /speech-to-text | Bulbul v4 Flash via POST /text-to-speech | API key; optional speaker ID, default simran_en_customer |
| Fish Audio | POST /v1/asr, model transcribe-1-pro | POST /v1/tts, model s2.1-pro-free | API key; required voice reference_id for TTS |
| ElevenLabs | Scribe v3 via POST /v1/speech-to-text | POST /v1/text-to-speech/{voice_id}/stream | API key; required voice ID for TTS |

### Sarvam

- STT uses https://api.sarvam.ai/speech-to-text, multipart file, model saaras:v4, language_code=unknown for automatic detection and the api-subscription-key header.
- TTS uses https://api.sarvam.ai/text-to-speech, model bulbul:v4-flash, language_code, a speaker ID and WAV output.
- Voice selection and language configuration should be validated against the current Sarvam model/speaker catalog before enabling production defaults.

### Fish Audio

- STT uses https://api.fish.audio/v1/asr, multipart audio, Authorization: Bearer ... and the model: transcribe-1-pro header.
- TTS uses https://api.fish.audio/v1/tts, a voice reference_id, MP3 output and an explicit model header.
- A key by itself is not enough for TTS; the project must also provide a valid reference ID.

### ElevenLabs

- STT uses https://api.elevenlabs.io/v1/speech-to-text, xi-api-key and model_id=scribe_v3.
- TTS uses https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream with xi-api-key, a configured voice ID and eleven_flash_v2_5.
- The voice ID is not the API key; configure both separately.

Provider endpoints and model identifiers are isolated in apps/control-plane/app/api/v1/voice.py. Keep provider-specific payloads out of the dashboard.

## 3. Web SDKs versus API routing

The first dashboard implementation uses the vendors' speech APIs through the Workflo control plane. This is intentional: it keeps credentials server-side and preserves one Workflo command/policy/run authority.

Provider Web SDKs are a separate integration mode, not interchangeable API wrappers:

- **ElevenLabs React SDK (@elevenlabs/react)** connects the browser to an ElevenLabs ElevenAgent. Private agents need a signed URL or conversation token minted by the server. The SDK is suitable for a future real-time agent mode, but a vendor-hosted agent must call Workflo through a narrowly scoped, server-side tool/webhook. Do not let browser audio or an ElevenAgent decide a QA verdict.
- **ElevenLabs Speech Engine** is a closer fit when the platform owns the conversation/LLM/tool logic: ElevenLabs handles speech recognition and synthesis while the server retains the conversation and tool-calling logic over its Speech Engine connection.
- **Sarvam Conversational AI browser SDK** connects to a configured Sarvam voice agent using its workspace/app configuration. That uses a vendor-managed conversation/agent setup; it is not the same as calling Saaras and Bulbul APIs.
- **Fish Agent Web SDK** is an agent-session integration. If enabled later, create short-lived session credentials on the server; never put the Fish API key in browser code.

For the initial release, the UI provides one consistent provider selector and the Workflo control plane owns intent resolution and task execution. A future streaming transport can sit behind the same provider interface after its session-token and server-tool contracts are implemented and tested.

## 4. API endpoints added

All endpoints are mounted under /v1/voice and require a Workflo API key with run_tests, except provider key mutation which requires admin.

| Endpoint | Purpose |
|---|---|
| GET /v1/voice/providers | Return configured provider and capability status |
| PUT /v1/voice/providers/{provider} | Encrypt and save a project-specific provider key |
| DELETE /v1/voice/providers/{provider} | Remove a project-specific provider key |
| POST /v1/voice/transcribe | Transcribe a short microphone recording |
| POST /v1/voice/speak | Synthesize a short spoken response |
| POST /v1/voice/resolve | Resolve text/transcript to a safe QA run preview |

POST /v1/runs remains unchanged and is called only after the user confirms the preview. The dashboard then polls GET /v1/runs/{run_id} and displays the returned receipt and execution state separately.

## 5. API key and secret handling

There are two credential types:

1. **Workflo project API key** — used by the dashboard to call Workflo. The first UI keeps it in React component memory only; it is not written to localStorage or sessionStorage. Reloading the page requires re-entry.
2. **Provider API key** — belongs to the selected speech provider. It is posted once to the control plane and stored in the project's config_json after encryption using the existing organization DEK / KEK mechanism.

Project-level key storage requires:
- a project linked to an organization;
- an enabled encryption key (MASTER_KEK_HEX in the local development profile, or a KMS-backed KEK provider in production);
- an API key with admin scope to configure or remove a provider secret.

An operator may instead set provider keys as backend environment variables. Environment keys are fallback defaults; they are never returned by the provider-status API.

Never:
- put provider keys in NEXT_PUBLIC_* variables;
- commit real values or .env files;
- send provider keys to the browser SDK as permanent credentials;
- log request headers, raw audio, full transcripts or API keys;
- use a provider-hosted agent as the authority for Workflo QA state.

## 6. Local setup

1. Configure the control plane dependencies from the repository root:

       pip install -e ./packages/workflo-schema
       pip install -e ./packages/workflo-utils
       pip install -e ./packages/sandbox-isolation
       pip install -e ./apps/sandbox-executor
       pip install -e "./apps/control-plane[dev]"

2. Copy .env.example to the control plane's .env (or use the environment loader already used by the deployment) and set:
   - DATABASE_URL
   - DASHBOARD_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
   - one or more optional provider environment keys, or configure project keys through the UI.

3. For project BYOK encryption in local development, generate a random 32-byte key and set MASTER_KEK_HEX to its 64-character hex representation. Keep it outside source control. Production must use the approved KMS-backed KEK provider and the existing fail-closed startup checks.

4. Start the control plane from apps/control-plane:

       uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

5. Set NEXT_PUBLIC_API_URL=http://localhost:8000 for the dashboard and start it:

       cd apps/dashboard
       npm install
       npm run dev

6. Open the dashboard, paste a Workflo project API key with run_tests scope, select the STT/TTS providers, and verify provider readiness. To save project provider keys from the UI, use an admin-scoped key with project BYOK encryption enabled.

7. Allow microphone access in the browser. Choose **Voice**, record a short QA request, edit the transcript, confirm repository/commit/profile, inspect the preview, and click **Start QA run**. Or choose **Text** and enter the command directly.

## 7. Supported first-release command behavior

Examples:
- “Run QA on this repository.”
- “Run QA including security checks.”
- “Run deep regression tests.”
- “Run browser QA.”

The request must resolve to an HTTPS clone URL and a full commit SHA. A branch name such as main is not a pinned execution target; the current resolver asks for the exact SHA rather than guessing. The browser profile also requires an approved application start command and port.

The resolver currently handles QA-run intent and profile selection, not general natural-language chat, repository discovery or free-form agent tool calls. Those require the durable Supervisor/agent runtime and registered capability catalog to be implemented. This first voice assistant is a real speech-to-QA command path, not a claim that the full multi-agent roadmap is complete.

## 8. Operational and production notes

- The browser recording is capped at 25 seconds in this UI. The API limits upload size to 10 MB.
- The initial provider route is request/response turn-based; it is not full-duplex streaming or an always-listening wake-word agent.
- Provider rate limits, supported audio formats and model/voice availability depend on the provider account.
- Workflo's existing run API and runner policies still decide what executes.
- Workflo's documented Firecracker/KVM Gate B remains a production prerequisite for untrusted workload execution. Development sandbox results must not be described as production microVM isolation.
- Test outcomes live inside the receipt and must not be inferred solely from status=completed.
