import Link from "next/link";

export default function HomePage() {
  return (
    <div>
      {/* Hero */}
      <section
        style={{
          paddingTop: 96,
          paddingBottom: 80,
          textAlign: "center",
        }}
      >
        <div className="container">
          <div
            style={{
              display: "inline-block",
              padding: "6px 14px",
              borderRadius: 999,
              background: "rgba(59, 130, 246, 0.12)",
              border: "1px solid rgba(59, 130, 246, 0.3)",
              fontSize: 13,
              color: "var(--accent-bright)",
              marginBottom: 24,
            }}
          >
            Now in public beta
        </div>
          <h1
            style={{
              fontSize: 64,
              maxWidth: 880,
              margin: "0 auto 24px",
            }}
          >
            Know{" "}
            <span className="gradient-text">what breaks</span>
            <br />
            before you deploy.
        </h1>
          <p
            style={{
              fontSize: 20,
              maxWidth: 640,
              margin: "0 auto 40px",
              color: "var(--text-dim)",
            }}
          >
            Cortex Autopilot is a CI/CD Impact Gate for dbt and Snowflake
            teams. Read the manifest, compute the blast radius, and block
            risky data changes — before they reach production.
        </p>
          <div
            style={{
              display: "flex",
              gap: 16,
              justifyContent: "center",
              flexWrap: "wrap",
            }}
          >
            <a href="mailto:hello@cortex.dev?subject=demo" className="btn btn-primary">
              Book a 15-minute demo
          </a>
            <Link href="/product" className="btn btn-secondary">
              How it works →
          </Link>
        </div>
      </div>
    </section>

      {/* Problem */}
      <section style={{ paddingTop: 80, paddingBottom: 32 }}>
        <div className="container">
          <h2 style={{ textAlign: "center", marginBottom: 16 }}>
            Data changes don't have a CI gate
         </h2>
          <p
            style={{
              textAlign: "center",
              fontSize: 18,
              color: "var(--text-dim)",
              maxWidth: 720,
              margin: "0 auto 48px",
            }}
          >
            Every other change in your stack — code, infra, even ML models — has
            a review gate. Data changes? A column rename silently breaks three
            downstream dashboards. You find out in the morning standup.
        </p>
       </div>
     </section>

      {/* Three-step flow */}
      <section style={{ paddingTop: 32, paddingBottom: 80 }}>
        <div className="container">
          <div className="grid-3">
            <div className="card">
              <div style={{ fontSize: 32, marginBottom: 12 }}>①</div>
              <h3 style={{ marginTop: 0 }}>Detect</h3>
              <p style={{ color: "var(--text-dim)" }}>
                Reads your dbt manifest.json and catalog.json on every PR. No
                live database connection required for the open-source edition.
            </p>
          </div>
            <div className="card">
              <div style={{ fontSize: 32, marginBottom: 12 }}>②</div>
              <h3 style={{ marginTop: 0 }}>Simulate</h3>
              <p style={{ color: "var(--text-dim)" }}>
                Builds the downstream graph, computes blast radius and
                severity for the proposed change. Returns ranked
                recommendations in milliseconds.
            </p>
          </div>
            <div className="card">
              <div style={{ fontSize: 32, marginBottom: 12 }}>③</div>
              <h3 style={{ marginTop: 0 }}>Enforce</h3>
              <p style={{ color: "var(--text-dim)" }}>
                Posts a structured PR comment with{" "}
                <code>pass / warn / block</code> verdict. Slack alert fires in
                parallel. Engineers keep velocity.
            </p>
          </div>
        </div>
      </div>
    </section>

      {/* Stats */}
      <section style={{ paddingTop: 32, paddingBottom: 64 }}>
        <div className="container">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 32,
              textAlign: "center",
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: "var(--accent-bright)",
                }}
              >
                <1ms
           </div>
              <div style={{ color: "var(--text-dim)", fontSize: 14 }}>
                p95 simulation latency (synthetic benchmark, 10k changes)
           </div>
         </div>
            <div>
              <div
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: "var(--accent-bright)",
                }}
              >
                2.7%
           </div>
              <div style={{ color: "var(--text-dim)", fontSize: 14 }}>
                False-positive rate (synthetic benchmark)
           </div>
         </div>
            <div>
              <div
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: "var(--accent-bright)",
                }}
              >
                ~70%
           </div>
              <div style={{ color: "var(--text-dim)", fontSize: 14 }}>
                Reduction in schema-related incidents (customer-reported)
           </div>
         </div>
            <div>
              <div
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: "var(--accent-bright)",
                }}
              >
                1 command
            </div>
              <div style={{ color: "var(--text-dim)", fontSize: 14 }}>
                Setup to first verdict
            </div>
          </div>
        </div>
      </div>
    </section>

      {/* Stack */}
      <section style={{ paddingTop: 32, paddingBottom: 96 }}>
        <div className="container">
          <h2 style={{ textAlign: "center" }}>Plugs into your stack</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 16,
              marginTop: 32,
            }}
          >
            {[
              { name: "GitHub Actions", role: "CI gate" },
              { name: "dbt", role: "Schema source" },
              { name: "Snowflake", role: "Live warehouse" },
              { name: "BigQuery", role: "Live warehouse" },
              { name: "DataHub", role: "Metadata catalog" },
              { name: "Slack", role: "Alert channel" },
              { name: "PagerDuty", role: "Pager integration" },
              { name: "OpenMetadata", role: "Metadata catalog" },
            ].map((s) => (
              <div
                key={s.name}
                className="card"
                style={{ textAlign: "center", padding: 16 }}
              >
                <div style={{ fontWeight: 600 }}>{s.name</div>
                <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  {s.role}
            </div>
          </div>
            ))}
        </div>
      </div>
    </section>

      {/* CTA */}
      <section style={{ paddingTop: 32, paddingBottom: 96 }}>
        <div className="container">
          <div
            className="card"
            style={{
              padding: 48,
              textAlign: "center",
              background:
                "linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(139, 92, 246, 0.08) 100%)",
              borderColor: "rgba(59, 130, 246, 0.3)",
            }}
          >
            <h2 style={{ marginTop: 0 }}>Ready to gate your next PR</h2>
            <p
              style={{
                fontSize: 18,
                color: "var(--text-dim)",
                maxWidth: 540,
                margin: "0 auto 32px",
              }}
            >
              Run the open-source demo locally in under 10 minutes. Or book a
              15-minute walkthrough on your own dbt project.
          </p>
            <div
              style={{
                display: "flex",
                gap: 16,
                justifyContent: "center",
                flexWrap: "wrap",
              }}
            >
              <a
                href="https://docs.cortex.dev/install"
                className="btn btn-primary"
              >
                Install locally
            </a>
              <a href="mailto:hello@cortex.dev" className="btn btn-secondary">
                Talk to a founder
            </a>
          </div>
        </div>
      </div>
    </section>
  </div>
  );
}
