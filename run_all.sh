#!/usr/bin/env bash
# Reproduce the whole report locally: download -> analyze -> build.
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/download_data.py
python3 scripts/analyze.py
python3 scripts/build_site.py
echo
echo "Preview with:  python3 -m http.server -d site 8000   then open http://localhost:8000"
