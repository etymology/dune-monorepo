#!/usr/bin/env bash
# Launch the Upload Tensions GUI on Linux.
#
# Picks an interpreter (uv > project .venv > python3), checks that a display
# and the Tk bindings are available, then runs the GUI module.
set -euo pipefail

# Run from the repo root regardless of where the script is invoked from.
cd "$(dirname "$0")/.."

MODULE="dune_tension.gui.upload_tensions_app"

# --- Choose how to run Python -------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    RUN=(uv run python)
elif [[ -x .venv/bin/python ]]; then
    RUN=(.venv/bin/python)
elif command -v python3 >/dev/null 2>&1; then
    RUN=(python3)
else
    echo "error: no Python found (need 'uv', '.venv/bin/python', or 'python3')." >&2
    exit 1
fi

# --- Require a display --------------------------------------------------------
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "error: no display detected (DISPLAY and WAYLAND_DISPLAY are both unset)." >&2
    echo "       A graphical session is required. Over SSH, connect with 'ssh -X'." >&2
    exit 1
fi

# --- Require the Tk bindings --------------------------------------------------
if ! "${RUN[@]}" -c "import tkinter" >/dev/null 2>&1; then
    echo "error: Python's tkinter (Tk) bindings are not available." >&2
    echo "       Install them, e.g.:" >&2
    echo "         Debian/Ubuntu : sudo apt install python3-tk" >&2
    echo "         Fedora/RHEL   : sudo dnf install python3-tkinter" >&2
    echo "         Arch          : sudo pacman -S tk" >&2
    exit 1
fi

# --- Launch -------------------------------------------------------------------
echo "Launching Upload Tensions GUI..."
exec "${RUN[@]}" -m "$MODULE" "$@"
