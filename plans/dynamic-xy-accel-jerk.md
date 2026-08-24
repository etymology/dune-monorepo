# Dynamic XY accel jerk for `~anchorToTarget`

## Context

`xy_regulated_accel_jerk` is a program-scope DINT in the `state_3_move_xy` PLC program
(`winder/plc/state_3_move_xy/programTags.json:996-1009`, live value 800). It is the S-curve accel-jerk
operand of the tension-regulated coordinated move at
`winder/plc/state_3_move_xy/xy_speed_regulator/xy_speed_regulator.rung:17`. Today nothing outside the
ladder touches it — it is a static tuning constant frozen in the ACD.

Some wrap transitions want a softer XY acceleration profile (less wire disturbance) and others want a
snappier one. The operator needs to pick per-move, from the recipe, without re-importing ladder.

Outcome: three configurable jerk values (`default` 1500, `gentle` 1000, `jerky` 2000) editable on the
web Configuration page, selectable per G-code line via a new `jerk=` keyword on `~anchorToTarget`, and
pushed to the PLC tag before the state-3 request — exactly the way `X_POSITION`/`Y_POSITION` are pushed
today (`plc_logic.py:161-182`).

### Decisions taken

- **Syntax:** `jerk=gentle` — a name=value keyword, consistent with the existing `offset=` / `hover=` /
  `inTwoMoves=` grammar the parser already enforces at `handler_base.py:815-819`.
- **No ladder edit.** The tag already exists and is `ExternalAccess="Read/Write"`. Python-only change.
- **Write on every XY move.** `setXY_Position` always writes the resolved jerk (configured default unless
  the pending action carries an override), so a `gentle` value can never leak into a later move.

### Known limitation to state in the PR description

`xy_regulated_accel_jerk` only feeds the **regulated** MCLM, which the ladder gates on
`TENSION_CONTROL_OK and speed_regulator_switch` (`main.rung:95`). The unregulated MCLM
(`main.rung:97-105`) omits `accel_jerk` and so uses the schema default 500 baked into
`main_Routine_RLL.L5X:136`. **`jerk=gentle` therefore has no observable effect when the speed regulator
is off.** Extending it to the unregulated path is a separate `.rung` change requiring the Studio 5000
round-trip and is explicitly out of scope.

## Implementation

### 1. Config: three values — `src/dune_winder/library/app_config.py`

Add three `float` fields to the `AppConfig` dataclass alongside `maxJerkAccel`/`maxJerkDecel` (~line 72-77):

```python
xyRegulatedAccelJerkDefault: float = 1500.0
xyRegulatedAccelJerkGentle: float = 1000.0
xyRegulatedAccelJerkJerky: float = 2000.0
```

Declare them `float`, not `int` — `configuration.set` stringifies every value
(`api/commands.py:1701-1708`), and an `int`-typed field rejects a decimal the UI happily accepts.

In `AppConfig.set` (~line 288-296), extend the existing normalizer chain to guard the three keys.
**Reuse `normalize_queued_motion_jerk`** from `src/dune_winder/queued_motion/jerk_limits.py` — already
imported in this module and already does exactly the needed non-finite/`<= 0` → fallback check:

```python
elif key == "xyRegulatedAccelJerkDefault":
    value = normalize_queued_motion_jerk(value, default=1500.0)
# ...same for Gentle (1000.0) and Jerky (2000.0)
```

Hoist the three defaults into module constants so the dataclass defaults and the normalizer fallbacks
cannot drift.

### 2. UI: Configuration page — `winder/web/Desktop/Pages/Configuration.js`

Three lines in `loadConfiguration()`, in the "Configuration Parameters" list (after line 360). No HTML
or CSS change — the page generates all its markup, and the default validator is already `$.isNumeric`:

```js
configuration.display( "XY jerk (default)", "xyRegulatedAccelJerkDefault", tag )
configuration.display( "XY jerk (gentle)",  "xyRegulatedAccelJerkGentle",  tag )
configuration.display( "XY jerk (jerky)",   "xyRegulatedAccelJerkJerky",   tag )
```

### 3. Macro keyword — `src/dune_winder/gcode/handler_base.py`

In the `anchorToTarget` keyword loop (lines 813-869), add a `jerk` branch mirroring the `hover` branch:

- Accept `default` / `gentle` / `jerky`, case-insensitively; anything else raises `GCodeExecutionError`
  naming the three valid words.
- Update the two existing catch-all error strings at lines 806-809 and 866-869 to mention `jerk`.

Pass `jerk=<keyword or None>` into `_plan_explicit_wrap_transition` (line 870-876), add the parameter to
its signature (line 608-615), and resolve it to a number **once** at the top of that method via a new
helper:

```python
def _resolve_xy_accel_jerk(self, keyword):
    """Map a jerk keyword to a value from live configuration.  None -> no override."""
```

Read from `getattr(self, "_configuration", None)` with `getattr(configuration, "...", <fallback>)`,
following the established live-config pattern at `handler.py:426-448`
(`_queued_motion_accel_limits`) so UI edits take effect without a restart. `jerk=default` resolves to
the configured default rather than `None`, so the keyword is always explicit in the trace.

Attach the resolved number to **every** `"xy"` pending action this method emits — there are four call
sites (lines 722, 746, 748, 751; the `inTwoMoves` split emits two) — as `accel_jerk=<value>`. The
existing `_append_pending_action(kind, **kwargs)` helper (line 245-251) already supports arbitrary keys,
so no change there. Leave the `head` / `head_transfer` / `wrap_state` actions alone.

### 4. Pending-action dispatch — `src/dune_winder/gcode/handler.py`

In `_dispatch_pending_action`, `action_kind == "xy"` branch (line 1077-1129), read the override with the
existing accessor and forward it on the single call at line 1126:

```python
accel_jerk = self._pending_action_value(action, "accel_jerk", None)
...
self._io.plcLogic.setXY_Position(
    raw_target_x, target_xy[1], velocity, accelJerk=accel_jerk
)
```

Nothing else needs touching: queued motion never sees macro calls (`MacroCall` is handled only at
`handler_base.py:1023`), so `~anchorToTarget` XY moves always take this state-3 path.

### 5. PLC tag write — `src/dune_winder/io/controllers/plc_logic.py`

In `__init__` (~line 701-708), add the tag next to the other write-only targets. Use the `writeOnly`
attributes already defined there so it is **not** added to the polled-tag batch — a program-scope name
in the poll list would risk the whole batch read. Program-qualified name, precedent
`machine/calibration/loadcell.py:42-44`:

```python
self._xyRegulatedAccelJerk = PLC.Tag(
    plc,
    "Program:state_3_move_xy.xy_regulated_accel_jerk",
    writeOnly,
    tagType="DINT",
)
```

Add `self._xyAccelJerkDefault = None` to `__init__` and an optional `xyAccelJerk=None` parameter to
`setupLimits` (line 589-611) that stores it — this is the fallback for **manual/jog** XY moves, which do
not flow through the G-code handler.

In `setXY_Position` (line 161-182), add an `accelJerk=None` parameter and write the resolved value
**before** `_requestState`, since the MCLM latches its jerk operand on the rising `trigger_xy_move`
one-shot (`main.rung:58`):

```python
jerk = accelJerk if accelJerk is not None else self._xyAccelJerkDefault
if jerk is not None:
    self._xyRegulatedAccelJerk.set(int(round(float(jerk))))
```

`int(round(...))` because the tag is a DINT while config carries floats.

### 6. Startup wiring — `src/dune_winder/core/process.py`

At the existing `setupLimits` call (line 191-199), pass the configured default:

```python
io.plcLogic.setupLimits(
    maxVelocity,
    float(configuration.maxAcceleration),
    float(configuration.maxDeceleration),
    xyAccelJerk=float(configuration.xyRegulatedAccelJerkDefault),
)
```

Note the asymmetry to document in the PR: G-code moves resolve all three values from live config, but
the manual/jog fallback is seeded at startup — same restart semantics `maxAcceleration` already has.

### 7. The other two `~anchorToTarget` parsers must accept `jerk=`

There are **three** independent parsers for this macro. Missing either of the last two means a recipe
line carrying `jerk=` fails in the calibration/offline paths:

- `src/dune_winder/uv_head_target_parts/constants.py:16-25` — `_ANCHOR_TO_TARGET_RE`. Add a
  `jerk=(?:default|gentle|jerky)` alternative and bump `{0,3}` → `{0,4}`.
- `src/dune_winder/uv_head_target_parts/anchor_to_target.py:64-111` — the keyword loop. Accept and
  **ignore** `jerk` (it is a motion-profile hint with no bearing on the geometry view result); do not
  add it to `AnchorToTargetCommand` in `models.py:162`.
- `src/dune_winder/api/commands.py:1511-1539` — an inline copy of the same regex inside
  `machine_compute_roller_y_cal`. Same two edits.

Worth a short comment on each regex pointing at the other copies; leave the de-duplication alone.

### 8. Docs — skipped, and why

This step rested on a false premise: there is no `~anchorToTarget` signature line anywhere in `docs/`.
The two `*_gcode_summary.md` files contain only abstracted recipe pseudo-code, and a repo-wide search for
`inTwoMoves` / `hover=` in `docs/` returns nothing — **none** of the macro's keywords are documented
today. Documenting `jerk` alone would be as inconsistent as adding it to the Allium spec, which is
skipped for the same reason (`specs/winder-macros.allium:159` models neither `hover`, `offset`, nor
`inTwoMoves`). A single reference covering all four keywords is worth writing, but that is its own task.

## Tests

- **`tests/dune_winder/test_app_config.py`** — defaults are 1500/1000/2000; a `set()` round-trips through
  disk; a `<= 0` or non-finite value falls back to the default. Copy the tmpdir + reload shape of
  `test_x_backlash_compensation_defaults_and_persists` (line 57-67).
- **`tests/dune_winder/test_gcode_domain.py:148-158`** — add `"anchorToTarget(B1201,B2001,jerk=gentle)"`
  to the parse/render round-trip loop.
- **`tests/dune_winder/test_wrap_runtime.py`** — `~anchorToTarget(...,jerk=gentle)` puts
  `accel_jerk == 1000.0` on the emitted `"xy"` pending action(s); no keyword leaves the key absent; an
  `inTwoMoves=True` split carries it on **both** actions; `jerk=bogus` raises `GCodeExecutionError`.
- **`tests/dune_winder/test_plc_logic.py`** — `setXY_Position(..., accelJerk=1000.0)` writes
  `Program:state_3_move_xy.xy_regulated_accel_jerk` as int `1000` **before** `STATE_REQUEST`; with
  `accelJerk=None` it writes the `setupLimits` default instead. Assert ordering, not just the values.
- **`tests/dune_winder/test_command_validation.py:63-99`** — add a `gcode_line` case carrying `jerk=` so
  the `commands.py` regex copy is covered.

Both simulators accept an unknown `Program:`-prefixed write without error (they fall through to a generic
dict store — `simulated_plc.py:332-418`, `ladder_simulated_plc.py:727-803`), so no simulator change is
needed. The ladder simulator will *store* but not *act on* the value, because
`plc_ladder/runtime.py:190-211` does not strip the `Program:` prefix — out of scope, and worth a one-line
comment in the test so the next reader does not chase it.

## Verification

1. `uv run pytest tests/dune_winder -k "app_config or plc_logic or wrap_runtime or gcode_domain"`
2. `uv run ruff format src tests && uv run ruff check src tests && uv run ty check`
3. `uv run pytest tests/dune_winder` — full suite. Per the known xdist flake, if something fails under
   the default `-n auto` but passes under `-n0`, it is a cold-worker timeout, not this change.
4. `uv run dune-winder` in sim mode → Configuration page → confirm the three new fields render, show
   1500/1000/2000, validate (letters turn the box red), and Save persists to `winder/configuration.toml`.
5. Run a G-code line `~anchorToTarget(B1201,B2001,jerk=gentle)` in sim and confirm via the sim tag
   inspector that `Program:state_3_move_xy.xy_regulated_accel_jerk` reads 1000 during that move and is
   back to 1500 on the next plain XY move.
6. On real hardware, with tension control **and** the speed regulator switch on, watch the tag in Studio
   5000 across a `jerk=jerky` line and confirm the value tracks and the motion profile changes.
