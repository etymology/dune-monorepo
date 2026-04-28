# Product Specifications

These documents describe what operators see and do — the **user-facing workflows** that are authoritative and must be preserved during the port.

Unlike architecture (which can change) and specs (which are formal), product specs capture the operator experience.

## Files

- **winder-operator-workflows.md** — Manual jog, winding, pause/resume, head transfer, homing workflows
- **tension-measurement-workflows.md** — Measurement setup, capture, result review, upload workflows

## Authority

These specifications are **AUTHORITATIVE** and **NON-NEGOTIABLE** during the port.

- Python implementation may have bugs (fix them)
- Operator workflows must be preserved (do not change)
- New features are separate (not part of port scope)

## How to Use

Before implementing any feature in dune_winder or dune_tension, check the corresponding product spec to understand what the operator expects to see and do.

The Rust port should look and feel the same from the operator's perspective, even if the internals are completely different.
