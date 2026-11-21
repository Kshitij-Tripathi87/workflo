import Link from "next/link";

const repositoryUrl = "https://github.com/Kshitij-Tripathi87/workflo";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-shell">
        <div className="site-footer__top">
          <div className="site-footer__identity">
            <Link className="wordmark" href="/">
              <span className="brand-mark" aria-hidden="true">W</span>
              <span>workflo</span>
            </Link>
            <p>
              Autonomous QA built around controlled execution, useful findings,
              and evidence you can inspect.
            </p>
          </div>

          <div className="site-footer__links">
            <div>
              <span className="site-footer__heading">Explore</span>
              <Link href="/#platform">Platform</Link>
              <Link href="/#workflow">How it works</Link>
              <Link href="/#trust">Trust model</Link>
            </div>
            <div>
              <span className="site-footer__heading">Project</span>
              <a href={repositoryUrl} target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
              <Link href="/product">Product details</Link>
              <Link href="/pricing">Availability</Link>
            </div>
          </div>
        </div>

        <div className="site-footer__bottom">
          <span>© {new Date().getFullYear()} Workflo</span>
          <span>Built for software that deserves to be tested properly.</span>
        </div>
      </div>
    </footer>
  );
}
