import Link from "next/link";

export default function BlogPage() {
  return (
    <section className="subpage-hero">
      <div className="site-shell">
        <p className="eyebrow">WORKFLO / FIELD NOTES</p>
        <h1>Engineering notes, without the noise.</h1>
        <p>
          Workflo technical notes and product updates will be published here
          as they are ready. Until then, the repository is the source of truth
          for implementation details, current capabilities, and installation
          guidance.
        </p>
        <Link className="button button--light" href="/">
          Back to Workflo <span aria-hidden="true">↗</span>
        </Link>
        <a
          className="text-link closing-panel__secondary-link"
          href="https://github.com/Kshitij-Tripathi87/workflo"
          target="_blank"
          rel="noreferrer"
        >
          View repository <span aria-hidden="true">↗</span>
        </a>
      </div>
    </section>
  );
}
