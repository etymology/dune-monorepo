# Dune Winder PLC RLL

Minimal VS Code syntax highlighting for the normalized `pasteable.rll` ladder
files under `plc/`.

## What It Highlights

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

To install it into your normal VS Code profile, package it from this directory
and install the generated `.vsix`.
