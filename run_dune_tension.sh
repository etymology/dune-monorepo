#!/bin/bash
set -e

echo "--- Building dune-tension-core (Rust) ---"
uv run maturin build --manifest-path rust/crates/dune_tension_core/Cargo.toml

# Copy the built library to the site-packages if on Darwin (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "--- Installing extension (macOS) ---"
    cp rust/target/debug/libdune_tension_core.dylib ./.venv/lib/python3.13/site-packages/dune_tension_core/dune_tension_core.abi3.so
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "--- Installing extension (Linux) ---"
    cp rust/target/debug/libdune_tension_core.so ./.venv/lib/python3.13/site-packages/dune_tension_core/dune_tension_core.abi3.so
fi

echo "--- Running Rust/Python Surface Tests ---"
uv run python tests/dune_tension/test_rust_surface.py

echo "--- Launching dune-tension Interface (Spoofed) ---"
if [[ "$*" == *"--gui"* ]]; then
    echo "Starting full GUI..."
    uv run dune-tension-gui --spoof --spoof-movement
else
    # Use 'spoof=True' to ensure it runs without actual hardware
    uv run python -c "
from dune_tension.tensiometer import build_tensiometer
import threading
import time

print('Initializing spoofed tensiometer...')
t = build_tensiometer(
    apa_name='APA1',
    layer='U',
    side='A',
    spoof=True,
    spoof_movement=True
)

print('Initialization successful.')
"
fi

echo "Build, Run, and Test sequence completed successfully."
