"use client";

import { useMemo, useState, useCallback, useRef, useEffect } from "react";
import { assets as mockAssets } from "../lib/mock";
import { Panel } from "../components/Panel";
import { AssetPicker } from "../components/AssetPicker";
import { GraphSummary } from "../components/GraphSummary";
import { ScenarioForm } from "../components/ScenarioForm";
import { ImpactPanel } from "../components/ImpactPanel";
import { RecommendationCard } from "../components/RecommendationCard";
import { ArtifactPreview } from "../components/ArtifactPreview";
import { WritebackStatus } from "../components/WritebackStatus";
import { LineageGraph } from "../components/LineageGraph";
import { SeverityBadge } from "../components/SeverityBadge";
import { FutureSearchPanel } from "../components/FutureSearchPanel";
import { ContractTestPanel } from "../components/ContractTestPanel";
import { ReceiptVerifierModal } from "../components/ReceiptVerifierModal";
import { ComplianceCenter } from "../components/ComplianceCenter";
import * as api from "../lib/api";
import type {
  AssetNode,
  GraphEdge,
  GraphSnapshot,
  ScenarioRequest,
  ScenarioResult,
  ImpactReport,
  Recommendation,
  ArtifactDraft,
  WritebackRecord,
  FuturePlan,
} from "../lib/types";

interface GraphData extends GraphSnapshot {
  node_count: number;
  edge_count: number;
}

export default function Home() {
  const [selectedUrn, setSelectedUrn] = useState(mockAssets[0].urn);
  const [asset, setAsset] = useState<AssetNode | null>(mockAssets[0]);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [scenario, setScenario] = useState<ScenarioResult | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [artifact, setArtifact] = useState<ArtifactDraft | null>(null);
  const [writeback, setWriteback] = useState<WritebackRecord | null>(null);
  const [futurePlan, setFuturePlan] = useState<FuturePlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [futureLoading, setFutureLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [useMock, setUseMock] = useState(true);

  // Request token refs prevent race conditions: if an in-flight fetch is
  // for a stale URN, we ignore its result when it resolves.
  const graphTokenRef = useRef(0);
  const scenarioTokenRef = useRef(0);

  const loadAsset = useCallback(
    async (urn: string) => {
      setSelectedUrn(urn);
      setGraphError(null);

      if (useMock) {
        const a = mockAssets.find((x) => x.urn === urn) || null;
        setAsset(a);
        setGraphData(null);
        return;
      }

      const token = ++graphTokenRef.current;
      try {
        const [assetRes, graphRes] = await Promise.all([
          api.fetchAsset(urn),
          api.fetchGraph(urn).catch((e) => {
            if (token === graphTokenRef.current) setGraphError(e?.message || "graph unavailable");
            return null;
          }),
        ]);
        // Discard stale responses
        if (token !== graphTokenRef.current) return;
        setAsset(assetRes);
        setGraphData(graphRes);
      } catch (e: unknown) {
        if (token !== graphTokenRef.current) return;
        const a = mockAssets.find((x) => x.urn === urn) || null;
        setAsset(a);
        setGraphData(null);
        setGraphError((e as Error)?.message || "asset unavailable");
      }
    },
    [useMock]
  );

  const runScenario = useCallback(
    async (request: ScenarioRequest) => {
      setLoading(true);
      const token = ++scenarioTokenRef.current;
      try {
        // Read the currently-selected asset from state synchronously to
        // avoid stale closures. `selectedUrn` is captured here in the
        // current render and used as the request URN.
        const liveUrn = request.asset_urn;

        if (useMock) {
          // Build mock outputs from the live asset (read via local state)
          // rather than closure-captured `asset` which may be stale.
          const liveAsset = mockAssets.find((a) => a.urn === liveUrn) || null;
          const downstream = liveAsset?.downstream || [];

          const explain: string[] = [];
          if (downstream.length > 0) explain.push(`This asset feeds ${downstream.length} downstream asset(s).`);
          else explain.push("No downstream assets affected directly.");
          if (liveAsset?.criticality === "critical") explain.push("Asset is marked as critical.");
          if (!liveAsset?.owner) explain.push("No owner is assigned.");

          const severity: ScenarioResult["predicted_severity"] =
            request.scenario_type === "pipeline_failure"
              ? "critical"
              : downstream.length > 0
                ? "high"
                : "medium";

          const mockScenario: ScenarioResult = {
            scenario_id: "mock-" + Date.now(),
            asset_urn: liveUrn,
            scenario_type: request.scenario_type,
            applied_change: request.change,
            predicted_breakages: [`Mock: ${request.scenario_type} applied`],
            predicted_severity: severity,
            confidence: 0.85,
          };

          const mockImpact: ImpactReport = {
            impact_id: "mock-impact-" + Date.now(),
            asset_urn: liveUrn,
            affected_assets: downstream,
            affected_dashboards: downstream.filter((d) => d.includes("dashboard")),
            affected_models: downstream.filter((d) => d.includes("mlModel")),
            affected_pipelines: downstream.filter((d) => d.includes("pipeline")),
            severity,
            reason: `Mock impact for ${request.scenario_type}`,
            confidence: 0.8,
            explanation: explain,
          };

          const isOwner = request.scenario_type === "owner_missing";
          const mockRec: Recommendation = {
            recommendation_id: "mock-rec-" + Date.now(),
            impact_id: mockImpact.impact_id,
            action_type: isOwner ? "assign_owner" : "patch_sql",
            title: isOwner ? "Assign asset owner" : "Patch downstream transforms",
            rationale: "Mock recommendation for demo purposes.",
            confidence: 0.75,
            risk: severity,
            artifacts: [],
          };

          const mockArtifact: ArtifactDraft = {
            artifact_id: "mock-artifact-" + Date.now(),
            recommendation_id: mockRec.recommendation_id,
            artifact_type: isOwner ? "yaml" : "sql",
            title: "Mock Remediation Artifact",
            body: isOwner
              ? "# Ownership Assignment\nowner: <assignee>\n"
              : `-- SQL Patch\nALTER TABLE ${liveAsset?.name || "asset"} MODIFY COLUMN ...;\n`,
            file_path: null,
            confidence: 0.75,
          };

          const mockWriteback: WritebackRecord = {
            record_id: "mock-wb-" + Date.now(),
            asset_urn: liveUrn,
            status: "triaged",
            summary: `Mock resolution recorded for ${request.scenario_type}.`,
            linked_artifact: mockArtifact.artifact_id,
            affected_assets: mockImpact.affected_assets,
            created_by: "dev-user",
            created_at: new Date().toISOString(),
          };

          if (token !== scenarioTokenRef.current) return;
          setScenario(mockScenario);
          setImpact(mockImpact);
          setRecommendation(mockRec);
          setArtifact(mockArtifact);
          setWriteback(mockWriteback);
        } else {
          const demoResp = await api.runDemo({
            asset_urn: liveUrn,
            scenario_type: request.scenario_type,
            change: request.change,
            notes: request.notes,
          });
          if (token !== scenarioTokenRef.current) return;
          setScenario(demoResp.scenario);
          setImpact(demoResp.impact);
          setRecommendation(demoResp.recommendation);
          setArtifact(demoResp.artifact);
          setWriteback(demoResp.writeback);
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (token === scenarioTokenRef.current) setLoading(false);
      }
    },
    [useMock]
  );

  const runFutureSearch = useCallback(async () => {
    setFutureLoading(true);
    setFuturePlan(null);
    try {
      if (useMock) {
        // Use candidate count of 3 in the mock (matches what we actually generate)
        const mockPlan: FuturePlan = {
          plan_id: "mock-plan-" + Date.now(),
          asset_urn: selectedUrn,
          objective: "minimize incident risk",
          candidates: [
            {
              future_id: "mock-f1",
              asset_urn: selectedUrn,
              scenario_type: "do_nothing",
              change: {},
              predicted_severity: 65,
              predicted_effort: 5,
              predicted_benefit: 35,
              confidence: 0.9,
              evidence: ["No action taken", "Risk remains elevated"],
            },
            {
              future_id: "mock-f2",
              asset_urn: selectedUrn,
              scenario_type: "patch_dbt",
              change: { action: "patch dbt model" },
              predicted_severity: 22,
              predicted_effort: 25,
              predicted_benefit: 78,
              confidence: 0.85,
              evidence: ["Downstream models will be updated", "Breaking changes resolved"],
            },
            {
              future_id: "mock-f3",
              asset_urn: selectedUrn,
              scenario_type: "patch_sql",
              change: { action: "patch SQL" },
              predicted_severity: 28,
              predicted_effort: 20,
              predicted_benefit: 72,
              confidence: 0.82,
              evidence: ["SQL queries updated", "Compatibility maintained"],
            },
          ],
          ranked_choice: {
            future_id: "mock-f2",
            asset_urn: selectedUrn,
            scenario_type: "patch_dbt",
            change: { action: "patch dbt model" },
            predicted_severity: 22,
            predicted_effort: 25,
            predicted_benefit: 78,
            confidence: 0.85,
            evidence: ["Downstream models will be updated", "Breaking changes resolved"],
          },
          rationale:
            "Selected patch_dbt because it provides the best balance of risk reduction and benefit while staying within reasonable effort bounds.",
          explanation: [
            "Selected: patch_dbt",
            "Predicted severity: 22/100",
            "Predicted effort: 25/100",
            "Predicted benefit: 78/100",
            "Confidence: 85%",
            "This option provides the highest predicted benefit.",
            "Evidence from impact analysis:",
            "  - Downstream models will be updated",
            "  - Breaking changes resolved",
          ],
          created_at: new Date().toISOString(),
        };
        setFuturePlan(mockPlan);
      } else {
        const plan = await api.runFutureSearch({
          asset_urn: selectedUrn,
          objective: "minimize incident risk",
          constraints: { max_effort: 40 },
        });
        setFuturePlan(plan);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setFutureLoading(false);
    }
  }, [useMock, selectedUrn]);

  const selectedAsset = useMemo(() => {
    return asset || mockAssets.find((a) => a.urn === selectedUrn) || null;
  }, [asset, selectedUrn]);

  const downstreamCount = selectedAsset?.downstream.length || 0;
  const criticalCount = selectedAsset?.criticality === "critical" ? 1 : 0;

  // Reset transient state when the user picks a different asset.
  useEffect(() => {
    setScenario(null);
    setImpact(null);
    setRecommendation(null);
    setArtifact(null);
    setWriteback(null);
    setFuturePlan(null);
  }, [selectedUrn]);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: 24, color: "#e2e8f0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 32, marginBottom: 4 }}>Cortex Autopilot</h1>
          <p style={{ color: "#94a3b8", margin: 0 }}>
            Enterprise decision intelligence — explore millions of possible futures before touching production.
         </p>
       </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <label style={{ fontSize: 13, color: "#94a3b8" }}>
            <input
              type="checkbox"
              checked={useMock}
              onChange={(e) => setUseMock(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            Mock Mode
         </label>
          <SeverityBadge severity={selectedAsset?.criticality || "low"} />
       </div>
     </div>

      {graphError && (
        <div
          style={{
            padding: "10px 14px",
            marginBottom: 16,
            borderRadius: 8,
            backgroundColor: "#7f1d1d",
            color: "#fee2e2",
            fontSize: 13,
          }}
        >
          Graph fetch failed: {graphError}. Showing local fallback.
       </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 16 }}>
        <Panel title="1. Select Asset">
          <AssetPicker assets={mockAssets} selectedUrn={selectedUrn} onChange={loadAsset} />
          {selectedAsset && (
            <div style={{ marginTop: 12, fontSize: 13, color: "#94a3b8" }}>
              <div>
                <b>URN</b> <span style={{ color: "#cbd5e1" }}>{selectedAsset.urn}</span>
             </div>
              <div>
                <b>Owner</b>{" "}
                <span style={{ color: "#cbd5e1" }}>{selectedAsset.owner || "Unassigned"}</span>
             </div>
              <div>
                <b>Kind</b> <span style={{ color: "#cbd5e1" }}>{selectedAsset.kind}</span>
             </div>
           </div>
          )}
       </Panel>

        <Panel title="Graph Summary">
          <GraphSummary
            nodeCount={graphData?.node_count || (selectedAsset ? 1 + downstreamCount : 0)}
            edgeCount={graphData?.edge_count || downstreamCount}
            downstreamCount={downstreamCount}
            criticalCount={criticalCount}
          />
       </Panel>
     </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 16 }}>
        <Panel title="2. Simulate Scenario">
          <ScenarioForm
            assetUrn={selectedUrn}
            assetName={selectedAsset?.name || "asset"}
            onSubmit={runScenario}
            loading={loading}
          />
       </Panel>

        <Panel title="Lineage">
          <LineageGraph
            node={selectedAsset}
            edges={(graphData?.edges as GraphEdge[]) || []}
            allNodes={Object.fromEntries(mockAssets.map((a) => [a.urn, a]))}
          />
       </Panel>
     </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 16 }}>
        <Panel title="3. Impact Analysis">
          <ImpactPanel impact={impact} />
       </Panel>

        <Panel title="4. Recommendation">
          <RecommendationCard recommendation={recommendation} />
       </Panel>
     </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 16 }}>
        <Panel title="5. Artifact">
          <ArtifactPreview artifact={artifact} />
        </Panel>

        <Panel title="6. Write-back">
          <WritebackStatus record={writeback} />
        </Panel>
      </div>

      <FutureSearchPanel plan={futurePlan} onRun={runFutureSearch} loading={futureLoading} />

      {futurePlan?.receipt && (
        <ReceiptVerifierModal receipt={futurePlan.receipt} />
      )}

      <ContractTestPanel assetUrn={selectedUrn} />

      <ComplianceCenter />
    </main>
  );
}
