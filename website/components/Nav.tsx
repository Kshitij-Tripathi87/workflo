import Link from "next/link";

const repositoryUrl = "https://github.com/Kshitij-Tripathi87/workflo";

export function Nav() {
  return (
    <header className="site-header">
      <div className="site-shell site-header__inner">
        <Link className="wordmark" href="/" aria-label="Workflo home">
          <span className="brand-mark" aria-hidden="true">W</span>
          <span>workflo</span>
        </Link>

        <nav className="site-nav" aria-label="Main navigation">
          <Link href="/#platform">Platform</Link>
          <Link href="/#workflow">How it works</Link>
          <Link href="/#trust">Trust model</Link>
        </nav>

        <div className="site-header__actions">
          <a href={repositoryUrl} target="_blank" rel="noreferrer">
            GitHub <span aria-hidden="true">↗</span>
          </a>
          <a
            className="button button--light button--small"
            href={repositoryUrl}
            target="_blank"
            rel="noreferrer"
          >
            Explore Workflo
          </a>
        </div>

        <details className="mobile-nav">
          <summary aria-label="Open navigation menu">
            <span />
            <span />
          </summary>
          <nav aria-label="Mobile navigation">
            <Link href="/#platform">Platform</Link>
            <Link href="/#workflow">How it works</Link>
            <Link href="/#trust">Trust model</Link>
            <a href={repositoryUrl} target="_blank" rel="noreferrer">
              GitHub ↗
            </a>
          </nav>
        </details>
      </div>
    </header>
  );
}
