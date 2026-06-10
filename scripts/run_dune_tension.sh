#!/bin/bash
set -e

# Run from the repo root regardless of where the script is invoked from.
cd "$(dirname "$0")/.."

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

echo "Run sequence completed successfully."
