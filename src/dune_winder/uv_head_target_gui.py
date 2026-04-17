from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

from dune_winder.uv_head_target import (
  Point2D,
  UvHeadTargetError,
  UvHeadTargetRequest,
  UvHeadTargetResult,
  compute_uv_head_target,
)


CANVAS_WIDTH = 900
CANVAS_HEIGHT = 700
CANVAS_PADDING = 40.0


@dataclass
class _FormState:
  layer_var: tk.StringVar
  head_z_mode_var: tk.StringVar
  anchor_pin_var: tk.StringVar
  near_pin_var: tk.StringVar
  target_pair_pin_var: tk.StringVar
  error_var: tk.StringVar
  summary_var: tk.StringVar
  canvas: tk.Canvas


def build_request_from_form(form: _FormState) -> UvHeadTargetRequest:
  return UvHeadTargetRequest(
    layer=form.layer_var.get(),
    anchor_pin=form.anchor_pin_var.get(),
    near_pin=form.near_pin_var.get(),
    target_pair_pin_b=form.target_pair_pin_var.get(),
    head_z_mode=form.head_z_mode_var.get(),
  )


def format_result_summary(result: UvHeadTargetResult) -> str:
  return "\n".join(
    (
      f"Orientation: {result.orientation_token}",
      f"Midpoint: ({result.midpoint_point.x:.3f}, {result.midpoint_point.y:.3f})",
      f"Transfer: ({result.transfer_point.x:.3f}, {result.transfer_point.y:.3f})",
      f"Final head: ({result.final_head_point.x:.3f}, {result.final_head_point.y:.3f})",
      f"Final wire: ({result.final_wire_point.x:.3f}, {result.final_wire_point.y:.3f})",
    )
  )


def _collect_draw_points(result: UvHeadTargetResult) -> list[Point2D]:
  bounds = result.transfer_bounds
  return [
    Point2D(result.anchor_pin_point.x, result.anchor_pin_point.y),
    Point2D(result.near_pin_point.x, result.near_pin_point.y),
    Point2D(result.target_pair_pin_point.x, result.target_pair_pin_point.y),
    Point2D(result.midpoint_point.x, result.midpoint_point.y),
    result.transfer_point,
    Point2D(result.effective_anchor_point.x, result.effective_anchor_point.y),
    Point2D(result.final_head_point.x, result.final_head_point.y),
    Point2D(result.final_wire_point.x, result.final_wire_point.y),
    Point2D(bounds.left, bounds.top),
    Point2D(bounds.right, bounds.bottom),
  ]


def _build_canvas_transform(result: UvHeadTargetResult, width: float, height: float):
  points = _collect_draw_points(result)
  xs = [point.x for point in points]
  ys = [point.y for point in points]
  min_x = min(xs) - result.pin_radius - CANVAS_PADDING
  max_x = max(xs) + result.pin_radius + CANVAS_PADDING
  min_y = min(ys) - result.pin_radius - CANVAS_PADDING
  max_y = max(ys) + result.pin_radius + CANVAS_PADDING
  span_x = max(max_x - min_x, 1.0)
  span_y = max(max_y - min_y, 1.0)
  scale = min(width / span_x, height / span_y)

  def project(point: Point2D) -> tuple[float, float]:
    x = (point.x - min_x) * scale
    y = height - ((point.y - min_y) * scale)
    return (x, y)

  return project, scale


def _draw_labeled_point(
  canvas: tk.Canvas,
  project,
  point: Point2D,
  *,
  label: str,
  color: str,
  radius: float = 4.0,
) -> None:
  x, y = project(point)
  canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=color)
  canvas.create_text(x + 8, y - 10, text=label, fill=color, anchor="w")


def draw_result(canvas: tk.Canvas, result: UvHeadTargetResult) -> None:
  width = float(canvas.winfo_width() or CANVAS_WIDTH)
  height = float(canvas.winfo_height() or CANVAS_HEIGHT)
  canvas.delete("all")
  project, scale = _build_canvas_transform(result, width, height)
  bounds = result.transfer_bounds
  left_top = project(Point2D(bounds.left, bounds.top))
  right_bottom = project(Point2D(bounds.right, bounds.bottom))
  canvas.create_rectangle(
    left_top[0],
    left_top[1],
    right_bottom[0],
    right_bottom[1],
    outline="#888888",
    dash=(4, 4),
  )

  anchor_center = Point2D(result.anchor_pin_point.x, result.anchor_pin_point.y)
  effective_anchor = Point2D(result.effective_anchor_point.x, result.effective_anchor_point.y)
  midpoint = Point2D(result.midpoint_point.x, result.midpoint_point.y)
  final_head = Point2D(result.final_head_point.x, result.final_head_point.y)
  final_wire = Point2D(result.final_wire_point.x, result.final_wire_point.y)
  near_pin = Point2D(result.near_pin_point.x, result.near_pin_point.y)
  target_pair_pin = Point2D(result.target_pair_pin_point.x, result.target_pair_pin_point.y)
  transfer_point = result.transfer_point

  anchor_x, anchor_y = project(anchor_center)
  canvas.create_oval(
    anchor_x - (result.pin_radius * scale),
    anchor_y - (result.pin_radius * scale),
    anchor_x + (result.pin_radius * scale),
    anchor_y + (result.pin_radius * scale),
    outline="#3b82f6",
    width=2,
  )

  transfer_xy = project(transfer_point)
  midpoint_xy = project(midpoint)
  effective_anchor_xy = project(effective_anchor)
  final_head_xy = project(final_head)
  final_wire_xy = project(final_wire)
  near_xy = project(near_pin)
  target_pair_xy = project(target_pair_pin)

  canvas.create_line(anchor_x, anchor_y, midpoint_xy[0], midpoint_xy[1], fill="#b0b0b0", dash=(2, 2))
  canvas.create_line(effective_anchor_xy[0], effective_anchor_xy[1], final_wire_xy[0], final_wire_xy[1], fill="#059669", width=2)
  canvas.create_line(final_head_xy[0], final_head_xy[1], final_wire_xy[0], final_wire_xy[1], fill="#dc2626", width=2)
  canvas.create_line(midpoint_xy[0], midpoint_xy[1], transfer_xy[0], transfer_xy[1], fill="#7c3aed", dash=(4, 2))

  _draw_labeled_point(canvas, project, anchor_center, label="anchor", color="#1d4ed8", radius=5.0)
  _draw_labeled_point(canvas, project, near_pin, label="near", color="#0f766e", radius=4.0)
  _draw_labeled_point(canvas, project, target_pair_pin, label="pair", color="#0f766e", radius=4.0)
  _draw_labeled_point(canvas, project, midpoint, label="midpoint", color="#6d28d9")
  _draw_labeled_point(canvas, project, transfer_point, label="transfer", color="#7c3aed")
  _draw_labeled_point(canvas, project, effective_anchor, label="tangent", color="#2563eb")
  _draw_labeled_point(canvas, project, final_head, label="head", color="#dc2626", radius=5.0)
  _draw_labeled_point(canvas, project, final_wire, label="wire", color="#059669", radius=5.0)
  canvas.create_text(10, 10, anchor="nw", fill="#222222", text=f"{result.request.layer} {result.orientation_token}")


def calculate_and_render(
  form: _FormState,
  *,
  compute_fn=compute_uv_head_target,
) -> UvHeadTargetResult | None:
  request = build_request_from_form(form)
  try:
    result = compute_fn(request)
  except UvHeadTargetError as exc:
    form.error_var.set(str(exc))
    form.summary_var.set("")
    form.canvas.delete("all")
    return None

  form.error_var.set("")
  form.summary_var.set(format_result_summary(result))
  draw_result(form.canvas, result)
  return result


def _build_form(root: tk.Misc) -> _FormState:
  controls = tk.Frame(root, padx=12, pady=12)
  controls.grid(row=0, column=0, sticky="ns")
  viewer = tk.Frame(root, padx=12, pady=12)
  viewer.grid(row=0, column=1, sticky="nsew")
  root.columnconfigure(1, weight=1)
  root.rowconfigure(0, weight=1)
  viewer.columnconfigure(0, weight=1)
  viewer.rowconfigure(1, weight=1)

  layer_var = tk.StringVar(master=root, value="U")
  head_z_mode_var = tk.StringVar(master=root, value="front")
  anchor_pin_var = tk.StringVar(master=root, value="B1201")
  near_pin_var = tk.StringVar(master=root, value="B2002")
  target_pair_pin_var = tk.StringVar(master=root, value="B2003")
  error_var = tk.StringVar(master=root, value="")
  summary_var = tk.StringVar(master=root, value="")

  tk.Label(controls, text="Layer").grid(row=0, column=0, sticky="w")
  tk.OptionMenu(controls, layer_var, "U", "V").grid(row=1, column=0, sticky="ew")
  tk.Label(controls, text="Head Z").grid(row=2, column=0, sticky="w", pady=(10, 0))
  tk.OptionMenu(controls, head_z_mode_var, "front", "back").grid(row=3, column=0, sticky="ew")

  tk.Label(controls, text="Anchor Pin").grid(row=4, column=0, sticky="w", pady=(10, 0))
  tk.Entry(controls, textvariable=anchor_pin_var).grid(row=5, column=0, sticky="ew")
  tk.Label(controls, text="Near Pin").grid(row=6, column=0, sticky="w", pady=(10, 0))
  tk.Entry(controls, textvariable=near_pin_var).grid(row=7, column=0, sticky="ew")
  tk.Label(controls, text="Target Pair Pin").grid(row=8, column=0, sticky="w", pady=(10, 0))
  tk.Entry(controls, textvariable=target_pair_pin_var).grid(row=9, column=0, sticky="ew")

  canvas = tk.Canvas(viewer, width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg="white", highlightthickness=1, highlightbackground="#cccccc")
  canvas.grid(row=1, column=0, sticky="nsew")

  form = _FormState(
    layer_var=layer_var,
    head_z_mode_var=head_z_mode_var,
    anchor_pin_var=anchor_pin_var,
    near_pin_var=near_pin_var,
    target_pair_pin_var=target_pair_pin_var,
    error_var=error_var,
    summary_var=summary_var,
    canvas=canvas,
  )

  tk.Button(
    controls,
    text="Calculate",
    command=lambda: calculate_and_render(form),
  ).grid(row=10, column=0, sticky="ew", pady=(12, 0))
  tk.Label(controls, textvariable=error_var, fg="#b91c1c", justify="left", wraplength=240).grid(row=11, column=0, sticky="ew", pady=(10, 0))
  tk.Label(viewer, textvariable=summary_var, justify="left", anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 10))
  return form


def run_app(root: tk.Misc | None = None) -> None:
  root = root or tk.Tk()
  root.title("UV Head Target GUI")
  _build_form(root)
  root.mainloop()


if __name__ == "__main__":
  run_app()
