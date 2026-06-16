# docs/

Project documentation. Agent-readable Markdown is grouped by package; large
binary reference material is isolated under `reference-assets/`.

## Agent-readable docs

- [`winder/`](winder/) — winder reference notes
  - [`u_gcode_summary.md`](winder/u_gcode_summary.md) — U-layer G-code summary
  - [`v_gcode_summary.md`](winder/v_gcode_summary.md) — V-layer G-code summary
  - [`z_calibration_spec.md`](winder/z_calibration_spec.md) — Z calibration spec
- [`tension/`](tension/) — tension tooling docs
  - [`dune_tension_manual.md`](tension/dune_tension_manual.md) — dune_tension user manual
- [`Todo.md`](Todo.md) — running TODO list

For agent behaviour rules and the PLC edit workflow, see the repo-root
[`AGENTS.md`](../AGENTS.md). Per-package operational detail lives in
[`winder/README.md`](../winder/README.md) and [`tension/README.md`](../tension/README.md).

## reference-assets/ — binary, NOT agent-readable

Large vendor and design artifacts kept for human reference only. Agents should
**not** attempt to read or grep these (they are `.ACD`, `.pdf`, `.ods`, `.docx`,
`.xml`, and image files, ~136 MB total):

- [`reference-assets/chicago-plc/`](reference-assets/chicago-plc/) — Chicago PLC ACD snapshots, recipe spreadsheets, wiring/PID images
- [`reference-assets/rockwell-manuals/`](reference-assets/rockwell-manuals/) — Rockwell ControlLogix / motion vendor manuals (public PDFs)

> Note: these binaries are committed directly to git history (no LFS). Moving
> them to Git LFS or external storage to shrink clones is a deferred decision.
