"use client";

/**
 * PolicyTweaker — interactive policy editor with real-time verdict flip.
 *
 * Adjusts `max_severity` / `max_blast_radius` sliders and immediately
 * calls POST /policy/validate to show the verdict changing in real
 * time, without firing a full future-search.
 */

import { useEffect, useState } from "react";

import { Skeleton } from "./Skeleton";

export interface Policy {
  name: string;
  max_severity?: number;
  max_blast_radius?: number;
  require_owner?: boolean;
  action: "pass" | "warn" | "block";
}

interface PolicyTweakerProps {
  initialPolicies: Policy[];
  severity: number;
  blastRadius: number;
  hasOwner: boolean;
  onVerdict?: (verdict: "pass" | "warn" | "block") => void;
}

const VERDICT_COLOR: Record<string, string> = {
  pass: "#22c55e",
  warn: "#f59e0b",
  block: "#ef4444",
};

export function PolicyTweaker({
  initialPolicies,
  severity,
  blastRadius,
  hasOwner,
  onVerdict,
}: PolicyTweakerProps) {
  const [policies, setPolicies] = useState<Policy[]>(initialPolicies);
  const [verdict, setVerdict] = useState<"pass" | "warn" | "block" | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch("/policy/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            policies,
            severity,
            blast_radius: blastRadius,
            has_owner: hasOwner,
          }),
        });
        if (res.ok) {
          const body = await res.json();
          setVerdict(body.verdict);
          onVerdict?.(body.verdict);
        }
      } catch {
        // Silent: tweak loop is best-effort
      } finally {
        setLoading(false);
      }
    }, 250); // Debounce 250ms
    return () => clearTimeout(t);
  }, [policies, severity, blastRadius, hasOwner, onVerdict]);

  const updatePolicy = (idx: number, patch: Partial<Policy>) => {
    setPolicies((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

  return (
    <div
      style={{
        background: "rgba(15, 23, 42, 0.4)",
        border: "1px solid rgba(148, 163, 184, 0.18)",
        borderRadius: 12,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 12, color: "#94a3b8", textTransform: "uppercase" }}>
            Live verdict
        </div>
          {loading || !verdict ? (
            <Skeleton width={120} height={36} style={{ marginTop: 4 }} />
          ) : (
            <div
              style={{
                fontSize: 32,
                fontWeight: 800,
                color: VERDICT_COLOR[verdict],
                letterSpacing: 2,
              }}
            >
              {verdict.toUpperCase()}
          </div>
          )}
      </div>
        <span style={{ fontSize: 11, color: "#64748b" }}>Auto-refresh 250ms</span>
   </div>

      {policies.map((policy, idx) => (
        <div
          key={idx}
          style={{
            padding: 12,
            background: "rgba(15, 23, 42, 0.6)",
            borderRadius: 8,
            border: "1px solid rgba(148, 163, 184, 0.12)",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 8 }}>{policy.name</div>

          {policy.max_severity !== undefined && (
            <SliderRow
              label="Max severity"
              value={policy.max_severity}
              min={0}
              max={100}
              onChange={(v) => updatePolicy(idx, { max_severity: v })}
            />
          )}

          {policy.max_blast_radius !== undefined && (
            <SliderRow
              label="Max blast radius"
              value={policy.max_blast_radius}
              min={0}
              max={50}
              onChange={(v) => updatePolicy(idx, { max_blast_radius: v })}
            />
          )}

          <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#94a3b8" }}>Action</span>
            <select
              value={policy.action}
              onChange={(e) =>
                updatePolicy(idx, { action: e.target.value as Policy["action"] })
              }
              style={{
                background: "rgba(15, 23, 42, 0.8)",
                border: "1px solid rgba(148, 163, 184, 0.3)",
                color: "#e2e8f0",
                padding: "4px 8px",
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              <option value="pass">pass</option>
              <option value="warn">warn</option>
              <option value="block">block</option>
           </select>
        </div>
      </div>
      ))}
 </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span style={{ color: "#94a3b8" }}>{label</span>
        <span style={{ color: "#e2e8f0", fontWeight: 600 }}>{value</span>
  </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "#3b82f6" }}
      />
  </div>
  );
}
