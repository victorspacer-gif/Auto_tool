from dataclasses import dataclass, field


@dataclass(frozen=True)
class LightProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0xAD
    signature_pattern: str | None = None
    signature_offset_to_base: int = 0
    default_value_hex: str = "07"
    boosted_value_hex: str = "11"
    description: str = ""


DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x254, 0x18, 0x3C, 0x0],
        [0x18, 0x234, 0x48, 0x0],
        [0x38, 0x24C, 0x84, 0x24, 0x0],
    ],
    structure_value_offset=0xAD,
    signature_pattern="44 65 70 72 69 76 65 64",
    signature_offset_to_base=0,
    default_value_hex="07",
    boosted_value_hex="11",
    description="Light value via module-relative pointer chains with signature fallback.",
)
