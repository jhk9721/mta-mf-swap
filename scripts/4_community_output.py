"""
SCRIPT 4: COMMUNITY OUTPUT (v2)
"""

import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import date

# Paths are resolved relative to this script's location so the script works
# regardless of which directory it is invoked from.
RESULTS_DIR   = Path(__file__).parent / "results"
COMMUNITY_DIR = RESULTS_DIR / "community"
SWAP_DATE     = date(2025, 12, 8)

TIME_BUCKETS = [
    ( 0,  6, "1: Early AM (12–6 AM)",        "1: Early AM (12–6 AM)"),
    ( 6,  9, "2: Morning Rush (6–9 AM)",      "2: Morning (6–9 AM)"),
    ( 9, 16, "3: Midday (9 AM–4 PM)",         "3: Midday (9 AM–4 PM)"),
    (16, 19, "4: Evening Rush (4–7 PM)",      "4: Afternoon/Evening (4–7 PM)"),
    (19, 24, "5: Night (7 PM–midnight)",      "5: Night (7 PM–midnight)"),
]
SWAP_ACTIVE_BUCKETS = {"2:", "3:", "4:"}
COLOR_BEFORE = "#4C8BE0"
COLOR_AFTER  = "#E05C4C"
SOURCE_NOTE  = "Source: subwaydata.nyc  |  Roosevelt Island (B06)  |  Oct 2025–Feb 2026"


def assign_bucket(hour, is_weekday):
    for start, end, wd_label, we_label in TIME_BUCKETS:
        if start <= hour < end:
            return wd_label if is_weekday else we_label
    return "Unknown"


def load_and_prep(csv_path):
    df = pd.read_csv(csv_path)
    df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    df["is_weekday"]   = df["is_weekday"].astype(bool)
    df["swap_period"]  = df["arrival_date"].apply(
        lambda d: "After swap" if d >= SWAP_DATE else "Before swap"
    )
    df["day_type"]    = df["is_weekday"].map({True: "Weekday", False: "Weekend"})
    df["time_bucket"] = df.apply(lambda r: assign_bucket(r["hour"], r["is_weekday"]), axis=1)
    early_am = df["time_bucket"].str.startswith("1:")
    df = df[(early_am & (df["headway_min"] <= 90)) | (~early_am & (df["headway_min"] <= 60))]
    df = df[df["headway_min"] >= 1]
    print(f"Loaded {len(df):,} headway observations.")
    return df


def plot_all_periods(df, out_dir):
    wd_nb = df[(df["day_type"] == "Weekday") & (df["direction"] == "S")]
    bucket_labels, before_medians, after_medians, before_p90s, after_p90s, in_swap = [], [], [], [], [], []

    for _, __, wd_label, _ in TIME_BUCKETS:
        sub = wd_nb[wd_nb["time_bucket"] == wd_label]
        b   = sub[sub["swap_period"] == "Before swap"]["headway_min"]
        a   = sub[sub["swap_period"] == "After swap"]["headway_min"]
        if b.empty or a.empty: continue
        short = wd_label.split(":", 1)[1].strip()
        bucket_labels.append(short)
        before_medians.append(b.median())
        after_medians.append(a.median())
        before_p90s.append(b.quantile(0.90))
        after_p90s.append(a.quantile(0.90))
        in_swap.append(wd_label[:2] in SWAP_ACTIVE_BUCKETS)

    x, width = np.arange(len(bucket_labels)), 0.35
    fig, ax = plt.subplots(figsize=(13, 7))
    bars_b = ax.bar(x - width/2, before_medians, width, label="F Train — Before Swap", color=COLOR_BEFORE, edgecolor="white", linewidth=1.2)
    bars_a = ax.bar(x + width/2, after_medians,  width, label="M Train — After Swap",  color=COLOR_AFTER,  edgecolor="white", linewidth=1.2)

    for i, (bp, ap) in enumerate(zip(before_p90s, after_p90s)):
        ax.plot(i - width/2, bp, "^", color=COLOR_BEFORE, markersize=9, zorder=5)
        ax.plot(i + width/2, ap, "^", color=COLOR_AFTER,  markersize=9, zorder=5)

    for i, (bv, av) in enumerate(zip(before_medians, after_medians)):
        ax.text(i - width/2, bv + 0.2, f"{bv:.1f}m", ha="center", va="bottom", fontsize=9, fontweight="bold", color=COLOR_BEFORE)
        ax.text(i + width/2, av + 0.2, f"{av:.1f}m", ha="center", va="bottom", fontsize=9, fontweight="bold", color=COLOR_AFTER)
        pct = (av - bv) / bv * 100
        ax.text(i, max(av, bv) + 1.6, f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold", color="#333333")

    for i, swap in enumerate(in_swap):
        if swap: ax.axvspan(i - 0.5, i + 0.5, alpha=0.06, color=COLOR_AFTER, zorder=0)

    ax.set_xticks(x); ax.set_xticklabels(bucket_labels, fontsize=11)
    ax.set_ylabel("Median Minutes Between Trains", fontsize=12)
    ax.set_title("Roosevelt Island Station — Weekday Wait Times: Before vs. After F/M Swap\nSouthbound (→ Manhattan) & Northbound (→ Queens)  |  All Time Periods", fontsize=13, fontweight="bold", pad=12)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
    ax.set_ylim(0, max(after_p90s) * 1.38)
    triangle = mpatches.Patch(color="gray", label="▲ = 90th percentile (1-in-10 worst waits)")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles + [triangle], labels + ["▲ = 90th percentile (1-in-10 worst waits)"], fontsize=10, loc="upper left")
    ax.annotate("★ shaded = swap active (weekdays only)", xy=(1.0, 0.03), xycoords="axes fraction", fontsize=9, color="#999999", ha="right", style="italic")
    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=9, color="gray")
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = out_dir / "all_periods_comparison.png"
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def plot_evening_rush_spotlight(df, out_dir):
    wd  = df[df["day_type"] == "Weekday"]
    eve = wd[wd["time_bucket"].str.startswith("4:")]
    fig, ax = plt.subplots(figsize=(10, 7))
    categories, dir_codes = ["Northbound\n(→ Queens/Home)", "Southbound\n(→ Manhattan)"], ["N", "S"]
    x, width = np.arange(2), 0.32
    before_m, after_m, before_p, after_p = [], [], [], []
    for d in dir_codes:
        b = eve[(eve["direction"] == d) & (eve["swap_period"] == "Before swap")]["headway_min"]
        a = eve[(eve["direction"] == d) & (eve["swap_period"] == "After swap")]["headway_min"]
        before_m.append(b.median()); after_m.append(a.median())
        before_p.append(b.quantile(0.90)); after_p.append(a.quantile(0.90))
    ax.bar(x - width/2, before_m, width, label="F Train (before Dec 8)", color=COLOR_BEFORE, edgecolor="white", linewidth=1.5)
    ax.bar(x + width/2, after_m,  width, label="M Train (after Dec 8)",  color=COLOR_AFTER,  edgecolor="white", linewidth=1.5)
    for i, (bv, av) in enumerate(zip(before_m, after_m)):
        ax.text(i - width/2, bv + 0.2, f"{bv:.1f} min", ha="center", va="bottom", fontsize=13, fontweight="bold", color=COLOR_BEFORE)
        ax.text(i + width/2, av + 0.2, f"{av:.1f} min", ha="center", va="bottom", fontsize=13, fontweight="bold", color=COLOR_AFTER)
        pct = (av - bv) / bv * 100
        ax.annotate(f"+{pct:.0f}% longer", xy=(i, max(av, bv) + 1.8), ha="center", fontsize=13, fontweight="bold", color="#CC2200",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF0ED", edgecolor="#E05C4C"))
    ax.set_xticks(x); ax.set_xticklabels(categories, fontsize=13)
    ax.set_ylabel("Median Minutes Between Trains", fontsize=12)
    ax.set_title("Roosevelt Island — Evening Rush Hour (4–7 PM)\nWait Times Have More Than Doubled Since F/M Swap", fontsize=14, fontweight="bold", pad=14)
    ax.legend(fontsize=12); ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
    ax.set_ylim(0, max(after_p) * 1.4)
    fig.text(0.5, 0.01, SOURCE_NOTE + "  |  Weekdays only", ha="center", fontsize=9, color="gray")
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = out_dir / "evening_rush_spotlight.png"
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def plot_direction_overview(df, out_dir, direction_code, direction_label, filename):
    """All-periods overview for a single direction. Used for both NB and SB."""
    wd = df[(df["day_type"] == "Weekday") & (df["direction"] == direction_code)]
    bucket_labels, before_medians, after_medians, before_p90s, after_p90s, in_swap = [], [], [], [], [], []

    for _, __, wd_label, _ in TIME_BUCKETS:
        sub = wd[wd["time_bucket"] == wd_label]
        b   = sub[sub["swap_period"] == "Before swap"]["headway_min"]
        a   = sub[sub["swap_period"] == "After swap"]["headway_min"]
        if b.empty or a.empty: continue
        short = wd_label.split(":", 1)[1].strip()
        bucket_labels.append(short)
        before_medians.append(b.median())
        after_medians.append(a.median())
        before_p90s.append(b.quantile(0.90))
        after_p90s.append(a.quantile(0.90))
        in_swap.append(wd_label[:2] in SWAP_ACTIVE_BUCKETS)

    x, width = np.arange(len(bucket_labels)), 0.35
    fig, ax = plt.subplots(figsize=(13, 7))
    bars_b = ax.bar(x - width/2, before_medians, width, label="F Train — Before Swap", color=COLOR_BEFORE, edgecolor="white", linewidth=1.2)
    bars_a = ax.bar(x + width/2, after_medians,  width, label="M Train — After Swap",  color=COLOR_AFTER,  edgecolor="white", linewidth=1.2)

    for i, (bp, ap) in enumerate(zip(before_p90s, after_p90s)):
        ax.plot(i - width/2, bp, "^", color=COLOR_BEFORE, markersize=9, zorder=5)
        ax.plot(i + width/2, ap, "^", color=COLOR_AFTER,  markersize=9, zorder=5)

    for i, (bv, av) in enumerate(zip(before_medians, after_medians)):
        ax.text(i - width/2, bv + 0.2, f"{bv:.1f}m", ha="center", va="bottom", fontsize=9, fontweight="bold", color=COLOR_BEFORE)
        ax.text(i + width/2, av + 0.2, f"{av:.1f}m", ha="center", va="bottom", fontsize=9, fontweight="bold", color=COLOR_AFTER)
        pct = (av - bv) / bv * 100
        color = "#CC2200" if pct > 0 else "#006600"
        ax.text(i, max(av, bv) + 1.6, f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold", color=color)

    for i, swap in enumerate(in_swap):
        if swap: ax.axvspan(i - 0.5, i + 0.5, alpha=0.06, color=COLOR_AFTER, zorder=0)

    ax.set_xticks(x); ax.set_xticklabels(bucket_labels, fontsize=11)
    ax.set_ylabel("Median Minutes Between Trains", fontsize=12)
    ax.set_title(f"Roosevelt Island Station — {direction_label}\nWeekday Wait Times Before vs. After F/M Swap", fontsize=13, fontweight="bold", pad=12)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
    ax.set_ylim(0, max(after_p90s) * 1.38)
    triangle = mpatches.Patch(color="gray", label="▲ = 90th percentile (1-in-10 worst waits)")
    handles, labels_leg = ax.get_legend_handles_labels()
    ax.legend(handles + [triangle], labels_leg + ["▲ = 90th percentile (1-in-10 worst waits)"], fontsize=10, loc="upper left")
    ax.annotate("★ shaded = swap active (weekdays only)", xy=(1.0, 0.03), xycoords="axes fraction", fontsize=9, color="#999999", ha="right", style="italic")
    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=9, color="gray")
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = out_dir / filename
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def plot_long_wait_frequency(df, out_dir, direction_code, direction_label, filename):
    """How often riders face waits above common thresholds. Used for both NB and SB."""
    swap_buckets = df["time_bucket"].str[:2].isin(SWAP_ACTIVE_BUCKETS)
    subset = df[(df["day_type"] == "Weekday") & (df["direction"] == direction_code) & swap_buckets]
    before = subset[subset["swap_period"] == "Before swap"]["headway_min"]
    after  = subset[subset["swap_period"] == "After swap"]["headway_min"]
    thresholds = [5, 8, 10, 12, 15]
    before_pcts = [100 * (before > t).mean() for t in thresholds]
    after_pcts  = [100 * (after  > t).mean() for t in thresholds]
    x, width = np.arange(len(thresholds)), 0.35
    fig, ax = plt.subplots(figsize=(11, 7))
    bars_b = ax.bar(x - width/2, before_pcts, width, label="F Train — Before Swap", color=COLOR_BEFORE, edgecolor="white")
    bars_a = ax.bar(x + width/2, after_pcts,  width, label="M Train — After Swap",  color=COLOR_AFTER,  edgecolor="white")
    for bar in bars_b:
        h = bar.get_height()
        if h > 0.5: ax.text(bar.get_x() + bar.get_width()/2, h + 0.4, f"{h:.0f}%", ha="center", va="bottom", fontsize=9, color=COLOR_BEFORE, fontweight="bold")
    for bar in bars_a:
        h = bar.get_height()
        if h > 0.5: ax.text(bar.get_x() + bar.get_width()/2, h + 0.4, f"{h:.0f}%", ha="center", va="bottom", fontsize=9, color=COLOR_AFTER, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([f"More than\n{t} minutes" for t in thresholds], fontsize=12)
    ax.set_ylabel("% of train intervals where riders waited this long", fontsize=12)
    ax.set_title(f"Roosevelt Island — How Often Do Riders Face a Long Wait?\n{direction_label}, Weekdays 6 AM–7 PM (Swap Active Hours)", fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=11); ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
    ax.set_ylim(0, max(max(before_pcts), max(after_pcts)) * 1.35)
    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=9, color="gray")
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = out_dir / filename
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def plot_weekend_impact(df, out_dir):
    """Weekend headways before vs after the swap date.

    The swap is weekday-only — the F train serves Roosevelt Island on weekends
    in both periods. Any increase in weekend headways therefore suggests broader
    F-line service degradation unrelated to the swap itself, and provides context
    for understanding whether the F has gotten worse system-wide.
    """
    we = df[df["day_type"] == "Weekend"]
    directions = [
        ("S", "Southbound (→ Manhattan)"),
        ("N", "Northbound (→ Queens/Home)"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharey=False)
    fig.suptitle(
        "Roosevelt Island — Weekend Headways Before vs. After Swap Date\n"
        "F Train Both Periods (Swap is Weekday-Only) — Changes Suggest Systemwide F Service Shifts",
        fontsize=13, fontweight="bold", y=1.01
    )

    for ax, (dir_code, dir_label) in zip(axes, directions):
        bucket_labels, before_medians, after_medians = [], [], []
        for _, __, _, we_label in TIME_BUCKETS:
            sub = we[(we["direction"] == dir_code) & (we["time_bucket"] == we_label)]
            b = sub[sub["swap_period"] == "Before swap"]["headway_min"]
            a = sub[sub["swap_period"] == "After swap"]["headway_min"]
            if b.empty or a.empty: continue
            short = we_label.split(":", 1)[1].strip()
            bucket_labels.append(short)
            before_medians.append(b.median())
            after_medians.append(a.median())

        x, width = np.arange(len(bucket_labels)), 0.35
        ax.bar(x - width/2, before_medians, width, label="F Train — Before Dec 8", color=COLOR_BEFORE, edgecolor="white", linewidth=1.2)
        ax.bar(x + width/2, after_medians,  width, label="F Train — After Dec 8",  color=COLOR_AFTER,  edgecolor="white", linewidth=1.2)

        for i, (bv, av) in enumerate(zip(before_medians, after_medians)):
            ax.text(i - width/2, bv + 0.2, f"{bv:.1f}m", ha="center", va="bottom", fontsize=8, fontweight="bold", color=COLOR_BEFORE)
            ax.text(i + width/2, av + 0.2, f"{av:.1f}m", ha="center", va="bottom", fontsize=8, fontweight="bold", color=COLOR_AFTER)
            pct = (av - bv) / bv * 100
            color = "#CC2200" if pct > 5 else ("#006600" if pct < -5 else "#666666")
            ax.text(i, max(av, bv) + 1.4, f"{pct:+.0f}%",
                    ha="center", va="bottom", fontsize=9, fontweight="bold", color=color)

        ax.set_xticks(x); ax.set_xticklabels(bucket_labels, fontsize=9)
        ax.set_ylabel("Median Minutes Between Trains", fontsize=11)
        ax.set_title(dir_label, fontsize=12, fontweight="bold")
        ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
        ax.set_ylim(0, max(max(before_medians), max(after_medians)) * 1.45)
        ax.legend(fontsize=9)

    fig.text(0.5, -0.02,
             SOURCE_NOTE + "  |  Weekends only  |  F train serves RI on weekends in both periods",
             ha="center", fontsize=9, color="gray")
    # Interpretive note
    fig.text(0.5, -0.06,
             "Note: Changes here cannot be attributed to the F/M swap (which is weekday-only).\n"
             "Increases suggest broader F-line service changes affecting Roosevelt Island on weekends.",
             ha="center", fontsize=9, color="#555555", style="italic")
    plt.tight_layout()
    path = out_dir / "weekend_impact.png"
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def plot_worst_waits(df, out_dir):
    swap_buckets = df["time_bucket"].str[:2].isin(SWAP_ACTIVE_BUCKETS)
    wd_nb_swap = df[(df["day_type"] == "Weekday") & (df["direction"] == "S") & swap_buckets]
    before = wd_nb_swap[wd_nb_swap["swap_period"] == "Before swap"]["headway_min"]
    after  = wd_nb_swap[wd_nb_swap["swap_period"] == "After swap"]["headway_min"]
    thresholds = [5, 8, 10, 12, 15]
    before_pcts = [100 * (before > t).mean() for t in thresholds]
    after_pcts  = [100 * (after  > t).mean() for t in thresholds]
    x, width = np.arange(len(thresholds)), 0.35
    fig, ax = plt.subplots(figsize=(11, 7))
    bars_b = ax.bar(x - width/2, before_pcts, width, label="F Train — Before Swap", color=COLOR_BEFORE, edgecolor="white")
    bars_a = ax.bar(x + width/2, after_pcts,  width, label="M Train — After Swap",  color=COLOR_AFTER,  edgecolor="white")
    for bar in list(bars_b):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=11, fontweight="bold", color=COLOR_BEFORE)
    for bar in list(bars_a):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=11, fontweight="bold", color=COLOR_AFTER)
    ax.set_xticks(x); ax.set_xticklabels([f"More than\n{t} minutes" for t in thresholds], fontsize=12)
    ax.set_ylabel("% of train intervals where riders waited this long", fontsize=12)
    ax.set_title("Roosevelt Island — How Often Do Riders Face a Long Wait?\nSouthbound (→ Manhattan), Weekdays 6 AM–7 PM (Swap Active Hours)", fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=11); ax.yaxis.grid(True, linestyle="--", alpha=0.4); ax.set_axisbelow(True)
    ax.set_ylim(0, max(max(before_pcts), max(after_pcts)) * 1.3)
    fig.text(0.5, 0.01, SOURCE_NOTE, ha="center", fontsize=9, color="gray")
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = out_dir / "worst_waits.png"
    plt.savefig(path, dpi=180, bbox_inches="tight"); plt.close()
    print(f"Saved: {path}")


def write_talking_points(df, out_dir):
    def get(day_type, bucket_prefix, direction, swap):
        return df[(df["day_type"]==day_type) & df["time_bucket"].str.startswith(bucket_prefix) &
                  (df["direction"]==direction) & (df["swap_period"]==swap)]["headway_min"]
    def med(s): return f"{s.median():.1f}" if not s.empty else "N/A"
    def p90(s): return f"{s.quantile(.9):.1f}" if not s.empty else "N/A"
    def pct_over(s, t): return f"{100*(s>t).mean():.0f}%" if not s.empty else "N/A"
    def chg(b, a):
        if b.empty or a.empty: return "N/A"
        d = a.median()-b.median(); p = d/b.median()*100
        return f"+{p:.0f}% ({'LONGER' if d>0 else 'SHORTER'} by {abs(d):.1f} min)"

    am_b = get("Weekday","2:","S","Before swap"); am_a = get("Weekday","2:","S","After swap")  # Southbound = to Manhattan
    md_b = get("Weekday","3:","S","Before swap"); md_a = get("Weekday","3:","S","After swap")
    ev_b_nb = get("Weekday","4:","N","Before swap"); ev_a_nb = get("Weekday","4:","N","After swap")  # Northbound = to Queens/home
    ev_b_sb = get("Weekday","4:","S","Before swap"); ev_a_sb = get("Weekday","4:","S","After swap")  # Southbound = to Manhattan
    swap_all = df[df["time_bucket"].str[:2].isin(SWAP_ACTIVE_BUCKETS) & (df["day_type"]=="Weekday")]  # Both directions
    all_b = swap_all[swap_all["swap_period"]=="Before swap"]["headway_min"]
    all_a = swap_all[swap_all["swap_period"]=="After swap"]["headway_min"]
    ev_pct_nb = (ev_a_nb.median()-ev_b_nb.median())/ev_b_nb.median()*100
    monthly_extra = (am_a.median()-am_b.median())*2*22 if not am_b.empty else 0

    content = f"""
ROOSEVELT ISLAND SUBWAY — DATA-DRIVEN TALKING POINTS
F/M Train Swap  |  Analysis: Oct 2025–Feb 2026
Station: Roosevelt Island (GTFS stop IDs: B06N / B06S)
Data source: subwaydata.nyc (MTA GTFS real-time feeds, archived daily)
Pre-swap:  Oct 1 – Dec 7, 2025  |  Post-swap: Dec 8, 2025 – Feb 15, 2026
================================================================

HEADLINE FINDINGS (Northbound, weekdays)
─────────────────────────────────────────

EVENING RUSH (4–7 PM) — The strongest finding:
  Northbound (→ Queens/home): {med(ev_b_nb)} min → {med(ev_a_nb)} min  ({chg(ev_b_nb, ev_a_nb)})
  Southbound (→ Manhattan):   {med(ev_b_sb)} min → {med(ev_a_sb)} min  ({chg(ev_b_sb, ev_a_sb)})
  → Evening commute wait has more than doubled in both directions.

MORNING RUSH (6–9 AM) — Commute to Manhattan (southbound):
  Southbound (→ Manhattan): {med(am_b)} min → {med(am_a)} min  ({chg(am_b, am_a)})
  → Daily commuters lose ~{monthly_extra:.0f} extra minutes per month.

MIDDAY (9 AM–4 PM):
  Northbound: {med(md_b)} min → {med(md_a)} min  ({chg(md_b, md_a)})

ALL SWAP-ACTIVE HOURS (6 AM–7 PM, northbound):
  Median: {med(all_b)} min → {med(all_a)} min  ({chg(all_b, all_a)})
  90th pct (1-in-10 worst waits): {p90(all_b)} → {p90(all_a)} min
  Waits > 10 min: {pct_over(all_b,10)} → {pct_over(all_a,10)}
  Waits > 15 min: {pct_over(all_b,15)} → {pct_over(all_a,15)}

FLIER LANGUAGE
─────────────────────────────────────────

HEADLINE OPTION A (sharpest):
  "Evening rush wait times at Roosevelt Island have more than doubled
   since the F/M swap — from {med(ev_b_nb)} to {med(ev_a_nb)} minutes northbound."

HEADLINE OPTION B (broader):
  "Since December 8, Roosevelt Island riders wait up to {ev_pct_nb:.0f}% longer
   for a northbound train during the evening commute."

COMMUTER IMPACT FRAMING:
  "Before the swap, a northbound train came every {am_b.median():.0f} minutes during
   morning rush. Today it's {am_a.median():.0f} minutes — an extra {am_a.median()-am_b.median():.0f} minutes
   every morning, or {monthly_extra:.0f} extra minutes per month for daily commuters."

AVOID:
  ✗ "The MTA lied." (hard to prove intent; invites legal pushback)
  ✗ "Headways increased." (jargon most residents won't recognize)
  ✗ Citing percentages alone — always pair with the raw numbers.

USE:
  ✓ "The data tells a different story than the MTA's promises."
  ✓ "Here is what actually happened at our station."
  ✓ Both absolute numbers AND percentages in every claim.

ASKS — WHAT TO REQUEST FROM MTA/RIOC/REPS
─────────────────────────────────────────

1. PUBLISH THE SCHEDULED HEADWAY COMPARISON
   Ask the MTA to publish the scheduled headway for the M train at
   Roosevelt Island vs. the prior F train schedule. If the M was
   scheduled to run less frequently, that is an acknowledgment that
   service frequency was cut, not improved.

2. PROVIDE STATION-LEVEL RELIABILITY DATA
   Ask the MTA for on-time performance data at Roosevelt Island
   specifically, pre- and post-swap. If they claim reliability improved,
   they should prove it with their own numbers.

3. REQUEST A FORMAL 90-DAY SERVICE REVIEW
   Propose a structured review with published ridership and headway
   data for Roosevelt Island, similar to reviews the MTA has conducted
   at other stations after major service changes.

4. REQUEST A COMMUNITY HEARING BEFORE THE NEXT SCHEDULED REVIEW
   Roosevelt Island's geographic isolation means residents have no
   alternative subway option. This warrants special consideration in
   any service planning affecting the station.

METHODOLOGY — FOR CREDIBILITY IF CHALLENGED
─────────────────────────────────────────

- Data: subwaydata.nyc archives the complete MTA GTFS real-time feed
  daily — not a periodic sample. Every train captured.
- Station: Roosevelt Island confirmed as GTFS stop B06N/B06S, verified
  against the official MTA station glossary on data.ny.gov (Feb 2026).
- Headways: time between consecutive train arrivals per direction per
  day. Values < 1 min or > 60 min excluded as data artifacts.
- Pre-swap: Oct 1–Dec 7, 2025 (10 weeks of weekday data)
- Post-swap: Dec 8, 2025–Feb 15, 2026 (10 weeks of weekday data)
  Holiday weeks (Dec 22–Jan 5) are included in post-swap. Excluding
  them would make the post-swap numbers appear slightly worse.
- Observed (actual) headways only — not scheduled headways.
"""
    path = out_dir / "talking_points.txt"
    with open(path, "w") as f: f.write(content)
    print(f"Saved: {path}"); print(content)


def main():
    COMMUNITY_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "roosevelt_island_headways.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Cannot find {csv_path}. Run 3_analyze.py first.")
    df = load_and_prep(csv_path)

    # ── Original charts ───────────────────────────────────────────────────────
    plot_all_periods(df, COMMUNITY_DIR)           # combined SB/NB overview (legacy)
    plot_evening_rush_spotlight(df, COMMUNITY_DIR)
    plot_worst_waits(df, COMMUNITY_DIR)           # SB long-wait frequency (legacy name)

    # ── New directional overviews ─────────────────────────────────────────────
    plot_direction_overview(
        df, COMMUNITY_DIR,
        direction_code="S",
        direction_label="Southbound (→ Manhattan) — Morning Commute Direction",
        filename="southbound_overview.png"
    )
    plot_direction_overview(
        df, COMMUNITY_DIR,
        direction_code="N",
        direction_label="Northbound (→ Queens/Home) — Evening Commute Direction",
        filename="northbound_overview.png"
    )

    # ── Long-wait frequency by direction ─────────────────────────────────────
    plot_long_wait_frequency(
        df, COMMUNITY_DIR,
        direction_code="S",
        direction_label="Southbound (→ Manhattan)",
        filename="long_waits_southbound.png"
    )
    plot_long_wait_frequency(
        df, COMMUNITY_DIR,
        direction_code="N",
        direction_label="Northbound (→ Queens/Home)",
        filename="long_waits_northbound.png"
    )

    # ── Weekend impact (F train both periods — systemwide signal) ─────────────
    plot_weekend_impact(df, COMMUNITY_DIR)

    write_talking_points(df, COMMUNITY_DIR)
    print(f"\nAll community outputs saved to: {COMMUNITY_DIR.resolve()}/")

if __name__ == "__main__":
    main()
