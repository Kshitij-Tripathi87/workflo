"use client";

/**
 * Toast — small notification banner that surfaces backend errors with
 * actionable hints. Powered by the ErrorMapper in lib/errorMapper.ts.
 */

import { useEffect, useState } from "react";

export type ToastKind = "error" | "warn" | "info" | "success";

export interface ToastPayload {
  kind: ToastKind;
  title: string;
  message: string;
  hint?: string;
}

const KIND_COLOR: Record<ToastKind, { bg: string; border: string; text: string }> = {
  error: { bg: "rgba(239, 68, 68, 0.12)", border: "#ef4444", text: "#fca5a5" },
  warn: { bg: "rgba(245, 158, 11, 0.12)", border: "#f59e0b", text: "#fcd34d" },
  info: { bg: "rgba(59, 130, 246, 0.12)", border: "#3b82f6", text: "#93c5fd" },
  success: { bg: "rgba(34, 197, 94, 0.12)", border: "#22c55e", text: "#86efac" },
};

export function Toast({ payload, onDismiss }: { payload: ToastPayload; onDismiss: () => void }) {
  const [closing, setClosing] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setClosing(true), 4500);
    const closeTimer = setTimeout(onDismiss, 5000);
    return () => {
      clearTimeout(timer);
      clearTimeout(closeTimer);
    };
  }, [onDismiss]);

  const cfg = KIND_COLOR[payload.kind];

  return (
    <div
      role="alert"
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
        maxWidth: 420,
        padding: "14px 16px",
        borderRadius: 12,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        boxShadow: `0 8px 32px ${cfg.border}55`,
        opacity: closing ? 0 : 1,
        transform: closing ? "translateY(20px)" : "translateY(0)",
        transition: "opacity 300ms ease, transform 300ms ease",
        color: "#e2e8f0",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <strong style={{ color: cfg.text, fontSize: 14 }}>{payload.title}</strong>
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          style={{
            background: "transparent",
            border: "none",
            color: "#94a3b8",
            cursor: "pointer",
            fontSize: 16,
          }}
        >
          ×
       </button>
    </div>
      <div style={{ fontSize: 13, color: "#cbd5e1" }}>{payload.message}</div>
      {payload.hint && (
        <div
          style={{
            marginTop: 8,
            fontSize: 12,
            color: "#94a3b8",
            background: "rgba(15, 23, 42, 0.6)",
            padding: "6px 10px",
            borderRadius: 6,
            borderLeft: `3px solid ${cfg.border}`,
          }}
        >
          <strong style={{ color: cfg.text }}>Hint:</strong>
          {payload.hint}
      </div>
      )}
  </div>
  );
}
