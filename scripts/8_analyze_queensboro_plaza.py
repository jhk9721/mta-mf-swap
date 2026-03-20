"""
SCRIPT 8: QUEENSBORO PLAZA RELIABILITY ANALYSIS
=================================================
Answers: "Has Queensboro Plaza seen improved service after the F/M swap?"

BACKGROUND AND FRAMING:
  The MTA's stated rationale for the F/M swap was to eliminate the track
  merge at Queens Plaza where M/R local trains crossed onto the express
  tracks, creating cascading delays for E, F, M, and R trains. By keeping
  the M on the 63rd St (local) tracks and routing F with E on the 53rd St
  (express) tracks, the MTA argued that E/F reliability would improve.

  IMPORTANT: Queensboro Plaza (stop 718) is served by the 7, N, and W
  trains — NOT by E/F/M/R. It is a DIFFERENT station from "Queens Plaza,"
  which is the E/F/M/R stop on the Queens Blvd express/local tracks.

  This script analyzes reliability at TWO stations:
    1. Queens Plaza (G21) — E/F/R station on the Queens Blvd express tracks.
       This is the station directly downstream of the merge point the MTA
       claimed to eliminate. The M does NOT stop here; it runs on the local
       tracks through 36 St and Steinway St before that merge point.
       "Improved reliability" here means shorter or more consistent E/F/R
       headways and fewer 10+ minute gap events.
    2. Queensboro Plaza (718/R09) — served by 7, N, and W trains only.
       Entirely unrelated to the E/F/M/R corridor. Included because it is
       frequently confused with Queens Plaza in press and official discussions.

  DATA QUALITY NOTE — QUEENS PLAZA (G21):
    The GTFS-RT feed records M train arrivals at G21 pre-swap, despite the
    MTA station glossary listing G21 as an E/F/R stop. This indicates G21
    functions as a complex-level ID that captures arrivals across both the
    express and local platforms, not just the express platform.

    The practical consequence: pre-swap "E/F" headways at G21 are a mixture
    of E, F, AND M trains interleaved. Post-swap, the M disappears from G21
    (rerouted to the 63rd St line), leaving only E and F. The apparent halving
    of headways (e.g., 4.8 → 2.1 min) is almost entirely an artifact of this
    compositional change — not a genuine reliability improvement. Measuring
    E/F-specific headways at Queens Plaza would require isolating individual
    route_ids, but even then the pre/post comparison is not apples-to-apples
    because the service pattern at that station fundamentally changed.

    For these reasons, Queens Plaza E/F headway comparisons should NOT be
    used as evidence of improved reliability in advocacy materials. The R
    train headways (which did not change routes) are a cleaner signal and
    show effectively no change before vs. after the swap.

WHAT YOU NEED BEFORE RUNNING:
  1. Run 1_download.py and 1b_download_extended.py (raw data in raw_data/)
  2. No dependency on earlier analysis scripts — this script is standalone.

HOW TO RUN:
    python3 8_analyze_queensboro_plaza.py

OUTPUTS (saved to results/queensboro/):
  - queensboro_headways.csv          — headway records for both stations
  - queensboro_summary.csv           — median/p90 before vs. after
  - queens_plaza_ef_comparison.png   — E/F headways at Queens Plaza before/after
  - queensboro_plaza_7nw.png         — 7/N/W headways (should show no change)
  - queensboro_report.txt            — plain-English findings
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

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

SCRIPTS_DIR  = Path(__file__).parent
RAW_DATA_DIR = SCRIPTS_DIR / "raw_data"
RESULTS_DIR  = SCRIPTS_DIR / "results"
OUT_DIR      = RESULTS_DIR / "queensboro"

SWAP_DATE = date(2025, 12, 8)

# ── Station definitions ───────────────────────────────────────────────────────
#
# Queens Plaza — Queens Blvd corridor station.
# GTFS stop ID: G21 (confirmed from MTA station glossary).
# The service pattern changed with the swap:
#   Pre-swap:  E, M, R  (F ran via 63rd St line, not Queens Plaza)
#   Post-swap: E, F, R  (M rerouted to 63rd St line, F takes its place)
# This is precisely the congestion question: did swapping M for F at Queens
# Plaza change throughput or headways for each individual line?
# Note: G21 appears to function as a complex-level ID in the GTFS-RT feed,
# capturing arrivals from both the express and local platforms. All routes
# with meaningful observations are retained and tracked individually.
QUEENS_PLAZA_STOP_IDS = {
    "G21N", "G21S",
}

# Queensboro Plaza — 7/N/W station. Entirely separate from Queens Plaza.
# GTFS stop IDs: 718N/718S (7 train) and R09N/R09S (N/W trains).
QUEENSBORO_PLAZA_STOP_IDS = {
    "718N", "718S",   # 7 train
    "R09N", "R09S",   # N/W trains
}

ALL_STOP_IDS = QUEENS_PLAZA_STOP_IDS | QUEENSBORO_PLAZA_STOP_IDS

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
RUSH_BUCKET_PREFIXES = {"2:", "3:", "4:"}

COLOR_BEFORE = "#4C8BE0"
COLOR_AFTER  = "#E05C4C"

SOURCE_NOTE = (
    "Source: subwaydata.nyc  |  Weekdays only  |  Holiday and storm days excluded  |"
    "  Jan 2025–Mar 2026"
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


def station_group(stop_id: str) -> str:
    """Assign each stop_id to a named station group."""
    base = stop_id.upper()
    if base in {s.upper() for s in QUEENS_PLAZA_STOP_IDS}:
        return "Queens Plaza"
    if base in {s.upper() for s in QUEENSBORO_PLAZA_STOP_IDS}:
        return "Queensboro Plaza (7/N/W)"
    return "Unknown"


def route_group(route_id: str) -> str:
    """Individual route grouping for Queens Plaza congestion analysis."""
    if route_id in {"E"}:
        return "E"
    if route_id in {"F", "FX"}:
        return "F"
    if route_id in {"M"}:
        return "M"
    if route_id in {"R"}:
        return "R"
    if route_id in {"7", "7X"}:
        return "7/7X"
    if route_id in {"N", "W"}:
        return "N/W"
    return route_id


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_one_day(tar_path: str, file_date: date) -> pd.DataFrame:
    """Load stop_times for Queens Plaza and Queensboro Plaza from one archive."""
    with tarfile.open(tar_path, "r:xz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        st_m = next((m for n, m in members.items() if n.endswith("stop_times.csv")), None)
        tr_m = next((m for n, m in members.items() if n.endswith("trips.csv")),      None)
        if st_m is None or tr_m is None:
            print(f"  [WARN] {os.path.basename(tar_path)}: missing CSVs.")
            return pd.DataFrame()

        stop_times = pd.read_csv(tar.extractfile(st_m), low_memory=False)
        # Case-insensitive match: some GTFS feeds use lowercase
        stop_times["stop_id_upper"] = stop_times["stop_id"].astype(str).str.upper()
        stop_times = stop_times[
            stop_times["stop_id_upper"].isin({s.upper() for s in ALL_STOP_IDS})
        ].copy()
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


def load_all_data(raw_dir: Path) -> pd.DataFrame:
    """Load all available weekday, non-holiday dates from raw_data/."""
    files = sorted(glob.glob(str(raw_dir / "*.tar.xz")))
    if not files:
        raise FileNotFoundError(
            f"No .tar.xz files in {raw_dir}/\n"
            "Run 1_download.py and 1b_download_extended.py first."
        )

    print(f"Found {len(files)} archive files. Loading...\n")
    all_dfs = []
    skipped_no_data = 0

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            file_date = datetime.strptime(fname.split("_")[1], "%Y-%m-%d").date()
        except (IndexError, ValueError):
            continue

        if file_date.weekday() >= 5 or is_holiday(file_date):
            continue

        try:
            day_df = load_one_day(filepath, file_date)
            if not day_df.empty:
                all_dfs.append(day_df)
                print(f"  [OK]   {fname}  → {len(day_df):,} records")
            else:
                skipped_no_data += 1
        except Exception as e:
            print(f"  [ERR]  {fname}: {e}")

    if skipped_no_data > 0:
        print(f"\n  [NOTE] {skipped_no_data} files had no matching stop_ids."
              " This is expected if stop IDs vary across GTFS versions.")

    if not all_dfs:
        raise ValueError(
            "No data loaded for Queens Plaza or Queensboro Plaza.\n"
            "Possible causes:\n"
            "  1. The GTFS feed uses different stop IDs for these stations.\n"
            "     Run 2_inspect.py and check the stop_id values.\n"
            "  2. You may need to update QUEENS_PLAZA_STOP_IDS in this script.\n"
            "  Common alternatives: 'G05', '718', 'R09' (without N/S suffix)"
        )

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal records loaded: {len(combined):,}\n")
    return combined


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def add_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["arrival_date"]  = df["arrival_dt"].dt.date
    df["hour"]          = df["arrival_dt"].dt.hour
    df["is_weekday"]    = df["arrival_dt"].dt.dayofweek < 5
    df["direction"]     = df["stop_id"].astype(str).str[-1]
    df["swap_period"]   = df["arrival_date"].apply(
        lambda d: "After swap" if d >= SWAP_DATE else "Before swap"
    )
    df["time_bucket"]   = df["hour"].apply(assign_time_bucket)
    df["station_group"] = df["stop_id"].apply(station_group)
    df["route_group"]   = df["route_id"].apply(route_group)
    return df


def compute_headways(df: pd.DataFrame) -> pd.DataFrame:
    """
    Headways computed within each
    arrival_date × station_group × route_group × direction × time_bucket group.
    """
    print("Computing headways...")
    df_s = df.sort_values([
        "arrival_date", "station_group", "route_group", "direction",
        "time_bucket", "arrival_dt"
    ]).copy()

    grp = ["arrival_date", "station_group", "route_group", "direction", "time_bucket"]
    df_s["prev_arrival"] = df_s.groupby(grp)["arrival_dt"].shift(1)
    df_s["headway_min"]  = (
        (df_s["arrival_dt"] - df_s["prev_arrival"]).dt.total_seconds() / 60
    )
    df_s = df_s.dropna(subset=["headway_min"])

    below_min = (df_s["headway_min"] < 1).sum()
    df_s      = df_s[df_s["headway_min"] >= 1]

    early_am = df_s["time_bucket"].str.startswith("1:")
    above_max = (
        ( early_am & (df_s["headway_min"] > 90)) |
        (~early_am & (df_s["headway_min"] > 60))
    ).sum()
    df_s = df_s[
        ( early_am & (df_s["headway_min"] <= 90)) |
        (~early_am & (df_s["headway_min"] <= 60))
    ]

    total_removed = below_min + above_max
    print(f"  Outlier removal: {total_removed} records removed")
    print(f"  {len(df_s):,} headway observations retained.\n")
    return df_s


def compute_long_gap_rates(df_hw: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the share of intervals exceeding 10 minutes (a proxy for
    cascading delay events — the condition the swap was meant to reduce).
    """
    rush = df_hw[df_hw["time_bucket"].str[:2].isin(RUSH_BUCKET_PREFIXES)]
    result = (
        rush.groupby(["station_group", "route_group", "direction", "swap_period"])
        .apply(lambda x: pd.Series({
            "n_intervals": len(x),
            "n_over_10min": (x["headway_min"] > 10).sum(),
            "pct_over_10min": (x["headway_min"] > 10).mean() * 100,
            "n_over_15min": (x["headway_min"] > 15).sum(),
            "pct_over_15min": (x["headway_min"] > 15).mean() * 100,
        }))
        .reset_index()
    )
    return result.sort_values(["station_group", "route_group", "direction", "swap_period"])


def build_summary(df_hw: pd.DataFrame) -> pd.DataFrame:
    rush = df_hw[df_hw["time_bucket"].str[:2].isin(RUSH_BUCKET_PREFIXES)]
    g = rush.groupby(
        ["station_group", "route_group", "time_bucket", "direction", "swap_period"]
    )["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).round(2).reset_index()
    return g.sort_values([
        "station_group", "route_group", "time_bucket", "direction", "swap_period"
    ])


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

def _plot_station_comparison(df_hw: pd.DataFrame,
                              station: str,
                              route_groups: list,
                              title: str,
                              out_dir: Path,
                              fname: str):
    """Reusable before/after bar chart for any station × route combination."""
    rush_buckets = {
        "2: Morning Rush (6–9 AM)": "Morning Rush\n(6–9 AM)",
        "3: Midday (9 AM–4 PM)":   "Midday\n(9 AM–4 PM)",
        "4: Evening Rush (4–7 PM)": "Evening Rush\n(4–7 PM)",
    }
    directions = {
        "S": "Southbound (→ Manhattan)",
        "N": "Northbound (→ Queens)",
    }

    station_data = df_hw[
        (df_hw["station_group"] == station) &
        df_hw["route_group"].isin(route_groups)
    ]
    if station_data.empty:
        print(f"  [WARN] No data for {station} / {route_groups} — skipping chart.")
        return

    n_buckets = len(rush_buckets)
    n_dirs    = len(directions)
    # Taller figure so rows don't crowd the suptitle
    fig, axes = plt.subplots(n_dirs, n_buckets,
                              figsize=(5.5 * n_buckets, 6 * n_dirs),
                              sharey=False, squeeze=False)
    # rect leaves room at top for suptitle and bottom for source note
    fig.suptitle(title, fontsize=13, fontweight="bold")
    plt.tight_layout(rect=[0, 0.04, 1, 0.93])

    for row, (direction, dir_label) in enumerate(directions.items()):
        # Direction label as a row annotation on the left axis instead of
        # repeating it in every subplot title
        axes[row][0].annotate(
            dir_label,
            xy=(0, 0.5), xycoords="axes fraction",
            xytext=(-0.18, 0.5), textcoords="axes fraction",
            fontsize=10, fontweight="bold", color="#333333",
            ha="right", va="center",
            rotation=90,
        )

        for col, (bucket, bucket_label) in enumerate(rush_buckets.items()):
            ax = axes[row][col]
            sub = station_data[
                (station_data["direction"]   == direction) &
                (station_data["time_bucket"] == bucket)
            ]

            before = sub[sub["swap_period"] == "Before swap"]["headway_min"]
            after  = sub[sub["swap_period"] == "After swap"]["headway_min"]

            med_b = before.median() if not before.empty else np.nan
            med_a = after.median()  if not after.empty  else np.nan

            positions = [1, 2]
            heights   = [med_b, med_a]
            colors    = [COLOR_BEFORE, COLOR_AFTER]
            xlabels   = [
                f"Before\n(pre-swap)\nn={len(before):,}",
                f"After\n(post-swap)\nn={len(after):,}",
            ]

            for pos, h, c in zip(positions, heights, colors):
                if pd.notna(h):
                    ax.bar(pos, h, color=c, alpha=0.85, width=0.5, zorder=3)
                    ax.text(pos, h + 0.1, f"{h:.1f}m",
                             ha="center", va="bottom", fontsize=10,
                             fontweight="bold", color=c)

            if pd.notna(med_b) and pd.notna(med_a) and med_b > 0:
                pct = (med_a - med_b) / med_b * 100
                direction_word = "▼ improvement" if pct < -2 else "▲ degradation" if pct > 2 else "≈ no change"
                ax.text(1.5, max(med_b, med_a) + 0.7,
                         f"{pct:+.0f}%\n{direction_word}",
                         ha="center", va="bottom", fontsize=9,
                         fontweight="bold",
                         color="#1A7A3F" if pct < -2 else "#CC0000" if pct > 2 else "#555555")

            ax.set_xticks(positions)
            ax.set_xticklabels(xlabels, fontsize=8.5)
            # Bucket label only — direction is handled by the row annotation
            ax.set_title(bucket_label, fontsize=10, fontweight="bold", pad=8)
            ax.set_ylabel("Median Headway (minutes)" if col == 0 else "")
            ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
            # Top padding so value labels don't touch the subplot title
            current_max = max((h for h in heights if pd.notna(h)), default=1)
            ax.set_ylim(bottom=0, top=current_max * 1.45)

    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=8.5, color="gray")
    path = out_dir / fname
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot_queens_plaza_by_route(df_hw: pd.DataFrame, out_dir: Path):
    """
    Queens Plaza congestion chart: each route shown individually,
    with bars only in the period it actually operated at this station.

    Pre-swap:  E (both periods), M (pre only), R (both periods)
    Post-swap: E (both periods), F (post only), R (both periods)

    The M→F substitution is the core story: did replacing M with F
    at Queens Plaza change the headway each line provides?

    Each route gets its own bar group. Routes that only exist in one
    period show a single bar; E and R show both for continuity check.
    """
    rush_buckets = {
        "2: Morning Rush (6–9 AM)": "Morning Rush\n(6–9 AM)",
        "3: Midday (9 AM–4 PM)":   "Midday\n(9 AM–4 PM)",
        "4: Evening Rush (4–7 PM)": "Evening Rush\n(4–7 PM)",
    }
    directions = {
        "S": "Southbound (→ Manhattan)",
        "N": "Northbound (→ Queens)",
    }

    # Route display order and which periods each route is expected in
    # pre = before swap, post = after swap, both = both periods
    ROUTE_CONFIG = [
        ("E", "#4C8BE0", "both"),   # E runs both periods
        ("M", "#E05C4C", "pre"),    # M only pre-swap at Queens Plaza
        ("F", "#E8A838", "post"),   # F only post-swap at Queens Plaza
        ("R", "#6AAF40", "both"),   # R runs both periods — clean control
    ]

    qp = df_hw[df_hw["station_group"] == "Queens Plaza"]
    if qp.empty:
        print("  [WARN] No Queens Plaza data for per-route chart.")
        return

    n_buckets = len(rush_buckets)
    for direction, dir_label in directions.items():
        # Taller figure to give suptitle, bars, legend, and source note room
        fig, axes = plt.subplots(1, n_buckets, figsize=(5.5 * n_buckets, 8),
                                  sharey=False)
        if n_buckets == 1:
            axes = [axes]

        fig.suptitle(
            f"Queens Plaza — Headway by Route Before vs. After F/M Swap\n"
            f"{dir_label} | Weekdays | Service pattern: E+M+R → E+F+R",
            fontsize=13, fontweight="bold",
        )
        # rect: leave space at top for suptitle, bottom for legend + source note
        plt.tight_layout(rect=[0, 0.12, 1, 0.91])

        for ax, (bucket, bucket_label) in zip(axes, rush_buckets.items()):
            bucket_data = qp[
                (qp["direction"]   == direction) &
                (qp["time_bucket"] == bucket)
            ]

            # Build one bar group per route
            bar_positions = []
            bar_heights   = []
            bar_colors    = []
            bar_labels    = []
            bar_n         = []
            group_centers = []
            group_names   = []

            x = 0
            gap_between_routes = 0.3
            bar_width = 0.35

            for route, color, period in ROUTE_CONFIG:
                route_data = bucket_data[bucket_data["route_group"] == route]
                pre  = route_data[route_data["swap_period"] == "Before swap"]["headway_min"]
                post = route_data[route_data["swap_period"] == "After swap"]["headway_min"]

                positions_in_group = []

                if period in ("both", "pre") and not pre.empty:
                    bar_positions.append(x)
                    bar_heights.append(pre.median())
                    bar_colors.append(color)
                    bar_labels.append(f"Before\nn={len(pre):,}")
                    bar_n.append(len(pre))
                    positions_in_group.append(x)
                    x += bar_width + 0.05

                if period in ("both", "post") and not post.empty:
                    bar_positions.append(x)
                    bar_heights.append(post.median())
                    # Slightly lighter shade for after bar when route runs both periods
                    bar_colors.append(color if period == "post" else color + "99")
                    bar_labels.append(f"After\nn={len(post):,}")
                    bar_n.append(len(post))
                    positions_in_group.append(x)
                    x += bar_width + 0.05

                if positions_in_group:
                    group_centers.append(sum(positions_in_group) / len(positions_in_group))
                    period_note = " (pre only)" if period == "pre" else " (post only)" if period == "post" else ""
                    group_names.append(f"{route}{period_note}")
                    x += gap_between_routes

            # Draw bars
            for pos, h, c in zip(bar_positions, bar_heights, bar_colors):
                if pd.notna(h) and h > 0:
                    ax.bar(pos, h, width=bar_width, color=c, alpha=0.85, zorder=3)
                    ax.text(pos, h + 0.15, f"{h:.1f}m",
                             ha="center", va="bottom", fontsize=9,
                             fontweight="bold", color=c[:7])

            # Route group labels on x-axis
            ax.set_xticks(group_centers)
            ax.set_xticklabels(group_names, fontsize=9.5, fontweight="bold")
            ax.set_title(bucket_label, fontsize=11, fontweight="bold", pad=10)
            ax.set_ylabel("Median Headway (minutes)" if ax == axes[0] else "")
            ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
            # Enough headroom for value labels above bars
            current_max = max((h for h in bar_heights if pd.notna(h)), default=1)
            ax.set_ylim(bottom=0, top=current_max * 1.5)
            ax.set_xlim(left=-0.3)

        # Legend and source note sit below the plot area reserved by rect
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#4C8BE0", label="E train (both periods)"),
            Patch(facecolor="#E05C4C", label="M train (pre-swap only)"),
            Patch(facecolor="#E8A838", label="F train (post-swap only)"),
            Patch(facecolor="#6AAF40", label="R train (both periods — control)"),
        ]
        fig.legend(handles=legend_elements, loc="lower center",
                   ncol=4, fontsize=9, bbox_to_anchor=(0.5, 0.05))

        fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=8.5, color="gray")

        fname = f"queens_plaza_by_route_{direction.lower()}bound.png"
        path  = out_dir / fname
        plt.savefig(path, dpi=160, bbox_inches="tight")
        plt.close()
        print(f"Saved: {path}")


def plot_long_gaps(gap_data: pd.DataFrame, out_dir: Path):
    """
    Bar chart: % of intervals > 10 min per route at Queens Plaza, before/after swap.

    Only routes with >= MIN_N intervals in a given period are shown.
    This prevents misleading statistics from near-zero observations:
      - M post-swap at G21: only 1-4 records → 100% gap rate is noise
      - F pre-swap at G21: F didn't serve Queens Plaza before Dec 8

    Each bar is annotated with its sample size so readers can assess reliability.
    Routes that only appear in one period (M pre-swap, F post-swap) show a
    single bar rather than a spurious before/after comparison.
    """
    MIN_N = 50

    rush_data = gap_data[gap_data["station_group"].str.contains("Queens Plaza")].copy()
    if rush_data.empty:
        print("  [WARN] No Queens Plaza gap data — skipping long-gap chart.")
        return

    # Drop route×period combinations with insufficient observations
    dropped = rush_data[rush_data["n_intervals"] < MIN_N]
    if not dropped.empty:
        print(f"  [Long-gap filter] Dropping {len(dropped)} route×period combinations "
              f"with < {MIN_N} intervals:")
        for _, row in dropped.iterrows():
            print(f"    {row['route_group']} | {row['swap_period']} | "
                  f"{row['direction']} | n={int(row['n_intervals'])}")
    rush_data = rush_data[rush_data["n_intervals"] >= MIN_N]

    # Route display order and colors — consistent with plot_queens_plaza_by_route
    ROUTE_COLORS = {"E": "#4C8BE0", "M": "#E05C4C", "F": "#E8A838", "R": "#6AAF40"}
    PERIOD_ALPHA = {"Before swap": 0.85, "After swap": 0.65}

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharey=False)
    fig.suptitle(
        "Queens Plaza — Share of Train Intervals Exceeding 10 Minutes\n"
        "Before vs. After F/M Swap | Weekday Rush Hours",
        fontsize=13, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0.08, 1, 0.91])

    for ax, direction, dir_label in [
        (axes[0], "S", "Southbound (→ Manhattan)"),
        (axes[1], "N", "Northbound (→ Queens)"),
    ]:
        sub = rush_data[rush_data["direction"] == direction].copy()
        if sub.empty:
            ax.text(0.5, 0.5, "No routes with sufficient data",
                     ha="center", va="center", transform=ax.transAxes, color="gray")
            ax.set_title(dir_label, fontsize=11, fontweight="bold", pad=8)
            continue

        # Build bar positions manually — one group per route, 1-2 bars per group
        route_order = [r for r in ["E", "M", "F", "R"] if r in sub["route_group"].values]
        bar_positions, bar_heights, bar_colors, bar_alphas = [], [], [], []
        bar_ns, group_centers, group_labels = [], [], []

        x = 0.0
        width = 0.38
        gap_within = 0.05
        gap_between = 0.35

        for route in route_order:
            route_rows = sub[sub["route_group"] == route]
            color = ROUTE_COLORS.get(route, "#888888")
            positions_in_group = []

            for period in ["Before swap", "After swap"]:
                row = route_rows[route_rows["swap_period"] == period]
                if not row.empty:
                    bar_positions.append(x)
                    bar_heights.append(row["pct_over_10min"].values[0])
                    bar_colors.append(color)
                    bar_alphas.append(PERIOD_ALPHA[period])
                    bar_ns.append(int(row["n_intervals"].values[0]))
                    positions_in_group.append(x)
                    x += width + gap_within

            if positions_in_group:
                group_centers.append(np.mean(positions_in_group))
                group_labels.append(route)
                x += gap_between

        # Draw bars
        for pos, h, c, a in zip(bar_positions, bar_heights, bar_colors, bar_alphas):
            ax.bar(pos, h, width=width, color=c, alpha=a, zorder=3)

        # Annotate value + n on each bar
        for pos, h, n in zip(bar_positions, bar_heights, bar_ns):
            ax.text(pos, h + 0.5, f"{h:.1f}%\nn={n:,}",
                     ha="center", va="bottom", fontsize=8,
                     fontweight="bold", color="#333333", linespacing=1.3)

        # % change annotation between before/after pairs where both exist
        for route in route_order:
            route_rows = sub[sub["route_group"] == route]
            b_row = route_rows[route_rows["swap_period"] == "Before swap"]
            a_row = route_rows[route_rows["swap_period"] == "After swap"]
            if not b_row.empty and not a_row.empty:
                bv = b_row["pct_over_10min"].values[0]
                av = a_row["pct_over_10min"].values[0]
                gc = group_centers[route_order.index(route)]
                pct_chg = (av - bv) / bv * 100
                ax.text(gc, max(bv, av) + 4, f"{pct_chg:+.0f}%",
                         ha="center", va="bottom", fontsize=9, fontweight="bold",
                         color="#1A7A3F" if pct_chg < -5 else
                               "#CC0000" if pct_chg > 5 else "#555555")

        ax.set_xticks(group_centers)
        ax.set_xticklabels(group_labels, fontsize=11, fontweight="bold")
        ax.set_title(dir_label, fontsize=11, fontweight="bold", pad=8)
        ax.set_ylabel("% of intervals > 10 min" if ax == axes[0] else "")
        ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
        all_vals = [h for h in bar_heights if pd.notna(h)]
        ax.set_ylim(bottom=0, top=max(all_vals) * 1.6 if all_vals else 30)

    # Shared legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#4C8BE0", alpha=0.85, label="E  —  both periods"),
        Patch(facecolor="#E05C4C", alpha=0.85, label="M  —  pre-swap only"),
        Patch(facecolor="#E8A838", alpha=0.65, label="F  —  post-swap only"),
        Patch(facecolor="#6AAF40", alpha=0.85, label="R  —  both periods (control)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=4,
               fontsize=9, bbox_to_anchor=(0.5, 0.02))

    fig.text(0.5, -0.01, SOURCE_NOTE, ha="center", fontsize=8.5, color="gray")
    path = out_dir / "queens_plaza_long_gaps.png"
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(summary: pd.DataFrame, gap_data: pd.DataFrame, out_dir: Path):

    def med(station, route_grp, bucket_prefix, direction, period):
        sub = summary[
            (summary["station_group"] == station) &
            (summary["route_group"]   == route_grp) &
            summary["time_bucket"].str.startswith(bucket_prefix) &
            (summary["direction"]     == direction) &
            (summary["swap_period"]   == period)
        ]
        return f"{sub['median'].values[0]:.1f}" if not sub.empty else "N/A"

    def gap_pct(station, route_grp, direction, period):
        sub = gap_data[
            (gap_data["station_group"] == station) &
            (gap_data["route_group"]   == route_grp) &
            (gap_data["direction"]     == direction) &
            (gap_data["swap_period"]   == period)
        ]
        return f"{sub['pct_over_10min'].values[0]:.1f}%" if not sub.empty else "N/A"

    lines = [
        "QUEENSBORO PLAZA / QUEENS PLAZA — RELIABILITY ANALYSIS",
        "F/M Swap Impact on Queens Blvd Corridor | Before vs. After December 8, 2025",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 70,
        "",
        "STATION CLARIFICATION",
        "-" * 40,
        "  Two similarly named stations are often confused in discussions of",
        "  the F/M swap:",
        "",
        "  Queens Plaza (E/F/R) — GTFS stop ID: G21N/G21S",
        "    The E/F/R station on the Queens Blvd express tracks, directly",
        "    downstream of the merge point the MTA claimed to eliminate.",
        "    Note: the M does NOT stop at Queens Plaza. It runs on the local",
        "    tracks through 36 St (G20) and Steinway St (G19).",
        "    THIS is the station whose E/F/R reliability the MTA claimed would",
        "    improve after the swap.",
        "",
        "  Queensboro Plaza (7/N/W) — GTFS stop IDs: 718N/718S and R09N/R09S",
        "    A completely different station, served by the 7, N, and W trains.",
        "    Unrelated to the E/F/M/R Queens Blvd corridor.",
        "    The F/M swap has NO direct mechanism to affect service here.",
        "",
        "QUEENS PLAZA — CONGESTION BEFORE VS. AFTER THE SWAP",
        "-" * 40,
        "",
        "  The service pattern at Queens Plaza changed with the swap:",
        "    Pre-swap:  E, M, R  (F ran via 63rd St line, not Queens Plaza)",
        "    Post-swap: E, F, R  (M rerouted to 63rd St; F takes its place)",
        "",
        "  The MTA's claim: replacing M with F at Queens Plaza, and eliminating",
        "  the local-to-express merge, would improve reliability for all lines.",
        "",
        "  E train — runs Queens Plaza in both periods (direct comparison):",
        f"    Morning Rush southbound: {med('Queens Plaza', 'E', '2:', 'S', 'Before swap')} min → {med('Queens Plaza', 'E', '2:', 'S', 'After swap')} min",
        f"    Evening Rush northbound: {med('Queens Plaza', 'E', '4:', 'N', 'Before swap')} min → {med('Queens Plaza', 'E', '4:', 'N', 'After swap')} min",
        "",
        "  M train — pre-swap only (replaced by F after Dec 8):",
        f"    Morning Rush southbound: {med('Queens Plaza', 'M', '2:', 'S', 'Before swap')} min  (pre-swap only)",
        f"    Evening Rush northbound: {med('Queens Plaza', 'M', '4:', 'N', 'Before swap')} min  (pre-swap only)",
        "",
        "  F train — post-swap only (replaced M at Queens Plaza after Dec 8):",
        f"    Morning Rush southbound: {med('Queens Plaza', 'F', '2:', 'S', 'After swap')} min  (post-swap only)",
        f"    Evening Rush northbound: {med('Queens Plaza', 'F', '4:', 'N', 'After swap')} min  (post-swap only)",
        "",
        "  R train — runs Queens Plaza in both periods (independent control):",
        f"    Morning Rush southbound: {med('Queens Plaza', 'R', '2:', 'S', 'Before swap')} min → {med('Queens Plaza', 'R', '2:', 'S', 'After swap')} min",
        f"    Evening Rush northbound: {med('Queens Plaza', 'R', '4:', 'N', 'Before swap')} min → {med('Queens Plaza', 'R', '4:', 'N', 'After swap')} min",
        "",
        "  Note: G21 appears to function as a complex-level stop ID in the GTFS-RT",
        "  feed, capturing arrivals from both express and local platforms. Headways",
        "  are computed per route, so lines do not contaminate each other.",
        "",
        "QUEENSBORO PLAZA — 7/N/W HEADWAYS (UNRELATED TO SWAP)",
        "-" * 40,
        "",
        "  Morning Rush (6–9 AM) | Southbound:",
        f"    7 train before:  {med('Queensboro Plaza (7/N/W)', '7/7X', '2:', 'S', 'Before swap')} min",
        f"    7 train after:   {med('Queensboro Plaza (7/N/W)', '7/7X', '2:', 'S', 'After swap')} min",
        f"    (Stable = expected; 7/N/W not affected by F/M swap)",
        "",
        "ADVOCACY FRAMING",
        "-" * 40,
        "  Even if Queens Plaza E/F shows genuine reliability improvement,",
        "  this does not justify the Roosevelt Island service degradation.",
        "  The MTA made a specific written commitment to Roosevelt Island riders",
        "  that the swap would add only ~1 minute of average wait time.",
        "  That commitment was broken regardless of whether other stations improved.",
        "",
        "  The appropriate framing: the MTA chose to distribute the benefits of",
        "  the swap broadly while concentrating the costs on Roosevelt Island —",
        "  a community of 12,000 people with no alternative subway service.",
        "",
        "=" * 70,
        "METHODOLOGY",
        "-" * 40,
        "  Data source : subwaydata.nyc GTFS-RT archives",
        "  Stop IDs    : G21N/G21S (Queens Plaza); 718N/718S, R09N/R09S (Queensboro Plaza 7/N/W)",
        "  Note        : G21 is a complex-level ID capturing arrivals from both express",
        "                and local platforms. Routes are tracked individually (E, M, F, R)",
        "                so each line's headways are computed independently.",
        "  Day filter  : Weekdays only, non-holiday",
        "  Headways    : Inter-arrival time within day × station × route × direction × bucket",
        "  Long gaps   : Intervals > 10 min as proxy for cascading delay events",
        "",
        SOURCE_NOTE,
    ]

    report = "\n".join(lines)
    path = out_dir / "queensboro_report.txt"
    path.write_text(report)
    print(f"Saved: {path}")
    print()
    print(report)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Roosevelt Island MTA Analysis — Queensboro/Queens Plaza Reliability")
    print("=" * 65)
    print("Queens Plaza: did the M→F substitution change congestion at G21?")
    print("Queensboro Plaza: 7/N/W control (unrelated to swap)\n")

    df_raw = load_all_data(RAW_DATA_DIR)

    # Print stop IDs found — useful for debugging if IDs differ from expected
    found_stops = sorted(df_raw["stop_id"].astype(str).unique())
    print(f"Stop IDs found in data: {found_stops}")
    qp_found  = [s for s in found_stops if any(s.upper().startswith(x[:3]) for x in QUEENS_PLAZA_STOP_IDS)]
    qbp_found = [s for s in found_stops if any(s.upper().startswith(x[:3]) for x in QUEENSBORO_PLAZA_STOP_IDS)]
    print(f"  Queens Plaza stops found:     {qp_found}")
    print(f"  Queensboro Plaza stops found: {qbp_found}")
    print()

    df     = add_columns(df_raw)
    df_hw  = compute_headways(df[df["is_weekday"]])

    # Save headways
    csv_path = OUT_DIR / "queensboro_headways.csv"
    df_hw.to_csv(csv_path, index=False)
    print(f"Headway data saved: {csv_path}\n")

    summary  = build_summary(df_hw)
    gap_data = compute_long_gap_rates(df_hw)

    summary.to_csv(OUT_DIR / "queensboro_summary.csv", index=False)
    gap_data.to_csv(OUT_DIR / "queensboro_long_gaps.csv", index=False)

    print("── Summary (rush hours, by station and route) ──────────────────")
    print(summary.to_string(index=False))
    print()
    print("── Long Gap Rates (% of intervals > 10 min) ────────────────────")
    print(gap_data.to_string(index=False))
    print()

    # Charts
    plot_queens_plaza_by_route(df_hw, OUT_DIR)
    _plot_station_comparison(
        df_hw,
        station="Queensboro Plaza (7/N/W)",
        route_groups=["7/7X", "N/W"],
        title=(
            "Queensboro Plaza (7/N/W) — Headways Before vs. After F/M Swap\n"
            "Weekday Rush Hours | Expected: No change (7/N/W unaffected by swap)"
        ),
        out_dir=OUT_DIR,
        fname="queensboro_plaza_7nw.png",
    )
    plot_long_gaps(gap_data, OUT_DIR)

    write_report(summary, gap_data, OUT_DIR)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
