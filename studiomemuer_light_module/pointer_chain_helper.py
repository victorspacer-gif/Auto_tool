from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


HEX_ADDRESS_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]{6,16})")
POINTER_LITERAL_RE = re.compile(r"P->(?:0x)?([0-9A-Fa-f]{1,16})", re.IGNORECASE)


# =========================
# DATA CLASSES
# =========================

@dataclass
class AddressListParseResult:
    file_path: Path
    absolute_addresses: list[int]
    pointer_literals: list[int]


@dataclass
class ValidatedStructure:
    base: int
    score: float
    matches: list[str]


# =========================
# PARSING
# =========================

def parse_addresslist_file(path: Path) -> AddressListParseResult:
    absolute_addresses: list[int] = []
    pointer_literals: list[int] = []

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        pointer_match = POINTER_LITERAL_RE.search(line)
        if pointer_match:
            pointer_literals.append(int(pointer_match.group(1), 16))
            continue

        left = line.split("=", 1)[0].strip()
        address_match = HEX_ADDRESS_RE.match(left)
        if address_match:
            absolute_addresses.append(int(address_match.group(1), 16))

    return AddressListParseResult(
        file_path=path,
        absolute_addresses=absolute_addresses,
        pointer_literals=pointer_literals,
    )


# =========================
# STRUCTURE VALIDATION
# =========================

def score_structure_bytes(data: bytes) -> tuple[float, list[str]]:
    score = 0.0
    matches: list[str] = []

    if b"Deprived" in data:  # ASCII string "Deprived" is a strong marker for the light struct
        score += 0.5
        matches.append("ASCII:Deprived")

    if b"\xCE\x07" in data:  # Known byte pattern at struct base (from CE pointer analysis)
        score += 0.3
        matches.append("Pattern:CE07")

    # float 1.0 pattern (0x3F800000 in little-endian IEEE 754)
    float_count = data.count(b"\x00\x00\x80\x3F")
    if float_count >= 4:  # Need at least 4 occurrences for confidence (reduces false positives)
        score += 0.2
        matches.append("FloatBlock")

    return score, matches


def load_memory_dump(path: Path) -> bytes:
    """
    Accepts raw hex dump (like CE copy) OR binary file
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")

    # try hex parsing
    hex_bytes = re.findall(r"[0-9A-Fa-f]{2}", raw)
    if hex_bytes:
        try:
            return bytes(int(b, 16) for b in hex_bytes)
        except Exception:
            pass

    # fallback: raw bytes
    return path.read_bytes()


# =========================
# CORE LOGIC
# =========================

def summarize_runs(parsed_runs: list[AddressListParseResult], value_offset: int) -> dict:
    by_file = []
    base_candidates_by_file: list[set[int]] = []

    for run in parsed_runs:
        structure_bases = [address - value_offset for address in run.absolute_addresses]
        base_candidates_by_file.append(set(structure_bases))

        by_file.append(
            {
                "file": str(run.file_path),
                "absolute_addresses": [f"0x{value:X}" for value in run.absolute_addresses],
                "structure_base_candidates": [f"0x{value:X}" for value in structure_bases],
                "pointer_literals": [f"0x{value:X}" for value in run.pointer_literals],
            }
        )

    shared_bases: set[int] = set()
    if base_candidates_by_file:
        shared_bases = set.intersection(*base_candidates_by_file)

    all_bases = sorted({value for base_set in base_candidates_by_file for value in base_set})

    return {
        "runs": by_file,
        "shared_structure_bases": [f"0x{v:X}" for v in sorted(shared_bases)],
        "all_structure_bases": [f"0x{v:X}" for v in all_bases],
    }


def validate_structures_from_dumps(dump_files: list[Path]) -> list[dict]:
    results: list[dict] = []

    for dump in dump_files:
        data = load_memory_dump(dump)
        score, matches = score_structure_bytes(data)

        if score > 0:
            results.append(
                {
                    "file": str(dump),
                    "score": round(score, 3),
                    "matches": matches,
                }
            )

    return results


# =========================
# PROFILE SNIPPET
# =========================

def build_profile_snippet(value_offset: int) -> str:
    return f"""DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl",
    module_name="miracle_gl",
    pointer_chains=[
        # Fill after pointer scan validation
        # Example: [0x01ABCDEF, 0x20, 0x10, 0x{value_offset:X}]
    ],
    structure_value_offset=0x{value_offset:X},
    signature_pattern="44 65 70 72 69 76 65 64",  # "Deprived"
    signature_offset_to_base=0,
    default_value_hex="07",
    boosted_value_hex="11",
    description="Code-anchored light resolver (EAX + 0xAD).",
)
"""


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--study-dir", default="Pointer_study")
    parser.add_argument("--value-offset", default="0xAD")
    parser.add_argument("--output-json", default="pointer_analysis.json")
    parser.add_argument("--memory-dumps", nargs="*", default=[])

    args = parser.parse_args()

    value_offset = int(args.value_offset, 0)

    study_dir = Path(args.study_dir)
    files = sorted(study_dir.glob("*.scandata.addresslist"))

    if not files:
        raise SystemExit("No addresslist files found.")

    parsed = [parse_addresslist_file(f) for f in files]

    summary = summarize_runs(parsed, value_offset)

    # Add structure validation
    dump_paths = [Path(p) for p in args.memory_dumps]
    validated = validate_structures_from_dumps(dump_paths)

    final_output = {
        "value_offset_hex": f"0x{value_offset:X}",
        "code_anchors": [
            {
                "instruction": "miracle_gl.exe+18664A",
                "operation": "mov [eax+0xAD], cl",
                "base_register": "EAX",
                "confidence": "high"
            }
        ],
        **summary,
        "validated_structures": validated,
        "pointer_chain_templates": [
            f"[0x<module_relative_offset>, ..., 0x{value_offset:X}]"
        ],
        "profile_snippet": build_profile_snippet(value_offset),
    }

    out_path = Path(args.output_json)
    out_path.write_text(json.dumps(final_output, indent=2), encoding="utf-8")

    print(f"[INFO] Analysis written to {out_path}")
    print()
    print(final_output["profile_snippet"])


if __name__ == "__main__":
    main()