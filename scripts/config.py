"""Shared settings for the New England snow analysis.

Every threshold used to pick stations or seasons lives here so the method is
easy to audit and easy to change.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SNOW_DATA_DIR", ROOT / "data"))  # git-ignored
RAW_DIR = DATA_DIR / "raw"          # one .csv.gz per station
RESULTS_DIR = DATA_DIR / "results"  # analysis output (CSV + JSON)
SITE_DIR = Path(os.environ.get("SNOW_SITE_DIR", ROOT / "site"))  # built page (git-ignored)

# --- NOAA GHCN-Daily sources -------------------------------------------------
GHCN_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
STATIONS_URL = f"{GHCN_BASE}/ghcnd-stations.txt"
INVENTORY_URL = f"{GHCN_BASE}/ghcnd-inventory.txt"
BY_STATION_URL = f"{GHCN_BASE}/by_station/{{station}}.csv.gz"

# --- Region ------------------------------------------------------------------
NEW_ENGLAND = ["CT", "MA", "ME", "NH", "RI", "VT"]
STATE_NAMES = {
    "CT": "Connecticut", "MA": "Massachusetts", "ME": "Maine",
    "NH": "New Hampshire", "RI": "Rhode Island", "VT": "Vermont",
}

# --- Periods (winters are labelled by the year they START: 1940 = 1940-41) ---
BASE_START, BASE_END = 1940, 1999      # "last six decades of the 20th century"
RECENT_START, RECENT_END = 2000, 2019  # "first two decades of the 21st century"
BASE_DECADES = list(range(1940, 2000, 10))
RECENT_DECADES = [2000, 2010]

# --- Season definition -------------------------------------------------------
# A snow season runs Oct 1 - May 31. Dec-Mar are the core months and must be
# nearly complete; Nov and Apr may have a few gaps (counted as no snow);
# Oct and May gaps are counted as no snow.
SEASON_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5]
CORE_MONTHS = [12, 1, 2, 3]
CORE_MAX_MISSING = 3      # max missing days per core month
SHOULDER_MONTHS = [11, 4]
SHOULDER_MAX_MISSING = 7  # max missing days per shoulder month

ONE_INCH_MM = 25          # GHCN stores snow in whole mm; 1.0 inch is stored as 25

# --- Station inclusion -------------------------------------------------------
# Inventory pre-filter (what we bother downloading)
INVENTORY_FIRST_YEAR_MAX = 1945
INVENTORY_LAST_YEAR_MIN = 2020
# Per-metric inclusion after quality control
MIN_SEASONS_PER_BASE_DECADE = 5    # of 10, in every decade 1940s..1990s
MIN_SEASONS_PER_RECENT_DECADE = 7  # of 10, in both the 2000s and 2010s
MIN_STATION_SHARE_FOR_INDEX = 0.5  # regional index needs half the stations reporting

# --- Statistics --------------------------------------------------------------
ALPHA = 0.05
N_BOOTSTRAP = 10_000
RANDOM_SEED = 1939                 # the year the uncle was born
ROLLING_WINDOW = 10

METRICS = {
    "snowfall": {
        "element": "SNOW",
        "label": "Seasonal snowfall",
        "unit": "in",
        "short": "snowfall",
        "description": "Total snow that fell, October through May",
    },
    "snow_days": {
        "element": "SNOW",
        "label": "Days with 1 inch or more of new snow",
        "unit": "days",
        "short": "snowy days",
        "description": "Days on which at least 1 inch of new snow fell",
    },
    "cover_days": {
        "element": "SNWD",
        "label": "Days with 1 inch or more of snow on the ground",
        "unit": "days",
        "short": "snow-cover days",
        "description": "Days with at least 1 inch of snow depth on the ground",
        # Snow-depth reporting only became routine around 1948, so for this
        # metric the 1940s are used where present but not required.
        "required_base_decades": list(range(1950, 2000, 10)),
    },
}
PRIMARY_METRIC = "snowfall"
