"use client";

/**
 * useOptimisticWriteback — flips the writeback status to "processing"
 * immediately when called, then transitions to "triaged" or "failed"
 * when the API call resolves. Keeps the UI snappy even on slow links.
 */

import { useState, useCallback } from "react";
import { writebackResolution, CortexApiError } from "./api";
import type { WritebackRecord, ImpactReport, Recommendation, ArtifactDraft } from "./types";

export type WritebackStatus = "idle" | "processing" | "triaged" | "failed";

export function useOptimisticWriteback() {
  const [status, setStatus] = useState<WritebackStatus>("idle");
  const [record, setRecord] = useState<WritebackRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (
      assetUrn: string,
      impact: ImpactReport,
      recommendation: Recommendation,
      artifact?: ArtifactDraft,
    ): Promise<WritebackRecord | null> => {
      setStatus("processing");
      setError(null);

      const optimisticRecord: WritebackRecord = {
        record_id: `optimistic-${Date.now()}`,
        asset_urn: assetUrn,
        // "open" is the backend's status for a freshly recorded resolution.
        // The optimistic UI state ("processing") lives in `status` below —
        // the record itself must carry a status the API can round-trip.
        status: "open",
        summary: "Recording resolution...",
        linked_artifact: artifact ? artifact.artifact_id : null,
        affected_assets: [],
        created_by: "user",
        created_at: new Date().toISOString(),
      };
      setRecord(optimisticRecord);

      try {
        const result = await writebackResolution(assetUrn, impact, recommendation, artifact);
        setStatus("triaged");
        setRecord(result);
        return result;
      } catch (e) {
        setStatus("failed");
        if (e instanceof CortexApiError) {
          setError(typeof e.body === "string" ? e.body : e.body?.message || e.message);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError("Unknown error");
        }
        return null;
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setStatus("idle");
    setRecord(null);
    setError(null);
  }, []);

  return { status, record, error, submit, reset };
}
