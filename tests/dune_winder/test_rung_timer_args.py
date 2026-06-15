import json

from dune_winder.convert_plc_rllscrap import resolve_timer_counter_args as resolve_paste_timer_args
from dune_winder.plc_ladder.metadata import load_plc_metadata
from dune_winder.rung_lang.cli import main_compile
from dune_winder.rung_lang.context import build_import_l5x
from dune_winder.rung_lang.emit_rllscrap import rung_text
from dune_winder.rung_lang.lower import Lowered, lower_routine
from dune_winder.rung_lang.parse_rllscrap import parse_rllscrap_text
from dune_winder.rung_lang.parser import parse_rung_source
from dune_winder.rung_lang.render import render_routine
from dune_winder.rung_lang.tagmeta import load_tag_meta
from dune_winder.rung_lang.timer_args import resolve_timer_counter_args


def _write_tag_json(root):
    (root / "prog").mkdir(parents=True)
    (root / "controller_level_tags.json").write_text(
        json.dumps(
            {
                "controller_level_tags": [
                    {
                        "name": "TimerA",
                        "fully_qualified_name": "TimerA",
                        "data_type_name": "TIMER",
                        "value": {"PRE": 123, "ACC": 45},
                    },
                    {
                        "name": "OffDelay",
                        "fully_qualified_name": "OffDelay",
                        "data_type_name": "TIMER",
                        "value": {"PRE": 500, "ACC": 7},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "prog" / "programTags.json").write_text(
        json.dumps(
            {
                "program_name": "prog",
                "main_routine_name": "main",
                "routines": ["main"],
                "program_tags": [],
            }
        ),
        encoding="utf-8",
    )


def _write_donor(root):
    donor_dir = root / "ACD" / "donors" / "prog"
    donor_dir.mkdir(parents=True)
    (donor_dir / "main_Routine_RLL.L5X").write_text(
        """
<RSLogix5000Content>
<Controller Use="Context">
<Programs Use="Context">
<Program Use="Context" Name="prog">
<Tags Use="Context">
</Tags>
</Program>
</Programs>
</Controller>
<Routine Use="Target" Name="main" Type="RLL">
<RLLContent>
</RLLContent>
</Routine>
</RSLogix5000Content>
""".strip(),
        encoding="utf-8",
    )


def test_render_resolves_tof_timer_arguments_from_tag_values(tmp_path):
    _write_tag_json(tmp_path)
    meta = load_tag_meta(tmp_path)
    routine = parse_rllscrap_text(
        "XIC(Input)TOF(OffDelay,?,?);",
        program="prog",
        routine="main",
    )

    resolved = resolve_timer_counter_args(routine, meta)
    rendered = render_routine(resolved, meta).text

    assert "TOF(OffDelay, 500, 7) when Input" in rendered


def test_paste_timer_resolver_handles_tof_and_paren_dialect(tmp_path):
    _write_tag_json(tmp_path)
    metadata = load_plc_metadata(tmp_path)

    resolved = resolve_paste_timer_args(
        "XIC(Input) TOF(OffDelay,?,?) TON TimerA ? ?",
        metadata,
        "prog",
    )

    assert resolved == "XIC(Input) TOF(OffDelay,500,7) TON TimerA 123 45"


def test_lowered_timer_arguments_are_written_to_import_l5x(tmp_path):
    _write_tag_json(tmp_path)
    _write_donor(tmp_path)
    meta = load_tag_meta(tmp_path)
    source = """
routine prog/main

uses TimerA, OffDelay

start_timer TimerA

TOF(OffDelay, ?, ?)
""".lstrip()

    ast = parse_rung_source(source)
    lowered = lower_routine(ast)
    resolved = Lowered(
        resolve_timer_counter_args(lowered.routine, meta),
        lowered.auto_tags,
    )
    texts = [rung_text(rung) for rung in resolved.routine.rungs]
    l5x = build_import_l5x(tmp_path, "prog", "main", texts, [])

    assert "<![CDATA[TON(TimerA,123,45);]]>" in l5x
    assert "<![CDATA[TOF(OffDelay,500,7);]]>" in l5x


def test_rung_compile_writes_resolved_timer_arguments_to_import_l5x(tmp_path):
    _write_tag_json(tmp_path)
    _write_donor(tmp_path)
    routine_dir = tmp_path / "prog" / "main"
    routine_dir.mkdir()
    (routine_dir / "studio_copy.rllscrap").write_text(
        "TON(TimerA,?,?);TOF(OffDelay,?,?);",
        encoding="utf-8",
    )
    source = routine_dir / "main.rung"
    source.write_text(
        """
routine prog/main

uses TimerA, OffDelay

start_timer TimerA

TOF(OffDelay, ?, ?)
""".lstrip(),
        encoding="utf-8",
    )

    assert main_compile([str(source), "--plc-root", str(tmp_path)]) == 0
    l5x = (routine_dir / "main_import.L5X").read_text(encoding="utf-8-sig")

    assert "<![CDATA[TON(TimerA,123,45);]]>" in l5x
    assert "<![CDATA[TOF(OffDelay,500,7);]]>" in l5x
