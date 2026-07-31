"use client";

import { FuturePlan } from "../lib/types";

interface FutureSearchPanelProps {
  plan: FuturePlan | null;
  onRun: () => void;
  loading?: boolean;
}

function SeverityBar({ value, label }: { value: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  const color = clamped <= 25 ? "#22c55e" : clamped <= 50 ? "#eab308" : clamped <= 75 ? "#f97316" : "#ef4444";
  // Enforce a minimum visible width for very-low values so the bar is
  // never an invisible sliver (e.g., predicted_effort of 5).
  const widthPct = Math.max(clamped, 3);
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span>{label</span>
        <span>{clamped}/100</span>
     </div>
      <div style={{ height: 6, backgroundColor: "#1e293b", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${widthPct}%`, height: "100%", backgroundColor: color }} />
     </div>
   </div>
  );
}

export function FutureSearchPanel({ plan, onRun, loading }: FutureSearchPanelProps) {
  return (
    <section style={{
      border: "1px solid #23304f",
      borderRadius: 16,
      padding: 16,
      background: "#11182b",
      marginBottom: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Future Search</h2>
        <button
          onClick={onRun}
          disabled={loading}
          style={{
            padding: "10px 16px",
            borderRadius: 8,
            backgroundColor: loading ? "#475569" : "#8b5cf6",
            color: "#fff",
            border: "none",
            fontWeight: 600,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Searching..." : "Run Future Search"}
        </button>
      </div>

      {!plan ? (
        <div style={{ color: "#94a3b8" }}>
          <p>Generate and rank multiple plausible futures for this asset</p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Evaluates {loading ? "..." : "up to 6 candidate scenarios"} across risk, effort, and benefit dimensions.
        </p>
      </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Ranked Choice */}
          <div style={{ padding: 16, backgroundColor: "#1e293b", borderRadius: 12, border: "1px solid #334155" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 20 }}>🎯</span>
              <h3 style={{ margin: 0, fontSize: 16 }}>Recommended Action</h3>
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#a78bfa", marginBottom: 4 }}>
              {plan.ranked_choice.scenario_type.replace(/_/g, " ").toUpperCase()}
            </div>
            <p style={{ color: "#94a3b8", fontSize: 13, margin: "8px 0" }}>{plan.rationale}</p>

            <div style={{ marginTop: 12 }}>
              <SeverityBar value={plan.ranked_choice.predicted_severity} label="Predicted Severity" />
              <SeverityBar value={plan.ranked_choice.predicted_effort} label="Engineering Effort" />
              <SeverityBar value={plan.ranked_choice.predicted_benefit} label="Expected Benefit" />
            </div>

            <div style={{ marginTop: 12, padding: 12, backgroundColor: "#0f172a", borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 4 }}>Confidence</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{(plan.ranked_choice.confidence * 100).toFixed(0)}%</div>
            </div>
          </div>

          {/* Explanation */}
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Why This Was Chosen</h3>
            <ul style={{ margin: 0, paddingLeft: 20, color: "#cbd5e1", fontSize: 13 }}>
              {plan.explanation.map((line, idx) => (
                <li key={idx} style={{ marginBottom: 4 }}>{line}</li>
              ))}
            </ul>
          </div>

          {/* All Candidates */}
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>All Evaluated Futures</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
              {plan.candidates.map((c) => (
                <div
                  key={c.future_id}
                  style={{
                    padding: 12,
                    backgroundColor: c.future_id === plan.ranked_choice.future_id ? "#1e293b" : "#0f172a",
                    borderRadius: 8,
                    border: c.future_id === plan.ranked_choice.future_id ? "1px solid #8b5cf6" : "1px solid #334155",
                    fontSize: 12,
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 4, textTransform: "capitalize" }}>
                    {c.scenario_type.replace(/_/g, " ")}
                  </div>
                  <div style={{ color: "#94a3b8", fontSize: 11 }}>
                    <div>Severity: {c.predicted_severity}</div>
                    <div>Effort: {c.predicted_effort}</div>
                    <div>Benefit: {c.predicted_benefit}</div>
                    <div>Confidence: {(c.confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}