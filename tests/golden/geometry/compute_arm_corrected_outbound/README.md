# Arm-correction outbound golden fixtures

Per `plans/UVlayerRewritePlan.md` (Phase D follow-up — wire-tangent solver
port). Each JSON file pairs the inputs to `_compute_arm_corrected_outbound`
(anchor pin, target pin, the two tangent points, transfer bounds, head
geometry, optional `roller_arm_y_offsets`) with the legacy outputs —
`corrected_outbound`, `corrected_head_center`, `roller_index`, and
`quadrant` — or the legacy error string when the inputs are
indeterminate.

Authoritative shapes:

- **Producer (legacy):** `_compute_arm_corrected_outbound` in
  `src/dune_winder/uv_head_target_parts/geometry2d.py`.
- **Consumer (Rust port):** `dune_geometry::wire::compute_arm_corrected_outbound`
  in `rust/crates/dune_geometry/src/wire.rs`, plus the PyO3 surface at
  `dune_geometry.compute_arm_corrected_outbound`.

The Rust implementation must match these fixtures within `1e-9` per
ordinate. `roller_index` is exact; `quadrant` is one of `"NW"`,
`"NE"`, `"SW"`, `"SE"`.

## Adding fixtures

Append a new case to `_CASES` in
`scripts/generate_compute_arm_corrected_outbound_fixtures.py` and run:

```sh
uv run python scripts/generate_compute_arm_corrected_outbound_fixtures.py
```

Never hand-edit the JSON — it must come from the legacy implementation so
that drift is caught by the parity test.
