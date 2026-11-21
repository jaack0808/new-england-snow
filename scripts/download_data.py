"""Download GHCN-Daily station metadata and per-station records for New England.

Only stations whose inventory shows snowfall (SNOW) observations spanning the
whole study window are downloaded. Files are cached in data/raw/, so re-running
only fetches what is missing.

Usage:  python scripts/download_data.py [--force]
"""
import argparse
import sys
import time

import requests

import config as C

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "new-england-snow-analysis (github.com/jaack0808)"


def fetch(url, dest, force=False, retries=4):
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with SESSION.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            tmp.replace(dest)
            return True
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            wait = 5 * attempt
            print(f"  retry {attempt}/{retries} for {url} in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)


def parse_stations(path):
    """Fixed-width ghcnd-stations.txt -> dict id -> metadata."""
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            sid = line[0:11]
            out[sid] = {
                "id": sid,
                "lat": float(line[12:20]),
                "lon": float(line[21:30]),
                "elev_m": float(line[31:37]),
                "state": line[38:40].strip(),
                "name": line[41:71].strip(),
                "hcn": line[76:79].strip() == "HCN",
            }
    return out


def parse_inventory(path):
    """Fixed-width ghcnd-inventory.txt -> dict (id, element) -> (first, last)."""
    out = {}
    with open(path) as fh:
        for line in fh:
            out[(line[0:11], line[31:35])] = (int(line[36:40]), int(line[41:45]))
    return out


def candidate_stations(stations, inventory):
    picks = []
    for sid, meta in stations.items():
        if not sid.startswith("US") or meta["state"] not in C.NEW_ENGLAND:
            continue
        span = inventory.get((sid, "SNOW"))
        if not span:
            continue
        first, last = span
        if first <= C.INVENTORY_FIRST_YEAR_MAX and last >= C.INVENTORY_LAST_YEAR_MIN:
            picks.append(sid)
    return sorted(picks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download everything")
    args = ap.parse_args()

    meta_dir = C.DATA_DIR / "meta"
    st_path, inv_path = meta_dir / "ghcnd-stations.txt", meta_dir / "ghcnd-inventory.txt"
    print("Fetching station list and inventory ...")
    fetch(C.STATIONS_URL, st_path, args.force)
    fetch(C.INVENTORY_URL, inv_path, args.force)

    stations = parse_stations(st_path)
    inventory = parse_inventory(inv_path)
    picks = candidate_stations(stations, inventory)
    print(f"{len(picks)} New England stations have SNOW records from <= "
          f"{C.INVENTORY_FIRST_YEAR_MAX} to >= {C.INVENTORY_LAST_YEAR_MIN}")

    failed = []
    for i, sid in enumerate(picks, 1):
        url = C.BY_STATION_URL.format(station=sid)
        try:
            new = fetch(url, C.RAW_DIR / f"{sid}.csv.gz", args.force)
            print(f"  [{i:3d}/{len(picks)}] {sid} {stations[sid]['name']:<30} "
                  f"{'downloaded' if new else 'cached'}")
        except requests.RequestException as exc:
            print(f"  [{i:3d}/{len(picks)}] {sid} FAILED: {exc}", file=sys.stderr)
            failed.append(sid)

    with open(meta_dir / "candidates.txt", "w") as fh:
        fh.write("\n".join(s for s in picks if s not in failed) + "\n")
    if failed:
        print(f"{len(failed)} downloads failed: {' '.join(failed)}", file=sys.stderr)
        if len(failed) > len(picks) / 4:
            sys.exit(1)


if __name__ == "__main__":
    main()
