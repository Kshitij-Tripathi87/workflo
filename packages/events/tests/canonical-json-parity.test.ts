import { createHash } from "node:crypto";
import { expect, it } from "vitest";
import golden from "../../workflo-schema/tests/fixtures/v1-golden.json";
import { canonicalJson } from "../src/hash-chain";

// Compatible inputs only: the legacy TS ledger's accepted input domain and
// bound record are not the Workflo v2 evidence-chain contract.
it.each(golden.canonical_json)(
  "matches Python canonical bytes for $name",
  ({ payload, canonical, digest }) => {
    const bytes = Buffer.from(canonicalJson(payload), "utf8");
    expect(bytes).toEqual(Buffer.from(canonical, "utf8"));
    expect(`sha256:${createHash("sha256").update(bytes).digest("hex")}`).toBe(
      digest
    );
  }
);
