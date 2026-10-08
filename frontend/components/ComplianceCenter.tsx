"use client";

import React, { useEffect, useState } from "react";
import { fetchComplianceReport } from "../lib/api";
import { ComplianceReport } from "../lib/types";

export function ComplianceCenter() {
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchComplianceReport();
      setReport(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load compliance report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  return (
    <div style={{
      background: "#0f172a",
      borderRadius: 12,
      border: "1px solid #1e293b",
      padding: 18,
      marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 17, color: "#f8fafc", fontWeight: 600 }}>
            🏛️ SOC 2 Compliance & Audit Readiness Center
          </h3>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#94a3b8" }}>
            Continuous verification against AICPA Trust Services Criteria (CC6.1 & CC7.2).
          </p>
        </div>
        <button
          onClick={loadReport}
          disabled={loading}
          style={{
            padding: "8px 14px",
            background: "#6366f1",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 600,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Auditing..." : "Refresh Audit Report"}
        </button>
      </div>

      {error && (
        <div style={{ padding: 10, background: "#7f1d1d", color: "#fca5a5", borderRadius: 6, fontSize: 13, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {report && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div style={{ background: "#1e293b", padding: 12, borderRadius: 8, textAlign: "center" }}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Overall Score</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: report.overall_compliance_score >= 80 ? "#34d399" : "#f59e0b" }}>
                {report.overall_compliance_score}%
              </div>
            </div>
            <div style={{ background: "#1e293b", padding: 12, borderRadius: 8, textAlign: "center" }}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Audited Assets</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#38bdf8" }}>
                {report.total_assets}
              </div>
            </div>
            <div style={{ background: "#1e293b", padding: 12, borderRadius: 8, textAlign: "center" }}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Receipt Coverage</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#a855f7" }}>
                {report.cryptographic_receipt_coverage_pct}%
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Object.entries(report.controls).map(([key, ctrl]) => (
              <div key={key} style={{
                background: "#1e293b",
                borderRadius: 8,
                padding: 12,
                border: `1px solid ${ctrl.status === "compliant" ? "#059669" : "#d97706"}`,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div>
                    <strong style={{ color: "#f8fafc", fontSize: 14 }}>{ctrl.control_id}: {ctrl.name}</strong>
                    <span style={{
                      marginLeft: 8,
                      fontSize: 11,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: ctrl.status === "compliant" ? "#064e3b" : "#78350f",
                      color: ctrl.status === "compliant" ? "#34d399" : "#fbbf24",
                    }}>
                      {ctrl.status.toUpperCase()} ({ctrl.score}%)
                    </span>
                  </div>
                </div>
                <p style={{ margin: "0 0 6px", fontSize: 12, color: "#cbd5e1" }}>{ctrl.description}</p>
                {ctrl.violating_assets.length > 0 && (
                  <div style={{ fontSize: 12, color: "#f87171", marginBottom: 4 }}>
                    ⚠️ Violating Assets: {ctrl.violating_assets.join(", ")}
                  </div>
                )}
                {ctrl.recommendations.length > 0 && (
                  <div style={{ fontSize: 12, color: "#38bdf8" }}>
                    💡 Recommendation: {ctrl.recommendations.join(" ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
