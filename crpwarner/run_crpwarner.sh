#!/bin/bash
# Run CRPWarner (via Gigahorse) on every runtime bytecode file in a directory.
#
# Usage:
#   ./run_crpwarner.sh <gigahorse_dir> <hex_dir> <results.json> [jobs] [timeout_seconds]
#
# Example:
#   ./run_crpwarner.sh RugPull/gigahorse bytecode/clean results_clean.json 12 300
#
# Requirements: Souffle 2.3, the Gigahorse souffle-addon functors (see README.md),
# and the CRPWarner repository (https://github.com/CRPWarner/RugPull).
set -euo pipefail
GH_DIR=$(realpath "$1"); HEX_DIR=$(realpath "$2"); OUT=$(realpath -m "$3")
JOBS=${4:-$(nproc)}; TIMEOUT=${5:-300}
cd "$GH_DIR"
python3 ./gigahorse.py -C ./clients/crpwarner.dl -j "$JOBS" -T "$TIMEOUT" \
    -r "$OUT" -w "/tmp/crpwarner_work_$$" "$HEX_DIR"/*.hex | tee "${OUT%.json}.log"
rm -rf "/tmp/crpwarner_work_$$"
