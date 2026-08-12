# Plan: Fix U/V wire targeting when "Flipped" is checked

## Context

When the APA is physically flipped (upside down), the spatial coordinates for Side A wires match what the database stores as Side B coordinates, and vice versa. The "Flipped" checkbox signals this: the laser must navigate using the opposite side's geometric layout to locate the correct physical wire positions.

The recording side is **unchanged** — if the GUI shows Side A and Flipped is checked, measurements are still saved as Side A. Only the targeting (where the laser physically moves) uses the opposite side's geometry.

**Current gap:** X/G layers already implement the A↔B swap in `WirePositionProvider._build_snapshot` via `virtual_side`. U/V layers do not — `_resolve_uv_plan` unconditionally passes `config.side` to `plan_uv_wire`, so the laser targets the wrong physical positions when flipped.

## Changes

### 1. `src/dune_tension/tensiometer_functions.py` — `_resolve_uv_plan` (~line 303)

Compute a `targeting_side` that mirrors the existing `virtual_side` pattern from `_build_snapshot`, and pass it to `plan_uv_wire`:

```python
def _resolve_uv_plan(self, config, wire_number, *, zone=None):
    if config.layer not in ["U", "V"]:
        return None
    targeting_side = (
        {"A": "B", "B": "A"}[config.side.upper()]
        if config.flipped
        else config.side.upper()
    )
    try:
        from dune_tension.uv_wire_planner import plan_uv_wire
        planned = plan_uv_wire(
            str(config.layer).upper(),
            targeting_side,          # was: str(config.side).upper()
            int(wire_number),
            zone=zone,
        )
    ...
```

This covers both the legacy path (`_resolve_uv_planned_pose` → `_resolve_uv_plan`) and the streaming path (`build_corridors_for_wire_numbers` → `WirePositionProvider.get_xy` → `_resolve_uv_planned_pose`).

### 2. `src/dune_tension/gui/actions.py` — wire preview callback (~line 413)

The live wire preview popup calls `plan_uv_wire` via `_show_uv_wire_preview`. It should preview the side the laser will actually target. Fix the `side` argument in the `_request_uv_wire_preview` lambda inside `create_tensiometer`:

```python
str(
    {"A": "B", "B": "A"}[str(inputs.side).upper()]
    if inputs.flipped
    else str(inputs.side).upper()
),  # was: str(inputs.side).upper()
```

## What does NOT change

- `_build_snapshot` virtual_side logic — X/G already correct, untouched.
- `_resolve_xy` wire-number mirroring for X/G — untouched.
- Recording: all `TensionResult` creation sites use `config.side` (the displayed side) — no change.
- Zone selection (`plan_uv_wire_zone` calls in actions.py lines 1127, 1517) — these select *which* side-A wires to measure, not where to physically position; displayed side is correct.
- Skip-measured filtering — queries against the displayed side's recorded data; correct.
- `dy` negation in `make_config` — correct for historical-neighbour extrapolation direction; untouched.
- `manual_increment` X-sign logic — purely a jog UI feature; untouched.

## Verification

1. Run `uv run ty check` — no new type errors.
2. Run `uv run pytest tests/dune_tension` — all existing tests pass.
3. Manual smoke test: launch `uv run dune-tension-gui`, select a U/V layer, check Flipped, trigger any measurement action — confirm the wire preview (if enabled) shows the geometry for the opposite side, and that no exception is raised.
