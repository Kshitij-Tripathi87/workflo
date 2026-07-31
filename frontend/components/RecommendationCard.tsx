import React from "react";
import { Recommendation } from "../lib/types";
import { SeverityBadge } from "./SeverityBadge";

interface RecommendationCardProps {
  recommendation: Recommendation | null;
}

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  if (!recommendation) {
    return <div style={{ color: "#64748b" }}>No recommendation generated yet.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <SeverityBadge severity={recommendation.risk} />
        <span style={{ fontSize: 14, color: "#94a3b8" }}>Confidence: {(recommendation.confidence * 100).toFixed(0)}%</span>
      </div>

      <div>
        <div style={{ fontWeight: 600, fontSize: 16 }}>{recommendation.title}</div>
        <div style={{ color: "#94a3b8", marginTop: 4 }}>{recommendation.rationale}</div>
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Action Type</div>
        <code style={{ backgroundColor: "#0f172a", padding: "4px 8px", borderRadius: 4, fontSize: 12 }}>
          {recommendation.action_type}
        </code>
      </div>

      {recommendation.fallback_action && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Fallback Action</div>
          <code style={{ backgroundColor: "#0f172a", padding: "4px 8px", borderRadius: 4, fontSize: 12 }}>
            {recommendation.fallback_action}
          </code>
        </div>
      )}
    </div>
  );
}