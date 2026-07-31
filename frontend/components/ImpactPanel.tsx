import React from "react";
import { ImpactReport } from "../lib/types";
import { SeverityBadge } from "./SeverityBadge";

interface ImpactPanelProps {
  impact: ImpactReport | null;
}

export function ImpactPanel({ impact }: ImpactPanelProps) {
  if (!impact) {
    return <div style={{ color: "#64748b" }}>Run a scenario to see impact analysis.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <SeverityBadge severity={impact.severity} />
        <span style={{ fontSize: 14, color: "#94a3b8" }}>Confidence: {(impact.confidence * 100).toFixed(0)}%</span>
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Explanation</div>
        <ul style={{ margin: 0, paddingLeft: 20, color: "#cbd5e1" }}>
          {impact.explanation.map((e, i) => (
            <li key={i} style={{ marginBottom: 4 }}>{e}</li>
          ))}
        </ul>
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Affected Assets ({impact.affected_assets.length})</div>
        {impact.affected_assets.length === 0 ? (
          <div style={{ color: "#64748b" }}>No downstream assets affected.</div>
        ) : (
          <pre style={{ backgroundColor: "#0f172a", padding: 12, borderRadius: 8, fontSize: 12, overflow: "auto" }}>
            {JSON.stringify(impact.affected_assets, null, 2)}
          </pre>
        )}
      </div>

      {impact.affected_dashboards.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Affected Dashboards</div>
          <pre style={{ backgroundColor: "#0f172a", padding: 12, borderRadius: 8, fontSize: 12 }}>
            {JSON.stringify(impact.affected_dashboards, null, 2)}
          </pre>
        </div>
      )}

      {impact.affected_models.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Affected ML Models</div>
          <pre style={{ backgroundColor: "#0f172a", padding: 12, borderRadius: 8, fontSize: 12 }}>
            {JSON.stringify(impact.affected_models, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}