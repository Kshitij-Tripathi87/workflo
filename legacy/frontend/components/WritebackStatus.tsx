import React from "react";
import { WritebackRecord } from "../lib/types";

interface WritebackStatusProps {
  record: WritebackRecord | null;
}

export function WritebackStatus({ record }: WritebackStatusProps) {
  if (!record) {
    return <div style={{ color: "#64748b" }}>No resolution recorded yet.</div>;
  }

  const statusColor: Record<string, string> = {
    open: "#64748b",
    triaged: "#3b82f6",
    mitigated: "#eab308",
    fixed: "#22c55e",
    dismissed: "#ef4444",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{
            display: "inline-block",
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: statusColor[record.status] || "#64748b",
          }}
        />
        <span style={{ fontWeight: 600, textTransform: "capitalize" }}>{record.status}</span>
        <span style={{ fontSize: 12, color: "#64748b" }}>
          {new Date(record.created_at).toLocaleString()}
        </span>
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Summary</div>
        <div style={{ color: "#cbd5e1", fontSize: 14 }}>{record.summary}</div>
      </div>

      {record.linked_artifact && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Linked Artifact</div>
          <code style={{ backgroundColor: "#0f172a", padding: "4px 8px", borderRadius: 4, fontSize: 12 }}>
            {record.linked_artifact}
          </code>
        </div>
      )}

      {record.affected_assets.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Affected Assets</div>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>{record.affected_assets.length} assets</div>
        </div>
      )}
    </div>
  );
}