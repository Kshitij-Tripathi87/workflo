"use client";

/**
 * VerdictCard — the most prominent UI element.
 *
 * Shows pass/warn/block with high-contrast colors, severity score, and
 * blast radius. This is what a user opens the page to see; everything
 * else (impact, recommendations, lineage) is supporting evidence.
 */

import { ReactNode } from "react";

export type Verdict = "pass" | "warn" | "block";

const VERDICT_CONFIG: Record<
  Verdict,
  { label: string; bg: string; border: string; text: string; emoji: string; tagline: string }
> = {
  pass: {
    label: "PASS",
    bg: "rgba(34, 197, 94, 0.12)",
    border: "#22c55e",
    text: "#4ade80",
    emoji: "✓",
    tagline: "Safe to merge",
  },
  warn: {
    label: "WARN",
    bg: "rgba(245, 158, 11, 0.12)",
    border: "#f59e0b",
    text: "#fbbf24",
    emoji: "!",
    tagline: "Review before merging",
  },
  block: {
    label: "BLOCK",
    bg: "rgba(239, 68, 68, 0.14)",
    border: "#ef4444",
    text: "#f87171",
    emoji: "⛔",
    tagline: "Cannot merge",
  },
};

export interface VerdictCardProps {
  verdict: Verdict | null;
  assetUrn?: string;
  severity?: number;
  blastRadius?: number;
  recommendedAction?: string;
  loading?: boolean;
  children?: ReactNode;
}

export function VerdictCard({
  verdict,
  assetUrn,
  severity,
  blastRadius,
  recommendedAction,
  loading = false,
  children,
}: VerdictCardProps) {
  if (loading || !verdict) {
    return (
      <div
        style={{
          padding: "32px 28px",
          borderRadius: 16,
          background: "rgba(148, 163, 184, 0.06)",
          border: "1px solid rgba(148, 163, 184, 0.18)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
        data-testid="verdict-card-loading"
      >
        <Skeleton width={120} height={20} />
        <Skeleton width={220} height={56} />
        <Skeleton width={180} height={16} />
     </div>
    );
  }

  const cfg = VERDICT_CONFIG[verdict];

  return (
    <div
      style={{
        padding: "32px 28px",
        borderRadius: 16,
        background: cfg.bg,
        border: `2px solid ${cfg.border}`,
        boxShadow: `0 0 24px ${cfg.border}33`,
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
      data-testid={`verdict-card-${verdict}`}
      aria-live="polite"
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div
            style={{
              fontSize: 14,
              color: "#94a3b8",
              letterSpacing: 1.2,
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Cortex Autopilot Verdict
         </div>
          <div
            style={{
              fontSize: 56,
              fontWeight: 800,
              color: cfg.text,
              letterSpacing: 2,
              lineHeight: 1,
            }}
          >
            {cfg.emoji} {cfg.label}
         </div>
          <div
            style={{
              marginTop: 8,
              color: "#cbd5e1",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            {cfg.tagline}
         </div>
       </div>

        <div style={{ textAlign: "right" }}>
          {typeof severity === "number" && (
            <Metric label="Severity" value={`${severity}/100`} />
          )}
          {typeof blastRadius === "number" && (
            <Metric
              label="Blast Radius"
              value={`${blastRadius} downstream`}
            />
          )}
       </div>
     </div>

      {assetUrn && (
        <div
          style={{
            fontSize: 12,
            color: "#94a3b8",
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            background: "rgba(15, 23, 42, 0.5)",
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid rgba(148, 163, 184, 0.2)",
            overflowX: "auto",
          }}
        >
          {assetUrn}
       </div>
      )}

      {recommendedAction && (
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            fontSize: 13,
            color: "#e2e8f0",
          }}
        >
          <span style={{ color: "#94a3b8" }}>Recommended action</span>
          <code
            style={{
              padding: "3px 10px",
              background: "rgba(15, 23, 42, 0.6)",
              borderRadius: 6,
              fontSize: 12,
              color: cfg.text,
            }}
          >
            {recommendedAction}
         </code>
       </div>
      )}

      {children}
   </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>
        {label}
     </div>
      <div style={{ fontSize: 18, color: "#e2e8f0", fontWeight: 600 }}>{value</div>
   </div>
  );
}

function Skeleton({ width, height }: { width: number | string; height: number }) {
  return (
    <div
      style={{
        width,
        height,
        background: "rgba(148, 163, 184, 0.18)",
        borderRadius: 8,
        animation: "pulse 1.4s ease-in-out infinite",
      }}
    />
  );
}
