# Cortex Website Plan — Minimal, Plain-English, No Fluff

## Company & Product Hierarchy (critical)

**Cortex** = the company
**Cortex Nexus** = the flagship product (enterprise operational intelligence platform)
**workflo** = a Cortex product (sandboxed test execution with cryptographic receipts)
**cortex ASTRA** = a Cortex product (mission design orchestration)

The website must make this hierarchy explicit everywhere: Cortex is the company name. Nexus is the primary product. workflo and Astra are additional products under the Cortex brand.

---

## Design Requirements (non-negotiable)

- **Color scheme**: Flat colors only. One accent color used sparingly for CTAs and links. No gradients. No glassmorphism. No purple/blue combinations.
- **Typography**: One good sans-serif font (e.g., Inter, System UI, or IBM Plex Sans). Proper spacing. Line height at least 1.6 for body text. Headings clearly hierarchical.
- **Imagery**: Real screenshots of the workflo CLI, Nexus dashboard, ASTRA interface. Real numbers from the codebase and early partners. No floating orbs, no abstract "technology" shapes, no fake testimonials.
- **No template junk**: No marquee blurbs, no gradient backgrounds masquerading as "hero sections", no generic "we power the future" copy.
- **Responsive**: Works on mobile and desktop. No hidden overflow. No breakpoints that produce terrible layouts.

---

## Site Structure

### 1. Homepage (`/`)

**Hero — two-line maximum, plain English:**
```
Cortex — enterprise intelligence platforms

Cortex Nexus: operational intelligence for supply chains
workflo: sandboxed test execution with cryptographic receipts
cortex ASTRA: mission design, tool-agnostic
```

**Primary CTA group (three buttons, flat design):**
- [Learn about Nexus] — the flagship product
- [Learn about workflo] — sandboxed test execution
- [Learn about ASTRA] — mission design orchestration

**Below the hero (flat layout, no gradients):**

**Cortex Nexus — what it does:**
Nexus reads enterprise data (ERP, WMS, TMS, supplier records, BOMs, etc.) and builds an operational graph. It shows how disruptions propagate, simulates alternative futures, and determines coordinated mitigation strategies. When authorized, it can execute decisions into enterprise systems.

*Real numbers (early partner demo, supplier disruption chain):*
- Supplier disruption chain: early partner demo showed multi-node propagation through operational graph
- First stockout prediction: 36 hours from supplier delay (partner data, not invented)
- Revenue exposure: calculated from customer order data (partner provided numbers, not invented)
- Note: Exact numbers vary by customer deployment — these are demo illustrative values

**workflo — what it does:**
workflo runs your test suite (pytest, Playwright) inside an isolated Docker container. The container has no network access, a size-limited RAM filesystem, resource limits (CPU, memory, timeout). After the run, the container is killed, the RAM filesystem is unmounted, and both are confirmed gone. Test results, teardown proof, and a canary check (blocked outbound request) are bundled and signed with Ed25519. You get a receipt that anyone can verify with just a public key — no trust in the tool required.

*Real numbers (proven against live Docker daemon):*
- 1,930 real tests executed against a public repository
- Container and filesystem independently confirmed removed after run
- Canary check: outbound HTTPS request to example.com confirmed blocked
- Receipt signature verified valid on independent verification

**cortex ASTRA — what it does:**
ASTRA takes a mission objective and constraints (target body, launch window, payload, duration, fuel limits, communication limits, risk level) and returns a validated, explainable mission plan. It runs in two modes:
- **ASTRA Core** — uses built-in physics and optimization engines
- **ASTRA Connect** — orchestrates a customer's existing tools (GMAT, STK, FreeFlyer, proprietary) instead of replacing them

*Market data (real, not invented):*
- Space mission design software TAM: $1.24B (2024), projected $3.18B by 2033 at 10.8% CAGR
- APAC growing fastest at 13.2% CAGR
- Verified competitors: Sedaro (defense/IC-embedded digital twin), WarpWare (NATO DIANA selected), Exotrail's ExoOPS, Cognitive Space's CNTIENT
- Position: tool-agnostic orchestrator — the only one explicitly making that claim

---

### 2. Products page (`/products`)

- High-level overview of all three products
- Links to individual product pages
- No comparison tables with made-up numbers. Just product names + one-line descriptions, arranged under the Cortex brand umbrella.

---

### 3. Product pages

#### `/products/nexus` — Cortex Nexus (the flagship)

**Headline:**
Cortex Nexus — enterprise operational intelligence platform

**What it does (plain English):**
Nexus reads enterprise data and builds an operational graph. It shows how disruptions propagates, simulates alternative futures, and determines coordinated mitigation strategies. When authorized, it can execute decisions into enterprise systems.

**Key capabilities (real, not made-up):**
- Operational graph: maps relationships between suppliers, components, warehouses, factories, products, customer orders
- World state: current conditions (inventory levels, lead times, capacity usage)
- Digital twin: simulate "do nothing" vs. "expedite" vs. "transfer" scenarios
- Multi-agent deliberation: specialized agents propose actions, executive synthesis resolves conflicts
- Policy engine: organizational constraints (spending authority, approved suppliers, safety stock) block policy-violating recommendations
- Human approval: decision card shows recommended action, cost, revenue impact, risk level; operator approves/rejects/modifies
- Enterprise execution: authenticated, authorized, idempotent adapters for ERP, WMS, TMS, procurement systems
- Decision memory: records what was predicted vs. what actually happened → learning flywheel

**Who it's for:** COO, Supply Chain Leader, Procurement, Logistics, Inventory, Manufacturing, CIO/CTO, CFO

**Real numbers (from early partners / hackathon demo):**
- Supplier disruption chain: early partner demo showed multi-node propagation through operational graph (illustrative example)
- First stockout prediction: 36 hours from supplier delay (partner data, not invented)
- Revenue exposure: calculated from customer order data (partner provided numbers, not invented)
- Note: Exact numbers vary by customer deployment — these are demo illustrative values

**Screenshot:** Real Nexus dashboard mockup (not abstract). Show the operational graph, world state panel, and decision card. If using real data, annotate with "example data from partner."

#### `/products/workflo`

**Headline:**
workflo — sandboxed test execution with cryptographic receipts

**What it does (plain English):**
workflo runs your test suite (pytest, Playwright) inside an isolated Docker container. The container has no network access, a size-limited RAM filesystem, resource limits (CPU, memory, timeout). After the run, the container is killed, the RAM filesystem is unmounted, and both are confirmed gone. Test results, teardown proof, and a canary check (blocked outbound request) are bundled and signed with Ed25519. You get a receipt that anyone can verify with just a public key — no trust in the tool required.

**How it works (4 steps, plain English):**

1. **Container spin-up** — Docker container with network_mode=none, read-only root filesystem, tmpfs mount at /workspace. Resource limits enforced.
2. **Repo clone** — Target repo cloned into tmpfs. Nothing touches persistent disk.
3. **Test execution** — pytest or Playwright runs inside the sealed container. Probe groups: surface (--test), security (--security), deep (--deep-test), aggressive (--aggressive-test), web (--web).
4. **Teardown + signing** — Container killed, tmpfs unmounted. Results + teardown proof + canary outcome + probe results bundled and signed. Receipt written to file or printed to stdout.

**CLI examples (real commands from the codebase):**

```
workflo run --repo <url> --test --security
workflo run --repo <url> --deep-test
workflo run --repo <url> --web --start-command "python app.py" --port 5000
workflo verify --receipt receipt.json --pubkey pubkey.pem
workflo keygen --output pubkey.pem --force
```

**Real numbers (from proven runs against live Docker daemon):**
- 1,930 real tests executed against a public repository in a live sandboxed run
- Container and filesystem independently confirmed removed after run
- Canary check: outbound HTTPS request to example.com confirmed blocked (proves network isolation)
- Receipt signature verified valid on independent verification

**Who it's for:** Dev teams, QA engineers, security teams, CI/CD pipelines needing verified test execution

**Screenshot:** Real workflo CLI output showing a run result, or the dashboard run view. Not abstract diagrams. If showing CLI output, censor any secrets or tokens.

#### `/products/astra` — cortex ASTRA

**Headline:**
cortex ASTRA — mission design orchestration

**What it does (plain English):**
ASTRA takes a mission objective and constraints (target body, launch window, payload, duration, fuel limits, communication limits, risk level) and returns a validated, explainable mission plan. It runs in two modes:

- **ASTRA Core** — uses built-in physics and optimization engines
- **ASTRA Connect** — orchestrates a customer's existing tools (GMAT, STK, FreeFlyer, proprietary) instead of replacing them

**How it works (plain English pipeline, 9 steps):**

1. **Intake** — mission objective + constraints entered
2. **Mission decomposition** — broken into sub-problems (trajectory, sequencing, resource allocation)
3. **Candidate architecture generation** — candidate paths identified
4. **Capability Registry lookup** — each required capability routed to whatever's available: customer's tool or ASTRA's fallback engine
5. **Constraint checking** — deterministic: delta-v, comms, power. Not AI-guessed.
6. **Risk flagging** — quantified against thresholds
7. **Optimization** — best option selected
8. **LLM trade-off explanation** — strictly grounded in computed numbers, not hallucinated
9. **Final report** — trajectory options, resource estimates, timeline, risk summary, recommended plan

**Mission Dependency Graph** — changing one input re-runs only the correct downstream steps, not the whole pipeline.

**Who it's for:** Indian NewSpace startups, university cubesat programs, emerging space-capable nations, defense/dual-use programs

**Real numbers (market data, not invented):**
- Space mission design software TAM: $1.24B (2024), projected $3.18B by 2033 at 10.8% CAGR
- APAC growing fastest at 13.2% CAGR
- Verified competitors: Sedaro (defense/IC-embedded digital twin), WarpWare (NATO DIANA selected), Exotrail's ExoOPS, Cognitive Space's CNTIENT
- Position: tool-agnostic orchestrator — the only one explicitly making that claim

**Screenshot:** Real ASTRA interface mockup showing mission plan output, capability registry, or constraint results. Not abstract.

---

### 4. About page (`/about`)

- Company mission (plain English, no fluff). Emphasize: Cortex builds enterprise intelligence platforms. Nexus is the flagship product. workflo and Astra are additional products.
- Team (real names, no fake bios)
- Clarify the Cortex/Nexus/workflo/Astra relationship: Cortex the company, Nexus the flagship product, workflo and Astra as additional products.

---

### 5. Docs page (`/docs`)

- Getting started guides for each product
- CLI reference for workflo (real commands from the codebase)
- API endpoints (real endpoints from the control plane)
- Architecture diagrams (actual system diagrams, not generic boxes). Show the Cortex/Nexus/workflo/Astra relationship.

---

### 6. Contact page (`/contact`)

- Contact form (functional or simple placeholder)
- Email address
- GitHub link (to the actual repository)

---

## Technical Stack (minimal, no vendor lock-in)

- **Framework**: Next.js 14 with App Router (or static HTML if the team prefers). Keep it simple — no unnecessary complexity.
- **CSS**: Tailwind CSS with custom base. No UI component library that brings gradients/glassmorphism by default.
- **Font**: One sans-serif (Inter, System UI, or IBM Plex Sans). Import via `<link>` or host locally. Use proper heading hierarchy (h1, h2, h3).
- **Deployment**: Vercel or self-hosted. Static HTML if possible — no build steps required for content changes.
- **Icons**: Line icons or custom. No decorative SVGs that add no information.

---

## Content Rules (strict, enforced)

1. **No "revolutionize", "empower", "transform", "synergy", "paradigm shift", "game-changing", "cutting-edge", "state-of-the-art", "world-class", "leading", "first-of-its-kind"**
2. **No fake testimonials**. If quoting a customer, use their real name and organization (or "early partner" anonymized).
3. **No floating orbs, abstract technology shapes, gradient backgrounds masquerading as "hero sections"**
4. **Every number must be traceable**. If it comes from a customer, say so: "customer provided numbers." If it's market data, cite the source. If it's from the codebase, say "proven against a live Docker daemon."
5. **No "world's best", "leading AI", "best-in-class" claims without proof**. Proof = real numbers, real screenshots, real CLI output.
6. **No animated elements that move without user interaction**. No autoplay, no auto-scrolling, no marquee.
7. **All links must have visible focus indicators**. Color contrast: minimum 4.5:1 for normal text, 3:1 for large text.
8. **Everywhere on the site, make the hierarchy explicit**: Cortex = company. Cortex Nexus = flagship product. workflo and cortex Astra = additional products. Do not confuse the reader.

---

## Open Questions (to resolve with user)

1. **Accent color**: One color only. Recommendation: muted teal (e.g., #0D9488) used sparingly for CTAs and links only. No gradients. User may choose a different single accent color, but must remain flat (no gradients) and used consistently across the site.
2. **Product priority order on homepage**: Which product leads? Nexus (flagship) should be first, then workflo, then Astra. Or user to specify order.
3. **Screenshots**: Do we use actual codebase/screenshots from the project, or create new mockups? If mockups, keep them flat, no gradients, no glassmorphism.
4. **Domain**: cortex.dev? cortex.io? User to provide.
5. **CTA text**: "Learn more" vs. "Try it" vs. something else. User to confirm. Keep it plain.
6. **Whether to include pricing**: If yes, simple tiers. If no, omit from MVP. If included, keep it flat — no gradient pricing bars.
7. **How explicitly to show the Cortex/Nexus/hierarchy**: Should the word "Cortex" always appear near "Nexus"? Should workflo and Astra always have "Cortex" prefix or tag? User to decide the branding approach.

---

## Validation Checklist

- [ ] Homepage hero conveys value proposition in plain English, no fluff words, hierarchy clear (Cortex = company, Nexus = flagship product, workflo + Astra = additional Cortex products)
- [ ] Three product sections use flat colors only, one accent color for CTAs only (no gradients)
- [ ] All numbers are traceable (from codebase, customers, or market data) and properly attributed with source
- [ ] No gradients, no glassmorphism, no purple/blue combinations anywhere on the site
- [ ] Typography: one font family, proper line height (>=1.6), readable measure, hierarchical headings (h1 > h2 > h3)
- [ ] Screenshots are real codebase output or flat mockups — no abstract "technology" imagery, no floating orbs, no glassmorphism
- [ ] No fake testimonials, no floating orbs, no template junk, no gradient backgrounds masquerading as features
- [ ] Mobile layout works — no horizontal scrolling, no cut-off text, focus order logical, visible focus indicators
- [ ] Focus indicators visible on all interactive elements, color contrast 4.5:1 minimum for normal text, 3:1 for large text
- [ ] About, Docs, Contact pages have plain English content, hierarchy explicitly stated (Cortex = company, Nexus = flagship, workflo + Astra = additional products)
- [ ] Open questions resolved or explicitly out of scope with user
- [ ] Every page makes the Cortex/Nexus/workflo/Astra hierarchy explicit without confusion — Cortex always identified as company name, Nexus as flagship product, workflo and Astra as Cortex products