import React from "react";
import { ArtifactDraft } from "../lib/types";

interface ArtifactPreviewProps {
  artifact: ArtifactDraft | null;
}

export function ArtifactPreview({ artifact }: ArtifactPreviewProps) {
  if (!artifact) {
    return <div style={{ color: "#64748b" }}>Generate a recommendation to see the artifact.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontWeight: 600 }}>{artifact.title}</span>
        <code style={{ backgroundColor: "#1e293b", padding: "4px 8px", borderRadius: 4, fontSize: 12 }}>
          {artifact.artifact_type}
        </code>
      </div>

      <div style={{ position: "relative" }}>
        <pre
          style={{
            backgroundColor: "#0f172a",
            padding: 16,
            borderRadius: 8,
            fontSize: 12,
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 400,
          }}
        >
          {artifact.body}
        </pre>
      </div>

      <button
        onClick={() => navigator.clipboard.writeText(artifact.body)}
        style={{
          padding: "10px 16px",
          borderRadius: 8,
          backgroundColor: "#334155",
          color: "#fff",
          border: "none",
          cursor: "pointer",
          fontWeight: 500,
        }}
      >
        Copy to Clipboard
      </button>
    </div>
  );
}