import Link from "next/link";

export function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border)",
        marginTop: 96,
        padding: "48px 0 32px",
        color: "var(--text-dim)",
        fontSize: 14,
      }}
    >
      <div
        className="container"
        style={{
          display: "grid",
          gridTemplateColumns: "2fr 1fr 1fr 1fr",
          gap: 32,
        }}
      >
        <div>
          <div
            style={{ fontWeight: 700, color: "var(--text)", marginBottom: 8 }}
          >
            <span className="gradient-text">Cortex</span> Autopilot
       </div>
          <p style={{ maxWidth: 280, color: "var(--text-muted)" }}>
            CI/CD Impact Gate for data platforms. Block risky data changes
            before they reach production.
         </p>
     </div>
        <div>
          <h4 style={{ color: "var(--text)", fontSize: 13, marginBottom: 12 }}>
            Product
       </h4>
          <Link href="/product" style={{ display: "block", marginBottom: 6 }}>
            Overview
       </Link>
          <Link href="/pricing" style={{ display: "block", marginBottom: 6 }}>
            Pricing
       </Link>
          <a href="https://docs.cortex.dev" style={{ display: "block" }}>
            Docs
       </a>
     </div>
        <div>
          <h4 style={{ color: "var(--text)", fontSize: 13, marginBottom: 12 }}>
            Company
       </h4>
          <Link href="/blog" style={{ display: "block", marginBottom: 6 }}>
            Blog
       </Link>
          <a href="mailto:hello@cortex.dev" style={{ display: "block", marginBottom: 6 }}>
            Contact
       </a>
          <a href="https://github.com/cortex-autopilot" style={{ display: "block" }}>
            GitHub
       </a>
     </div>
        <div>
          <h4 style={{ color: "var(--text)", fontSize: 13, marginBottom: 12 }}>
            Legal
       </h4>
          <a href="/license" style={{ display: "block", marginBottom: 6 }}>
            License
       </a>
          <a href="/privacy" style={{ display: "block", marginBottom: 6 }}>
            Privacy
       </a>
          <a href="/terms" style={{ display: "block" }}>
            Terms
       </a>
     </div>
   </div>
      <div
        className="container"
        style={{
          marginTop: 32,
          paddingTop: 24,
          borderTop: "1px solid var(--border)",
          color: "var(--text-muted)",
          fontSize: 13,
        }}
      >
        © 2026 Cortex Autopilot, Inc.
     </div>
   </footer>
  );
}
