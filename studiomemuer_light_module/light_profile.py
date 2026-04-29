from dataclasses import dataclass, field


@dataclass(frozen=True)
class LightProfile:
    process_name: str
    module_name: str
    pointer_chains: list[list[int]] = field(default_factory=list)
    structure_value_offset: int = 0  # Offset into the struct where the value field lives (usually 0 for flat structs)
    signature_pattern: str | None = None  # AOB pattern string for signature scanning (e.g., "44 65 70 72 69 76 65 64")
    signature_offset_to_base: int = 0  # Distance from signature match to module base address (0 if not using signatures)
    color_enabled_value: int = 215  # Byte value written to enable/disable color mode in the game client
    default_intensity_value: int = 8  # Intensity byte for normal/default lighting state
    boosted_intensity_value: int = 11  # Intensity byte for boosted/brighter lighting state (higher = brighter)
    description: str = ""


DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl.exe",
    module_name="miracle_gl",
    pointer_chains=[
        [0x00A783E0, 0xAC],  # Chain A: shortest path (2 hops) — highest reliability
        [0x00A786F8, 0x8, 0x14, 0xAC],  # Chain B: 4-hop chain from alternate anchor
        [0x00A786F8, 0x0, 0x0, 0x8, 0x14, 0xAC],  # Chain C: deeper variant with extra indirection
        [0x00A786F8, 0x0, 0x4, 0x8, 0x14, 0xAC],  # Chain D: slight offset variation
        [0x00A786F8, 0x4, 0x4, 0x8, 0x14, 0xAC],  # Chain E: another offset variant
        [0x00A786F8, 0x0, 0x8, 0x8, 0x14, 0xAC],  # Chain F: deeper path with 0x8 hop
        [0x00A786F8, 0x4, 0x8, 0x8, 0x14, 0xAC],  # Chain G: variant of F with different first hop
        [0x00A783EC, 0x5C, 0x0, 0xDC, 0xAC],  # Chain H: alternate anchor (0x00A783EC) path
        [0x00A786F8, 0x4, 0x0, 0x0, 0x14, 0xAC],  # Chain I: shorter variant with zero hops
        [0x00A786F8, 0x8, 0x0, 0x0, 0x14, 0xAC],  # Chain J: similar to I but first hop is 0x8
        [0x00A786F8, 0x4, 0x4, 0x0, 0x14, 0xAC],  # Chain K: zero final hop variant
        [0x00A786F8, 0x8, 0x4, 0x0, 0x14, 0xAC],  # Chain L: variant of K with different first hop
        [0x00A786F8, 0x4, 0x8, 0x0, 0x14, 0xAC],  # Chain M: zero final hop with 0x8 middle
        [0x00A786F8, 0x8, 0x8, 0x0, 0x14, 0xAC],  # Chain N: variant of M with different first hop
        [0x00A786F8, 0x4, 0x14, 0xAC],  # Chain O: medium-depth chain skipping intermediate hops
        [0x00A786F8, 0x0, 0x0, 0x4, 0x14, 0xAC],  # Chain P: shorter variant with zero first hop
        [0x00A786F8, 0x8, 0x0, 0x4, 0x14, 0xAC],  # Chain Q: similar to P but first hop is 0x8
        [0x00A786F8, 0x0, 0x4, 0x4, 0x14, 0xAC],  # Chain R: zero first hop with 0x4 middle
        [0x00A786F8, 0x8, 0x4, 0x4, 0x14, 0xAC],  # Chain S: variant of R with different first hop
        [0x00A786F8, 0x0, 0x8, 0x4, 0x14, 0xAC],  # Chain T: zero first hop with 0x8 middle
        [0x00A786F8, 0x8, 0x8, 0x4, 0x14, 0xAC],  # Chain U: variant of T with different first hop
        [0x00A786F8, 0x4, 0x0, 0x8, 0x14, 0xAC],  # Chain V: medium-depth chain with zero middle hop
        [0x00A786F8, 0x0, 0x14, 0xAC],  # Chain W: short chain skipping intermediate indirections
    ],
    structure_value_offset=0,  # Offset into the struct where the value field lives (usually 0 for flat structs)
    signature_pattern=None,  # AOB pattern string for signature scanning (e.g., "44 65 70 72 69 76 65 64")
    signature_offset_to_base=0,  # Distance from signature match to module base address (0 if not using signatures)
    color_enabled_value=215,  # Byte value written to enable/disable color mode in the game client (0xD7)
    default_intensity_value=8,  # Intensity byte for normal/default lighting state
    boosted_intensity_value=11,  # Intensity byte for boosted/brighter lighting state (higher = brighter)
    description="Light color pointer list imported from Light Pointers.CT.",
)
