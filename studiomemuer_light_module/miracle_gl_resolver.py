"""
miracle_gl_resolver.py
──────────────────────
Single-file live pointer chain resolver for miracle_gl.exe.

Integrates:
  • JSON analysis files (pointer_analysis.json)
  • Live process connection via pymem
  • Signature validation at resolved bases
  • Multi-chain scoring and ranking
  • Optional value write (torch control)

Usage:
  python miracle_gl_resolver.py
  python miracle_gl_resolver.py --json analysis1.json analysis2.json
  python miracle_gl_resolver.py --write 0x07
  python miracle_gl_resolver.py --no-write --verbose

Requirements:
  pip install pymem
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import struct
import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

TARGET_PROCESS   = "miracle_gl.exe"
TARGET_MODULE    = "miracle_gl.exe"
VALUE_OFFSET     = 0xAD       # [EAX + 0xAD] = light byte
TORCH_ON_VALUE   = 0x07
TORCH_BOOST      = 0x11       # optional boosted value

# Known signature at structure base (± search window)
SIGNATURE_WINDOW = 0x300      # bytes to scan around resolved base
SIGNATURES = [
    (b"Deprived",            0.50, "ASCII:Deprived"),
    (b"\xCE\x07\x00\x00",   0.30, "Pattern:CE07"),
    (b"\x00\x00\x80\x3F",   0.20, "FloatBlock:1.0f"),   # needs >= 4 occurrences
]
FLOAT_BLOCK_MIN_COUNT = 4

# Pointer chains: (module_offset, [hop_offsets], score_weight)
# Ranked best → worst from previous analysis.
# Last hop reaches EAX (structure base); VALUE_OFFSET is appended separately.
CANDIDATE_CHAINS = [
    # Rank 1 – shallow, uniform small offsets
    {
        "id":     "chain_A",
        "label":  "exe+0x254 → +0x18 → +0x3C → +0x0",
        "anchor": 0x254,
        "hops":   [0x18, 0x3C, 0x0],
        "prior_score": 1.0,
    },
    # Rank 2 – shallow but one large intermediate hop
    {
        "id":     "chain_B",
        "label":  "exe+0x18 → +0x234 → +0x48 → +0x0",
        "anchor": 0x18,
        "hops":   [0x234, 0x48, 0x0],
        "prior_score": 0.75,
    },
    # Rank 3 – deepest, two large intermediate hops
    {
        "id":     "chain_C",
        "label":  "exe+0x38 → +0x24C → +0x84 → +0x24 → +0x0",
        "anchor": 0x38,
        "hops":   [0x24C, 0x84, 0x24, 0x0],
        "prior_score": 0.50,
    },
]

# Validated bases from JSON runs (used for cross-reference scoring)
JSON_VALIDATED_BASES: list[int] = [
    0x217AECB8,   # shared across map1+map2, validated score 0.95
    0x217AFC90,   # session 2 secondary, also validated
]


# ─────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class ChainResult:
    chain_id:       str
    label:          str
    anchor:         int
    hops:           list[int]
    resolved_base:  Optional[int]  = None
    value_addr:     Optional[int]  = None
    current_value:  Optional[int]  = None
    sig_score:      float          = 0.0
    sig_matches:    list[str]      = field(default_factory=list)
    prior_score:    float          = 1.0
    final_score:    float          = 0.0
    error:          Optional[str]  = None

    @property
    def resolved(self) -> bool:
        return self.resolved_base is not None and self.error is None

    @property
    def value_ok(self) -> bool:
        return self.current_value is not None


@dataclass
class JsonAnalysis:
    source_file:      str
    value_offset:     int
    validated_bases:  list[int]
    all_bases:        list[int]
    shared_bases:     list[int]


# ─────────────────────────────────────────────
#  JSON LOADING
# ─────────────────────────────────────────────

def _parse_hex_list(lst: list) -> list[int]:
    out = []
    for v in lst:
        if isinstance(v, str) and v.startswith("0x"):
            out.append(int(v, 16))
        elif isinstance(v, int):
            out.append(v)
    return out


def load_json_analysis(path: Path) -> Optional[JsonAnalysis]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] Cannot load {path}: {e}")
        return None

    val_offset_raw = data.get("value_offset_hex", "0xAD")
    val_offset = int(val_offset_raw, 16) if isinstance(val_offset_raw, str) else val_offset_raw

    validated_bases: list[int] = []
    for vs in data.get("validated_structures", []):
        b = vs.get("base")
        if isinstance(b, str) and b.startswith("0x"):
            validated_bases.append(int(b, 16))
        elif isinstance(b, int):
            validated_bases.append(b)

    all_bases   = _parse_hex_list(data.get("all_structure_bases", []))
    shared      = _parse_hex_list(data.get("shared_structure_bases", []))

    return JsonAnalysis(
        source_file     = str(path),
        value_offset    = val_offset,
        validated_bases = validated_bases,
        all_bases       = all_bases,
        shared_bases    = shared,
    )


# ─────────────────────────────────────────────
#  PROCESS HELPERS
# ─────────────────────────────────────────────

def connect(process_name: str):
    """
    Returns (pymem_instance, module_base) or raises RuntimeError.
    Lazy-imports pymem so the rest of the file is importable without it.
    """
    try:
        import pymem
        import pymem.process
    except ImportError:
        raise RuntimeError(
            "pymem is not installed.\n"
            "  pip install pymem"
        )

    try:
        pm = pymem.Pymem(process_name)
    except Exception as e:
        raise RuntimeError(f"Cannot attach to '{process_name}': {e}")

    try:
        mod = pymem.process.module_from_name(pm.process_handle, TARGET_MODULE)
        base = mod.lpBaseOfDll
    except Exception as e:
        raise RuntimeError(f"Cannot locate module '{TARGET_MODULE}': {e}")

    return pm, base


def safe_read_uint(pm, addr: int) -> Optional[int]:
    """Read a 32-bit unsigned int, returning None on failure."""
    try:
        return pm.read_uint(addr)
    except Exception:
        return None


def safe_read_uchar(pm, addr: int) -> Optional[int]:
    """Read a byte, returning None on failure."""
    try:
        return pm.read_uchar(addr)
    except Exception:
        return None


def safe_read_bytes(pm, addr: int, size: int) -> Optional[bytes]:
    try:
        return pm.read_bytes(addr, size)
    except Exception:
        return None


def write_byte(pm, addr: int, value: int) -> bool:
    try:
        pm.write_uchar(addr, value & 0xFF)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────
#  POINTER CHAIN RESOLUTION
# ─────────────────────────────────────────────

def resolve_chain(pm, module_base: int, anchor: int, hops: list[int]) -> tuple[Optional[int], Optional[str]]:
    """
    Walk pointer chain from module_base + anchor through each hop.
    Returns (final_address, None) on success or (None, error_message).
    """
    addr = safe_read_uint(pm, module_base + anchor)
    if addr is None:
        return None, f"anchor read failed @ module+{anchor:#x}"

    for i, hop in enumerate(hops):
        if addr == 0:
            return None, f"null pointer at hop {i} (offset {hop:#x})"
        if addr < 0x10000:
            return None, f"kernel/null range at hop {i}: {addr:#x}"

        next_addr = safe_read_uint(pm, addr + hop)
        if next_addr is None:
            return None, f"read failed at hop {i}: [{addr:#x} + {hop:#x}]"
        addr = next_addr

    # addr is now EAX (structure base)
    if addr == 0 or addr < 0x10000:
        return None, f"resolved to invalid base: {addr:#x}"

    return addr, None


# ─────────────────────────────────────────────
#  SIGNATURE VALIDATION
# ─────────────────────────────────────────────

def validate_signature(pm, base: int) -> tuple[float, list[str]]:
    """
    Scan ± SIGNATURE_WINDOW around base for known structure signatures.
    Returns (score 0.0–1.0, list_of_matched_labels).
    """
    scan_start = max(0x10000, base - SIGNATURE_WINDOW)
    scan_size  = SIGNATURE_WINDOW * 2

    data = safe_read_bytes(pm, scan_start, scan_size)
    if data is None:
        return 0.0, ["READ_FAIL"]

    score   = 0.0
    matches: list[str] = []

    for pattern, weight, label in SIGNATURES:
        if label.startswith("FloatBlock"):
            count = data.count(pattern)
            if count >= FLOAT_BLOCK_MIN_COUNT:
                score += weight
                matches.append(f"{label}(x{count})")
        else:
            if pattern in data:
                score += weight
                matches.append(label)

    return round(min(score, 1.0), 3), matches


# ─────────────────────────────────────────────
#  SCORING
# ─────────────────────────────────────────────

def compute_final_score(result: ChainResult, json_bases: list[int]) -> float:
    """
    Deterministic score combining:
      - Resolution success          (prerequisite)
      - Signature confidence        40 pts
      - Prior structural analysis   30 pts
      - JSON cross-reference        20 pts
      - Depth penalty               -5 per hop beyond 2
      - Large offset penalty        -10 per hop > 0x100
    """
    if not result.resolved:
        return 0.0

    score = 0.0

    # Signature confidence (0.0–1.0 → up to 40 pts)
    score += result.sig_score * 40.0

    # Prior analysis ranking (from static analysis)
    score += result.prior_score * 30.0

    # JSON cross-reference: does this base appear in a validated run?
    if result.resolved_base and json_bases:
        # Allow ± 0x1000 tolerance for minor heap variation between runs
        for jb in json_bases:
            if abs(result.resolved_base - jb) < 0x1000:
                score += 20.0
                break

    # Depth penalty: each hop beyond 2 costs 5 pts
    depth_penalty = max(0, len(result.hops) - 2) * 5.0
    score -= depth_penalty

    # Large offset penalty
    large_offsets = sum(1 for h in result.hops if h > 0x100)
    score -= large_offsets * 10.0

    return round(max(0.0, score), 2)


# ─────────────────────────────────────────────
#  SIGNATURE SCAN FALLBACK
# ─────────────────────────────────────────────

def scan_for_structure(pm, module_base: int, scan_pages: int = 512) -> list[int]:
    """
    Fallback: brute-force scan for 'Deprived' in process heap pages near module.
    Returns list of candidate base addresses (offset-adjusted).
    scan_pages: number of 4KB pages to scan starting from module_base.
    """
    found: list[int] = []
    page_size = 0x1000
    target = b"Deprived"

    print(f"  [SCAN] Brute-force scanning {scan_pages} pages for 'Deprived'...")
    for i in range(scan_pages):
        addr = module_base + (i * page_size)
        chunk = safe_read_bytes(pm, addr, page_size)
        if chunk is None:
            continue
        offset = chunk.find(target)
        if offset != -1:
            candidate_base = addr + offset
            found.append(candidate_base)
            print(f"  [SCAN] Found 'Deprived' @ {candidate_base:#x}  (page {i})")

    # Also try known heap regions from JSON analysis
    for jb in JSON_VALIDATED_BASES:
        chunk = safe_read_bytes(pm, jb - 0x100, 0x300)
        if chunk and b"Deprived" in chunk:
            offset = chunk.find(b"Deprived")
            candidate = jb - 0x100 + offset
            if candidate not in found:
                found.append(candidate)
                print(f"  [SCAN] Found via JSON-hint @ {candidate:#x}")

    return found


# ─────────────────────────────────────────────
#  DISPLAY
# ─────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BLUE   = "\033[94m"

def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║       miracle_gl.exe  —  Pointer Chain Resolver              ║
║       instruction anchor: miracle_gl.exe+0x18664A            ║
║       operation:  mov [eax+0xAD], cl                         ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def print_json_summary(analyses: list[JsonAnalysis]):
    if not analyses:
        return
    print(f"{BOLD}── JSON Analysis Summary ─────────────────────────────────────{RESET}")
    for a in analyses:
        print(f"  Source      : {a.source_file}")
        print(f"  Offset      : {a.value_offset:#x}")
        if a.validated_bases:
            print(f"  Validated   : {', '.join(f'{b:#x}' for b in a.validated_bases)}")
        if a.shared_bases:
            print(f"  Shared bases: {', '.join(f'{b:#x}' for b in a.shared_bases)}")
        if a.all_bases:
            print(f"  All bases   : {', '.join(f'{b:#x}' for b in a.all_bases)}")
        print()


def print_chain_result(rank: int, r: ChainResult):
    status_color = GREEN if r.resolved else RED
    status_icon  = "✓" if r.resolved  else "✗"

    print(f"{BOLD}  #{rank}  {r.label}{RESET}")
    print(f"       anchor       : module + {r.anchor:#x}")
    print(f"       hops         : {' → '.join(f'+{h:#x}' for h in r.hops)}")

    if r.resolved:
        print(f"       base         : {status_color}{r.resolved_base:#x}{RESET}")
        print(f"       value addr   : {r.value_addr:#x}  (base + {VALUE_OFFSET:#x})")
        val_str = f"{r.current_value:#x}" if r.current_value is not None else "UNREADABLE"
        val_color = GREEN if r.current_value == TORCH_ON_VALUE else YELLOW
        print(f"       current value: {val_color}{val_str}{RESET}")
        sig_color = GREEN if r.sig_score >= 0.8 else (YELLOW if r.sig_score >= 0.4 else RED)
        print(f"       sig score    : {sig_color}{r.sig_score:.2f}{RESET}  {GRAY}({', '.join(r.sig_matches) or 'none'}){RESET}")
    else:
        print(f"       {RED}FAILED: {r.error}{RESET}")

    final_color = GREEN if r.final_score >= 70 else (YELLOW if r.final_score >= 40 else RED)
    print(f"       final score  : {final_color}{r.final_score:.1f} / 90.0{RESET}")
    print()


def print_recommendation(results: list[ChainResult]):
    resolved = [r for r in results if r.resolved]
    if not resolved:
        print(f"{RED}{BOLD}  No chains resolved. Recommendations:{RESET}")
        print(f"  1. Verify process is running and torch mechanic is active")
        print(f"  2. Run --scan to brute-force locate structure")
        print(f"  3. Re-run pointer scanner in Cheat Engine from instruction +0x18664A")
        return

    best = resolved[0]
    print(f"{GREEN}{BOLD}  Best chain: #{1}  {best.label}{RESET}")
    print(f"  Resolved base : {best.resolved_base:#x}")
    print(f"  Value address : {best.value_addr:#x}")
    print()
    print(f"  CE pointer path (append to pointer list):")
    print(f"  {CYAN}[miracle_gl.exe + {best.anchor:#x}]{RESET}", end="")
    for h in best.hops:
        print(f" → [{h:#x}]", end="")
    print(f" → [{VALUE_OFFSET:#x}]")
    print()


# ─────────────────────────────────────────────
#  WATCH MODE
# ─────────────────────────────────────────────

def watch_value(pm, value_addr: int, interval: float = 0.5):
    """
    Poll value_addr and print when it changes.
    Ctrl+C to exit.
    """
    print(f"\n{CYAN}[WATCH] Monitoring {value_addr:#x}  (Ctrl+C to stop){RESET}")
    last = None
    try:
        while True:
            current = safe_read_uchar(pm, value_addr)
            if current != last:
                ts = time.strftime("%H:%M:%S")
                color = GREEN if current == TORCH_ON_VALUE else YELLOW
                print(f"  {GRAY}[{ts}]{RESET}  {value_addr:#x}  =  {color}{current:#x}{RESET}")
                last = current
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{GRAY}[WATCH] Stopped.{RESET}")


# ─────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────

def run(
    json_paths:    list[Path],
    write_value:   Optional[int],
    do_scan:       bool,
    do_watch:      bool,
    verbose:       bool,
) -> int:
    banner()

    # ── 1. Load JSON analyses ──
    analyses: list[JsonAnalysis] = []
    for p in json_paths:
        if p.exists():
            a = load_json_analysis(p)
            if a:
                analyses.append(a)
        else:
            print(f"  {YELLOW}[WARN] JSON not found: {p}{RESET}")

    if analyses:
        print_json_summary(analyses)

    # Collect all validated bases from JSON for cross-reference
    all_json_bases = list(JSON_VALIDATED_BASES)
    for a in analyses:
        all_json_bases.extend(a.validated_bases)
        all_json_bases.extend(a.shared_bases)
    all_json_bases = list(dict.fromkeys(all_json_bases))  # deduplicate, preserve order

    # ── 2. Connect to process ──
    print(f"{BOLD}── Process Connection ────────────────────────────────────────{RESET}")
    try:
        pm, module_base = connect(TARGET_PROCESS)
        print(f"  {GREEN}Attached to {TARGET_PROCESS}{RESET}")
        print(f"  Module base  : {module_base:#x}")
    except RuntimeError as e:
        print(f"  {RED}ERROR: {e}{RESET}")
        return 1
    print()

    # ── 3. Optional: signature scan fallback ──
    scan_bases: list[int] = []
    if do_scan:
        print(f"{BOLD}── Signature Scan (fallback) ─────────────────────────────────{RESET}")
        scan_bases = scan_for_structure(pm, module_base)
        if not scan_bases:
            print(f"  {YELLOW}No structures found by scan{RESET}")
        print()

    # ── 4. Resolve each chain ──
    print(f"{BOLD}── Chain Resolution ──────────────────────────────────────────{RESET}")
    results: list[ChainResult] = []

    for chain in CANDIDATE_CHAINS:
        r = ChainResult(
            chain_id    = chain["id"],
            label       = chain["label"],
            anchor      = chain["anchor"],
            hops        = chain["hops"],
            prior_score = chain["prior_score"],
        )

        if verbose:
            print(f"  Trying {r.label}...")

        base, err = resolve_chain(pm, module_base, r.anchor, r.hops)

        if err:
            r.error = err
            if verbose:
                print(f"    {RED}✗ {err}{RESET}")
        else:
            r.resolved_base = base
            r.value_addr    = base + VALUE_OFFSET
            r.current_value = safe_read_uchar(pm, r.value_addr)
            r.sig_score, r.sig_matches = validate_signature(pm, base)
            if verbose:
                print(f"    {GREEN}✓ base={base:#x}  val={r.current_value:#x if r.current_value else 'ERR'}  sig={r.sig_score:.2f}{RESET}")

        r.final_score = compute_final_score(r, all_json_bases)
        results.append(r)

    # Sort by final score descending
    results.sort(key=lambda r: r.final_score, reverse=True)

    print()
    print(f"{BOLD}── Results (ranked) ──────────────────────────────────────────{RESET}")
    print()
    for i, r in enumerate(results, 1):
        print_chain_result(i, r)

    # ── 5. Recommendation ──
    print(f"{BOLD}── Recommendation ────────────────────────────────────────────{RESET}")
    print()
    print_recommendation(results)

    # ── 6. Optional scan-base report ──
    if scan_bases:
        print(f"{BOLD}── Scan Results ──────────────────────────────────────────────{RESET}")
        for sb in scan_bases:
            sscore, smatches = validate_signature(pm, sb)
            val = safe_read_uchar(pm, sb + VALUE_OFFSET)
            val_str = f"{val:#x}" if val is not None else "UNREADABLE"
            print(f"  {sb:#x}  sig={sscore:.2f}  val@+{VALUE_OFFSET:#x}={val_str}  matches={smatches}")
        print()

    # ── 7. Optional write ──
    best_resolved = next((r for r in results if r.resolved), None)

    if write_value is not None:
        print(f"{BOLD}── Write Operation ───────────────────────────────────────────{RESET}")
        if best_resolved is None:
            print(f"  {RED}No resolved chain available for write.{RESET}")
            return 1

        target_addr = best_resolved.value_addr
        print(f"  Writing {write_value:#x} → {target_addr:#x} (via {best_resolved.label})")
        confirm = input(f"  {YELLOW}Confirm? [y/N]: {RESET}").strip().lower()
        if confirm == "y":
            ok = write_byte(pm, target_addr, write_value)
            if ok:
                verify = safe_read_uchar(pm, target_addr)
                if verify == write_value:
                    print(f"  {GREEN}✓ Written and verified: {verify:#x}{RESET}")
                else:
                    print(f"  {YELLOW}Written but verify mismatch: read back {verify:#x}{RESET}")
            else:
                print(f"  {RED}Write failed (access denied or invalid address){RESET}")
        else:
            print(f"  {GRAY}Write cancelled.{RESET}")
        print()

    # ── 8. Optional watch ──
    if do_watch and best_resolved:
        watch_value(pm, best_resolved.value_addr)

    # ── 9. Output summary JSON ──
    output = {
        "process":       TARGET_PROCESS,
        "module_base":   f"{module_base:#x}",
        "value_offset":  f"{VALUE_OFFSET:#x}",
        "chains": [
            {
                "id":            r.chain_id,
                "label":         r.label,
                "resolved":      r.resolved,
                "base":          f"{r.resolved_base:#x}" if r.resolved_base else None,
                "value_addr":    f"{r.value_addr:#x}"    if r.value_addr    else None,
                "current_value": f"{r.current_value:#x}" if r.current_value is not None else None,
                "sig_score":     r.sig_score,
                "sig_matches":   r.sig_matches,
                "final_score":   r.final_score,
                "error":         r.error,
            }
            for r in results
        ],
        "scan_bases": [f"{b:#x}" for b in scan_bases],
    }

    out_path = Path("resolver_output.json")
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"{GRAY}[INFO] Full results written to {out_path}{RESET}")

    return 0 if best_resolved else 1


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="miracle_gl.exe pointer chain resolver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python miracle_gl_resolver.py
  python miracle_gl_resolver.py --json analysis1.json analysis2.json
  python miracle_gl_resolver.py --write 0x07
  python miracle_gl_resolver.py --write 0x11 --verbose
  python miracle_gl_resolver.py --scan
  python miracle_gl_resolver.py --watch
        """
    )
    parser.add_argument(
        "--json", nargs="*", default=[],
        metavar="FILE",
        help="JSON analysis files to cross-reference (default: auto-discover *.json)"
    )
    parser.add_argument(
        "--write", default=None,
        metavar="HEX_VALUE",
        help="Write a byte to the resolved value address (e.g. 0x07 for torch ON)"
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Fallback: brute-force scan for 'Deprived' signature in process memory"
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="After resolving, poll the value address and print changes (Ctrl+C to stop)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print each chain resolution step"
    )

    args = parser.parse_args()

    # Resolve JSON paths
    json_paths: list[Path] = []
    if args.json:
        json_paths = [Path(p) for p in args.json]
    else:
        # Auto-discover JSON files in cwd
        json_paths = sorted(Path(".").glob("*.json"))
        if json_paths:
            print(f"  {GRAY}[INFO] Auto-discovered JSON: {', '.join(str(p) for p in json_paths)}{RESET}")

    # Parse write value
    write_value: Optional[int] = None
    if args.write:
        try:
            write_value = int(args.write, 0)
        except ValueError:
            print(f"  {RED}ERROR: --write value must be hex or int (e.g. 0x07){RESET}")
            sys.exit(1)

    sys.exit(run(
        json_paths  = json_paths,
        write_value = write_value,
        do_scan     = args.scan,
        do_watch    = args.watch,
        verbose     = args.verbose,
    ))


if __name__ == "__main__":
    main()