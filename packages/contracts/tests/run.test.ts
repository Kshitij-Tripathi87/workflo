import { describe, expect, it } from "vitest";
import lifecycle from "../../workflo-schema/schemas/v1/lifecycle-state.schema.json";
import outcome from "../../workflo-schema/schemas/v1/run-outcome.schema.json";
import golden from "../../workflo-schema/tests/fixtures/v1-golden.json";
import {
  LegacyRunStateSchema,
  LifecycleStateSchema,
  RunOutcomeV1Schema,
  RunStateSchema,
} from "../src";

const fullPass = golden.outcomes.full_pass.record;

describe("product lifecycle", () => {
  it("matches the Python export exactly", () => {
    expect(LifecycleStateSchema.options).toEqual(lifecycle.enum);
    for (const state of lifecycle.enum) {
      expect(LifecycleStateSchema.parse(state)).toBe(state);
    }
  });

  it("does not mistake legacy DB states for product states", () => {
    expect(RunStateSchema).toBe(LegacyRunStateSchema);
    expect(LegacyRunStateSchema.safeParse("INGESTING").success).toBe(true);
    expect(LegacyRunStateSchema.safeParse("CANCEL_REQUESTED").success).toBe(
      false
    );
    for (const state of LegacyRunStateSchema.options) {
      expect(LifecycleStateSchema.safeParse(state).success).toBe(
        lifecycle.enum.includes(state)
      );
    }
    expect(LifecycleStateSchema.safeParse("queued").success).toBe(false);
  });
});

describe("run outcome v1", () => {
  it("has the same fields and vocabularies as the Python export", () => {
    const { shape } = RunOutcomeV1Schema.innerType();
    expect(Object.keys(shape).sort()).toEqual(
      Object.keys(outcome.properties).sort()
    );
    expect(shape.execution_status.options).toEqual(
      outcome.$defs.ExecutionStatus.enum
    );
    expect(shape.qa_verdict.options).toEqual(outcome.$defs.QaVerdict.enum);
    expect(shape.trust_status.options).toEqual(
      outcome.$defs.TrustVerificationStatus.enum
    );
    for (const field of [
      shape.evidence_validation,
      shape.teardown_verification,
      shape.receipt_status,
    ]) {
      expect(field.options).toEqual(
        outcome.$defs.ComponentVerificationStatus.enum
      );
    }
  });

  it("matches required fields and defaults on valid wire input", () => {
    for (const key of Object.keys(fullPass)) {
      const record: Partial<typeof fullPass> = { ...fullPass };
      delete record[key as keyof typeof fullPass];
      expect(RunOutcomeV1Schema.safeParse(record).success, key).toBe(
        !outcome.required.includes(key)
      );
    }
    const {
      schema_version: _version,
      cancelled: _cancelled,
      ...required
    } = fullPass;
    expect(RunOutcomeV1Schema.parse(required)).toEqual({
      ...required,
      schema_version: outcome.properties.schema_version.default,
      cancelled: outcome.properties.cancelled.default,
    });
    expect(
      RunOutcomeV1Schema.safeParse({ ...fullPass, cancelled: "false" }).success
    ).toBe(false);
  });

  it.each(Object.entries(golden.outcomes))(
    "round-trips the Python record for %s",
    (_name, example) => {
      expect(RunOutcomeV1Schema.parse(example.record)).toEqual(example.record);
    }
  );

  it.each(golden.invalid_outcomes)("rejects $name", ({ base, overrides }) => {
    const { record } = golden.outcomes[base as keyof typeof golden.outcomes];
    expect(
      RunOutcomeV1Schema.safeParse({ ...record, ...overrides }).success
    ).toBe(false);
  });
});
