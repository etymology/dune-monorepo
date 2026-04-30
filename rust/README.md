# Rust Workspace

This workspace is the home for the incremental Rust rewrite of the DUNE
winder and tension tools. The first production boundary is the `dune_tension`
audio hot path and PESTO ONNX inference.

## Crates

- `crates/dune-audio` contains Rust audio capture, DSP helpers, HCQT
  preprocessing, and ONNX Runtime inference.
- `crates/dune-python` exposes the PyO3 module installed as
  `dune_tension._rust_audio`.

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

Install the extension into the repository virtual environment:

```bash
uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml
```

Run the Rust tests:

```bash
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
