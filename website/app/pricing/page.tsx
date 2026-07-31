import Link from "next/link";

export default function PricingPage() {
  const tiers = [
    {
      name: "Free",
      price: "$0",
      cadence: "forever",
      description: "Open-source, self-hosted. Everything you need to gate your first PR.",
      features: [
        "Unlimited repos (self-hosted)",
        "dbt + Snowflake + DataHub connectors",
        "GitHub Action + PR comments",
        "Slack notifications",
        "Community support",
      ],
      cta: "Install locally",
      href: "https://docs.cortex.dev/install",
      highlighted: false,
    },
    {
      name: "Team",
      price: "$999",
      cadence: "per repo / month",
      description: "Hosted Cortex with policy library, audit log, and team analytics.",
      features: [
        "Hosted Cortex (no infra to run)",
        "Policy library (saved + shareable)",
        "Audit log with 90-day retention",
        "Per-team analytics dashboard",
        "Slack + PagerDuty + Teams alerts",
        "Priority email support",
      ],
      cta: "Start 30-day trial",
      href: "mailto:hello@cortex.dev?subject=team%20trial",
      highlighted: true,
    },
    {
      name: "Enterprise",
      price: "Custom",
      cadence: "starts at $25k / year",
      description: "SSO, custom connectors, on-prem, and a named CSM.",
      features: [
        "SAML SSO + SCIM provisioning",
        "Custom connector development",
        "On-prem or VPC deployment",
        "Custom retention + data residency",
        "Named Customer Success Manager",
        "99.9% SLA + 24/7 incident support",
      ],
      cta: "Talk to sales",
      href: "mailto:hello@cortex.dev?subject=enterprise",
      highlighted: false,
    },
  ];

  return (
    <div className="container" style={{ paddingTop: 64, paddingBottom: 64 }}>
      <h1 style={{ textAlign: "center", marginBottom: 16 }}>Pricing</h1>
      <p
        style={{
          textAlign: "center",
          fontSize: 18,
          color: "var(--text-dim)",
          maxWidth: 600,
          margin: "0 auto 48px",
        }}
      >
        Start free, self-host everything. Upgrade when you want hosted Cortex
        with team analytics. Enterprise for SSO and on-prem.
  </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 24,
        }}
      >
        {tiers.map((tier) => (
          <div
            key={tier.name}
            className="card"
            style={{
              borderColor: tier.highlighted
                ? "var(--accent)"
                : "var(--border)",
              boxShadow: tier.highlighted
                ? "0 0 32px rgba(59, 130, 246, 0.18)"
                : "none",
              position: "relative",
            }}
          >
            {tier.highlighted && (
              <div
                style={{
                  position: "absolute",
                  top: -12,
                  left: "50%",
                  transform: "translateX(-50%)",
                  background: "var(--gradient)",
                  padding: "4px 12px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                Most popular
            </div>
            )}
            <h2 style={{ marginTop: 0 }}>{tier.name</h2>
            <div
              style={{
                fontSize: 36,
                fontWeight: 700,
                margin: "8px 0",
              }}
            >
              {tier.price}
          </div>
            <div style={{ color: "var(--text-muted)", marginBottom: 16 }}>
              {tier.cadence}
          </div>
            <p style={{ color: "var(--text-dim)" }}>{tier.description</p>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: "16px 0",
                color: "var(--text-dim)",
                fontSize: 14,
              }}
            >
              {tier.features.map((f) => (
                <li
                  key={f}
                  style={{
                    padding: "6px 0",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  ✓ {f}
              </li>
              ))}
         </ul>
            <a
              href={tier.href}
              className={tier.highlighted ? "btn btn-primary" : "btn btn-secondary"}
              style={{
                display: "block",
                textAlign: "center",
                marginTop: 16,
              }}
            >
              {tier.cta}
          </a>
       </div>
        ))}
   </div>

      <div
        style={{
          textAlign: "center",
          marginTop: 64,
          color: "var(--text-muted)",
          fontSize: 14,
        }}
      >
        All plans include the core engine, all current connectors, and the
        GitHub Action. No per-seat fees.{" "}
        <Link href="/product">See what's included →</Link>
  </div>
 </div>
  );
}
