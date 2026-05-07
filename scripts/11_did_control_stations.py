"""
SCRIPT 11: DIFFERENCE-IN-DIFFERENCES VS CONTROL STATIONS
==========================================================
Closes the MTA's "first months were affected by systemwide incidents
and historic winter storms" defense by comparing the pre→post wait-time
change at Roosevelt Island against pre→post changes at unaffected
control stations.

The DiD logic:
  Δ_treatment = wait_time_post(RI) − wait_time_pre(RI)
  Δ_control_i = wait_time_post(control_i) − wait_time_pre(control_i)
  DiD_i        = Δ_treatment − Δ_control_i

If winter storms and systemwide incidents had inflated the post-period
RI numbers, control stations on independent or unchanged routes would
show similar inflation. If controls are flat, the RI delta is
swap-attributable.

CONTROLS:
  - 7 train at Queensboro Plaza (718) — completely independent line
    (B division vs IRT; different rolling stock, different control
    system). Most independent control.
  - R train at Queens Plaza (G21) — same QBL corridor as the affected M;
    R route unchanged through the swap. Captures any QBL-corridor-wide
    effect (weather, incidents, seasonal ridership).

INPUTS:
  - results/roosevelt_island_headways.csv          (3_analyze.py)
  - results/queensboro/queensboro_headways.csv     (8_analyze_queensboro_plaza.py)

OUTPUTS (saved to results/did_control_stations/):
  - did_summary.csv          — DiD estimates with bootstrap CIs
  - did_monthly.csv          — monthly wait time per station
  - did_chart.png            — bar chart: RI Δ vs control Δ vs DiD residual
  - did_monthly.png          — monthly trend lines, treatment vs controls
  - did_report.txt           — narrative
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SCRIPTS_DIR = Path(__file__).parent
RESULTS_DIR = SCRIPTS_DIR / "results"
OUT_DIR     = RESULTS_DIR / "did_control_stations"

RI_HEADWAYS_CSV   = RESULTS_DIR / "roosevelt_island_headways.csv"
QPZ_HEADWAYS_CSV  = RESULTS_DIR / "queensboro" / "queensboro_headways.csv"

PEAK_BUCKET_PREFIXES = {"2:", "4:"}     # Morning Rush + Evening Rush
N_BOOTSTRAP   = 1000
BOOTSTRAP_SEED = 42

# (station_label, source_csv, route_group, station_group_filter, role)
# role ∈ {"treatment", "control"}
SCOPES = [
    {
        "label":         "Roosevelt Island (F→M, swap-affected)",
        "short":         "RI (B06)",
        "csv":           RI_HEADWAYS_CSV,
        "route_filter":  None,           # all routes — F pre, M post
        "station_group": None,
        "role":          "treatment",
    },
    {
        "label":         "Queens Plaza R train (route unchanged)",
        "short":         "R @ G21",
        "csv":           QPZ_HEADWAYS_CSV,
        "route_filter":  "R",
        "station_group": "Queens Plaza",
        "role":          "control",
    },
    {
        "label":         "Queensboro Plaza 7 train (independent line)",
        "short":         "7 @ 718",
        "csv":           QPZ_HEADWAYS_CSV,
        "route_filter":  "7/7X",
        "station_group": "Queensboro Plaza (7/N/W)",
        "role":          "control",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def load_scope(scope: dict) -> pd.DataFrame:
    """
    Returns a DataFrame with columns
        arrival_date, hour, direction, swap_period, time_bucket,
        is_weekday, headway_min, is_holiday_week (if available)
    filtered to weekday + non-holiday + the scope's route/station.
    """
    df = pd.read_csv(scope["csv"], low_memory=False)
    if scope["route_filter"] is not None:
        col = "route_group" if "route_group" in df.columns else "route_id"
        df = df[df[col] == scope["route_filter"]]
    if scope["station_group"] is not None and "station_group" in df.columns:
        df = df[df["station_group"] == scope["station_group"]]
    if "is_weekday" in df.columns:
        df = df[df["is_weekday"]]
    if "is_holiday_week" in df.columns:
        df = df[~df["is_holiday_week"]]
    df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    return df


# ══════════════════════════════════════════════════════════════════════════════
# DIFFERENCE-IN-DIFFERENCES
# ══════════════════════════════════════════════════════════════════════════════

def compute_did(treat_df: pd.DataFrame,
                  control_df: pd.DataFrame,
                  bucket_prefix: str,
                  direction: str,
                  n_boot: int = N_BOOTSTRAP,
                  seed: int = BOOTSTRAP_SEED) -> dict:
    """
    Bootstrap DiD for one (time_bucket, direction) cell. Resamples within
    each (station × period) cell with replacement, computes wait_time =
    mean/2 in each, then DiD = (post_RI − pre_RI) − (post_ctrl − pre_ctrl).
    """
    def _slice(df, period):
        s = df[
            df["time_bucket"].str.startswith(bucket_prefix) &
            (df["direction"]   == direction) &
            (df["swap_period"] == period)
        ]["headway_min"].dropna().to_numpy()
        return s

    t_pre,  t_post = _slice(treat_df,   "Before swap"), _slice(treat_df,   "After swap")
    c_pre,  c_post = _slice(control_df, "Before swap"), _slice(control_df, "After swap")

    if min(len(t_pre), len(t_post), len(c_pre), len(c_post)) < 30:
        return None

    wait_t_pre,  wait_t_post  = t_pre.mean()/2,  t_post.mean()/2
    wait_c_pre,  wait_c_post  = c_pre.mean()/2,  c_post.mean()/2
    delta_t = wait_t_post - wait_t_pre
    delta_c = wait_c_post - wait_c_pre
    did     = delta_t - delta_c

    rng = np.random.default_rng(seed)
    dids = np.empty(n_boot)
    for i in range(n_boot):
        tp  = rng.choice(t_pre,  size=len(t_pre),  replace=True).mean()/2
        tq  = rng.choice(t_post, size=len(t_post), replace=True).mean()/2
        cp  = rng.choice(c_pre,  size=len(c_pre),  replace=True).mean()/2
        cq  = rng.choice(c_post, size=len(c_post), replace=True).mean()/2
        dids[i] = (tq - tp) - (cq - cp)

    return {
        "treat_wait_pre":  round(float(wait_t_pre),  2),
        "treat_wait_post": round(float(wait_t_post), 2),
        "treat_delta":     round(float(delta_t),     2),
        "ctrl_wait_pre":   round(float(wait_c_pre),  2),
        "ctrl_wait_post":  round(float(wait_c_post), 2),
        "ctrl_delta":      round(float(delta_c),     2),
        "did":             round(float(did),         2),
        "did_ci_low":      round(float(np.percentile(dids,  2.5)), 2),
        "did_ci_high":     round(float(np.percentile(dids, 97.5)), 2),
        "n_t_pre":  int(len(t_pre)),  "n_t_post": int(len(t_post)),
        "n_c_pre":  int(len(c_pre)),  "n_c_post": int(len(c_post)),
    }


def did_table(treat_df: pd.DataFrame, controls: list) -> pd.DataFrame:
    """Build one row per (time_bucket, direction, control)."""
    rows = []
    for bucket_prefix, bucket_label in [("2:", "Morning Rush (6–9 AM)"),
                                          ("4:", "Evening Rush (4–7 PM)")]:
        for direction, dir_label in [("S", "Southbound"), ("N", "Northbound")]:
            for ctrl_scope, ctrl_df in controls:
                res = compute_did(treat_df, ctrl_df, bucket_prefix, direction)
                if res is None:
                    continue
                rows.append({
                    "time_bucket":    bucket_label,
                    "direction":      dir_label,
                    "control_label":  ctrl_scope["short"],
                    "control_full":   ctrl_scope["label"],
                    **res,
                })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY TREND
# ══════════════════════════════════════════════════════════════════════════════

def monthly_wait_time(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Weekday peak-hour wait time (= mean/2) per calendar month."""
    sub = df[df["time_bucket"].str[:2].isin(PEAK_BUCKET_PREFIXES)].copy()
    sub["arrival_month"] = pd.to_datetime(sub["arrival_date"]).dt.to_period("M").astype(str)
    g = sub.groupby("arrival_month")["headway_min"].agg(n="count", mean="mean").reset_index()
    g["wait_time_min"] = g["mean"] / 2
    g["station"] = label
    return g


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_did_bars(did_df: pd.DataFrame, out_path: Path) -> None:
    """
    For each (bucket × direction), grouped bars showing:
      - Δ at Roosevelt Island (treatment)
      - Δ at each control
      - DiD residual (RI Δ − control Δ) with 95% CI error bar
    """
    if did_df.empty:
        print("  [WARN] No DiD rows; skipping chart.")
        return

    cells = list(did_df[["time_bucket", "direction"]].drop_duplicates()
                  .itertuples(index=False, name=None))
    n = len(cells)
    fig, axes = plt.subplots(1, n, figsize=(5.0 * n, 6), sharey=True)
    if n == 1:
        axes = [axes]

    fig.suptitle(
        "Difference-in-Differences: Wait-Time Δ at Roosevelt Island vs Controls\n"
        "Test of MTA's \"early months were noisy\" defense",
        fontsize=12.5, fontweight="bold",
    )

    for ax, (bucket, direction) in zip(axes, cells):
        sub = did_df[(did_df["time_bucket"] == bucket) &
                     (did_df["direction"]  == direction)]
        if sub.empty:
            continue
        # Build groups: RI Δ (single, identical across controls), each control Δ,
        # each DiD residual.
        ri_delta = sub["treat_delta"].iloc[0]

        positions, heights, colors, labels, ci = [], [], [], [], []
        # RI bar (treatment)
        positions.append(0)
        heights.append(ri_delta)
        colors.append("#E05C4C")
        labels.append("RI\n(treatment)")
        ci.append(None)

        x = 1.2
        for _, r in sub.iterrows():
            positions.append(x); heights.append(r["ctrl_delta"])
            colors.append("#4C8BE0")
            labels.append(f"Δ\n{r['control_label']}")
            ci.append(None)
            x += 1.0

            positions.append(x); heights.append(r["did"])
            colors.append("#1A7A3F")
            labels.append(f"DiD\n{r['control_label']}")
            ci.append((r["did_ci_low"], r["did_ci_high"]))
            x += 1.6

        for pos, h, c in zip(positions, heights, colors):
            ax.bar(pos, h, width=0.85, color=c, alpha=0.85, zorder=3)
        for pos, h, ci_pair in zip(positions, heights, ci):
            if ci_pair is not None:
                lo, hi = ci_pair
                ax.errorbar(pos, h, yerr=[[h - lo], [hi - h]],
                             fmt="none", color="black", capsize=4,
                             linewidth=1.2, zorder=4)
            ax.text(pos, h + (0.15 if h >= 0 else -0.25),
                     f"{h:+.2f}", ha="center", va="bottom" if h >= 0 else "top",
                     fontsize=8.5, fontweight="bold")

        # MTA's commitment line
        ax.axhline(1.0, color="#888888", linestyle="--", linewidth=1, zorder=1)
        ax.text(positions[-1] + 0.5, 1.0, "MTA's +1 min\ncommitment",
                 fontsize=8, color="#666666", va="center")

        ax.set_xticks(positions)
        ax.set_xticklabels(labels, fontsize=8.5)
        ax.set_title(f"{direction} — {bucket}", fontsize=10.5, fontweight="bold")
        ax.set_ylabel("Δ wait time (post − pre, min)")
        ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
        ax.axhline(0, color="black", linewidth=0.6, zorder=2)

    fig.text(0.5, -0.02,
              "Wait time = mean headway / 2 (MTA methodology). "
              "DiD = Δ_RI − Δ_control. CI = 95% bootstrap (1000 resamples). "
              "If DiD ≫ 0, the RI change is not explained by systemwide noise.",
              ha="center", fontsize=8.5, color="gray")
    plt.tight_layout(rect=[0, 0.03, 1, 0.93])
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def plot_monthly_trend(monthly_df: pd.DataFrame, out_path: Path) -> None:
    if monthly_df.empty:
        return

    fig, ax = plt.subplots(figsize=(13, 5.5))
    fig.suptitle(
        "Weekday peak wait time by month — Roosevelt Island vs control stations\n"
        "MTA's \"noisy early months\" defense should produce parallel post-swap "
        "drift across stations",
        fontsize=11.5, fontweight="bold"
    )

    monthly_df = monthly_df.copy()
    monthly_df["arrival_month_dt"] = pd.to_datetime(monthly_df["arrival_month"] + "-01")

    style = {
        "RI (B06)":  ("#E05C4C", "-",  "o", 2.6, "Roosevelt Island (treatment)"),
        "R @ G21":   ("#4C8BE0", "--", "s", 2.0, "R train @ Queens Plaza (control)"),
        "7 @ 718":   ("#6AAF40", "--", "^", 2.0, "7 train @ Queensboro Plaza (control)"),
    }
    for station, (color, ls, marker, lw, lbl) in style.items():
        d = monthly_df[monthly_df["station"] == station].sort_values("arrival_month_dt")
        if d.empty:
            continue
        ax.plot(d["arrival_month_dt"], d["wait_time_min"],
                 color=color, linestyle=ls, marker=marker, linewidth=lw,
                 markersize=6, label=lbl)

    ax.axvline(pd.Timestamp("2025-12-08"), color="black", linestyle=":",
                linewidth=1.5)
    ax.text(pd.Timestamp("2025-12-08"), ax.get_ylim()[1] * 0.96,
             "  ← F train     M train →",
             fontsize=9, va="top",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="black"))

    ax.set_xlabel("Month")
    ax.set_ylabel("Wait time (E[H]/2, min)")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)
    ax.legend(fontsize=9, loc="upper left")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0)

    fig.text(0.5, -0.02,
              "Source: subwaydata.nyc weekday peak hours, non-holiday. "
              "Wait time = mean headway / 2 (MTA methodology).",
              ha="center", fontsize=8.5, color="gray")
    plt.tight_layout(rect=[0, 0.03, 1, 0.92])
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(did_df: pd.DataFrame, out_dir: Path) -> None:
    lines = [
        "DIFFERENCE-IN-DIFFERENCES: ROOSEVELT ISLAND vs CONTROL STATIONS",
        "Closing the \"early months were noisy\" defense from the MTA's April 2026 letter",
        "=" * 75,
        "",
        "DESIGN:",
        "  Treatment: Roosevelt Island (B06) — F pre-swap, M post-swap.",
        "  Controls:",
        "    - R train at Queens Plaza (G21): same QBL corridor; route",
        "      unchanged through swap. Captures any QBL-wide drift.",
        "    - 7 train at Queensboro Plaza (718): completely independent",
        "      line (IRT vs B division). Captures systemwide drift only.",
        "",
        "  DiD = (RI_post − RI_pre) − (control_post − control_pre).",
        "  If the MTA's \"systemwide incidents and historic winter storms\"",
        "  defense were the explanation, controls would show similar drift",
        "  and DiD ≈ 0. A large positive DiD = the change is swap-specific.",
        "",
        "  Wait time = mean headway / 2 (MTA methodology). 95% CIs from",
        "  1000-resample bootstrap.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "RESULTS",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for _, r in did_df.iterrows():
        lines += [
            f"  {r['direction']} — {r['time_bucket']} | control: {r['control_full']}",
            f"    Treatment Δ wait (RI):       {r['treat_wait_pre']:.2f} → "
            f"{r['treat_wait_post']:.2f}  ({r['treat_delta']:+.2f} min)",
            f"    Control   Δ wait:            {r['ctrl_wait_pre']:.2f} → "
            f"{r['ctrl_wait_post']:.2f}  ({r['ctrl_delta']:+.2f} min)",
            f"    DiD:                         {r['did']:+.2f} min  "
            f"[95% CI {r['did_ci_low']:+.2f}, {r['did_ci_high']:+.2f}]",
            "",
        ]

    # Headline
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "INTERPRETATION",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    avg_did = did_df["did"].mean()
    avg_ctrl_delta = did_df["ctrl_delta"].mean()
    avg_treat_delta = did_df["treat_delta"].mean()

    lines += [
        f"  Average treatment Δ wait at RI:      {avg_treat_delta:+.2f} min",
        f"  Average control   Δ wait:            {avg_ctrl_delta:+.2f} min",
        f"  Average DiD (swap-attributable):     {avg_did:+.2f} min",
        "",
        "  If the post-swap RI drift were driven by systemwide noise, the",
        "  control stations would have drifted by a similar amount and DiD",
        "  would be ≈ 0. The DiD value above is the swap-attributable share",
        "  of the wait-time increase, net of any systemwide effects.",
        "",
        "  Compare against the MTA's September 2025 commitment of +1 min",
        f"  average additional wait. Average DiD: {avg_did:+.2f} min, "
        f"vs commitment: +1.00 min.",
        "",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "did_report.txt"
    path.write_text("\n".join(lines))
    print(f"Saved: {path}\n")
    print("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load all scopes
    print("Loading data...")
    loaded = []
    for scope in SCOPES:
        df = load_scope(scope)
        loaded.append((scope, df))
        print(f"  {scope['short']:<10}: {len(df):,} weekday non-holiday headways")
    print()

    treat_scope, treat_df = loaded[0]
    controls = [(s, d) for (s, d) in loaded[1:]]

    # ── DiD table ────────────────────────────────────────────────────────
    print("Computing DiD with bootstrap CIs...")
    did_df = did_table(treat_df, controls)
    did_df.to_csv(OUT_DIR / "did_summary.csv", index=False)
    print(f"  {len(did_df)} cells")
    print()
    print("── DiD table ───────────────────────────────────────────────────")
    show_cols = ["time_bucket", "direction", "control_label",
                 "treat_delta", "ctrl_delta", "did", "did_ci_low", "did_ci_high"]
    print(did_df[show_cols].to_string(index=False))
    print()

    # ── Monthly trend ────────────────────────────────────────────────────
    print("Building monthly trend...")
    pieces = []
    for scope, df in loaded:
        if df.empty:
            continue
        m = monthly_wait_time(df, scope["short"])
        pieces.append(m)
    monthly_df = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    monthly_df.to_csv(OUT_DIR / "did_monthly.csv", index=False)
    print()

    # ── Charts ───────────────────────────────────────────────────────────
    plot_did_bars(did_df, OUT_DIR / "did_chart.png")
    plot_monthly_trend(monthly_df, OUT_DIR / "did_monthly.png")

    # ── Report ───────────────────────────────────────────────────────────
    write_report(did_df, OUT_DIR)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
