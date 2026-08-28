import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { WORKFLO_HERO } from "./workfloHero";

describe("Workflo hero messaging", () => {
  it("keeps the product promise concise and evidence-led", () => {
    expect(WORKFLO_HERO.tagline).toBe("QA you can verify.");
    expect(WORKFLO_HERO.description).toBe("Isolated runs. Evidence you can review.");
  });

  it("retains a concise static hero background and staged entry treatment", () => {
    const homeSource = readFileSync(new URL("../pages/Home.tsx", import.meta.url), "utf8");
    const styles = readFileSync(new URL("../index.css", import.meta.url), "utf8");

    expect(homeSource).toContain("--hero-scroll-y");
    expect(homeSource).toContain("minimal-hero__loader-orbit");
    expect(homeSource).toContain("workflo-sandbox-immersive-hero_b63d7110.jpg");
    expect(homeSource).not.toContain("workflo-sandbox-hero-motion_36908eda.mp4");
    expect(homeSource).not.toContain("<video");
    expect(homeSource).toContain("hero-reveal");
    expect(homeSource).not.toContain("typewriter-tagline");
    expect(homeSource).not.toContain("MOTION: ON");
    expect(homeSource).not.toContain("AUTONOMOUS QA</small>");
    expect(homeSource).toContain("updatePointer");
    expect(homeSource).toContain("--hero-image-x");
    expect(homeSource).toContain("renderPointerDepth");
    expect(homeSource).toContain("--hero-image-tilt-x");
    expect(homeSource).toContain("Motion: {reducedMotion ? \"Off\" : \"On\"}");
    expect(homeSource).toContain("ultrawideTiltFactor");
    expect(homeSource).toContain("--hero-glare-opacity");
    expect(homeSource).not.toContain("<SandboxScene");
    expect(homeSource).toContain("/api/trial-signups");
    expect(homeSource).toContain("<Dialog open={trialOpen}");
    expect(homeSource).toContain("trialConsentAttempted");
    expect(homeSource).toContain("Please confirm consent before requesting a trial.");
    expect(styles).toContain("workflo-sandbox-immersive-hero_b63d7110.jpg");
    expect(styles).toContain(".minimal-hero__sandbox-poster");
    expect(styles).toContain("@keyframes workflo-hero-reveal");
    expect(styles).toContain("inset 5px 5px 12px");
    expect(styles).toContain("rotateX(var(--hero-image-tilt-x))");
    expect(styles).toContain(".minimal-hero__motion-toggle");
    expect(styles).toContain(".minimal-hero__glare");
    expect(styles).toContain(".docs-nav-block a:active");
    expect(styles).toContain(".docs-sidebar-changelog button:active");
    expect(styles).toContain(".minimal-hero__content.is-ready > h1");
    expect(styles).toContain(".motion-reduced .minimal-hero__content > *");
    expect(styles).toContain("@keyframes workflo-loader-orbit");
    expect(styles).toContain("@media (hover: hover) and (pointer: fine)");
    expect(styles).toContain("@media (min-width: 761px) and (max-width: 1100px)");
  });
});
