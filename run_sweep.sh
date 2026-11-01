#!/usr/bin/env bash
# run_sweep.sh — run one workload under the four L2 configurations.
#
# Usage:
#   ./run_sweep.sh <gem5_root> <binary> "<binary args>" <tag> [ff_insts] [max_insts]
#
# Example:
#   ./run_sweep.sh ~/gem5Project ./chase "320 small 20" chase_320_small 5000000 50000000
#
# Produces results/<tag>/<config>/stats.txt plus a .log per config.
#
# The four configurations (everything else identical):
#   stock_256k_4w : plain set-associative L2, 256 kB, 4-way, NO compressor.
#                   This is the honest uncompressed baseline.
#   never         : variable-segment L2 (8 tags/set, physical data = 4 lines/set
#                   = 256 kB), compression policy forced OFF.
#                   Validation: its L2 miss count should match stock_256k_4w
#                   almost exactly. If it doesn't, the capacity accounting is wrong.
#   always        : same L2, every fill compressed with FPC.
#   adaptive      : same L2, the global predictor decides (the project's mechanism).
#
# NOTE on sizes: in this fork "--l2_size=512kB --l2_assoc=8" means
#   512kB/64B/8 = 1024 sets x 8 TAGS, but only assoc/2 = 4 lines of physical
#   DATA per set, i.e. 256 kB of real storage. That is what the ECE565 report
#   calls "256 KB L2".
set -euo pipefail

GEM5=${1:?gem5 root}
BIN=${2:?workload binary}
ARGS=${3:-}
TAG=${4:?result tag}
FF=${5:-5000000}        # instructions to fast-forward with AtomicSimpleCPU (skips init, warms caches)
MAXI=${6:-50000000}     # detailed O3 instructions to measure after the switch

BUILD=$GEM5/build/ECE565-X86/gem5.opt
SE=$GEM5/configs/example/se.py
OUT=results/$TAG
mkdir -p "$OUT"

common=(
  --cpu-type=O3CPU --caches --l2cache
  --l1d_size=64kB --l1i_size=32kB --cacheline_size=64
  --mem-size=2GB
  -F "$FF" --maxinsts="$MAXI"
)

run() {
  local name=$1; shift
  echo "[$(date +%H:%M:%S)] $TAG / $name ..."
  "$BUILD" --outdir="$OUT/$name" "$SE" --cmd="$BIN" --options="$ARGS" \
      "${common[@]}" "$@" > "$OUT/$name.log" 2>&1 \
    || { echo "  FAILED — see $OUT/$name.log"; return 1; }
  # one-line summary so you can watch progress
  awk '/^simInsts/{i=$2} /switch_cpus.numCycles|system.cpu.numCycles/{c=$2}
       /l2.overallMisses::total/{m=$2} /hostSeconds/{h=$2}
       END{printf "  insts=%s cycles=%s L2misses=%s host=%ss\n", i, c, m, h}' \
       "$OUT/$name/stats.txt"
}

run stock_256k_4w --l2_size=256kB --l2_assoc=4 --l2-compression=none
run never         --l2_size=512kB --l2_assoc=8 --l2-compression=never
run always        --l2_size=512kB --l2_assoc=8 --l2-compression=always
run adaptive      --l2_size=512kB --l2_assoc=8 --l2-compression=adaptive

echo "done: $OUT"
