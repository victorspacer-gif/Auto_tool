from dataclasses import dataclass


@dataclass(frozen=True)
class LightProfile:
    process_name: str
    address_hex: str
    default_value_hex: str
    boosted_value_hex: str
    description: str


DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl.exe",
    address_hex="133AA965",
    default_value_hex="07",
    boosted_value_hex="11",
    description="Light effect byte discovered from exact-value scans.",
)
