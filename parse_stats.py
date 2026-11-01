#!/usr/bin/env python3
"""
parse_stats.py — collect the metrics that matter from every results/*/*/stats.txt
into one CSV you can plot or paste into a table.

Usage:
    python3 parse_stats.py [results_dir] [out.csv]

Columns (per run):
    tag, config, insts, cycles, ipc, l2_accesses, l2_misses, l2_miss_rate, l2_mpki,
    l2_replacements, compressed_fills, uncompressed_fills, frac_fills_compressed,
    predictor_flips, pred_penalty, pred_avoided_miss, pred_avoidable_miss,
    data_expansions, data_contractions, decompressions, compressions,
    avg_comp_size_bits, host_seconds

Notes:
  * With -F (fast-forward) the detailed CPU is "system.switch_cpus"; without it,
    "system.cpu". Both are handled.
  * Fields that a configuration does not produce (e.g. compressor stats under
    --l2-compression=none) are left empty.
  * If gem5 dumped stats more than once into the same file (e.g. periodic
    dumps), only the LAST dump block is used.
"""
import csv
import os
import re
import sys

RESULTS = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = sys.argv[2] if len(sys.argv) > 2 else "summary.csv"

# stat-name -> column; first match wins; names are matched as full stat keys
WANT = {
    "insts": [r"simInsts"],
    "cycles": [r"system\.switch_cpus\.numCycles", r"system\.cpu\.numCycles"],
    "ipc": [r"system\.switch_cpus\.ipc", r"system\.cpu\.ipc"],
    "l2_accesses": [r"system\.l2\.overallAccesses::total"],
    "l2_misses": [r"system\.l2\.overallMisses::total"],
    "l2_miss_rate": [r"system\.l2\.overallMissRate::total"],
    "l2_replacements": [r"system\.l2\.replacements"],
    "compressed_fills": [r"system\.l2\.compressedFills"],
    "uncompressed_fills": [r"system\.l2\.uncompressedFills"],
    "predictor_flips": [r"system\.l2\.predictorFlips"],
    "pred_penalty": [r"system\.l2\.predPenaltyEvents"],
    "pred_avoided_miss": [r"system\.l2\.predAvoidedMissEvents"],
    "pred_avoidable_miss": [r"system\.l2\.predAvoidableMissEvents"],
    "data_expansions": [r"system\.l2\.dataExpansions"],
    "data_contractions": [r"system\.l2\.dataContractions"],
    "decompressions": [r"system\.l2\.compressor\.decompressions"],
    "compressions": [r"system\.l2\.compressor\.compressions"],
    "avg_comp_size_bits": [r"system\.l2\.compressor\.avgCompressionSizeBits"],
    "host_seconds": [r"hostSeconds"],
}
DERIVED = ["l2_mpki", "frac_fills_compressed"]
COLUMNS = ["tag", "config"] + list(WANT.keys()) + DERIVED

LINE_RE = re.compile(r"^(\S+)\s+(-?[\d.]+(?:e[+-]?\d+)?|nan|inf)\b")


def last_dump(text):
    """Return only the final '---------- Begin ... End ----------' block."""
    blocks = text.split("---------- Begin Simulation Statistics ----------")
    return blocks[-1] if len(blocks) > 1 else text


def parse_stats(path):
    with open(path) as f:
        text = last_dump(f.read())
    raw = {}
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            raw.setdefault(m.group(1), m.group(2))
    row = {}
    for col, patterns in WANT.items():
        val = ""
        for pat in patterns:
            rx = re.compile("^" + pat + "$")
            for k, v in raw.items():
                if rx.match(k):
                    val = v
                    break
            if val != "":
                break
        row[col] = val
    # derived
    try:
        row["l2_mpki"] = f"{1000.0 * float(row['l2_misses']) / float(row['insts']):.4f}"
    except (ValueError, ZeroDivisionError):
        row["l2_mpki"] = ""
    try:
        c = float(row["compressed_fills"] or 0)
        u = float(row["uncompressed_fills"] or 0)
        row["frac_fills_compressed"] = f"{c / (c + u):.4f}" if (c + u) > 0 else ""
    except ValueError:
        row["frac_fills_compressed"] = ""
    return row


def main():
    rows = []
    for tag in sorted(os.listdir(RESULTS)):
        tdir = os.path.join(RESULTS, tag)
        if not os.path.isdir(tdir):
            continue
        for cfg in sorted(os.listdir(tdir)):
            sp = os.path.join(tdir, cfg, "stats.txt")
            if os.path.isfile(sp) and os.path.getsize(sp) > 0:
                row = parse_stats(sp)
                row["tag"], row["config"] = tag, cfg
                rows.append(row)
            elif os.path.isdir(os.path.join(tdir, cfg)):
                print(f"warning: no stats.txt in {tdir}/{cfg} (run failed or still running?)",
                      file=sys.stderr)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {len(rows)} rows to {OUT}")
    # quick on-screen table
    if rows:
        print(f"{'tag':28} {'config':14} {'IPC':>7} {'L2 MPKI':>9} {'miss%':>7} {'cmpFill%':>9} {'flips':>6} {'expand':>7}")
        for r in rows:
            def fmt(k, nd=3, pct=False):
                try:
                    v = float(r[k]) * (100 if pct else 1)
                    return f"{v:.{nd}f}"
                except (ValueError, TypeError):
                    return "-"
            print(f"{r['tag'][:28]:28} {r['config'][:14]:14} {fmt('ipc'):>7} {fmt('l2_mpki',2):>9} "
                  f"{fmt('l2_miss_rate',1,True):>7} {fmt('frac_fills_compressed',1,True):>9} "
                  f"{r['predictor_flips'] or '-':>6} {r['data_expansions'] or '-':>7}")


if __name__ == "__main__":
    main()
