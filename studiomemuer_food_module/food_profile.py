"""Food timer pointer profile imported from Food_pointers.CT.

Pointer chain: miracle_gl.exe + 0x00285388 → [read_uint] + 0x69C → [read_uint] + 0x3E8 = food value (Double)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FoodProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0
    signature_pattern: str | None = None
    signature_offset_to_base: int = 0
    description: str = ""


DEFAULT_FOOD_PROFILE = FoodProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00285388, 0x69C, 0x3E8],  # Chain A: shortest path (3 hops) — highest reliability from miracle_gl.exe
        [0x00285388, 0x69C, 0x3E8, 0x3BC],  # Chain B: variant with extra indirection at 0x3BC
        [0x00285388, 0x69C, 0x3E8, 0x3CC],  # Chain C: variant with extra indirection at 0x3CC
    ],
    structure_value_offset=0,
    signature_pattern=None,
    signature_offset_to_base=0,
    description="Food timer pointer imported from Food_pointers.CT.",
)
