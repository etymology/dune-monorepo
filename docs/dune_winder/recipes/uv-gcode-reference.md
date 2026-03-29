# U/V Recipe G-Code Reference

This note documents the current programmatic `U` and `V` recipe generators in:

- `src/dune_winder/recipes/u_template_gcode.py`
- `src/dune_winder/recipes/v_template_gcode.py`

It focuses on:

- which `G` commands those generators actually emit
- what the `P...` parameters mean
- how XY waypoints depend on calibration files and on geometry code

## How `P...` Parameters Work

In this codebase, a `P...` token is not its own command. The parser attaches each `P...`
token to the immediately preceding command word or `G` function.

Examples:

- `G109 PB1201 PBR`
  - `PB1201` and `PBR` are both parameters of `G109`
- `G103 PB1201 PB1200 PXY`
  - `PB1201`, `PB1200`, and `PXY` are all parameters of `G103`
- `G105 PX-50`
  - `PX-50` is a parameter of `G105`
- `G113 PPRECISE`
  - `PPRECISE` is a parameter of `G113`

The parser behavior is defined in `src/dune_winder/gcode/parser.py`: `P` words are bound to
the previous item, preserving legacy behavior.

## `G` Commands Actually Emitted By U/V

The current `U` and `V` generators emit these custom `G` commands:

| G code | Meaning in runtime | Emitted by U | Emitted by V | Changes XY directly |
| --- | --- | --- | --- | --- |
| `G102` | Seek transfer edge | yes | yes | yes |
| `G103` | Pin-center lookup | yes | yes | yes |
| `G105` | Relative coordinate offset | yes | yes | yes |
| `G106` | Head location / Z mode | yes | yes | no |
| `G108` | Arm compensation | yes | yes | yes |
| `G109` | Anchor point + wire orientation | yes | yes | no |
| `G111` | Break point / stop marker | no | yes | no |
| `G113` | Queue-merge mode | yes | yes | no |

The current `U` and `V` generators do not emit:

- `G104`
- `G110`

Both generators also emit ordinary absolute `X...`, `Y...`, and `F...` command words.
Those are not `P` parameters; they are separate command words.

## `P...` Parameters Used In U/V Recipes

### `G102`

`G102` is emitted with no `P` parameters.

Its XY result is computed from:

- the current anchor point previously established by `G109`
- the current target location accumulated so far on the line
- machine transfer bounds from machine calibration

### `G103`

Form:

```text
G103 PB... PB... PXY
G103 PF... PF... PX
G103 PF... PF... PY
```

Meaning of the parameters:

- `PB<number>` or `PF<number>`
  - pin identifiers
  - these are looked up by exact string in the active layer calibration
- `PXY`, `PX`, `PY`
  - axis selector for which coordinates to update from the computed pin center
  - `PXY` updates both X and Y
  - `PX` updates only X
  - `PY` updates only Y

Runtime behavior:

- fetch pin A location from layer calibration
- fetch pin B location from layer calibration
- compute their midpoint
- add `layerCalibration.offset`
- write X and/or Y depending on the axis selector

### `G105`

Form:

```text
G105 PX...
G105 PY...
G105 PX... PY...
```

Meaning of the parameters:

- `PX<number>`
  - add a relative delta to X
- `PY<number>`
  - add a relative delta to Y

Examples:

- `G105 PX-50`
- `G105 PY30`
- `G105 PX12`

### `G106`

Form:

```text
G106 P0
G106 P1
G106 P2
G106 P3
```

Meaning of the parameter:

- `P0`
  - use machine `zFront`
- `P1`
  - use layer calibration `zFront`
- `P2`
  - use layer calibration `zBack`
- `P3`
  - use machine `zBack`

Notes:

- `U` and `V` preambles emit `G106 P3`
- transfer helper lines can emit `P0`, `P1`, `P2`, and `P3`
- `P1` and `P2` appear only when the optional transfer-pause mode is enabled

`G106` does not change XY by itself, but later compensation math uses the Z mode it selects.

### `G108`

`G108` is emitted with no `P` parameters.

It adjusts the current XY target using head-arm and roller compensation.

### `G109`

Form:

```text
G109 PB... PBR
G109 PF... PLT
...
```

Meaning of the parameters:

- `PB<number>` or `PF<number>`
  - anchor pin identifier
- orientation token
  - the current U/V scripts emit these forms:
    - `PBR`
    - `PBL`
    - `PLT`
    - `PLB`
    - `PRT`
    - `PRB`
    - `PTR`
    - `PTL`

More precisely, after the parser strips the leading `P`, the runtime orientation string is one
of:

- `BR`
- `BL`
- `LT`
- `LB`
- `RT`
- `RB`
- `TR`
- `TL`

These orientation strings tell head compensation which tangent solution to use around the anchor
pin. They do not mean "move right" or "move left" directly; they describe which side of the pin
the wire occupies for compensation math.

`G109` sets state for later `G102` and `G108`; it does not request an XY move by itself.

### `G111`

`G111` is emitted with no `P` parameters.

It appears only in the `V` final-tail sequence.

### `G113`

Form:

```text
G113 PPRECISE
```

Meaning of the parameter:

- `PPRECISE`
  - mark the current XY waypoint as queue-merge eligible in precise mode

The runtime also supports `PTOLERANT`, but the current U/V generators emit only `PPRECISE`.

`G113` does not change coordinates. It affects how consecutive XY-only lines can be merged into a
queued motion path.

## `P` Token Quick Reference

| Token shape | Used with | Meaning |
| --- | --- | --- |
| `PB123`, `PF123` | `G103`, `G109` | Pin identifier in the active layer calibration |
| `PXY` | `G103` | Update both X and Y from the pin center |
| `PX` | `G103` | Update only X from the pin center |
| `PY` | `G103` | Update only Y from the pin center |
| `PX-50`, `PX12` | `G105` | Relative X offset |
| `PY30`, `PY-60` | `G105` | Relative Y offset |
| `P0`, `P1`, `P2`, `P3` | `G106` | Head location / Z mode |
| `PBR`, `PLT`, `PRT`, etc. | `G109` | Anchor-wire orientation for compensation |
| `PPRECISE` | `G113` | Queue-merge mode |

## XY Calculation Path In U/V Recipes

Most U/V XY targets are built from lines shaped like:

```text
G113 PPRECISE G109 ... G103 ... PXY/PX/PY G105 ... G102 G108
```

Read left to right, the runtime behavior is:

1. `G109`
   - store anchor pin and orientation
2. `G103`
   - look up two pins in the active layer calibration
   - compute center point
   - add calibration offset
   - write X and/or Y
3. `G105`
   - add local recipe-specific offset
4. `G102`
   - if present, project the path to the transfer-area boundary
5. `G108`
   - if present, apply arm/roller compensation
6. end of line
   - queue one XY move with the final X/Y values

## Where Calibration Files Enter

There are two different calibration sources involved.

### Layer Calibration JSON

The active layer calibration file is typically:

- `U_Calibration.json`
- `V_Calibration.json`

It supplies:

- pin locations used by `G103`
- anchor-pin locations used by `G109`
- `offset`, added after the pin-center calculation in `G103`
- `zFront` / `zBack`, used by `G106 P1` and `G106 P2`

This means:

- moving a pin in the layer calibration changes where `PB...` and `PF...` resolve
- changing `offset` shifts all `G103` results together
- changing `zFront` / `zBack` changes the Z reference used by partial-head modes

### Machine Calibration JSON

The machine calibration file supplies:

- transfer-area bounds used by `G102`
- machine `zFront` / `zBack` used by `G106 P0` and `G106 P3`
- head-arm and roller constants used by `G108`
- safety limits used when the XY move is finally sent to the PLC

This means:

- changing transfer bounds changes transfer seek results
- changing head geometry constants changes compensation results

## Where Geometry Code Enters

The geometry modules under `src/dune_winder/machine/geometry/` are upstream nominal definitions.

For U/V, the main files are:

- `uv.py`
- `u.py`
- `v.py`
- `factory.py`

They define the nominal pin layout, APA offsets, depths, and numbering pattern for each layer.

Those geometry definitions matter in two main ways:

1. They are used when generating a default calibration file.
2. They define the nominal layer numbering and layout that manual or generated calibrations are
   built from.

Important runtime consequence:

- the live U/V G-code interpreter mostly uses the calibration JSON already on disk
- changing geometry code alone usually does not immediately change runtime XY
- geometry changes affect runtime only after the relevant calibration files are regenerated or
  rewritten from the new geometry

## Practical Summary

For current U/V recipes:

- `PB...` and `PF...` are calibration pin references
- `PXY`, `PX`, and `PY` tell `G103` which axes to update
- `PX...` and `PY...` after `G105` are relative coordinate deltas
- `P0` through `P3` on `G106` choose which front/back Z reference to use
- `PBR`, `PLT`, and similar tokens on `G109` define anchor-wire orientation for compensation
- `PPRECISE` on `G113` affects queue merging, not coordinates

The dominant path for XY in U/V is:

layer calibration pin lookup -> optional recipe offset -> optional transfer seek -> optional arm
compensation -> final XY move
