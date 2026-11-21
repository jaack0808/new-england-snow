"""Build the GitHub Pages report from data/results/results.json.

Every number and every sentence that depends on the data is computed here,
so the headline always matches the analysis that produced it.

Usage:  python scripts/build_site.py
Output: site/index.html (+ site/results.json, site/stations.csv)
"""
import html
import json
import shutil
import sys

import config as C

REPO_URL = "https://github.com/jaack0808/new-england-snow"


def esc(x):
    return html.escape(str(x))


def fmt_pct(x, signed=True):
    if x is None:
        return "n/a"
    x = round(x)
    s = ("0%" if x == 0 else f"{x:+d}%") if signed else f"{abs(x):d}%"
    return s.replace("-", "−")


def fmt_pts(x):
    if x is None:
        return "n/a"
    return f"{x:+.1f}".replace("-", "\u2212")


def fmt_p(p):
    if p is None:
        return "n/a"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}" if p < 0.1 else f"p = {p:.2f}"


def pct_change(m):
    return 100 * (m["recent_index"] / m["base_index"] - 1)


def season(s):
    return f"{s}–{str(s + 1)[-2:]}"


def ranked_decades(m):
    decs = [d for d in m["decades"] if d["period"] != "after"]
    return sorted(decs, key=lambda d: d["index"], reverse=True)


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------
def build_story(res):
    M = res["metrics"]
    P = M[C.PRIMARY_METRIC]
    cover = M.get("cover_days")
    sdays = M.get("snow_days")
    pc = pct_change(P)
    yes = P["significant_lower"]
    s = {"verdict": "Yes" if yes else "No", "yes": yes}

    inches = (f"about {P['base_abs']:.0f} inches a winter at a typical station in 1940–1999, "
              f"versus {P['recent_abs']:.0f} inches in 2000–2019")
    ci = f"95% confidence interval {fmt_pts(P['ci'][0])} to {fmt_pts(P['ci'][1])} points"
    if yes:
        s["dek"] = (f"New England really did get less snow. Across {P['n_stations']} long-record "
                    f"weather stations, 2000–2019 averaged {fmt_pct(pc, False)} less snowfall than "
                    f"1940–1999 ({inches}). Your uncle wasn't just being nostalgic.")
    elif pc > 0:
        s["dek"] = (f"About as much snow fell in 2000–2019 as in 1940–1999, or slightly more "
                    f"({fmt_pct(pc)}). Across {P['n_stations']} long-record New England weather "
                    f"stations: {inches}. On snowfall alone, the good old days weren't snowier.")
    else:
        s["dek"] = (f"Snowfall in 2000–2019 was only {fmt_pct(pc, False)} lower than in "
                    f"1940–1999 across {P['n_stations']} long-record New England stations ({inches}). "
                    f"That gap is smaller than the normal swing from one winter to the next and "
                    f"can't be told apart from chance. On snowfall alone, the good old days "
                    f"weren't clearly snowier.")

    # Supporting evidence, one bullet per argument -------------------------
    ev = []
    ev.append(
        f"<strong>The regional average:</strong> each winter is expressed as a percentage of "
        f"that station's own 1940–1999 average, and the percentages are averaged across "
        f"stations. 2000–2019 came out at <strong>{P['recent_index']:.0f}%</strong> of the "
        f"1940–1999 level ({P['base_index']:.0f}%). Difference: {fmt_pts(P['diff'])} points "
        f"({ci}; Welch's t-test {fmt_p(P['welch_p'])}, Mann–Whitney {fmt_p(P['mannwhitney_p'])}).")
    ev.append(
        f"<strong>Station by station:</strong> {P['stations_lower']} of {P['n_stations']} stations "
        f"recorded less snow in 2000–2019 and {P['stations_higher']} recorded more. Only "
        f"{P['stations_sig_lower']} had a decrease large enough to be statistically significant "
        f"on its own; {P['stations_sig_higher']} had a significant increase. The median station "
        f"changed by {fmt_pct(P['median_station_pct'])}.")
    trend_sig = P["trend_p"] is not None and P["trend_p"] < C.ALPHA
    ev.append(
        f"<strong>Long-term trend:</strong> a robust (Theil–Sen) trend line through every "
        f"winter from 1940–41 to 2019–20 slopes {fmt_pts(P['trend_per_decade'])} points per "
        f"decade (Mann–Kendall {fmt_p(P['trend_p'])}), which is "
        f"{'a statistically significant' if trend_sig else 'not a statistically significant'} trend.")
    rk = ranked_decades(P)
    pos = {d["decade"]: i + 1 for i, d in enumerate(rk)}
    ev.append(
        f"<strong>Decade by decade:</strong> the snowiest decade was the {rk[0]['label']} "
        f"({rk[0]['index']:.0f}% of the 1940–99 average) and the least snowy was the "
        f"{rk[-1]['label']} ({rk[-1]['index']:.0f}%). Of the {len(rk)} decades, the 2000s ranked "
        f"{ordinal(pos.get(2000, 0))} and the 2010s ranked {ordinal(pos.get(2010, 0))}.")
    pb, pr = P["pooled"]["base"], P["pooled"]["recent"]
    ev.append(
        f"<strong>Big and meagre winters:</strong> a winter with at least 150% of a station's "
        f"normal snow happened {pb['big']:.1f}% of the time in 1940–1999 and {pr['big']:.1f}% of "
        f"the time in 2000–2019. Meagre winters (50% or less of normal): {pb['meagre']:.1f}% "
        f"vs {pr['meagre']:.1f}%.")
    s["evidence"] = ev

    # Other ways of reading "less snow" ------------------------------------
    other = []
    for key, m in (("snow_days", sdays), ("cover_days", cover)):
        if not m:
            continue
        p = pct_change(m)
        sig = ("a statistically significant decrease" if m["significant_lower"] else
               "a statistically significant increase" if m["significant_higher"] else
               "within the range of chance")
        other.append(
            f"<strong>{esc(m['label'])}:</strong> {m['base_abs']:.0f} → {m['recent_abs']:.0f} "
            f"days a winter at a typical station ({fmt_pct(p)}; 95% CI {fmt_pts(m['ci'][0])} to "
            f"{fmt_pts(m['ci'][1])} points; {sig}; {m['n_stations']} stations).")
    s["other"] = other

    # Where the uncle's feeling could come from ---------------------------
    why = []
    child = next((x for x in P["sensitivity"] if x["start"] == 1940 and x["end"] == 1969), None)
    if child:
        if child["significant"] and child["diff"] < 0:
            why.append(
                f"<strong>His childhood really was snowier.</strong> Born in 1939, he grew up in the "
                f"1940s to 1960s. Compared with just 1940–1969, 2000–2019 had "
                f"{fmt_pct(child['pct'], False)} less snowfall, and that gap <em>is</em> statistically "
                f"significant (95% CI {fmt_pts(child['ci'][0])} to {fmt_pts(child['ci'][1])} points). "
                f"Measured against the winters he grew up with, he had a point.")
        else:
            why.append(
                f"<strong>His childhood wasn't clearly snowier either.</strong> Born in 1939, he grew up "
                f"in the 1940s to 1960s. Even compared with just 1940–1969, 2000–2019 differed "
                f"by {fmt_pct(child['pct'])}, which is not statistically significant "
                f"(95% CI {fmt_pts(child['ci'][0])} to {fmt_pts(child['ci'][1])} points).")
    if cover and cover["significant_lower"] and not yes:
        why.append(
            "<strong>Snow stopped sticking around.</strong> Snowfall held up, but the number of "
            "days with snow on the ground fell significantly. Fewer white weeks can feel like "
            "less snow even when the same amount falls, because it melts faster between storms.")
    elif cover and cover["significant_lower"] and yes:
        why.append(
            "<strong>And it didn't stay as long.</strong> Days with snow on the ground fell too, "
            "so recent winters were less white as well as less snowy.")
    after = P["after"]
    if after["n"] and after["index"] is not None:
        low = after["index"] < P["recent_index"]
        why.append(
            f"<strong>The most recent winters.</strong> He complained up to 2024. The "
            f"{after['n']} winters from {season(after['first'])} to {season(after['last'])} "
            f"(outside the formal comparison) averaged {after['index']:.0f}% of the 1940–99 level"
            + (", lower than 2000–2019, which could easily colour his memory of what's 'normal'."
               if low else ", which doesn't point to a recent drought of snow either."))
    why.append(
        "<strong>Memory isn't a rain gauge.</strong> Big storms and childhood winters stick in "
        "memory, and drifts look deeper when you're four feet tall. Comparing against measurements "
        "rather than recollections is the whole point of this exercise.")
    s["why"] = why
    return s


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def tiles(res):
    P = res["metrics"][C.PRIMARY_METRIC]
    out = [(fmt_pct(pct_change(P)), "change in snowfall, 2000–19 vs 1940–99"),
           (f"{P['base_abs']:.0f} → {P['recent_abs']:.0f} in",
            "typical station's seasonal snowfall"),
           (f"{P['stations_lower']} / {P['n_stations']}", "stations with less snow")]
    cv = res["metrics"].get("cover_days")
    if cv:
        out.append((fmt_pct(pct_change(cv)), "change in days with snow on the ground"))
    return "\n".join(
        f'<div class="tile"><div class="tile-num">{esc(n)}</div><div class="tile-lbl">{esc(l)}</div></div>'
        for n, l in out)


def li(items):
    return "\n".join(f"<li>{x}</li>" for x in items)


def sens_rows(res):
    rows = []
    for key, m in res["metrics"].items():
        for x in m["sensitivity"]:
            rows.append(f"<tr><td>{esc(m['short'])}</td><td>{esc(x['baseline'])}</td>"
                        f"<td>{fmt_pct(x['pct'])}</td><td>{fmt_pts(x['ci'][0])} to {fmt_pts(x['ci'][1])}</td>"
                        f"<td>{'yes' if x['significant'] else 'no'}</td></tr>")
    return "\n".join(rows)


def page(res):
    story = build_story(res)
    P = res["metrics"][C.PRIMARY_METRIC]
    T = res["thresholds"]
    for m in res["metrics"].values():   # names come from NOAA files; escape before embedding
        for st in m["stations"]:
            st["name"] = esc(st["name"].title())
    data_json = json.dumps(res, separators=(",", ":")).replace("</", "<\\/")
    metric_buttons = "\n".join(
        f'<button type="button" role="tab" data-metric="{k}" aria-selected="{str(k == C.PRIMARY_METRIC).lower()}">'
        f'{esc(m["label"])}</button>' for k, m in res["metrics"].items())
    verdict_cls = "yes" if story["yes"] else "no"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Was my uncle right? Snow in New England, then and now</title>
<meta name="description" content="Did New England get less snow in 2000-2019 than in 1940-1999? An analysis of NOAA GHCN-Daily station data.">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="">
<style>
:root {{
  color-scheme: light;
  --surface-0:#f6f5f2; --surface-1:#fcfcfb; --border:#e3e2dd; --grid:#ecebe7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7974;
  --base:#2a78d6; --recent:#eb6834; --context:#b8b7b1;
  --div-neg:#d03b3b; --div-neg-deep:#8f1f1f; --div-mid:#f0efec; --div-pos:#2a78d6; --div-pos-deep:#104281;
  --yes:#0ca30c; --no:#d03b3b;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    color-scheme: dark;
    --surface-0:#121211; --surface-1:#1a1a19; --border:#33332f; --grid:#2a2a27;
    --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#929189;
    --base:#3987e5; --recent:#d95926; --context:#5c5b56;
    --div-neg:#e66767; --div-neg-deep:#f5a3a3; --div-mid:#383835; --div-pos:#3987e5; --div-pos-deep:#9ec5f4;
    --yes:#0ca30c; --no:#e66767;
  }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--surface-0); color:var(--text-primary);
  font:17px/1.6 "Iowan Old Style","Charter","Georgia",serif; }}
.wrap {{ max-width:860px; margin:0 auto; padding:2.5rem 1.25rem 4rem; }}
h1,h2,h3,.tile-num,.verdict,nav,button,table,.kicker,figcaption,.fine {{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif; }}
.kicker {{ text-transform:uppercase; letter-spacing:.08em; font-size:.78rem; color:var(--text-secondary); }}
h1 {{ font-size:clamp(1.8rem,4.5vw,2.6rem); line-height:1.15; margin:.3rem 0 1.4rem; }}
h2 {{ font-size:1.35rem; margin:3rem 0 .6rem; }}
h3 {{ font-size:1.05rem; margin:1.8rem 0 .4rem; }}
.answer {{ display:flex; gap:1.4rem; align-items:center; background:var(--surface-1);
  border:1px solid var(--border); border-radius:12px; padding:1.4rem 1.5rem; }}
.verdict {{ font-size:3.4rem; font-weight:800; line-height:1; letter-spacing:-.02em; }}
.verdict.yes {{ color:var(--yes); }} .verdict.no {{ color:var(--no); }}
.answer p {{ margin:0; font-size:1.08rem; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:.8rem; margin:1.2rem 0 0; }}
.tile {{ background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:.9rem 1rem; }}
.tile-num {{ font-size:1.55rem; font-weight:700; font-variant-numeric:tabular-nums; }}
.tile-lbl {{ font-size:.85rem; color:var(--text-secondary); font-family:-apple-system,"Segoe UI",sans-serif; line-height:1.35; }}
ul.ev {{ padding-left:1.1rem; }} ul.ev li {{ margin:.55rem 0; }}
figure {{ margin:1.4rem 0; background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:1rem 1rem .6rem; }}
figcaption {{ font-size:.85rem; color:var(--text-secondary); margin-top:.4rem; line-height:1.45; }}
figure .ttl {{ font-weight:650; font-size:.98rem; color:var(--text-primary); font-family:-apple-system,"Segoe UI",sans-serif; margin:0 0 .3rem; }}
.chart {{ width:100%; height:360px; }}
#map {{ height:440px; border-radius:8px; }}
nav.metrics {{ position:sticky; top:0; z-index:500; background:var(--surface-0); padding:.6rem 0;
  display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; border-bottom:1px solid var(--border); }}
nav.metrics span {{ font-size:.82rem; color:var(--text-secondary); margin-right:.3rem; }}
nav.metrics button {{ font-size:.85rem; border:1px solid var(--border); background:var(--surface-1);
  color:var(--text-primary); border-radius:999px; padding:.35rem .8rem; cursor:pointer; }}
nav.metrics button[aria-selected="true"] {{ background:var(--text-primary); color:var(--surface-1); border-color:var(--text-primary); }}
table {{ border-collapse:collapse; width:100%; font-size:.84rem; font-variant-numeric:tabular-nums; }}
th,td {{ text-align:left; padding:.35rem .5rem; border-bottom:1px solid var(--grid); }}
th {{ color:var(--text-secondary); font-weight:600; }}
td.num, th.num {{ text-align:right; }}
details {{ margin:1rem 0; }} summary {{ cursor:pointer; font-family:-apple-system,"Segoe UI",sans-serif; font-weight:600; }}
.legend {{ display:flex; gap:1rem; flex-wrap:wrap; font:13px -apple-system,"Segoe UI",sans-serif; color:var(--text-secondary); margin:.4rem 0; }}
.key {{ display:inline-block; width:14px; height:10px; border-radius:2px; margin-right:.35rem; vertical-align:middle; }}
.ramp {{ display:inline-block; width:160px; height:10px; border-radius:2px; vertical-align:middle; margin:0 .4rem; }}
.fine {{ font-size:.8rem; color:var(--text-muted); }}
a {{ color:var(--base); }}
code {{ font-size:.88em; }}
@media (max-width:600px) {{ .answer {{ flex-direction:column; align-items:flex-start; }} .chart {{ height:300px; }} }}
</style>
</head>
<body>
<div class="wrap">
<div class="kicker">NOAA GHCN-Daily · {P['n_stations']} New England stations · 1940–{res['latest_season'] + 1}</div>
<h1>Was my uncle right that New England gets less snow than it used to?</h1>

<div class="answer">
  <div class="verdict {verdict_cls}">{story['verdict']}</div>
  <p>{story['dek']}</p>
</div>
<div class="tiles">{tiles(res)}</div>

<h2>The question</h2>
<p>My uncle (1939–2024) spent most of his life in New England and complained more than once that
there's less snow nowadays. Taking him at his word, the test is whether winters in the
<strong>first two decades of the 21st century (2000–2019)</strong> had less snow than winters in
the <strong>last six decades of the 20th century (1940–1999)</strong>. Winters are labelled by the year
they start, so "1940" is the winter of 1940–41.</p>
<p>"Less snow" most naturally means less snow <em>falling</em>, so seasonal snowfall decides the headline.
Two other readings are checked too: how many days had a decent snowfall, and how many days had snow
on the ground.</p>

<h2>The evidence</h2>
<ul class="ev">{li(story['evidence'])}</ul>
{"<h3>Other ways to measure “less snow”</h3><ul class='ev'>" + li(story['other']) + "</ul>" if story['other'] else ""}

<nav class="metrics" role="tablist" aria-label="Metric shown in the charts below">
  <span>Charts show:</span>
  {metric_buttons}
</nav>

<figure>
  <div class="ttl" id="ts-title"></div>
  <div class="legend">
    <span><i class="key" style="background:var(--base)"></i>1940–1999 winters</span>
    <span><i class="key" style="background:var(--recent)"></i>2000–2019 winters</span>
    <span><i class="key" style="background:var(--context)"></i>after 2019 (context only)</span>
    <span><i class="key" style="background:var(--text-primary);height:2px"></i>10-winter average</span>
    <span><i class="key" style="border-top:2px dashed var(--text-secondary);height:0;background:none"></i>period average</span>
  </div>
  <div id="ts" class="chart"></div>
  <figcaption>Each bar is one winter, as a percentage of the stations' own 1940–1999 averages (100% = a normal
  winter by 20th-century standards). Hover for the value, approximate amount at a typical station, and how
  many stations reported that winter.</figcaption>
</figure>

<figure>
  <div class="ttl" id="dec-title"></div>
  <div id="dec" class="chart" style="height:300px"></div>
  <figcaption>Average of the regional index for each decade of winters. Blue decades make up the 1940–1999
  baseline, orange decades the 2000–2019 comparison.</figcaption>
</figure>

<figure>
  <div class="ttl" id="map-title"></div>
  <div class="legend"><span>less<i class="ramp" id="ramp"></i>more</span><span id="map-note"></span></div>
  <div id="map"></div>
  <figcaption>Each circle is a weather station, coloured by its change from 1940–1999 to 2000–2019. Click a
  station for details.</figcaption>
</figure>

<figure>
  <div class="ttl" id="db-title"></div>
  <div class="legend">
    <span><i class="key" style="background:var(--base);border-radius:50%;width:10px"></i>1940–1999 average</span>
    <span><i class="key" style="background:var(--recent);border-radius:50%;width:10px"></i>2000–2019 average</span>
  </div>
  <div id="db" class="chart"></div>
  <figcaption>Every station's two period averages, sorted by percentage change. A bold station name means its
  change is statistically significant on its own (Welch's t-test, p &lt; 0.05).</figcaption>
</figure>

<figure>
  <div class="ttl" id="sens-title"></div>
  <div id="sens" class="chart" style="height:280px"></div>
  <figcaption>Does the answer depend on which 20th-century years count as "the old days"? Each bar compares
  2000–2019 with a different baseline; whiskers are 95% bootstrap confidence intervals. A whisker that
  crosses zero means the difference can't be told apart from chance.</figcaption>
</figure>

<details>
  <summary>Station table (current metric)</summary>
  <div style="overflow-x:auto"><table id="station-table"></table></div>
</details>

<h2>So why would he say that?</h2>
<ul class="ev">{li(story['why'])}</ul>

<h2>Method</h2>
<ol>
  <li><strong>Data.</strong> Daily snowfall (<code>SNOW</code>) and snow depth (<code>SNWD</code>) from NOAA's
  <a href="https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily">Global
  Historical Climatology Network – Daily</a>, downloaded per station from NCEI. Values that failed any of
  NOAA's quality checks (non-blank Q flag) are dropped.</li>
  <li><strong>Stations.</strong> All US stations in CT, MA, ME, NH, RI and VT whose inventory shows snowfall
  records from {T['first_year_max']} or earlier through {T['last_year_min']} or later ({res['n_files']} downloaded).
  For each measure, a station is kept only if it has at least {T['min_base_decade']} usable winters in every
  decade of the baseline (1940s–1990s; 1950s–1990s for snow depth, which wasn't routinely recorded before
  about 1948) and at least {T['min_recent_decade']} in each of the 2000s and 2010s. This stops the result
  from being driven by stations that only cover part of either period.</li>
  <li><strong>Winters.</strong> A season runs October through May. It counts only if December–March each
  miss no more than {T['core_max_missing']} days and November and April no more than
  {T['shoulder_max_missing']}; missing shoulder-month days count as no snow.</li>
  <li><strong>Regional index.</strong> Each station-winter is divided by that station's own 1940–1999 average,
  and the percentages are averaged across the stations reporting that winter (at least half of them).
  Snowy mountain stations and coastal stations therefore count equally. Inches and days quoted for a
  "typical station" are the index multiplied by the average baseline across stations.</li>
  <li><strong>Tests.</strong> The 2000–2019 vs 1940–1999 difference in the index gets a 95% bootstrap confidence
  interval ({T['bootstrap']:,} resamples of winters within each period), plus Welch's t-test and Mann–Whitney U.
  The headline is "Yes" only if the whole interval is below zero. Per-station Welch tests, a sign test, and a
  Theil–Sen / Mann–Kendall trend for 1940–2019 are reported as supporting evidence.</li>
</ol>

<details>
  <summary>Sensitivity to the choice of baseline (all measures)</summary>
  <div style="overflow-x:auto"><table>
  <thead><tr><th>Measure</th><th>Baseline winters</th><th class="num">2000–19 change</th><th>95% CI (points)</th><th>Significant?</th></tr></thead>
  <tbody>{sens_rows(res)}</tbody></table></div>
</details>

<h3>Caveats</h3>
<ul>
  <li>Stations move, observers change, and observing practice has shifted over 80 years (for example, how often
  the snowboard is cleared). GHCN-Daily is quality-controlled but not homogenised for these changes.</li>
  <li>Requiring long, nearly complete records leaves a modest number of stations, mostly cooperative-observer and
  airport sites, which may not represent the high mountains or the far north evenly.</li>
  <li>Neighbouring stations share the same storms, so they aren't independent. The sign test across stations
  overstates certainty for that reason. The regional index test, which treats each winter as one observation,
  is the main test.</li>
  <li>Twenty winters is a short sample for something as variable as New England snowfall: one or two
  blockbuster winters can move the 2000–2019 average noticeably.</li>
</ul>

<p class="fine">Generated {esc(res['generated'])} from NOAA GHCN-Daily. Code, data download and analysis:
<a href="{REPO_URL}">{REPO_URL.replace('https://', '')}</a>. Machine-readable results:
<a href="results.json">results.json</a> · <a href="stations.csv">stations.csv</a>.</p>
</div>

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script id="results" type="application/json">{data_json}</script>
<script>
{SCRIPT}
</script>
</body>
</html>
"""


SCRIPT = r"""
const RES = JSON.parse(document.getElementById('results').textContent);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let current = Object.keys(RES.metrics)[0];
const seasonLbl = s => `${s}–${String(s + 1).slice(-2)}`;
const fmtSigned = x => (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(0) + '%';
const unitOf = m => m.unit === 'in' ? 'in' : 'days';
const unitLong = m => m.unit === 'in' ? 'inches' : 'days';

function baseLayout(extra) {
  return Object.assign({
    margin: {l: 52, r: 12, t: 8, b: 40},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {family: '-apple-system,BlinkMacSystemFont,Segoe UI,Inter,Roboto,sans-serif', size: 12, color: css('--text-secondary')},
    xaxis: {gridcolor: css('--grid'), linecolor: css('--border'), zeroline: false, tickcolor: css('--border')},
    yaxis: {gridcolor: css('--grid'), linecolor: css('--border'), zeroline: false},
    hoverlabel: {bgcolor: css('--surface-1'), bordercolor: css('--border'), font: {color: css('--text-primary')}},
    showlegend: false, bargap: 0.12,
  }, extra || {});
}
const CONFIG = {displayModeBar: false, responsive: true};

function periodOf(s) {
  if (s >= RES.periods.base[0] && s <= RES.periods.base[1]) return 'base';
  if (s >= RES.periods.recent[0] && s <= RES.periods.recent[1]) return 'recent';
  return 'after';
}
const colorOf = p => p === 'base' ? css('--base') : p === 'recent' ? css('--recent') : css('--context');

function drawSeries(m) {
  const S = m.series;
  document.getElementById('ts-title').textContent = `${m.label}: regional index, winter by winter`;
  const absTxt = S.index.map(v => v == null ? '' : `${(v * m.abs_scale).toFixed(0)} ${unitOf(m)}`);
  const bars = {
    type: 'bar', x: S.season, y: S.index, marker: {color: S.season.map(s => colorOf(periodOf(s)))},
    customdata: S.season.map((s, i) => [seasonLbl(s), absTxt[i], S.n_stations[i]]),
    hovertemplate: '<b>%{y:.0f}%</b> of 1940–99 average<br>%{customdata[0]} winter<br>≈ %{customdata[1]} at a typical station<br>%{customdata[2]} stations reporting<extra></extra>',
  };
  const roll = {type: 'scatter', mode: 'lines', x: S.season, y: S.rolling, line: {color: css('--text-primary'), width: 2},
    hovertemplate: '10-winter average: <b>%{y:.0f}%</b><extra></extra>', connectgaps: false};
  const P = RES.periods;
  const seg = (a, b, v, name) => ({type: 'scatter', mode: 'lines', x: [a - 0.4, b + 0.4], y: [v, v],
    line: {color: css('--text-secondary'), width: 2, dash: 'dash'}, hovertemplate: `${name} average: <b>${v.toFixed(0)}%</b><extra></extra>`});
  const ymax = Math.max(...S.index.filter(v => v != null)) * 1.12;
  const lay = baseLayout({
    yaxis: {gridcolor: css('--grid'), ticksuffix: '%', range: [0, ymax], zeroline: false},
    xaxis: {gridcolor: 'rgba(0,0,0,0)', linecolor: css('--border'), dtick: 10},
    hovermode: 'closest',
    annotations: [
      {x: (P.base[0] + P.base[1]) / 2, y: ymax, yanchor: 'top', text: `1940–99 average: ${m.base_index.toFixed(0)}%`, showarrow: false, font: {color: css('--text-primary'), size: 12}},
      {x: (P.recent[0] + P.recent[1]) / 2, y: ymax, yanchor: 'top', text: `2000–19 average: ${m.recent_index.toFixed(0)}%`, showarrow: false, font: {color: css('--text-primary'), size: 12}},
    ],
  });
  Plotly.react('ts', [bars, roll, seg(P.base[0], P.base[1], m.base_index, '1940–99'),
    seg(P.recent[0], P.recent[1], m.recent_index, '2000–19')], lay, CONFIG);
}

function drawDecades(m) {
  document.getElementById('dec-title').textContent = `${m.label}: average by decade`;
  const D = m.decades;
  Plotly.react('dec', [{
    type: 'bar', x: D.map(d => d.label), y: D.map(d => d.index),
    marker: {color: D.map(d => colorOf(d.period))},
    text: D.map(d => d.index.toFixed(0) + '%'), textposition: 'outside', cliponaxis: false,
    textfont: {color: css('--text-primary')},
    customdata: D.map(d => [d.abs, d.n]),
    hovertemplate: `<b>%{y:.0f}%</b> of 1940–99 average<br>≈ %{customdata[0]} ${unitOf(m)} at a typical station<br>%{customdata[1]} winters<extra>%{x}</extra>`,
  }], baseLayout({
    yaxis: {gridcolor: css('--grid'), ticksuffix: '%', rangemode: 'tozero', range: [0, Math.max(...D.map(d => d.index)) * 1.15]},
    xaxis: {linecolor: css('--border')},
    shapes: [{type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100, line: {color: css('--text-muted'), width: 1, dash: 'dot'}}],
  }), CONFIG);
}

function divColor(p) {
  // diverging: red = less, blue = more, neutral grey midpoint; saturates at +/-30%
  const t = Math.max(-1, Math.min(1, p / 30));
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mid = hex(css('--div-mid'));
  const [a, b] = t < 0 ? [hex(css('--div-neg')), hex(css('--div-neg-deep'))] : [hex(css('--div-pos')), hex(css('--div-pos-deep'))];
  const k = Math.abs(t);
  const pole = k < 0.66 ? a.map((v, i) => mid[i] + (v - mid[i]) * (k / 0.66)) : a.map((v, i) => v + (b[i] - v) * ((k - 0.66) / 0.34));
  return `rgb(${pole.map(Math.round).join(',')})`;
}

let map, layer;
function drawMap(m) {
  document.getElementById('map-title').textContent = `${m.label}: change at each station, 2000–19 vs 1940–99`;
  document.getElementById('ramp').style.background =
    `linear-gradient(90deg, ${divColor(-30)}, ${divColor(-15)}, ${divColor(0)}, ${divColor(15)}, ${divColor(30)})`;
  document.getElementById('map-note').textContent = 'colour saturates at ±30%';
  if (typeof L === 'undefined') { document.getElementById('map').textContent = 'Map library failed to load.'; return; }
  if (!map) {
    map = L.map('map', {scrollWheelZoom: false}).setView([43.9, -71.3], 6);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 12}).addTo(map);
  }
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);
  const u = unitOf(m);
  m.stations.forEach(s => {
    const c = L.circleMarker([s.lat, s.lon], {radius: 8, color: css('--surface-1'), weight: 2, fillColor: divColor(s.pct_change), fillOpacity: 1});
    const pop = document.createElement('div');
    const b = document.createElement('b'); b.innerHTML = s.name; pop.appendChild(b);  // name pre-escaped server-side
    pop.appendChild(document.createElement('br'));
    pop.appendChild(document.createTextNode(`${s.state} · ${s.station} · ${Math.round(s.elev_m * 3.281)} ft`));
    pop.appendChild(document.createElement('br'));
    pop.appendChild(document.createTextNode(`${s.base_mean.toFixed(1)} → ${s.recent_mean.toFixed(1)} ${u} (${fmtSigned(s.pct_change)})`));
    pop.appendChild(document.createElement('br'));
    pop.appendChild(document.createTextNode(`Welch p = ${s.welch_p.toFixed(3)}; winters: ${s.n_base} + ${s.n_recent}`));
    c.bindPopup(pop); c.bindTooltip(`${fmtSigned(s.pct_change)}`, {direction: 'top'});
    c.addTo(layer);
  });
}

function drawDumbbell(m) {
  document.getElementById('db-title').textContent = `${m.label}: every station, before and after`;
  const st = [...m.stations].sort((a, b) => b.pct_change - a.pct_change);
  const names = st.map(s => (s.welch_p < 0.05 ? `<b>${s.name}</b>` : s.name) + `, ${s.state}`);
  const segX = [], segY = [];
  st.forEach((s, i) => { segX.push(s.base_mean, s.recent_mean, null); segY.push(names[i], names[i], null); });
  const u = unitOf(m);
  const hov = st.map(s => [s.base_mean.toFixed(1), s.recent_mean.toFixed(1), fmtSigned(s.pct_change), s.welch_p.toFixed(3)]);
  const tmpl = `1940–99: <b>%{customdata[0]} ${u}</b><br>2000–19: <b>%{customdata[1]} ${u}</b><br>change %{customdata[2]} (p = %{customdata[3]})<extra>%{y}</extra>`;
  const dot = (key, col) => ({type: 'scatter', mode: 'markers', x: st.map(s => s[key]), y: names,
    marker: {size: 10, color: col, line: {color: css('--surface-1'), width: 2}}, customdata: hov, hovertemplate: tmpl});
  const h = Math.max(320, st.length * 22 + 70);
  document.getElementById('db').style.height = h + 'px';
  Plotly.react('db', [
    {type: 'scatter', mode: 'lines', x: segX, y: segY, line: {color: css('--text-muted'), width: 2}, hoverinfo: 'skip'},
    dot('base_mean', css('--base')), dot('recent_mean', css('--recent')),
  ], baseLayout({
    margin: {l: 210, r: 16, t: 8, b: 40}, height: h, hovermode: 'closest',
    xaxis: {gridcolor: css('--grid'), title: {text: `${m.label} (${unitLong(m)} per winter)`}, rangemode: 'tozero'},
    yaxis: {automargin: true, tickfont: {size: 11, color: css('--text-secondary')}, autorange: 'reversed', gridcolor: 'rgba(0,0,0,0)'},
  }), CONFIG);
}

function drawSensitivity(m) {
  document.getElementById('sens-title').textContent = `${m.label}: 2000–19 compared with different baselines`;
  const S = m.sensitivity;
  Plotly.react('sens', [{
    type: 'bar', orientation: 'h', y: S.map(s => s.baseline), x: S.map(s => s.diff),
    marker: {color: S.map(s => s.diff < 0 ? css('--div-neg') : css('--div-pos'))},
    error_x: {type: 'data', symmetric: false, array: S.map(s => s.ci[1] - s.diff), arrayminus: S.map(s => s.diff - s.ci[0]), color: css('--text-secondary'), thickness: 1.5, width: 5},
    customdata: S.map(s => [s.ci[0], s.ci[1], s.significant ? 'significant' : 'not significant']),
    hovertemplate: '<b>%{x:+.1f} points</b> vs %{y}<br>95% CI %{customdata[0]} to %{customdata[1]}<br>%{customdata[2]}<extra></extra>',
  }], baseLayout({
    margin: {l: 90, r: 16, t: 8, b: 40},
    xaxis: {gridcolor: css('--grid'), zeroline: true, zerolinecolor: css('--text-muted'), title: {text: 'Change in regional index (percentage points)'}},
    yaxis: {autorange: 'reversed', gridcolor: 'rgba(0,0,0,0)'},
  }), CONFIG);
}

function drawTable(m) {
  const t = document.getElementById('station-table');
  t.replaceChildren();
  const u = unitOf(m);
  const head = ['Station', 'State', 'ID', `1940–99 (${u})`, `2000–19 (${u})`, 'Change', 'Welch p', 'Winters'];
  const tr = document.createElement('tr');
  head.forEach((h, i) => { const th = document.createElement('th'); th.textContent = h; if (i > 2) th.className = 'num'; tr.appendChild(th); });
  const thead = document.createElement('thead'); thead.appendChild(tr); t.appendChild(thead);
  const tb = document.createElement('tbody');
  [...m.stations].sort((a, b) => a.pct_change - b.pct_change).forEach(s => {
    const r = document.createElement('tr');
    const tmp = document.createElement('span'); tmp.innerHTML = s.name;  // decode pre-escaped name
    [tmp.textContent, s.state, s.station, s.base_mean.toFixed(1), s.recent_mean.toFixed(1), fmtSigned(s.pct_change),
     s.welch_p.toFixed(3), `${s.n_base} + ${s.n_recent}`].forEach((v, i) => {
      const td = document.createElement('td'); td.textContent = v; if (i > 2) td.className = 'num'; r.appendChild(td);
    });
    tb.appendChild(r);
  });
  t.appendChild(tb);
}

function render() {
  const m = RES.metrics[current];
  document.querySelectorAll('nav.metrics button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.metric === current)));
  if (typeof Plotly !== 'undefined') { drawSeries(m); drawDecades(m); drawDumbbell(m); drawSensitivity(m); }
  drawMap(m); drawTable(m);
}
document.querySelectorAll('nav.metrics button').forEach(b => b.addEventListener('click', () => { current = b.dataset.metric; render(); }));
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
render();
"""


def main():
    src = C.RESULTS_DIR / "results.json"
    if not src.exists():
        sys.exit("No results.json. Run scripts/analyze.py first.")
    res = json.loads(src.read_text())
    C.SITE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, C.SITE_DIR / "results.json")
    if (C.RESULTS_DIR / "stations.csv").exists():
        shutil.copy(C.RESULTS_DIR / "stations.csv", C.SITE_DIR / "stations.csv")
    (C.SITE_DIR / "index.html").write_text(page(res), encoding="utf-8")
    (C.SITE_DIR / ".nojekyll").write_text("")
    story = build_story(json.loads(src.read_text()))
    print(f"Headline: {story['verdict']}. {html.unescape(story['dek'])}")
    print(f"Wrote {C.SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
