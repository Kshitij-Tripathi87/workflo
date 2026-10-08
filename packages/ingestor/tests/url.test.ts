import { describe, expect, it } from "vitest";
import { parseRepoUrl } from "../src/git";

describe("parseRepoUrl", () => {
  it("github https", () => {
    expect(parseRepoUrl("https://github.com/psf/requests")).toEqual({
      provider: "github",
      url: "https://github.com/psf/requests.git",
      owner: "psf",
      repo: "requests",
    });
    expect(parseRepoUrl("https://github.com/psf/requests.git").repo).toBe("requests");
  });

  it("github ssh", () => {
    expect(parseRepoUrl("git@github.com:org/repo")).toEqual({
      provider: "github",
      url: "git@github.com:org/repo.git",
      owner: "org",
      repo: "repo",
    });
  });

  it("local path is provider git", () => {
    const parsed = parseRepoUrl("C:\\tmp\\repo");
    expect(parsed.provider).toBe("git");
    expect(parsed.url).not.toContain("\\");
  });

  it("rejecting nothing here: malformed github path falls back to git provider", () => {
    expect(parseRepoUrl("https://github.com/just-owner").provider).toBe("git");
  });
});
