# System Architecture

**Status:** Specification-first port from Python to Rust/TypeScript (2026-04-28)

## Overview

DUNE APA production system with two separate applications:

- **dune_winder** — winding stage (applies wire to APA frame)
- **dune_tension** — tension measurement stage (measures applied wire tension)

Both share a **common domain model**: machine geometry, PLC communication, safety interlocks, and calibration data.

## Architecture Principles

1. **Specification-first** — Allium specs are the source of truth
2. **Type-safe** — Rust core runtime, TypeScript UI, strong contracts
3. **Zero duplication** — shared domain model used by both applications
4. **Skeptical of Python** — verify math/logic against first principles, trust operator workflows
5. **Parallel-first port** — Rust code alongside Python until proven

## Shared Domain Model

See [`docs/design-docs/allium-specs/index.md`](docs/design-docs/allium-specs/index.md) for authoritative specifications:

- **Geometry** — U/V pin systems, wire segments, coordinate transforms (both apps)
- **PLC communication** — tag structures, state machine, safety interlocks (both apps)
- **Calibration** — machine dimensions, sensor offsets, material properties (both apps)

## Application Boundaries

### dune_winder (Winding Stage)

**Responsibility:** Control APA wire winding, head transfer between stage/fixed mounts, recipe execution

**Key components:**
- Recipe generation & validation (templates, variables)
- Motion planning (waypoints, timing, queued motion)
- Winder state machine (manual/wind/pause/homing/error)
- Head transfer protocol (G206/G106 latch sequences)

**Spec:** [`docs/design-docs/allium-specs/winder-states-safety.allium`](docs/design-docs/allium-specs/winder-states-safety.allium)

### dune_tension (Measurement Stage)

**Responsibility:** Measure wire tension via audio resonance, manage measurement campaigns, report results

**Key components:**
- Measurement setup & targeting (pose planning, focus control)
- Audio capture & FFT spectrum analysis
- Neural network inference (pitch estimation)
- Legacy vs. streaming measurement modes
- Result acceptance & summary statistics

**Spec:** [`docs/design-docs/allium-specs/tension-measurement.allium`](docs/design-docs/allium-specs/tension-measurement.allium)

## Documentation Structure

```
docs/
├── design-docs/              ← Authoritative specifications & architecture
│   ├── allium-specs/         ← Formal domain model (current: Apr 26-27)
│   ├── architecture/         ← System design & boundaries
│   └── core-beliefs.md       ← Design principles
├── exec-plans/               ← Implementation roadmaps & decisions
│   ├── active/               ← Current work (e.g., rust-port-2026-04.md)
│   ├── completed/            ← Archived execution plans
│   └── audit-results/        ← Phase verification documents
├── product-specs/            ← Operator workflows (what users see)
├── references/               ← How-to guides, constants, syntax help
└── STALENESS.md              ← Authority framework & staleness guide
```

**Quick links:**
- 📋 **What's current?** → [`docs/STALENESS.md`](docs/STALENESS.md)
- 📐 **Formal specs?** → [`docs/design-docs/allium-specs/index.md`](docs/design-docs/allium-specs/index.md)
- 🛠️ **Implementation plan?** → [`docs/exec-plans/active/`](docs/exec-plans/active/)
- 👤 **Operator workflows?** → [`docs/product-specs/`](docs/product-specs/)

## Port Roadmap

**Phase 0 (Audit):** Verify Python against Allium specs, identify divergences → [`exec-plans/audit-results/`](docs/exec-plans/audit-results/)

**Phase 1-3:** Shared domain model (types, API contracts, golden tests) in Rust

**Phase 5-7:** Application-specific implementations (winder, tension) with domain types

**Phase 8-9:** PLC communication, desktop consolidation, UI migration

See [`docs/exec-plans/active/rust-port-2026-04.md`](docs/exec-plans/active/rust-port-2026-04.md) for detailed phases.

## Authority & Staleness

| Source | Status | Trust | Reference |
|--------|--------|-------|-----------|
| Allium specs (design-docs/allium-specs/) | ✅ CURRENT (Apr 26-27) | **AUTHORITATIVE** | [`STALENESS.md`](docs/STALENESS.md) |
| Active exec plans (exec-plans/active/) | ✅ CURRENT | **AUTHORITATIVE** | [`STALENESS.md`](docs/STALENESS.md) |
| Architecture docs (design-docs/architecture/) | ✅ CURRENT | AUTHORITATIVE | [`STALENESS.md`](docs/STALENESS.md) |
| Product specs (product-specs/) | ✅ CURRENT | AUTHORITATIVE | [`STALENESS.md`](docs/STALENESS.md) |
| Markdown in dune_winder/planning/ | ❌ STALE (Mar 29) | REFERENCE ONLY | [`STALENESS.md`](docs/STALENESS.md) |
| Markdown in dune_tension/streaming_*.md | ❌ STALE (Mar 29) | REFERENCE ONLY | [`STALENESS.md`](docs/STALENESS.md) |

**Always check [`docs/STALENESS.md`](docs/STALENESS.md) if unsure.**
