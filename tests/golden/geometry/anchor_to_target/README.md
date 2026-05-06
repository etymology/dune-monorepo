# Anchor-to-target golden parity fixtures

Per `plans/UVlayerRewritePlan.md` Phase D. Each fixture in this directory is a
JSON file pairing an `AnchorToTargetRequest` (raw camera-space inputs +
machine-calibration model + commanded head side) with the expected
`AnchorToTargetSolution` (commanded winder pose + effective offsets).

Authoritative shape: `dune_geometry::wire::AnchorToTargetRequest` /
`AnchorToTargetSolution` (see `rust/crates/dune_geometry/src/wire.rs`).

Producer: today the legacy Python solver at
`src/dune_winder/uv_head_target_parts/anchor_to_target.py` is run on each
fixture's inputs and the result is frozen. The new
`dune_geometry::wire::solve_anchor_to_target` (still to be ported) must
match these fixtures within numeric tolerance for cases where the per-pose
offset model collapses to a constant. Cases where the per-pose model
diverges from the legacy single-offset assumption are documented in the
fixture's `notes` field.

Add fixtures by running the capture script (TBD) against a calibrated
machine state checkpoint, never by hand-crafting expected outputs.
