# Standardize APA Names + GUI Dropdowns

## Context

APA names in `dune_tension` are currently a free-text `tk.Entry`. Over time
this has produced ~17 variant spellings in `tension_data.db` (`USAPA12`,
`UKAPA7`, `APAUK007`, `USAPA10TEST`, `USAPA10v2`, `USAPA999`, …) — there is
no validation, no zero-padding, and no canonical format.

The fix is forward-only:
1. Define a canonical format — **`APA-US-001` … `APA-US-152`** and **`APA-UK-001`
   … `APA-UK-152`** (304 valid names total).
2. Replace the free-text `entry_apa` widget with two dropdowns (location
   US/UK + zero-padded number 001–152) so operators cannot enter a
   non-canonical name going forward.

Existing rows in `tension_data.db` / `audio_recordings.db` and existing files
on disk are **left untouched**. New measurements use the canonical form. Code
that reads historical data continues to work because `apa_name` remains a
plain `TEXT` column — only the *write* path is constrained.

## Critical files

**New**
- `src/dune_tension/apa_naming.py` — canonical-name helper.
- `src/dune_tension/tests/test_apa_naming.py` — unit tests.

**Modified**
- `src/dune_tension/gui/context.py` — replace `entry_apa: tk.Entry` with
  `apa_location_var: tk.StringVar` + `apa_number_var: tk.StringVar`.
- `src/dune_tension/gui/app.py` — replace the `entry_apa` widget with two
  `OptionMenu`s; update GUIWidgets construction; fix the read site at line 148.
- `src/dune_tension/gui/actions.py` — fix the two read sites (≈line 258 and
  ≈line 1886) to compose the canonical name from the two StringVars.
- `src/dune_tension/gui/state.py` — change `_PersistedState` save/load paths;
  the existing `_set_entry` helper does not work on `StringVar`.

## Step 1 — Naming helper (`apa_naming.py`)

Small, dependency-free module:

```
LOCATIONS = ("US", "UK")
NUMBERS = range(1, 153)        # 1..152 inclusive

def compose(location: str, number: int) -> str
def parse(name: str) -> tuple[str, int] | None
def is_canonical(name: str) -> bool
def all_canonical_names() -> list[str]   # 304 entries
```

`compose` returns `f"APA-{location}-{number:03d}"` and raises on out-of-range
input. `parse` accepts only the exact regex `^APA-(US|UK)-(\d{3})$` and
validates the number is in 1..152. `is_canonical` is `parse(...) is not None`.

No legacy normalization logic — we are not migrating old names.

## Step 2 — GUI dropdowns (`app.py`, `context.py`)

In `app.py`, around lines 357–360, replace:

```
tk.Label(apa_frame, text="APA Name:").grid(row=0, column=0, sticky="e")
entry_apa = tk.Entry(apa_frame)
entry_apa.grid(row=0, column=1)
```

with two label/OptionMenu pairs that mirror the existing layer/side pattern at
lines 371–377:

```
tk.Label(apa_frame, text="APA Location:").grid(row=0, column=0, sticky="e")
apa_location_var = tk.StringVar(apa_frame, value="US")
tk.OptionMenu(apa_frame, apa_location_var, *apa_naming.LOCATIONS).grid(row=0, column=1)

tk.Label(apa_frame, text="APA Number:").grid(row=0, column=2, sticky="e")
apa_number_var = tk.StringVar(apa_frame, value="001")
tk.OptionMenu(apa_frame, apa_number_var, *(f"{n:03d}" for n in apa_naming.NUMBERS)).grid(row=0, column=3)
```

(Existing rows 1+ in `apa_frame` keep their current row indices — we are only
filling columns 0–3 of row 0.)

In `context.py`, replace `entry_apa: tk.Entry` with:

```
apa_location_var: tk.StringVar
apa_number_var: tk.StringVar
```

In `app.py`'s `GUIWidgets(...)` constructor (≈line 674), drop `entry_apa=…`
and pass the two new vars. In `app.py:148`, change
`apa_name=ctx.widgets.entry_apa.get()` to:

```
apa_name=apa_naming.compose(
    ctx.widgets.apa_location_var.get(),
    int(ctx.widgets.apa_number_var.get()),
)
```

Add a small helper at the top of `actions.py` (the same composition is needed
in two places, ≈line 258 and ≈line 1886):

```
def _current_apa_name(w: GUIWidgets) -> str:
    return apa_naming.compose(w.apa_location_var.get(), int(w.apa_number_var.get()))
```

Use it from `_get_inputs` and `_make_config_from_widgets`.

## Step 3 — State persistence (`state.py`)

Keep `_PersistedState.apa_name: str` storing the composed canonical name —
this avoids JSON-schema churn and is what every downstream consumer already
expects.

Save (≈line 67) becomes:

```
apa_name=_current_apa_name(w),
```

Load (≈line 145) replaces the `_set_entry` call with:

```
parsed = apa_naming.parse(data.get("apa_name", ""))
location, number = parsed if parsed else ("US", 1)
w.apa_location_var.set(location)
w.apa_number_var.set(f"{number:03d}")
```

The fallback covers fresh installs and stale state files containing legacy
free-text names (e.g. `USAPA12`) — they map to the default selection on next
launch and the operator picks the correct dropdown values.

## Step 4 — Tests (`tests/test_apa_naming.py`)

- `compose` produces `APA-US-001` and `APA-UK-152`; rejects bad locations and
  out-of-range numbers (0, 153, negative).
- `parse` round-trips with `compose` for every value in
  `all_canonical_names()` and returns `None` for malformed inputs (`USAPA12`,
  `APA-US-1`, `APA-US-153`, `APA-DE-001`, empty string, lowercase).
- `all_canonical_names()` has length 304 and is sorted.

## Risks

- **Stale `gui_state.json`.** Handled by the load fallback.
- **Read paths still see legacy names.** Intentional — historical data stays
  queryable under its original spelling. Anywhere code joins old + new data
  by `apa_name` will continue to treat them as distinct APAs; that is the
  correct behavior under "do not modify old APAs."
- **Operators can no longer reproduce a legacy spelling.** Acceptable: that's
  the whole point. If someone needs to write more rows under an old name,
  they can do it directly in SQL or by temporarily restoring the Entry
  widget.

## Verification

1. `python -m pytest src/dune_tension/tests/test_apa_naming.py` — naming
   helper tests pass.
2. Launch the GUI. Confirm the APA frame shows two dropdowns: Location
   (US/UK) and Number (001–152). The free-text Entry is gone.
3. Pick `US` / `012`, run a measurement, then check
   `sqlite3 dune_tension/data/tension_data/tension_data.db
   "SELECT DISTINCT apa_name FROM tension_data WHERE apa_name LIKE 'APA-%';"`
   — confirm `APA-US-012` appears.
4. Restart the GUI; confirm `APA-US-012` is restored as the selection from
   `gui_state.json`.
5. Run the GUI once with a stale `gui_state.json` containing
   `"apa_name": "USAPA12"` — confirm the dropdowns fall back to `US` /
   `001` cleanly without crashing.
