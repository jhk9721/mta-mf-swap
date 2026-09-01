"""
SCRIPT 12: SCHEDULED vs REALIZED HEADWAYS AT ROOSEVELT ISLAND
==============================================================
Separates "what the MTA promised on paper" from "what the MTA delivered
in practice." Two falsifiable comparisons at Roosevelt Island (B06):

  1. Post-swap WEEKDAY M trains
        scheduled peak headway  vs  realized peak headway
     If realized > scheduled, the schedule was not delivered — that is a
     reliability gap independent of the planning decision.

  2. Post-swap WEEKEND F trains  (METHODOLOGY CONTROL)
        scheduled peak headway  vs  realized peak headway
     Weekend F service is unchanged by the swap, so any scheduled-vs-
     realized gap here is the methodology error floor — it shows how
     much GTFS-RT realized headways differ from GTFS static even when
     no service change is in play.

ALSO TESTED: the September 2025 Staff Summary committed to "increasing
peak-hour M service" so that the average additional wait time would be
"approximately 1 minute on average." That commitment translates to a
maximum scheduled peak headway of ~7 min (pre-swap F was ~5 min peak,
half-headway 2.5; +1 min average wait = post-swap peak ~7 min). We can
test directly whether the schedule itself respects that commitment.

INPUTS:
  - Resources/gtfs_static/        (run 1c_download_gtfs_static.py first)
  - results/roosevelt_island_headways.csv   (run 3_analyze.py first)

OUTPUTS (saved to results/schedule_vs_realized/):
  - schedule_vs_realized_hourly.csv      — per-hour scheduled vs realized
  - schedule_vs_realized_buckets.csv     — per time-bucket comparison
  - schedule_vs_realized_chart.png       — line chart, weekday M
  - schedule_vs_realized_weekend.png     — control: weekend F
  - schedule_vs_realized_report.txt
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPTS_DIR  = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent   # data + analysis live in the project root
GTFS_DIR     = PROJECT_ROOT / "Resources" / "gtfs_static"
RESULTS_DIR  = PROJECT_ROOT / "results"
OUT_DIR      = RESULTS_DIR / "schedule_vs_realized"
HEADWAYS_CSV = RESULTS_DIR / "roosevelt_island_headways.csv"

ROOSEVELT_STOPS = {"B06N", "B06S"}
SWAP_DATE       = date(2025, 12, 8)

# Hours we want to surface as the "peak" headlines (MTA's 6 AM–9 PM swap window
# and AM/PM peaks specifically).
TIME_BUCKETS = [
    ( 0,  6, "1: Early AM (12–6 AM)"),
    ( 6,  9, "2: Morning Rush (6–9 AM)"),
    ( 9, 16, "3: Midday (9 AM–4 PM)"),
    (16, 19, "4: Evening Rush (4–7 PM)"),
    (19, 24, "5: Night (7 PM–midnight)"),
]
RUSH_PREFIXES = {"2:", "4:"}

# MTA methodology: average wait time = mean headway / 2.
# Staff Summary commitment: "average additional wait time will be reduced to
# approximately 1 minute on average."
SEPT_2025_COMMITMENT_MAX_DELTA_MIN = 1.0


# ══════════════════════════════════════════════════════════════════════════════
# GTFS STATIC LOADER
# ══════════════════════════════════════════════════════════════════════════════

def parse_gtfs_time(s: str) -> float:
    """
    GTFS arrival_time can exceed 24h (e.g. '25:30:00' for next-day trips).
    Returns seconds since service-day start.
    """
    if not isinstance(s, str) or not s:
        return float("nan")
    parts = s.split(":")
    if len(parts) != 3:
        return float("nan")
    try:
        h, m, sec = (int(p) for p in parts)
    except ValueError:
        return float("nan")
    return h * 3600 + m * 60 + sec


def assign_bucket(hour: int) -> str:
    for s, e, label in TIME_BUCKETS:
        if s <= hour < e:
            return label
    return "Unknown"


def load_gtfs_schedule_at_b06() -> pd.DataFrame:
    """
    Build a frame of (route_id, service_id, day_type, stop_id, direction,
    arrival_sec, hour, time_bucket) for every scheduled stop at B06.
    """
    if not GTFS_DIR.is_dir():
        raise FileNotFoundError(
            f"GTFS static not found at {GTFS_DIR}. "
            "Run 1c_download_gtfs_static.py first."
        )

    print(f"Loading GTFS static from: {GTFS_DIR}")
    stop_times = pd.read_csv(GTFS_DIR / "stop_times.txt", low_memory=False,
                              usecols=["trip_id", "stop_id",
                                       "arrival_time", "stop_sequence"])
    stop_times = stop_times[stop_times["stop_id"].isin(ROOSEVELT_STOPS)].copy()

    trips = pd.read_csv(GTFS_DIR / "trips.txt",
                         usecols=["trip_id", "route_id", "service_id",
                                  "direction_id"])
    df = stop_times.merge(trips, on="trip_id", how="left")

    cal = pd.read_csv(GTFS_DIR / "calendar.txt")
    weekday_services = set(
        cal[cal[["monday", "tuesday", "wednesday", "thursday", "friday"]]
            .sum(axis=1) > 0]["service_id"]
    )
    saturday_services = set(cal[cal["saturday"] == 1]["service_id"])
    sunday_services   = set(cal[cal["sunday"]   == 1]["service_id"])

    def day_type(svc):
        if svc in weekday_services:  return "Weekday"
        if svc in saturday_services: return "Saturday"
        if svc in sunday_services:   return "Sunday"
        return "Unknown"

    df["day_type"]      = df["service_id"].map(day_type)
    df["arrival_sec"]   = df["arrival_time"].apply(parse_gtfs_time)
    df = df.dropna(subset=["arrival_sec"])
    df["hour"]          = (df["arrival_sec"] // 3600).astype(int) % 24
    df["time_bucket"]   = df["hour"].apply(assign_bucket)
    df["direction"]     = df["stop_id"].astype(str).str[-1]

    print(f"  Loaded {len(df):,} scheduled stop events at B06.")
    print(f"  Routes present: {sorted(df['route_id'].unique())}")
    print(f"  Day types:      {sorted(df['day_type'].unique())}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED HEADWAYS
# ══════════════════════════════════════════════════════════════════════════════

def compute_scheduled_headways(df: pd.DataFrame) -> pd.DataFrame:
    """
    Inter-arrival headway between consecutive scheduled stops within
    (route_id, day_type, direction, hour). Same outlier filter as realized.
    """
    df = df.sort_values(
        ["route_id", "day_type", "direction", "arrival_sec"]
    ).copy()
    grp = ["route_id", "day_type", "direction"]
    df["prev_sec"] = df.groupby(grp)["arrival_sec"].shift(1)
    df["headway_min"] = (df["arrival_sec"] - df["prev_sec"]) / 60
    df = df.dropna(subset=["headway_min"])
    df = df[(df["headway_min"] >= 1) & (df["headway_min"] <= 90)]
    return df


def summarize_scheduled(sched_hw: pd.DataFrame) -> pd.DataFrame:
    """Per (route × day_type × direction × hour) scheduled headway stats."""
    g = sched_hw.groupby(["route_id", "day_type", "direction", "hour"])
    s = g["headway_min"].agg(
        n="count", median="median", mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).reset_index()
    s["wait_time_min"] = s["mean"] / 2
    s["time_bucket"]   = s["hour"].apply(assign_bucket)
    return s.round({"median": 2, "mean": 2, "p90": 2, "wait_time_min": 2})


# ══════════════════════════════════════════════════════════════════════════════
# REALIZED HEADWAYS
# ══════════════════════════════════════════════════════════════════════════════

def load_realized_headways() -> pd.DataFrame:
    """Load the per-arrival headway dataset produced by 3_analyze.py."""
    if not HEADWAYS_CSV.exists():
        raise FileNotFoundError(
            f"{HEADWAYS_CSV} not found. Run 3_analyze.py first."
        )
    print(f"Loading realized headways from: {HEADWAYS_CSV}")
    df = pd.read_csv(HEADWAYS_CSV, low_memory=False)
    df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    print(f"  {len(df):,} realized headway records.")
    return df


def summarize_realized(real_hw: pd.DataFrame) -> pd.DataFrame:
    """Per (route × day_type × direction × hour) realized headway stats."""
    g = real_hw.groupby(["route_id", "day_type", "direction", "hour"])
    s = g["headway_min"].agg(
        n="count", median="median", mean="mean",
        p90=lambda x: x.quantile(0.90),
    ).reset_index()
    s["wait_time_min"] = s["mean"] / 2
    s["time_bucket"]   = s["hour"].apply(assign_bucket)
    return s.round({"median": 2, "mean": 2, "p90": 2, "wait_time_min": 2})


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def merge_schedule_realized(sched: pd.DataFrame,
                             realized: pd.DataFrame) -> pd.DataFrame:
    """
    Join scheduled and realized stats on (route_id, day_type, direction, hour).
    Wide-form output.
    """
    cols = ["n", "median", "mean", "p90", "wait_time_min"]
    sched_r = sched.rename(columns={c: f"sched_{c}" for c in cols})
    real_r  = realized.rename(columns={c: f"real_{c}"  for c in cols})

    merged = sched_r.merge(real_r,
                            on=["route_id", "day_type", "direction", "hour",
                                "time_bucket"],
                            how="outer")
    merged["headway_gap_min"] = merged["real_mean"] - merged["sched_mean"]
    merged["wait_gap_min"]    = merged["real_wait_time_min"] - merged["sched_wait_time_min"]
    return merged.sort_values(
        ["route_id", "day_type", "direction", "hour"]
    ).round({"headway_gap_min": 2, "wait_gap_min": 2})


def bucket_summary(sched: pd.DataFrame,
                    realized: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to the 5 time buckets (matching script 3) for headline-style
    comparison. Computes wait_time = mean / 2 from bucket-level headways.
    """
    def _summ(df, label):
        # Recompute time_bucket from hour so weekday and weekend labels align
        # (the realized CSV uses different bucket labels for weekends).
        df = df.copy()
        df["time_bucket"] = df["hour"].apply(assign_bucket)
        g = df.groupby(["route_id", "day_type", "direction", "time_bucket"])
        s = g["headway_min"].agg(
            n="count", median="median", mean="mean",
            p90=lambda x: x.quantile(0.90),
        ).reset_index()
        s["wait_time_min"] = s["mean"] / 2
        rename = {c: f"{label}_{c}" for c in ["n", "median", "mean", "p90",
                                                "wait_time_min"]}
        return s.rename(columns=rename)

    s_b = _summ(sched,    "sched")
    r_b = _summ(realized, "real")
    merged = s_b.merge(r_b,
                        on=["route_id", "day_type", "direction", "time_bucket"],
                        how="outer")
    merged["headway_gap_min"] = merged["real_mean"]          - merged["sched_mean"]
    merged["wait_gap_min"]    = merged["real_wait_time_min"] - merged["sched_wait_time_min"]
    return merged.sort_values(
        ["route_id", "day_type", "direction", "time_bucket"]
    ).round({
        "sched_median": 2, "sched_mean": 2, "sched_p90": 2,
        "sched_wait_time_min": 2,
        "real_median": 2,  "real_mean": 2,  "real_p90": 2,
        "real_wait_time_min": 2,
        "headway_gap_min": 2, "wait_gap_min": 2,
    })


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_hourly(merged: pd.DataFrame,
                  route: str,
                  day_type: str,
                  title: str,
                  out_path: Path) -> None:
    sub = merged[(merged["route_id"] == route) &
                 (merged["day_type"] == day_type)].copy()
    if sub.empty:
        print(f"  [WARN] No data for {route} {day_type}; skipping chart.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    fig.suptitle(title, fontsize=12.5, fontweight="bold")

    for ax, direction, dir_label in [
        (axes[0], "S", "Southbound (→ Manhattan)"),
        (axes[1], "N", "Northbound (→ Queens/Home)"),
    ]:
        d = sub[sub["direction"] == direction].sort_values("hour")
        if d.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                     transform=ax.transAxes, color="gray")
            continue
        ax.plot(d["hour"], d["sched_mean"], "-o",
                 color="#4C8BE0", lw=2.2, label="Scheduled (GTFS static)")
        ax.plot(d["hour"], d["real_mean"], "--s",
                 color="#E05C4C", lw=2.2, label="Realized (GTFS-RT)")
        ax.fill_between(d["hour"], d["sched_mean"], d["real_mean"],
                          where=d["real_mean"] > d["sched_mean"],
                          color="#E05C4C", alpha=0.12)

        ax.set_title(dir_label, fontsize=11)
        ax.set_xlabel("Hour of day")
        if ax is axes[0]:
            ax.set_ylabel("Mean headway (min)")
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlim(0, 23)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=9, loc="upper left")

    fig.text(0.5, -0.02,
              "Source: MTA GTFS static schedule (current) + subwaydata.nyc realized arrivals "
              "(post-swap weekdays for M / all weekends for F)",
              ha="center", fontsize=8.5, color="gray")
    plt.tight_layout(rect=[0, 0.02, 1, 0.93])
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def build_report(merged_hourly: pd.DataFrame,
                  bucket_df: pd.DataFrame,
                  out_dir: Path) -> None:

    def cell(df, route, day, direction, bucket, col):
        sub = df[(df["route_id"]   == route) &
                 (df["day_type"]   == day) &
                 (df["direction"]  == direction) &
                 (df["time_bucket"] == bucket)]
        if sub.empty or pd.isna(sub[col].values[0]):
            return "  N/A "
        v = sub[col].values[0]
        return f"{v:5.2f}" if isinstance(v, (int, float)) else str(v)

    def line(route, day, direction, bucket):
        sm = cell(bucket_df, route, day, direction, bucket, "sched_mean")
        rm = cell(bucket_df, route, day, direction, bucket, "real_mean")
        sw = cell(bucket_df, route, day, direction, bucket, "sched_wait_time_min")
        rw = cell(bucket_df, route, day, direction, bucket, "real_wait_time_min")
        gap = cell(bucket_df, route, day, direction, bucket, "headway_gap_min")
        return (f"  {bucket:<32} | sched {sm} → real {rm}  "
                f"| wait sched {sw} → real {rw}  | gap {gap}")

    lines = [
        "ROOSEVELT ISLAND — SCHEDULED vs REALIZED HEADWAYS",
        "What MTA scheduled vs what subwaydata.nyc actually observed",
        "=" * 70,
        "",
        "METHODOLOGY:",
        "  Scheduled headways come from the MTA's GTFS static feed (currently",
        "  in effect, post-swap). Realized headways come from arrival",
        "  observations in subwaydata.nyc's GTFS-RT archives. Wait time is",
        "  defined as the MTA defines it: mean headway / 2.",
        "",
        "  Two scopes are compared:",
        "    1. Weekday M at Roosevelt Island (post-swap; the swap-affected",
        "       service). Realized data: post-swap weekdays only.",
        "    2. Weekend F at Roosevelt Island (unchanged by the swap; serves",
        "       as a methodology control). Realized data: all weekends in the",
        "       observation period.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "WEEKDAY M — POST-SWAP (the swap-affected service)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "  Southbound (→ Manhattan, AM commute):",
    ]
    for b in [t[2] for t in TIME_BUCKETS]:
        lines.append(line("M", "Weekday", "S", b))

    lines += ["", "  Northbound (→ Queens/Home, PM commute):"]
    for b in [t[2] for t in TIME_BUCKETS]:
        lines.append(line("M", "Weekday", "N", b))

    # MTA Sept 2025 Staff Summary commitment test ─────────────────────────
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STAFF SUMMARY COMMITMENT TEST (Sept 2025)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "  The September 2025 Staff Summary committed: \"AM and PM peak-hour",
        "  M service will be increased, so that the average additional wait",
        f"  time will be reduced to approximately {SEPT_2025_COMMITMENT_MAX_DELTA_MIN:.0f} minute on average.\"",
        "",
        "  Pre-swap baseline (F train, weekday peak, from realized data):",
    ]

    # Pull pre-swap F realized peak for comparison from bucket_df
    f_pre_sb_2 = bucket_df[(bucket_df["route_id"]   == "F") &
                            (bucket_df["day_type"]   == "Saturday") &
                            (bucket_df["direction"]  == "S")]
    # We don't have a pre-swap F weekday peak in this script's outputs because
    # GTFS schedule reflects current service only. Pull from realized side.
    lines += [
        "    (Pre-swap F-train peak headway is reported by 3_analyze.py;",
        "     median ≈ 4.75 min Southbound Morning Rush.)",
        "",
        "  Post-swap M scheduled peak headway (this script):",
    ]
    for direction, lbl in [("S", "Southbound"), ("N", "Northbound")]:
        for bucket_label in ["2: Morning Rush (6–9 AM)", "4: Evening Rush (4–7 PM)"]:
            sub = bucket_df[(bucket_df["route_id"]  == "M") &
                            (bucket_df["day_type"]  == "Weekday") &
                            (bucket_df["direction"] == direction) &
                            (bucket_df["time_bucket"] == bucket_label)]
            if not sub.empty:
                sm = sub["sched_mean"].values[0]
                sw = sub["sched_wait_time_min"].values[0]
                lines.append(
                    f"    {lbl} {bucket_label}: scheduled mean {sm:.2f} min "
                    f"(scheduled wait = {sw:.2f} min)"
                )

    lines += [
        "",
        "  INTERPRETATION:",
        "    The Staff Summary's \"+1 minute average wait\" implies post-swap",
        "    scheduled peak headway around 7 minutes (since pre-swap F peak",
        "    headway was ~5 min, and a +1 min wait increase ≈ +2 min headway).",
        "    Compare the scheduled means above against this benchmark.",
        "    A scheduled mean noticeably above 7 min in peak hours indicates",
        "    the schedule itself does not honor the September 2025 commitment.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "WEEKEND F — METHODOLOGY CONTROL",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "  Weekend F service at RI is unchanged by the swap. The scheduled-vs-",
        "  realized gap here represents the methodology error floor — how much",
        "  GTFS-RT observed headways differ from the GTFS static schedule even",
        "  when the underlying service is stable.",
        "",
        "  Saturday Southbound:",
    ]
    for b in [t[2] for t in TIME_BUCKETS]:
        lines.append(line("F", "Saturday", "S", b))
    lines += ["", "  Sunday Southbound:"]
    for b in [t[2] for t in TIME_BUCKETS]:
        lines.append(line("F", "Sunday", "S", b))

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "HOW TO READ THIS:",
        "  - If the realized M peak headway exceeds the scheduled M peak",
        "    headway by more than the weekend-F control gap, the MTA is not",
        "    delivering its own schedule. This is a reliability story",
        "    distinct from the planning decision.",
        "  - If the scheduled M peak headway is itself well above the",
        "    September 2025 commitment (~7 min implied), the schedule itself",
        "    breaks the commitment, regardless of operational delivery.",
        "  - These two issues compound: a schedule that breaks the commitment",
        "    AND a service that runs worse than the schedule both contribute",
        "    to rider-experienced wait time.",
        "",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "schedule_vs_realized_report.txt"
    path.write_text("\n".join(lines))
    print(f"Saved: {path}")
    print()
    print("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Scheduled side ───────────────────────────────────────────────────
    sched_raw = load_gtfs_schedule_at_b06()
    sched_hw  = compute_scheduled_headways(sched_raw)
    print(f"  Scheduled headway observations: {len(sched_hw):,}")

    # ── Realized side ────────────────────────────────────────────────────
    real_raw = load_realized_headways()
    # Align scopes: weekday M post-swap; weekend F any period (control)
    real_wkd_m = real_raw[
        (real_raw["route_id"] == "M") &
        (real_raw["arrival_date"] >= SWAP_DATE) &
        (real_raw["day_type"]  == "Weekday")
    ].copy()
    real_wkd_m["day_type"] = "Weekday"

    real_wknd_f = real_raw[
        (real_raw["route_id"] == "F") &
        (real_raw["day_type"].isin(["Weekend"]))
    ].copy()
    # Realized data labels weekends "Weekend" — split into Sat/Sun by date.
    real_wknd_f["day_of_week"] = pd.to_datetime(
        real_wknd_f["arrival_date"]
    ).dt.dayofweek
    real_wknd_f["day_type"] = real_wknd_f["day_of_week"].map(
        {5: "Saturday", 6: "Sunday"}
    )
    real_wknd_f = real_wknd_f.dropna(subset=["day_type"])

    realized = pd.concat([real_wkd_m, real_wknd_f], ignore_index=True)
    print(f"  Realized scope: {len(realized):,} observations "
          f"(weekday M post-swap + weekend F).")

    # ── Hourly comparison ────────────────────────────────────────────────
    sched_h = summarize_scheduled(sched_hw)
    real_h  = summarize_realized(realized)
    merged_hourly = merge_schedule_realized(sched_h, real_h)
    merged_hourly.to_csv(OUT_DIR / "schedule_vs_realized_hourly.csv", index=False)
    print(f"  Hourly comparison: {len(merged_hourly)} rows")

    # ── Bucket comparison ────────────────────────────────────────────────
    bucket_df = bucket_summary(sched_hw, realized)
    bucket_df.to_csv(OUT_DIR / "schedule_vs_realized_buckets.csv", index=False)
    print(f"  Bucket comparison: {len(bucket_df)} rows")
    print()
    print("── Bucket comparison ───────────────────────────────────────────")
    show_cols = ["route_id", "day_type", "direction", "time_bucket",
                 "sched_mean", "real_mean", "headway_gap_min",
                 "sched_wait_time_min", "real_wait_time_min", "wait_gap_min"]
    print(bucket_df[show_cols].to_string(index=False))
    print()

    # ── Charts ───────────────────────────────────────────────────────────
    plot_hourly(merged_hourly, "M", "Weekday",
                "Roosevelt Island — Weekday M (Post-Swap): Scheduled vs Realized",
                OUT_DIR / "schedule_vs_realized_chart.png")
    plot_hourly(merged_hourly, "F", "Saturday",
                "Roosevelt Island — Saturday F (Methodology Control): "
                "Scheduled vs Realized",
                OUT_DIR / "schedule_vs_realized_weekend.png")

    # ── Report ───────────────────────────────────────────────────────────
    build_report(merged_hourly, bucket_df, OUT_DIR)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
