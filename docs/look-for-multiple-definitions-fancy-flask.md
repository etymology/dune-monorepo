# Centralize U/V Layer Geometry Definitions

## Context

Geometry constants for the U and V layers (pin boundaries, wrap counts, pin sequences, pull-in values, comb positions) are duplicated across 6+ files. The centralized `UvLayerLayout` in `uv_layout.py` already has raw data (side ranges, endpoint pins, tangent ranges) but doesn't expose it in the form consumers need. Each consumer independently hardcodes its own copies of derived values like named endpoint pins, wrap parameters, and pin sequences. A change to pin numbering requires updating multiple files independently, risking inconsistency.

There is also a latent bug: `v_template_gcode.py` sets `PIN_MAX=2400` but V-layer geometry only has 2399 pins (1-2399). The `_wrap_pin_number()` function with `PIN_SPAN=2400` would return 2400 for edge inputs, producing a non-existent pin. This doesn't trigger in practice because wrap 400 uses a special final-tail script with literal pin numbers, but it's incorrect.

### Code paths that must remain working

1. **G109/G103 in normal mode** (U_WRAP_SCRIPT, V_WRAP_BASE_SCRIPT + tail scripts): Template strings like `emit G109 PB${1200 + wrap}` are compiled at module load via `compile_template_script()`. The `${...}` expressions are `eval()`'d at execution time with an environment dict. The literal pin numbers (1200, 2002, 800, etc.) in these strings **cannot be changed** -- they remain as-is. What CAN change is the module-level Python constants (PIN_MIN, PIN_MAX, WRAP_COUNT, etc.) and the environment values (Y_PULL_IN, X_PULL_IN, COMB_PULL_FACTOR).

2. **G115/G117/G118 in wrapping mode** (U_WRAP_WRAPPING_SCRIPT): Same template-string constraint. Additionally, `_render_wrapping_wrap_lines()` (lines 663-754) uses hardcoded endpoint pins in Python code -- these CAN be centralized.

3. **anchorToTarget macro** (~anchorToTarget): Called from wrapping-mode gcode at runtime. The handler `_plan_explicit_wrap_transition()` at handler_base.py:531 already calls `plan_wrap_transition()` which uses `get_uv_layout()` internally. **No changes needed** in the anchorToTarget execution path.

4. **_wrap_symbolic_numbers()** in handler_base.py: Provides named pin resolution for `~` macro expressions. Currently only supports U layer. Should be extended to V using the layout.

5. **V XZ variants** (V_WRAP_BASE_SCRIPT_XZ, V_WRAP_NORMAL_TAIL_SCRIPT_XZ, V_WRAP_FINAL_TAIL_SCRIPT_XZ): Same constraints as default V scripts -- template strings stay as-is, only Python constants change.

---

## Step 1: Add `UvWrapParams` and derived properties to `uv_layout.py`

**File**: [uv_layout.py](src/dune_winder/machine/geometry/uv_layout.py)

### 1a. Add `UvWrapParams` frozen dataclass (after `WrapOrientation` class, around line 117)

```python
@dataclass(frozen=True)
class UvWrapParams:
    wrap_count: int
    segments_per_wrap: int  # always 12
    combs: tuple[int, ...]
    y_pull_in: float
    x_pull_in: float
    comb_pull_factor: float
```

### 1b. Add `_WRAP_PARAMS` dict (after `_LAYOUT_SPECS`, around line 91)

```python
_WRAP_PARAMS = {
    "U": UvWrapParams(
        wrap_count=400,
        segments_per_wrap=12,
        combs=(596, 744, 892, 1040, 1758, 1906, 2054, 2202),
        y_pull_in=200.0,
        x_pull_in=200.0,
        comb_pull_factor=3.0,
    ),
    "V": UvWrapParams(
        wrap_count=400,
        segments_per_wrap=12,
        combs=(596, 744, 892, 1040, 1758, 1906, 2054, 2202),
        y_pull_in=60.0,
        x_pull_in=70.0,
        comb_pull_factor=3.0,
    ),
}
```

### 1c. Store `wrap_params` in `UvLayerLayout.__init__` (around line 225)

After `self._bootstrap_pins = ...`:
```python
self.wrap_params = _WRAP_PARAMS[self.layer]
```

### 1d. Add `named_pins` property (after `bootstrap_pins` property, around line 515)

Derives the 8 named endpoint pins from `self.side_ranges`:

```python
@property
def named_pins(self) -> dict[str, int]:
    sr = self.side_ranges
    return {
        "bottom_foot_end": sr["bottom"][1],
        "bottom_head_end": sr["bottom"][0],
        "top_foot_end": sr["top"][0],
        "top_head_end": sr["top"][1],
        "foot_bottom_end": sr["foot"][0],
        "foot_top_end": sr["foot"][1],
        "head_bottom_end": sr["head"][1],
        "head_top_end": sr["head"][0],
    }
```

This maps to:
- **U**: bottom_foot_end=1200, bottom_head_end=401, top_foot_end=1602, top_head_end=2401, foot_bottom_end=1201, foot_top_end=1601, head_bottom_end=400, head_top_end=1
- **V**: bottom_foot_end=1199, bottom_head_end=400, top_foot_end=1600, top_head_end=2399, foot_bottom_end=1200, foot_top_end=1599, head_bottom_end=399, head_top_end=1

### 1e. Add `wrap_pin_sequence` method

Returns the 12-pin tuple for one wrap (0-based wrap_index). U and V have different trajectories. Uses `self.translate_pin()` for B-to-A conversion.

```python
def wrap_pin_sequence(self, wrap_index: int) -> tuple[str, ...]:
    """Return 12 pin names for one wrap (wrap_index is 0-based)."""
    n = wrap_index
    wc = self.wrap_params.wrap_count
    np = self.named_pins

    def b(pin: int) -> str:
        return f"B{self._wrap_pin(pin)}"

    def a_from_b(pin: int) -> str:
        b_name = f"B{self._wrap_pin(pin)}"
        return self.translate_pin(b_name, "A")

    if self.layer == "U":
        return (
            b(np["foot_bottom_end"] + n),
            b(np["top_foot_end"] + wc - 1 - n),
            a_from_b(np["top_foot_end"] + wc - 1 - n),
            a_from_b(np["bottom_head_end"] + n),
            b(np["bottom_head_end"] + n),
            b(np["head_bottom_end"] - n),
            a_from_b(np["head_bottom_end"] - n),
            a_from_b(np["top_head_end"] - wc + 1 + n),
            b(np["top_head_end"] - wc + 1 + n),
            b(np["bottom_foot_end"] - n),
            a_from_b(np["bottom_foot_end"] - n),
            a_from_b(np["foot_bottom_end"] + n + 1),
        )
    else:  # V
        return (
            b(np["bottom_head_end"] + n),
            b(np["top_foot_end"] + wc - 1 - n),
            a_from_b(np["top_foot_end"] + wc - 1 - n),
            a_from_b(np["foot_bottom_end"] + n),
            b(np["foot_bottom_end"] + n),
            b(np["bottom_foot_end"] - n),
            a_from_b(np["bottom_foot_end"] - n),
            a_from_b(np["top_head_end"] - wc + 1 + n),
            b(np["top_head_end"] - wc + 1 + n),
            b(np["head_bottom_end"] - n),
            a_from_b(np["head_bottom_end"] - n),
            a_from_b(np["bottom_head_end"] + n + 1),
        )
```

### 1f. Add `_wrap_pin` helper method

Centralizes the modular wrapping of pin numbers that each template module currently duplicates:

```python
def _wrap_pin(self, value: int) -> int:
    """Wrap a pin number into the valid range [1, pin_max]."""
    return ((value - 1) % self.pin_max) + 1
```

### 1g. Add `full_wrap_pin_sequence` method

```python
def full_wrap_pin_sequence(self) -> tuple[str, ...]:
    """Return all pins for all wraps (wrap_count * segments_per_wrap)."""
    pins: list[str] = []
    for i in range(self.wrap_params.wrap_count):
        pins.extend(self.wrap_pin_sequence(i))
    return tuple(pins)
```

### 1h. Update `__all__` to include new exports

Add `"UvWrapParams"` to `__all__`.

---

## Step 2: Replace constants in `u_template_gcode.py`

**File**: [u_template_gcode.py](src/dune_winder/recipes/u_template_gcode.py)

### 2a. Add import and create layout instance (after existing imports, around line 19)

```python
from dune_winder.machine.geometry.uv_layout import get_uv_layout
_U_LAYOUT = get_uv_layout("U")
```

### 2b. Replace module-level constants (lines 30-49)

**Replace** these definitions:
- `WRAP_COUNT = 400` → `WRAP_COUNT = _U_LAYOUT.wrap_params.wrap_count`
- `Y_PULL_IN = 200.0` → `Y_PULL_IN = _U_LAYOUT.wrap_params.y_pull_in`
- `X_PULL_IN = 200.0` → `X_PULL_IN = _U_LAYOUT.wrap_params.x_pull_in`
- `COMB_PULL_FACTOR = 3.0` → `COMB_PULL_FACTOR = _U_LAYOUT.wrap_params.comb_pull_factor`
- `COMBS = (596, 744, 892, 1040, 1758, 1906, 2054, 2202)` → `COMBS = _U_LAYOUT.wrap_params.combs`
- `PIN_MAX = 2401` → `PIN_MAX = _U_LAYOUT.pin_max`
- `PIN_SPAN = PIN_MAX - PIN_MIN + 1` → keep as-is (derives from updated PIN_MAX)
- `DEFAULT_PULL_INS`: change to use `_U_LAYOUT.wrap_params.y_pull_in` and `x_pull_in` instead of module-level Y_PULL_IN/X_PULL_IN (or keep referencing the module-level names since they now come from the layout)

**Do NOT change**:
- `PIN_MIN = 1` (same for both layers, keep as-is)
- `PREAMBLE_X`, `PREAMBLE_Y`, `PREAMBLE_BOARD_GAP_PULL` (U-layer-specific, not duplicated geometry)
- `DEFAULT_OFFSETS`, `DEFAULT_U_TEMPLATE_WORKBOOK`, etc. (not geometry)
- `FOOT_PAUSE_MIN_PIN = 1200`, `FOOT_PAUSE_MAX_PIN = 1600` (boundary pin values that include edge pins outside strict face ranges -- verify separately)
- Template script strings `U_WRAP_SCRIPT` and `U_WRAP_WRAPPING_SCRIPT` (lines 101-159): The literal pin numbers in `${...}` expressions like `${1200 + wrap}` are compiled at import time and cannot reference layout methods.

### 2c. Replace hardcoded pins in `_render_wrapping_wrap_lines()` (lines 663-754)

This function builds gcode lines for wrapping mode using `anchor_to_target()`. It uses hardcoded endpoint pins:

- `1201 + n` → `_U_LAYOUT.named_pins["foot_bottom_end"] + n`
- `1602 + (399 - n)` → `_U_LAYOUT.named_pins["top_foot_end"] + (WRAP_COUNT - 1 - n)`
- `401 + n` → `_U_LAYOUT.named_pins["bottom_head_end"] + n`
- `400 - n` → `_U_LAYOUT.named_pins["head_bottom_end"] - n`
- `n - 399` → `n - (WRAP_COUNT - 1)` (result passed to `_wrap_pin_number()`)
- `1 - 399 + n` → equivalent to above, keep `_wrap_pin_number()` call
- `1200 - n` → `_U_LAYOUT.named_pins["bottom_foot_end"] - n`
- `1201 + n + 1` → `_U_LAYOUT.named_pins["foot_bottom_end"] + n + 1`
- `b_to_a_pin("U", ...)` calls: already centralized, keep as-is
- `_wrap_pin_number(...)` calls: keep, now uses centralized PIN_MAX/PIN_SPAN
- `_near_comb(...)` calls: keep, uses centralized COMBS

Also at line 787: `b_to_a_pin("U", "B1601")` uses literal pin 1601 (foot_top_end for U). Could use `_U_LAYOUT.named_pins["foot_top_end"]` but this is a one-off; optional.

### 2d. Update environment dicts (lines 582-593 and 639-650)

The `environment` dicts pass constants to template execution. Currently reference module-level `COMB_PULL_FACTOR`. After step 2b, these already point to layout-derived values, so no change needed (they reference `COMB_PULL_FACTOR` which now comes from the layout).

---

## Step 3: Replace constants in `v_template_gcode.py`

**File**: [v_template_gcode.py](src/dune_winder/recipes/v_template_gcode.py)

### 3a. Add import and create layout instance (after existing imports, around line 21)

```python
from dune_winder.machine.geometry.uv_layout import get_uv_layout
_V_LAYOUT = get_uv_layout("V")
```

### 3b. Replace module-level constants (lines 29-46)

**Replace** these definitions:
- `WRAP_COUNT = 400` → `WRAP_COUNT = _V_LAYOUT.wrap_params.wrap_count`
- `PRE_FINAL_WRAP_COUNT = WRAP_COUNT - 1` → keep as-is (derives from updated WRAP_COUNT)
- `Y_PULL_IN = 60.0` → `Y_PULL_IN = _V_LAYOUT.wrap_params.y_pull_in`
- `X_PULL_IN = 70.0` → `X_PULL_IN = _V_LAYOUT.wrap_params.x_pull_in`
- `COMB_PULL_FACTOR = 3.0` → `COMB_PULL_FACTOR = _V_LAYOUT.wrap_params.comb_pull_factor`
- `COMBS = (596, 744, 892, 1040, 1758, 1906, 2054, 2202)` → `COMBS = _V_LAYER.wrap_params.combs`
- `PIN_MAX = 2400` → `PIN_MAX = _V_LAYOUT.pin_max` (**fixes bug**: 2400 → 2399)
- `PIN_SPAN = PIN_MAX - PIN_MIN + 1` → keep as-is

**Do NOT change**:
- `PIN_MIN = 1`
- `PREAMBLE_BOARD_GAP_PULL`, `DEFAULT_OFFSETS`, etc.
- `FOOT_PAUSE_MIN_PIN = 1200`, `FOOT_PAUSE_MAX_PIN = 1600`
- Template script strings (V_WRAP_BASE_SCRIPT, V_WRAP_NORMAL_TAIL_SCRIPT, V_WRAP_FINAL_TAIL_SCRIPT, and all XZ variants at lines 94-195): literal pin numbers in `${...}` stay as-is.

### 3c. Verify PIN_MAX fix doesn't break output

All V template pin expressions stay within 1-2399 for wraps 1-400:
- `${399 + wrap}` → max 799
- `${1999 + wrap}` → max 2399
- `${2399 - wrap}` → max 2398
- Wrap 400 uses `V_WRAP_FINAL_TAIL_SCRIPT` with literal pins PB2398, PB2399

The `_wrap_pin_number()` function with PIN_SPAN=2399 now correctly wraps:
- `_wrap_pin_number(2400)` → `((2400-1) % 2399) + 1` = 1 (was 2400 with old PIN_SPAN=2400)
- `_wrap_pin_number(0)` → hits the `if pin_number < PIN_MIN: return PIN_MAX` branch → returns 2399 (was 2400)

---

## Step 4: Replace constants in `handler_base.py`

**File**: [handler_base.py](src/dune_winder/gcode/handler_base.py)

### 4a. Add import (at top of file, with other imports)

```python
from dune_winder.machine.geometry.uv_layout import get_uv_layout
```

### 4b. Replace `_wrap_symbolic_numbers()` (lines 254-276)

Current code hardcodes U-only pin names and U-only pull-in defaults. Replace with:

```python
def _wrap_symbolic_numbers(self):
    layer = None
    if self._layerCalibration is not None:
        layer = str(self._layerCalibration.getLayerNames()).strip().upper()
    values = {
        "x_pull_in": 200.0,
        "y_pull_in": 200.0,
        "comb_pull_factor": 3.0,
    }
    if layer in ("U", "V"):
        layout = get_uv_layout(layer)
        values.update(layout.named_pins)
        values["x_pull_in"] = layout.wrap_params.x_pull_in
        values["y_pull_in"] = layout.wrap_params.y_pull_in
        values["comb_pull_factor"] = layout.wrap_params.comb_pull_factor
    return values
```

This extends symbolic-number support to the V layer (previously only U was supported). The `named_pins` dict keys match the existing symbolic names (`bottom_foot_end`, `bottom_head_end`, etc.).

### 4c. No changes to `_plan_explicit_wrap_transition` or `_plan_wrap_transition`

These already call `plan_wrap_transition()` from `uv_wrap_geometry.py`, which uses `get_uv_layout()` internally. The anchorToTarget path is already fully centralized.

---

## Step 5: Replace constants in `uv_head_target_gui.py`

**File**: [uv_head_target_gui.py](src/dune_winder/uv_head_target_gui.py)

### 5a. Add import (with existing imports)

```python
from dune_winder.machine.geometry.uv_layout import get_uv_layout
```

### 5b. Replace `_TOTAL_WRAPS` and `_SEGMENTS_PER_WRAP` (line 37-38)

```python
_U_LAYOUT = get_uv_layout("U")
_V_LAYOUT = get_uv_layout("V")
_TOTAL_WRAPS = _U_LAYOUT.wrap_params.wrap_count
_SEGMENTS_PER_WRAP = _U_LAYOUT.wrap_params.segments_per_wrap
```

### 5c. Replace `_u_pin_sequence()` (lines 42-72)

Replace the entire function with:
```python
@lru_cache(maxsize=1)
def _u_pin_sequence() -> tuple[str, ...]:
    return _U_LAYOUT.full_wrap_pin_sequence()
```

### 5d. Replace `_v_pin_sequence()` (lines 76-105)

Replace the entire function with:
```python
@lru_cache(maxsize=1)
def _v_pin_sequence() -> tuple[str, ...]:
    return _V_LAYOUT.full_wrap_pin_sequence()
```

This removes the inline `b_to_a()` and `b()` functions and the hardcoded endpoint pin values, using the centralized layout instead.

---

## Step 6: Verify and test

### 6a. Run existing test suite

```bash
pytest tests/ -x
```

### 6b. Verify U template gcode output is unchanged

Run the U template generator and diff output against pre-change output. The template strings are untouched so normal-mode output should be identical. Wrapping-mode output uses `_render_wrapping_wrap_lines()` with layout-derived pins -- verify these produce the same pin numbers.

### 6c. Verify V template gcode output is unchanged

Same as above for V layer. The PIN_MAX change from 2400 to 2399 does NOT affect any template output:
- All V template pin expressions evaluate within 1-2399
- Wrap 400 uses V_WRAP_FINAL_TAIL_SCRIPT with literal pins PB2398, PB2399
- `_wrap_pin_number()` is only called on generated pin numbers that are already in range

### 6d. Verify uv_head_target_gui pin sequences

Call `_u_pin_sequence()` and `_v_pin_sequence()` and verify the output matches the previous hardcoded sequences element-by-element.

### 6e. Verify handler_base.py symbolic numbers

Test that `_wrap_symbolic_numbers()` returns correct values for both U and V layers, including the new V-layer pin names.

### 6f. Add unit tests for new layout methods

In a test file for `uv_layout.py`:
- Test `UvWrapParams` is stored correctly for both U and V
- Test `named_pins` returns correct values for both layers (compare against known values)
- Test `wrap_pin_sequence(0)` and `wrap_pin_sequence(399)` for U match the first and last wraps from the old `_u_pin_sequence()`
- Test `wrap_pin_sequence(0)` and `wrap_pin_sequence(399)` for V match the old `_v_pin_sequence()`
- Test `full_wrap_pin_sequence()` produces 400 * 12 = 4800 pins for both layers
- Test `_wrap_pin()` for edge cases (0, pin_max+1, negative values)

---

## Files modified

| File | Change | Lines affected |
|------|--------|----------------|
| [uv_layout.py](src/dune_winder/machine/geometry/uv_layout.py) | Add `UvWrapParams`, `named_pins`, `wrap_params`, `wrap_pin_sequence`, `full_wrap_pin_sequence`, `_wrap_pin` | ~90 lines added |
| [u_template_gcode.py](src/dune_winder/recipes/u_template_gcode.py) | Import layout, replace 7 constants, replace pins in `_render_wrapping_wrap_lines` | ~30 lines changed |
| [v_template_gcode.py](src/dune_winder/recipes/v_template_gcode.py) | Import layout, replace 7 constants (incl. PIN_MAX bug fix) | ~10 lines changed |
| [handler_base.py](src/dune_winder/gcode/handler_base.py) | Import layout, rewrite `_wrap_symbolic_numbers()` | ~20 lines changed |
| [uv_head_target_gui.py](src/dune_winder/uv_head_target_gui.py) | Import layout, replace `_u_pin_sequence` and `_v_pin_sequence` | ~60 lines removed, ~10 added |
