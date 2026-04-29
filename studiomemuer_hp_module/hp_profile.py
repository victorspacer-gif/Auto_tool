"""HP pointer profile imported from HP pointer.CT.

Pointer chain: miracle_gl.exe + 0x00A783E0 → [read_uint] + 0x4A0 → [read_uchar] = HP value (Byte)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HPProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)  # Pointer chains from module base to struct (ranked best→worst)
    structure_value_offset: int = 0  # Offset into the struct where the value field lives (0 for flat structs like Cap/HP/MP)
    description: str = ""


DEFAULT_HP_PROFILE = HPProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0x4A0],  # Chain: module_base + 0x00A783E0 → read_uint → + 0x4A0 = HP value (Byte)
    ],
    structure_value_offset=0,  # Flat struct — value is at the resolved address itself (no additional offset)
    description="HP pointer imported from HP pointer.CT.",
)
