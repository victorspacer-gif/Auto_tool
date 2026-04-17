from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


HEX_ADDRESS_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]{6,16})")
POINTER_LITERAL_RE = re.compile(r"P->(?:0x)?([0-9A-Fa-f]{1,16})", re.IGNORECASE)


@dataclass
class AddressListParseResult:
    file_path: Path
    absolute_addresses: list[int]
    pointer_literals: list[int]


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

    # These are not guaranteed pointer chains; they are candidate direct RVAs.
    # Useful when you can compare against a live module base in CE.
    direct_rva_templates = ["[0x<module_relative_offset>, 0x%X]" % value_offset]

    return {
        "value_offset_hex": f"0x{value_offset:X}",
        "runs": by_file,
        "shared_structure_bases": [f"0x{value:X}" for value in sorted(shared_bases)],
        "all_structure_bases": [f"0x{value:X}" for value in all_bases],
        "pointer_chain_templates": direct_rva_templates,
    }


def build_profile_snippet(value_offset: int) -> str:
    return f"""DEFAULT_PROFILE = LightProfile(
    process_name="miracle_gl",
    module_name="miracle_gl",
    pointer_chains=[
        # Replace with CE chains in module-relative form.
        # Example: [0x01ABCDEF, 0x20, 0x10, 0x{value_offset:X}]
    ],
    structure_value_offset=0x{value_offset:X},
    signature_pattern="AA BB CC ?? DD",
    signature_offset_to_base=0,
    default_value_hex="07",
    boosted_value_hex="11",
    description="Dynamic light resolver: pointer chain first, signature fallback.",
)
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse Cheat Engine addresslist snapshots and generate pointer-chain scaffolding "
            "for light_profile.py."
        )
    )
    parser.add_argument(
        "--study-dir",
        default="Pointer_study",
        help="Directory containing *.scandata.addresslist files.",
    )
    parser.add_argument(
        "--value-offset",
        default="0xAD",
        help="Structure field offset from base (e.g. 0xAD from mov [eax+0xAD], cl).",
    )
    parser.add_argument(
        "--output-json",
        default="studiomemuer_light_module/pointer_chain_candidates.json",
        help="Where to write machine-readable analysis output.",
    )
    args = parser.parse_args()

    value_offset = int(args.value_offset, 0)
    study_dir = Path(args.study_dir)
    input_files = sorted(study_dir.glob("*.scandata.addresslist"))

    if not input_files:
        raise SystemExit(f"No addresslist files found in: {study_dir}")

    parsed_runs = [parse_addresslist_file(path) for path in input_files]
    summary = summarize_runs(parsed_runs, value_offset)
    summary["profile_snippet"] = build_profile_snippet(value_offset)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[INFO] Parsed {len(parsed_runs)} addresslist file(s).")
    print(f"[INFO] Wrote analysis: {output_path}")
    print()
    print("=== Profile snippet template ===")
    print(summary["profile_snippet"])

    if summary["shared_structure_bases"]:
        print("[INFO] Shared structure-base candidates across all runs:")
        for item in summary["shared_structure_bases"]:
            print(f"  - {item}")
    else:
        print("[WARN] No shared structure-base candidates across all runs.")
        print("[WARN] This is expected when targets are fully dynamic per session.")
        print("[HINT] Use this tool's output plus CE pointer scanner chains to fill pointer_chains.")


if __name__ == "__main__":
    main()
