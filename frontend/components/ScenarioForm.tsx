import React, { useState } from "react";
import { ScenarioRequest } from "../lib/types";

interface ScenarioFormProps {
  assetUrn: string;
  assetName: string;
  onSubmit: (request: ScenarioRequest) => void;
  loading?: boolean;
}

export function ScenarioForm({ assetUrn, assetName, onSubmit, loading }: ScenarioFormProps) {
  const [scenarioType, setScenarioType] = useState("schema_remove");
  const [removedField, setRemovedField] = useState("");
  const [oldName, setOldName] = useState("");
  const [newName, setNewName] = useState("");

  if (!assetUrn) {
    return (
      <div style={{ color: "#94a3b8", fontSize: 13 }}>
        Select an asset before running a scenario.
     </div>
    );
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    let change: Record<string, unknown> = {};

    if (scenarioType === "schema_remove") {
      change = {
        removed: removedField.split(",").map((s) => s.trim()).filter(Boolean),
      };
    } else if (scenarioType === "schema_rename") {
      change = { removed: [oldName], added: [newName] };
    } else if (scenarioType === "owner_missing") {
      change = { owner: null };
    } else if (scenarioType === "pipeline_failure") {
      change = { status: "failed" };
    } else if (scenarioType === "dataset_deprecation") {
      change = { status: "deprecated" };
    }

    onSubmit({
      asset_urn: assetUrn,
      scenario_type: scenarioType,
      change,
      notes: `Simulated ${scenarioType} on ${assetName}`,
    });
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <label style={{ display: "block", marginBottom: 4, fontSize: 13 }}>Scenario Type</label>
        <select
          value={scenarioType}
          onChange={(e) => setScenarioType(e.target.value)}
          style={{ width: "100%", padding: 10, borderRadius: 8, backgroundColor: "#1e293b", color: "#fff", border: "1px solid #334155" }}
        >
          <option value="schema_remove">Column Removal</option>
          <option value="schema_rename">Column Rename</option>
          <option value="owner_missing">Owner Missing</option>
          <option value="pipeline_failure">Pipeline Failure</option>
          <option value="dataset_deprecation">Dataset Deprecation</option>
       </select>
     </div>

      {scenarioType === "schema_remove" && (
        <div>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13 }}>
            Fields to Remove (comma-separated)
         </label>
          <input
            type="text"
            value={removedField}
            onChange={(e) => setRemovedField(e.target.value)}
            placeholder="e.g., customer_name, email"
            style={{ width: "100%", padding: 10, borderRadius: 8, backgroundColor: "#0f172a", color: "#fff", border: "1px solid #334155" }}
          />
       </div>
      )}

      {scenarioType === "schema_rename" && (
        <>
          <div>
            <label style={{ display: "block", marginBottom: 4, fontSize: 13 }}>Old Column Name</label>
            <input
              type="text"
              value={oldName}
              onChange={(e) => setOldName(e.target.value)}
              placeholder="e.g., customer_name"
              style={{ width: "100%", padding: 10, borderRadius: 8, backgroundColor: "#0f172a", color: "#fff", border: "1px solid #334155" }}
            />
         </div>
          <div>
            <label style={{ display: "block", marginBottom: 4, fontSize: 13 }}>New Column Name</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g., name"
              style={{ width: "100%", padding: 10, borderRadius: 8, backgroundColor: "#0f172a", color: "#fff", border: "1px solid #334155" }}
            />
         </div>
        </>
      )}

      <button
        type="submit"
        disabled={loading}
        style={{
          padding: "12px 16px",
          borderRadius: 8,
          backgroundColor: loading ? "#475569" : "#3b82f6",
          color: "#fff",
          border: "none",
          fontWeight: 600,
          cursor: loading ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Simulating..." : "Simulate Scenario"}
     </button>
   </form>
  );
}
