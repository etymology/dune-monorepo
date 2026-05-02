# Select-tangent-solution golden fixtures

Per `plans/UVlayerRewritePlan.md` (Phase D follow-up — wire-tangent solver
port). Each JSON file pairs the inputs to the candidate-ranking step
(`circle_pair_tangent_pairs` output, transfer bounds, optional anchor /
wrapped side constraints) with the selected `(tangent_a, tangent_b,
clipped_start, clipped_end)` tuple — or the legacy error when no
candidate clips into the transfer rectangle.

Authoritative shapes:

- **Producer (legacy):** `_select_tangent_solution` in
  `src/dune_winder/uv_head_target_parts/geometry2d.py`.
- **Consumer (Rust port):** `dune_geometry::wire::select_tangent_solution`
  in `rust/crates/dune_geometry/src/wire.rs`, plus the PyO3 surface at
  `dune_geometry.select_tangent_solution`.

The Rust implementation must match these fixtures within `1e-9` per
ordinate. Order matters — Rust uses a stable descending sort on the
same rank key the legacy uses
(`(match_total, target_matches, outbound.y, outbound.x, tangent_a.y)`),
so identical-key ties resolve to the candidate that appeared first in
the `circle_pair_tangent_pairs` output.

## Adding fixtures

Append a new case to `_CASES` in
`scripts/generate_select_tangent_solution_fixtures.py` and run:

```sh
uv run python scripts/generate_select_tangent_solution_fixtures.py
```

Never hand-edit the JSON — it must come from the legacy implementation so
that drift is caught by the parity test.
