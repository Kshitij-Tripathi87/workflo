import React from "react";

interface GraphSummaryProps {
  nodeCount: number;
  edgeCount: number;
  downstreamCount: number;
  criticalCount: number;
}

export function GraphSummary({ nodeCount, edgeCount, downstreamCount, criticalCount }: GraphSummaryProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
      <div style={{ padding: 12, backgroundColor: "#1e293b", borderRadius: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{nodeCount}</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Nodes</div>
      </div>
      <div style={{ padding: 12, backgroundColor: "#1e293b", borderRadius: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{edgeCount}</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Edges</div>
      </div>
      <div style={{ padding: 12, backgroundColor: "#1e293b", borderRadius: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{downstreamCount}</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Downstream</div>
      </div>
      <div style={{ padding: 12, backgroundColor: "#1e293b", borderRadius: 8 }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: "#ef4444" }}>{criticalCount}</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Critical</div>
      </div>
    </div>
  );
}