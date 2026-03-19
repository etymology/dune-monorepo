from __future__ import annotations

import argparse
import math
import threading
from dataclasses import replace
import tkinter as tk
from tkinter import scrolledtext
from tkinter import messagebox, ttk
from typing import Optional

from dune_winder.io.Devices.controllogix_plc import ControllogixPLC
from dune_winder.io.Devices.simulated_plc import SimulatedPLC
from dune_winder.machine.calibration.defaults import DefaultMachineCalibration
from dune_winder.machine.settings import Settings

from dune_winder.queued_motion import (
  DEFAULT_CONSTANT_VELOCITY_MODE,
  DEFAULT_CURVATURE_SPEED_SAFETY,
  DEFAULT_MAX_SEGMENT_FACTOR,
  DEFAULT_MIN_JERK_RATIO,
  DEFAULT_MIN_SEGMENT_LENGTH,
  DEFAULT_TEST_TERM_TYPE,
  DEFAULT_V_X_MAX,
  DEFAULT_V_Y_MAX,
  DEFAULT_WAYPOINT_ALLOW_STOPS,
  DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  DEFAULT_WAYPOINT_ORDER_MODE,
  LISSAJOUS_TESSELLATION_SEGMENTS,
  MotionQueueClient,
  MotionSegment,
  PLC_QUEUE_DEPTH,
  TESTABLE_TERM_TYPES,
  apply_merge_term_types,
  build_segments,
  cap_segments_speed_by_axis_velocity,
  load_motion_safety_limits,
  run_queue_case,
  tune_segments_for_constant_velocity,
  validate_segments_within_safety_limits,
)
from dune_winder.queued_motion.filleted_path import dynamic_min_radius
from dune_winder.queued_motion.segment_types import (
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
  arc_sweep_rad,
  circle_center_for_segment,
  segment_path_length,
)


DEFAULT_PLC_PATH = "192.168.140.13"
TAG_X_ACTUAL_POSITION = "X_axis.ActualPosition"
TAG_Y_ACTUAL_POSITION = "Y_axis.ActualPosition"
TAG_SAFETY_TRIPPED = "Safety_Tripped_S"
POSITION_POLL_S = 0.20
POSITION_ERROR_RETRY_S = 1.00
DEFAULT_COMMAND_SPEED = 1000.0


def _open_plc_connection(path: str):
  if str(path).strip().upper() == "SIM":
    return SimulatedPLC("SIM")
  return ControllogixPLC(path)


def _close_plc_connection(plc) -> None:
  if getattr(plc, "_plcDriver", None) is not None:
    try:
      plc._plcDriver.close()
    except Exception:
      pass


def _effective_planner_start_xy(
  waypoints: list[tuple[float, float]],
  start_xy: Optional[tuple[float, float]],
) -> Optional[tuple[float, float]]:
  if start_xy is not None:
    return (float(start_xy[0]), float(start_xy[1]))
  if not waypoints:
    return None
  first_x, first_y = waypoints[0]
  return (float(first_x), float(first_y))


def _load_axis_velocity_limits(calibration_path: Optional[str]) -> tuple[float, float]:
  if calibration_path:
    path = calibration_path.strip()
  else:
    path = ""

  if path:
    from pathlib import Path

    calibration_file = Path(path)
    if calibration_file.is_dir():
      output_path = str(calibration_file)
      output_name = Settings.MACHINE_CALIBRATION_FILE
    else:
      output_path = str(calibration_file.parent)
      output_name = calibration_file.name
  else:
    output_path = Settings.MACHINE_CALIBRATION_PATH
    output_name = Settings.MACHINE_CALIBRATION_FILE

  calibration = DefaultMachineCalibration(output_path, output_name)
  v_x_max = calibration.get("v_x_max")
  v_y_max = calibration.get("v_y_max")
  return (
    float(v_x_max if v_x_max is not None else DEFAULT_V_X_MAX),
    float(v_y_max if v_y_max is not None else DEFAULT_V_Y_MAX),
  )


def _planned_speed_summary_text(
  requested_speed: float,
  segments: list[MotionSegment],
) -> str:
  if not segments:
    return f"requested_speed={float(requested_speed):.1f}"

  speeds = [float(seg.speed) for seg in segments]
  min_speed = min(speeds)
  max_speed = max(speeds)
  requested_text = f"requested_speed={float(requested_speed):.1f}"
  if math.isclose(min_speed, max_speed, rel_tol=0.0, abs_tol=1e-9):
    return f"{requested_text} planned_speed={max_speed:.1f}"
  return f"{requested_text} planned_speed[min/max]={min_speed:.1f}/{max_speed:.1f}"


def _extract_plc_read_value(read_result, tag: str):
  if read_result is None:
    raise RuntimeError(f"{tag}: no response")

  if isinstance(read_result, list):
    if not read_result:
      raise RuntimeError(f"{tag}: empty response")
    first = read_result[0]
    if hasattr(first, "error"):
      if first.error:
        raise RuntimeError(f"{tag}: {first.error}")
      return first.value
    if isinstance(first, (list, tuple)):
      if len(first) >= 2:
        return first[1]
      if len(first) == 1:
        return first[0]
    return first

  if hasattr(read_result, "error"):
    if read_result.error:
      raise RuntimeError(f"{tag}: {read_result.error}")
    return read_result.value

  return read_result


def _read_plc_tag_value(plc, tag: str):
  return _extract_plc_read_value(plc.read([tag]), tag)


def _coerce_to_bool(value) -> bool:
  if isinstance(value, str):
    normalized = value.strip().lower()
    if normalized in ("1", "true", "t", "yes", "y", "on"):
      return True
    if normalized in ("0", "false", "f", "no", "n", "off", ""):
      return False
  return bool(value)


class WaypointPlannerApp(tk.Tk):
  def __init__(self, plc_path: str, machine_calibration: str) -> None:
    super().__init__()
    self.title("Motion Queue Waypoint Planner")
    self.geometry("1300x780")
    self.minsize(1120, 700)

    self.safety_limits = load_motion_safety_limits(machine_calibration or None)
    self.v_x_max, self.v_y_max = _load_axis_velocity_limits(machine_calibration or None)
    self.machine_calibration = machine_calibration
    self._plc_path = plc_path.strip()
    self.waypoints: list[tuple[float, float]] = []
    self.segments: list[MotionSegment] = []
    self.start_xy: Optional[tuple[float, float]] = None
    self.live_position_xy: Optional[tuple[float, float]] = None
    self._run_thread: Optional[threading.Thread] = None
    self._position_tracker_stop = threading.Event()
    self._position_tracker_thread: Optional[threading.Thread] = None

    self.plc_path_var = tk.StringVar(value=plc_path)
    self.plc_path_var.trace_add("write", self._on_plc_path_var_changed)
    self.start_x_var = tk.StringVar(value="")
    self.start_y_var = tk.StringVar(value="")
    self.order_mode_var = tk.StringVar(value=DEFAULT_WAYPOINT_ORDER_MODE)
    self.min_arc_radius_var = tk.StringVar(value=f"{DEFAULT_WAYPOINT_MIN_ARC_RADIUS:.1f}")
    self.allow_stops_var = tk.BooleanVar(value=DEFAULT_WAYPOINT_ALLOW_STOPS)
    self.speed_var = tk.StringVar(value=f"{DEFAULT_COMMAND_SPEED:.1f}")
    self.term_type_var = tk.StringVar(value=str(DEFAULT_TEST_TERM_TYPE))
    self.min_segment_length_var = tk.StringVar(value=f"{DEFAULT_MIN_SEGMENT_LENGTH:.1f}")
    self.constant_velocity_var = tk.BooleanVar(value=DEFAULT_CONSTANT_VELOCITY_MODE)
    self.status_var = tk.StringVar(
      value=(
        "Left click to add waypoints. Right click to remove last waypoint. "
        "Press Replan, then Execute Path."
      )
    )
    self.stats_var = tk.StringVar(value="No plan yet.")
    self.pointer_var = tk.StringVar(value="")
    self.live_position_var = tk.StringVar(
      value="Live position: unavailable (set PLC path to start tracking)."
    )
    self.safety_state_var = tk.StringVar(
      value="Safety state: unavailable (set PLC path to start tracking)."
    )

    self._build_layout()
    self._set_segment_details("No planned segments.")
    self._refresh_canvas()
    self.protocol("WM_DELETE_WINDOW", self._on_close)
    self._start_position_tracker()

  def _build_layout(self) -> None:
    self.columnconfigure(1, weight=1)
    self.rowconfigure(0, weight=1)

    controls = ttk.Frame(self, padding=10)
    controls.grid(row=0, column=0, sticky="ns")
    controls.columnconfigure(1, weight=1)

    plot = ttk.Frame(self, padding=(0, 10, 10, 10))
    plot.grid(row=0, column=1, sticky="nsew")
    plot.columnconfigure(0, weight=1)
    plot.rowconfigure(0, weight=3)
    plot.rowconfigure(1, weight=2)

    row = 0
    ttk.Label(controls, text="Planner Settings", font=("Segoe UI", 11, "bold")).grid(
      row=row, column=0, columnspan=2, sticky="w"
    )
    row += 1

    row = self._entry_row(controls, row, "PLC path", self.plc_path_var)
    row = self._entry_row(controls, row, "Start X (optional)", self.start_x_var)
    row = self._entry_row(controls, row, "Start Y (optional)", self.start_y_var)

    ttk.Label(controls, text="Waypoint order").grid(row=row, column=0, sticky="w", pady=(8, 0))
    order_combo = ttk.Combobox(
      controls,
      state="readonly",
      textvariable=self.order_mode_var,
      values=("input", "shortest"),
      width=16,
    )
    order_combo.grid(row=row, column=1, sticky="ew", pady=(8, 0))
    order_combo.bind("<<ComboboxSelected>>", lambda _e: self._replan())
    row += 1

    ttk.Label(controls, text="Term type").grid(row=row, column=0, sticky="w", pady=(8, 0))
    term_combo = ttk.Combobox(
      controls,
      state="readonly",
      textvariable=self.term_type_var,
      values=[str(v) for v in TESTABLE_TERM_TYPES],
      width=16,
    )
    term_combo.grid(row=row, column=1, sticky="ew", pady=(8, 0))
    term_combo.bind("<<ComboboxSelected>>", lambda _e: self._replan())
    row += 1

    row = self._entry_row(controls, row, "Min arc radius", self.min_arc_radius_var)
    row = self._entry_row(controls, row, "Speed", self.speed_var)
    row = self._entry_row(controls, row, "Min segment length", self.min_segment_length_var)

    cv_check = ttk.Checkbutton(
      controls,
      text="Constant velocity tuning",
      variable=self.constant_velocity_var,
      command=self._replan,
    )
    cv_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    row += 1

    stops_check = ttk.Checkbutton(
      controls,
      text="Allow stop/start fallback",
      variable=self.allow_stops_var,
      command=self._replan,
    )
    stops_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
    row += 1

    ttk.Label(
      controls,
      text=(
        "Machine bounds: "
        f"X[{self.safety_limits.limit_left:.1f}, {self.safety_limits.limit_right:.1f}] "
        f"Y[{self.safety_limits.limit_bottom:.1f}, {self.safety_limits.limit_top:.1f}]\n"
        f"Intrinsic caps: Vx={self.v_x_max:.1f}, Vy={self.v_y_max:.1f}, "
        f"QueueDepth={PLC_QUEUE_DEPTH}"
      ),
      wraplength=320,
      justify="left",
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    row += 1

    button_bar_1 = ttk.Frame(controls)
    button_bar_1.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    button_bar_1.columnconfigure(0, weight=1)
    button_bar_1.columnconfigure(1, weight=1)
    button_bar_1.columnconfigure(2, weight=1)
    ttk.Button(button_bar_1, text="Replan", command=self._replan).grid(
      row=0, column=0, sticky="ew", padx=(0, 4)
    )
    ttk.Button(button_bar_1, text="Undo Last", command=self._undo_last_waypoint).grid(
      row=0, column=1, sticky="ew", padx=4
    )
    ttk.Button(button_bar_1, text="Clear", command=self._clear_waypoints).grid(
      row=0, column=2, sticky="ew", padx=(4, 0)
    )
    row += 1

    self.execute_button = ttk.Button(
      controls,
      text="Execute Path",
      command=self._execute_path,
      state="disabled",
    )
    self.execute_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    row += 1

    ttk.Label(controls, textvariable=self.stats_var, wraplength=320, justify="left").grid(
      row=row, column=0, columnspan=2, sticky="w", pady=(10, 0)
    )
    row += 1
    ttk.Label(controls, textvariable=self.status_var, wraplength=320, justify="left").grid(
      row=row, column=0, columnspan=2, sticky="w", pady=(6, 0)
    )
    row += 1
    ttk.Label(controls, textvariable=self.pointer_var).grid(
      row=row, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )
    row += 1
    ttk.Label(
      controls,
      textvariable=self.live_position_var,
      wraplength=320,
      justify="left",
    ).grid(
      row=row, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )
    row += 1
    tk.Label(
      controls,
      textvariable=self.safety_state_var,
      wraplength=320,
      justify="left",
      fg="#b91c1c",
      bg=self.cget("bg"),
      anchor="w",
    ).grid(
      row=row, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )

    self.canvas = tk.Canvas(
      plot,
      bg="#0b1220",
      highlightthickness=0,
      cursor="crosshair",
    )
    self.canvas.grid(row=0, column=0, sticky="nsew")
    self.canvas.bind("<Configure>", lambda _e: self._refresh_canvas())
    self.canvas.bind("<Button-1>", self._on_left_click)
    self.canvas.bind("<Button-3>", self._on_right_click)
    self.canvas.bind("<Motion>", self._on_canvas_motion)
    self.canvas.focus_set()

    details_frame = ttk.Frame(plot, padding=(0, 10, 0, 0))
    details_frame.grid(row=1, column=0, sticky="nsew")
    details_frame.columnconfigure(0, weight=1)
    details_frame.rowconfigure(1, weight=1)

    ttk.Label(
      details_frame,
      text="Queued Segment Details",
      font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))

    self.segment_details_text = scrolledtext.ScrolledText(
      details_frame,
      height=14,
      wrap=tk.NONE,
      font=("Consolas", 9),
      state="disabled",
    )
    self.segment_details_text.grid(row=1, column=0, sticky="nsew")

  def _entry_row(
    self,
    frame: ttk.Frame,
    row: int,
    label: str,
    variable: tk.StringVar,
  ) -> int:
    ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
    entry = ttk.Entry(frame, textvariable=variable)
    entry.grid(row=row, column=1, sticky="ew", pady=(6, 0))
    entry.bind("<Return>", lambda _e: self._replan())
    return row + 1

  def _set_status(self, message: str, is_error: bool = False) -> None:
    prefix = "Error" if is_error else "Status"
    self.status_var.set(f"{prefix}: {message}")

  def _set_segment_details(self, text: str) -> None:
    self.segment_details_text.configure(state="normal")
    self.segment_details_text.delete("1.0", tk.END)
    self.segment_details_text.insert("1.0", text)
    self.segment_details_text.configure(state="disabled")

  def _segment_details_report(
    self,
    segments: list[MotionSegment],
    start_xy: Optional[tuple[float, float]],
    requested_min_arc_radius: float,
  ) -> str:
    if not segments:
      return "No planned segments."

    if start_xy is None:
      cursor_x = float(segments[0].x)
      cursor_y = float(segments[0].y)
      start_label = "unknown"
    else:
      cursor_x = float(start_xy[0])
      cursor_y = float(start_xy[1])
      start_label = f"({cursor_x:.2f}, {cursor_y:.2f})"

    lines = [
      f"start_xy={start_label}",
      (
        "idx seq kind            start_xy               end_xy                 "
        "len     speed   accel   decel   jerk_a  jerk_d  r_min_dyn  r_arc"
      ),
    ]

    for idx, seg in enumerate(segments, start=1):
      start_seg = MotionSegment(seq=seg.seq - 1, x=cursor_x, y=cursor_y)
      path_len = segment_path_length(start_seg, seg)
      accel_limit = min(float(seg.accel), float(seg.decel))
      jerk_limit = min(float(seg.jerk_accel), float(seg.jerk_decel))
      dynamic_radius = dynamic_min_radius(
        speed=float(seg.speed),
        base_min_radius=requested_min_arc_radius,
        accel_limit=accel_limit,
        jerk_limit=jerk_limit,
      )

      arc_radius_text = "-"
      if seg.seg_type == SEG_TYPE_CIRCLE:
        center = circle_center_for_segment(start_seg, seg)
        if center is not None:
          arc_radius = math.hypot(cursor_x - center[0], cursor_y - center[1])
          arc_radius_text = f"{arc_radius:8.2f}"

      kind = "circle" if seg.seg_type == SEG_TYPE_CIRCLE else "line"
      lines.append(
        f"{idx:>3} {seg.seq:>3} {kind:<15}"
        f"({cursor_x:>8.2f},{cursor_y:>8.2f}) "
        f"({float(seg.x):>8.2f},{float(seg.y):>8.2f}) "
        f"{path_len:>7.2f} {float(seg.speed):>7.2f} {float(seg.accel):>7.2f} "
        f"{float(seg.decel):>7.2f} {float(seg.jerk_accel):>7.2f} "
        f"{float(seg.jerk_decel):>7.2f} {dynamic_radius:>10.2f} "
        f"{arc_radius_text}"
      )
      cursor_x = float(seg.x)
      cursor_y = float(seg.y)

    lines.append("")
    lines.append(
      "r_min_dyn is the conservative minimum radius from requested Min arc radius, "
      "v^2/a, and sqrt(v^3/j) using min(accel,decel) and min(jerk_accel,jerk_decel)."
    )
    return "\n".join(lines)

  def _on_plc_path_var_changed(self, *_args) -> None:
    self._plc_path = self.plc_path_var.get().strip()

  def _parse_float(self, text: str, label: str) -> float:
    value = text.strip()
    if not value:
      raise ValueError(f"{label} is required.")
    try:
      return float(value)
    except ValueError as exc:
      raise ValueError(f"{label} must be numeric.") from exc

  def _parse_int(self, text: str, label: str) -> int:
    value = text.strip()
    if not value:
      raise ValueError(f"{label} is required.")
    try:
      return int(value)
    except ValueError as exc:
      raise ValueError(f"{label} must be an integer.") from exc

  def _parse_optional_float(self, text: str, label: str) -> Optional[float]:
    value = text.strip()
    if not value:
      return None
    try:
      return float(value)
    except ValueError as exc:
      raise ValueError(f"{label} must be numeric.") from exc

  def _parse_start_xy(self) -> Optional[tuple[float, float]]:
    sx = self._parse_optional_float(self.start_x_var.get(), "Start X")
    sy = self._parse_optional_float(self.start_y_var.get(), "Start Y")
    if (sx is None) != (sy is None):
      raise ValueError("Specify both Start X and Start Y, or leave both empty.")
    if sx is None:
      return None
    return (sx, sy)

  def _plot_transform(self) -> tuple[float, float, float, float, float]:
    width = max(2, self.canvas.winfo_width())
    height = max(2, self.canvas.winfo_height())
    margin = 45.0

    limits = self.safety_limits
    span_x = max(1e-9, limits.limit_right - limits.limit_left)
    span_y = max(1e-9, limits.limit_top - limits.limit_bottom)

    plot_w = max(2.0, width - 2.0 * margin)
    plot_h = max(2.0, height - 2.0 * margin)
    scale = min(plot_w / span_x, plot_h / span_y)
    used_w = span_x * scale
    used_h = span_y * scale
    x_off = margin + (plot_w - used_w) * 0.5
    y_off = margin + (plot_h - used_h) * 0.5
    return x_off, y_off, used_w, used_h, scale

  def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
    x_off, y_off, used_w, used_h, scale = self._plot_transform()
    limits = self.safety_limits
    px = x_off + (x - limits.limit_left) * scale
    py = y_off + used_h - (y - limits.limit_bottom) * scale
    return (px, py)

  def _canvas_to_world(self, px: float, py: float) -> Optional[tuple[float, float]]:
    x_off, y_off, used_w, used_h, scale = self._plot_transform()
    if px < x_off or px > x_off + used_w or py < y_off or py > y_off + used_h:
      return None

    limits = self.safety_limits
    x = limits.limit_left + (px - x_off) / scale
    y = limits.limit_bottom + (used_h - (py - y_off)) / scale
    return (x, y)

  def _on_canvas_motion(self, event) -> None:
    world = self._canvas_to_world(float(event.x), float(event.y))
    if world is None:
      self.pointer_var.set("")
      return
    self.pointer_var.set(f"Pointer: X={world[0]:.1f}, Y={world[1]:.1f}")

  def _on_left_click(self, event) -> None:
    point = self._canvas_to_world(float(event.x), float(event.y))
    if point is None:
      return
    self.waypoints.append(point)
    self._replan()

  def _on_right_click(self, _event) -> None:
    self._undo_last_waypoint()

  def _undo_last_waypoint(self) -> None:
    if not self.waypoints:
      return
    self.waypoints.pop()
    self._replan()

  def _clear_waypoints(self) -> None:
    self.waypoints.clear()
    self.segments = []
    self.start_xy = None
    self.stats_var.set("No plan yet.")
    self._set_segment_details("No planned segments.")
    self._set_status("Waypoints cleared.")
    self.execute_button.configure(state="disabled")
    self._refresh_canvas()

  def _segment_polyline_points(
    self,
    segments: list[MotionSegment],
    start_xy: Optional[tuple[float, float]],
  ) -> list[tuple[float, float]]:
    if not segments:
      return []

    points: list[tuple[float, float]] = []
    if start_xy is None:
      prev_x = float(segments[0].x)
      prev_y = float(segments[0].y)
      points.append((prev_x, prev_y))
    else:
      prev_x = float(start_xy[0])
      prev_y = float(start_xy[1])
      points.append((prev_x, prev_y))

    for seg in segments:
      if seg.seg_type == SEG_TYPE_CIRCLE:
        start_seg = MotionSegment(seq=seg.seq - 1, x=prev_x, y=prev_y)
        center = circle_center_for_segment(start_seg, seg)
        if center is not None:
          cx, cy = center
          r0 = math.hypot(prev_x - cx, prev_y - cy)
          r1 = math.hypot(seg.x - cx, seg.y - cy)
          if r0 > 1e-9 and r1 > 1e-9:
            a0 = math.atan2(prev_y - cy, prev_x - cx)
            a1 = math.atan2(seg.y - cy, seg.x - cx)
            sweep = arc_sweep_rad(a0, a1, seg.direction)
            if sweep is not None:
              radius = 0.5 * (r0 + r1)
              steps = max(4, int(math.ceil(abs(sweep) / math.radians(4.0))))
              for i in range(1, steps + 1):
                t = i / steps
                angle = a0 + sweep * t
                points.append(
                  (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
                )
              prev_x = float(seg.x)
              prev_y = float(seg.y)
              continue

      points.append((float(seg.x), float(seg.y)))
      prev_x = float(seg.x)
      prev_y = float(seg.y)

    return points

  def _path_length(
    self,
    segments: list[MotionSegment],
    start_xy: Optional[tuple[float, float]],
  ) -> float:
    if not segments:
      return 0.0

    if start_xy is None:
      prev = MotionSegment(seq=segments[0].seq - 1, x=segments[0].x, y=segments[0].y)
    else:
      prev = MotionSegment(seq=segments[0].seq - 1, x=start_xy[0], y=start_xy[1])

    total = 0.0
    for seg in segments:
      total += segment_path_length(prev, seg)
      prev = seg
    return total

  def _draw_machine_overlay(self) -> None:
    limits = self.safety_limits
    x0, y0 = self._world_to_canvas(limits.limit_left, limits.limit_bottom)
    x1, y1 = self._world_to_canvas(limits.limit_right, limits.limit_top)
    self.canvas.create_rectangle(x0, y1, x1, y0, outline="#334155", width=2)

    transfer_x_max = limits.transfer_left - limits.transfer_left_margin
    if transfer_x_max > limits.limit_left and limits.limit_top > limits.transfer_y_threshold:
      tx0, ty0 = self._world_to_canvas(limits.limit_left, limits.transfer_y_threshold)
      tx1, ty1 = self._world_to_canvas(transfer_x_max, limits.limit_top)
      self.canvas.create_rectangle(
        tx0,
        ty1,
        tx1,
        ty0,
        outline="",
        fill="#302132",
        stipple="gray25",
      )

    px0 = limits.headward_pivot_x - limits.headward_pivot_x_tolerance
    px1 = limits.headward_pivot_x + limits.headward_pivot_x_tolerance
    py0 = limits.headward_pivot_y - limits.headward_pivot_y_tolerance
    py1 = limits.headward_pivot_y + limits.headward_pivot_y_tolerance
    kx0, ky0 = self._world_to_canvas(px0, py0)
    kx1, ky1 = self._world_to_canvas(px1, py1)
    self.canvas.create_rectangle(
      kx0,
      ky1,
      kx1,
      ky0,
      outline="#ef4444",
      width=1,
      fill="#3b1d1d",
      stipple="gray25",
    )

  def _draw_grid(self) -> None:
    limits = self.safety_limits
    x_step = 1000.0
    y_step = 500.0

    x_tick = math.ceil(limits.limit_left / x_step) * x_step
    while x_tick <= limits.limit_right + 1e-6:
      px0, py0 = self._world_to_canvas(x_tick, limits.limit_bottom)
      px1, py1 = self._world_to_canvas(x_tick, limits.limit_top)
      self.canvas.create_line(px0, py0, px1, py1, fill="#1f2937")
      self.canvas.create_text(px0 + 3, py0 - 10, text=f"{x_tick:.0f}", fill="#94a3b8", anchor="w")
      x_tick += x_step

    y_tick = math.ceil(limits.limit_bottom / y_step) * y_step
    while y_tick <= limits.limit_top + 1e-6:
      px0, py0 = self._world_to_canvas(limits.limit_left, y_tick)
      px1, py1 = self._world_to_canvas(limits.limit_right, y_tick)
      self.canvas.create_line(px0, py0, px1, py1, fill="#1f2937")
      self.canvas.create_text(px0 + 3, py0 - 3, text=f"{y_tick:.0f}", fill="#94a3b8", anchor="w")
      y_tick += y_step

  def _refresh_canvas(self) -> None:
    self.canvas.delete("all")
    self._draw_grid()
    self._draw_machine_overlay()

    if self.segments:
      poly = self._segment_polyline_points(self.segments, self.start_xy)
      if len(poly) >= 2:
        flat: list[float] = []
        for x, y in poly:
          px, py = self._world_to_canvas(x, y)
          flat.extend([px, py])
        self.canvas.create_line(
          *flat,
          fill="#f59e0b",
          width=2.4,
          capstyle=tk.ROUND,
          joinstyle=tk.ROUND,
        )

        spx, spy = self._world_to_canvas(poly[0][0], poly[0][1])
        epx, epy = self._world_to_canvas(poly[-1][0], poly[-1][1])
        self.canvas.create_oval(spx - 6, spy - 6, spx + 6, spy + 6, fill="#22c55e", outline="")
        self.canvas.create_oval(epx - 6, epy - 6, epx + 6, epy + 6, fill="#ef4444", outline="")

    for i, (x, y) in enumerate(self.waypoints, start=1):
      px, py = self._world_to_canvas(x, y)
      color = "#60a5fa"
      if i == 1:
        color = "#22c55e"
      elif i == len(self.waypoints):
        color = "#ef4444"
      self.canvas.create_oval(px - 5, py - 5, px + 5, py + 5, fill=color, outline="#0f172a")
      self.canvas.create_text(px + 9, py - 10, text=str(i), fill="#dbeafe", anchor="w")

    if self.live_position_xy is not None:
      x, y = self.live_position_xy
      limits = self.safety_limits
      if (
        limits.limit_left <= x <= limits.limit_right
        and limits.limit_bottom <= y <= limits.limit_top
      ):
        px, py = self._world_to_canvas(x, y)
        self.canvas.create_line(px - 9, py, px + 9, py, fill="#22d3ee", width=2)
        self.canvas.create_line(px, py - 9, px, py + 9, fill="#22d3ee", width=2)
        self.canvas.create_oval(
          px - 4,
          py - 4,
          px + 4,
          py + 4,
          fill="#22d3ee",
          outline="#164e63",
          width=1,
        )
        self.canvas.create_text(
          px + 10,
          py + 10,
          text=f"Live ({x:.1f}, {y:.1f})",
          fill="#67e8f9",
          anchor="nw",
        )

  def _replan(self) -> None:
    if len(self.waypoints) < 2:
      self.segments = []
      self.start_xy = None
      self.stats_var.set("Add at least 2 waypoints to build a plan.")
      self._set_segment_details("No planned segments.")
      self._set_status("Waiting for more waypoints.")
      self.execute_button.configure(state="disabled")
      self._refresh_canvas()
      return

    try:
      start_xy = self._parse_start_xy()
      effective_start_xy = _effective_planner_start_xy(self.waypoints, start_xy)
      term_type = self._parse_int(self.term_type_var.get(), "Term type")
      if term_type not in TESTABLE_TERM_TYPES:
        raise ValueError("Term type must be one of 0..6.")

      min_arc_radius = self._parse_float(self.min_arc_radius_var.get(), "Min arc radius")
      speed = self._parse_float(self.speed_var.get(), "Speed")
      if speed <= 0.0:
        raise ValueError("Speed must be > 0.")
      min_segment_length = self._parse_float(
        self.min_segment_length_var.get(), "Min segment length"
      )
      if min_segment_length < 0.0:
        raise ValueError("Min segment length must be >= 0.")

      segments = build_segments(
        pattern="waypoint_path",
        start_seq=100,
        term_type=term_type,
        lissajous_segments_count=LISSAJOUS_TESSELLATION_SEGMENTS,
        min_segment_length=min_segment_length,
        waypoint_points=list(self.waypoints),
        waypoint_min_arc_radius=min_arc_radius,
        waypoint_order_mode=self.order_mode_var.get(),
        waypoint_start_xy=start_xy,
        waypoint_bounds=(
          self.safety_limits.limit_left,
          self.safety_limits.limit_right,
          self.safety_limits.limit_bottom,
          self.safety_limits.limit_top,
        ),
        waypoint_allow_stops=self.allow_stops_var.get(),
      )
      segments = [replace(seg, speed=speed) for seg in segments]
      effective_min_segment_length = min_segment_length

      if self.constant_velocity_var.get():
        segments, effective_min_segment_length, _, _ = tune_segments_for_constant_velocity(
          segments=segments,
          requested_min_segment_length=min_segment_length,
          curvature_speed_safety=DEFAULT_CURVATURE_SPEED_SAFETY,
          min_jerk_ratio=DEFAULT_MIN_JERK_RATIO,
          max_segment_factor=DEFAULT_MAX_SEGMENT_FACTOR,
        )

      segments = cap_segments_speed_by_axis_velocity(
        segments=segments,
        v_x_max=self.v_x_max,
        v_y_max=self.v_y_max,
        start_xy=effective_start_xy,
      )
      segments = apply_merge_term_types(
        segments=segments,
        start_xy=effective_start_xy,
        tangential_term_type=term_type,
        non_tangential_term_type=1 if self.allow_stops_var.get() else 0,
        final_term_type=None,
      )
      validate_segments_within_safety_limits(
        segments,
        self.safety_limits,
        start_xy=effective_start_xy,
      )
    except Exception as exc:
      self.segments = []
      self.start_xy = None
      self.stats_var.set("Plan is invalid.")
      self._set_segment_details("No planned segments.")
      self._set_status(str(exc), is_error=True)
      self.execute_button.configure(state="disabled")
      self._refresh_canvas()
      return

    line_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_LINE)
    circle_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE)
    total_length = self._path_length(segments, effective_start_xy)
    self.stats_var.set(
      "Plan ready: "
      f"segments={len(segments)} "
      f"line/circle={line_count}/{circle_count} "
      f"path_length={total_length:.1f} "
      f"{_planned_speed_summary_text(speed, segments)} "
      f"effective_min_segment_length={effective_min_segment_length:.2f}"
    )

    self.segments = segments
    self.start_xy = effective_start_xy
    self._set_segment_details(
      self._segment_details_report(
        segments=segments,
        start_xy=effective_start_xy,
        requested_min_arc_radius=min_arc_radius,
      )
    )
    self.execute_button.configure(state="normal")
    self._set_status("Plan valid and within motion safety limits.")
    self._refresh_canvas()

  def _execute_path(self) -> None:
    if not self.segments:
      self._set_status("No plan to execute.", is_error=True)
      return
    if self._run_thread is not None and self._run_thread.is_alive():
      self._set_status("Execution already in progress.", is_error=True)
      return

    plc_path = self.plc_path_var.get().strip()
    if not plc_path:
      self._set_status("PLC path is required.", is_error=True)
      return

    if not messagebox.askyesno(
      "Execute path",
      (
        f"Queue and execute {len(self.segments)} segment(s) on PLC '{plc_path}' "
        f"(queue depth {PLC_QUEUE_DEPTH})?\n\n"
        "Use this only when the machine is ready."
      ),
      parent=self,
    ):
      return

    segments_to_run = list(self.segments)
    self.execute_button.configure(state="disabled")
    self._set_status("Executing planned path...")

    def run() -> None:
      try:
        with MotionQueueClient(plc_path) as motion:
          run_queue_case(motion, segments_to_run, queue_depth=PLC_QUEUE_DEPTH)
      except Exception as exc:
        error_message = str(exc)
        self.after(
          0,
          lambda msg=error_message: self._finish_execution(False, msg),
        )
        return
      self.after(
        0,
        lambda: self._finish_execution(
          True,
          f"Execution finished successfully ({len(segments_to_run)} segments).",
        ),
      )

    self._run_thread = threading.Thread(target=run, daemon=True)
    self._run_thread.start()

  def _finish_execution(self, success: bool, message: str) -> None:
    self.execute_button.configure(state="normal" if self.segments else "disabled")
    self._set_status(message, is_error=not success)

  def _start_position_tracker(self) -> None:
    self._position_tracker_thread = threading.Thread(
      target=self._position_tracker_loop,
      daemon=True,
    )
    self._position_tracker_thread.start()

  def _position_tracker_loop(self) -> None:
    plc = None
    connected_path = ""

    try:
      while not self._position_tracker_stop.is_set():
        current_path = self._plc_path
        if not current_path:
          if plc is not None:
            _close_plc_connection(plc)
            plc = None
            connected_path = ""
          self.after(
            0,
            lambda: self._set_live_position_unavailable(
              "Live position: unavailable (set PLC path to start tracking)."
            ),
          )
          self._position_tracker_stop.wait(POSITION_ERROR_RETRY_S)
          continue

        try:
          if plc is None or connected_path != current_path:
            if plc is not None:
              _close_plc_connection(plc)
            plc = _open_plc_connection(current_path)
            connected_path = current_path

          x_val = float(_read_plc_tag_value(plc, TAG_X_ACTUAL_POSITION))
          y_val = float(_read_plc_tag_value(plc, TAG_Y_ACTUAL_POSITION))
          safety_tripped = _coerce_to_bool(_read_plc_tag_value(plc, TAG_SAFETY_TRIPPED))
          self.after(
            0,
            lambda x=x_val, y=y_val, tripped=safety_tripped: self._update_live_status(
              x,
              y,
              tripped,
            ),
          )
          self._position_tracker_stop.wait(POSITION_POLL_S)
        except Exception as exc:
          if plc is not None:
            _close_plc_connection(plc)
          plc = None
          connected_path = ""
          self.after(
            0,
            lambda msg=str(exc): self._set_live_position_unavailable(
              f"Live position unavailable: {msg}"
            ),
          )
          self._position_tracker_stop.wait(POSITION_ERROR_RETRY_S)
    finally:
      if plc is not None:
        _close_plc_connection(plc)

  def _update_live_status(self, x: float, y: float, safety_tripped: bool) -> None:
    self.live_position_xy = (x, y)
    self.live_position_var.set(f"Live position: X={x:.2f}, Y={y:.2f}")
    if safety_tripped:
      self.safety_state_var.set(
        "Safety state: TRIPPED. Reset E-stop cords, then press the lighted Reset "
        "button to re-enable the winder."
      )
    else:
      self.safety_state_var.set("Safety state: OK (not tripped).")
    self._refresh_canvas()

  def _set_live_position_unavailable(self, message: str) -> None:
    self.live_position_xy = None
    self.live_position_var.set(message)
    self.safety_state_var.set(
      "Safety state: unavailable (PLC not connected or tag read failed)."
    )
    self._refresh_canvas()

  def _on_close(self) -> None:
    self._position_tracker_stop.set()
    self.destroy()


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description=(
      "GUI waypoint planner/executor for motionQueueTest waypoint_path flow."
    )
  )
  parser.add_argument(
    "--plc-path",
    type=str,
    default=DEFAULT_PLC_PATH,
    help="PLC path/IP used by MotionQueueClient.",
  )
  parser.add_argument(
    "--machine-calibration",
    type=str,
    default="",
    help=(
      "Optional machine calibration JSON path or directory. "
      "Defaults to config/machineCalibration.json."
    ),
  )
  parser.add_argument(
    "--waypoint-allow-stops",
    action=argparse.BooleanOptionalAction,
    default=DEFAULT_WAYPOINT_ALLOW_STOPS,
    help=(
      "Enable stop/start fallback for waypoint planning when smooth biarc "
      "segments cannot stay inside machine XY bounds."
    ),
  )
  return parser.parse_args()


def main() -> None:
  args = parse_args()
  app = WaypointPlannerApp(
    plc_path=args.plc_path,
    machine_calibration=args.machine_calibration,
  )
  app.allow_stops_var.set(bool(args.waypoint_allow_stops))
  app.mainloop()


if __name__ == "__main__":
  main()
