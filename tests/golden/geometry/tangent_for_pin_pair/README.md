# Tangent-for-pin-pair golden fixtures

Per `plans/UVlayerRewritePlan.md` (Phase D follow-up — analytic
single-tangent solver). Each JSON file pairs an `(anchor_pin,
target_pin, xy, radius)` input set with the unique tangent line that
satisfies both pins' wrap-side rules.

Authoritative shapes:

- **Producer (legacy):** `dune_winder.uv_head_target_parts.pin_layout.tangent_sides`
  + `dune_winder.queued_motion.filleted_path.circle_pair_tangent_pairs`,
  picking the unique candidate whose anchor- and target-side normals
  match the legacy `tangent_sides` rule.
- **Consumer (Rust port):** `dune_geometry::wire::tangent_for_pin_pair`
  in `rust/crates/dune_geometry/src/wire.rs`, plus the PyO3 surface at
  `dune_geometry.tangent_for_pin_pair`.

The Rust implementation must match these fixtures within `1e-9` per
ordinate. Each case has *exactly one* matching candidate — that's the
analytic-solver premise: knowing `(layer, side, n)` for both pins
collapses the four-candidate enumeration to a closed-form solve.

## Adding fixtures

Append a new case to `_CASES` in
`scripts/generate_tangent_for_pin_pair_fixtures.py` and run:

```sh
uv run python scripts/generate_tangent_for_pin_pair_fixtures.py
```

The generator rejects cases where zero or multiple candidates match the
`tangent_sides` rule — that's a sign the chosen geometry is incompatible
with the wrap-side preference (e.g., pins on opposite faces, or
positions that don't admit the requested normal direction).

Never hand-edit the JSON.
