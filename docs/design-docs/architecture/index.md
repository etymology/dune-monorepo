# System Architecture

See [`ARCHITECTURE.md`](../../ARCHITECTURE.md) at the root for high-level overview.

This directory contains detailed architecture documentation for:

- **shared-domain-model.md** — Geometry, PLC, calibration (shared by both apps)
- **dune-winder-application.md** — Winding stage, recipes, motion planning, state machine
- **dune-tension-application.md** — Measurement stage, audio/FFT/inference, workflow

## Reference

All architecture decisions should:

1. **Reference Allium specs** (design-docs/allium-specs/) as source of truth
2. **Avoid duplication** of specification — link to Allium, don't repeat rules
3. **Explain integration** — why components interact this way, not what each does
4. **Document boundaries** — what's shared, what's app-specific, what changes during port

## Files to Create

- [ ] shared-domain-model.md
- [ ] dune-winder-application.md
- [ ] dune-tension-application.md
- [ ] core-beliefs.md (design principles)
