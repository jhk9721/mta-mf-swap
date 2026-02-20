"""
SCRIPT: TEST — Automated Output Verification
=============================================
Checks that prior analysis steps produced the expected files and that
key invariants hold in the data (direction convention, headway bounds, etc.).

Run AFTER 3_analyze.py and 4_community_output.py:
    python3 test_scripts.py

Exits 0 on full pass, 1 on any failure.
"""

import sys
from pathlib import Path
from datetime import date

SCRIPTS_DIR   = Path(__file__).parent
RAW_DATA_DIR  = SCRIPTS_DIR / "raw_data"
RESULTS_DIR   = SCRIPTS_DIR / "results"
COMMUNITY_DIR = RESULTS_DIR / "community"

SWAP_DATE  = date(2025, 12, 8)
STORM_DATE = date(2026, 1, 25)

# ── Helpers ───────────────────────────────────────────────────────────────────

_pass = 0
_fail = 0


def ok(msg: str):
    global _pass
    _pass += 1
    print(f"  [PASS] {msg}")


def fail(msg: str):
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}")


def section(title: str):
    print(f"\n── {title} {'─' * max(1, 54 - len(title))}")


# ── Test suites ───────────────────────────────────────────────────────────────

def test_raw_data_exists():
    section("Raw data files")
    tar_files = sorted(RAW_DATA_DIR.glob("*.tar.xz"))
    if tar_files:
        ok(f"{len(tar_files)} .tar.xz files found in {RAW_DATA_DIR.name}/")
    else:
        fail(f"No .tar.xz files in {RAW_DATA_DIR}. Run 1_download.py first.")
        return

    # Check at least one file per study period
    pre_files  = [f for f in tar_files if "_2025-1" in f.name or "_2025-11" in f.name]
    post_files = [f for f in tar_files if "_2026-" in f.name]
    if pre_files:
        ok(f"Pre-swap files present ({len(pre_files)} files in Oct/Nov 2025)")
    else:
        fail("No pre-swap (Oct/Nov 2025) files found.")
    if post_files:
        ok(f"Post-swap files present ({len(post_files)} files in 2026)")
    else:
        fail("No post-swap (2026) files found.")


def test_analysis_outputs():
    section("Analysis outputs (3_analyze.py)")
    expected_files = [
        RESULTS_DIR / "roosevelt_island_headways.csv",
        RESULTS_DIR / "headway_summary.csv",
        RESULTS_DIR / "results_report.txt",
    ]
    for f in expected_files:
        if f.exists() and f.stat().st_size > 0:
            ok(f"{f.name} exists ({f.stat().st_size // 1024} KB)")
        else:
            fail(f"{f.name} missing or empty. Run 3_analyze.py.")

    chart_files = [
        RESULTS_DIR / "headway_distribution_weekday.png",
        RESULTS_DIR / "headway_distribution_weekend.png",
        RESULTS_DIR / "headways_over_time.png",
        RESULTS_DIR / "hourly_headways.png",
    ]
    for f in chart_files:
        if f.exists() and f.stat().st_size > 0:
            ok(f"{f.name} exists")
        else:
            fail(f"{f.name} missing. Run 3_analyze.py.")


def test_community_outputs():
    section("Community outputs (4_community_output.py)")
    expected = [
        COMMUNITY_DIR / "all_periods_comparison.png",
        COMMUNITY_DIR / "evening_rush_spotlight.png",
        COMMUNITY_DIR / "northbound_overview.png",
        COMMUNITY_DIR / "southbound_overview.png",
        COMMUNITY_DIR / "long_waits_northbound.png",
        COMMUNITY_DIR / "long_waits_southbound.png",
        COMMUNITY_DIR / "weekend_impact.png",
        COMMUNITY_DIR / "worst_waits.png",
        COMMUNITY_DIR / "talking_points.txt",
    ]
    for f in expected:
        if f.exists() and f.stat().st_size > 0:
            ok(f"{f.name} exists")
        else:
            fail(f"{f.name} missing. Run 4_community_output.py.")


def test_direction_convention():
    section("Direction convention (headway CSV)")
    csv_path = RESULTS_DIR / "roosevelt_island_headways.csv"
    if not csv_path.exists():
        fail("roosevelt_island_headways.csv not found — skipping direction check.")
        return

    try:
        import pandas as pd
        df = pd.read_csv(csv_path, usecols=["stop_id", "route_id", "is_weekday",
                                             "arrival_date", "swap_period"],
                         low_memory=False)
        df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    except Exception as e:
        fail(f"Could not read headways CSV: {e}")
        return

    # Stop IDs
    stop_ids = set(df["stop_id"].astype(str).str[-3:].unique())
    for expected in ["06N", "06S"]:
        if any(expected in s for s in stop_ids):
            ok(f"B{expected} stop ID present in data")
        else:
            fail(f"B{expected} stop ID NOT found — check GTFS station IDs.")

    # Route IDs
    weekdays = df[df["is_weekday"] == True]
    pre  = weekdays[weekdays["swap_period"] == "Before swap"]
    post = weekdays[weekdays["swap_period"] == "After swap"]

    pre_routes  = set(pre["route_id"].dropna().unique())
    post_routes = set(post["route_id"].dropna().unique())

    if "F" in pre_routes:
        ok(f"F train in pre-swap weekdays (routes: {sorted(pre_routes)})")
    else:
        fail(f"F train NOT in pre-swap weekdays (found: {sorted(pre_routes)})")

    if "M" in post_routes:
        ok(f"M train in post-swap weekdays (routes: {sorted(post_routes)})")
    else:
        fail(f"M train NOT in post-swap weekdays (found: {sorted(post_routes)})")


def test_headway_bounds():
    section("Headway value bounds")
    csv_path = RESULTS_DIR / "roosevelt_island_headways.csv"
    if not csv_path.exists():
        fail("roosevelt_island_headways.csv not found — skipping bounds check.")
        return

    try:
        import pandas as pd
        df = pd.read_csv(csv_path, usecols=["headway_min", "time_bucket"],
                         low_memory=False)
    except Exception as e:
        fail(f"Could not read headways CSV: {e}")
        return

    below_min = (df["headway_min"] < 1).sum()
    early_am  = df["time_bucket"].astype(str).str.startswith("1:")
    above_max = (
        (early_am  & (df["headway_min"] > 90)) |
        (~early_am & (df["headway_min"] > 60))
    ).sum()

    if below_min == 0:
        ok("No headways < 1 min (outlier filter applied)")
    else:
        fail(f"{below_min} headways < 1 min found — outlier filter may not have run.")

    if above_max == 0:
        ok("No headways above time-of-day threshold (60/90 min cap applied)")
    else:
        fail(f"{above_max} headways above threshold — outlier filter may not have run.")

    total = len(df)
    ok(f"Total headway observations: {total:,}")


def test_date_coverage():
    section("Date coverage in headway data")
    csv_path = RESULTS_DIR / "roosevelt_island_headways.csv"
    if not csv_path.exists():
        fail("roosevelt_island_headways.csv not found — skipping date coverage.")
        return

    try:
        import pandas as pd
        df = pd.read_csv(csv_path, usecols=["arrival_date"], low_memory=False)
        df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    except Exception as e:
        fail(f"Could not parse dates: {e}")
        return

    min_date = df["arrival_date"].min()
    max_date = df["arrival_date"].max()
    n_dates  = df["arrival_date"].nunique()
    ok(f"Date range: {min_date} → {max_date}  ({n_dates} distinct days)")

    if min_date <= date(2025, 10, 31):
        ok("Pre-swap baseline reaches into October 2025")
    else:
        fail(f"Pre-swap data starts {min_date} — expected on or before Oct 2025.")

    if max_date >= date(2026, 1, 1):
        ok("Post-swap data extends into 2026")
    else:
        fail(f"Post-swap data ends {max_date} — expected data into 2026.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("Roosevelt Island MTA Analysis — Script Output Tests")
    print("=" * 55)

    test_raw_data_exists()
    test_analysis_outputs()
    test_community_outputs()
    test_direction_convention()
    test_headway_bounds()
    test_date_coverage()

    print(f"\n{'=' * 55}")
    print(f"Results: {_pass} passed, {_fail} failed.")
    if _fail == 0:
        print("All checks passed.")
        sys.exit(0)
    else:
        print(f"{_fail} check(s) failed. See [FAIL] lines above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
