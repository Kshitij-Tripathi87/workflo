import Link from "next/link";

const posts = [
  {
    slug: "why-schema-changes-break-analytics",
    title: "Why schema changes break analytics",
    excerpt:
      "A schema change is the most common cause of silent data outages. Here's why, and what to do about it.",
    date: "2026-08-04",
    read: "5 min",
  },
  {
    slug: "designing-a-blast-radius-engine",
    title: "Designing a blast-radius engine for dbt",
    excerpt:
      "How we compute impact from a single column rename — and why graph topology matters more than ML.",
    date: "2026-08-18",
    read: "10 min",
  },
  {
    slug: "from-ci-to-data-ci-cd",
    title: "From CI to data CI/CD: the missing gate",
    excerpt:
      "Treating data changes as second-class citizens compared to code is the root cause of most analytics incidents.",
    date: "2026-09-01",
    read: "7 min",
  },
];

export default function BlogPage() {
  return (
    <div className="container" style={{ paddingTop: 64, paddingBottom: 64 }}>
      <h1 style={{ textAlign: "center", marginBottom: 16 }}>Blog</h1>
      <p
        style={{
          textAlign: "center",
          fontSize: 18,
          color: "var(--text-dim)",
          maxWidth: 640,
          margin: "0 auto 48px",
        }}
      >
        Engineering deep dives, customer stories, and lessons from the
        Cortex team.
 </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {posts.map((post) => (
          <Link
            key={post.slug}
            href={`/blog/${post.slug}`}
            className="card"
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                color: "var(--text-muted)",
                fontSize: 13,
                marginBottom: 8,
              }}
            >
              <span>{post.date</span>
              <span>{post.read} read</span>
        </div>
            <h2 style={{ marginTop: 0, marginBottom: 8, color: "var(--text)" }}>
              {post.title}
        </h2>
            <p style={{ color: "var(--text-dim)", margin: 0 }}>{post.excerpt</p>
      </Link>
        ))}
    </div>
 </div>
  );
}
