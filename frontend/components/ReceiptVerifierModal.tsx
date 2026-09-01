"use client";

import React, { useState } from "react";
import { verifyReceipt } from "../lib/api";
import { ReceiptVerificationResponse, SignedReceipt } from "../lib/types";

interface ReceiptVerifierModalProps {
  receipt?: SignedReceipt | null;
  onClose?: () => void;
}

export function ReceiptVerifierModal({ receipt, onClose }: ReceiptVerifierModalProps) {
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<ReceiptVerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!receipt) return null;

  const handleVerify = async () => {
    setVerifying(true);
    setError(null);
    try {
      const res = await verifyReceipt(receipt);
      setResult(res);
    } catch (err: any) {
      setError(err?.message || "Verification failed");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div style={{
      background: "#0b1329",
      border: "1px solid #1e293b",
      borderRadius: 12,
      padding: 16,
      marginTop: 14,
      marginBottom: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={{ margin: 0, fontSize: 15, color: "#38bdf8", fontWeight: 600 }}>
          🔒 Cryptographic Receipt & Proof
        </h4>
        <button
          onClick={handleVerify}
          disabled={verifying}
          style={{
            padding: "6px 12px",
            background: "#6366f1",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 600,
            cursor: verifying ? "not-allowed" : "pointer",
          }}
        >
          {verifying ? "Verifying..." : "Verify Cryptographic Signature"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12, color: "#94a3b8", marginBottom: 12 }}>
        <div>
          <strong style={{ color: "#cbd5e1" }}>Receipt ID:</strong>{" "}
          <span style={{ fontFamily: "monospace", color: "#38bdf8" }}>{receipt.receipt_id}</span>
        </div>
        <div>
          <strong style={{ color: "#cbd5e1" }}>Action:</strong> {receipt.action_type}
        </div>
        <div>
          <strong style={{ color: "#cbd5e1" }}>Fingerprint:</strong>{" "}
          <span style={{ fontFamily: "monospace" }}>{receipt.public_key_fingerprint}</span>
        </div>
        <div>
          <strong style={{ color: "#cbd5e1" }}>Teardown Proof:</strong>{" "}
          <span style={{ color: "#34d399" }}>
            {receipt.teardown_proof?.filesystem_wipe_method || "tmpfs_umount"} (Wiped)
          </span>
        </div>
      </div>

      {result && (
        <div style={{
          padding: 10,
          background: result.is_valid ? "#064e3b" : "#7f1d1d",
          border: `1px solid ${result.is_valid ? "#059669" : "#dc2626"}`,
          borderRadius: 6,
          fontSize: 13,
          color: "#f8fafc",
        }}>
          <strong>{result.is_valid ? "✅ SIGNATURE VALID" : "❌ TAMPER DETECTED"}:</strong> {result.message}
          <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 4 }}>
            Signer Digest: {result.signer_fingerprint} | Verified at: {result.verified_at}
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding: 8, background: "#7f1d1d", color: "#fca5a5", borderRadius: 6, fontSize: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
