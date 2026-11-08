"use client";

import { useEffect, useRef, useState } from "react";

const stages = [
  {
    eyebrow: "01 / SOURCE",
    title: "Start with a pinned source.",
    description:
      "Workflo resolves the requested revision, records its identity, and prepares a stable snapshot. The run should always have a clear answer to the question: which code was tested?",
    label: "Repository snapshot",
    detail: "Commit identity · source snapshot · provenance",
  },
  {
    eyebrow: "02 / BOUNDARY",
    title: "Prepare the execution boundary.",
    description:
      "The runtime validates its configuration, provisions the selected environment, applies the run policy, and checks the controls required for that execution profile.",
    label: "Policy and isolation",
    detail: "Runtime preflight · network policy · resource limits",
  },
  {
    eyebrow: "03 / EXERCISE",
    title: "Exercise the software, not just the checklist.",
    description:
      "Native tests remain the foundation. Where configured and supported, Workflo can add application, API, browser, and model-assisted probes to investigate behavior beyond the existing suite.",
    label: "QA workloads",
    detail: "Native tests · application probes · governed exploration",
  },
  {
    eyebrow: "04 / VERIFY",
    title: "Make every conclusion traceable.",
    description:
      "Results are evaluated against execution records, temporary resources are torn down, and the run produces a report with evidence references and receipt provenance.",
    label: "Evidence and receipt",
    detail: "Deterministic review · teardown · signed receipt",
  },
];

export function ExecutionStory() {
  const sectionRef = useRef<HTMLElement | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    let frame = 0;

    const update = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        const rect = section.getBoundingClientRect();
        const travel = Math.max(1, section.offsetHeight - window.innerHeight);
        const next = Math.min(1, Math.max(0, -rect.top / travel));
        setProgress((current) =>
          Math.abs(current - next) < 0.008 ? current : next
        );
      });
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  const activeIndex = Math.min(3, Math.floor(progress * stages.length));
  const activeStage = stages[activeIndex];
  const rotateX = 13 - progress * 11;
  const rotateY = -19 + progress * 17;
  const rotateZ = 5 - progress * 5;
  const lift = 18 - progress * 36;
  const capsuleTransform =
    "perspective(1400px) rotateX(" +
    rotateX +
    "deg) rotateY(" +
    rotateY +
    "deg) rotateZ(" +
    rotateZ +
    "deg) translateY(" +
    lift +
    "px)";

  return (
    <section
      className="execution-story"
      id="workflow"
      ref={sectionRef}
      aria-labelledby="execution-story-title"
    >
      <div className="execution-story__sticky">
        <div className="site-shell execution-story__layout">
          <div className="execution-story__copy">
            <p className="eyebrow">A RUN WITH A TRACEABLE LIFECYCLE</p>
            <p className="execution-story__step">{activeStage.eyebrow}</p>
            <h2 id="execution-story-title">{activeStage.title}</h2>
            <p className="execution-story__description">
              {activeStage.description}
            </p>
            <div className="execution-story__detail">
              <span className="execution-story__detail-mark" aria-hidden="true" />
              {activeStage.detail}
            </div>
            <div className="execution-story__progress" aria-hidden="true">
              {stages.map((stage, index) => (
                <span
                  className={
                    index <= activeIndex
                      ? "execution-story__progress-segment is-active"
                      : "execution-story__progress-segment"
                  }
                  key={stage.eyebrow}
                />
              ))}
            </div>
            <p className="execution-story__disclaimer">
              Product workflow illustration. The active runtime and available
              checks depend on the selected Workflo build and configuration.
            </p>
          </div>

          <div className="execution-visual" aria-hidden="true">
            <div className="execution-visual__halo" />
            <div className="execution-visual__orbit execution-visual__orbit--one" />
            <div className="execution-visual__orbit execution-visual__orbit--two" />
            <div
              className="execution-capsule"
              style={{ transform: capsuleTransform }}
            >
              <div className="execution-capsule__edge" />
              <div className="execution-capsule__top">
                <span className="execution-capsule__brand">
                  <span className="brand-mark brand-mark--small">W</span>
                  WORKFLO / EXECUTION
                </span>
                <span className="execution-capsule__top-meta">
                  CONTROLLED RUN
                </span>
              </div>
              <div className="execution-capsule__screen">
                <div className="execution-capsule__toolbar">
                  <span />
                  <span />
                  <span />
                  <b>RUN OVERVIEW</b>
                  <small>ILLUSTRATIVE</small>
                </div>
                <div className="execution-capsule__screen-body">
                  <div className="execution-capsule__screen-heading">
                    <span>WORKSPACE / QA</span>
                    <span className="execution-capsule__revision">
                      REVISION PINNED
                    </span>
                  </div>
                  <div className="execution-capsule__main-label">
                    {activeStage.label}
                  </div>
                  <div className="execution-capsule__main-detail">
                    {activeStage.detail}
                  </div>
                  <div className="execution-capsule__terminal">
                    <div>
                      <span className="terminal-prompt">$</span>
                      <span>workflo run</span>
                    </div>
                    <div>
                      <span className="terminal-muted">stage</span>
                      <strong>{activeStage.eyebrow.slice(5)}</strong>
                    </div>
                    <div>
                      <span className="terminal-muted">record</span>
                      <strong>evidence-linked</strong>
                    </div>
                  </div>
                  <div className="execution-capsule__footer">
                    <span>WORKFLO / QA PIPELINE</span>
                    <span>STAGE {activeIndex + 1} OF 4</span>
                  </div>
                </div>
              </div>
              <div className="execution-capsule__base">
                <span />
                <span />
                <span />
              </div>
            </div>
            <div className="execution-visual__caption">
              <span className="execution-visual__caption-dot" />
              ANATOMY OF A WORKFLO RUN
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
