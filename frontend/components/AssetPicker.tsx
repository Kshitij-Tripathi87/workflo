import React, { useState, useMemo } from "react";
import { AssetNode } from "../lib/types";

interface AssetPickerProps {
  assets: AssetNode[];
  selectedUrn: string;
  onChange: (urn: string) => void;
}

export function AssetPicker({ assets, selectedUrn, onChange }: AssetPickerProps) {
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter) return assets;
    const f = filter.toLowerCase();
    return assets.filter(
      (a) => a.name.toLowerCase().includes(f) || a.urn.toLowerCase().includes(f)
    );
  }, [filter, assets]);

  return (
    <div>
      <input
        type="text"
        placeholder="Search assets..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #334155", backgroundColor: "#0f172a", color: "#fff" }}
      />
      {filtered.length === 0 ? (
        <div
          style={{
            marginTop: 8,
            padding: 10,
            borderRadius: 8,
            border: "1px dashed #334155",
            color: "#94a3b8",
            fontSize: 13,
            textAlign: "center",
          }}
        >
          No assets match "{filter}".{" "}
          <button
            type="button"
            onClick={() => setFilter("")}
            style={{
              padding: "2px 8px",
              borderRadius: 4,
              border: "1px solid #475569",
              backgroundColor: "transparent",
              color: "#cbd5e1",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Clear
         </button>
        </div>
      ) : (
        <select
          value={selectedUrn}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: "100%",
            padding: 10,
            borderRadius: 8,
            marginTop: 8,
            backgroundColor: "#1e293b",
            color: "#fff",
            border: "1px solid #334155",
          }}
        >
          {filtered.map((a) => (
            <option key={a.urn} value={a.urn}>
              {a.name} ({a.kind})
           </option>
          ))}
       </select>
      )}
   </div>
  );
}
