"""MP (Mana Points) pointer profile imported from MP pointer.CT.

Pointer chain: miracle_gl.exe + 0x00A783E0 → [read_uint] + 0x4F8 → [read_double] = MP value (Double)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MPProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)  # Pointer chains from module base to struct (ranked best→worst)
    structure_value_offset: int = 0  # Offset into the struct where the value field lives (0 for flat structs like Cap/HP/MP)
    description: str = ""


DEFAULT_MP_PROFILE = MPProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0x4F8],  # Chain: module_base + 0x00A783E0 → read_uint → + 0x4F8 = MP value (Double)
    ],
    structure_value_offset=0,  # Flat struct — value is at the resolved address itself (no additional offset)
    description="MP (Mana Points) pointer imported from MP pointer.CT.",
)
