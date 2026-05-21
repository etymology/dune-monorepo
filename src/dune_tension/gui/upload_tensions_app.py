"""Tkinter GUI for uploading measured wire tensions to the DUNE database.

Pick an APA (location + number) and layer from dropdowns, paste the action
ID of the existing "single layer tension measurements" record, and upload.
The upload runs on a background thread so the window stays responsive, and
validation failures are reported both inline and via a dialog:

* data not found      - no summary CSV for the APA/layer, or no such action
* not enough data     - a side is missing measurements for expected wires
* action not editable  - the server refused the edit
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import cast

from dune_tension import apa_naming
from dune_tension.uploadTensions import (
    ActionNotEditableError,
    DataNotFoundError,
    IncompleteMeasurementsError,
    UploadError,
    UploadResult,
    upload_tensions,
)

LAYERS: tuple[str, ...] = ("X", "V", "U", "G")
MAX_MISSING_SHOWN = 20

_ERROR_TITLES = {
    DataNotFoundError: "Data not found",
    IncompleteMeasurementsError: "Not enough measurements",
    ActionNotEditableError: "Action not editable",
}


class UploadTensionsApp:
    """Small form: APA dropdowns + action ID, with a threaded upload button."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = cast(tk.Tk, root)
        self.root.title("Upload Tensions")

        self.location_var = tk.StringVar(value=apa_naming.LOCATIONS[0])
        self.number_var = tk.StringVar(value=apa_naming.NUMBER_LABELS[0])
        self.layer_var = tk.StringVar(value=LAYERS[0])
        self.action_id_var = tk.StringVar(value="")
        self.apa_name_var = tk.StringVar(value=self._apa_name())
        self.status_var = tk.StringVar(value="Ready.")

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="APA Location:").grid(row=0, column=0, sticky="e", pady=2)
        ttk.Combobox(
            frame,
            textvariable=self.location_var,
            values=list(apa_naming.LOCATIONS),
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(frame, text="APA Number:").grid(row=1, column=0, sticky="e", pady=2)
        ttk.Combobox(
            frame,
            textvariable=self.number_var,
            values=list(apa_naming.NUMBER_LABELS),
            state="readonly",
            width=12,
        ).grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(frame, text="Layer:").grid(row=2, column=0, sticky="e", pady=2)
        ttk.Combobox(
            frame,
            textvariable=self.layer_var,
            values=list(LAYERS),
            state="readonly",
            width=12,
        ).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(frame, text="Action ID:").grid(row=3, column=0, sticky="e", pady=2)
        ttk.Entry(frame, textvariable=self.action_id_var, width=38).grid(
            row=3, column=1, sticky="ew", pady=2
        )

        ttk.Label(frame, text="APA name:").grid(row=4, column=0, sticky="e", pady=2)
        ttk.Label(frame, textvariable=self.apa_name_var).grid(
            row=4, column=1, sticky="w", pady=2
        )

        self.upload_button = ttk.Button(frame, text="Upload", command=self.on_upload)
        self.upload_button.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        ttk.Label(
            frame, textvariable=self.status_var, wraplength=380, justify="left"
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        for var in (self.location_var, self.number_var):
            var.trace_add("write", lambda *_: self.apa_name_var.set(self._apa_name()))

    def _apa_name(self) -> str:
        try:
            return apa_naming.compose(
                self.location_var.get(), int(self.number_var.get())
            )
        except (ValueError, TypeError):
            return "(invalid selection)"

    def on_upload(self) -> None:
        action_id = self.action_id_var.get().strip()
        if not action_id:
            messagebox.showerror("Upload Tensions", "Please enter an action ID.")
            return
        try:
            apa_name = apa_naming.compose(
                self.location_var.get(), int(self.number_var.get())
            )
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Upload Tensions", f"Invalid APA selection: {exc}")
            return
        layer = self.layer_var.get()

        self.upload_button.configure(state="disabled")
        self.status_var.set(f"Uploading {apa_name} layer {layer}...")
        threading.Thread(
            target=self._do_upload,
            args=(apa_name, layer, action_id),
            daemon=True,
        ).start()

    def _do_upload(self, apa_name: str, layer: str, action_id: str) -> None:
        # Runs off the Tk thread; results are marshalled back via ``after``.
        try:
            result = upload_tensions(apa_name, layer, action_id)
        except UploadError as exc:
            self.root.after(0, lambda e=exc: self._on_error(e))
        except Exception as exc:  # network/M2M failures, malformed CSV, etc.
            self.root.after(0, lambda e=exc: self._on_unexpected(e))
        else:
            self.root.after(0, lambda r=result: self._on_success(r))

    def _on_success(self, result: UploadResult) -> None:
        self.upload_button.configure(state="normal")
        message = (
            f"Uploaded {result.wires_side_a} side-A and "
            f"{result.wires_side_b} side-B tensions to action "
            f"{result.action_id}."
        )
        self.status_var.set(message)
        messagebox.showinfo("Upload Tensions", message)

    def _on_error(self, exc: UploadError) -> None:
        self.upload_button.configure(state="normal")
        title = _ERROR_TITLES.get(type(exc), "Upload failed")
        message = self._format_error(exc)
        self.status_var.set(message)
        messagebox.showerror(f"Upload Tensions - {title}", message)

    def _on_unexpected(self, exc: Exception) -> None:
        self.upload_button.configure(state="normal")
        message = f"Upload failed: {exc}"
        self.status_var.set(message)
        messagebox.showerror("Upload Tensions", message)

    @staticmethod
    def _format_error(exc: UploadError) -> str:
        if not isinstance(exc, IncompleteMeasurementsError):
            return str(exc)
        lines = [str(exc)]
        for side in ("A", "B"):
            wires = exc.missing.get(side, [])
            if not wires:
                continue
            shown = ", ".join(str(w) for w in wires[:MAX_MISSING_SHOWN])
            if len(wires) > MAX_MISSING_SHOWN:
                shown += f", ... (+{len(wires) - MAX_MISSING_SHOWN} more)"
            lines.append(f"Side {side} missing wires: {shown}")
        return "\n".join(lines)


def run_upload_tensions_app(root: tk.Misc | None = None) -> UploadTensionsApp:
    created_root = root is None
    root = root or tk.Tk()
    app = UploadTensionsApp(root)
    if created_root:
        root.mainloop()
    return app


def main() -> None:
    run_upload_tensions_app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
