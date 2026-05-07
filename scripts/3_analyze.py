"""
SCRIPT 3: ANALYZE (v4 — consistent time buckets, weekday/weekend labels)
=========================================================================
DIRECTION CONVENTION:
  N (B06N) = Northbound = toward Queens (trains leaving Manhattan, commute HOME)
  S (B06S) = Southbound = toward Manhattan (trains to work, MORNING commute)
  Roosevelt Island is on the 63rd Street line; "northbound" is geographically NE toward Queens.
Key changes from v3:
  - Five consistent clock-based time buckets apply to ALL days
  - Weekday and weekend get different LABELS for the same buckets
    (e.g. "AM Rush" on weekdays, "Early Morning" on weekends)
    because the data shows no rush-hour pattern on weekends
  - Swap window annotated in charts rather than used as a bucket boundary

TIME BUCKETS (same clock boundaries every day):
  1. Overnight:       12:00 AM –  5:00 AM
  2. AM Rush / Early Morning:  5:00 AM –  9:00 AM
  3. Midday:           9:00 AM –  4:00 PM
  4. PM Rush / Afternoon:      4:00 PM –  8:00 PM
  5. Late Night:       8:00 PM – 12:00 AM

HOW TO RUN:
    python3 3_analyze.py

OUTPUTS (saved to results/ folder):
  - roosevelt_island_headways.csv         — every headway observation
  - headway_summary.csv                   — summary + wait time (E[H]/2) + tails
  - headway_summary_clean_days.csv        — same summary, no holidays/storm
  - headway_per_hour.csv                  — per-hour weekday comparison
  - headway_monthly.csv                   — monthly stratification, peaks
  - headway_bootstrap_ci.csv              — 95% CIs on pre→post deltas
  - headway_distribution_weekday.png
  - headway_distribution_weekend.png
  - headways_over_time.png
  - hourly_headways.png
  - results_report.txt                    — extended with rebuttal sections
"""

import os
import sys
import tarfile
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
from datetime import datetime, date

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

RAW_DATA_DIR = "raw_data"
RESULTS_DIR  = "results"

# Roosevelt Island — confirmed from MTA official GTFS station glossary
ROOSEVELT_ISLAND_STOP_IDS = {"B06N", "B06S"}

SWAP_DATE       = date(2025, 12, 8)
STORM_DATE      = date(2026, 1, 25)   # January blizzard — major service disruption
STORM_END_DATE  = date(2026, 2, 1)    # One-week disruption window after storm
STEADY_START    = date(2026, 2, 1)    # "Steady-state" stratum begins
N_BOOTSTRAP     = 1000
BOOTSTRAP_SEED  = 42

# Holiday periods: dates where reduced ridership or service exceptions may
# affect headway patterns. The list below matches the canonical filter used
# by script 8 (Queens Plaza analysis), so downstream comparisons (notably
# the difference-in-differences in script 11) apply identical date exclusions
# to treatment and control data.
HOLIDAY_PERIODS = [
    (date(2025,  1, 20), date(2025,  1, 20)),   # MLK Day 2025
    (date(2025,  2, 17), date(2025,  2, 17)),   # Presidents Day 2025
    (date(2025, 12, 22), date(2026,  1,  5)),   # Christmas / New Year
    (date(2026,  1, 19), date(2026,  1, 19)),   # MLK Day 2026
    (date(2026,  1, 25), date(2026,  1, 25)),   # Jan 25 storm (already a Sunday)
]

# ── Time bucket definitions ───────────────────────────────────────────────────
# (start_hour_inclusive, end_hour_exclusive, weekday_label, weekend_label)
# Same clock boundaries on all days.
# Weekday labels use "Rush" where data shows peak frequency;
# weekend labels are identical since no rush pattern exists on weekends.
TIME_BUCKETS = [
    ( 0,  6, "1: Early AM (12–6 AM)",           "1: Early AM (12–6 AM)"),
    ( 6,  9, "2: Morning Rush (6–9 AM)",         "2: Morning (6–9 AM)"),
    ( 9, 16, "3: Midday (9 AM–4 PM)",            "3: Midday (9 AM–4 PM)"),
    (16, 19, "4: Evening Rush (4–7 PM)",         "4: Afternoon/Evening (4–7 PM)"),
    (19, 24, "5: Night (7 PM–midnight)",         "5: Night (7 PM–midnight)"),
]

# Swap window: weekdays 6 AM–9:30 PM
# Morning Rush (6–9am): fully within swap window
# Midday (9am–4pm):     fully within swap window
# Evening Rush (4–7pm): fully within swap window
# Night (7–9:30pm):     PARTIALLY within swap window (first 2.5 hrs)
SWAP_AFFECTED_BUCKETS_NOTE = (
    "* F/M swap active weekdays 6 AM–9:30 PM: fully affects Morning Rush, Midday, and Evening Rush. "
    "Night bucket (7 PM–midnight) is partially affected on weekdays (7–9:30 PM within swap window)."
)

def is_holiday_week(d: date) -> bool:
    """Return True if the date falls within a known holiday period."""
    for start, end in HOLIDAY_PERIODS:
        if start <= d <= end:
            return True
    return False


def assign_time_bucket(hour: int, is_weekday: bool) -> str:
    for start, end, wd_label, we_label in TIME_BUCKETS:
        if start <= hour < end:
            return wd_label if is_weekday else we_label
    return "Unknown"

# ══════════════════════════════════════════════════════════════════════════════


def load_one_day(tar_path: str, file_date: date) -> pd.DataFrame:
    with tarfile.open(tar_path, "r:xz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        st_member = next(
            (m for n, m in members.items() if n.endswith("stop_times.csv")), None)
        tr_member = next(
            (m for n, m in members.items() if n.endswith("trips.csv")), None)

        if st_member is None or tr_member is None:
            print(f"  [WARN] {os.path.basename(tar_path)}: missing CSVs.")
            return pd.DataFrame()

        stop_times = pd.read_csv(tar.extractfile(st_member), low_memory=False)
        stop_times = stop_times[
            stop_times["stop_id"].isin(ROOSEVELT_ISLAND_STOP_IDS)
        ].copy()

        if stop_times.empty:
            print(f"  [WARN] {os.path.basename(tar_path)}: no B06 records.")
            return pd.DataFrame()

        trips = pd.read_csv(tar.extractfile(tr_member), low_memory=False,
                             usecols=["trip_uid", "route_id", "direction_id"])

    df = stop_times.merge(trips, on="trip_uid", how="left")
    df["arrival_time"]   = pd.to_numeric(df["arrival_time"],   errors="coerce")
    df["departure_time"] = pd.to_numeric(df["departure_time"], errors="coerce")
    df["timestamp"] = df["arrival_time"].fillna(df["departure_time"])
    df = df.dropna(subset=["timestamp"])

    df["arrival_dt"] = (pd.to_datetime(df["timestamp"], unit="s", utc=True)
                          .dt.tz_convert("America/New_York"))
    df["calendar_date"] = file_date
    return df


def load_all_data(raw_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(raw_dir, "*.tar.xz")))
    if not files:
        raise FileNotFoundError(f"No .tar.xz files in '{raw_dir}/'.")

    print(f"Found {len(files)} daily files. Loading...\n")
    all_dfs = []

    for filepath in files:
        filename = os.path.basename(filepath)
        try:
            date_str  = filename.split("_")[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (IndexError, ValueError):
            print(f"  [SKIP] {filename}")
            continue
        try:
            day_df = load_one_day(filepath, file_date)
            if not day_df.empty:
                all_dfs.append(day_df)
                print(f"  [OK]   {filename}  → {len(day_df):,} RI arrivals")
        except Exception as e:
            print(f"  [ERR]  {filename}: {e}")

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal Roosevelt Island records: {len(combined):,}\n")
    return combined


def add_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["arrival_date"] = df["arrival_dt"].dt.date
    df["hour"]         = df["arrival_dt"].dt.hour
    df["minute"]       = df["arrival_dt"].dt.minute
    df["day_of_week"]  = df["arrival_dt"].dt.dayofweek
    df["is_weekday"]   = df["day_of_week"] < 5
    df["direction"]    = df["stop_id"].astype(str).str[-1]
    df["swap_period"]  = df["arrival_date"].apply(
        lambda d: "After swap" if d >= SWAP_DATE else "Before swap"
    )
    df["day_type"]     = df["is_weekday"].map({True: "Weekday", False: "Weekend"})
    df["time_bucket"]    = df.apply(
        lambda r: assign_time_bucket(r["hour"], r["is_weekday"]), axis=1
    )
    df["is_holiday_week"] = df["arrival_date"].apply(is_holiday_week)
    return df


def compute_headways(df: pd.DataFrame) -> pd.DataFrame:
    """Headways computed within each day + direction + time_bucket group."""
    print("Computing headways...")
    df_s = df.sort_values(
        ["arrival_date", "direction", "time_bucket", "arrival_dt"]
    ).copy()

    grp = ["arrival_date", "direction", "time_bucket"]
    df_s["prev_arrival"] = df_s.groupby(grp)["arrival_dt"].shift(1)
    df_s["headway_min"]  = (
        (df_s["arrival_dt"] - df_s["prev_arrival"]).dt.total_seconds() / 60
    )
    df_s = df_s.dropna(subset=["headway_min"])
    total_before_filter = len(df_s)

    # Overnight allows longer gaps (≤90 min); daytime cap at 60 min
    below_min  = (df_s["headway_min"] < 1).sum()
    df_s       = df_s[df_s["headway_min"] >= 1]

    early_am_mask = df_s["time_bucket"].str.startswith("1:")
    above_max     = (
        (early_am_mask  & (df_s["headway_min"] > 90)) |
        (~early_am_mask & (df_s["headway_min"] > 60))
    ).sum()
    df_s = df_s[
        (early_am_mask  & (df_s["headway_min"] <= 90)) |
        (~early_am_mask & (df_s["headway_min"] <= 60))
    ]

    total_removed = below_min + above_max
    pct_removed   = 100 * total_removed / total_before_filter if total_before_filter > 0 else 0
    print(f"  Outlier removal: {below_min} below 1 min, {above_max} above threshold "
          f"({total_removed} total, {pct_removed:.1f}% of intervals)")
    print(f"  {len(df_s):,} headway observations retained.\n")
    return df_s


def _add_wait_time_column(s: pd.DataFrame) -> pd.DataFrame:
    """
    Add wait_time_min = mean_headway / 2 — the MTA's own definition of
    "average wait time" under the random-arrival assumption it uses in
    the April 2026 letter. Matching their methodology lets the comparison
    speak in their terms.
    """
    s["wait_time_min"] = s["mean"] / 2
    return s


def summarize_headways(df_hw: pd.DataFrame) -> pd.DataFrame:
    g = df_hw.groupby(["day_type", "time_bucket", "swap_period", "direction"])
    s = g["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75),
        p90=lambda x: x.quantile(0.90),
        p95=lambda x: x.quantile(0.95),
        max_gap="max",
        pct_over_10=lambda x: (x > 10).mean() * 100,
        pct_over_15=lambda x: (x > 15).mean() * 100,
    ).reset_index()

    s = _add_wait_time_column(s)

    s = s.round({
        "median": 2, "mean": 2, "p25": 2, "p75": 2, "p90": 2, "p95": 2,
        "max_gap": 2, "pct_over_10": 1, "pct_over_15": 1,
        "wait_time_min": 2,
    })
    s["direction"] = s["direction"].map(
        {"N": "Northbound (→ Queens/Home)", "S": "Southbound (→ Manhattan)"}
    )
    return s.sort_values(["day_type", "time_bucket", "direction", "swap_period"])


def summarize_by_hour(df_hw: pd.DataFrame,
                       hours=range(6, 21)) -> pd.DataFrame:
    """
    Per-hour weekday breakdown for rush + adjacent hours.

    Lets us answer the MTA on its own terms: their letter quotes "during
    the 8 AM hour—the increase in average wait time is about 1.3 minutes."
    This produces the matched 1-hour-vs-1-hour comparison.
    """
    sub = df_hw[df_hw["is_weekday"] & df_hw["hour"].isin(list(hours))]
    if sub.empty:
        return pd.DataFrame()

    g = sub.groupby(["hour", "swap_period", "direction"])
    s = g["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).reset_index()

    s = _add_wait_time_column(s)

    s = s.round({
        "median": 2, "mean": 2, "p90": 2, "wait_time_min": 2,
    })
    s["direction"] = s["direction"].map(
        {"N": "Northbound (→ Queens/Home)", "S": "Southbound (→ Manhattan)"}
    )
    return s.sort_values(["direction", "hour", "swap_period"])


def summarize_by_month(df_hw: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly stratification — addresses the MTA's "early months were noisy"
    framing. Lets us point to Feb/Mar 2026 as the steady-state read.

    Scope: weekday, peak hours (AM + PM rush), Southbound + Northbound.
    """
    sub = df_hw[
        df_hw["is_weekday"] &
        df_hw["time_bucket"].str[:2].isin({"2:", "4:"})
    ].copy()
    if sub.empty:
        return pd.DataFrame()

    sub["arrival_month"] = (
        pd.to_datetime(sub["arrival_date"]).dt.to_period("M").astype(str)
    )

    g = sub.groupby(["arrival_month", "direction", "swap_period"])
    s = g["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).reset_index()

    s = _add_wait_time_column(s)

    s = s.round({
        "median": 2, "mean": 2, "p90": 2, "wait_time_min": 2,
    })
    s["direction"] = s["direction"].map(
        {"N": "Northbound (→ Queens/Home)", "S": "Southbound (→ Manhattan)"}
    )
    return s.sort_values(["direction", "arrival_month"])


def filter_clean_days(df_hw: pd.DataFrame) -> pd.DataFrame:
    """
    Exclude (a) holiday weeks and (b) the storm disruption window.
    Used for the steady-state side-by-side variant — addresses the MTA's
    "first months were affected by systemwide incidents and historic
    winter storms" defense.
    """
    in_storm = (
        (df_hw["arrival_date"] >= STORM_DATE) &
        (df_hw["arrival_date"] <  STORM_END_DATE)
    )
    return df_hw[~df_hw["is_holiday_week"] & ~in_storm]


def bootstrap_pre_post_ci(df_hw: pd.DataFrame,
                            n_boot: int = N_BOOTSTRAP,
                            seed: int = BOOTSTRAP_SEED) -> pd.DataFrame:
    """
    Bootstrap 95% confidence intervals on the pre→post delta for:
      - median headway
      - wait time = mean headway / 2  (the MTA's own definition)

    Reports per (time_bucket, direction) on weekdays. The CI lets us state
    "+1.5 min, 95% CI [1.3, 1.7]" against the MTA's projected ~1.0 min and
    show whether the gap is statistically distinguishable.

    Min sample requirement: 30 in each of pre and post; otherwise skipped.
    """
    rng = np.random.default_rng(seed)
    rows = []

    # Apply the same is_holiday_week filter that downstream comparisons
    # (script 11 DiD) use, so the bootstrap CI and the DiD report identical
    # treatment-side numbers.
    sub = df_hw[df_hw["is_weekday"] & ~df_hw["is_holiday_week"]]
    for (bucket, direction), grp in sub.groupby(["time_bucket", "direction"]):
        pre  = grp[grp["swap_period"] == "Before swap"]["headway_min"].to_numpy()
        post = grp[grp["swap_period"] == "After swap" ]["headway_min"].to_numpy()
        if len(pre) < 30 or len(post) < 30:
            continue

        med_deltas  = np.empty(n_boot)
        wait_deltas = np.empty(n_boot)
        for i in range(n_boot):
            ps = rng.choice(pre,  size=len(pre),  replace=True)
            qs = rng.choice(post, size=len(post), replace=True)
            med_deltas[i]  = np.median(qs) - np.median(ps)
            wait_deltas[i] = qs.mean() / 2 - ps.mean() / 2

        wait_pre  = pre.mean()  / 2
        wait_post = post.mean() / 2

        rows.append({
            "time_bucket":      bucket,
            "direction":        direction,
            "n_pre":            int(len(pre)),
            "n_post":           int(len(post)),
            "median_pre":       round(float(np.median(pre)), 2),
            "median_post":      round(float(np.median(post)), 2),
            "median_delta":     round(float(np.median(post) - np.median(pre)), 2),
            "median_delta_ci_low":  round(float(np.percentile(med_deltas, 2.5)), 2),
            "median_delta_ci_high": round(float(np.percentile(med_deltas, 97.5)), 2),
            "wait_time_pre":    round(float(wait_pre), 2),
            "wait_time_post":   round(float(wait_post), 2),
            "wait_time_delta":  round(float(wait_post - wait_pre), 2),
            "wait_time_delta_ci_low":  round(float(np.percentile(wait_deltas, 2.5)), 2),
            "wait_time_delta_ci_high": round(float(np.percentile(wait_deltas, 97.5)), 2),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["direction"] = df["direction"].map(
            {"N": "Northbound (→ Queens/Home)", "S": "Southbound (→ Manhattan)"}
        )
    return df


def verify_direction_convention(df: pd.DataFrame) -> None:
    """
    Verify that stop IDs map to expected train routes.
      B06N + B06S pre-swap weekdays  → F train
      B06N + B06S post-swap weekdays → M train
    Exits with a non-zero code if the convention cannot be confirmed.
    """
    print("── Direction Convention Verification ──────────────────────────")
    weekdays = df[df["is_weekday"]]
    pre  = weekdays[weekdays["swap_period"] == "Before swap"]
    post = weekdays[weekdays["swap_period"] == "After swap"]

    pre_routes  = set(pre["route_id"].dropna().unique())
    post_routes = set(post["route_id"].dropna().unique())
    print(f"  Pre-swap weekday routes:  {sorted(pre_routes)}")
    print(f"  Post-swap weekday routes: {sorted(post_routes)}")

    fail = False
    if "F" not in pre_routes:
        print("  [FAIL] F train not found in pre-swap weekday data!")
        fail = True
    if "M" not in post_routes:
        print("  [FAIL] M train not found in post-swap weekday data!")
        fail = True
    for stop in ["B06N", "B06S"]:
        if stop not in df["stop_id"].values:
            print(f"  [FAIL] Expected stop {stop} not found in data!")
            fail = True
    if fail:
        print("  Aborting — fix direction convention before analysis.")
        sys.exit(1)

    print("  [OK] F pre-swap, M post-swap. Both B06N and B06S present.\n")


def validate_data_completeness(df: pd.DataFrame) -> None:
    """
    Check for date gaps and days with suspiciously few arrivals.
    Warns on gaps > 3 days or days with < 10 Roosevelt Island arrivals.
    Prompts the user to continue if critical issues are found.
    """
    print("── Data Completeness Check ─────────────────────────────────────")
    dates = sorted(df["arrival_date"].unique())
    if not dates:
        print("  [FAIL] No dates found in data!")
        sys.exit(1)

    print(f"  Date range: {dates[0]} → {dates[-1]}  ({len(dates)} distinct days)")

    # Check for gaps > 3 days
    gaps = []
    prev = None
    for d in dates:
        if prev is not None:
            gap = (d - prev).days
            if gap > 3:
                gaps.append((prev, d, gap))
        prev = d

    if gaps:
        print(f"  [WARN] {len(gaps)} gap(s) > 3 days detected:")
        for g_start, g_end, g_days in gaps:
            print(f"         {g_start} → {g_end}  ({g_days} days missing)")
    else:
        print("  [OK]  No gaps > 3 days found.")

    # Check for days with very few arrivals
    daily_counts = df.groupby("arrival_date").size()
    low_days = daily_counts[daily_counts < 10]
    if not low_days.empty:
        print(f"  [WARN] {len(low_days)} day(s) with < 10 RI arrivals (possible bad data):")
        for d, n in low_days.items():
            print(f"         {d}: {n} arrivals")
    else:
        print("  [OK]  All days have ≥ 10 Roosevelt Island arrivals.")

    critical = len(gaps) > 5 or not low_days.empty
    if critical:
        answer = input("\n  Data quality issues found. Continue anyway? [y/N] ").strip().lower()
        if answer != "y":
            print("  Aborting.")
            sys.exit(0)

    print()


def analyze_storm_impact(df_hw: pd.DataFrame) -> None:
    """
    Three-period headway comparison around the January 2026 blizzard:
      1. Pre-swap       (F train, before Dec 8)
      2. Post-swap pre-storm  (M train, Dec 8 – Jan 24)
      3. Post-storm     (M train, Jan 25+)

    Swap-active hours only (Morning Rush + Midday + Evening Rush), weekdays.
    """
    SWAP_ACTIVE = {"2:", "3:", "4:"}
    wd_swap = df_hw[
        df_hw["is_weekday"] &
        df_hw["time_bucket"].str[:2].isin(SWAP_ACTIVE)
    ]

    pre   = wd_swap[wd_swap["arrival_date"] < SWAP_DATE]
    mid   = wd_swap[
        (wd_swap["arrival_date"] >= SWAP_DATE) &
        (wd_swap["arrival_date"] <  STORM_DATE)
    ]
    post  = wd_swap[wd_swap["arrival_date"] >= STORM_DATE]

    print("── Storm Impact Analysis ───────────────────────────────────────")
    print(f"  Storm date: {STORM_DATE}  (Jan 2026 blizzard)\n")
    periods = [
        ("Pre-swap  (F train, before Dec 8) ", pre),
        ("Post-swap pre-storm (M, Dec 8–Jan 24)", mid),
        ("Post-storm (M train, Jan 25+)     ", post),
    ]
    medians = {}
    for label, sub in periods:
        if sub.empty:
            print(f"  {label}: no data")
            continue
        m = sub["headway_min"].median()
        p = sub["headway_min"].quantile(0.90)
        medians[label] = m
        print(f"  {label}: median={m:.1f} min, p90={p:.1f} min, n={len(sub):,}")

    vals = list(medians.values())
    if len(vals) >= 2:
        swap_effect = (vals[1] - vals[0]) / vals[0] * 100
        print(f"\n  Swap effect (pre→post-swap pre-storm): {swap_effect:+.0f}%")
    if len(vals) >= 3:
        storm_effect = (vals[2] - vals[1]) / vals[1] * 100
        print(f"  Storm effect (pre-storm→post-storm):   {storm_effect:+.0f}%")
    print()


def analyze_holiday_impact(df_hw: pd.DataFrame) -> None:
    """
    Compare post-swap headways during holiday weeks vs. non-holiday weeks.
    Helps confirm whether holiday reduced-service periods skew the results.
    """
    post = df_hw[
        df_hw["is_weekday"] &
        (df_hw["swap_period"] == "After swap") &
        df_hw["time_bucket"].str[:2].isin({"2:", "3:", "4:"})
    ]
    holiday     = post[post["is_holiday_week"]]
    non_holiday = post[~post["is_holiday_week"]]

    print("── Holiday Week Impact ─────────────────────────────────────────")
    for label, sub in [("Holiday weeks", holiday), ("Non-holiday weeks", non_holiday)]:
        if sub.empty:
            print(f"  {label}: no data")
            continue
        print(f"  {label}: median={sub['headway_min'].median():.1f} min, "
              f"n={len(sub):,}")

    if not holiday.empty and not non_holiday.empty:
        diff = holiday["headway_min"].median() - non_holiday["headway_min"].median()
        print(f"  Holiday vs. non-holiday difference: {diff:+.1f} min")
        note = ("Holidays inflate post-swap medians." if diff > 1
                else "Holiday effect is minimal — results are robust.")
        print(f"  → {note}")
    print()


def analyze_weekend_control_group(df_hw: pd.DataFrame) -> None:
    """
    Explicit weekend before/after comparison as a control group.
    The F train runs on weekends in both periods, so any headway change
    here reflects systemwide F-line drift — NOT the swap itself.
    """
    we = df_hw[df_hw["day_type"] == "Weekend"]
    before = we[we["swap_period"] == "Before swap"]["headway_min"]
    after  = we[we["swap_period"] == "After swap"]["headway_min"]

    print("── Weekend Control Group (F train both periods) ────────────────")
    print("  Changes here = systemwide F drift, NOT the M swap.\n")

    bucket_map = [
        ("2:", "Morning (6–9 AM)       "),
        ("3:", "Midday (9 AM–4 PM)     "),
        ("4:", "Afternoon/Eve (4–7 PM) "),
    ]
    for prefix, label in bucket_map:
        bef = we[we["time_bucket"].str.startswith(prefix) & (we["swap_period"] == "Before swap")]["headway_min"]
        aft = we[we["time_bucket"].str.startswith(prefix) & (we["swap_period"] == "After swap")]["headway_min"]
        if bef.empty or aft.empty:
            continue
        diff = aft.median() - bef.median()
        pct  = diff / bef.median() * 100
        print(f"  {label}: {bef.median():.1f} → {aft.median():.1f} min  ({pct:+.0f}%)")

    if not before.empty and not after.empty:
        d = after.median() - before.median()
        p = d / before.median() * 100
        interp = ("systemwide F service degradation" if d > 0.5
                  else "no meaningful baseline drift")
        print(f"\n  Overall weekend: {before.median():.1f} → {after.median():.1f} min  ({p:+.0f}%)")
        print(f"  Interpretation: suggests {interp}.")
    print()


def _bucket_order(df_hw, day_type):
    """Return time buckets in sorted order for a given day type."""
    return sorted(df_hw[df_hw["day_type"] == day_type]["time_bucket"].unique())


def plot_distribution(df_hw: pd.DataFrame, day_type: str, results_dir: str):
    """
    Before/after violin plots for each time bucket.
    One chart for weekdays, one for weekends.
    Southbound (→ Manhattan) shown as primary commute direction for morning rush.
    """
    buckets = _bucket_order(df_hw, day_type)
    n = len(buckets)
    fig, axes = plt.subplots(1, n, figsize=(4.5 * n, 7), sharey=False)
    if n == 1:
        axes = [axes]

    day_label = "Weekdays" if day_type == "Weekday" else "Weekends"
    fig.suptitle(
        f"Roosevelt Island — {day_label} Headway Distribution by Time Period\n"
        "Southbound (→ Manhattan) | Before vs. After F/M Swap",
        fontsize=13, fontweight="bold"
    )

    COLOR_BEFORE = "#4C8BE0"
    COLOR_AFTER  = "#E05C4C"

    for ax, bucket in zip(axes, buckets):
        data = df_hw[
            (df_hw["day_type"]    == day_type) &
            (df_hw["time_bucket"] == bucket) &
            (df_hw["direction"]   == "N")
        ]
        before = data[data["swap_period"] == "Before swap"]["headway_min"].dropna()
        after  = data[data["swap_period"] == "After swap"]["headway_min"].dropna()

        # Short title: strip the number prefix
        short = bucket.split(":", 1)[1].strip() if ":" in bucket else bucket
        ax.set_title(short, fontsize=9.5, fontweight="bold", pad=8)

        if before.empty and after.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color="gray")
            continue

        datasets  = [before, after]
        colors    = [COLOR_BEFORE, COLOR_AFTER]
        positions = [1, 2]
        n_before  = len(before)
        n_after   = len(after)

        parts = ax.violinplot(datasets, positions=positions,
                               showmedians=True, showextrema=False)
        for body, color in zip(parts["bodies"], colors):
            body.set_facecolor(color); body.set_alpha(0.55)
        parts["cmedians"].set_color("black"); parts["cmedians"].set_linewidth(2)

        ax.boxplot(datasets, positions=positions, widths=0.13,
                    patch_artist=True,
                    medianprops=dict(color="black", linewidth=2),
                    boxprops=dict(facecolor="white", alpha=0.85),
                    whiskerprops=dict(linestyle="--"),
                    flierprops=dict(marker=".", markersize=2, alpha=0.25))

        for pos, d, color in zip(positions, datasets, colors):
            if not d.empty:
                ax.text(pos, d.median() + 0.4, f"{d.median():.1f}m",
                         ha="center", va="bottom", fontsize=9,
                         fontweight="bold", color=color)

        ax.set_xticks(positions)
        ax.set_xticklabels([
            f"Before\n(F train)\nn={n_before:,}",
            f"After\n(M train)\nn={n_after:,}",
        ], fontsize=8.5)
        ax.set_ylabel("Headway (minutes)" if bucket == buckets[0] else "")
        ax.yaxis.grid(True, linestyle="--", alpha=0.4)
        ax.set_ylim(bottom=0)

    # Swap window note for weekdays only
    if day_type == "Weekday":
        fig.text(0.5, 0.01, SWAP_AFFECTED_BUCKETS_NOTE,
                  ha="center", fontsize=8.5, color="#555555",
                  style="italic")

    fig.text(0.5, -0.01 if day_type != "Weekday" else -0.03,
              "Source: subwaydata.nyc  |  Roosevelt Island (B06N/B06S)  |  Oct 2025–Feb 2026",
              ha="center", fontsize=8.5, color="gray")

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    fname = f"headway_distribution_{'weekday' if day_type == 'Weekday' else 'weekend'}.png"
    path = os.path.join(results_dir, fname)
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot_hourly_headways(df_hw: pd.DataFrame, results_dir: str):
    """Full 24-hour headway profile, weekday vs weekend, before vs after."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=True)
    fig.suptitle(
        "Roosevelt Island — Average Headway by Hour (Both Directions)\n"
        "Before vs. After F/M Swap",
        fontsize=13, fontweight="bold"
    )

    nb = df_hw[df_hw["direction"] == "N"]

    for ax, day_type, title in [
        (axes[0], "Weekday", "Weekdays"),
        (axes[1], "Weekend", "Weekends"),
    ]:
        sub = nb[nb["day_type"] == day_type]
        hourly = sub.groupby(["swap_period", "hour"])["headway_min"].mean().reset_index()

        for sp, color, ls in [
            ("Before swap", "#4C8BE0", "-"),
            ("After swap",  "#E05C4C", "--"),
        ]:
            d = hourly[hourly["swap_period"] == sp].sort_values("hour")
            if not d.empty:
                ax.plot(d["hour"], d["headway_min"],
                         label=sp, color=color, linewidth=2.5,
                         linestyle=ls, marker="o", markersize=4)

        # Shade time buckets alternately for readability
        bucket_boundaries = [0, 6, 9, 16, 19, 24]
        shades = [0.06, 0.0, 0.06, 0.0, 0.06]
        for i, (s, e, shade) in enumerate(
            zip(bucket_boundaries, bucket_boundaries[1:], shades)
        ):
            if shade > 0:
                ax.axvspan(s, e, alpha=shade, color="gray", zorder=0)

        # Mark swap window on weekday chart
        if day_type == "Weekday":
            ax.axvspan(6, 21.5, alpha=0.06, color="#E05C4C", zorder=0,
                        label="Swap active (6am–9:30pm)")
            ax.axvline(x=6,    color="#E05C4C", linewidth=0.8, linestyle=":")
            ax.axvline(x=21.5, color="#E05C4C", linewidth=0.8, linestyle=":")

        ax.set_title(title, fontsize=12)
        ax.set_xlabel("Hour of Day", fontsize=10)
        ax.set_ylabel("Avg Headway (minutes)" if ax == axes[0] else "")
        ax.set_xlim(0, 23)
        ax.set_xticks(range(0, 24))
        ax.set_xticklabels(
            [f"{h}" for h in range(0, 24)], rotation=45, fontsize=8
        )
        ax.yaxis.grid(True, linestyle="--", alpha=0.4)
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

    plt.tight_layout()
    path = os.path.join(results_dir, "hourly_headways.png")
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot_daily_median_headway(df_hw: pd.DataFrame, results_dir: str):
    """Daily median headway over time — AM Rush bucket, northbound."""
    am = df_hw[
        df_hw["time_bucket"].str.startswith("2:") &
        (df_hw["day_type"]  == "Weekday") &
        (df_hw["direction"] == "N")
    ]
    daily = am.groupby("arrival_date")["headway_min"].median().reset_index()
    daily["arrival_date"] = pd.to_datetime(daily["arrival_date"])

    fig, ax = plt.subplots(figsize=(15, 6))
    ax.plot(daily["arrival_date"], daily["headway_min"],
             color="#4C8BE0", linewidth=1.2, alpha=0.45)
    rolling = (daily.set_index("arrival_date")["headway_min"]
                     .rolling("7D", min_periods=3).mean())
    ax.plot(rolling.index, rolling.values,
             color="#4C8BE0", linewidth=3, label="7-day rolling average")

    ax.axvline(x=pd.Timestamp(SWAP_DATE), color="black",
                linewidth=2, linestyle=":", label="Dec 8: F/M Swap")
    ylim = ax.get_ylim()
    ax.text(pd.Timestamp(SWAP_DATE), ylim[1] * 0.97,
             "  ← F train   M train →",
             ha="left", va="top", fontsize=10,
             bbox=dict(boxstyle="round,pad=0.3",
                        facecolor="white", edgecolor="black"))

    ax.set_title(
        "Roosevelt Island — Daily Median Headway (Southbound/Manhattan-bound)\n"
        "Weekday Morning Rush (6–9 AM) | Oct 2025–Feb 2026",
        fontsize=13, fontweight="bold"
    )
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Median Headway (minutes)", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.xticks(rotation=45)
    ax.legend(fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_ylim(bottom=0)
    plt.tight_layout()

    path = os.path.join(results_dir, "headways_over_time.png")
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def _format_hour_block(by_hour: pd.DataFrame, direction_label: str) -> list:
    """Render the per-hour comparison for a direction as report lines."""
    lines = []
    if by_hour.empty:
        return ["  (per-hour data unavailable)"]
    sub = by_hour[by_hour["direction"] == direction_label].copy()
    if sub.empty:
        return ["  (no rows for direction " + direction_label + ")"]

    lines.append(
        f"  Hour | n(pre)/n(post) |   median (min)   |  wait = E[H]/2  | wait Δ"
    )
    lines.append("  " + "-" * 70)
    for hour in sorted(sub["hour"].unique()):
        pre  = sub[(sub["hour"] == hour) & (sub["swap_period"] == "Before swap")]
        post = sub[(sub["hour"] == hour) & (sub["swap_period"] == "After swap")]
        if pre.empty or post.empty:
            continue
        n_pre  = int(pre["n"].values[0])
        n_post = int(post["n"].values[0])
        m_pre  = pre["median"].values[0]
        m_post = post["median"].values[0]
        w_pre  = pre["wait_time_min"].values[0]
        w_post = post["wait_time_min"].values[0]
        delta_w = w_post - w_pre
        h12 = (hour - 12) if hour > 12 else hour
        am_pm = "PM" if hour >= 12 else "AM"
        h12 = 12 if h12 == 0 else h12
        lines.append(
            f"  {hour:>2} ({h12:>2} {am_pm}) | {n_pre:>5,}/{n_post:<5,} "
            f"|  {m_pre:>4.2f} → {m_post:>4.2f}  "
            f"|  {w_pre:>4.2f} → {w_post:>4.2f}  | {delta_w:+.2f}"
        )
    return lines


def _format_bootstrap_block(boot: pd.DataFrame, direction_label: str) -> list:
    """Render bootstrap CI comparison for a direction as report lines."""
    if boot.empty:
        return ["  (bootstrap data unavailable)"]
    sub = boot[boot["direction"] == direction_label]
    if sub.empty:
        return ["  (no rows for direction " + direction_label + ")"]

    lines = []
    lines.append(f"  {'Bucket':<32} | median Δ (95% CI)         | wait Δ (E[H]/2, 95% CI)")
    lines.append("  " + "-" * 80)
    for _, r in sub.sort_values("time_bucket").iterrows():
        lines.append(
            f"  {r['time_bucket']:<32} | "
            f"{r['median_delta']:+.2f} [{r['median_delta_ci_low']:+.2f}, "
            f"{r['median_delta_ci_high']:+.2f}]  | "
            f"{r['wait_time_delta']:+.2f} [{r['wait_time_delta_ci_low']:+.2f}, "
            f"{r['wait_time_delta_ci_high']:+.2f}]"
        )
    return lines


def _format_monthly_block(monthly: pd.DataFrame, direction_label: str) -> list:
    """Render monthly stratification for a direction as report lines."""
    if monthly.empty:
        return ["  (monthly data unavailable)"]
    sub = monthly[monthly["direction"] == direction_label].copy()
    if sub.empty:
        return ["  (no rows for direction " + direction_label + ")"]

    lines = []
    lines.append(
        f"  Month   | period       |    n   | median | wait = E[H]/2"
    )
    lines.append("  " + "-" * 60)
    for _, r in sub.sort_values("arrival_month").iterrows():
        lines.append(
            f"  {r['arrival_month']} | {r['swap_period']:<12} | "
            f"{int(r['n']):>5,} | {r['median']:>5.2f}  | {r['wait_time_min']:>5.2f}"
        )
    return lines


def write_report(df_hw: pd.DataFrame,
                  summary: pd.DataFrame,
                  results_dir: str,
                  *,
                  summary_clean: pd.DataFrame | None = None,
                  by_hour: pd.DataFrame | None = None,
                  monthly: pd.DataFrame | None = None,
                  boot: pd.DataFrame | None = None):

    def med(day_type, bucket_prefix, direction, swap):
        sub = df_hw[
            (df_hw["day_type"]    == day_type) &
            df_hw["time_bucket"].str.startswith(bucket_prefix) &
            (df_hw["direction"]   == direction) &
            (df_hw["swap_period"] == swap)
        ]["headway_min"]
        return f"{sub.median():.1f}" if not sub.empty else "N/A"

    def p90(day_type, bucket_prefix, direction, swap):
        sub = df_hw[
            (df_hw["day_type"]    == day_type) &
            df_hw["time_bucket"].str.startswith(bucket_prefix) &
            (df_hw["direction"]   == direction) &
            (df_hw["swap_period"] == swap)
        ]["headway_min"]
        return f"{sub.quantile(0.90):.1f}" if not sub.empty else "N/A"

    def chg(day_type, bucket_prefix, direction):
        b = df_hw[
            (df_hw["day_type"]    == day_type) &
            df_hw["time_bucket"].str.startswith(bucket_prefix) &
            (df_hw["direction"]   == direction) &
            (df_hw["swap_period"] == "Before swap")
        ]["headway_min"]
        a = df_hw[
            (df_hw["day_type"]    == day_type) &
            df_hw["time_bucket"].str.startswith(bucket_prefix) &
            (df_hw["direction"]   == direction) &
            (df_hw["swap_period"] == "After swap")
        ]["headway_min"]
        if b.empty or a.empty:
            return "N/A"
        d = a.median() - b.median()
        p = d / b.median() * 100
        w = "LONGER ▲" if d > 0 else "SHORTER ▼"
        return f"{abs(d):.1f} min {w} ({abs(p):.0f}%)"

    report = f"""
ROOSEVELT ISLAND SUBWAY — HEADWAY ANALYSIS
F/M Train Swap | Before vs. After December 8, 2025
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Station: Roosevelt Island (GTFS: B06N northbound, B06S southbound)
================================================================

STUDY DESIGN
  Pre-swap:  Oct 1 – Dec 7, 2025
  Post-swap: Dec 8, 2025 – Feb 15, 2026
  Time buckets (identical clock boundaries on all days):
    1. Early AM          12:00 AM –  6:00 AM
    2. Morning Rush       6:00 AM –  9:00 AM  (weekdays)
       Morning            6:00 AM –  9:00 AM  (weekends)
    3. Midday             9:00 AM –  4:00 PM
    4. Evening Rush       4:00 PM –  7:00 PM  (weekdays)
       Afternoon/Evening  4:00 PM –  7:00 PM  (weekends)
    5. Night              7:00 PM – 12:00 AM
  Swap active: Weekdays only, 6:00 AM – 9:30 PM
    Fully affects:    Morning Rush, Midday, Evening Rush
    Partially affects: Night (7:00–9:30 PM only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEEKDAYS — Southbound (→ Manhattan) [primary commute direction]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[2] Morning Rush (6–9 AM) ★ SWAP AFFECTS THIS PERIOD
  Before: median {med('Weekday','2:','N','Before swap')} min | 90th pct {p90('Weekday','2:','N','Before swap')} min
  After:  median {med('Weekday','2:','N','After swap')} min | 90th pct {p90('Weekday','2:','N','After swap')} min
  Change: {chg('Weekday','2:','N')}

[3] Midday (9 AM–4 PM) ★ SWAP AFFECTS THIS PERIOD
  Before: median {med('Weekday','3:','N','Before swap')} min | 90th pct {p90('Weekday','3:','N','Before swap')} min
  After:  median {med('Weekday','3:','N','After swap')} min | 90th pct {p90('Weekday','3:','N','After swap')} min
  Change: {chg('Weekday','3:','N')}

[4] Evening Rush (4–7 PM) ★ SWAP AFFECTS THIS PERIOD
  Before: median {med('Weekday','4:','N','Before swap')} min | 90th pct {p90('Weekday','4:','N','Before swap')} min
  After:  median {med('Weekday','4:','N','After swap')} min | 90th pct {p90('Weekday','4:','N','After swap')} min
  Change: {chg('Weekday','4:','N')}

[5] Night (7 PM–midnight) ★ PARTIALLY AFFECTED (7–9:30 PM within swap window)
  Before: median {med('Weekday','5:','N','Before swap')} min | 90th pct {p90('Weekday','5:','N','Before swap')} min
  After:  median {med('Weekday','5:','N','After swap')} min | 90th pct {p90('Weekday','5:','N','After swap')} min
  Change: {chg('Weekday','5:','N')}

[1] Early AM (12–6 AM) — F train both periods
  Before: median {med('Weekday','1:','N','Before swap')} min | 90th pct {p90('Weekday','1:','N','Before swap')} min
  After:  median {med('Weekday','1:','N','After swap')} min | 90th pct {p90('Weekday','1:','N','After swap')} min
  Change: {chg('Weekday','1:','N')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEEKENDS — Southbound (→ Manhattan)
All periods: F train both before and after swap.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1] Early AM (12–6 AM)
  Before: median {med('Weekend','1:','N','Before swap')} min | After: {med('Weekend','1:','N','After swap')} min | Change: {chg('Weekend','1:','N')}

[2] Morning (6–9 AM)
  Before: median {med('Weekend','2:','N','Before swap')} min | After: {med('Weekend','2:','N','After swap')} min | Change: {chg('Weekend','2:','N')}

[3] Midday (9 AM–4 PM)
  Before: median {med('Weekend','3:','N','Before swap')} min | After: {med('Weekend','3:','N','After swap')} min | Change: {chg('Weekend','3:','N')}

[4] Afternoon/Evening (4–7 PM)
  Before: median {med('Weekend','4:','N','Before swap')} min | After: {med('Weekend','4:','N','After swap')} min | Change: {chg('Weekend','4:','N')}

[5] Night (7 PM–midnight)
  Before: median {med('Weekend','5:','N','Before swap')} min | After: {med('Weekend','5:','N','After swap')} min | Change: {chg('Weekend','5:','N')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FULL STATISTICS TABLE  (median, mean, tails, MTA-style wait time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Columns: wait_time_min = mean_headway / 2 — the MTA's own definition of
                          "average wait time" used in the April 2026 letter.
         pct_over_10   = % of headway intervals exceeding 10 minutes
{summary.to_string(index=False)}
"""

    extra_lines = []
    if boot is not None and not boot.empty:
        extra_lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"BOOTSTRAP CIs ON PRE→POST DELTAS  ({N_BOOTSTRAP} resamples, 95% CI)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  Tests whether the realized increase is distinguishable from MTA's",
            "  September 2025 commitment of ~1 minute additional wait.",
            "",
            "  Southbound (→ Manhattan, AM commute):",
        ]
        extra_lines += _format_bootstrap_block(boot, "Southbound (→ Manhattan)")
        extra_lines += ["", "  Northbound (→ Queens):"]
        extra_lines += _format_bootstrap_block(boot, "Northbound (→ Queens/Home)")
        extra_lines += [""]

    # ── Per-hour section ────────────────────────────────────────────────
    if by_hour is not None and not by_hour.empty:
        extra_lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "PER-HOUR COMPARISON (matched 1-hr windows; weekday only)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  Lets us answer the MTA on its own terms — their letter cites",
            "  \"during the 8 AM hour—the increase in average wait is about 1.3",
            "  minutes.\" Here is each rush + adjacent hour, weekday, both",
            "  directions, with median headway and MTA-style wait = E[H]/2.",
            "",
            "  Southbound (→ Manhattan):",
        ]
        extra_lines += _format_hour_block(by_hour, "Southbound (→ Manhattan)")
        extra_lines += ["", "  Northbound (→ Queens/Home):"]
        extra_lines += _format_hour_block(by_hour, "Northbound (→ Queens/Home)")
        extra_lines += [""]

    # ── Monthly stratification section ───────────────────────────────────
    if monthly is not None and not monthly.empty:
        extra_lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "MONTHLY STRATIFICATION — STEADY STATE vs SHAKEDOWN",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  The MTA letter argues that \"the first months of the new service",
            "  pattern were affected by systemwide incidents and historic winter",
            "  storms.\" This breakdown shows weekday peak headways month by",
            "  month so the steady-state period (Feb-Mar 2026, post-storm) can",
            "  speak for itself.",
            "",
            "  Southbound (→ Manhattan):",
        ]
        extra_lines += _format_monthly_block(monthly, "Southbound (→ Manhattan)")
        extra_lines += ["", "  Northbound (→ Queens/Home):"]
        extra_lines += _format_monthly_block(monthly, "Northbound (→ Queens/Home)")
        extra_lines += [""]

    # ── Clean-days side-by-side ──────────────────────────────────────────
    if summary_clean is not None and not summary_clean.empty:
        extra_lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "CLEAN-DAYS VARIANT (excludes holiday weeks + Jan 25–Jan 31 storm)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  Same summary as above, restricted to non-holiday non-storm",
            "  weekdays. Closes the MTA's \"early months were noisy\" loophole.",
            "",
            summary_clean.to_string(index=False),
            "",
        ]

    report = report + "\n".join(extra_lines)

    path = os.path.join(results_dir, "results_report.txt")
    with open(path, "w") as f:
        f.write(report)
    print(f"Saved: {path}")
    print(report)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df_raw = load_all_data(RAW_DATA_DIR)
    df     = add_analysis_columns(df_raw)

    # ── Phase 1: Validation ──────────────────────────────────────────────
    verify_direction_convention(df)
    validate_data_completeness(df)

    df_hw  = compute_headways(df)

    hw_path = os.path.join(RESULTS_DIR, "roosevelt_island_headways.csv")
    df_hw.to_csv(hw_path, index=False)
    print(f"Headway data saved to: {hw_path}\n")

    summary = summarize_headways(df_hw)
    summary.to_csv(os.path.join(RESULTS_DIR, "headway_summary.csv"), index=False)
    print("Summary statistics:")
    print(summary.to_string(index=False))
    print()

    # ── Phase 2: Extended analysis ───────────────────────────────────────
    analyze_storm_impact(df_hw)
    analyze_holiday_impact(df_hw)
    analyze_weekend_control_group(df_hw)

    # ── Phase 2b: Methodology rebuttals to MTA letter ────────────────────
    print("── Per-hour weekday comparison (rush + adjacent) ───────────────")
    by_hour = summarize_by_hour(df_hw)
    by_hour.to_csv(os.path.join(RESULTS_DIR, "headway_per_hour.csv"), index=False)
    print(by_hour.to_string(index=False)); print()

    print("── Monthly stratification (peak hours, weekday) ────────────────")
    monthly = summarize_by_month(df_hw)
    monthly.to_csv(os.path.join(RESULTS_DIR, "headway_monthly.csv"), index=False)
    print(monthly.to_string(index=False)); print()

    print(f"── Bootstrap pre/post CIs ({N_BOOTSTRAP} resamples) ────────────────────")
    boot = bootstrap_pre_post_ci(df_hw)
    boot.to_csv(os.path.join(RESULTS_DIR, "headway_bootstrap_ci.csv"), index=False)
    print(boot.to_string(index=False)); print()

    print("── Clean-days variant (no holiday weeks, no storm window) ──────")
    df_hw_clean = filter_clean_days(df_hw)
    summary_clean = summarize_headways(df_hw_clean)
    summary_clean.to_csv(
        os.path.join(RESULTS_DIR, "headway_summary_clean_days.csv"), index=False
    )
    print(f"  Clean days: {df_hw_clean['arrival_date'].nunique()} of "
          f"{df_hw['arrival_date'].nunique()} weekdays retained.")
    print(summary_clean.to_string(index=False)); print()

    # ── Phase 3: Charts + report ─────────────────────────────────────────
    plot_distribution(df_hw, "Weekday", RESULTS_DIR)
    plot_distribution(df_hw, "Weekend", RESULTS_DIR)
    plot_hourly_headways(df_hw, RESULTS_DIR)
    plot_daily_median_headway(df_hw, RESULTS_DIR)
    write_report(df_hw, summary, RESULTS_DIR,
                  summary_clean=summary_clean, by_hour=by_hour,
                  monthly=monthly, boot=boot)

    print(f"\nAll results saved to: {os.path.abspath(RESULTS_DIR)}/")


if __name__ == "__main__":
    main()
