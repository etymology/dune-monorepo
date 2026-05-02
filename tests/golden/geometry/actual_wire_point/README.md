# Actual-wire-point golden fixtures

Per `plans/UVlayerRewritePlan.md` (Phase D follow-up — wire-tangent solver
port). Each JSON file pairs the inputs to
`_actual_wire_point_from_machine_target` (commanded head XY, compensated
anchor XY, anchor and head Z, head geometry) with the legacy returned
`(wire_x, wire_y)`.

Authoritative shapes:

- **Producer (legacy):** `_actual_wire_point_from_machine_target` in
  `src/dune_winder/uv_head_target_parts/anchor_to_target.py`.
- **Consumer (Rust port):** `dune_geometry::wire::actual_wire_point_from_machine_target`
  in `rust/crates/dune_geometry/src/wire.rs`, plus the PyO3 surface at
  `dune_geometry.actual_wire_point_from_machine_target`.

The Rust implementation must match these fixtures within `1e-9` per
ordinate. The Rust port preserves the legacy quirk that
`roller_offset_z` is computed but never applied to the returned XY —
fixtures pin behaviour, not intent.

## Adding fixtures

Append a new case to `_CASES` in
`scripts/generate_actual_wire_point_fixtures.py` and run:

```sh
uv run python scripts/generate_actual_wire_point_fixtures.py
```

Never hand-edit the JSON — it must come from the legacy implementation so
that drift is caught by the parity test.
