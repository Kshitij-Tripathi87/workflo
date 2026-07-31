import Link from "next/link";

export function Nav() {
  return (
    <nav
      style={{
        borderBottom: "1px solid var(--border)",
        padding: "16px 0",
        position: "sticky",
        top: 0,
        background: "rgba(10, 14, 26, 0.85)",
        backdropFilter: "blur(12px)",
        zIndex: 100,
      }}
    >
      <div
        className="container"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Link
          href="/"
          style={{
            fontWeight: 700,
            fontSize: 18,
            color: "var(--text)",
            textDecoration: "none",
          }}
        >
          <span className="gradient-text">Cortex</span> Autopilot
      </Link>
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <Link href="/product" style={{ color: "var(--text-dim)" }}>
            Product
        </Link>
          <Link href="/pricing" style={{ color: "var(--text-dim)" }}>
            Pricing
        </Link>
          <Link href="/blog" style={{ color: "var(--text-dim)" }}>
            Blog
        </Link>
          <a
            href="https://docs.cortex.dev"
            style={{ color: "var(--text-dim)" }}
          >
            Docs
        </a>
          <a
            href="mailto:hello@cortex.dev"
            className="btn btn-primary"
            style={{ padding: "8px 16px", fontSize: 14 }}
          >
            Book a demo
        </a>
      </div>
    </div>
  </nav>
  );
}
