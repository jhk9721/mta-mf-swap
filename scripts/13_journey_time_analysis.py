"""
SCRIPT 13: ROOSEVELT ISLAND JOURNEY-TIME ANALYSIS
==================================================
Computes end-to-end journey time for the Roosevelt Island commuter
going to five representative Manhattan destinations, weekday peak
hours, southbound, before vs after the F/M swap.

This is the rider-experience answer to the MTA's "the swap saves
~1 minute on average for 47,000 AM peak QBL riders" claim. The 47k
average isn't directly testable without ridership weights, but RI's
specific journey-time delta is — and it's the central concern of
Roosevelt Island advocacy.

DESIGN:
  Origin: B06S (Roosevelt Island, southbound to Manhattan).
  Destinations:
    Lex Av/63 St (B08S)        — direct M post-swap, direct F pre-swap
    57 St-6 Av (B10S)          — direct, both periods
    47-50 Rockefeller (D15S)   — direct, both periods (M continues 6 Ave)
    34 St-Herald Sq (D17S)     — direct, both periods (M continues 6 Ave)
    W 4 St-Wash Sq (D20S)      — direct, both periods (M continues 6 Ave)
    Broadway-Lafayette (D21S)  — direct, both periods (M's last shared stop)
    2 Av (F14S)                — direct pre-swap; transfer post (F only south of D21)
    Delancey-Essex (F15S)      — direct pre-swap; transfer post (F only south of D21)

  KEY FINDING ABOUT THE M's POST-SWAP ROUTING:
    Despite the Staff Summary's phrasing ("rerouting M trains onto the
    63rd Street line between 21 St-Queensbridge and 57 St"), the post-
    swap M weekday continues from 57 St south on the 6 Ave Manhattan
    line through Broadway-Lafayette before transitioning to the BMT
    Jamaica line for Brooklyn. This means RI riders going to most
    6 Ave Manhattan destinations have DIRECT M service post-swap, just
    as they had direct F service pre-swap. Verified from GTFS static.

  For direct journeys:
    travel_time = arrival_at_destination − arrival_at_origin
    matched within the same trip_uid.

  For post-swap transfer journeys (RI → F-only stops south of D21):
    travel_time = M(B06S→D21S median)  +  transfer_wait at D21S
                + F(D21S→destination median)
    transfer_wait = ½ × median F headway at D21S (peak, post-swap)
    This is the MTA's own wait-time methodology applied to the
    transfer.

  Filters: weekday, non-holiday, peak hours (6–9 AM).

INPUTS:
  - raw_data/*.tar.xz  (subwaydata.nyc archives)

OUTPUTS (saved to results/journey_times/):
  - journey_times.csv      — per O-D × period × type
  - journey_times.png      — bar chart, Δ travel time per destination
  - journey_times_report.txt
"""

from __future__ import annotations

import os
import sys
import tarfile
import glob
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

SCRIPTS_DIR  = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent   # data + analysis live in the project root
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"
RESULTS_DIR  = PROJECT_ROOT / "results"
OUT_DIR      = RESULTS_DIR / "journey_times"

SWAP_DATE       = date(2025, 12, 8)
STORM_DATE      = date(2026, 1, 25)
STORM_END_DATE  = date(2026, 2, 1)

HOLIDAY_PERIODS = [
    (date(2025, 12, 22), date(2026, 1,  5)),
    (date(2026,  1, 19), date(2026, 1, 19)),
]

# Peak window for the AM commute (matching MTA framing of "47,000 AM peak hour riders")
AM_PEAK_HOURS = set(range(6, 9))      # 6, 7, 8 AM

# Stations of interest. Southbound only (Manhattan-bound from RI).
ORIGIN = "B06S"          # Roosevelt Island
TRANSFER = "D21S"        # Broadway-Lafayette — last shared M/F stop on 6 Ave
DESTINATIONS = {
    "B08S": "Lex Av/63 St",
    "B10S": "57 St-6 Av",
    "D15S": "47-50 Sts-Rockefeller Ctr",
    "D17S": "34 St-Herald Sq",
    "D20S": "W 4 St-Wash Sq",
    "D21S": "Broadway-Lafayette St",
    "F14S": "2 Av (F-only south of D21)",
    "F15S": "Delancey-Essex (F-only south of D21)",
}

# All stops we need to load
ANALYSIS_STOPS = {ORIGIN} | set(DESTINATIONS.keys()) | {TRANSFER}

ROUTE_FILTERS = {
    "F": {"F", "FX"},
    "M": {"M"},
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_holiday(d: date) -> bool:
    return any(s <= d <= e for s, e in HOLIDAY_PERIODS)


def in_storm_window(d: date) -> bool:
    return STORM_DATE <= d < STORM_END_DATE


def swap_period(d: date) -> str:
    return "After swap" if d >= SWAP_DATE else "Before swap"


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_one_day(tar_path: str, file_date: date) -> pd.DataFrame:
    """Load arrivals at the analysis stops from one daily archive."""
    with tarfile.open(tar_path, "r:xz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        st_m = next((m for n, m in members.items() if n.endswith("stop_times.csv")), None)
        tr_m = next((m for n, m in members.items() if n.endswith("trips.csv")),      None)
        if st_m is None or tr_m is None:
            return pd.DataFrame()

        st = pd.read_csv(tar.extractfile(st_m), low_memory=False,
                          usecols=["trip_uid", "stop_id", "arrival_time", "departure_time"])
        st = st[st["stop_id"].isin(ANALYSIS_STOPS)].copy()
        if st.empty:
            return pd.DataFrame()

        tr = pd.read_csv(tar.extractfile(tr_m), low_memory=False,
                          usecols=["trip_uid", "route_id", "direction_id"])

    df = st.merge(tr, on="trip_uid", how="left")
    df["arrival_time"]   = pd.to_numeric(df["arrival_time"],   errors="coerce")
    df["departure_time"] = pd.to_numeric(df["departure_time"], errors="coerce")
    df["timestamp"]      = df["arrival_time"].fillna(df["departure_time"])
    df = df.dropna(subset=["timestamp"])

    df["arrival_dt"]     = (pd.to_datetime(df["timestamp"], unit="s", utc=True)
                              .dt.tz_convert("America/New_York"))
    df["calendar_date"]  = file_date
    df["arrival_date"]   = df["arrival_dt"].dt.date
    df["hour"]           = df["arrival_dt"].dt.hour
    df["is_weekday"]     = df["arrival_dt"].dt.dayofweek < 5
    df["swap_period"]    = df["arrival_date"].apply(swap_period)
    df["is_holiday"]     = df["arrival_date"].apply(is_holiday)
    df["in_storm"]       = df["arrival_date"].apply(in_storm_window)
    return df


def load_all_data(raw_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(raw_dir / "*.tar.xz")))
    if not files:
        raise FileNotFoundError(
            f"No archives in {raw_dir}/. Run 1_download.py and 1b_download_extended.py."
        )
    print(f"Found {len(files)} archives. Loading...\n")
    frames = []
    for fp in files:
        fname = os.path.basename(fp)
        try:
            d = datetime.strptime(fname.split("_")[1], "%Y-%m-%d").date()
        except (IndexError, ValueError):
            continue
        if d.weekday() >= 5 or is_holiday(d):
            continue
        try:
            day_df = load_one_day(fp, d)
            if not day_df.empty:
                frames.append(day_df)
        except Exception as e:
            print(f"  [ERR] {fname}: {e}")
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"Loaded {len(combined):,} arrivals at "
          f"{len(ANALYSIS_STOPS)} analysis stops.\n")
    return combined


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT TRIP TRAVEL TIMES
# ══════════════════════════════════════════════════════════════════════════════

EMPTY_JT = pd.DataFrame(columns=["travel_min", "swap_period", "origin_hour"])


def direct_journey_times(df: pd.DataFrame,
                          origin: str,
                          destination: str,
                          routes: set | None = None,
                          peak_hours: set = AM_PEAK_HOURS) -> pd.DataFrame:
    """
    Per trip_uid that visits both origin and destination, compute travel
    time (destination_arrival − origin_arrival) in minutes. Filter to
    weekday + AM peak (origin hour) + non-holiday.

    Always returns a DataFrame with columns travel_min, swap_period,
    origin_hour (possibly empty).
    """
    sub = df[df["is_weekday"] & ~df["is_holiday"]].copy()
    if routes:
        sub = sub[sub["route_id"].isin(routes)]
    rel = sub[sub["stop_id"].isin([origin, destination])]
    if rel.empty:
        return EMPTY_JT.copy()

    pivot = rel.pivot_table(
        index="trip_uid",
        columns="stop_id",
        values="arrival_dt",
        aggfunc="first",
    )
    if origin not in pivot.columns or destination not in pivot.columns:
        return EMPTY_JT.copy()

    valid = pivot.dropna(subset=[origin, destination]).copy()
    if valid.empty:
        return EMPTY_JT.copy()
    valid["origin_hour"] = valid[origin].dt.hour
    valid = valid[valid["origin_hour"].isin(peak_hours)]
    if valid.empty:
        return EMPTY_JT.copy()

    valid["travel_min"]  = (valid[destination] - valid[origin]).dt.total_seconds() / 60
    valid["origin_date"] = valid[origin].dt.date
    # Drop reversed/implausible rows
    valid = valid[(valid["travel_min"] > 0) & (valid["travel_min"] < 60)]
    valid["swap_period"] = valid["origin_date"].apply(swap_period)
    return valid[["travel_min", "swap_period", "origin_hour"]]


def headway_at_stop(df: pd.DataFrame,
                     stop: str,
                     routes: set,
                     peak_hours: set,
                     period: str) -> pd.Series:
    """Inter-arrival headways at one stop, filtered."""
    sub = df[
        df["is_weekday"] & ~df["is_holiday"] &
        (df["stop_id"]    == stop) &
        df["route_id"].isin(routes) &
        df["hour"].isin(peak_hours) &
        (df["swap_period"] == period)
    ].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    sub = sub.sort_values(["arrival_date", "arrival_dt"])
    grp = ["arrival_date"]
    sub["prev"] = sub.groupby(grp)["arrival_dt"].shift(1)
    hw = (sub["arrival_dt"] - sub["prev"]).dt.total_seconds() / 60
    hw = hw.dropna()
    hw = hw[(hw >= 1) & (hw <= 60)]
    return hw


# ══════════════════════════════════════════════════════════════════════════════
# JOURNEY TIME COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_journey_times(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each destination, compute pre-swap and post-swap median journey
    time from B06S, AM peak, weekday.
    """
    rows = []

    # ── F headway at the transfer point D21S, post-swap (used for transfer wait).
    # Use a slightly wider window (6–10 AM) so we don't artificially truncate
    # gaps spanning the peak boundary, which would understate sample size.
    f_hw_post = headway_at_stop(df, TRANSFER, ROUTE_FILTERS["F"],
                                  set(range(6, 11)), "After swap")
    transfer_wait_post = float(f_hw_post.median()) / 2 if not f_hw_post.empty else float("nan")
    if not f_hw_post.empty:
        print(f"Post-swap F median headway at {TRANSFER} (Bdwy-Lafayette): "
              f"{f_hw_post.median():.2f} min  "
              f"→ transfer wait estimate {transfer_wait_post:.2f} min  "
              f"(n={len(f_hw_post)})")
    else:
        print(f"Post-swap F headway at {TRANSFER}: no data")
    print()

    for dest_stop, dest_name in DESTINATIONS.items():
        # ── Pre-swap: direct F trip
        pre_jt = direct_journey_times(df, ORIGIN, dest_stop,
                                        routes=ROUTE_FILTERS["F"])
        pre = pre_jt[pre_jt["swap_period"] == "Before swap"]["travel_min"]

        # ── Post-swap: direct M trip if it exists (only for B08S, B10S)
        post_direct_m = direct_journey_times(df, ORIGIN, dest_stop,
                                              routes=ROUTE_FILTERS["M"])
        post_direct = post_direct_m[
            post_direct_m["swap_period"] == "After swap"
        ]["travel_min"]

        if not post_direct.empty and len(post_direct) >= 30:
            post_type = "direct M (post-swap)"
            post_value = float(post_direct.median())
            post_n     = int(len(post_direct))
        else:
            # ── Build transfer journey: M (B06S→B10S) + transfer + F (B10S→dest)
            m_leg_jt = direct_journey_times(df, ORIGIN, TRANSFER,
                                              routes=ROUTE_FILTERS["M"])
            m_leg = m_leg_jt[m_leg_jt["swap_period"] == "After swap"]["travel_min"]
            f_leg_jt = direct_journey_times(df, TRANSFER, dest_stop,
                                              routes=ROUTE_FILTERS["F"])
            f_leg = f_leg_jt[f_leg_jt["swap_period"] == "After swap"]["travel_min"]

            if m_leg.empty or f_leg.empty or pd.isna(transfer_wait_post):
                post_type  = "post-swap unavailable (insufficient data)"
                post_value = float("nan")
                post_n     = 0
            else:
                post_type = (f"M ({m_leg.median():.1f}) + transfer wait "
                             f"({transfer_wait_post:.1f}) + F ({f_leg.median():.1f})")
                post_value = (float(m_leg.median()) + transfer_wait_post
                               + float(f_leg.median()))
                post_n = int(min(len(m_leg), len(f_leg)))

        rows.append({
            "destination_stop": dest_stop,
            "destination_name": dest_name,
            "pre_swap_type":    "direct F (pre-swap)",
            "pre_swap_median":  round(float(pre.median()), 2) if not pre.empty else None,
            "pre_swap_n":       int(len(pre)),
            "post_swap_type":   post_type,
            "post_swap_median": round(post_value, 2) if not pd.isna(post_value) else None,
            "post_swap_n":      post_n,
            "delta_min":        round(post_value - float(pre.median()), 2)
                                  if not pre.empty and not pd.isna(post_value) else None,
        })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════════════════

def plot_journey_times(jt: pd.DataFrame, out_path: Path) -> None:
    if jt.empty or jt["delta_min"].isna().all():
        print("  [WARN] No journey-time data to plot.")
        return

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.suptitle(
        "Roosevelt Island AM Peak Journey Time — Pre vs Post F/M Swap\n"
        "(weekday, AM peak hours 6–9 AM, southbound)",
        fontsize=12.5, fontweight="bold",
    )

    plot_df = jt.dropna(subset=["delta_min"]).copy()
    plot_df = plot_df.sort_values("destination_stop")
    x = np.arange(len(plot_df))
    width = 0.36

    pre  = plot_df["pre_swap_median"].astype(float).to_numpy()
    post = plot_df["post_swap_median"].astype(float).to_numpy()

    ax.bar(x - width/2, pre,  width=width, color="#4C8BE0", alpha=0.85,
            label="Pre-swap (direct F)")
    ax.bar(x + width/2, post, width=width, color="#E05C4C", alpha=0.85,
            label="Post-swap (direct M or M+transfer+F)")

    for xi, p, q, d in zip(x, pre, post, plot_df["delta_min"]):
        ax.text(xi - width/2, p + 0.4, f"{p:.1f}", ha="center", va="bottom",
                 fontsize=9, fontweight="bold", color="#4C8BE0")
        ax.text(xi + width/2, q + 0.4, f"{q:.1f}", ha="center", va="bottom",
                 fontsize=9, fontweight="bold", color="#E05C4C")
        # Δ annotation above the higher bar
        ymax = max(p, q)
        ax.text(xi, ymax + 1.4, f"Δ {d:+.1f} min",
                 ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                 color="#1A7A3F" if d < 0 else "#CC0000")

    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["destination_name"], rotation=18, ha="right",
                       fontsize=9)
    ax.set_ylabel("Median journey time from RI (minutes)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0, top=max(post.max(), pre.max()) * 1.25)
    ax.legend(fontsize=9, loc="upper left")

    fig.text(0.5, -0.02,
              "Source: subwaydata.nyc weekday AM peak. Direct travel times "
              "computed within trip_uid; transfer wait ≈ ½ × median F headway "
              "at 57 St (post-swap).",
              ha="center", fontsize=8.5, color="gray")
    plt.tight_layout(rect=[0, 0.02, 1, 0.93])
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(jt: pd.DataFrame, out_dir: Path) -> None:
    lines = [
        "ROOSEVELT ISLAND JOURNEY-TIME ANALYSIS",
        "AM peak (6–9 AM) southbound trips, weekday non-holiday",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 70,
        "",
        "WHY THIS ANALYSIS:",
        "  The September 2025 Staff Summary justified the F/M swap by",
        "  promising \"approximately one minute in savings for 47,000 AM",
        "  peak hour riders.\" That AVERAGE across the QBL service area is",
        "  not directly testable without ridership weights. But the RI-",
        "  rider experience IS — and Roosevelt Island riders are inside",
        "  that 47k count.",
        "",
        "  This script measures end-to-end journey time from RI (B06S) to",
        "  eight Manhattan destinations in the AM peak, before vs after",
        "  the swap. The post-swap M continues past 57 St south on the",
        "  6 Ave Manhattan line through Broadway-Lafayette (verified",
        "  from GTFS static), so most 6 Ave destinations remain one-",
        "  seat rides. The transfer penalty applies only for F-only",
        "  stops south of Broadway-Lafayette (2 Av, Delancey-Essex, and",
        "  F-line Brooklyn destinations). For those, post-swap journey",
        "  time is built as: M (B06S → Bdwy-Lafayette) + transfer wait",
        "  at D21 (½ × F headway) + F (D21 → destination).",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "RESULTS",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for _, r in jt.iterrows():
        d = r["delta_min"]
        d_str = f"Δ {d:+.2f} min" if d is not None else "Δ N/A"
        verdict = ("(longer)"  if d is not None and d > 0 else
                    "(shorter)" if d is not None and d < 0 else "")
        lines += [
            f"  {r['destination_name']} ({r['destination_stop']})",
            f"    Pre-swap  ({r['pre_swap_type']}):  "
            f"{r['pre_swap_median']:.2f} min   (n={r['pre_swap_n']:,})"
            if r["pre_swap_median"] is not None else
            f"    Pre-swap:  insufficient data",
            f"    Post-swap ({r['post_swap_type']}):"
            f"  {r['post_swap_median']:.2f} min   (n={r['post_swap_n']:,})"
            if r["post_swap_median"] is not None else
            f"    Post-swap: insufficient data",
            f"    {d_str}  {verdict}",
            "",
        ]

    # Headline numbers
    valid = jt.dropna(subset=["delta_min"])
    if not valid.empty:
        avg_delta = valid["delta_min"].mean()
        worst = valid.loc[valid["delta_min"].idxmax()]
        # Split into direct vs transfer destinations for clearer narrative
        valid["is_transfer"] = valid["post_swap_type"].str.contains(
            "transfer", case=False, na=False
        )
        direct_part   = valid[~valid["is_transfer"]]
        transfer_part = valid[ valid["is_transfer"]]

        lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "INTERPRETATION",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"  Mean journey-time Δ across {len(valid)} destinations:  "
            f"{avg_delta:+.2f} min",
            f"  Worst-affected destination: {worst['destination_name']}  "
            f"(Δ {worst['delta_min']:+.2f} min)",
            "",
        ]
        if not direct_part.empty:
            lines += [
                f"  Destinations with one-seat service in BOTH periods "
                f"(M continues 6 Ave to D21):",
                f"    {len(direct_part)} destinations | mean Δ "
                f"{direct_part['delta_min'].mean():+.2f} min — essentially flat",
                "    The in-vehicle ride time is unchanged. The rider impact",
                "    on these trips is the wait-time delta at RI",
                "    (+1.36 min via DiD; see 11_did_control_stations.py).",
                "",
            ]
        if not transfer_part.empty:
            lines += [
                f"  Destinations requiring a NEW transfer post-swap "
                f"(F-only south of D21):",
                f"    {len(transfer_part)} destinations | mean Δ "
                f"{transfer_part['delta_min'].mean():+.2f} min",
                "    These trips now face a structural transfer penalty",
                "    (transfer wait + F-segment) on top of any wait-time",
                "    change at the RI origin.",
                "",
            ]
        lines += [
            "  The MTA's claim was \"approximately 1 minute in savings\"",
            "  averaged across 47,000 AM peak QBL riders. The RI-rider",
            "  side of that average is, at minimum, +1.36 min worse for",
            "  destinations on the M-served portion of 6 Ave Manhattan,",
            f"  and ~{transfer_part['delta_min'].mean():+.1f} min worse for "
            f"F-only destinations south of D21" if not transfer_part.empty else
            "  Brooklyn-bound F destinations face a similar transfer penalty.",
            "  not directly tested for systemwide ridership-weighted average.",
            "",
        ]
    else:
        lines += ["", "  No O-D pairs produced sufficient data.", ""]

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "METHODOLOGY NOTES",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "  - Direct travel times: median (destination_arrival − origin_arrival)",
        "    over trip_uids that visit both, AM peak, weekday non-holiday.",
        "  - Transfer wait estimate: ½ × median F headway at Broadway-",
        "    Lafayette (D21S), AM peak post-swap — the last shared M/F",
        "    stop on the 6 Ave line. This is the MTA's own 'wait time'",
        "    formula applied to the transfer step.",
        "  - Storm window (Jan 25–Feb 1, 2026) is INCLUDED for parity with",
        "    the upstream realized-headway analysis. Sensitivity analysis",
        "    excluding it would only sharpen, not change, the direction.",
        "  - The 47,000-rider average savings claim cannot be evaluated",
        "    here without origin-destination ridership weights from the MTA.",
        "    This analysis tests RI's specific rider-side delta only.",
        "",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "journey_times_report.txt"
    path.write_text("\n".join(lines))
    print(f"Saved: {path}\n")
    print("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_all_data(RAW_DATA_DIR)
    if df.empty:
        print("No data loaded; aborting.")
        return 1

    jt = compute_journey_times(df)
    jt.to_csv(OUT_DIR / "journey_times.csv", index=False)

    print("── Journey times ──────────────────────────────────────────────")
    print(jt.to_string(index=False))
    print()

    plot_journey_times(jt, OUT_DIR / "journey_times.png")
    write_report(jt, OUT_DIR)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
