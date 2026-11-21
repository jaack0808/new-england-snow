# Was my uncle right about the snow?

**📄 Report: <https://jaack0808.github.io/new-england-snow/>**

My uncle (1939–2024) lived most of his life in New England and kept saying there's less snow
nowadays than there used to be. This repo checks him against the record. It compares winters in
**2000–2019** with winters in **1940–1999** at long-running New England weather stations, using
NOAA's [Global Historical Climatology Network – Daily](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)
(GHCN-Daily).

The headline answer (Yes or No), the evidence behind it, and the graphs are on the report page.
That page is rebuilt from the raw NOAA data on every push, so the verdict always comes from the
data and is never typed in by hand.

## What's measured

| Measure | GHCN element | Role |
|---|---|---|
| Seasonal snowfall (Oct–May total) | `SNOW` | **Decides the headline** |
| Days with ≥ 1 inch of new snow | `SNOW` | Supporting |
| Days with ≥ 1 inch of snow on the ground | `SNWD` | Supporting |

The verdict is **Yes** only if the 95% bootstrap confidence interval for the 2000–2019 minus
1940–1999 difference in regional snowfall lies entirely below zero. Otherwise it's **No**.

## How it works

```
scripts/
  config.py         every threshold and setting in one place
  download_data.py  station list + inventory -> picks New England stations with long SNOW
                    records -> downloads each station's file from NCEI into data/raw/
  analyze.py        quality-filters daily values, builds winter totals, keeps stations with
                    data in every decade, computes the regional index, tests and trends
                    -> data/results/{results.json,stations.csv,station_seasons.csv}
  build_site.py     turns results.json into site/index.html (text, numbers, interactive charts)
tests/
  make_fake_data.py synthetic GHCN-format data for offline testing
  smoke_test.sh     runs the whole pipeline on the fake data
.github/workflows/pages.yml   runs download -> analyze -> build and deploys site/ to Pages
```

In brief, the method:

1. **Stations.** Every US station in CT, MA, ME, NH, RI or VT whose snowfall record runs from
   1945 or earlier to 2020 or later is downloaded. For each measure, a station is kept only if it
   has at least 5 usable winters in every decade 1940s–1990s (1950s–1990s for snow depth) and at
   least 7 in each of the 2000s and 2010s.
2. **Winters.** A season runs Oct 1 – May 31 and is labelled by its starting year. December–March
   may miss at most 3 days each, and November and April at most 7. Values with a NOAA quality
   flag are dropped.
3. **Regional index.** Each station-winter is converted to a percentage of that station's own
   1940–1999 average, then averaged across stations, so every station counts equally.
4. **Tests.** 95% bootstrap confidence interval (10,000 resamples), Welch's t-test and
   Mann–Whitney U on the regional index, plus per-station tests, a sign test, a Theil–Sen /
   Mann–Kendall trend, and a check of how the answer changes with the choice of baseline.

## Run it yourself

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run_all.sh                          # download (~100 MB), analyze, build
python3 -m http.server -d site 8000   # open http://localhost:8000
```

Offline check with synthetic data: `bash tests/smoke_test.sh`.

## Deploying (one-time setup)

1. Create an empty public repo named `new-england-snow` on GitHub and push this repo to it.
2. In **Settings → Pages**, set **Source** to **GitHub Actions**.
3. The *Build and deploy report* workflow runs on every push to `main` (or run it by hand from
   the Actions tab). When it finishes, the report is live at the URL above and the job summary
   shows the headline.

## What isn't in git

Raw NOAA files (`data/`) and the built page (`site/`) are git-ignored and exist only on your
machine or on the Actions runner. Pages is deployed from a workflow artifact, so no data or
build output is ever committed, not even in history.

---

*Code and write-up developed with the help of an AI assistant.*
