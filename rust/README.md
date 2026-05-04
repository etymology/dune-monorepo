# Rust Workspace

This workspace is the home for the incremental Rust rewrite of the DUNE winder
and tension tools. Rust code is tested through Cargo and, where exposed through
PyO3, installed into the root Python environment through `uv` local path
dependencies.

## Crates

- `crates/dune-audio` contains Rust audio capture, DSP helpers, HCQT
  preprocessing, and ONNX Runtime inference. It is a Rust library crate used by
  the Python-facing crates.
- `crates/dune-python` exposes the PyO3 module installed as
  `dune_tension._rust_audio`.
- `crates/dune_tension_core` exposes the PyO3 module installed as
  `dune_tension_core`.
- `crates/dune_geometry` contains APA geometry, pin, wire, spine, and
  calibration logic. It builds both a Rust library and the `dune_geometry` PyO3
  module.
- `crates/dune_plc_bus` contains PLC tag bus primitives and Python bridge
  helpers. It builds both a Rust library and the `dune_plc_bus` PyO3 module.

The root `pyproject.toml` maps those Python package names to local crate paths
with `tool.uv.sources`. Run `uv sync` from the monorepo root after changing
Python package metadata, PyO3 module names, crate features, or lockfiles.

The Python layer imports the extension only through
`src/dune_tension/rust_audio.py`. Runtime selection is controlled by:

- `DUNE_AUDIO_BACKEND=auto|rust|python`
- `PESTO_BACKEND=auto|rust_onnx|onnx|pytorch`

`DUNE_AUDIO_BACKEND=auto` prefers Rust for DSP helpers where the extension is
available. Live microphone capture uses Rust only when the extension was built
with `cpal-capture`; otherwise it stays on the existing Python `sounddevice`
path. `PESTO_BACKEND=auto` keeps live neural-network inference on PyTorch; use
`PESTO_BACKEND=rust_onnx` explicitly to exercise the Rust ONNX runtime.

## Build And Test

Install all Python dependencies and local PyO3 packages into the shared root
`.venv`:

```bash
uv sync
```

Explicitly rebuild the audio extension while iterating on audio backend code:

```bash
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml
```

Run the Rust tests:

```bash
cargo test --workspace --manifest-path rust/Cargo.toml
```

Run Python tests that exercise the PyO3 surfaces:

```bash
uv run pytest tests/dune_tension tests/dune_geometry tests/dune_plc_bus
```

For a cross-boundary change, run both the Python and Rust suites:

```bash
uv run pytest
cargo test --workspace --manifest-path rust/Cargo.toml
```

The default build excludes live microphone capture so the workspace can build
on machines without ALSA development headers. Enable CPAL capture explicitly
when building on a host with the native audio headers installed:

```bash
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml --features cpal-capture
```

## PESTO ONNX Artifacts

The runtime uses the checked-in `mir-1k_g7` artifacts in
`dune_tension/data/pesto_onnx/`. Regenerate them with:

```bash
uv run python -m spectrum_analysis.export_pesto_onnx --model-name mir-1k_g7 --step-size 5.0 --sampling-rate 44100
```
