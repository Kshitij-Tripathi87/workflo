import Link from "next/link";
import { ExecutionStory } from "../components/ExecutionStory";
import { RunCustomizer } from "../components/RunCustomizer";

const repositoryUrl = "https://github.com/Kshitij-Tripathi87/workflo";

const capabilities = [
  {
    number: "01",
    title: "Start with the repository",
    description:
      "Resolve a source revision, prepare a stable snapshot, and keep the run tied to the code that was actually tested.",
    tag: "SOURCE PROVENANCE",
  },
  {
    number: "02",
    title: "Run the checks that matter",
    description:
      "Use the project's native test suite as the foundation, then add application, API, and browser probes where the run is configured to support them.",
    tag: "EXECUTION",
  },
  {
    number: "03",
    title: "Explore beyond the checklist",
    description:
      "Governed model-assisted workflows can propose additional test cases and invariants. Generated output is validated before it is allowed into the run.",
    tag: "AI-ASSISTED QA",
  },
  {
    number: "04",
    title: "Keep the evidence",
    description:
      "Connect outcomes to execution records, evidence references, and receipt provenance. A narrative is useful only when it can be inspected.",
    tag: "VERIFICATION",
  },
];

const trustPillars = [
  {
    title: "A revision you can identify",
    description:
      "A QA result should name the source revision and snapshot it evaluated. A branch name alone is not a reproducible test target.",
    mark: "01",
  },
  {
    title: "A boundary that can fail closed",
    description:
      "Runtime prerequisites and execution policies must be checked before untrusted code runs. A control that cannot be verified must not be presented as active.",
    mark: "02",
  },
  {
    title: "A result tied to evidence",
    description:
      "Findings should point back to the records that support them. Signed receipts and independent verification are part of the trust model, not decoration.",
    mark: "03",
  },
];

export default function HomePage() {
  return (
    <>
      <section className="hero" id="platform">
        <div className="hero__ambient" aria-hidden="true" />
        <div className="site-shell hero__layout">
          <div className="hero__copy">
            <p className="eyebrow">
              <span className="eyebrow__line" />
              AUTONOMOUS QA FOR SOFTWARE REPOSITORIES
            </p>
            <h1>
              Find what your tests <span>don’t.</span>
            </h1>
            <p className="hero__lede">
              Workflo runs your project’s checks, probes application behavior,
              and turns verified failures into evidence your team can inspect.
            </p>
            <div className="hero__actions">
              <a
                className="button button--light"
                href={repositoryUrl}
                target="_blank"
                rel="noreferrer"
              >
                Explore Workflo <span aria-hidden="true">↗</span>
              </a>
              <Link className="button button--quiet" href="#workflow">
                See how a run works <span aria-hidden="true">↓</span>
              </Link>
            </div>
            <div className="hero__facts">
              <span>REPOSITORY-NATIVE</span>
              <span>GOVERNED EXPLORATION</span>
              <span>EVIDENCE-LED</span>
            </div>
          </div>

          <div className="hero__visual">
            <div className="hero__visual-orbit hero__visual-orbit--outer" />
            <div className="hero__visual-orbit hero__visual-orbit--inner" />
            <div className="run-preview">
              <div className="run-preview__topbar">
                <div className="window-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <span>WORKFLO / RUN PREVIEW</span>
                <span className="run-preview__tag">CONCEPT</span>
              </div>

              <div className="run-preview__body">
                <div className="run-preview__identity">
                  <div>
                    <span className="micro-label">PROJECT</span>
                    <strong>sample-repository</strong>
                  </div>
                  <div className="run-preview__revision">
                    <span className="micro-label">SOURCE</span>
                    <strong>REVISION PINNED</strong>
                  </div>
                </div>

                <div className="run-preview__divider" />

                <div className="run-preview__stage">
                  <span className="run-preview__stage-index">01</span>
                  <div>
                    <strong>Prepare</strong>
                    <small>Configuration · snapshot · runtime</small>
                  </div>
                  <span className="stage-symbol stage-symbol--done" aria-label="Illustrative completed stage">✓</span>
                </div>
                <div className="run-preview__stage">
                  <span className="run-preview__stage-index">02</span>
                  <div>
                    <strong>Exercise</strong>
                    <small>Native tests · application probes</small>
                  </div>
                  <span className="stage-symbol" aria-hidden="true">↗</span>
                </div>
                <div className="run-preview__stage">
                  <span className="run-preview__stage-index">03</span>
                  <div>
                    <strong>Verify</strong>
                    <small>Findings · evidence · teardown</small>
                  </div>
                  <span className="stage-symbol" aria-hidden="true">◇</span>
                </div>

                <div className="run-preview__terminal">
                  <div className="run-preview__terminal-heading">
                    <span>EXECUTION RECORD</span>
                    <span>ILLUSTRATIVE DATA</span>
                  </div>
                  <p><span>$</span> workflo run --test</p>
                  <p className="run-preview__terminal-muted">source&nbsp;&nbsp; pinned revision</p>
                  <p className="run-preview__terminal-muted">policy&nbsp;&nbsp; selected runtime profile</p>
                  <p className="run-preview__terminal-muted">output&nbsp; evidence-linked report</p>
                </div>
              </div>
            </div>
            <div className="hero__visual-caption">
              <span className="caption-dot" />
              A RUN SHOULD LEAVE AN EVIDENCE TRAIL
            </div>
          </div>
        </div>
        <div className="hero__bottom-rule" />
      </section>

      <section className="intro-section section-pad">
        <div className="site-shell intro-section__layout">
          <p className="eyebrow">THE GAP IN THE TEST LOOP</p>
          <div>
            <h2>
              Passing tests tell you what you checked. They don’t tell you
              everything you missed.
            </h2>
            <p>
              Workflo is designed to add a disciplined investigation layer to
              software QA: execute existing checks, explore configured
              application behavior, validate candidate tests, and preserve the
              evidence behind each result.
            </p>
          </div>
        </div>
      </section>

      <section className="capabilities-section section-pad" id="platform-capabilities">
        <div className="site-shell">
          <div className="section-heading">
            <div>
              <p className="eyebrow">THE WORKFLOW, NOT THE HYPE</p>
              <h2>QA that goes beyond a green check.</h2>
            </div>
            <p>
              Four connected responsibilities. Each has a clear input, an
              observable output, and a boundary around what it is allowed to
              claim.
            </p>
          </div>

          <div className="capability-grid">
            {capabilities.map((item) => (
              <article className="capability-card" key={item.number}>
                <div className="capability-card__top">
                  <span>{item.number}</span>
                  <span>{item.tag}</span>
                </div>
                <div className="capability-card__glyph" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <div className="capability-card__rule" />
              </article>
            ))}
          </div>
        </div>
      </section>

      <ExecutionStory />

      <section className="trust-section section-pad" id="trust">
        <div className="site-shell">
          <div className="section-heading section-heading--trust">
            <div>
              <p className="eyebrow">THE TRUST MODEL</p>
              <h2>Evidence before confidence.</h2>
            </div>
            <p>
              A useful QA result is more than a summary. It needs provenance,
              a clearly defined execution boundary, and a way to inspect what
              actually happened.
            </p>
          </div>

          <div className="trust-grid">
            {trustPillars.map((item) => (
              <article className="trust-card" key={item.mark}>
                <span className="trust-card__number">{item.mark}</span>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </article>
            ))}
          </div>

          <div className="local-first-panel">
            <div className="local-first-panel__visual" aria-hidden="true">
              <div className="local-first-panel__ring local-first-panel__ring--one" />
              <div className="local-first-panel__ring local-first-panel__ring--two" />
              <div className="local-first-panel__core">
                <span className="brand-mark brand-mark--large">W</span>
              </div>
            </div>
            <div className="local-first-panel__copy">
              <p className="eyebrow">LOCAL-FIRST BY DESIGN</p>
              <h3>Your code. Your execution boundary.</h3>
              <p>
                Workflo’s architecture is being developed around
                customer-controlled execution and locally operated model
                inference. The guarantees for a particular release depend on
                its verified runtime, model artifacts, network policy, and
                retention configuration.
              </p>
              <Link className="text-link" href="/product">
                Read the product architecture <span aria-hidden="true">↗</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="closing-section section-pad">
        <div className="site-shell closing-panel">
          <p className="eyebrow">MAKE THE NEXT RUN COUNT</p>
          <h2>Bring the repository. Leave with evidence.</h2>
          <p>
            Explore the implementation, current CLI, and development status
            directly in the Workflo repository.
          </p>
          <div className="closing-panel__actions">
            <a
              className="button button--light"
              href={repositoryUrl}
              target="_blank"
              rel="noreferrer"
            >
              View Workflo on GitHub <span aria-hidden="true">↗</span>
            </a>
            <Link className="button button--quiet" href="/product">
              Explore the product
            </Link>
          </div>
          <div className="closing-panel__index">WF / QA / 001</div>
        </div>
      </section>

      <RunCustomizer />
    </>
  );
}
