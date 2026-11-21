#!/usr/bin/env bash
# Run the full pipeline offline on synthetic data in a temp folder.
# Checks that analysis and page building work; says nothing about real snow.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
export SNOW_DATA_DIR="$tmp/data" SNOW_SITE_DIR="$tmp/site"
python3 tests/make_fake_data.py > /dev/null
python3 scripts/analyze.py | tail -n 4
python3 scripts/build_site.py
test -s "$tmp/site/index.html"
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$tmp/site/results.json"
echo "Smoke test passed ($tmp)"
