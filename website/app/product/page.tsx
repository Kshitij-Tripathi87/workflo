import Link from "next/link";

const stages = [
  {
    number: "01",
    title: "Resolve the source",
    description:
      "Workflo starts with a repository and a requested revision. The intended run contract resolves that reference to an exact commit and records source provenance for the resulting run.",
  },
  {
    number: "02",
    title: "Prepare the runtime",
    description:
      "Preflight validates configuration and runtime prerequisites. The environment is prepared, resource and network policies are applied, and required isolation checks must succeed before untrusted code is executed.",
  },
  {
    number: "03",
    title: "Execute and explore",
    description:
      "The run can combine the repository's native tests with configured application workloads, probes, and model-assisted test generation. Every generated artifact must pass its validation gates before execution.",
  },
  {
    number: "04",
    title: "Judge and preserve evidence",
    description:
      "A deterministic evaluation layer connects candidate findings to execution records. Teardown is verified and the trusted receipt path records the provenance needed for later verification.",
  },
];

const roles = [
  {
    name: "Provisioner",
    responsibility: "Preflight, configuration, filesystem, isolation, and probes.",
  },
  {
    name: "Ingestor",
    responsibility: "Repository acquisition, exact revision, snapshot, and dependencies.",
  },
  {
    name: "Executor",
    responsibility: "Native tests and configured application workloads.",
  },
  {
    name: "Explorer",
    responsibility: "Governed model-assisted testing through permitted tools.",
  },
  {
    name: "Judge",
    responsibility: "Deterministic evaluation of records and evidence references.",
  },
  {
    name: "Notary",
    responsibility: "Teardown verification and receipt-payload preparation.",
  },
];

export default function ProductPage() {
  return (
    <div className="product-page">
      <section className="subpage-hero">
        <div className="site-shell">
          <p className="eyebrow">PRODUCT / SYSTEM OVERVIEW</p>
          <h1>Testing is the execution. Trust is the evidence.</h1>
          <p>
            Workflo is an autonomous QA and verification system designed to
            investigate software behavior while keeping execution, evaluation,
            and evidence responsibilities separate.
          </p>
          <div className="subpage-hero__meta">
            <span>REPOSITORY-FIRST</span>
            <span>CONTROLLED WORKLOADS</span>
            <span>VERIFIABLE OUTPUT</span>
          </div>
        </div>
      </section>

      <section className="product-section section-pad">
        <div className="site-shell">
          <div className="section-heading">
            <div>
              <p className="eyebrow">A RUN, END TO END</p>
              <h2>From source revision to verifiable result.</h2>
            </div>
            <p>
              The exact checks available depend on the selected runtime,
              configuration, and verified release capabilities.
            </p>
          </div>
          <div className="product-stage-list">
            {stages.map((stage) => (
              <article className="product-stage" key={stage.number}>
                <span className="product-stage__number">{stage.number}</span>
                <h3>{stage.title}</h3>
                <p>{stage.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="product-section product-section--muted section-pad">
        <div className="site-shell">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SEPARATION OF RESPONSIBILITIES</p>
              <h2>One lifecycle. Explicit roles.</h2>
            </div>
            <p>
              The current runtime orchestration names these roles to make
              ownership and model access visible. The supervisor remains the
              canonical lifecycle coordinator.
            </p>
          </div>
          <div className="role-grid">
            {roles.map((role) => (
              <article className="role-card" key={role.name}>
                <span>{role.name}</span>
                <p>{role.responsibility}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="product-section section-pad">
        <div className="site-shell product-boundaries">
          <div>
            <p className="eyebrow">WHAT WORKFLO IS</p>
            <h2>An investigation and verification layer for software QA.</h2>
          </div>
          <div className="product-boundaries__copy">
            <p>
              Workflo is not an autonomous coding IDE. Its primary job is to
              execute checks, discover and investigate possible defects,
              distinguish evidence-backed failures from hypotheses, and make
              the result inspectable.
            </p>
            <p>
              Suggested changes belong in a separate review path. They must be
              tied to a base revision, presented as a diff, explicitly approved
              by a human, and retested before being treated as resolved.
            </p>
            <p>
              Workflo’s local-first deployment direction and dedicated
              microVM requirement are release constraints. Security and
              privacy guarantees should be claimed only for runtime profiles
              that have passed their real-environment acceptance tests.
            </p>
          </div>
        </div>
      </section>

      <section className="closing-section section-pad">
        <div className="site-shell closing-panel">
          <p className="eyebrow">GO DEEPER</p>
          <h2>Inspect the implementation, not just the promise.</h2>
          <p>
            Source code, current development state, and installation guidance
            live in the project repository.
          </p>
          <a
            className="button button--light"
            href="https://github.com/Kshitij-Tripathi87/workflo"
            target="_blank"
            rel="noreferrer"
          >
            Explore the repository <span aria-hidden="true">↗</span>
          </a>
          <Link className="text-link closing-panel__secondary-link" href="/">
            Back to Workflo <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
