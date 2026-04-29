"""Cap (Maximum HP) pointer profile imported from CAP pointer.CT.

Pointer chain: miracle_gl.exe + 0x00A783E0 → [read_uint] + 0x4B8 → [read_double] = Cap value (Double)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)  # Pointer chains from module base to struct (ranked best→worst)
    structure_value_offset: int = 0  # Offset into the struct where the value field lives (0 for flat structs like Cap/HP/MP)
    description: str = ""


DEFAULT_CAP_PROFILE = CapProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0x4B8],  # Chain: module_base + 0x00A783E0 → read_uint → + 0x4B8 = Cap value (Double)
    ],
    structure_value_offset=0,  # Flat struct — value is at the resolved address itself (no additional offset)
    description="Cap (Maximum HP) pointer imported from CAP pointer.CT.",
)
