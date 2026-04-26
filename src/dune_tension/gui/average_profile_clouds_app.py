"""Interactive GUI for average_profile_clouds."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import threading
import traceback
import tkinter as tk
from tkinter import ttk
from typing import Any, cast

from dune_tension.average_profile_clouds import (
    AverageProfileCloudOptions,
    LayerAnalysisResult,
    PLOT_MODE_APPLIED_LENGTH,
    PLOT_MODE_ENDPOINT_CATEGORIES,
    PLOT_MODE_ENDPOINT_MAPPING,
    PLOT_MODE_LABELS,
    PLOT_MODE_WIRE_NUMBER,
    PLOT_MODE_WRAP_NUMBER,
    _save_figure_with_padding,
    build_layer_figure,
    compute_average_profile_results,
    export_layer_analysis,
    normalize_options,
    plot_mode_supported_for_layer,
)


DEFAULT_LAYERS = ",".join(AverageProfileCloudOptions().layers)
PLOT_MODE_SUFFIXES = {
    PLOT_MODE_WIRE_NUMBER: "",
    PLOT_MODE_WRAP_NUMBER: "_by_wrap",
    PLOT_MODE_APPLIED_LENGTH: "_by_applied_length",
    PLOT_MODE_ENDPOINT_MAPPING: "_by_endpoint_mapping",
    PLOT_MODE_ENDPOINT_CATEGORIES: "_by_endpoint_categories",
}


@dataclass
class LayerTabState:
    frame: Any
    status_var: Any
    scroll_canvas: Any
    content_frame: Any
    image_labels: list[Any] = field(default_factory=list)
    images: list[Any] = field(default_factory=list)
    location_labels: list[Any] = field(default_factory=list)


class AverageProfileExplorerApp:
    def __init__(self, root: tk.Misc) -> None:
        self.root = cast(tk.Tk, root)
        self.root.title("Average Profile Cloud Explorer")
        self._pending_refresh_id: Any = None
        self._refresh_generation = 0
        self._latest_options: AverageProfileCloudOptions | None = None
        self._latest_results: dict[str, list[LayerAnalysisResult]] | None = None
        self._tab_state: dict[str, LayerTabState] = {}
        self._controls_visible = True

        self.source_var = tk.StringVar(
            master=root, value=AverageProfileCloudOptions().source
        )
        self.layers_var = tk.StringVar(master=root, value=DEFAULT_LAYERS)
        self.db_path_var = tk.StringVar(master=root, value="")
        self.csv_dir_var = tk.StringVar(
            master=root, value=AverageProfileCloudOptions().csv_dir
        )
        self.min_coverage_var = tk.StringVar(
            master=root, value=str(AverageProfileCloudOptions().min_coverage)
        )
        self.iterations_var = tk.StringVar(
            master=root, value=str(AverageProfileCloudOptions().iterations)
        )
        self.exclude_regex_var = tk.StringVar(
            master=root, value=AverageProfileCloudOptions().exclude_apa_regex
        )
        self.bins_var = tk.StringVar(
            master=root, value=str(AverageProfileCloudOptions().bins)
        )
        self.moving_average_var = tk.StringVar(
            master=root, value=str(AverageProfileCloudOptions().moving_average_window)
        )
        self.no_scaling_var = tk.BooleanVar(
            master=root, value=AverageProfileCloudOptions().no_scaling
        )
        self.average_per_wire_var = tk.BooleanVar(
            master=root, value=AverageProfileCloudOptions().average_per_wire
        )
        self.split_by_location_var = tk.BooleanVar(
            master=root, value=AverageProfileCloudOptions().split_by_location
        )
        self.show_all_locations_var = tk.BooleanVar(
            master=root, value=AverageProfileCloudOptions().show_all_locations
        )
        self.split_by_side_var = tk.BooleanVar(
            master=root, value=AverageProfileCloudOptions().split_by_side
        )
        self.plot_mode_var = tk.StringVar(master=root, value=PLOT_MODE_WIRE_NUMBER)
        self.global_status_var = tk.StringVar(
            master=root, value="Waiting for first refresh."
        )

        self._build_layout()
        self._bind_auto_refresh()
        self._sync_split_by_location_state()
        self.schedule_refresh()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=8)
        container.grid(row=0, column=0, sticky="nsew")
        if hasattr(self.root, "columnconfigure"):
            self.root.columnconfigure(0, weight=1)
        if hasattr(self.root, "rowconfigure"):
            self.root.rowconfigure(0, weight=1)
        if hasattr(container, "columnconfigure"):
            container.columnconfigure(0, weight=1)
        if hasattr(container, "rowconfigure"):
            container.rowconfigure(2, weight=1)

        top_bar = ttk.Frame(container)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(1, weight=1)
        self.controls_toggle_button = ttk.Button(
            top_bar,
            text="Hide parameters",
            command=self.toggle_parameters_panel,
        )
        self.controls_toggle_button.grid(row=0, column=0, sticky="w")
        ttk.Label(top_bar, textvariable=self.global_status_var).grid(
            row=0, column=1, padx=(12, 0), sticky="e"
        )

        controls = ttk.LabelFrame(container, text="Parameters", padding=8)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        self.controls_panel = controls

        self._add_labeled_entry(
            controls, "Source", 0, 0, variable=self.source_var, kind="combo"
        )
        self._add_labeled_entry(controls, "Layers", 0, 2, variable=self.layers_var)
        self._add_labeled_entry(
            controls, "DB Path", 1, 0, variable=self.db_path_var, width=44
        )
        self._add_labeled_entry(
            controls, "CSV Dir", 1, 2, variable=self.csv_dir_var, width=44
        )
        self._add_labeled_entry(
            controls, "Min Coverage", 2, 0, variable=self.min_coverage_var, width=12
        )
        self._add_labeled_entry(
            controls, "Iterations", 2, 2, variable=self.iterations_var, width=12
        )
        self._add_labeled_entry(
            controls, "Exclude Regex", 3, 0, variable=self.exclude_regex_var, width=44
        )
        self._add_labeled_entry(
            controls, "Bins", 3, 2, variable=self.bins_var, width=12
        )
        self._add_labeled_entry(
            controls,
            "Moving Avg",
            4,
            0,
            variable=self.moving_average_var,
            width=12,
        )
        self._add_labeled_entry(
            controls,
            "Plot Mode",
            4,
            2,
            variable=self.plot_mode_var,
            kind="plot_mode_combo",
            width=24,
        )

        toggles = ttk.Frame(controls)
        toggles.grid(row=5, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(
            toggles,
            text="No scaling",
            variable=self.no_scaling_var,
            command=self.schedule_refresh,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Checkbutton(
            toggles,
            text="Average per wire",
            variable=self.average_per_wire_var,
            command=self.schedule_refresh,
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.split_by_location_button = ttk.Checkbutton(
            toggles,
            text="Split by location",
            variable=self.split_by_location_var,
            command=self.schedule_refresh,
        )
        self.split_by_location_button.grid(row=0, column=2, sticky="w")
        self.show_all_locations_button = ttk.Checkbutton(
            toggles,
            text="All locations on same plot",
            variable=self.show_all_locations_var,
            command=self.schedule_refresh,
        )
        self.show_all_locations_button.grid(row=0, column=3, sticky="w", padx=(8, 0))
        ttk.Checkbutton(
            toggles,
            text="Split by side (A/B)",
            variable=self.split_by_side_var,
            command=self.schedule_refresh,
        ).grid(row=0, column=4, sticky="w", padx=(8, 0))

        actions = ttk.Frame(controls)
        actions.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_now).grid(
            row=0, column=0, padx=(0, 6), sticky="w"
        )
        ttk.Button(actions, text="Export Current", command=self.export_current).grid(
            row=0, column=1, padx=(0, 6), sticky="w"
        )
        ttk.Button(actions, text="Export All", command=self.export_all).grid(
            row=0, column=2, sticky="w"
        )
        actions.columnconfigure(3, weight=1)

        self.notebook = ttk.Notebook(container)
        self.notebook.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

    def toggle_parameters_panel(self) -> None:
        self._set_controls_panel_visible(not self._controls_visible)

    def _set_controls_panel_visible(self, visible: bool) -> None:
        self._controls_visible = visible
        if visible:
            self.controls_panel.grid()
            self.controls_toggle_button.configure(text="Hide parameters")
        else:
            self.controls_panel.grid_remove()
            self.controls_toggle_button.configure(text="Show parameters")

    def _add_labeled_entry(
        self,
        parent: Any,
        label: str,
        row: int,
        column: int,
        *,
        variable: Any,
        width: int = 18,
        kind: str = "entry",
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=column, sticky="w", padx=(0, 6), pady=2
        )
        widget: Any
        if kind == "combo":
            widget = ttk.Combobox(
                parent,
                textvariable=variable,
                values=["legacy", "dunedb"],
                state="readonly",
                width=14,
            )
            widget.bind(
                "<<ComboboxSelected>>", lambda _event: self._on_source_changed()
            )
        elif kind == "plot_mode_combo":
            widget = ttk.Combobox(
                parent,
                textvariable=variable,
                values=list(PLOT_MODE_LABELS),
                state="readonly",
                width=width,
            )
            widget.bind("<<ComboboxSelected>>", lambda _event: self.schedule_refresh())
        else:
            widget = ttk.Entry(parent, textvariable=variable, width=width)
        widget.grid(row=row, column=column + 1, sticky="ew", padx=(0, 12), pady=2)

    def _bind_auto_refresh(self) -> None:
        for variable in [
            self.layers_var,
            self.db_path_var,
            self.csv_dir_var,
            self.min_coverage_var,
            self.iterations_var,
            self.exclude_regex_var,
            self.bins_var,
            self.moving_average_var,
            self.plot_mode_var,
            self.show_all_locations_var,
            self.split_by_side_var,
        ]:
            variable.trace_add("write", lambda *_args: self.schedule_refresh())
        self.split_by_location_var.trace_add(
            "write", lambda *_args: self._sync_split_by_location_state()
        )

    def _on_source_changed(self) -> None:
        self._sync_split_by_location_state()
        self.schedule_refresh()

    def _sync_split_by_location_state(self) -> None:
        enabled = self.source_var.get() == "dunedb"
        if not enabled:
            self.split_by_location_var.set(False)
        show_all_enabled = enabled and self.split_by_location_var.get()
        if not show_all_enabled:
            self.show_all_locations_var.set(False)
        try:
            self.split_by_location_button.state(
                ["!disabled"] if enabled else ["disabled"]
            )
            self.show_all_locations_button.state(
                ["!disabled"] if show_all_enabled else ["disabled"]
            )
        except Exception:
            pass

    def schedule_refresh(self) -> None:
        if self._pending_refresh_id is not None:
            try:
                self.root.after_cancel(self._pending_refresh_id)
            except Exception:
                pass
        self.global_status_var.set("Refresh scheduled...")
        self._pending_refresh_id = self.root.after(350, self.refresh_now)

    def refresh_now(self) -> None:
        self._pending_refresh_id = None
        try:
            options = self.collect_options()
        except Exception as exc:
            self._set_all_statuses(f"Invalid parameters: {exc}")
            return

        self._refresh_generation += 1
        generation = self._refresh_generation
        self.global_status_var.set("Refreshing plots...")
        self._ensure_layer_tabs(options.layers)
        self._set_all_statuses("Loading...")
        worker = threading.Thread(
            target=self._refresh_worker,
            args=(generation, options),
            daemon=True,
            name="average-profile-gui-refresh",
        )
        worker.start()

    def _refresh_worker(
        self, generation: int, options: AverageProfileCloudOptions
    ) -> None:
        try:
            results = compute_average_profile_results(options)
        except Exception as exc:
            message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.root.after(0, lambda: self._apply_refresh_error(generation, message))
            return
        self.root.after(
            0, lambda: self._apply_refresh_success(generation, options, results)
        )

    def _apply_refresh_error(self, generation: int, message: str) -> None:
        if generation != self._refresh_generation:
            return
        self.global_status_var.set("Refresh failed.")
        self._set_all_statuses(message)

    def _apply_refresh_success(
        self,
        generation: int,
        options: AverageProfileCloudOptions,
        results: dict[str, list[LayerAnalysisResult]],
    ) -> None:
        if generation != self._refresh_generation:
            return

        self._latest_options = options
        self._latest_results = results
        total_plots = 0
        plot_mode = self._selected_plot_mode()
        for layer, layer_results in results.items():
            self._render_layer_results(layer, layer_results, options)
            split_by_side = self._should_split_by_side_for_mode(
                options, plot_mode=plot_mode
            )
            if split_by_side:
                total_plots += sum(
                    sum(
                        1
                        for side in ("A", "B")
                        if not result.cloud.empty
                        and (result.cloud["side"] == side).any()
                    )
                    for result in layer_results
                )
            else:
                total_plots += sum(
                    1 for result in layer_results if not result.cloud.empty
                )
        self.global_status_var.set(f"Ready. Rendered {total_plots} plot(s).")

    def collect_options(self) -> AverageProfileCloudOptions:
        return normalize_options(
            {
                "source": self.source_var.get().strip(),
                "db_path": self.db_path_var.get().strip() or None,
                "layers": self.layers_var.get().strip(),
                "csv_dir": self.csv_dir_var.get().strip(),
                "min_coverage": self.min_coverage_var.get().strip(),
                "iterations": self.iterations_var.get().strip(),
                "exclude_apa_regex": self.exclude_regex_var.get(),
                "bins": self.bins_var.get().strip(),
                "moving_average_window": self.moving_average_var.get().strip(),
                "no_scaling": self.no_scaling_var.get(),
                "average_per_wire": self.average_per_wire_var.get(),
                "split_by_location": self.split_by_location_var.get(),
                "show_all_locations": self.show_all_locations_var.get(),
                "split_by_side": self.split_by_side_var.get(),
            }
        )

    def _ensure_layer_tabs(self, layers: tuple[str, ...]) -> None:
        existing = set(self._tab_state)
        desired = set(layers)

        for layer in list(existing - desired):
            state = self._tab_state.pop(layer)
            self.notebook.forget(state.frame)

        for layer in layers:
            if layer in self._tab_state:
                continue
            frame = ttk.Frame(self.notebook, padding=8)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)
            status_var = tk.StringVar(master=self.root, value="Waiting for data.")
            ttk.Label(frame, textvariable=status_var).grid(
                row=0, column=0, sticky="w", pady=(0, 6)
            )
            viewport = ttk.Frame(frame)
            viewport.grid(row=1, column=0, sticky="nsew")
            viewport.columnconfigure(0, weight=1)
            viewport.rowconfigure(0, weight=1)

            scroll_canvas = tk.Canvas(viewport, highlightthickness=0)
            scroll_canvas.grid(row=0, column=0, sticky="nsew")
            y_scrollbar = ttk.Scrollbar(
                viewport, orient="vertical", command=scroll_canvas.yview
            )
            y_scrollbar.grid(row=0, column=1, sticky="ns")
            x_scrollbar = ttk.Scrollbar(
                viewport, orient="horizontal", command=scroll_canvas.xview
            )
            x_scrollbar.grid(row=1, column=0, sticky="ew")
            scroll_canvas.configure(
                yscrollcommand=y_scrollbar.set,
                xscrollcommand=x_scrollbar.set,
            )

            content_frame = ttk.Frame(scroll_canvas)
            content_frame.columnconfigure(0, weight=1)
            window_id = scroll_canvas.create_window(
                (0, 0), window=content_frame, anchor="nw"
            )

            def _sync_scroll_region(
                _event: tk.Event, canvas: tk.Canvas = scroll_canvas
            ) -> None:
                canvas.configure(scrollregion=canvas.bbox("all"))

            def _sync_canvas_width(
                event: tk.Event,
                canvas: tk.Canvas = scroll_canvas,
                item: int = window_id,
            ) -> None:
                canvas.itemconfigure(item, width=max(event.width, 1))

            content_frame.bind("<Configure>", _sync_scroll_region)
            scroll_canvas.bind("<Configure>", _sync_canvas_width)
            self.notebook.add(frame, text=layer)
            self._tab_state[layer] = LayerTabState(
                frame=frame,
                status_var=status_var,
                scroll_canvas=scroll_canvas,
                content_frame=content_frame,
            )

    def _set_all_statuses(self, message: str) -> None:
        for state in self._tab_state.values():
            state.status_var.set(message)

    def _selected_plot_mode(self) -> str:
        plot_mode_var = getattr(self, "plot_mode_var", None)
        if plot_mode_var is None:
            return PLOT_MODE_WIRE_NUMBER
        return str(plot_mode_var.get()).strip() or PLOT_MODE_WIRE_NUMBER

    def _metadata_mode_placeholder(self, layer: str) -> str:
        label = PLOT_MODE_LABELS.get(
            self._selected_plot_mode(), self._selected_plot_mode()
        )
        return f"Layer {layer}: {label} is currently supported for U/V layers only."

    def _should_split_by_side_for_mode(
        self,
        options: AverageProfileCloudOptions,
        *,
        plot_mode: str,
    ) -> bool:
        return bool(
            options.split_by_side and plot_mode != PLOT_MODE_ENDPOINT_CATEGORIES
        )

    def _exploratory_output_path(
        self,
        output_path: Path,
        *,
        plot_mode: str,
        side_filter: str | None = None,
    ) -> Path:
        suffix = output_path.suffix or ".png"
        stem = (
            output_path.name[: -len(suffix)]
            if output_path.name.endswith(suffix)
            else output_path.stem
        )
        if side_filter is not None:
            stem = f"{stem}_side{side_filter}"
        mode_suffix = PLOT_MODE_SUFFIXES.get(plot_mode, "")
        return output_path.with_name(f"{stem}{mode_suffix}{suffix}")

    def _render_layer_results(
        self,
        layer: str,
        layer_results: list[LayerAnalysisResult],
        options: AverageProfileCloudOptions,
    ) -> None:
        plot_mode = self._selected_plot_mode()
        state = self._tab_state[layer]
        state.status_var.set(self._summarize_layer_results(layer_results))
        state.image_labels.clear()
        state.images.clear()
        state.location_labels.clear()
        for child in list(state.content_frame.winfo_children()):
            child.destroy()

        rendered_count = 0
        split_by_side = self._should_split_by_side_for_mode(
            options, plot_mode=plot_mode
        )
        for row, result in enumerate(layer_results):
            header_text = result.location_label or "All locations"
            header = ttk.Label(state.content_frame, text=header_text)
            header.grid(
                row=row * 2, column=0, sticky="w", pady=(0 if row == 0 else 8, 4)
            )
            state.location_labels.append(header)

            if not plot_mode_supported_for_layer(result.layer, plot_mode):
                placeholder = ttk.Label(
                    state.content_frame,
                    text=self._metadata_mode_placeholder(result.layer),
                )
                placeholder.grid(row=row * 2 + 1, column=0, sticky="w")
                continue

            if result.cloud.empty:
                placeholder = ttk.Label(state.content_frame, text=result.status_message)
                placeholder.grid(row=row * 2 + 1, column=0, sticky="w")
                continue

            if split_by_side:
                content = ttk.Frame(state.content_frame)
                content.grid(row=row * 2 + 1, column=0, sticky="nsew")
                content.columnconfigure(0, weight=1)

                inner_row = 0
                for side in ("A", "B"):
                    if not (result.cloud["side"] == side).any():
                        continue
                    ttk.Label(content, text=f"Side {side}").grid(
                        row=inner_row, column=0, sticky="w", pady=(0, 2)
                    )
                    inner_row += 1
                    figure = build_layer_figure(
                        result,
                        bins=options.bins,
                        average_per_wire=options.average_per_wire,
                        moving_average_window=options.moving_average_window,
                        side_filter=side,
                        plot_mode=plot_mode,
                    )
                    image = self._figure_to_photo_image(figure)
                    widget = ttk.Label(content, image=image)
                    cast(Any, widget).image = image
                    widget.grid(row=inner_row, column=0, sticky="nsew", pady=(0, 8))
                    inner_row += 1
                    state.images.append(image)
                    state.image_labels.append(widget)
                    rendered_count += 1
                if inner_row == 0:
                    ttk.Label(content, text=result.status_message).grid(
                        row=0, column=0, sticky="w"
                    )
            else:
                figure = build_layer_figure(
                    result,
                    bins=options.bins,
                    average_per_wire=options.average_per_wire,
                    moving_average_window=options.moving_average_window,
                    plot_mode=plot_mode,
                )
                image = self._figure_to_photo_image(figure)
                widget = ttk.Label(state.content_frame, image=image)
                cast(Any, widget).image = image
                widget.grid(row=row * 2 + 1, column=0, sticky="nsew")
                state.images.append(image)
                state.image_labels.append(widget)
                rendered_count += 1

        if rendered_count == 0 and not layer_results:
            ttk.Label(state.content_frame, text="No results.").grid(
                row=0, column=0, sticky="w"
            )

    def _figure_to_photo_image(self, figure: Any) -> Any:
        png_buffer = BytesIO()
        _save_figure_with_padding(figure, png_buffer, format="png", dpi=100)
        encoded = base64.b64encode(png_buffer.getvalue()).decode("ascii")
        return tk.PhotoImage(master=self.root, data=encoded)

    def _summarize_layer_results(self, layer_results: list[LayerAnalysisResult]) -> str:
        non_empty = [result for result in layer_results if not result.cloud.empty]
        if not non_empty:
            return layer_results[0].status_message if layer_results else "No data."
        total_points = sum(int(len(result.cloud)) for result in non_empty)
        return f"{len(non_empty)} view(s) ready, {total_points} plotted points."

    def _results_for_export(
        self,
    ) -> tuple[AverageProfileCloudOptions, dict[str, list[LayerAnalysisResult]]]:
        options = self.collect_options()
        if self._latest_options == options and self._latest_results is not None:
            return options, self._latest_results
        return options, compute_average_profile_results(options)

    def export_current(self) -> None:
        options, results = self._results_for_export()
        plot_mode = self._selected_plot_mode()
        current = self.notebook.select()
        for layer, state in self._tab_state.items():
            if str(state.frame) != str(current):
                continue
            for result in results.get(layer, []):
                export_layer_analysis(result, options)
                if plot_mode != PLOT_MODE_WIRE_NUMBER:
                    self._export_exploratory_pngs(result, options, plot_mode=plot_mode)
            self.global_status_var.set(f"Exported {layer}.")
            return
        self.global_status_var.set("No active tab to export.")

    def export_all(self) -> None:
        options, results = self._results_for_export()
        plot_mode = self._selected_plot_mode()
        export_count = 0
        for layer_results in results.values():
            for result in layer_results:
                export_layer_analysis(result, options)
                if plot_mode != PLOT_MODE_WIRE_NUMBER:
                    self._export_exploratory_pngs(result, options, plot_mode=plot_mode)
                export_count += 1
        self.global_status_var.set(f"Exported {export_count} result set(s).")

    def _export_exploratory_pngs(
        self,
        result: LayerAnalysisResult,
        options: AverageProfileCloudOptions,
        *,
        plot_mode: str,
    ) -> None:
        if result.cloud.empty or not plot_mode_supported_for_layer(
            result.layer, plot_mode
        ):
            return
        output_paths: list[tuple[str | None, Path]] = []
        split_by_side = self._should_split_by_side_for_mode(
            options, plot_mode=plot_mode
        )
        if split_by_side:
            for side in ("A", "B"):
                if not (result.cloud["side"] == side).any():
                    continue
                output_paths.append(
                    (
                        side,
                        self._exploratory_output_path(
                            result.output_path,
                            plot_mode=plot_mode,
                            side_filter=side,
                        ),
                    )
                )
        else:
            output_paths.append(
                (
                    None,
                    self._exploratory_output_path(
                        result.output_path, plot_mode=plot_mode
                    ),
                )
            )

        for side_filter, destination in output_paths:
            destination.parent.mkdir(parents=True, exist_ok=True)
            figure = build_layer_figure(
                result,
                bins=options.bins,
                average_per_wire=options.average_per_wire,
                moving_average_window=options.moving_average_window,
                side_filter=side_filter,
                plot_mode=plot_mode,
            )
            _save_figure_with_padding(figure, destination, format="png", dpi=300)


def run_average_profile_clouds_app(
    root: tk.Misc | None = None,
) -> AverageProfileExplorerApp:
    created_root = root is None
    root = root or tk.Tk()
    app = AverageProfileExplorerApp(root)
    if created_root:
        root.mainloop()
    return app


def main() -> None:
    run_average_profile_clouds_app()
