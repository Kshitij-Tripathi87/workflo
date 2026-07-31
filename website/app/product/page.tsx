import Link from "next/link";

export default function ProductPage() {
  return (
    <div className="container" style={{ paddingTop: 64, paddingBottom: 64 }}>
      <h1 style={{ textAlign: "center", marginBottom: 16 }}>
        One decision gate for every data PR
  </h1>
      <p
        style={{
          textAlign: "center",
          fontSize: 18,
          color: "var(--text-dim)",
          maxWidth: 720,
          margin: "0 auto 64px",
        }}
      >
        Cortex Autopilot reads your schema metadata, simulates the impact of
        proposed changes, and enforces policy — all before the change ships.
  </p>

      <h2>Architecture</h2>
      <p>
        The platform is built around four composable layers. You can use any
        combination of them.
  </p>

      <div className="grid-3" style={{ marginTop: 24 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Connectors</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Read schema metadata from dbt, Snowflake, BigQuery, or DataHub.
            Custom connector SDK for the rest.
      </p>
    </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Engine</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Builds the downstream graph, computes blast radius, ranks
            candidate actions, and produces a recommendation with evidence.
      </p>
    </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Policy</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Declarative YAML rules evaluated against the ranked
            recommendation. <code>pass / warn / block</code> verdict.
      </p>
    </div>
     </div>

      <h2>How a PR flows through Cortex</h2>
      <ol>
        <li>
          Developer opens a PR modifying a dbt model, a Snowflake table, or
          any metadata Cortex tracks.
    </li>
        <li>
          The GitHub Action (or webhook, or CLI) sends the change spec to
          <code> POST /future-search/run</code>.
    </li>
        <li>
          The engine builds a graph snapshot, simulates the impact, evaluates
          the policies in <code>cortex.yml</code>, and returns a verdict.
    </li>
        <li>
          The action posts a structured PR comment and (if verdict is
          <code> warn</code> or <code>block</code>) fires a Slack Block Kit
          alert.
    </li>
        <li>
          If verdict is <code>block</code>, the action exits with code 1 and
          the merge button is disabled.
    </li>
  </ol>

      <h2>What makes Cortex different</h2>
      <div className="grid-3">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Connector-agnostic</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Same engine runs against dbt, Snowflake, BigQuery, DataHub.
            Custom connectors take a single Python file.
      </p>
    </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Explainable</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Every recommendation ships with evidence-backed reasoning:
            which assets are affected, why the severity is what it is, and
            which policy fired.
      </p>
    </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Self-hostable</h3>
          <p style={{ color: "var(--text-dim)" }}>
            Runs in your VPC. PostgreSQL + the backend container. No data
            ever leaves your environment.
      </p>
    </div>
     </div>

      <div style={{ textAlign: "center", marginTop: 64 }}>
        <Link href="/pricing" className="btn btn-primary">
          See pricing
    </Link>
     </div>
  </div>
  );
}
