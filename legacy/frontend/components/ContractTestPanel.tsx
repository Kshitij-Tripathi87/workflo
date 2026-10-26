"use client";

import React, { useState } from "react";
import { generateContractTest, executeContractTest } from "../lib/api";
import { GeneratedContractTest, ContractExecutionResult } from "../lib/types";

interface ContractTestPanelProps {
  assetUrn: string;
}

export function ContractTestPanel({ assetUrn }: ContractTestPanelProps) {
  const [loading, setLoading] = useState(false);
  const [testSuite, setTestSuite] = useState<GeneratedContractTest | null>(null);
  const [execResult, setExecResult] = useState<ContractExecutionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const generated = await generateContractTest(assetUrn);
      setTestSuite(generated);
    } catch (err: any) {
      setError(err?.message || "Failed to generate contract test suite");
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await executeContractTest(assetUrn);
      setExecResult(res);
    } catch (err: any) {
      setError(err?.message || "Failed to execute contract tests");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: "#0f172a",
      borderRadius: 12,
      border: "1px solid #1e293b",
      padding: 18,
      marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 17, color: "#f8fafc", fontWeight: 600 }}>
            🛡️ Data Contract & Probe Test Generator
          </h3>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#94a3b8" }}>
            Compiles metadata-aware pytest contract tests directly from DataHub schemas and lineage.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleGenerate}
            disabled={loading}
            style={{
              padding: "8px 14px",
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Generating..." : "Generate Pytest Suite"}
          </button>
          <button
            onClick={handleExecute}
            disabled={loading}
            style={{
              padding: "8px 14px",
              background: "#10b981",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            Run Contract Tests
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 10, background: "#7f1d1d", color: "#fca5a5", borderRadius: 6, fontSize: 13, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {execResult && (
        <div style={{
          background: "#1e293b",
          borderRadius: 8,
          padding: 12,
          marginBottom: 14,
          border: `1px solid ${execResult.status === "passed" ? "#059669" : "#dc2626"}`,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: execResult.status === "passed" ? "#34d399" : "#f87171" }}>
              {execResult.status === "passed" ? "✅ All Contract Tests Passed" : "❌ Contract Violations Detected"}
            </span>
            <span style={{ fontSize: 12, color: "#cbd5e1" }}>
              {execResult.passed_tests}/{execResult.total_tests} passed ({execResult.duration_seconds}s)
            </span>
          </div>
          {execResult.receipt_id && (
            <div style={{ fontSize: 12, color: "#38bdf8", fontFamily: "monospace", marginBottom: 6 }}>
              Receipt ID: {execResult.receipt_id}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {execResult.findings.map((f, i) => (
              <div key={i} style={{ fontSize: 12, display: "flex", justifyContent: "space-between", color: "#cbd5e1" }}>
                <span>• {f.test}</span>
                <span style={{ color: f.status === "PASSED" ? "#34d399" : f.status === "FAILED" ? "#f87171" : "#fbbf24" }}>
                  {f.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {testSuite && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#cbd5e1" }}>
              Generated Pytest Module ({testSuite.dataset_name})
            </span>
            <span style={{ fontSize: 12, background: "#334155", padding: "2px 8px", borderRadius: 4, color: "#38bdf8" }}>
              SOC 2: {testSuite.soc2_controls.join(", ")} | Score: {testSuite.integrity_score}%
            </span>
          </div>
          <pre style={{
            background: "#020617",
            padding: 12,
            borderRadius: 6,
            fontSize: 12,
            fontFamily: "monospace",
            color: "#e2e8f0",
            overflowX: "auto",
            maxHeight: 240,
            border: "1px solid #1e293b",
          }}>
            <code>{testSuite.test_code}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
