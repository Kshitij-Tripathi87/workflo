# Workflo Design Directions

## Three Possible Directions

### Theme Name: Instrument Panel Noir
**Very Brief Intro:** A deep-space control-plane environment defined by crisp frames, restrained technical grids, phosphor mint signals, and information surfaces that feel calibrated rather than decorative. It makes autonomy feel observable, governed, and precise.

**Probability:** 0.041

### Theme Name: Archive of Proof
**Very Brief Intro:** An editorial, documentation-led aesthetic that treats every test as an artifact: monochrome paper panels, dense annotation, and protocol-like composition. It makes verification feel durable and legible.

**Probability:** 0.073

### Theme Name: Quiet Laboratory
**Very Brief Intro:** A light, tactile research interface with ivory substrates, steel details, and rare electric-blue intervention. It conveys rigorous experimentation without visual aggression.

**Probability:** 0.026

## Chosen Approach: Instrument Panel Noir

### Design Movement
**Instrument Panel Noir** blends mid-century aerospace instrument design with contemporary developer infrastructure. The visual language treats Workflo as a trustworthy flight deck for autonomous quality assurance, not a chat novelty.

### Core Principles
1. **Evidence is the interface.** Every visual device should make state, ownership, or proof more legible.
2. **Precision over spectacle.** Decorative effects are limited; contrast, calibrated alignment, and technical density create confidence.
3. **Asymmetry with anchors.** Strong rails, offset content fields, and intentional empty space create rhythm without a generic centered composition.
4. **One active signal.** Mint is reserved for live, verified, and actionable states; muted blue and warm off-white carry the rest of the system.

### Color Philosophy
The site starts in near-black **graphite blue** to suggest a protected sandbox, rather than a generic void. Oxide blue and smoked metallic panels carry structural depth. **Verification Mint** appears only as a status signal or action affordance, creating an ownable visual shorthand for a receipt that has passed inspection. Warm-white type softens the otherwise engineered atmosphere for long-form reading.

### Layout Paradigm
The marketing page behaves like a **protocol trace**: a slim vertical index rail establishes the control plane, and individual sections branch from it at differing widths. The hero places the operating context on a wide left field and a live receipt surface on the right. Docs and Dashboard compress into a persistent navigation spine plus dense working panels.

### Signature Elements
- **Signal rails:** Hairline vertical and horizontal rules punctuated by tiny coordinate labels.
- **Receipt frames:** Steel-framed cards with subtle corner notches, status lights, and encoded metadata rows.
- **System paths:** Deliberate node-and-line diagrams that animate a test's movement from intent to sandbox to verifiable receipt.

### Interaction Philosophy
Interaction is operational and declarative. Buttons press inward, status lights breathe softly, and hover states expose a little more metadata instead of merely changing color. Navigation transitions should feel like moving across connected control surfaces, always retaining orientation.

### Animation
Reveal large areas with 420–600ms opacity and translate transitions using a crisp custom easing; keep interaction feedback under 180ms. Terminal lines and system paths should phase in sequentially, never type indefinitely. Live indicators may pulse at low amplitude. Use `prefers-reduced-motion` to remove all non-essential entrances and continuous signaling.

### Typography System
**Space Grotesk** drives headings and labels: wide, authoritative, and technical without falling into sci-fi cliché. **IBM Plex Mono** carries coordinates, test data, code, and secondary metadata. Headlines use tight tracking and strong weight contrast; prose gets a relaxed line height and no more than 68 characters per line.

### Brand Essence
**Workflo is the privacy-first autonomous QA agent for engineering teams that need testing they can independently verify.**

**Personality:** exacting, composed, transparent.

### Brand Voice
Headlines speak in concrete outcomes; CTAs use purposeful verbs; microcopy documents state without hype. Avoid promises that imply human qualities without proof.

> “Autonomy you can audit.”

> “Run the test. Keep the receipt.”

### Wordmark & Logo
The mark is a bold geometric **W formed by two nested execution paths**: three angular strokes enter, traverse, and resolve into a small verified node. It can stand alone as a square application glyph; the Workflo wordmark uses the custom-feeling density and open counters of Space Grotesk.

### Signature Brand Color
**Verification Mint — #8AF5C6.** This is Workflo’s unmistakable sign of a tested and verifiable outcome.

## Style Decisions

- **Protocol trace rule:** Every primary page includes a visible control-plane spine or coordinate rail that anchors surfaces and makes navigation feel like moving through one calibrated system.
- **Receipt-frame rule:** Key panels use Workflo’s receipt language—corner notches, metadata strips, status nodes, and hairline rails—rather than plain bordered cards.
- **Mint discipline rule:** Verification Mint `#8AF5C6` is reserved for verified states, primary actions, active navigation, and proof-critical words. Other emphasis comes from warm-white type, scale, and graphite structure.
