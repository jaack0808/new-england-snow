"""Generate a small synthetic GHCN-Daily dataset for offline testing.

The files mimic NOAA's formats exactly (fixed-width station list and inventory,
headerless by_station CSVs), so the whole pipeline can be exercised without
network access. The numbers are random and mean nothing.

Usage:  SNOW_DATA_DIR=/tmp/fake python tests/make_fake_data.py
then run analyze.py and build_site.py with the same SNOW_DATA_DIR.
"""
import gzip
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import config as C  # noqa: E402

rng = np.random.default_rng(0)
STATES = ["CT", "MA", "ME", "NH", "RI", "VT"]


def write_station(path, sid, start, end, base_mean, drift):
    d = date(start, 1, 1)
    lines = []
    depth = 0.0
    while d <= date(end, 12, 31):
        m = d.month
        season = d.year if m >= 7 else d.year - 1
        cold = {12: 1, 1: 1.2, 2: 1.1, 3: 0.8, 11: 0.35, 4: 0.3, 10: 0.03, 5: 0.02}.get(m, 0)
        p_snow = 0.13 * cold
        mean_mm = base_mean * 25.4 / 18 * (1 + drift * (season - 1980) / 80)
        snow = int(rng.gamma(1.2, mean_mm / 1.2)) if rng.random() < p_snow else 0
        depth = max(0.0, depth * (0.93 if cold > 0.5 else 0.6) + snow * 0.6 - (5 if cold < 0.5 else 0))
        missing = rng.random() < 0.02 or (sid.endswith("9") and 1950 <= d.year <= 1958)
        if not missing:
            q = "X" if rng.random() < 0.001 else ""
            ds = d.strftime("%Y%m%d")
            lines.append(f"{sid},{ds},SNOW,{snow},,{q},7,0700")
            if d.year >= 1948:
                lines.append(f"{sid},{ds},SNWD,{int(depth)},,,7,0700")
            lines.append(f"{sid},{ds},PRCP,{snow // 10},,,7,0700")
        d += timedelta(days=1)
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    meta = C.DATA_DIR / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    st_lines, inv_lines = [], []
    for i in range(18):
        sid = f"USC00{190000 + i * 37:06d}"
        state = STATES[i % 6]
        lat, lon = 41.3 + rng.random() * 5.5, -73.4 + rng.random() * 4.5
        start = 1931 if i % 5 else 1950   # some start too late -> excluded
        end = 2026
        name = f"FAKE STATION {i:02d}"
        st_lines.append(f"{sid:<11} {lat:8.4f} {lon:9.4f} {200.0:6.1f} {state:<2} {name:<30} "
                        f"{'   '} {'HCN' if i % 3 == 0 else '   '} {'':5}")
        inv_lines.append(f"{sid:<11} {lat:8.4f} {lon:9.4f} SNOW {start} {end}")
        inv_lines.append(f"{sid:<11} {lat:8.4f} {lon:9.4f} SNWD {max(start, 1948)} {end}")
        write_station(C.RAW_DIR / f"{sid}.csv.gz", sid, start, end,
                      base_mean=40 + 60 * rng.random(), drift=rng.normal(-0.1, 0.15))
        print("wrote", sid)
    (meta / "ghcnd-stations.txt").write_text("\n".join(st_lines) + "\n")
    (meta / "ghcnd-inventory.txt").write_text("\n".join(inv_lines) + "\n")


if __name__ == "__main__":
    if "SNOW_DATA_DIR" not in os.environ:
        sys.exit("Set SNOW_DATA_DIR to a scratch folder so fake data never mixes with real data.")
    main()
