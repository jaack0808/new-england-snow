"""Turn raw GHCN-Daily station files into season totals and period comparisons.

Reads data/raw/*.csv.gz (from download_data.py) and writes:
  data/results/station_seasons.csv  one row per station, metric and winter
  data/results/stations.csv         per-station period means and tests
  data/results/results.json         everything the report needs

Usage:  python scripts/analyze.py
"""
import calendar
import json
import sys
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

import config as C
from download_data import parse_stations

COLS = ["id", "date", "element", "value", "mflag", "qflag", "sflag", "obstime"]


# ---------------------------------------------------------------------------
# Station file -> per-season metrics
# ---------------------------------------------------------------------------
def load_station(path):
    df = pd.read_csv(
        path, header=None, names=COLS, usecols=["date", "element", "value", "qflag"],
        dtype={"date": np.int64, "element": str, "value": np.int64, "qflag": str},
        compression="gzip",
    )
    df = df[df.element.isin(["SNOW", "SNWD"])]
    # Drop values that failed any NOAA quality check, and the missing sentinel.
    df = df[df.qflag.isna() & (df.value != -9999) & (df.value >= 0)]
    df = df.drop(columns="qflag")
    df["year"] = df.date // 10000
    df["month"] = (df.date // 100) % 100
    df = df[df.month.isin(C.SEASON_MONTHS)]
    df["season"] = np.where(df.month >= 7, df.year, df.year - 1)
    return df.drop_duplicates(["date", "element"])


def complete_seasons(d):
    """Return the set of seasons whose core/shoulder months are complete enough."""
    counts = d.groupby(["season", "month"]).size().unstack(fill_value=0)
    ok = pd.Series(True, index=counts.index)
    for m, max_missing in ([(m, C.CORE_MAX_MISSING) for m in C.CORE_MONTHS]
                           + [(m, C.SHOULDER_MAX_MISSING) for m in C.SHOULDER_MONTHS]):
        have = counts[m] if m in counts.columns else pd.Series(0, index=counts.index)
        cal_year = counts.index + (1 if m < 7 else 0)
        dim = np.array([calendar.monthrange(int(y), m)[1] for y in cal_year])
        ok &= have.values >= dim - max_missing
    return set(counts.index[ok])


def season_metrics(df):
    """Dict metric -> pd.Series(season -> value) for one station."""
    out = {}
    snow = df[df.element == "SNOW"]
    if len(snow):
        good = complete_seasons(snow)
        s = snow[snow.season.isin(good)]
        out["snowfall"] = s.groupby("season").value.sum() / 25.4
        out["snow_days"] = (s.value >= C.ONE_INCH_MM).groupby(s.season).sum().astype(float)
    snwd = df[df.element == "SNWD"]
    if len(snwd):
        good = complete_seasons(snwd)
        s = snwd[snwd.season.isin(good)]
        out["cover_days"] = (s.value >= C.ONE_INCH_MM).groupby(s.season).sum().astype(float)
    return out


def qualifies(series, base_decades=None):
    yrs = series.index.values
    for dec in (base_decades or C.BASE_DECADES):
        if ((yrs >= dec) & (yrs < dec + 10)).sum() < C.MIN_SEASONS_PER_BASE_DECADE:
            return False
    for dec in C.RECENT_DECADES:
        if ((yrs >= dec) & (yrs < dec + 10)).sum() < C.MIN_SEASONS_PER_RECENT_DECADE:
            return False
    return True


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------
def period(series, start, end):
    return series[(series.index >= start) & (series.index <= end)].dropna()


def bootstrap_diff(a, b, n, rng):
    """95% CI of mean(b) - mean(a) by resampling winters within each period."""
    a, b = np.asarray(a), np.asarray(b)
    da = rng.choice(a, (n, len(a))).mean(axis=1)
    db = rng.choice(b, (n, len(b))).mean(axis=1)
    lo, hi = np.percentile(db - da, [2.5, 97.5])
    return float(lo), float(hi)


def r(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), nd)


def analyze_metric(metric, per_station, meta, rng):
    m = C.METRICS[metric]
    included = {sid: s for sid, s in per_station.items()
                if qualifies(s, m.get("required_base_decades"))}
    if len(included) < 3:
        return None, []

    rows = []
    for sid, s in included.items():
        a = period(s, C.BASE_START, C.BASE_END)
        b = period(s, C.RECENT_START, C.RECENT_END)
        t_p = stats.ttest_ind(b, a, equal_var=False).pvalue
        u_p = stats.mannwhitneyu(b, a, alternative="two-sided").pvalue
        rows.append({
            "station": sid, "metric": metric, **{k: meta[sid][k] for k in
                                                 ("name", "state", "lat", "lon", "elev_m", "hcn")},
            "n_base": len(a), "n_recent": len(b),
            "base_mean": a.mean(), "recent_mean": b.mean(),
            "change": b.mean() - a.mean(),
            "pct_change": 100 * (b.mean() / a.mean() - 1) if a.mean() > 0 else np.nan,
            "welch_p": t_p, "mannwhitney_p": u_p,
        })
    st = pd.DataFrame(rows).sort_values("pct_change")

    # Regional index: each winter as % of that station's own 1940-99 average,
    # then averaged across stations. This stops snowy mountain stations from
    # dominating and makes stations with gaps comparable.
    base = st.set_index("station").base_mean
    wide = pd.DataFrame(included).sort_index()
    wide = wide[wide.index >= C.BASE_START]
    pct = 100 * wide / base
    n_rep = pct.notna().sum(axis=1)
    index = pct.mean(axis=1).where(n_rep >= C.MIN_STATION_SHARE_FOR_INDEX * len(included))
    index = index.dropna()
    abs_scale = base.mean() / 100  # % of baseline -> "typical station" units
    roll = index.rolling(C.ROLLING_WINDOW, center=False, min_periods=C.ROLLING_WINDOW).mean()

    a = period(index, C.BASE_START, C.BASE_END)
    b = period(index, C.RECENT_START, C.RECENT_END)
    diff = b.mean() - a.mean()
    ci = bootstrap_diff(a, b, C.N_BOOTSTRAP, rng)
    welch = stats.ttest_ind(b, a, equal_var=False)
    mw = stats.mannwhitneyu(b, a, alternative="two-sided")
    trend_win = period(index, C.BASE_START, C.RECENT_END)
    ts = stats.theilslopes(trend_win.values, trend_win.index.values)
    kt = stats.kendalltau(trend_win.index.values, trend_win.values)

    n_lower = int((st.change < 0).sum())
    n_higher = int((st.change > 0).sum())
    sig_lower = int(((st.change < 0) & (st.welch_p < C.ALPHA)).sum())
    sig_higher = int(((st.change > 0) & (st.welch_p < C.ALPHA)).sum())
    sign_p = stats.binomtest(n_lower, n_lower + n_higher, 0.5).pvalue if n_lower + n_higher else None

    decades = []
    for dec in C.BASE_DECADES + C.RECENT_DECADES + [2020]:
        v = period(index, dec, dec + 9)
        if len(v):
            decades.append({"decade": dec, "label": f"{dec}s", "n": len(v),
                            "index": r(v.mean()), "abs": r(v.mean() * abs_scale),
                            "period": "base" if dec < 2000 else ("recent" if dec < 2020 else "after")})

    # How often were winters big or meagre at each station?
    pooled = {}
    for name, (s0, s1) in {"base": (C.BASE_START, C.BASE_END),
                           "recent": (C.RECENT_START, C.RECENT_END)}.items():
        p = pct[(pct.index >= s0) & (pct.index <= s1)].stack()
        pooled[name] = {"big": r(100 * (p >= 150).mean()), "meagre": r(100 * (p <= 50).mean()),
                        "below_avg": r(100 * (p < 100).mean())}

    # Sensitivity: alternative baselines for the comparison
    sens = []
    for s0, s1 in [(1940, 1999), (1940, 1969), (1950, 1999), (1960, 1999), (1970, 1999), (1980, 1999)]:
        base2 = period(index, s0, s1)
        if len(base2) >= 10:
            lo, hi = bootstrap_diff(base2, b, C.N_BOOTSTRAP, rng)
            sens.append({"baseline": f"{s0}–{s1}",
                         "start": s0, "end": s1, "diff": r(b.mean() - base2.mean()),
                         "pct": r(100 * (b.mean() / base2.mean() - 1)),
                         "ci": [r(lo), r(hi)], "significant": bool(hi < 0 or lo > 0)})

    after = period(index, C.RECENT_END + 1, 9999)
    by_state = (st.groupby("state")["pct_change"].agg(["mean", "count"]).reset_index()
                .rename(columns={"mean": "pct", "count": "n"}))
    by_state["state_name"] = by_state.state.map(C.STATE_NAMES)

    summary = {
        "metric": metric, **{k: v for k, v in m.items() if k != "required_base_decades"},
        "required_from": (m.get("required_base_decades") or C.BASE_DECADES)[0],
        "n_stations": len(included),
        "base_index": r(a.mean()), "recent_index": r(b.mean()),
        "diff": r(diff), "ci": [r(ci[0]), r(ci[1])],
        "significant_lower": bool(ci[1] < 0), "significant_higher": bool(ci[0] > 0),
        "welch_p": r(welch.pvalue, 4), "mannwhitney_p": r(mw.pvalue, 4),
        "base_abs": r(a.mean() * abs_scale), "recent_abs": r(b.mean() * abs_scale),
        "abs_scale": abs_scale,
        "n_base_seasons": len(a), "n_recent_seasons": len(b),
        "trend_per_decade": r(ts.slope * 10, 2),
        "trend_ci": [r(ts.low_slope * 10, 2), r(ts.high_slope * 10, 2)],
        "trend_p": r(kt.pvalue, 4),
        "stations_lower": n_lower, "stations_higher": n_higher,
        "stations_sig_lower": sig_lower, "stations_sig_higher": sig_higher,
        "sign_test_p": r(sign_p, 4),
        "median_station_pct": r(st["pct_change"].median()),
        "decades": decades, "pooled": pooled, "sensitivity": sens,
        "after": {"n": len(after), "index": r(after.mean()) if len(after) else None,
                  "first": int(after.index.min()) if len(after) else None,
                  "last": int(after.index.max()) if len(after) else None},
        "by_state": json.loads(by_state.round(1).to_json(orient="records")),
        "series": {
            "season": [int(x) for x in index.index],
            "index": [r(x) for x in index.values],
            "rolling": [r(x) for x in roll.reindex(index.index).values],
            "n_stations": [int(n_rep[x]) for x in index.index],
        },
        "stations": json.loads(st.round(4).to_json(orient="records")),
    }
    return summary, rows


def season_label(s):
    return f"{s}–{str(s + 1)[-2:]}"


# ---------------------------------------------------------------------------
def main():
    meta_path = C.DATA_DIR / "meta" / "ghcnd-stations.txt"
    if not meta_path.exists():
        sys.exit("No station metadata. Run scripts/download_data.py first.")
    meta = parse_stations(meta_path)
    files = sorted(C.RAW_DIR.glob("*.csv.gz"))
    if not files:
        sys.exit("No station files in data/raw/. Run scripts/download_data.py first.")

    per_metric = {k: {} for k in C.METRICS}
    long_rows = []
    latest = 0
    for i, f in enumerate(files, 1):
        sid = f.name.split(".")[0]
        if sid not in meta:
            continue
        try:
            metrics = season_metrics(load_station(f))
        except Exception as exc:  # a corrupt file should not kill the run
            print(f"  skip {sid}: {exc}", file=sys.stderr)
            continue
        for k, s in metrics.items():
            per_metric[k][sid] = s
            latest = max(latest, int(s.index.max()) if len(s) else 0)
            long_rows += [{"station": sid, "metric": k, "season": int(y), "value": round(v, 2)}
                          for y, v in s.items()]
        print(f"  [{i:3d}/{len(files)}] {sid} parsed")

    C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(long_rows).to_csv(C.RESULTS_DIR / "station_seasons.csv", index=False)

    rng = np.random.default_rng(C.RANDOM_SEED)
    results, all_rows = {}, []
    for metric in C.METRICS:
        summary, rows = analyze_metric(metric, per_metric[metric], meta, rng)
        if summary:
            results[metric] = summary
            all_rows += rows
            print(f"{metric}: {summary['n_stations']} stations, "
                  f"{summary['base_index']}% -> {summary['recent_index']}% "
                  f"(diff {summary['diff']}, 95% CI {summary['ci']})")
        else:
            print(f"{metric}: not enough qualifying stations", file=sys.stderr)
    if C.PRIMARY_METRIC not in results:
        sys.exit("Primary metric could not be computed.")

    pd.DataFrame(all_rows).to_csv(C.RESULTS_DIR / "stations.csv", index=False)
    out = {
        "generated": date.today().isoformat(),
        "n_files": len(files),
        "latest_season": latest,
        "periods": {"base": [C.BASE_START, C.BASE_END], "recent": [C.RECENT_START, C.RECENT_END]},
        "thresholds": {
            "core_max_missing": C.CORE_MAX_MISSING, "shoulder_max_missing": C.SHOULDER_MAX_MISSING,
            "min_base_decade": C.MIN_SEASONS_PER_BASE_DECADE,
            "min_recent_decade": C.MIN_SEASONS_PER_RECENT_DECADE,
            "first_year_max": C.INVENTORY_FIRST_YEAR_MAX, "last_year_min": C.INVENTORY_LAST_YEAR_MIN,
            "bootstrap": C.N_BOOTSTRAP,
        },
        "metrics": results,
    }
    with open(C.RESULTS_DIR / "results.json", "w") as fh:
        json.dump(out, fh, indent=1, allow_nan=False)
    print(f"Wrote {C.RESULTS_DIR / 'results.json'}")


if __name__ == "__main__":
    main()
