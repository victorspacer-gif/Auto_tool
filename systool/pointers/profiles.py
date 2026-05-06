"""Central pointer profiles shared across the project."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


CT_POINTERS_DIR = Path(__file__).resolve().parents[2] / "pointers_ct"


@dataclass(frozen=True)
class StatPointerProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0
    read_method: str = "read_double"
    description: str = ""
    ct_filename: str = ""


@dataclass(frozen=True)
class LightPointerProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0
    signature_pattern: str | None = None
    signature_offset_to_base: int = 0
    color_enabled_value: int = 215
    default_intensity_value: int = 8
    boosted_intensity_value: int = 11
    description: str = ""
    ct_filename: str = ""


DEFAULT_HP_PROFILE = StatPointerProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[[0x00A783E0, 0x4A0]],
    structure_value_offset=0,
    read_method="read_double",
    description="HP pointer imported from HP pointer.CT.",
    ct_filename="HP pointer.CT",
)

DEFAULT_MP_PROFILE = StatPointerProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[[0x00A783E0, 0x4F8]],
    structure_value_offset=0,
    read_method="read_double",
    description="MP pointer imported from MP pointer.CT.",
    ct_filename="MP pointer.CT",
)

DEFAULT_CAP_PROFILE = StatPointerProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[[0x00A783E0, 0x4B8]],
    structure_value_offset=0,
    read_method="read_double",
    description="Cap pointer imported from CAP pointer.CT.",
    ct_filename="CAP pointer.CT",
)

DEFAULT_FOOD_PROFILE = StatPointerProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00285388, 0x69C, 0x3E8],
        [0x00285388, 0x69C, 0x3E8, 0x3BC],
        [0x00285388, 0x69C, 0x3E8, 0x3CC],
    ],
    structure_value_offset=0,
    read_method="read_double",
    description="Food pointer imported from Food_pointers.CT.",
    ct_filename="Food_pointers.CT",
)

DEFAULT_LIGHT_PROFILE = LightPointerProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0xAC],
        [0x00A786F8, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x0, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x4, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x4, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x8, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x8, 0x8, 0x14, 0xAC],
        [0x00A783EC, 0x5C, 0x0, 0xDC, 0xAC],
        [0x00A786F8, 0x4, 0x0, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x0, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x4, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x4, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x8, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x8, 0x0, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x0, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x0, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x4, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x4, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x8, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x8, 0x8, 0x4, 0x14, 0xAC],
        [0x00A786F8, 0x4, 0x0, 0x8, 0x14, 0xAC],
        [0x00A786F8, 0x0, 0x14, 0xAC],
    ],
    structure_value_offset=0,
    signature_pattern=None,
    signature_offset_to_base=0,
    color_enabled_value=215,
    default_intensity_value=8,
    boosted_intensity_value=11,
    description="Light color pointer list imported from Light Pointers.CT.",
    ct_filename="Light Pointers.CT",
)


STAT_PROFILES: dict[str, StatPointerProfile] = {
    "hp": DEFAULT_HP_PROFILE,
    "mp": DEFAULT_MP_PROFILE,
    "cap": DEFAULT_CAP_PROFILE,
    "food": DEFAULT_FOOD_PROFILE,
}
