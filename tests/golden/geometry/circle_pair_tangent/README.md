# Circle-pair tangent golden fixtures

Per `plans/UVlayerRewritePlan.md` (Phase D follow-up — wire-tangent solver
port). Each JSON file pairs an input pair of circles `(center, radius)`
with the expected list of tangent line pairs as produced by the legacy
Python implementation.

Authoritative shapes:

- **Producer (legacy):** `circle_pair_tangent_pairs` in
  `src/dune_winder/queued_motion/filleted_path.py`.
- **Consumer (Rust port):** `dune_geometry::wire::circle_pair_tangent_pairs`
  in `rust/crates/dune_geometry/src/wire.rs`, plus the PyO3 surface at
  `dune_geometry.circle_pair_tangent_pairs`.

The Rust implementation must match these fixtures within `1e-9` per
ordinate. Order matters — both implementations enumerate sign combinations
in the same order, so the parity test compares element-by-element rather
than as a set.

## Adding fixtures

Append a new case to `_CASES` in
`scripts/generate_circle_pair_tangent_fixtures.py` and run:

```sh
uv run python scripts/generate_circle_pair_tangent_fixtures.py
```

Never hand-edit the JSON — it must come from the legacy implementation so
that drift is caught by the parity test.
