from dataclasses import dataclass, field


@dataclass(frozen=True)
class LightProfile:
    process_name: str
    module_name: str
    # CE-style chains relative to module base. Example: [[0x01234567, 0x18, 0xAD]]
    pointer_chains: list[list[int]] = field(default_factory=list)
    # Fallback for `mov [eax+0xAD], cl` style layouts.
    structure_value_offset: int = 0xAD
    signature_pattern: str | None = None
    signature_offset_to_base: int = 0
    default_value_hex: str = "07"
    boosted_value_hex: str = "11"
    description: str = ""


DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl",
    module_name="miracle_gl",
    pointer_chains=[],
    structure_value_offset=0xAD,
    # Signature derived from your structure snapshots. Keep short/stable bytes and use ?? for volatile parts.
    signature_pattern=(
        "5F 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "0F 00 00 00"
    ),
    signature_offset_to_base=0,
    default_value_hex="07",
    boosted_value_hex="11",
    description="Dynamic light resolver: pointer chain first, signature fallback.",
)