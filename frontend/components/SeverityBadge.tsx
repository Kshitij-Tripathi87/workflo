import React from "react";
import { Severity } from "../lib/types";

const colorMap: Record<Severity, string> = {
  low: "#22c55e",
  medium: "#eab308",
  high: "#f97316",
  critical: "#ef4444",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: 999,
        backgroundColor: colorMap[severity],
        color: severity === "medium" ? "#000" : "#fff",
        fontSize: 12,
        fontWeight: 600,
        textTransform: "uppercase",
      }}
    >
      {severity}
    </span>
  );
}