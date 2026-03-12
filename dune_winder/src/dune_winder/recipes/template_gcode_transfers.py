###############################################################################
# Name: TemplateGCodeTransfers.py
# Uses: Shared helpers for G106 transfer emission in template generators.
# Date: 2026-03-05
###############################################################################


def g106_line(line_builder, mode):
  return line_builder("G106", "P" + str(int(mode)))


def append_g106_transfer(
  lines,
  *,
  line_builder,
  transfer_pause,
  include_lead_mode,
  lead_mode,
  pause_mode,
  tail_mode,
):
  if include_lead_mode:
    lines.append(g106_line(line_builder, lead_mode))
  if transfer_pause:
    lines.append(g106_line(line_builder, pause_mode))
  lines.append(g106_line(line_builder, tail_mode))


def append_b_to_a_transfer(
  lines,
  *,
  line_builder,
  transfer_pause,
  include_lead_mode,
):
  append_g106_transfer(
    lines,
    line_builder=line_builder,
    transfer_pause=transfer_pause,
    include_lead_mode=include_lead_mode,
    lead_mode=3,
    pause_mode=2,
    tail_mode=0,
  )


def append_a_to_b_transfer(
  lines,
  *,
  line_builder,
  transfer_pause,
  include_lead_mode,
):
  append_g106_transfer(
    lines,
    line_builder=line_builder,
    transfer_pause=transfer_pause,
    include_lead_mode=include_lead_mode,
    lead_mode=0,
    pause_mode=1,
    tail_mode=3,
  )
