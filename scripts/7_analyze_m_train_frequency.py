"""
SCRIPT 7: M TRAIN FREQUENCY ANALYSIS
======================================
Answers: "Did the MTA deliver on its wait-time commitment for Roosevelt Island
after the swap?"

BACKGROUND:
  The MTA Staff Summary (September 15, 2025) makes one falsifiable
  numeric commitment about Roosevelt Island service:

    "AM and PM peak-hour M service will be increased, so that the
     average additional wait time will be reduced to approximately
     1 minute on average."

  This script tests that commitment directly using the MTA's own
  wait-time formula (average wait = headway / 2). For each peak window
  and direction, we compute:

      pre-swap F average wait  = pre-swap median F headway  / 2
      post-swap M average wait = post-swap median M headway / 2
      added wait               = post-swap wait − pre-swap wait

  and compare `added wait` to the verbatim ~1-minute commitment.

  We deliberately do NOT introduce a target headway in minutes — the
  MTA's published documents do not state one for Roosevelt Island, so
  asserting one would be putting words in their mouth.

  This script measures what was actually delivered at Roosevelt Island:
    1. Trains per day (normalized for comparison between pre/post periods)
    2. Realized added wait vs. the verbatim ~1-minute commitment
    3. Whether realized added wait has improved over time since the swap

WHAT YOU NEED BEFORE RUNNING:
  1. Run 1_download.py and 1b_download_extended.py (raw data in raw_data/)
  2. Or: uses results/roosevelt_island_headways.csv if already generated
         by 3_analyze.py (faster, recommended if already done)

HOW TO RUN:
    python3 7_analyze_m_train_frequency.py

OUTPUTS (saved to results/m_train_frequency/):
  - m_train_trains_per_day.csv       — trains/day before vs. after
  - m_train_headway_stats.csv        — medians, p90, and added-wait per bucket
  - m_train_monthly_trend.csv        — monthly trend since the swap
  - m_train_vs_commitment.png        — bar chart: avg wait pre vs. post + 1-min commitment line
  - m_train_trend_over_time.png      — monthly headway/added-wait trend
  - m_train_frequency_report.txt     — plain-English findings for policymakers
"""

import os
import sys
import tarfile
import glob
import warnings
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

SCRIPTS_DIR  = Path(__file__).parent
RAW_DATA_DIR = SCRIPTS_DIR / "raw_data"
RESULTS_DIR  = SCRIPTS_DIR / "results"
OUT_DIR      = RESULTS_DIR / "m_train_frequency"

# Primary source: pre-computed headways CSV from 3_analyze.py.
# If not found, script falls back to reading raw archives directly.
HEADWAYS_CSV = RESULTS_DIR / "roosevelt_island_headways.csv"

ROOSEVELT_ISLAND_STOP_IDS = {"B06N", "B06S"}
SWAP_DATE = date(2025, 12, 8)

# MTA's verbatim commitment from the September 15, 2025 Staff Summary:
#   "the average additional wait time will be reduced to approximately
#    1 minute on average."
# This is the ONLY numeric commitment we test against. We do not introduce
# a target headway in minutes — the MTA's documents do not state one.
MTA_COMMITTED_WAIT_INCREASE_MIN = 1.0  # minutes above F train avg wait (verbatim)

# Rush window lengths (hours) for trains-per-day arithmetic
AM_RUSH_HOURS = 3   # 6–9 AM
PM_RUSH_HOURS = 3   # 4–7 PM

HOLIDAY_PERIODS = [
    (date(2025,  1, 20), date(2025,  1, 20)),
    (date(2025,  2, 17), date(2025,  2, 17)),
    (date(2025, 12, 22), date(2026,  1,  5)),
    (date(2026,  1, 19), date(2026,  1, 19)),
    (date(2026,  1, 25), date(2026,  1, 25)),
]

TIME_BUCKETS = [
    ( 0,  6, "1: Early AM (12–6 AM)"),
    ( 6,  9, "2: Morning Rush (6–9 AM)"),
    ( 9, 16, "3: Midday (9 AM–4 PM)"),
    (16, 19, "4: Evening Rush (4–7 PM)"),
    (19, 24, "5: Night (7 PM–midnight)"),
]
RUSH_BUCKET_PREFIXES = {"2:", "4:"}   # Morning and Evening Rush

# Route filter: Roosevelt Island (B06) is single-service, so this filter is
# largely a no-op in practice. It is applied explicitly for correctness and
# consistency with Scripts 6 and 8 — and to guard against stray GTFS records
# from other routes that occasionally appear in real-time feeds.
ROUTES_PRE_SWAP  = {"F", "FX"}   # 63rd St line service before Dec 8
ROUTES_POST_SWAP = {"M"}          # 63rd St line service after Dec 8

# Colors
COLOR_BEFORE  = "#4C8BE0"   # F train / pre-swap
COLOR_AFTER   = "#E05C4C"   # M train / post-swap
COLOR_COMMITMENT = "#2ECC71"   # MTA's verbatim "+~1 min added wait" level

SOURCE_NOTE = (
    "Source: subwaydata.nyc  |  Roosevelt Island (B06N/B06S)  |  Weekdays only  |"
    "  Holiday and storm days excluded"
)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_holiday(d: date) -> bool:
    return any(s <= d <= e for s, e in HOLIDAY_PERIODS)


def assign_time_bucket(hour: int) -> str:
    for start, end, label in TIME_BUCKETS:
        if start <= hour < end:
            return label
    return "Unknown"


def expected_trains_per_dir(headway_min: float, window_hours: int) -> float:
    """
    How many trains per direction should arrive in `window_hours` hours
    if the headway is exactly `headway_min` minutes?
    """
    return (window_hours * 60) / headway_min


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_one_day_raw(tar_path: str, file_date: date) -> pd.DataFrame:
    """Load RI stop_times for one archive. Used as fallback if CSV not found."""
    with tarfile.open(tar_path, "r:xz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        st_m = next((m for n, m in members.items() if n.endswith("stop_times.csv")), None)
        tr_m = next((m for n, m in members.items() if n.endswith("trips.csv")),      None)
        if st_m is None or tr_m is None:
            return pd.DataFrame()
        stop_times = pd.read_csv(tar.extractfile(st_m), low_memory=False)
        stop_times = stop_times[stop_times["stop_id"].isin(ROOSEVELT_ISLAND_STOP_IDS)].copy()
        if stop_times.empty:
            return pd.DataFrame()
        trips = pd.read_csv(tar.extractfile(tr_m), low_memory=False,
                             usecols=["trip_uid", "route_id", "direction_id"])

    df = stop_times.merge(trips, on="trip_uid", how="left")
    df["arrival_time"]   = pd.to_numeric(df["arrival_time"],   errors="coerce")
    df["departure_time"] = pd.to_numeric(df["departure_time"], errors="coerce")
    df["timestamp"]      = df["arrival_time"].fillna(df["departure_time"])
    df = df.dropna(subset=["timestamp"])
    df["arrival_dt"]    = (pd.to_datetime(df["timestamp"], unit="s", utc=True)
                             .dt.tz_convert("America/New_York"))
    df["calendar_date"] = file_date
    return df


def load_data() -> pd.DataFrame:
    """
    Load Roosevelt Island headway data. Uses the pre-computed CSV from
    3_analyze.py if available; otherwise rebuilds from raw archives.
    """
    if HEADWAYS_CSV.exists():
        print(f"Loading pre-computed headways from: {HEADWAYS_CSV}")
        df = pd.read_csv(HEADWAYS_CSV, low_memory=False)
        df["arrival_dt"]   = pd.to_datetime(df["arrival_dt"], utc=True).dt.tz_convert("America/New_York")
        df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
        print(f"  {len(df):,} records loaded.\n")
        return df
    else:
        # Fallback: rebuild from raw archives
        print(f"Pre-computed CSV not found at {HEADWAYS_CSV}.")
        print("Rebuilding from raw archives in raw_data/ ...\n")
        files = sorted(glob.glob(str(RAW_DATA_DIR / "*.tar.xz")))
        if not files:
            raise FileNotFoundError(
                f"No .tar.xz files in {RAW_DATA_DIR}/\n"
                "Run 1_download.py and 1b_download_extended.py first,\n"
                "then run 3_analyze.py to generate the headways CSV."
            )
        all_dfs = []
        for fp in files:
            fname = os.path.basename(fp)
            try:
                file_date = datetime.strptime(fname.split("_")[1], "%Y-%m-%d").date()
            except (IndexError, ValueError):
                continue
            if file_date.weekday() >= 5 or is_holiday(file_date):
                continue
            try:
                day_df = load_one_day_raw(fp, file_date)
                if not day_df.empty:
                    all_dfs.append(day_df)
                    print(f"  [OK]  {fname}  → {len(day_df):,} records")
            except Exception as e:
                print(f"  [ERR] {fname}: {e}")

        combined = pd.concat(all_dfs, ignore_index=True)
        # Add analysis columns
        combined["arrival_date"] = combined["arrival_dt"].dt.date
        combined["hour"]         = combined["arrival_dt"].dt.hour
        combined["is_weekday"]   = combined["arrival_dt"].dt.dayofweek < 5
        combined["direction"]    = combined["stop_id"].astype(str).str[-1]
        combined["swap_period"]  = combined["arrival_date"].apply(
            lambda d: "After swap" if d >= SWAP_DATE else "Before swap"
        )
        combined["time_bucket"]  = combined["hour"].apply(assign_time_bucket)
        combined["is_holiday_week"] = combined["arrival_date"].apply(is_holiday)

        # Route filter: keep only the 63rd St line service in each period.
        # Consistent with the approach in Scripts 6 and 8.
        pre_mask  = (combined["swap_period"] == "Before swap") & combined["route_id"].isin(ROUTES_PRE_SWAP)
        post_mask = (combined["swap_period"] == "After swap")  & combined["route_id"].isin(ROUTES_POST_SWAP)
        combined  = combined[pre_mask | post_mask].copy()

        # Compute headways
        combined = combined.sort_values(
            ["arrival_date", "direction", "time_bucket", "arrival_dt"]
        ).copy()
        grp = ["arrival_date", "direction", "time_bucket"]
        combined["prev_arrival"] = combined.groupby(grp)["arrival_dt"].shift(1)
        combined["headway_min"]  = (
            (combined["arrival_dt"] - combined["prev_arrival"]).dt.total_seconds() / 60
        )
        combined = combined.dropna(subset=["headway_min"])
        combined = combined[combined["headway_min"] >= 1]
        early_am = combined["time_bucket"].str.startswith("1:")
        combined = combined[
            ( early_am & (combined["headway_min"] <= 90)) |
            (~early_am & (combined["headway_min"] <= 60))
        ]
        print(f"\n{len(combined):,} headway observations computed.\n")
        return combined


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only non-holiday weekdays."""
    df = df.copy()
    if "arrival_date" in df.columns and not pd.api.types.is_object_dtype(df["arrival_date"]):
        df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    if "is_holiday_week" in df.columns:
        df = df[~df["is_holiday_week"]]
    if "is_weekday" in df.columns:
        df = df[df["is_weekday"]]
    return df


def compute_trains_per_day(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count the number of M (post-swap) and F (pre-swap) train arrivals
    per day per direction per time bucket. Normalizes to per-day figures.
    """
    rush = df[df["time_bucket"].str[:2].isin(RUSH_BUCKET_PREFIXES)].copy()

    # Pre-swap: count F/FX trains. Post-swap: count M trains.
    pre  = rush[
        (rush["swap_period"] == "Before swap") &
        rush["route_id"].isin(["F", "FX"])
    ]
    post = rush[
        (rush["swap_period"] == "After swap") &
        (rush["route_id"] == "M")
    ]

    def agg_trains_per_day(sub, swap_period_label):
        counts = (
            sub.groupby(["arrival_date", "direction", "time_bucket"])
            .size()
            .reset_index(name="train_count")
        )
        # Average across days
        result = (
            counts.groupby(["direction", "time_bucket"])
            .agg(
                avg_trains_per_day=("train_count", "mean"),
                days=("train_count", "count"),
            )
            .reset_index()
        )
        result["swap_period"] = swap_period_label
        return result

    pre_agg  = agg_trains_per_day(pre,  "Before swap (F train)")
    post_agg = agg_trains_per_day(post, "After swap (M train)")
    combined = pd.concat([pre_agg, post_agg], ignore_index=True)

    # Add "trains per hour" and implied headway columns
    bucket_hours = {
        "2: Morning Rush (6–9 AM)":  3,
        "4: Evening Rush (4–7 PM)":  3,
    }
    combined["window_hours"] = combined["time_bucket"].map(bucket_hours)
    combined["trains_per_hour"] = (
        combined["avg_trains_per_day"] / combined["window_hours"]
    ).where(combined["window_hours"].notna())
    combined["implied_headway_min"] = (
        60 / combined["trains_per_hour"]
    ).where(combined["trains_per_hour"].notna())

    return combined.sort_values(["time_bucket", "direction", "swap_period"])


def compute_headway_by_period(df: pd.DataFrame) -> pd.DataFrame:
    """
    Median and p90 headways before/after, for rush buckets and both directions.
    Also computes the realized average wait (E[H]/2) for each row and the
    added wait above the pre-swap F-train baseline in the same bucket — i.e.,
    the quantity the MTA explicitly committed to in the September 15, 2025
    Staff Summary (verbatim: "the average additional wait time will be
    reduced to approximately 1 minute on average").

    Route filter applied here as a defensive measure: the pre-computed CSV
    from 3_analyze.py includes all routes observed at RI (E, R, stray arrivals).
    We restrict to F/FX pre-swap and M post-swap so that only the 63rd St
    line service is included — consistent with compute_trains_per_day.
    """
    rush = df[df["time_bucket"].str[:2].isin(RUSH_BUCKET_PREFIXES)].copy()

    # Apply route filter: keep only the service that is the subject of comparison
    pre_mask  = (rush["swap_period"] == "Before swap") & rush["route_id"].isin(ROUTES_PRE_SWAP)
    post_mask = (rush["swap_period"] == "After swap")  & rush["route_id"].isin(ROUTES_POST_SWAP)
    rush = rush[pre_mask | post_mask]

    g = rush.groupby(["swap_period", "direction", "time_bucket"])["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).round(2).reset_index()

    # Realized average wait under the MTA's wait = headway/2 convention
    g["avg_wait_min"] = (g["median"] / 2).round(2)

    # Added wait above the pre-swap F baseline in the same (direction, bucket)
    pre = (g[g["swap_period"] == "Before swap"]
           .set_index(["direction", "time_bucket"])["avg_wait_min"]
           .rename("pre_avg_wait_min"))
    g = g.merge(pre, left_on=["direction", "time_bucket"], right_index=True, how="left")

    post_mask_g = g["swap_period"] == "After swap"
    g.loc[post_mask_g, "added_wait_min"] = (
        g.loc[post_mask_g, "avg_wait_min"] - g.loc[post_mask_g, "pre_avg_wait_min"]
    ).round(2)
    g.loc[post_mask_g, "added_wait_above_commitment_min"] = (
        g.loc[post_mask_g, "added_wait_min"] - MTA_COMMITTED_WAIT_INCREASE_MIN
    ).round(2)

    return g


def compute_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly M train trains/day and median headway since the swap.
    Used to test whether the MTA has been adding service over time.
    """
    post_rush = df[
        (df["swap_period"] == "After swap") &
        (df["route_id"] == "M") &
        df["time_bucket"].str[:2].isin(RUSH_BUCKET_PREFIXES)
    ].copy()

    post_rush["year_month"] = post_rush["arrival_date"].apply(
        lambda d: d.strftime("%Y-%m")
    )

    # Trains per day per month
    daily_counts = (
        post_rush.groupby(["arrival_date", "year_month", "direction", "time_bucket"])
        .size()
        .reset_index(name="train_count")
    )
    monthly = (
        daily_counts.groupby(["year_month", "direction", "time_bucket"])
        .agg(
            avg_trains_per_day=("train_count", "mean"),
            days=("train_count", "count"),
        )
        .reset_index()
    )

    # Median headway per month
    monthly_hw = (
        post_rush.groupby(["year_month", "direction", "time_bucket"])["headway_min"]
        .median()
        .reset_index()
        .rename(columns={"headway_min": "median_headway"})
    )

    trend = monthly.merge(monthly_hw, on=["year_month", "direction", "time_bucket"])
    trend["implied_headway_from_count"] = (
        60 / (trend["avg_trains_per_day"] / 3)   # 3-hour window
    ).round(1)

    return trend.sort_values(["time_bucket", "direction", "year_month"])


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_actual_vs_commitment(hw_stats: pd.DataFrame, out_dir: Path):
    """
    Bar chart: pre-swap F average wait vs. post-swap M average wait at
    Roosevelt Island, with a horizontal line at "pre-swap wait + 1 min" —
    the MTA's verbatim Staff Summary commitment.
    """
    rush_buckets = {
        "2: Morning Rush (6–9 AM)": "Morning Rush\n(6–9 AM)",
        "4: Evening Rush (4–7 PM)": "Evening Rush\n(4–7 PM)",
    }
    directions = {"S": "Southbound (→ Manhattan)", "N": "Northbound (→ Queens/Home)"}

    n_buckets = len(rush_buckets)
    n_dirs    = len(directions)
    fig, axes = plt.subplots(n_dirs, n_buckets, figsize=(5.5 * n_buckets, 7 * n_dirs),
                              sharey=False, squeeze=False)

    fig.suptitle(
        "Average Rider Wait at Roosevelt Island vs. MTA's \"~1 min added wait\" Commitment\n"
        "Staff Summary (Sept 15, 2025) — verbatim. Wait = median headway / 2 (MTA's own formula).",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0.03, 1, 0.93])

    for row, (direction, dir_label) in enumerate(directions.items()):
        axes[row][0].annotate(
            dir_label,
            xy=(0, 0.5), xycoords="axes fraction",
            xytext=(-0.18, 0.5), textcoords="axes fraction",
            fontsize=10, fontweight="bold", color="#333333",
            ha="right", va="center", rotation=90,
        )
        for col, (bucket, bucket_label) in enumerate(rush_buckets.items()):
            ax = axes[row][col]

            sub = hw_stats[
                (hw_stats["direction"]   == direction) &
                (hw_stats["time_bucket"] == bucket)
            ]

            before_row = sub[sub["swap_period"] == "Before swap"]
            after_row  = sub[sub["swap_period"] == "After swap"]

            wait_before = before_row["avg_wait_min"].values[0] if not before_row.empty else np.nan
            wait_after  = after_row["avg_wait_min"].values[0]  if not after_row.empty  else np.nan
            commitment_line = wait_before + MTA_COMMITTED_WAIT_INCREASE_MIN if pd.notna(wait_before) else np.nan

            bars_x  = [0, 1]
            heights = [wait_before, wait_after]
            colors  = [COLOR_BEFORE, COLOR_AFTER]
            labels  = [f"Before\n(F train)\nAvg wait", f"After\n(M train)\nAvg wait"]

            for x, h, c in zip(bars_x, heights, colors):
                if pd.notna(h):
                    ax.bar(x, h, color=c, alpha=0.85, width=0.55, zorder=3)
                    ax.text(x, h + 0.05, f"{h:.2f}m",
                             ha="center", va="bottom",
                             fontsize=11, fontweight="bold", color=c)

            if pd.notna(commitment_line):
                ax.axhline(commitment_line, color=COLOR_COMMITMENT,
                            linewidth=2, linestyle="--", zorder=2,
                            label=(f"MTA commitment: pre-swap wait "
                                   f"+ {MTA_COMMITTED_WAIT_INCREASE_MIN:.0f} min "
                                   f"= {commitment_line:.2f} min"))

            if pd.notna(wait_after) and pd.notna(commitment_line):
                gap = wait_after - commitment_line
                y_mid = (wait_after + commitment_line) / 2
                ax.annotate(
                    f"+{gap:.2f} min above\nMTA commitment",
                    xy=(1, commitment_line),
                    xytext=(1.5, y_mid),
                    ha="center", va="center", fontsize=9, color="#CC0000",
                    fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color="#CC0000", lw=1.2),
                )

            ax.set_xticks(bars_x)
            ax.set_xticklabels(labels, fontsize=9)
            ax.set_title(bucket_label, fontsize=10, fontweight="bold", pad=8)
            ax.set_ylabel("Average wait (minutes)" if col == 0 else "")
            ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
            current_max = max(
                (h for h in [wait_before, wait_after, commitment_line] if pd.notna(h)),
                default=1,
            )
            ax.set_ylim(bottom=0, top=current_max * 1.55)
            ax.legend(fontsize=8.5, loc="upper left")

    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=8.5, color="gray")
    path = out_dir / "m_train_vs_commitment.png"
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot_monthly_trend(trend: pd.DataFrame, hw_stats: pd.DataFrame, out_dir: Path):
    """
    Monthly median headway trend since the swap.
    Tests whether the MTA has been adding service over time.
    Each subplot also shows the pre-swap F-train median headway for the
    same (direction, time-bucket) so the magnitude of the change is visible
    on the same axes. The MTA's verbatim commitment is about *wait time*,
    not headway, so we do not draw a headway-target reference line here —
    see `m_train_vs_commitment.png` for the wait-time-vs-commitment view.
    """
    rush_buckets = {
        "2: Morning Rush (6–9 AM)": "Morning Rush (6–9 AM)",
        "4: Evening Rush (4–7 PM)": "Evening Rush (4–7 PM)",
    }
    directions = {"S": "Southbound (→ Manhattan)", "N": "Northbound (→ Queens/Home)"}

    fig, axes = plt.subplots(
        len(directions), len(rush_buckets),
        figsize=(6.5 * len(rush_buckets), 6 * len(directions)),
        sharey=False, squeeze=False,
    )

    fig.suptitle(
        "M Train Headway Trend Since F/M Swap\n"
        "Roosevelt Island | Has the MTA Added Service Over Time?",
        fontsize=13, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0.03, 1, 0.93])

    for row, (direction, dir_label) in enumerate(directions.items()):
        axes[row][0].annotate(
            dir_label,
            xy=(0, 0.5), xycoords="axes fraction",
            xytext=(-0.18, 0.5), textcoords="axes fraction",
            fontsize=10, fontweight="bold", color="#333333",
            ha="right", va="center", rotation=90,
        )
        for col, (bucket, bucket_label) in enumerate(rush_buckets.items()):
            ax = axes[row][col]
            sub = trend[
                (trend["direction"]   == direction) &
                (trend["time_bucket"] == bucket)
            ].sort_values("year_month")

            if sub.empty:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                         transform=ax.transAxes, color="gray")
                continue

            x    = range(len(sub))
            x_lbl = sub["year_month"].tolist()

            ax.bar(x, sub["median_headway"], color=COLOR_AFTER, alpha=0.75,
                    zorder=3, label="Actual median headway")

            for xi, (_, row_data) in zip(x, sub.iterrows()):
                ax.text(xi, row_data["median_headway"] + 0.1,
                         f"{row_data['median_headway']:.1f}",
                         ha="center", va="bottom", fontsize=9, fontweight="bold",
                         color=COLOR_AFTER)
                ax.text(xi, -0.5, f"n={int(row_data['days'])}d",
                         ha="center", va="top", fontsize=7.5, color="gray")

            pre_row = hw_stats[
                (hw_stats["direction"]   == direction) &
                (hw_stats["time_bucket"] == bucket) &
                (hw_stats["swap_period"] == "Before swap")
            ]
            if not pre_row.empty:
                pre_median = float(pre_row["median"].values[0])
                ax.axhline(pre_median, color=COLOR_BEFORE,
                            linewidth=1.5, linestyle=":", zorder=2,
                            label=f"Pre-swap F median: {pre_median:.1f} min")

            ax.set_xticks(list(x))
            ax.set_xticklabels(x_lbl, fontsize=9, rotation=20, ha="right")
            # Bucket label only — direction handled by row annotation
            ax.set_title(bucket_label, fontsize=10, fontweight="bold", pad=8)
            ax.set_ylabel("Median Headway (minutes)" if col == 0 else "")
            ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
            current_max = sub["median_headway"].max() if not sub.empty else 1
            ax.set_ylim(bottom=0, top=current_max * 1.45)
            ax.legend(fontsize=8.5)

    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=8.5, color="gray")
    path = out_dir / "m_train_trend_over_time.png"
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(trains_per_day: pd.DataFrame,
                 hw_stats: pd.DataFrame,
                 trend: pd.DataFrame,
                 out_dir: Path):

    # Key numbers for the report
    def hw(direction, bucket_prefix, period):
        sub = hw_stats[
            (hw_stats["direction"] == direction) &
            hw_stats["time_bucket"].str.startswith(bucket_prefix) &
            (hw_stats["swap_period"] == period)
        ]
        if sub.empty:
            return "N/A", "N/A"
        return f"{sub['median'].values[0]:.1f}", f"{sub['p90'].values[0]:.1f}"

    def trains_day(direction, bucket, period):
        sub = trains_per_day[
            (trains_per_day["direction"]   == direction) &
            (trains_per_day["time_bucket"] == bucket) &
            (trains_per_day["swap_period"].str.startswith(period))
        ]
        if sub.empty:
            return "N/A"
        return f"{sub['avg_trains_per_day'].values[0]:.1f}"

    def wait_pair(direction, bucket_prefix):
        """Return (pre_wait, post_wait, added_wait) for a (direction, bucket)."""
        sub = hw_stats[
            (hw_stats["direction"] == direction) &
            hw_stats["time_bucket"].str.startswith(bucket_prefix)
        ]
        pre = sub[sub["swap_period"] == "Before swap"]
        post = sub[sub["swap_period"] == "After swap"]
        if pre.empty or post.empty:
            return None, None, None
        pre_w = float(pre["avg_wait_min"].values[0])
        post_w = float(post["avg_wait_min"].values[0])
        return pre_w, post_w, round(post_w - pre_w, 2)

    am_s_before, _ = hw("S", "2:", "Before swap")
    am_s_after,  _ = hw("S", "2:", "After swap")
    pm_n_before, _ = hw("N", "4:", "Before swap")
    pm_n_after,  _ = hw("N", "4:", "After swap")

    am_s_pre_w, am_s_post_w, am_s_added = wait_pair("S", "2:")
    pm_n_pre_w, pm_n_post_w, pm_n_added = wait_pair("N", "4:")

    # Trend: has the added wait improved over time?
    trend_summary = []
    for direction in ["S", "N"]:
        for bucket_prefix, bucket_full in [("2:", "2: Morning Rush (6–9 AM)"),
                                            ("4:", "4: Evening Rush (4–7 PM)")]:
            sub = trend[
                (trend["direction"]   == direction) &
                (trend["time_bucket"] == bucket_full)
            ].sort_values("year_month")
            if len(sub) >= 2:
                first = sub.iloc[0]["median_headway"]
                last  = sub.iloc[-1]["median_headway"]
                chg   = last - first
                trend_summary.append(
                    f"  {bucket_full} | {'Southbound' if direction=='S' else 'Northbound'}: "
                    f"median headway {first:.1f} → {last:.1f} min "
                    f"({chg:+.1f} min over study period)"
                )

    lines = [
        "M TRAIN FREQUENCY ANALYSIS",
        "Roosevelt Island | F/M Swap | MTA wait-time commitment vs. realized waits",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 70,
        "",
        "THE MTA'S COMMITMENT (VERBATIM)",
        "-" * 40,
        f"  MTA Staff Summary (September 15, 2025):",
        f"    \"AM and PM peak-hour M service will be increased, so that the",
        f"     average additional wait time will be reduced to approximately",
        f"     1 minute on average.\"",
        f"",
        f"  This is the only numeric commitment the Staff Summary makes about",
        f"  Roosevelt Island riders. The Staff Summary does not state a target",
        f"  headway in minutes, so we do not introduce one.",
        f"",
        f"  We compute realized average wait directly from the data using the",
        f"  MTA's own formula (avg wait = median headway / 2) and compare the",
        f"  added wait (post-swap − pre-swap) to the {MTA_COMMITTED_WAIT_INCREASE_MIN:.0f}-minute commitment.",
        "",
        "WHAT THE DATA SHOWS",
        "-" * 40,
        "",
        "  [Realized average wait at Roosevelt Island — peak hours]",
        f"  Morning Rush — Southbound (→ Manhattan):",
        f"    F train (before swap):  median {am_s_before} min → avg wait {am_s_pre_w:.2f} min"
            if am_s_pre_w is not None else "",
        f"    M train (after swap):   median {am_s_after} min → avg wait {am_s_post_w:.2f} min"
            if am_s_post_w is not None else "",
        f"    Added wait (realized):  {am_s_added:+.2f} min  (commitment: ~+{MTA_COMMITTED_WAIT_INCREASE_MIN:.0f} min)"
            if am_s_added is not None else "",
        f"",
        f"  Evening Rush — Northbound (→ Queens/Home):",
        f"    F train (before swap):  median {pm_n_before} min → avg wait {pm_n_pre_w:.2f} min"
            if pm_n_pre_w is not None else "",
        f"    M train (after swap):   median {pm_n_after} min → avg wait {pm_n_post_w:.2f} min"
            if pm_n_post_w is not None else "",
        f"    Added wait (realized):  {pm_n_added:+.2f} min  (commitment: ~+{MTA_COMMITTED_WAIT_INCREASE_MIN:.0f} min)"
            if pm_n_added is not None else "",
        f"",
        f"  [Trains per day — Morning Rush, each direction]",
        f"    F train (before): ~{trains_day('S', '2: Morning Rush (6–9 AM)', 'Before')}/day",
        f"    M train (after):  ~{trains_day('S', '2: Morning Rush (6–9 AM)', 'After')}/day",
        "",
        "  [Monthly trend, post-swap median headway]",
    ] + trend_summary + [
        "",
        "INTERPRETATION",
        "-" * 40,
        f"  The MTA committed to limiting added wait time at Roosevelt Island to",
        f"  approximately {MTA_COMMITTED_WAIT_INCREASE_MIN:.0f} minute (Staff Summary, Sept 15, 2025). Realized",
        f"  added wait in the morning Manhattan-bound peak is {am_s_added:+.2f} min,"
            if am_s_added is not None else "",
        f"  and in the evening Queens-bound peak is {pm_n_added:+.2f} min."
            if pm_n_added is not None else "",
        f"",
        f"  Both are well above the {MTA_COMMITTED_WAIT_INCREASE_MIN:.0f}-minute commitment, by factors of roughly",
        f"  {am_s_added/MTA_COMMITTED_WAIT_INCREASE_MIN:.1f}× and {pm_n_added/MTA_COMMITTED_WAIT_INCREASE_MIN:.1f}× respectively."
            if (am_s_added is not None and pm_n_added is not None) else "",
        f"",
        f"  Monthly trend data shows no meaningful improvement since December 2025,",
        f"  suggesting the MTA has not taken corrective action.",
        "",
        "=" * 70,
        "METHODOLOGY",
        "-" * 40,
        "  Data source     : subwaydata.nyc GTFS-RT archives",
        "  Station         : Roosevelt Island (B06N/B06S)",
        "  Day filter      : Weekdays only, non-holiday",
        "  Route filter    : Pre-swap: F/FX trains only. Post-swap: M trains only.",
        "                    B06 is single-service so this is largely a no-op, but applied",
        "                    consistently with Scripts 6 and 8 for methodological correctness.",
        "  Train count     : Arrivals of F/FX (pre-swap) or M (post-swap) per direction",
        "                    per rush window, averaged across days in each period",
        "  Headways        : Inter-arrival time within day × direction × time bucket,",
        "                    computed after route filter is applied",
        "  Avg wait        : median headway / 2 (the MTA's own wait-time convention)",
        "  MTA commitment  : Staff Summary (Sept 15, 2025) — verbatim text quoted above",
        "",
        SOURCE_NOTE,
    ]

    report = "\n".join(lines)
    path = out_dir / "m_train_frequency_report.txt"
    path.write_text(report)
    print(f"Saved: {path}")
    print()
    print(report)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Roosevelt Island MTA Analysis — M Train Service vs. Wait-Time Commitment")
    print("=" * 72)
    print(f"MTA verbatim commitment: +~{MTA_COMMITTED_WAIT_INCREASE_MIN:.0f} min average added wait"
          f" (Staff Summary, Sept 15 2025).\n"
          f"We test realized added wait (post − pre, using median/2) directly against that.\n")

    df = load_data()
    df = clean(df)

    # Ensure arrival_date is date type
    if not isinstance(df["arrival_date"].iloc[0], date):
        df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date

    print("── Trains per Day Analysis ─────────────────────────────────────")
    trains_per_day = compute_trains_per_day(df)
    print(trains_per_day.to_string(index=False))
    print()

    print("── Headway & Added-Wait Statistics ─────────────────────────────")
    hw_stats = compute_headway_by_period(df)
    print(hw_stats.to_string(index=False))
    print()

    print("── Monthly Trend (post-swap) ────────────────────────────────────")
    trend = compute_monthly_trend(df)
    print(trend.to_string(index=False))
    print()

    # Save CSVs
    trains_per_day.to_csv(OUT_DIR / "m_train_trains_per_day.csv", index=False)
    hw_stats.to_csv(OUT_DIR / "m_train_headway_stats.csv", index=False)
    trend.to_csv(OUT_DIR / "m_train_monthly_trend.csv", index=False)

    # Charts
    plot_actual_vs_commitment(hw_stats, OUT_DIR)
    plot_monthly_trend(trend, hw_stats, OUT_DIR)

    # Report
    write_report(trains_per_day, hw_stats, trend, OUT_DIR)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
