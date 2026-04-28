# Rust Port Implementation Plan (Apr 2026)

**Status:** Planning phase (Phase 0 – Audit)  
**Owner:** Ben (system design)  
**Last updated:** 2026-04-28  
**Target:** Specification-first, parallel-first port from Python to Rust/TypeScript

---

## Overview

Reimplement DUNE APA production system (dune_winder + dune_tension) in Rust/TypeScript, prioritizing:

1. **Specification-first** — Allium specs are source of truth, not Python
2. **Type-safe** — Rust runtime, TypeScript UI, exhaustive contracts
3. **Zero duplication** — shared domain model (geometry, PLC, math)
4. **Skeptical of Python** — verify math/logic against first principles
5. **Preserve operator behavior** — Python UI/workflows are authoritative

---

## Master Plan

See `.harness/plans/type-safety-first-port.json` for complete phase breakdown.

**Quick summary:**
- **Phase 0:** Audit — cross-reference Allium specs vs. Python implementation
- **Phase 1:** Workspace setup — Cargo workspace, crates skeleton
- **Phase 2:** Domain model types — shared geometry, PLC, math types in Rust
- **Phase 3:** Golden parity tests — Python ↔ Rust comparison harnesses
- **Phase 5:** Offline calculations — geometry, recipes, motion planning
- **Phase 7:** Winder state machine — exhaustive state enums
- **Phase 6:** Tension engine — audio, FFT, inference
- **Phase 8:** PLC communication — gated on hardware spike
- **Phase 4/9:** UI — SvelteKit screens, Tauri apps

---

## Current Phase: 0 (Audit)

### What We're Doing

**Cross-reference Allium specs (Apr 26-27) against Python implementation.**

Produce verification documents showing:
- ✅ Where Python matches Allium (correct)
- ❓ Where Python deviates (needs decision)
- ❌ Where Python misses Allium logic (not implemented)
- 🐛 Where spec reveals Python bug (spec error, not impl bug)

### Subtasks

**0.0:** Verify PLC & head-transfer (winder-states-safety.allium + head-transfer.allium)
- Cross-check: PLCController state transitions vs. plc_logic.py
- Cross-check: ActuatorState sensor fusion vs. head.py
- Cross-check: G206/G106 transfer protocols vs. head.py implementation
- Output: `docs/exec-plans/audit-results/plc-and-head-verification.md`

**0.1:** Verify geometry (uv-layer-geometry.allium)
- Cross-check: Pin ranges, segment formulas, wrap-side classification
- Cross-check: Python geometry.py against Allium canonical formulas
- Verify: dune_tension uses same geometry (no duplication)
- Output: `docs/exec-plans/audit-results/geometry-verification.md`

**0.2:** Verify winder state machine (winder-states-safety.allium)
- Cross-check: RuntimeController / PLCController state dispatch
- Cross-check: Operator workflow rules vs. Python state_machine.py
- Cross-check: Safety interlocks and diagnostics
- Output: `docs/exec-plans/audit-results/winder-state-verification.md`

**0.3:** Verify tension measurement (tension-measurement.allium)
- Cross-check: Measurement modes (legacy, sweep, rescue) vs. Python tensiometer.py
- Cross-check: Result acceptance criteria and logic
- Cross-check: Streaming candidate aggregation and rescue workflow
- Output: `docs/exec-plans/audit-results/tension-measurement-verification.md`

**0.6:** Synthesize findings
- Create: `docs/exec-plans/audit-results/DOMAIN_MODEL_VERIFICATION.md`
- Summary: Which Allium rules are implemented in Python? Where are deviations?
- Decision: For each deviation, recommend port strategy (follow spec, follow Python, fix both)

### Timeline

- **Phase 0.0-0.5:** Individual verification audits (parallel, 1-2 weeks each)
- **Phase 0.6:** Synthesis and decision document (1 week)
- **Estimated completion:** 2026-05-15

---

## Success Criteria

**Phase 0 is complete when:**

1. ✅ All four Allium specs have verification documents showing:
   - List of entities and rules with Python implementation status
   - Deviations documented with rationale
   - Decision: port follows spec or Python (with reasoning)

2. ✅ DOMAIN_MODEL_VERIFICATION.md summarizes:
   - What's implemented correctly
   - What deviates (and why it matters)
   - What's missing (and priority for port)

3. ✅ No contradictions remain between docs:
   - Allium spec is authoritative
   - Python deviations are documented
   - Port strategy is clear for each module

---

## Next Phases (Preview)

### Phase 1: Workspace Setup
- Add Cargo.toml (root workspace)
- Create crates/ skeleton
- Create calibration/ and tests/golden/ directories

### Phase 2: Domain Model Types
- Define shared types in Rust (geometry, PLC structures, math constants)
- Generate TypeScript bindings
- All shared logic in one crate (no duplication)

### Phase 3: Golden Parity Tests
- Write comparison harnesses (Python ↔ Rust)
- Establish verification for geometry, recipes, motion, state machine
- Baseline for future verification

### Phase 5-9: Implementation
- Offline calculations (recipes, motion, geometry)
- Winder state machine (exhaustive enums)
- Tension engine (audio, FFT, inference)
- PLC communication (after hardware spike)
- UI consolidation (SvelteKit, Tauri)

---

## Authority & Staleness

| Source | Status | Trust |
|--------|--------|-------|
| Allium specs | ✅ CURRENT (Apr 26-27) | **AUTHORITATIVE** |
| This exec plan | ✅ CURRENT | **AUTHORITATIVE** |
| Python code | Reference (may lag/diverge) | To be verified |
| Markdown /docs/dune_*/planning | ❌ STALE (Mar 29) | IGNORE |

**See [`docs/STALENESS.md`](../../STALENESS.md) for authority framework.**

---

## Related Documents

- **Master plan:** `.harness/plans/type-safety-first-port.json`
- **Allium specs:** `docs/design-docs/allium-specs/index.md`
- **Architecture:** `docs/design-docs/architecture/`
- **Audit results:** `docs/exec-plans/audit-results/`
- **Authority guide:** `docs/STALENESS.md`
