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
  - roosevelt_island_headways.csv
  - headway_summary.csv
  - headway_distribution_weekday.png
  - headway_distribution_weekend.png
  - headways_over_time.png
  - hourly_headways.png
  - results_report.txt
"""

import os
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

SWAP_DATE = date(2025, 12, 8)

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
    df["time_bucket"]  = df.apply(
        lambda r: assign_time_bucket(r["hour"], r["is_weekday"]), axis=1
    )
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
    # Overnight allows longer gaps; daytime cap at 60 min
    df_s = df_s[df_s["headway_min"] >= 1]
    early_am_mask = df_s["time_bucket"].str.startswith("1:")
    df_s = df_s[
        (early_am_mask  & (df_s["headway_min"] <= 90)) |
        (~early_am_mask & (df_s["headway_min"] <= 60))
    ]
    print(f"  {len(df_s):,} headway observations.\n")
    return df_s


def summarize_headways(df_hw: pd.DataFrame) -> pd.DataFrame:
    g = df_hw.groupby(["day_type", "time_bucket", "swap_period", "direction"])
    s = g["headway_min"].agg(
        n="count",
        median="median",
        mean="mean",
        p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75),
        p90=lambda x: x.quantile(0.90),
    ).round(1).reset_index()
    s["direction"] = s["direction"].map(
        {"N": "Northbound (→ Queens/Home)", "S": "Southbound (→ Manhattan)"}
    )
    return s.sort_values(["day_type", "time_bucket", "direction", "swap_period"])


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


def write_report(df_hw: pd.DataFrame, summary: pd.DataFrame, results_dir: str):

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
FULL STATISTICS TABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{summary.to_string(index=False)}
"""

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
    df_hw  = compute_headways(df)

    hw_path = os.path.join(RESULTS_DIR, "roosevelt_island_headways.csv")
    df_hw.to_csv(hw_path, index=False)
    print(f"Headway data saved to: {hw_path}\n")

    summary = summarize_headways(df_hw)
    summary.to_csv(os.path.join(RESULTS_DIR, "headway_summary.csv"), index=False)
    print("Summary statistics:")
    print(summary.to_string(index=False))
    print()

    plot_distribution(df_hw, "Weekday", RESULTS_DIR)
    plot_distribution(df_hw, "Weekend", RESULTS_DIR)
    plot_hourly_headways(df_hw, RESULTS_DIR)
    plot_daily_median_headway(df_hw, RESULTS_DIR)
    write_report(df_hw, summary, RESULTS_DIR)

    print(f"\nAll results saved to: {os.path.abspath(RESULTS_DIR)}/")


if __name__ == "__main__":
    main()
