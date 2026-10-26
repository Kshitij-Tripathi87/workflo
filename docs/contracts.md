# Contracts (packages/crew-contracts)

Strict pydantic v2 models, `extra="forbid"`, a `schema_version` field, JSON Schema export. The orchestrator validates every handoff. A violation fails that stage.

| Contract | Key fields |
|---|---|
| RunInput | run_id, repo_ref, commit, snapshot_sha256, backend, privacy_mode, config (workflo.yaml), requirements_path? |
| SandboxHandle | run_id, backend, app_url (internal), image_digest, network_profile, canary_result, started_at |
| ProjectMap | stack, entry_points[], run_commands, ports, routes[{method,path,source: parsed or inferred}], deps_manifest_hashes |
| RequirementSet | items[{req_id, text, source_file, source_line, priority}] |
| ProbePlan | probes[{probe_id, kind, request, expected, req_id?}] |
| Candidate | candidate_id, probe_id, observed, expected, evidence_refs[], req_id?, origin: baseline or llm |
| Finding | finding_id, fingerprint, status: Confirmed, Flaky or Unconfirmed, confidence, severity, repro_evidence_refs[], control_evidence_ref, req_id? |
| ModelCallRecord | call_id, role, provider, model_id, privacy_mode, tokens_in, tokens_out, prompt_sha256, status |
| ReportDraft | finding_id, explanation, likely_cause_hypothesis, remediation_hint, cited_evidence_ids[] |
| ReportBundle | run_summary, findings[], requirement_statuses[], isolation_proof, model_stage_degraded, provider_provenance[] |
| StageResult | stage, ok, failure_stage?, failure_reason?, duration_ms |
| EventRecord | run_id, seq, ts, stage, kind, payload_hash |

Invariants (tested):
- Confirmed requires >= 2 repro evidence refs and 1 control ref, all present in the manifest.
- ReportDraft.cited_evidence_ids must be a subset of the finding's evidence.
- ModelCallRecord never stores prompt or response bodies.
