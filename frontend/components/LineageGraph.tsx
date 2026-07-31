import React from "react";
import { AssetNode, GraphEdge } from "../lib/types";

interface LineageGraphProps {
  node: AssetNode | null;
  edges: GraphEdge[];
  allNodes: Record<string, AssetNode>;
}

export function LineageGraph({ node, edges, allNodes }: LineageGraphProps) {
  if (!node) {
    return <div style={{ color: "#64748b" }}>Select an asset to view lineage.</div>;
  }

  const upstream = node.upstream.filter((u) => allNodes[u]);
  const downstream = node.downstream.filter((d) => allNodes[d]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {upstream.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 8, color: "#94a3b8" }}>Upstream</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {upstream.map((urn) => {
              const n = allNodes[urn];
              return (
                <div
                  key={urn}
                  style={{
                    padding: "8px 12px",
                    backgroundColor: "#1e293b",
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{n.name}</span>
                  <span style={{ color: "#64748b", marginLeft: 8 }}>({n.kind})</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ textAlign: "center", color: "#475569", fontSize: 20 }}>
        <strong>{node.name}</strong>
      </div>

      {downstream.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 8, color: "#94a3b8" }}>Downstream</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {downstream.map((urn) => {
              const n = allNodes[urn];
              return (
                <div
                  key={urn}
                  style={{
                    padding: "8px 12px",
                    backgroundColor: "#1e293b",
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{n.name}</span>
                  <span style={{ color: "#64748b", marginLeft: 8 }}>({n.kind})</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {upstream.length === 0 && downstream.length === 0 && (
        <div style={{ color: "#64748b", textAlign: "center" }}>No lineage connections found.</div>
      )}
    </div>
  );
}