import Link from "next/link";

export default function AvailabilityPage() {
  return (
    <div className="product-page">
      <section className="subpage-hero subpage-hero--compact">
        <div className="site-shell">
          <p className="eyebrow">AVAILABILITY / DEPLOYMENT</p>
          <h1>Built around customer-controlled execution.</h1>
          <p>
            Workflo’s initial deployment direction is local-first. The
            supported platform matrix, packaging requirements, commercial
            model, and release guarantees must be established against the
            verified runtime—not guessed through a generic SaaS pricing table.
          </p>
        </div>
      </section>

      <section className="product-section section-pad">
        <div className="site-shell availability-grid">
          <article className="availability-card">
            <span className="eyebrow">INITIAL DIRECTION</span>
            <h2>Customer-run</h2>
            <p>
              The intended first deployment keeps the application runtime,
              execution environment, and model inference under the customer’s
              control.
            </p>
            <ul>
              <li>Local project and repository workflows</li>
              <li>Locally operated inference path</li>
              <li>Explicit runtime and network policy</li>
              <li>Inspectable reports and receipt provenance</li>
            </ul>
          </article>
          <article className="availability-card availability-card--quiet">
            <span className="eyebrow">NOT PUBLISHED YET</span>
            <h2>Commercial plans</h2>
            <p>
              Pricing, quotas, service levels, and hosted deployment options
              will be published only after the supported release profiles and
              operating costs have been validated.
            </p>
            <p>
              No subscription tier or service guarantee is implied by this
              page.
            </p>
          </article>
        </div>
      </section>

      <section className="closing-section section-pad">
        <div className="site-shell closing-panel">
          <p className="eyebrow">CURRENT SOURCE OF TRUTH</p>
          <h2>Follow the product as it is built.</h2>
          <p>
            Check the repository for the current implementation, installation
            instructions, and verified capabilities.
          </p>
          <a
            className="button button--light"
            href="https://github.com/Kshitij-Tripathi87/workflo"
            target="_blank"
            rel="noreferrer"
          >
            Open the Workflo repository <span aria-hidden="true">↗</span>
          </a>
          <Link className="text-link closing-panel__secondary-link" href="/">
            Back to Workflo <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
