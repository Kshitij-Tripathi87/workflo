import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = (relativePath: string) => readFileSync(new URL(relativePath, import.meta.url), "utf8");

describe("Workflo product surfaces", () => {
  it("documents installation channels and a first verification command", () => {
    const docs = source("../pages/Docs.tsx");
    expect(docs).toContain('id="installation"');
    expect(docs).toContain("PACKAGE REGISTRY");
    expect(docs).toContain("RELEASE ARCHIVE");
    expect(docs).toContain("CONTAINER IMAGE");
    expect(docs).toContain("FIRST VERIFICATION");
    expect(docs).toContain("Copy package command");
    expect(docs).toContain("Search API & docs");
    expect(docs).toContain("docs-release-notes");
    expect(docs).toContain("Latest product updates.");
    expect(docs).toContain("Copy release command");
    expect(docs).toContain("Copy container command");
    expect(docs).toContain("Copy first-run command");
    expect(docs).toContain("Start with one test.");
    expect(docs).toContain("Other installation paths");
    expect(docs).toContain('id="how-it-works"');
    expect(docs).toContain("Open local request preview");
  });

  it("keeps the QA Console empty until a real workspace is connected", () => {
    const dashboard = source("../pages/Dashboard.tsx");
    expect(dashboard).toContain("No test runs yet.");
    expect(dashboard).not.toContain("WF-4492");
    expect(dashboard).not.toContain("98.4%");
    expect(dashboard).not.toContain("128");
    expect(dashboard).toContain("Create your first test run");
  });

  it("requires consent and supports success feedback and keyboard or outside dismissal", () => {
    const home = source("../pages/Home.tsx");
    expect(home).toContain('id="trial-consent"');
    expect(home).toContain('href="/privacy"');
    expect(home).toContain('target="_blank"');
    expect(home).toContain("WORK_EMAIL_PATTERN");
    expect(home).toContain("Email format looks good.");
    expect(home).toContain("Please confirm consent before requesting a trial.");
    expect(home).toContain("Thank you.");
    expect(home).toContain("onPointerDownOutside");
    expect(home).toContain("onEscapeKeyDown");
  });
});
