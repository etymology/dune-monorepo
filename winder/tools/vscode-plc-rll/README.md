# Dune Winder PLC Ladder Text

Minimal VS Code syntax highlighting for the normalized PLC ladder text files
under `winder/plc/`.

## What It Highlights

For `.rung` files:

- `routine`, `uses`, and `local` declarations
- `when`, `always`, `on rising`, `on falling`, and `on entry of` block headers
- action forms such as `latch`, `unlatch`, and `call`
- motion DSL commands such as `servo_on`, `move_axis`, and `coordinated_move`
- instruction calls such as `OSR(...)`, `MCS(...)`, `FFL(...)`, and `TON(...)`
- boolean/arithmetic operators, numeric literals, units, strings, tags, and `?`
  placeholders
- `#` comments

For `.rll` files:

- ladder opcodes such as `XIC`, `XIO`, `CPT`, `CMP`, `JSR`, `MCLM`, and `MCCD`
- branch markers `BST`, `NXB`, and `BND`
- math functions inside expressions such as `ABS(...)` and `SQR(...)`
- tags and member paths such as `X_axis.ActualPosition` and `Local:1:I.Pt00.Data`
- quoted units like `"Units per sec2"`
- numeric literals and `?` placeholder operands
- semicolon comments

## Using It

For local development from this repository, run the `PLC RLL syntax` launch
configuration from the root workspace to open an Extension Development Host.
Files ending in `.rung` are assigned to the `PLC Rung IR` language; files
ending in `.rll` are assigned to `PLC RLL`.

To install it into your normal VS Code profile, package it from this directory
and install the generated `.vsix`.
