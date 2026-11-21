"use client";

import {
  AlertCircle, Activity, Check, CheckCircle2, ChevronDown, HelpCircle,
  Command, FileText, KeyRound, Loader2, Mic, Play, RefreshCw, Send, Settings2,
  ShieldCheck, Square, Volume2, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const PROVIDERS = ["sarvam", "fish", "elevenlabs"] as const;

type Provider = (typeof PROVIDERS)[number];
type ProviderStatus = {
  provider: Provider;
  configured: boolean;
  speech_to_text: boolean;
  text_to_speech: boolean;
  key_source: "project" | "server" | null;
};
type RunRequest = {
  repo_url: string;
  commit_sha: string;
  probe_groups: string[];
  start_command?: string;
  port?: number;
};
type RunInfo = {
  run_id: string;
  status: string;
  created_at?: string;
  receipt?: Record<string, unknown> | null;
  error?: string | null;
};
type ResolveResponse = {
  status: "ready" | "needs_clarification" | "unsupported";
  message: string;
  clarifications: string[];
  run_request?: RunRequest | null;
  draft?: Record<string, unknown> | null;
};

function providerLabel(provider: Provider) {
  return provider === "sarvam" ? "Sarvam" : provider === "fish" ? "Fish Audio" : "ElevenLabs";
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

async function apiError(response: Response) {
  try {
    const data = await response.json();
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg || "Invalid input").join(", ");
    return data?.message || "Request failed (" + response.status + ").";
  } catch {
    return "Request failed (" + response.status + ").";
  }
}

async function toWav(blob: Blob): Promise<Blob> {
  if (!window.AudioContext) return blob;
  const context = new window.AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const channel = decoded.getChannelData(0);
    const buffer = new ArrayBuffer(44 + channel.length * 2);
    const view = new DataView(buffer);
    const write = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
    };
    write(0, "RIFF");
    view.setUint32(4, 36 + channel.length * 2, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, decoded.sampleRate, true);
    view.setUint32(28, decoded.sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, channel.length * 2, true);
    let offset = 44;
    for (let index = 0; index < channel.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, channel[index]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
    return new Blob([buffer], { type: "audio/wav" });
  } finally {
    await context.close().catch(() => undefined);
  }
}

export default function VoiceWorkspace() {
  const [workfloKey, setWorkfloKey] = useState("");
  const [connected, setConnected] = useState(false);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [sttProvider, setSttProvider] = useState<Provider>("sarvam");
  const [ttsProvider, setTtsProvider] = useState<Provider>("sarvam");
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [command, setCommand] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [commitSha, setCommitSha] = useState("");
  const [probeGroups, setProbeGroups] = useState<string[]>(["test"]);
  const [startCommand, setStartCommand] = useState("");
  const [port, setPort] = useState("3000");
  const [resolved, setResolved] = useState<ResolveResponse | null>(null);
  const [runRequest, setRunRequest] = useState<RunRequest | null>(null);
  const [runInfo, setRunInfo] = useState<RunInfo | null>(null);
  const [activity, setActivity] = useState("Connect a project API key to get started.");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsProvider, setSettingsProvider] = useState<Provider>("sarvam");
  const [providerSecret, setProviderSecret] = useState("");
  const [speaker, setSpeaker] = useState("simran_en_customer");
  const [fishReference, setFishReference] = useState("");
  const [elevenVoiceId, setElevenVoiceId] = useState("");
  const [savingProvider, setSavingProvider] = useState(false);
  const [playing, setPlaying] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recordTimeoutRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const spokenRunRef = useRef<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  const statusByProvider = useMemo(() => {
    const result: Partial<Record<Provider, ProviderStatus>> = {};
    providers.forEach((item) => { result[item.provider] = item; });
    return result;
  }, [providers]);

  const authFetch = useCallback(async (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers || {});
    headers.set("X-Workflo-Key", workfloKey.trim());
    if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(API_BASE + path, { ...init, headers });
    if (!response.ok) throw new Error(await apiError(response));
    return response;
  }, [workfloKey]);

  const refreshProviders = useCallback(async () => {
    const response = await authFetch("/v1/voice/providers");
    const data = await response.json();
    setProviders(data.providers || []);
  }, [authFetch]);

  const connect = async () => {
    setError("");
    setBusy(true);
    try {
      await refreshProviders();
      setConnected(true);
      setActivity("Project connected. Choose a voice provider or type a QA command.");
    } catch (err) {
      setConnected(false);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const toggleProfile = (profile: string) => {
    setProbeGroups((current) => current.includes(profile)
      ? current.filter((value) => value !== profile)
      : [...current, profile]);
  };

  const transcribeRecording = async (recorded: Blob) => {
    setBusy(true);
    setError("");
    setActivity("Transcribing with " + providerLabel(sttProvider) + "…");
    try {
      const wav = await toWav(recorded);
      const form = new FormData();
      form.set("provider", sttProvider);
      form.set("language_code", "unknown");
      form.set("audio", wav, "workflo-voice-command.wav");
      const response = await authFetch("/v1/voice/transcribe", { method: "POST", body: form });
      const result = await response.json();
      setCommand(result.transcript || "");
      setActivity("Transcript ready · " + (result.language_code || "language detected") + ". Review or edit it before resolving.");
    } catch (err) {
      setError(errorText(err));
      setActivity("Transcription failed. You can still type the command.");
    } finally {
      setBusy(false);
    }
  };

  const stopRecording = () => {
    if (recordTimeoutRef.current !== null) {
      window.clearTimeout(recordTimeoutRef.current);
      recordTimeoutRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
  };

  const startRecording = async () => {
    if (!connected) {
      setError("Connect a project API key first.");
      return;
    }
    if (!statusByProvider[sttProvider]?.speech_to_text) {
      setError(providerLabel(sttProvider) + " speech recognition is not configured for this project.");
      setSettingsOpen(true);
      setSettingsProvider(sttProvider);
      return;
    }
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? { mimeType: "audio/webm;codecs=opus" }
        : undefined;
      const recorder = new MediaRecorder(stream, options);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const captured = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setRecording(false);
        if (!captured.size) {
          setError("No audio was captured. Check your microphone and try again.");
          setActivity("Recording ended without audio.");
          return;
        }
        await transcribeRecording(captured);
      };
      recorder.start(250);
      setRecording(true);
      setActivity("Listening… speak your QA request. Recording stops automatically after 25 seconds.");
      recordTimeoutRef.current = window.setTimeout(() => stopRecording(), 25_000);
    } catch (err) {
      setError(errorText(err));
      setActivity("Microphone access is unavailable. Use the text command box instead.");
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };

  const resolveCommand = async () => {
    if (!command.trim()) {
      setError("Write or speak a command first.");
      return;
    }
    if (probeGroups.length === 0) {
      setError("Select at least one QA profile.");
      return;
    }
    setBusy(true);
    setError("");
    setResolved(null);
    setRunRequest(null);
    idempotencyKeyRef.current = null;
    setActivity("Resolving the target and building a typed QA request…");
    try {
      const response = await authFetch("/v1/voice/resolve", {
        method: "POST",
        body: JSON.stringify({
          command: command.trim(),
          repo_url: repoUrl.trim() || null,
          commit_sha: commitSha.trim() || null,
          probe_groups: probeGroups,
          start_command: startCommand.trim() || null,
          port: probeGroups.includes("web") ? Number(port) : null,
        }),
      });
      const result = (await response.json()) as ResolveResponse;
      setResolved(result);
      if (result.status === "ready" && result.run_request) {
        setRunRequest(result.run_request);
        setActivity("QA request is ready. Review the exact repository, commit and profile before starting.");
      } else if (result.status === "needs_clarification") {
        setActivity("More information is required. Nothing has been submitted.");
      } else {
        setActivity(result.message || "This command is not supported by the QA command composer.");
      }
    } catch (err) {
      setError(errorText(err));
      setActivity("Could not resolve the command.");
    } finally {
      setBusy(false);
    }
  };

  const startQaRun = async () => {
    if (!runRequest) return;
    setBusy(true);
    setError("");
    setRunInfo(null);
    setActivity("Submitting the reviewed QA request…");
    spokenRunRef.current = null;
    try {
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = window.crypto.randomUUID();
      }
      const response = await authFetch("/v1/runs", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKeyRef.current },
        body: JSON.stringify(runRequest),
      });
      const data = (await response.json()) as RunInfo;
      setRunInfo(data);
      setActivity("Run " + data.run_id + " submitted. Workflo is tracking its execution state.");
      setRunRequest(null);
    } catch (err) {
      setError(errorText(err));
      setActivity("The QA request was not accepted.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!runInfo?.run_id || !connected || !workfloKey || ["completed", "failed"].includes(runInfo.status)) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await authFetch("/v1/runs/" + encodeURIComponent(runInfo.run_id));
        const result = (await response.json()) as RunInfo;
        if (disposed) return;
        setRunInfo(result);
        if (result.status === "completed") {
          setActivity("Execution completed. Inspect the receipt for the actual test verdict and evidence.");
          return;
        }
        if (result.status === "failed") {
          setActivity("Execution failed. Review the error and run details below.");
          return;
        }
        setActivity("Run " + result.status + ". Waiting for the next status update…");
        timer = window.setTimeout(poll, 2500);
      } catch (err) {
        if (disposed) return;
        setError(errorText(err));
        setActivity("Could not refresh run status. The run may still be active; reconnect and check it again.");
      }
    };
    timer = window.setTimeout(poll, 2000);
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runInfo?.run_id, runInfo?.status, connected, workfloKey, authFetch]);

  const playSpeech = useCallback(async (text: string) => {
    if (!statusByProvider[ttsProvider]?.text_to_speech) {
      setError(providerLabel(ttsProvider) + " speech output is not configured. Select a configured TTS provider or add its voice settings.");
      setSettingsOpen(true);
      setSettingsProvider(ttsProvider);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await authFetch("/v1/voice/speak", {
        method: "POST",
        body: JSON.stringify({ provider: ttsProvider, text, language_code: "en-IN" }),
      });
      const blob = await response.blob();
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = audioUrlRef.current;
        await audioRef.current.play();
        setPlaying(true);
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }, [authFetch, statusByProvider, ttsProvider]);

  useEffect(() => {
    if (!runInfo || !["completed", "failed"].includes(runInfo.status) || mode !== "voice") return;
    if (spokenRunRef.current === runInfo.run_id) return;
    spokenRunRef.current = runInfo.run_id;
    const message = runInfo.status === "completed"
      ? "The QA execution is complete. Workflo has returned a receipt. Open the run details to review the test verdict and evidence."
      : "The QA execution ended with an error. " + (runInfo.error || "Open the run details to inspect the failure.");
    void playSpeech(message);
  }, [runInfo, mode, playSpeech]);

  const saveProvider = async () => {
    if (!providerSecret.trim()) {
      setError("Enter the provider API key first.");
      return;
    }
    setSavingProvider(true);
    setError("");
    try {
      const payload: Record<string, string> = { api_key: providerSecret.trim() };
      if (settingsProvider === "sarvam" && speaker.trim()) payload.speaker = speaker.trim();
      if (settingsProvider === "fish" && fishReference.trim()) payload.reference_id = fishReference.trim();
      if (settingsProvider === "elevenlabs" && elevenVoiceId.trim()) payload.voice_id = elevenVoiceId.trim();
      const response = await authFetch("/v1/voice/providers/" + settingsProvider, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      setProviderSecret("");
      await refreshProviders();
      setActivity(result.warning || providerLabel(settingsProvider) + " credentials encrypted and saved for this project.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSavingProvider(false);
    }
  };

  const removeProvider = async (provider: Provider) => {
    setError("");
    try {
      await authFetch("/v1/voice/providers/" + provider, { method: "DELETE" });
      await refreshProviders();
      setActivity(providerLabel(provider) + " project key removed. Any operator-managed server key remains available.");
    } catch (err) {
      setError(errorText(err));
    }
  };

  useEffect(() => {
    return () => {
      if (recordTimeoutRef.current !== null) window.clearTimeout(recordTimeoutRef.current);
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    };
  }, []);

  const isRunning = Boolean(runInfo && ["queued", "running"].includes(runInfo.status));

  return (
    <main className="voice-page">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={21} /></div>
          <div><div className="brand-name">WORKFLO</div><div className="brand-caption">VOICE QA WORKSPACE</div></div>
        </div>
        <div className="topbar-right">
          <span className="system-status"><span className={"status-dot " + (connected ? "online" : "")} />{connected ? "Project connected" : "Not connected"}</span>
          {connected && <button className="icon-button" onClick={() => void refreshProviders()} aria-label="Refresh voice providers"><RefreshCw size={17} /></button>}
          <button className="icon-button" onClick={() => setSettingsOpen((value) => !value)} aria-label="Voice provider settings" disabled={!connected}><Settings2 size={18} /></button>
        </div>
      </header>

      <section className="welcome-row">
        <div>
          <div className="eyebrow">AUTONOMOUS QUALITY WORKFLOW</div>
          <h1>Give your next task a voice.</h1>
          <p>Speak naturally or write a command. Workflo resolves the target, prepares a QA request and waits for your approval before starting.</p>
        </div>
        <div className="trust-chip"><ShieldCheck size={16} /> Policy-controlled execution</div>
      </section>

      {!connected && (
        <section className="connect-card">
          <div className="connect-icon"><KeyRound size={20} /></div>
          <div className="connect-copy">
            <h2>Connect a project</h2>
            <p>Enter a Workflo project API key with <code>run_tests</code> scope. It remains in this browser tab's memory and is not saved to local storage.</p>
          </div>
          <div className="connect-form">
            <input type="password" value={workfloKey} onChange={(event) => setWorkfloKey(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void connect(); }} placeholder="wf_live_…" autoComplete="off" aria-label="Workflo project API key" />
            <button className="primary-button" onClick={() => void connect()} disabled={busy || !workfloKey.trim()}>
              {busy ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />} Connect
            </button>
          </div>
        </section>
      )}

      {connected && (
        <section className="workspace-grid">
          <div className="main-column">
            <section className="composer-card">
              <div className="card-header">
                <div><div className="eyebrow">COMMAND INPUT</div><h2>What should Workflo do?</h2></div>
                <div className="mode-switch">
                  <button className={mode === "voice" ? "selected" : ""} onClick={() => setMode("voice")}><Mic size={15} /> Voice</button>
                  <button className={mode === "text" ? "selected" : ""} onClick={() => setMode("text")}><Command size={15} /> Text</button>
                </div>
              </div>

              {mode === "voice" ? (
                <div className={"voice-capture " + (recording ? "recording" : "")}>
                  <div className="orb-wrap">
                    <div className="orb-ring ring-one" /><div className="orb-ring ring-two" />
                    <button className="voice-orb" onClick={() => recording ? stopRecording() : void startRecording()} disabled={busy} aria-label={recording ? "Stop recording" : "Start voice recording"}>
                      {recording ? <Square size={20} fill="currentColor" /> : <Mic size={25} />}
                    </button>
                  </div>
                  <div className="voice-instruction">
                    <strong>{recording ? "Listening to your command" : "Tap to speak"}</strong>
                    <span>{recording ? "Tap the square to stop · maximum 25 seconds" : "Your recording is transcribed by the selected provider."}</span>
                  </div>
                  <div className="capture-provider-row">
                    <label>Speech recognition
                      <select value={sttProvider} onChange={(event) => setSttProvider(event.target.value as Provider)}>
                        {PROVIDERS.map((provider) => <option key={provider} value={provider}>{providerLabel(provider)}</option>)}
                      </select>
                    </label>
                    <span className={"provider-ready " + (statusByProvider[sttProvider]?.speech_to_text ? "ready" : "missing")}>
                      {statusByProvider[sttProvider]?.speech_to_text ? <Check size={13} /> : <AlertCircle size={13} />}
                      {statusByProvider[sttProvider]?.speech_to_text ? "Ready" : "Needs API key"}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-entry">
                  <div className="text-entry-label"><Command size={15} /> NATURAL LANGUAGE COMMAND</div>
                  <textarea value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Run QA on the API changes. Include regression and browser checks…" rows={5} />
                  <div className="text-entry-hint">Use the same words you would say. Add or edit the details before resolving.</div>
                </div>
              )}

              {mode === "voice" && (
                <div className="transcript-editor">
                  <div className="text-entry-label"><FileText size={15} /> TRANSCRIPT · REVIEW BEFORE EXECUTION</div>
                  <textarea value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Your transcript will appear here. Edit it before continuing…" rows={3} />
                  <div className="text-entry-hint">Transcription never starts a run automatically.</div>
                </div>
              )}

              <div className="target-fields">
                <div className="section-divider"><span>EXECUTION TARGET</span><i /></div>
                <label className="field-label">Repository HTTPS clone URL
                  <input value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} placeholder="https://github.com/org/repository.git" />
                </label>
                <label className="field-label">Exact commit SHA
                  <input value={commitSha} onChange={(event) => setCommitSha(event.target.value)} placeholder="Full 40 or 64 character commit SHA" spellCheck={false} />
                </label>
                <div className="section-divider"><span>QA PROFILES</span><i /></div>
                <div className="profile-options">
                  {[
                    ["test", "Functional", "Core checks"],
                    ["security", "Security", "Security probes"],
                    ["deep-test", "Deep test", "Expanded coverage"],
                    ["aggressive-test", "Aggressive", "Extended probing"],
                    ["web", "Browser", "Web checks"],
                  ].map(([id, title, subtitle]) => (
                    <label className={"profile-option " + (probeGroups.includes(id) ? "active" : "")} key={id}>
                      <input type="checkbox" checked={probeGroups.includes(id)} onChange={() => toggleProfile(id)} />
                      <span className="profile-check">{probeGroups.includes(id) ? <Check size={12} /> : null}</span>
                      <span><strong>{title}</strong><small>{subtitle}</small></span>
                    </label>
                  ))}
                </div>
                {probeGroups.includes("web") && (
                  <div className="web-fields">
                    <label className="field-label">Application start command
                      <input value={startCommand} onChange={(event) => setStartCommand(event.target.value)} placeholder="npm run start" />
                    </label>
                    <label className="field-label port-field">Port
                      <input type="number" min="1" max="65535" value={port} onChange={(event) => setPort(event.target.value)} />
                    </label>
                  </div>
                )}
              </div>
              <div className="composer-actions">
                <span className="safe-note"><ShieldCheck size={14} /> Review first · no auto-execution</span>
                <button className="primary-button large" onClick={() => void resolveCommand()} disabled={busy || recording || !command.trim()}>
                  {busy ? <Loader2 className="spin" size={17} /> : <Send size={16} />} Resolve command
                </button>
              </div>
            </section>

            {resolved && (
              <section className={"result-card " + (resolved.status === "ready" ? "result-ready" : "result-attention")}>
                <div className="result-title-row">
                  <div className={"result-icon " + (resolved.status === "ready" ? "good" : "attention")}>
                    {resolved.status === "ready" ? <CheckCircle2 size={20} /> : <HelpCircle size={20} />}
                  </div>
                  <div>
                    <div className="eyebrow">{resolved.status === "ready" ? "REQUEST READY FOR REVIEW" : "CLARIFICATION REQUIRED"}</div>
                    <h2>{resolved.message}</h2>
                  </div>
                </div>
                {resolved.clarifications?.length > 0 && <ul className="clarification-list">{resolved.clarifications.map((item) => <li key={item}>{item}</li>)}</ul>}
                {runRequest && (
                  <>
                    <div className="preview-grid">
                      <div><span>Repository</span><strong>{runRequest.repo_url}</strong></div>
                      <div><span>Commit</span><strong className="mono">{runRequest.commit_sha}</strong></div>
                      <div><span>Profiles</span><strong>{runRequest.probe_groups.join(" · ")}</strong></div>
                    </div>
                    <div className="approve-row">
                      <p>Nothing has started yet. Confirm this exact request to submit it to the QA runner.</p>
                      <button className="primary-button large" onClick={() => void startQaRun()} disabled={busy}>
                        {busy ? <Loader2 className="spin" size={16} /> : <Play size={16} fill="currentColor" />} Start QA run
                      </button>
                    </div>
                  </>
                )}
              </section>
            )}

            {runInfo && (
              <section className="run-card">
                <div className="run-heading">
                  <div><div className="eyebrow">LIVE EXECUTION</div><h2>QA run status</h2></div>
                  <span className={"run-status status-" + runInfo.status}>{runInfo.status}</span>
                </div>
                <div className="run-id"><span>Run ID</span><code>{runInfo.run_id}</code></div>
                <div className="run-progress">
                  <div className={"progress-line " + (isRunning ? "active" : "")} />
                  <div className="progress-labels"><span>Submitted</span><span>Executing</span><span>Terminal</span></div>
                </div>
                {runInfo.error && <div className="run-error"><AlertCircle size={15} /> {runInfo.error}</div>}
                {runInfo.receipt && (
                  <details className="receipt-details">
                    <summary><ShieldCheck size={15} /> Signed receipt and test evidence <ChevronDown size={15} /></summary>
                    <pre>{JSON.stringify(runInfo.receipt, null, 2)}</pre>
                  </details>
                )}
                <div className="run-footer">
                  <p>Execution state and QA verdict are different. A completed run means the runner returned a receipt; inspect the receipt for test outcomes.</p>
                  <button className="secondary-button" onClick={() => void playSpeech(runInfo.status === "completed" ? "The QA execution is complete. Workflo returned a receipt. Check the test outcomes and evidence in the run details." : "The QA run status is " + runInfo.status + ". " + (runInfo.error || ""))}>
                    <Volume2 size={15} /> Speak status
                  </button>
                </div>
              </section>
            )}
          </div>

          <aside className="side-column">
            <section className="side-card">
              <div className="side-card-heading"><div className="eyebrow">VOICE ROUTING</div><span className="side-icon"><Activity size={17} /></span></div>
              <h3>Choose the voice stack</h3>
              <p>Speech recognition and speech output can use different providers.</p>
              <label className="field-label compact">Speech-to-text
                <select value={sttProvider} onChange={(event) => setSttProvider(event.target.value as Provider)}>
                  {PROVIDERS.map((provider) => <option key={provider} value={provider}>{providerLabel(provider)}</option>)}
                </select>
              </label>
              <div className="route-status"><span>{statusByProvider[sttProvider]?.speech_to_text ? "Connected" : "Not configured"}</span><span className={statusByProvider[sttProvider]?.speech_to_text ? "status-word-on" : "status-word-off"} /></div>
              <label className="field-label compact">Text-to-speech
                <select value={ttsProvider} onChange={(event) => setTtsProvider(event.target.value as Provider)}>
                  {PROVIDERS.map((provider) => <option key={provider} value={provider}>{providerLabel(provider)}</option>)}
                </select>
              </label>
              <div className="route-status"><span>{statusByProvider[ttsProvider]?.text_to_speech ? "Connected" : "Voice not configured"}</span><span className={statusByProvider[ttsProvider]?.text_to_speech ? "status-word-on" : "status-word-off"} /></div>
              <button className="text-button" onClick={() => setSettingsOpen(true)}><Settings2 size={14} /> Configure provider keys</button>
            </section>

            <section className="side-card">
              <div className="side-card-heading"><div className="eyebrow">TASK PIPELINE</div><span className="side-icon"><Command size={17} /></span></div>
              <div className="pipeline">
                {[
                  ["01", "Capture or type", "Voice / text input"],
                  ["02", "Resolve intent", "Clarify missing details"],
                  ["03", "Review request", "Target + profile preview"],
                  ["04", "Execute QA", "Existing governed run API"],
                  ["05", "Verify result", "Receipt + test evidence"],
                  ["06", "Voice response", "Spoken status summary"],
                ].map(([number, title, detail], index) => (
                  <div className="pipeline-step" key={number}>
                    <span className={"pipeline-number " + (index <= (runInfo ? 4 : resolved ? 2 : command ? 1 : 0) ? "step-active" : "")}>{number}</span>
                    <div><strong>{title}</strong><small>{detail}</small></div>
                  </div>
                ))}
              </div>
            </section>

            <section className="side-card status-card">
              <div className="side-card-heading"><div className="eyebrow">SESSION STATUS</div><span className="side-icon"><ShieldCheck size={17} /></span></div>
              <div className="activity-copy">{activity}</div>
              {error && <div className="inline-error"><AlertCircle size={15} /> {error}</div>}
              <div className="security-footnote"><ShieldCheck size={14} /> Provider secrets never enter the browser response. QA commands require an explicit submit.</div>
            </section>
          </aside>
        </section>
      )}

      {settingsOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}>
          <section className="provider-modal" role="dialog" aria-modal="true" aria-labelledby="provider-modal-title">
            <div className="modal-header">
              <div><div className="eyebrow">SECURE CREDENTIALS</div><h2 id="provider-modal-title">Voice provider settings</h2><p>Project keys are encrypted by the control plane. The input is cleared after saving.</p></div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings"><X size={18} /></button>
            </div>
            <label className="field-label">Provider
              <select value={settingsProvider} onChange={(event) => setSettingsProvider(event.target.value as Provider)}>
                {PROVIDERS.map((provider) => <option key={provider} value={provider}>{providerLabel(provider)}</option>)}
              </select>
            </label>
            <label className="field-label">Provider API key
              <input type="password" value={providerSecret} onChange={(event) => setProviderSecret(event.target.value)} placeholder="Paste API key; not saved in this browser" autoComplete="off" />
            </label>
            {settingsProvider === "sarvam" && <label className="field-label">Sarvam speaker ID<input value={speaker} onChange={(event) => setSpeaker(event.target.value)} placeholder="simran_en_customer" /></label>}
            {settingsProvider === "fish" && <label className="field-label">Fish voice reference ID<input value={fishReference} onChange={(event) => setFishReference(event.target.value)} placeholder="Your Fish voice model reference ID" /></label>}
            {settingsProvider === "elevenlabs" && <label className="field-label">ElevenLabs voice ID<input value={elevenVoiceId} onChange={(event) => setElevenVoiceId(event.target.value)} placeholder="Your ElevenLabs voice ID" /></label>}
            <div className="modal-note"><ShieldCheck size={15} /> Saving needs a Workflo API key with <code>admin</code> scope, an organization-linked project and encrypted credential storage.</div>
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => void removeProvider(settingsProvider)}>Remove project key</button>
              <button className="primary-button" onClick={() => void saveProvider()} disabled={savingProvider || !providerSecret.trim()}>
                {savingProvider ? <Loader2 className="spin" size={15} /> : <Check size={15} />} Save encrypted key
              </button>
            </div>
          </section>
        </div>
      )}

      <audio ref={audioRef} onEnded={() => setPlaying(false)} onError={() => setPlaying(false)} className="audio-hidden" />
      {playing && <div className="audio-playing"><Activity size={14} /> Speaking with {providerLabel(ttsProvider)} <button onClick={() => { audioRef.current?.pause(); setPlaying(false); }}><Square size={12} fill="currentColor" /> Stop</button></div>}
      <footer className="page-footer">Workflo Voice QA · Transcripts are reviewed before execution · Provider API keys remain server-side</footer>
    </main>
  );
}
