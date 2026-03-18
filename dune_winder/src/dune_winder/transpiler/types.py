"""PLC type system: BOOL, REAL, DINT and register references."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto


class PLCType(Enum):
    BOOL = auto()
    REAL = auto()
    DINT = auto()
    IDX  = auto()   # scalar DINT for array subscripts; renders as idx_N (not DINTS[N])


@dataclass(frozen=True)
class Reg:
    """A reference to a numbered register slot: REALS[n], DINTS[n], BOOLS[n], idx_n."""
    typ: PLCType
    index: int

    def __str__(self) -> str:
        if self.typ == PLCType.REAL:
            return f"REALS[{self.index}]"
        if self.typ == PLCType.DINT:
            return f"DINTS[{self.index}]"
        if self.typ == PLCType.IDX:
            return f"idx_{self.index}"
        return f"BOOLS[{self.index}]"


@dataclass(frozen=True)
class SegField:
    """Reference to SegQueue[index_reg].FieldName (index_reg is a Reg or int literal)."""
    index_reg: Reg | int   # the loop counter register, or a literal index
    field: str             # e.g. "Speed", "XY[0]", "SegType"

    def __str__(self) -> str:
        return f"SegQueue[{self.index_reg}].{self.field}"


# Annotation strings → PLCType
ANNOTATION_MAP: dict[str, PLCType] = {
    "float": PLCType.REAL,
    "int": PLCType.DINT,
    "bool": PLCType.BOOL,
    "REAL": PLCType.REAL,
    "DINT": PLCType.DINT,
    "BOOL": PLCType.BOOL,
}


def plc_type_from_annotation(annotation: str) -> PLCType:
    return ANNOTATION_MAP.get(annotation, PLCType.REAL)
