"""Named-argument schemas for motion instructions (footguns #2/#4).

Each schema fixes the observed vendor operand order (see
``winder/plc/instruction_set.md``) and gives every trailing/optional
operand a default, so .rung sources only spell the values that matter:

    move_axis Z_axis using z_axis_pre_xy_retract:
        type     = absolute
        position = 0
        speed    = 1000 units/s
        ...

Both directions are table lookups: the compiler expands keys to the
positional list; the renderer maps positions back to keys and omits
defaults. An instruction whose operands don't fit its schema (wrong
count, unknown enum) renders as a generic ``MAM(...)`` action instead —
never a hard failure.
"""

from __future__ import annotations

from dataclasses import dataclass

# value <-> surface keyword maps -------------------------------------------

UNIT_WORDS = {
    "Units per sec": "units/s",
    "Units per sec2": "units/s2",
    "Units per sec3": "units/s3",
    "Seconds": "s",
}
UNIT_VALUES = {v: k for k, v in UNIT_WORDS.items()}

ENUM_WORDS = {
    "0": None,  # numeric enums handled per-field
    "S-Curve": "s-curve",
    "Trapezoidal": "trapezoidal",
    "Programmed": "programmed",
    "Actual Tolerance": "actual-tolerance",
    "No Settle": "no-settle",
    "Command Tolerance": "command-tolerance",
    "No Decel": "no-decel",
    "Disabled": "disabled",
    "Enabled": "enabled",
    "Coordinated Move": "coordinated-move",
    "Active Motion": "active-motion",
    "All": "all",
    "Yes": "yes",
    "No": "no",
    "None": "none",
    "Current": "current",
}
ENUM_VALUES = {v: k for k, v in ENUM_WORDS.items() if v}

MOVE_TYPE = {"0": "absolute", "1": "relative"}
MOVE_TYPE_VALUES = {v: k for k, v in MOVE_TYPE.items()}


@dataclass(frozen=True)
class Field:
    """One surface key covering one or more positional operands.

    kind:
        value  - number or tag reference (one operand)
        enum   - vendor enum string (one operand)
        type   - move type numeric enum (absolute/relative)
        rate   - value + unit pair (two operands; unit has a default)
        jerk   - accel jerk + decel jerk + unit (three operands; the
                 combined ``jerk`` key sets both jerks)
    ``default`` is the positional operand default ("" = required); for
    rate/jerk it is the value default, with ``unit_default`` alongside.
    """

    name: str
    index: int
    kind: str = "value"
    default: str | None = None
    unit_default: str | None = None

    @property
    def width(self) -> int:
        return {"rate": 2, "jerk": 3}.get(self.kind, 1)


@dataclass(frozen=True)
class MotionSchema:
    opcode: str
    keyword: str
    operand_count: int
    fields: tuple[Field, ...]


MAM = MotionSchema(
    "MAM",
    "move_axis",
    20,
    (
        Field("type", 2, "type"),
        Field("position", 3),
        Field("speed", 4, "rate", unit_default="Units per sec"),
        Field("accel", 6, "rate", unit_default="Units per sec2"),
        Field("decel", 8, "rate", unit_default="Units per sec2"),
        Field("profile", 10, "enum"),
        Field("jerk", 11, "jerk", unit_default="Units per sec3"),
        Field("merge", 14, default="0"),
        Field("merge_speed", 15, default="0"),
        Field("lock_position", 16, default="0"),
        Field("lock_direction", 17, default="0"),
        Field("event_distance", 18, default="0"),
        Field("calculated_data", 19, default="0"),
    ),
)

MCLM = MotionSchema(
    "MCLM",
    "coordinated_move",
    22,
    (
        Field("type", 2, "type"),
        Field("target", 3),
        Field("speed", 4, "rate", unit_default="Units per sec"),
        Field("accel", 6, "rate", unit_default="Units per sec2"),
        Field("decel", 8, "rate", unit_default="Units per sec2"),
        Field("profile", 10, "enum"),
        Field("jerk", 11, "jerk", default="500", unit_default="Units per sec3"),
        Field("merge", 14, default="0"),
        Field("merge_speed", 15, "enum", default="Disabled"),
        Field("termination", 16, "enum"),
        Field("command_tolerance", 17, default="50"),
        Field("lock_position", 18, default="0"),
        Field("lock_direction", 19, "enum", default="None"),
        Field("event_distance", 20, default="0"),
        Field("calculated_data", 21, default="0"),
    ),
)

MOTION_SCHEMAS = {s.opcode: s for s in (MAM, MCLM)}
MOTION_KEYWORDS = {s.keyword: s for s in MOTION_SCHEMAS.values()}

#: two-operand axis instructions with dedicated action keywords
SERVO_KEYWORDS = {
    "servo_on": "MSO",
    "servo_off": "MSF",
    "fault_reset": "MAFR",
}
SERVO_OPCODES = {v: k for k, v in SERVO_KEYWORDS.items()}


class SchemaError(ValueError):
    pass


def _needs_quote(text: str) -> bool:
    return any(ch in text for ch in ' ,()"')


def quote_operand(text: str) -> str:
    return f'"{text}"' if _needs_quote(text) else text


def unquote_operand(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _field_to_surface(
    field: Field, operands: tuple[str, ...]
) -> list[tuple[str, str]] | None:
    """Render one field; returns [] when all covered operands are default,
    None when the operands don't fit the schema (caller falls back)."""
    i = field.index
    if field.kind == "type":
        value = operands[i]
        word = MOVE_TYPE.get(value)
        if word is None:
            return None
        return [(field.name, word)]
    if field.kind == "enum":
        value = operands[i]
        if field.default is not None and value == field.default:
            return []
        word = ENUM_WORDS.get(value)
        return [(field.name, word if word else f'"{value}"')]
    if field.kind == "rate":
        value, unit = operands[i], operands[i + 1]
        unit_word = UNIT_WORDS.get(unit, f'"{unit}"')
        return [(field.name, f"{value} {unit_word}")]
    if field.kind == "jerk":
        accel, decel, unit = operands[i], operands[i + 1], operands[i + 2]
        out: list[tuple[str, str]] = []
        if accel == decel:
            if field.default is None or accel != field.default:
                out.append((field.name, accel))
        else:
            out.append(("accel_jerk", accel))
            out.append(("decel_jerk", decel))
        if unit != field.unit_default:
            out.append(("jerk_units", UNIT_WORDS.get(unit, f'"{unit}"')))
        return out
    # plain value
    value = operands[i]
    if field.default is not None and value == field.default:
        return []
    return [(field.name, value)]


def instr_to_surface(
    opcode: str, operands: tuple[str, ...]
) -> tuple[str, str, list[tuple[str, str]]] | None:
    """(keyword, "<target> using <control>", key/value list) or None when
    the operands don't fit the schema."""
    schema = MOTION_SCHEMAS.get(opcode)
    if schema is None or len(operands) != schema.operand_count:
        return None
    pairs: list[tuple[str, str]] = []
    for field in schema.fields:
        rendered = _field_to_surface(field, operands)
        if rendered is None:
            return None
        pairs.extend(rendered)
    header = f"{operands[0]} using {operands[1]}"
    return schema.keyword, header, pairs


def surface_to_operands(
    keyword: str, target: str, control: str, pairs: list[tuple[str, str]]
) -> tuple[str, tuple[str, ...]]:
    """Compile a motion action block back to the positional operand list."""
    schema = MOTION_KEYWORDS[keyword]
    operands: list[str | None] = [None] * schema.operand_count
    operands[0] = target
    operands[1] = control
    given = dict(pairs)
    if len(given) != len(pairs):
        raise SchemaError(f"{keyword}: duplicate key")

    for field in schema.fields:
        i = field.index
        if field.kind == "type":
            word = given.pop("type", None)
            if word is None:
                raise SchemaError(f"{keyword}: missing required key 'type'")
            value = MOVE_TYPE_VALUES.get(word, word)
            if value not in MOVE_TYPE:
                raise SchemaError(f"{keyword}: unknown move type {word!r}")
            operands[i] = value
        elif field.kind == "enum":
            word = given.pop(field.name, None)
            if word is None:
                if field.default is None:
                    raise SchemaError(f"{keyword}: missing required key {field.name!r}")
                operands[i] = field.default
            else:
                operands[i] = ENUM_VALUES.get(word, unquote_operand(word))
        elif field.kind == "rate":
            raw = given.pop(field.name, None)
            if raw is None:
                raise SchemaError(f"{keyword}: missing required key {field.name!r}")
            value, unit = _split_value_unit(raw, field, keyword)
            operands[i] = value
            operands[i + 1] = unit
        elif field.kind == "jerk":
            combined = given.pop(field.name, None)
            accel = given.pop("accel_jerk", None)
            decel = given.pop("decel_jerk", None)
            if combined is not None and (accel or decel):
                raise SchemaError(
                    f"{keyword}: give either 'jerk' or accel_jerk/decel_jerk"
                )
            if combined is None and accel is None and decel is None:
                if field.default is None:
                    raise SchemaError(f"{keyword}: missing required key 'jerk'")
                combined = field.default
            if combined is not None:
                accel = decel = combined
            if accel is None or decel is None:
                raise SchemaError(
                    f"{keyword}: accel_jerk and decel_jerk must both be given"
                )
            unit_word = given.pop("jerk_units", None)
            unit = (
                field.unit_default
                if unit_word is None
                else UNIT_VALUES.get(unit_word, unquote_operand(unit_word))
            )
            operands[i] = accel
            operands[i + 1] = decel
            operands[i + 2] = unit
        else:
            value = given.pop(field.name, None)
            if value is None:
                if field.default is None:
                    raise SchemaError(f"{keyword}: missing required key {field.name!r}")
                value = field.default
            operands[i] = unquote_operand(value)

    if given:
        raise SchemaError(f"{keyword}: unknown key(s) {sorted(given)}")
    missing = [i for i, op in enumerate(operands) if op is None]
    if missing:
        raise SchemaError(f"{keyword}: schema gap at operand(s) {missing}")
    return schema.opcode, tuple(op for op in operands if op is not None)


def _split_value_unit(raw: str, field: Field, keyword: str) -> tuple[str, str]:
    raw = raw.strip()
    if raw.endswith('"'):
        # trailing quoted unit, e.g. `5 "% of Maximum"`
        open_quote = raw.rfind('"', 0, len(raw) - 1)
        if open_quote > 0:
            return raw[:open_quote].strip(), raw[open_quote + 1 : -1]
    parts = raw.rsplit(None, 1)
    if len(parts) == 2 and parts[1] in UNIT_VALUES:
        return parts[0].strip(), UNIT_VALUES[parts[1]]
    if field.unit_default is None:
        raise SchemaError(f"{keyword}: {field.name} needs a unit")
    return raw, field.unit_default
