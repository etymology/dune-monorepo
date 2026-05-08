# Split changes since `eea12bf` into independent PRs

## Context

`main` is 32 commits ahead of the stable tag `eea12bf`. The working tree contains
~23k insertions across geometry, PLC I/O, two web stacks, configuration, and docs.
Goal: carve these into independent, reviewable PRs that can ship in any order
where possible, and as a small ordered stack where it isn't.

A purely commit-by-commit split won't work — `3ae146d0` ("responsive scaling")
*also* moves the machine calibration files, while the matching Python path
updates land later in `8092e143`. Splits below are by **logical feature**, not
by commit boundary.

User-confirmed decisions:
- **PR 2 will be split** into PR 2a (Phases A0–E) and PR 2b (Phases F–G + APA
  spine capture panel).
- **PR 6 will move the 40 MB DUNE TDR PDF to Git LFS** rather than keeping it
  as a regular blob.

---

## Recommended PR breakdown (7 PRs)

### PR 1 — PLC: Rust tag bus + STATE_REQUEST handshake
**Status:** independent of all other PRs.
**Commits:** `b8a397fc`, `76ca86f9`, `c6439298`, `6abea2d3`, `ecc30ca3`, `4c78cae6`

Replaces the legacy `PLC.Tag` Python layer with a Rust `dune_plc_bus` crate
exposed via PyO3, and adds the STATE_REQUEST ID/ACK/RESULT/FAULT_FLAGS
handshake. Adds the Phase C handler-thinning planning doc.

Critical paths:
- `rust/crates/dune_plc_bus/**` (new crate, ~2.5 kLOC + compile-fail tests)
- `src/dune_winder/io/controllers/plc_logic.py` (rewrite, +/-783 lines)
- `src/dune_winder/io/devices/{simulated_plc,legacy_bus_adapter,tag_bus_registry}.py`
- `src/dune_winder/io/primitives/{plc_input,plc_motor}.py`
- `src/dune_winder/io/maps/base_io.py`
- `src/dune_winder/queued_motion/plc_interface.py`
- `src/dune_winder/plc_ladder/runtime.py`
- `dune_winder/plc/{tags.toml,controller_level_tags.json,PHASE_C_HANDLER_THINNING_TODO.md}`
- `dune_winder/plc/main/main/pasteable.rll`, `state_1_ready/main/pasteable.rll`
- `tests/dune_plc_bus/**`, `tests/dune_winder/test_plc_logic*`,
  `test_plc_ladder_*`, `test_queued_motion.py`, `test_wrap_runtime.py`
- `rust/Cargo.toml`, `rust/Cargo.lock`, `pyproject.toml`, `uv.lock`

### PR 2a — UV layer rewrite Phases A0–E: `dune_geometry` crate foundation + 3D anchor offsets
**Status:** depends on PR 5 (config relocation) for stable paths; otherwise
independent.
**Commits:** `7ccac080`, `d6ae7cb0`, `1895f811`, `2358836f`, `cbe3bf2f`,
`b44d4c9d`. Plan-only edits from `0230a44c` and `22354389` go here.

Lands the Rust `dune_geometry` crate skeleton, the Pin adapter and pin-name
migration (Phase B), calibration schemas + legacy converter (Phase C),
extraction of tension geometry and the `solve_anchor_to_target` math kernel
(Phase D), and the 3D `~anchorToTarget` offset foundation in the gcode layer
(Phase E).

Critical paths:
- `rust/crates/dune_geometry/**` (initial crate: `lib.rs`, `pins.rs`,
  `tension.rs`, `wire.rs`, `calibration.rs`, `python.rs` foundations)
- `rust/Cargo.toml`, `rust/Cargo.lock`, `rust/crates/dune_tension_core/Cargo.toml`
- `src/dune_winder/machine/calibration/layer.py` (Pin adapter)
- `src/dune_winder/uv_head_target_parts/{anchor_to_target,models,constants}.py`,
  `src/dune_winder/uv_head_target.py`
- `src/dune_winder/machine/geometry/uv_wrap_geometry.py`
- `src/dune_winder/recipes/line_offset_overrides.py`
- `src/dune_winder/gcode/handler_base.py`
- `specs/{layer-geometry,uv-machine-calibration,uv-wrap-geometry}.allium`
  (Phase A0–D portions)
- `scripts/{convert_legacy_pin_calibration,migrate_pin_names,
  generate_actual_wire_point_fixtures,
  generate_compute_arm_corrected_outbound_fixtures}.py`
- `tests/dune_geometry/test_{actual_wire_point_parity,
  anchor_to_target_math_smoke,calibration_surface,
  compute_arm_corrected_outbound_parity,convert_legacy_pin_calibration,
  migrate_pin_names,pin_surface,wire_surface}.py`
- `tests/dune_winder/test_{anchor_to_target_parser,gcode_domain,
  layer_calibration_pin_adapter,uv_head_target,uv_tangency_analysis}.py`
- `tests/golden/geometry/{actual_wire_point,anchor_to_target,
  compute_arm_corrected_outbound}/**`
- `plans/UVlayerRewritePlan.md` (Phase A0–E sections)

### PR 2b — UV layer rewrite Phases F–G + APA spine capture panel
**Status:** stacks on top of PR 2a.
**Commits:** `b7e651f1`, `8238ab53`, `c02580a3`, `c220175b`, `cae1f680`,
`f31aa00d`, `6d4aebdc`, `e468636e`, `9e53c77d`, `b6ec4081`, `4a7e7615`,
`1f94a86c`, `0b8cf248`, `041cf304`.

Adds the spine-based continuous-loop calibration: analytic
`tangent_for_pin_pair` single-tangent solver, ridge-regularised
`solve_spine_plane`, X/G layer support in Rust, sign-flip cleanup, removal of
legacy `circle_pair_tangent_pairs` / `_select_tangent_solution` shims, and
the operator-facing APA spine-capture web panel that drives
`MachineCaptureService`.

Critical paths:
- `rust/crates/dune_geometry/src/{spine.rs,calibration.rs,wire.rs,pins.rs,
  python.rs,lib.rs}` (Phase F–G additions; `spine.rs` is new)
- `rust/crates/dune_tension_core/src/geometry.rs` (X/G layer support)
- `src/dune_winder/uv_head_target_parts/pin_pair_tangent.py` (rewire to
  `tangent_for_pin_pair`)
- `src/dune_winder/core/machine_calibration_capture.py` (new)
- `src/dune_winder/core/process.py`, `src/dune_winder/api/commands.py`
- `dune_winder/web/Desktop/Pages/APA.{html,css,js}` (spine-capture panel diffs
  added on top of PR 4's responsive-layout diffs)
- `dune_winder/web/Scripts/CommandCatalog.js`
- `specs/{layer-geometry,operator-workflows,spine-calibration}.allium`
- `scripts/generate_tangent_for_pin_pair_fixtures.py`
- `tests/dune_geometry/test_{spine_surface,tangent_for_pin_pair_parity}.py`
- `tests/dune_winder/test_machine_calibration_capture.py`
- `tests/dune_winder/test_head_g106_transfer.py` (deleted)
- `tests/golden/geometry/tangent_for_pin_pair/**`
- `plans/{UVlayerRewritePlan,XGrewritePlan}.md` (Phase F–G sections)

Reusable utilities to lean on (already in tree at this point):
- `dune_geometry::tangent_for_pin_pair` replaces both
  `circle_pair_tangent_pairs` and `_select_tangent_solution` for same-side
  callers — see `src/dune_winder/uv_head_target_parts/pin_pair_tangent.py`.
- `MachineCalibrationFile` is the persistence layer for capture; do not
  introduce a parallel JSON writer.

### PR 3 — `dune_tension`: Svelte web app + FastAPI backend
**Status:** independent of all other PRs.
**Commits:** `bc26958b`, `eabdc6ca`

Adds a FastAPI backend (`src/dune_tension/api/`), a primary Svelte UI
(`src/dune_tension/web/app/`) with measurement/calibration step components,
and an experimental Svelte tree at `dune_tension/web/app/` (still on disk —
the directory exists with both the new Svelte app and the older `Experiment.*`
files). Wires `wire_result_callback` through `Tensiometer` for real-time push.

Critical paths:
- `src/dune_tension/api/{cli,main,routes,state}.py`
- `src/dune_tension/web/app/**` (full Vite/Svelte/Tailwind tree)
- `src/dune_tension/web/dist/**` (built artefacts — confirm whether these
  should actually be checked in or `.gitignore`d before pushing)
- `dune_tension/web/app/**` (experimental tree)
- `src/dune_tension/{tensiometer,layer_calibration}.py`
- `dune_tension/data/logs/tensiometer_gui*.log` (likely should be dropped from
  the PR — see verification step below)
- `Makefile` (`build-web` target), `config/APA/TensionLaserOffsets.json`,
  `specs/layer-geometry.allium` (laser-offset-related lines only),
  `dune_tension/README.md`, `package-lock.json`, `node_modules/.package-lock.json`

**Pre-PR cleanup:** decide whether to keep both Svelte trees or collapse the
experimental one; drop the committed `tensiometer_gui*.log` files; reconsider
checking in the `dist/` build output.

### PR 4 — Winder web UI: responsive machine layout + PositionGraphic refactor
**Status:** independent (after the file-move bytes from `3ae146d0` are routed
to PR 5).
**Commits:** `3ae146d0` (web-only portion).

Introduces responsive scaling for `MachineLayout` and a substantial
`PositionGraphic` refactor; touches `ManualMove` and adds APA-page CSS that
predates the spine-capture panel.

Critical paths (subset of the commit):
- `dune_winder/web/Desktop/Modules/PositionGraphic.{js,css}`
- `dune_winder/web/Desktop/Modules/ManualMove.{js,html,css}`
- `dune_winder/web/Desktop/Pages/MachineLayout.{js,html,css}`
- `dune_winder/web/Desktop/Pages/APA.{html,css,js}` (the layout-scaling diffs
  only — the spine-capture additions live in PR 2)

To split this commit cleanly: cherry-pick `3ae146d0` onto the PR-4 branch,
then `git restore --source=eea12bf -- dune_winder/config/machineCalibration.*`
to leave the config files untouched here.

### PR 5 — Config: relocate `machineCalibration.*` to repo-root `config/`
**Status:** independent. Tiny.
**Commits:** the file-move bytes from `3ae146d0` + all of `8092e143`.

Move `dune_winder/config/machineCalibration.{json,xml}` → `config/` and update
every Python import path in one shot.

Critical paths:
- `config/machineCalibration.{json,xml}` (renames)
- `src/dune_winder/{machine/settings.py,uv_head_target_parts/constants.py,
  analysis/uv_tangency_analysis.py}`
- `tests/dune_winder/test_{layer_z_plane_calibration,
  machine_geometry_calibration,uv_head_target,uv_tangency_analysis}.py`

### PR 6 — Docs sweep + DUNE TDR PDF moved to Git LFS
**Status:** independent. Mostly a sweep.
**Commits:** `e57759dd` (Python/Rust workflow), `0aee7292` (DUNE TDR PDF —
re-routed through LFS), `AGENTS.md` / `README.md` / `dune_tension/README.md`
/ `dune_winder/README.md` churn from various commits, `specs/README.md`,
`plans/README.md` deletion, deletion of stale plan JSONs
(`plans/{improve-plc-contract-migration,type-safety-first-port,
uv-layer-rewrite,plc-contract-migration}.{json,md}`).

**LFS migration steps for the 40 MB TDR PDF:**
1. Confirm Git LFS is installed and enabled on the remote
   (`git lfs install` locally; verify the GitHub repo has LFS storage).
2. On the PR branch, before staging the PDF: add a `.gitattributes` rule —
   `*.pdf filter=lfs diff=lfs merge=lfs -text` (or scope it to the specific
   filename if PDFs elsewhere should stay regular).
3. If the PDF is currently a regular blob anywhere in the branch's history
   (it is — `0aee7292`), use `git lfs migrate import --include="*.pdf"
   --include-ref=<this-branch>` to rewrite the blob into an LFS pointer on
   this branch only. Do **not** rewrite `main`'s history.
4. Stage and commit the `.gitattributes` change plus the LFS-pointer version
   of the PDF. `git lfs ls-files` should show the file.
5. `git push` will upload the actual bytes to LFS storage; the pushed branch
   should contain the pointer file, not the 40 MB blob.

**Verify after migration:** `git cat-file -p HEAD:"Deep Underground Neutrino
Experiment (DUNE) - 2002.03010v3.pdf"` should print an LFS pointer
(`version https://git-lfs.github.com/...`), not binary bytes.

---

## Suggested merge order

1. PR 5 (config relocation) — smallest, eliminates a moving target.
2. PR 1 (PLC tag bus) — independent, foundation for follow-on PLC thinning.
3. PR 4 (winder web responsive scaling) — independent UI work.
4. PR 2a (UV rewrite Phases A0–E) — lands after PR 5 so paths are stable.
5. PR 2b (UV rewrite Phases F–G + APA capture panel) — stacked on PR 2a; the
   APA-page diffs sit on top of PR 4's responsive-layout diffs, so PR 4 should
   land first to avoid a merge conflict on `dune_winder/web/Desktop/Pages/APA.*`.
6. PR 3 (tension Svelte + API) — independent feature.
7. PR 6 (docs + LFS migration) — sweep at the end, after stale plans are
   clearly obsolete.

PR 1, 3, 4, 5 can all open and merge in parallel. PR 2a depends on PR 5;
PR 2b depends on PR 2a and (effectively) PR 4. PR 6 is otherwise orthogonal.

---

## Verification per PR

Run after building each PR branch:

- **PR 1 (PLC):** `cargo test -p dune_plc_bus`,
  `cargo test -p dune_plc_bus --test compile_fail`,
  `pytest tests/dune_plc_bus tests/dune_winder/test_plc_logic*.py
  tests/dune_winder/test_plc_ladder*.py tests/dune_winder/test_queued_motion.py`,
  manual smoke against the simulated PLC driver.
- **PR 2a (UV rewrite Phases A0–E):** `cargo test -p dune_geometry`,
  `pytest tests/dune_geometry/test_{actual_wire_point_parity,
  anchor_to_target_math_smoke,calibration_surface,
  compute_arm_corrected_outbound_parity,convert_legacy_pin_calibration,
  migrate_pin_names,pin_surface,wire_surface}.py
  tests/dune_winder/test_{anchor_to_target_parser,gcode_domain,
  layer_calibration_pin_adapter,uv_head_target,uv_tangency_analysis}.py`.
- **PR 2b (UV rewrite Phases F–G):** `cargo test -p dune_geometry`,
  `pytest tests/dune_geometry/test_{spine_surface,
  tangent_for_pin_pair_parity}.py
  tests/dune_winder/test_machine_calibration_capture.py`,
  load `dune_winder/web/Desktop/Pages/APA.html` and exercise the spine-capture
  panel against a simulated machine; confirm the 5 mm overshoot dialog fires.
- **PR 3 (tension web):** `cd src/dune_tension/web/app && npm install &&
  npm run build`, then `python -m dune_tension.api.cli` and hit `/health`,
  `/measurements/*` routes; load the built UI in a browser.
- **PR 4 (winder UI):** open `dune_winder/web/Desktop/Pages/MachineLayout.html`
  at multiple viewport sizes; confirm `PositionGraphic` rescales without
  layout breakage; exercise `ManualMove`.
- **PR 5 (config relocation):** `pytest tests/dune_winder/test_layer_z_plane_calibration.py
  tests/dune_winder/test_machine_geometry_calibration.py
  tests/dune_winder/test_uv_head_target.py
  tests/dune_winder/test_uv_tangency_analysis.py`; `rg "dune_winder/config/machineCalibration"`
  must return zero hits.
- **PR 6 (docs + LFS):** link-check; `git lfs ls-files` shows the TDR PDF;
  `git cat-file -p HEAD:"Deep Underground Neutrino Experiment (DUNE) - 2002.03010v3.pdf"`
  prints an LFS pointer (not raw PDF bytes); fresh clone with
  `GIT_LFS_SKIP_SMUDGE=1` followed by `git lfs pull` retrieves the PDF.

---

## Open question still to resolve before PR 3

PR 3: drop the experimental `dune_tension/web/app/` tree, drop the committed
`tensiometer_gui*.log` files, and/or `.gitignore` the `dist/` build output?
