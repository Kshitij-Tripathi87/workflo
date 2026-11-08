"use client";

import { useEffect, useMemo, useState } from "react";

type RunMode = "native" | "deep" | "aggressive";

const modeLabels: Record<RunMode, string> = {
  native: "Native test run",
  deep: "Deep exploration",
  aggressive: "Aggressive exploration",
};

export function RunCustomizer() {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<RunMode>("deep");
  const [security, setSecurity] = useState(true);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1100px)");
    setIsOpen(desktop.matches);
  }, []);

  const stages = useMemo(() => {
    const items = [
      "Preflight and configuration",
      "Repository snapshot",
      "Dependency preparation",
      mode === "native" ? "Native test execution" : "Native tests and app checks",
    ];

    if (mode !== "native") {
      items.push(
        mode === "deep"
          ? "Governed application exploration"
          : "Extended fuzz and property probes"
      );
    }

    if (security) items.push("Configured security checks");

    items.push("Evidence review and teardown", "Receipt and report");

    return items;
  }, [mode, security]);

  const reset = () => {
    setMode("deep");
    setSecurity(true);
  };

  return (
    <aside
      className={
        isOpen ? "run-customizer is-open" : "run-customizer is-minimized"
      }
      aria-label="Sample QA run configurator"
    >
      {isOpen ? (
        <div className="run-customizer__panel">
          <div className="run-customizer__header">
            <div>
              <p className="run-customizer__eyebrow">INTERACTIVE PREVIEW</p>
              <h2>Configure a run</h2>
              <p>Explore how a QA profile changes the execution plan.</p>
            </div>
            <button
              className="run-customizer__icon-button"
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Minimize run configurator"
              title="Minimize"
            >
              <span aria-hidden="true">−</span>
            </button>
          </div>

          <div className="run-customizer__field">
            <label htmlFor="workflo-run-mode">Testing profile</label>
            <select
              id="workflo-run-mode"
              value={mode}
              onChange={(event) => setMode(event.target.value as RunMode)}
            >
              <option value="native">Native test run</option>
              <option value="deep">Deep exploration</option>
              <option value="aggressive">Aggressive exploration</option>
            </select>
          </div>

          <label className="run-customizer__toggle">
            <span>
              <strong>Security checks</strong>
              <small>Add the configured security check stage.</small>
            </span>
            <input
              type="checkbox"
              checked={security}
              onChange={(event) => setSecurity(event.target.checked)}
            />
            <span className="run-customizer__switch" aria-hidden="true" />
          </label>

          <div className="run-customizer__plan">
            <div className="run-customizer__plan-heading">
              <span>PLAN PREVIEW</span>
              <span>{stages.length} STAGES</span>
            </div>
            <ol>
              {stages.map((stage, index) => (
                <li key={stage}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {stage}
                </li>
              ))}
            </ol>
          </div>

          <div className="run-customizer__footer">
            <button type="button" onClick={reset}>
              Reset
            </button>
            <span>Preview only · no run is started</span>
          </div>
        </div>
      ) : (
        <button
          className="run-customizer__launcher"
          type="button"
          onClick={() => setIsOpen(true)}
          aria-expanded="false"
        >
          <span className="run-customizer__launcher-icon" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>
            <strong>Configure a QA run</strong>
            <small>Open interactive preview</small>
          </span>
          <span className="run-customizer__launcher-arrow" aria-hidden="true">
            ↗
          </span>
        </button>
      )}
    </aside>
  );
}
