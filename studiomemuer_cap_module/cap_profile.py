"""Cap (Maximum HP) pointer profile imported from CAP pointer.CT.

Pointer chain: miracle_gl.exe + 0x00A783E0 → [read_uint] + 0x4B8 → [read_double] = Cap value (Double)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0
    description: str = ""


DEFAULT_CAP_PROFILE = CapProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0x4B8],
    ],
    structure_value_offset=0,
    description="Cap (Maximum HP) pointer imported from CAP pointer.CT.",
)
