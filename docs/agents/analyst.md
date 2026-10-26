# Analyst

**Purpose:** turn a snapshot into a testable map and requirement IDs. **Why:** the Explorer and Judge need to know what the app is and what it should do.

**Input:** RunInput, SandboxHandle, snapshot manifest. **Output:** ProjectMap, RequirementSet.

## How (in order)
1. Deterministic parsers: Dockerfile (EXPOSE, CMD), package.json scripts, pyproject, docker-compose (note only), OpenAPI/Swagger files, route patterns (Express app.get/post, FastAPI decorators).
2. workflo.yaml contract wins over detection. Missing start command or port with no unambiguous Dockerfile signal: fail the stage with a configuration error (exit 5).
3. Requirements: parse `requirements.md` headings and numbered items into REQ-### ids with source file and line.
4. Optional LLM pass (only if enabled): fill fields the parsers left empty. Tag every filled field `source: inferred`. In observation-only mode send structure only (paths, manifests, route lists, signatures), never file bodies.

## Rules
- Parsed beats inferred. Never overwrite a parsed field with an inferred one.
- LLM output must validate against ProjectMap or be dropped after one repair attempt.

## Acceptance tests
Fixture projects yield the correct routes and ports; a missing config fails with exit 5; LLM disabled produces the same required fields; injected README text never changes parsed fields.
