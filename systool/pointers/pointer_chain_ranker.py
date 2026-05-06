from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .memory_backend import AddressResolveError, LightMemoryController
from .profiles import DEFAULT_LIGHT_PROFILE


@dataclass
class ChainScore:
    chain_index: int
    chain: list[int]
    attempts: int = 0
    resolves: int = 0
    value_reads: int = 0
    expected_value_hits: int = 0
    signature_hits: int = 0
    errors: int = 0

    def final_score(self) -> float:
        if self.attempts <= 0:
            return 0.0
        repeatability = self.resolves / self.attempts
        readability = self.value_reads / self.attempts
        expected_hit_ratio = self.expected_value_hits / self.attempts
        sig_ratio = self.signature_hits / self.attempts
        depth_penalty = max(0, len(self.chain) - 4) * 0.03
        error_penalty = (self.errors / self.attempts) * 0.30
        score = 0.45 * repeatability + 0.25 * readability + 0.15 * expected_hit_ratio + 0.15 * sig_ratio
        score = score - depth_penalty - error_penalty
        return max(0.0, min(1.0, score))


def _parse_expected_values(raw: str) -> set[int]:
    values: set[int] = set()
    for token in [x.strip() for x in raw.split(",") if x.strip()]:
        values.add(int(token, 16))
    return values


def _signature_hit(controller: LightMemoryController, profile) -> bool:
    if not profile.signature_pattern:
        return False
    return controller.scan_signature_address(profile.signature_pattern) is not None


def run_ranking(sample_count: int, expected_values: set[int]) -> dict:
    profile = DEFAULT_LIGHT_PROFILE
    controller = LightMemoryController(profile.process_name)
    chain_scores = [ChainScore(chain_index=i, chain=list(chain)) for i, chain in enumerate(profile.pointer_chains)]

    try:
        controller.attach()
        module_base = controller.get_module_base(profile.module_name)

        for _ in range(sample_count):
            sig_hit = _signature_hit(controller, profile)
            for item in chain_scores:
                item.attempts += 1
                try:
                    base = controller.resolve_pointer_chain(module_base, item.chain)
                    target = base + profile.structure_value_offset
                    value = controller.read_byte(target)
                    item.resolves += 1
                    item.value_reads += 1
                    if value in expected_values:
                        item.expected_value_hits += 1
                    if sig_hit:
                        item.signature_hits += 1
                except AddressResolveError:
                    item.errors += 1
                except Exception:
                    item.errors += 1
    finally:
        controller.detach()

    ranked = sorted(chain_scores, key=lambda x: x.final_score(), reverse=True)
    return {
        "process_name": profile.process_name,
        "module_name": profile.module_name,
        "structure_value_offset": profile.structure_value_offset,
        "sample_count": sample_count,
        "expected_values_hex": [f"0x{v:02X}" for v in sorted(expected_values)],
        "ranked": [
            {
                **asdict(item),
                "chain_hex": [f"0x{v:X}" for v in item.chain],
                "score": round(item.final_score(), 4),
            }
            for item in ranked
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank configured light pointer chains by runtime reliability.")
    parser.add_argument("--samples", type=int, default=8, help="Number of attempts per chain in one run.")
    parser.add_argument(
        "--expected-values",
        default="07,11",
        help="Comma-separated expected byte values in hex (without 0x), e.g. 07,11",
    )
    parser.add_argument(
        "--output-json",
        default="systool/pointers/pointer_chain_rankings.json",
        help="Output JSON report path.",
    )
    args = parser.parse_args()

    expected_values = _parse_expected_values(args.expected_values)
    report = run_ranking(sample_count=max(1, args.samples), expected_values=expected_values)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[INFO] Wrote ranking report: {output_path}")
    print("[INFO] Ranked chains:")
    for idx, item in enumerate(report["ranked"], start=1):
        chain = " -> ".join(item["chain_hex"])
        print(f"  {idx}. score={item['score']:.4f}  chain={chain}")


if __name__ == "__main__":
    main()
