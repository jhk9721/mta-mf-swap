"""
app.py — Roosevelt Island Transit Dashboard
============================================
Run locally:  streamlit run app.py
Deploy:       Push to GitHub → connect to Render or Streamlit Community Cloud

Data:  Place roosevelt_island_headways.csv alongside this file (or in data/).
       Run scripts/3_analyze.py first if you don't have the CSV.
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from data_loader import (
    load_headways, get_median, get_pct_over,
    SWAP_DATE, SWAP_ACTIVE_BUCKETS, TIME_BUCKETS
)
from analytics import init_analytics, track_scroll_depth

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Roosevelt Island Transit — F/M Swap Analysis",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Analytics (privacy-first) ─────────────────────────────────────────────────
init_analytics()

# ── Theme constants ───────────────────────────────────────────────────────────
MTA_ORANGE  = "#FF6319"   # accent / brand (borders, links, CTAs)
DARK_NAVY   = "#0D1B2A"
MID_NAVY    = "#1B2E44"
LIGHT_NAVY  = "#243B55"
BLUE_BEFORE = "#3A9BFF"   # F-train "before" — vivid, unambiguously blue
RED_AFTER   = "#E8334A"   # M-train "after" — clearly red, visually apart from MTA_ORANGE
AMBER_SWAP  = "#F4A261"   # neutral comparison bar (sensitivity chart middle)
TEXT_LIGHT  = "#F0F4F8"
TEXT_MUTED  = "#9DB4C8"   # bumped slightly lighter for WCAG readability
GREEN_OK    = "#2ECC71"

BUCKET_ORDER = [
    "Early AM (12–6 AM)",
    "Morning Rush (6–9 AM)",
    "Midday (9 AM–4 PM)",
    "Evening Rush (4–7 PM)",
    "Night (7 PM–midnight)",
]

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

  html, body, [class*="css"] {{
    font-family: 'DM Sans', sans-serif;
    background-color: {DARK_NAVY};
    color: {TEXT_LIGHT};
  }}

  /* ── Header ── */
  .header-strip {{
    background: linear-gradient(135deg, {DARK_NAVY} 0%, {MID_NAVY} 100%);
    border-bottom: 3px solid {MTA_ORANGE};
    padding: 2rem 2.5rem 1.5rem;
    margin: -1rem -1rem 0 -1rem;
  }}
  .header-tag {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    color: {MTA_ORANGE};
    text-transform: uppercase;
    margin-bottom: 0.4rem;
  }}
  .header-title {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2.6rem;
    font-weight: 800;
    color: {TEXT_LIGHT};
    line-height: 1.1;
    margin: 0;
  }}
  .header-subtitle {{
    font-size: 1rem;
    color: {TEXT_LIGHT};
    opacity: 0.85;
    margin-top: 0.5rem;
    max-width: 720px;
    line-height: 1.55;
  }}

  /* ── Navigation bar ── */
  .nav-bar {{
    background: {MID_NAVY};
    border-bottom: 2px solid {LIGHT_NAVY};
    padding: 0.65rem 2rem;
    text-align: center;
    margin: 0 -1rem 2rem -1rem;
  }}
  .nav-bar a {{
    color: {TEXT_MUTED};
    margin: 0 1.1rem;
    text-decoration: none;
    font-weight: 500;
    font-size: 0.88rem;
    white-space: nowrap;
  }}
  .nav-bar a:hover, .nav-bar a.active {{ color: {MTA_ORANGE}; }}

  /* ── Metric cards ── */
  .metric-card {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    border-left: 4px solid {MTA_ORANGE};
    height: 100%;
  }}
  .metric-card.alarm {{ border-left-color: {RED_AFTER}; }}
  .metric-card.ok    {{ border-left-color: {GREEN_OK}; }}
  .metric-label {{
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {TEXT_MUTED};
    margin-bottom: 0.3rem;
  }}
  .metric-value {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    color: {TEXT_LIGHT};
    line-height: 1;
  }}
  .metric-value.red    {{ color: {RED_AFTER}; }}
  .metric-value.orange {{ color: {MTA_ORANGE}; }}
  .metric-value.green  {{ color: {GREEN_OK}; }}
  .metric-sub {{
    font-size: 0.78rem;
    color: {TEXT_MUTED};
    margin-top: 0.3rem;
  }}

  /* ── Section headers ── */
  .section-head {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: {TEXT_LIGHT};
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 2px solid {MTA_ORANGE};
    padding-bottom: 0.4rem;
    margin: 2rem 0 1rem 0;
  }}

  /* ── Section divider ── */
  .section-divider {{
    border: none;
    border-top: 1px solid {LIGHT_NAVY};
    margin: 3.5rem 0 0.5rem 0;
  }}

  /* ── Callout box ── */
  .callout {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-left: 4px solid {MTA_ORANGE};
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.4rem;
    margin: 1rem 0;
    font-size: 0.9rem;
    color: {TEXT_LIGHT};
    opacity: 0.9;
    line-height: 1.6;
  }}
  .callout strong {{ color: {TEXT_LIGHT}; opacity: 1; }}
  .callout.alarm {{
    border-left-color: {RED_AFTER};
    background: rgba(232, 51, 74, 0.07);
  }}

  /* ── Plain-English summary banner ── */
  .plain-summary {{
    background: linear-gradient(135deg, #112035 0%, {MID_NAVY} 100%);
    border: 1px solid {BLUE_BEFORE};
    border-left: 5px solid {BLUE_BEFORE};
    border-radius: 0 10px 10px 0;
    padding: 1.1rem 1.6rem;
    margin: 1.5rem 0;
    font-size: 1rem;
    color: {TEXT_LIGHT};
    line-height: 1.65;
  }}
  .plain-summary .ps-label {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: {BLUE_BEFORE};
    margin-bottom: 0.4rem;
  }}

  /* ── Big stat callout (hero) ── */
  .big-stat {{
    background: {MID_NAVY};
    border-left: 5px solid {RED_AFTER};
    border-radius: 0 12px 12px 0;
    padding: 1.8rem 2rem;
    margin: 1.2rem 0 1.5rem 0;
    text-align: center;
  }}
  .big-stat-number {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 3rem;
    font-weight: 800;
    color: {RED_AFTER};
    line-height: 1.1;
  }}
  .big-stat-label {{
    font-size: 1rem;
    color: {TEXT_LIGHT};
    margin: 0.5rem 0 0.3rem;
    font-weight: 500;
  }}
  .big-stat-sub {{
    font-size: 0.88rem;
    color: {TEXT_MUTED};
    line-height: 1.55;
    margin-top: 0.4rem;
  }}

  /* ── Promise vs reality cards ── */
  .promise-card {{
    border-radius: 0 8px 8px 0;
    padding: 1.5rem;
  }}
  .promise-label {{
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.8rem;
  }}
  .promise-quote {{
    font-size: 1rem;
    color: {TEXT_LIGHT};
    line-height: 1.65;
    font-style: italic;
  }}
  .promise-attribution {{
    font-size: 0.82rem;
    color: {TEXT_MUTED};
    margin-top: 0.8rem;
  }}

  /* ── Key-questions grid ── */
  .qa-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.75rem;
    margin: 0.75rem 0;
  }}
  .qa-item {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-radius: 8px;
    padding: 0.9rem 1.1rem;
  }}
  .qa-verdict {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 0.25rem;
  }}
  .qa-verdict.no  {{ color: {MTA_ORANGE}; }}
  .qa-verdict.yes {{ color: {RED_AFTER}; }}
  .qa-q {{
    font-weight: 600;
    color: {TEXT_LIGHT};
    font-size: 0.86rem;
    margin-bottom: 0.3rem;
  }}
  .qa-a {{
    font-size: 0.82rem;
    color: {TEXT_MUTED};
    line-height: 1.5;
  }}

  /* ── CTA buttons ── */
  .cta-btn {{
    display: block;
    padding: 1.4rem 1.2rem;
    border-radius: 8px;
    text-align: center;
    text-decoration: none;
  }}
  .cta-btn:hover {{ opacity: 0.88; }}

  /* ── Hide Streamlit chrome ── */
  #MainMenu, footer, header {{ visibility: hidden; }}
  div[data-testid="stVerticalBlock"] > div {{ padding-top: 0; }}

  /* ── Mobile responsive ── */
  @media (max-width: 768px) {{
    /* Typography */
    .header-title    {{ font-size: 1.6rem !important; line-height: 1.2 !important; }}
    .header-subtitle {{ font-size: 0.9rem !important; }}
    .big-stat-number {{ font-size: 2rem !important; }}
    .metric-value    {{ font-size: 2rem !important; }}
    .metric-label    {{ font-size: 0.65rem !important; }}
    .metric-card     {{ margin-bottom: 1rem; }}
    p, .qa-a, .callout, .plain-summary {{ font-size: 0.95rem !important; line-height: 1.6 !important; }}
    .section-head    {{ font-size: 1.2rem !important; }}

    /* Sticky nav */
    .nav-bar {{
      position: sticky;
      top: 0;
      z-index: 999;
      padding: 0.5rem 0.75rem;
      overflow-x: auto;
      white-space: nowrap;
    }}
    .nav-bar a {{ margin: 0 0.5rem; font-size: 0.78rem; }}

    /* Stack Streamlit columns */
    [data-testid="column"] {{ width: 100% !important; flex: 100% !important; }}

    /* CTA buttons: stack vertically, full-width, generous touch target */
    .cta-row {{ flex-direction: column !important; }}
    .cta-row > * {{ min-height: 64px; width: 100% !important; box-sizing: border-box; }}

    /* Content padding */
    .block-container {{
      padding-left: 1rem !important;
      padding-right: 1rem !important;
    }}
  }}
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading transit data...")
def get_data() -> pd.DataFrame:
    return load_headways(source="csv")


df = get_data()
n_obs      = len(df)
date_min   = df["arrival_date"].min()
date_max   = df["arrival_date"].max()
n_weekdays = df[df["is_weekday"]]["arrival_date"].nunique()


# ── Computed metrics (used throughout layout) ─────────────────────────────────
ev_nb_b = get_median(df, day_type="Weekday", bucket="Evening Rush (4–7 PM)", direction="N", period="Before swap")
ev_nb_a = get_median(df, day_type="Weekday", bucket="Evening Rush (4–7 PM)", direction="N", period="After swap")
am_sb_b = get_median(df, day_type="Weekday", bucket="Morning Rush (6–9 AM)", direction="S", period="Before swap")
am_sb_a = get_median(df, day_type="Weekday", bucket="Morning Rush (6–9 AM)", direction="S", period="After swap")
pct_over_10_before = get_pct_over(df, 10.0, direction="N", period="Before swap")
pct_over_10_after  = get_pct_over(df, 10.0, direction="N", period="After swap")

ev_pct        = (ev_nb_a - ev_nb_b) / ev_nb_b * 100
am_pct        = (am_sb_a - am_sb_b) / am_sb_b * 100
ev_delta      = ev_nb_a - ev_nb_b
am_delta      = am_sb_a - am_sb_b
monthly_extra = am_delta * 2 * 22

# Extreme wait statistics — both directions, swap-active hours, weekdays
_ew_bef = df[df["within_swap_window"] & (df["day_type"] == "Weekday") & (df["swap_period"] == "Before swap")]["headway_min"]
_ew_aft = df[df["within_swap_window"] & (df["day_type"] == "Weekday") & (df["swap_period"] == "After swap")]["headway_min"]
_bef_days = df[df["is_weekday"] & (df["arrival_date"] < SWAP_DATE)]["arrival_date"].nunique()
_aft_days = df[df["is_weekday"] & (df["arrival_date"] >= SWAP_DATE)]["arrival_date"].nunique()
ew_bef = {t: (100*(_ew_bef > t).mean(), (_ew_bef > t).sum()/_bef_days) for t in [15, 20, 25]}
ew_aft = {t: (100*(_ew_aft > t).mean(), (_ew_aft > t).sum()/_aft_days) for t in [15, 20, 25]}


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="header-strip">
  <div class="header-tag">🚇 Independent Community Analysis · Roosevelt Island, NYC</div>
  <div class="header-title">The F/M Swap Is Hurting Roosevelt Island</div>
  <div class="header-subtitle">
    Since December 8, 2025, the MTA replaced the F train with the M on weekdays.
    Median evening rush wait times have more than doubled. This dashboard documents the impact
    using {n_obs:,} train observations across {n_weekdays} weekdays.
  </div>
</div>
""", unsafe_allow_html=True)

# ── Navigation bar ────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="nav-bar">
  <a class="active" href="#hero">The Impact</a>
  <a href="#pattern">Full Picture</a>
  <a href="#commuters">For Commuters</a>
  <a href="#mta-promise">MTA's Promise</a>
  <a href="#data">The Data</a>
  <a href="#action">Take Action</a>
  <span style="margin:0 1rem; color:{LIGHT_NAVY};">|</span>
  <a href="https://github.com/jhk9721/mta-mf-swap" target="_blank"
     style="color:{TEXT_LIGHT}; font-weight:600;">📊 GitHub</a>
</div>
""", unsafe_allow_html=True)

# Track scroll depth for engagement metrics
track_scroll_depth()

# ── Plain-language summary ────────────────────────────────────────────────────
st.markdown(f"""
<div class="plain-summary">
  <div class="ps-label">The short version</div>
  On December 8, 2025, the MTA replaced the F train with the less-frequent M train on Roosevelt Island —
  without a compensating service improvement. Median evening wait times have <strong>more than doubled</strong>,
  and the MTA's own promised fix of "~1 minute extra" has not materialized.
  All figures below are based on <strong>{n_obs:,} real train arrivals</strong> pulled from the MTA's official
  GTFS real-time feed. Scroll down for charts, or jump ahead using the links above.
</div>
""", unsafe_allow_html=True)

# ── Key metrics row ───────────────────────────────────────────────────────────
def metric_card(label, value, sub, style="alarm"):
    return f"""
    <div class="metric-card {style}">
      <div class="metric-label">{label}</div>
      <div class="metric-value {'red' if style == 'alarm' else 'orange' if style == 'warning' else ''}">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>"""

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(metric_card(
        "Evening Commute Home ↑",
        f"+{ev_pct:.0f}%",
        f"Median: {ev_nb_b:.1f} → {ev_nb_a:.1f} min northbound (4–7 PM)",
        "alarm"
    ), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card(
        "Morning Commute to Manhattan ↑",
        f"+{am_pct:.0f}%",
        f"Median: {am_sb_b:.1f} → {am_sb_a:.1f} min southbound (6–9 AM)",
        "alarm"
    ), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card(
        "Extra Wait Time Per Month",
        f"{monthly_extra:.0f} min",
        f"Based on median increase × daily round-trip × 22 working days",
        "warning"
    ), unsafe_allow_html=True)
with c4:
    st.markdown(metric_card(
        "Evening Waits Over 10 Minutes",
        f"{pct_over_10_after:.0f}%",
        f"1-in-3 northbound trains — up from {pct_over_10_before:.0f}% (1-in-5)",
        "alarm"
    ), unsafe_allow_html=True)


# ── Plotting helpers ──────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=MID_NAVY,
    font=dict(family="DM Sans, sans-serif", color=TEXT_LIGHT),
    xaxis=dict(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, tickfont=dict(size=10)),
    yaxis=dict(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, tickfont=dict(size=10), automargin=False),
    margin=dict(l=70, r=20, t=100, b=80),
)

LEGEND_BASE = dict(
    bgcolor="rgba(0,0,0,0)",
    bordercolor=LIGHT_NAVY,
    borderwidth=1,
    font=dict(size=12),
)

def add_swap_bands(fig, x_vals, swap_active_flags, row=None, col=None):
    """Shade swap-active time buckets."""
    kwargs = dict(row=row, col=col) if row else {}
    for i, active in enumerate(swap_active_flags):
        if active:
            fig.add_vrect(
                x0=i - 0.5, x1=i + 0.5,
                fillcolor=RED_AFTER, opacity=0.06,
                layer="below", line_width=0,
                **kwargs
            )

def direction_overview_fig(df: pd.DataFrame, direction: str, dir_label: str) -> go.Figure:
    wd = df[(df["day_type"] == "Weekday") & (df["direction"] == direction)]
    tick_labels, bef_med, aft_med, bef_p90, aft_p90, active = [], [], [], [], [], []
    for _, __, label in TIME_BUCKETS:
        if "Early AM" in label:
            continue  # Swap inactive overnight; long headways distort the y-axis
        sub = wd[wd["time_bucket"] == label]
        b = sub[sub["swap_period"] == "Before swap"]["headway_min"]
        a = sub[sub["swap_period"] == "After swap"]["headway_min"]
        if b.empty or a.empty: continue
        tick_labels.append(label.split(" (")[0])  # "Morning Rush", "Midday", etc.
        bef_med.append(b.median()); aft_med.append(a.median())
        bef_p90.append(b.quantile(0.90)); aft_p90.append(a.quantile(0.90))
        active.append(label in SWAP_ACTIVE_BUCKETS)

    n = len(tick_labels)
    x_pos = list(range(n))
    width = 0.35

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Before (F)",
        x=[xi - width / 2 for xi in x_pos], y=bef_med,
        width=width, marker_color=BLUE_BEFORE,
        hovertemplate="<b>Before swap</b><br>Median: %{y:.1f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="After (M)",
        x=[xi + width / 2 for xi in x_pos], y=aft_med,
        width=width, marker_color=RED_AFTER,
        hovertemplate="<b>After swap</b><br>Median: %{y:.1f} min<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="90th pct (before)",
        x=[xi - width / 2 for xi in x_pos], y=bef_p90,
        mode="markers",
        marker=dict(symbol="triangle-up", size=12, color=BLUE_BEFORE, line=dict(color="white", width=1)),
        hovertemplate="90th pct (before): %{y:.1f} min<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="90th pct (after)",
        x=[xi + width / 2 for xi in x_pos], y=aft_p90,
        mode="markers",
        marker=dict(symbol="triangle-up", size=12, color=RED_AFTER, line=dict(color="white", width=1)),
        hovertemplate="90th pct (after): %{y:.1f} min<extra></extra>",
    ))
    for i, (bv, av) in enumerate(zip(bef_med, aft_med)):
        pct = (av - bv) / bv * 100
        color = RED_AFTER if pct > 0 else GREEN_OK
        fig.add_annotation(
            x=x_pos[i], y=max(aft_p90[i], bef_p90[i]) + 2.5,
            text=f"<b>{pct:+.0f}%</b>",
            showarrow=False, font=dict(size=12, color=color),
            bgcolor="rgba(0,0,0,0)",
        )
    for i, is_active in enumerate(active):
        if is_active:
            fig.add_vrect(
                x0=x_pos[i] - 0.5, x1=x_pos[i] + 0.5,
                fillcolor=RED_AFTER, opacity=0.06,
                layer="below", line_width=0,
            )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text=f"<b>{dir_label}</b> — All Time Periods", font=dict(size=15)),
        barmode="overlay",
        yaxis_title="Wait (min)",
        height=470,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    fig.update_xaxes(tickmode="array", tickvals=x_pos, ticktext=tick_labels,
                     tickangle=-30, tickfont=dict(size=10))
    return fig


def long_wait_fig(df: pd.DataFrame, direction: str, dir_label: str) -> go.Figure:
    sub = df[df["within_swap_window"] & (df["day_type"] == "Weekday") & (df["direction"] == direction)]
    b = sub[sub["swap_period"] == "Before swap"]["headway_min"]
    a = sub[sub["swap_period"] == "After swap"]["headway_min"]
    thresholds = [5, 8, 10, 12, 15]
    bef_pcts = [100 * (b > t).mean() for t in thresholds]
    aft_pcts = [100 * (a > t).mean() for t in thresholds]
    labels = [f">{t} min" for t in thresholds]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Before (F)", x=labels, y=bef_pcts,
        marker_color=BLUE_BEFORE, offsetgroup=0,
        hovertemplate="<b>%{x}</b><br>Before: %{y:.0f}% of waits<extra></extra>",
        text=[f"{v:.0f}%" for v in bef_pcts],
        textposition="outside", textfont=dict(color=BLUE_BEFORE, size=11),
    ))
    fig.add_trace(go.Bar(
        name="After (M)", x=labels, y=aft_pcts,
        marker_color=RED_AFTER, offsetgroup=1,
        hovertemplate="<b>%{x}</b><br>After: %{y:.0f}% of waits<extra></extra>",
        text=[f"{v:.0f}%" for v in aft_pcts],
        textposition="outside", textfont=dict(color=RED_AFTER, size=11),
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text=f"<b>Long Wait Frequency — {dir_label}</b><br><sup>Weekdays, 6 AM–7 PM (swap-active hours)</sup>", font=dict(size=14)),
        barmode="group",
        yaxis_title="% of train intervals",
        yaxis_range=[0, max(max(bef_pcts), max(aft_pcts)) * 1.5],
        height=450,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    return fig


def evening_spotlight_fig(df: pd.DataFrame) -> go.Figure:
    wd = df[(df["day_type"] == "Weekday") & (df["time_bucket"] == "Evening Rush (4–7 PM)")]
    dirs = [("N", "Northbound<br>(→ Queens/Home)"), ("S", "Southbound<br>(→ Manhattan)")]
    bef, aft, bef_p, aft_p = [], [], [], []
    for code, _ in dirs:
        b = wd[(wd["direction"] == code) & (wd["swap_period"] == "Before swap")]["headway_min"]
        a = wd[(wd["direction"] == code) & (wd["swap_period"] == "After swap")]["headway_min"]
        bef.append(b.median()); aft.append(a.median())
        bef_p.append(b.quantile(0.90)); aft_p.append(a.quantile(0.90))
    labels = [d[1] for d in dirs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Before (F)", x=labels, y=bef,
        marker_color=BLUE_BEFORE, offsetgroup=0,
        text=[f"{v:.1f} min" for v in bef],
        textposition="inside", textfont=dict(color="white", size=13, family="Barlow Condensed"),
        hovertemplate="<b>%{x}</b><br>Median (before): %{y:.1f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="After (M)", x=labels, y=aft,
        marker_color=RED_AFTER, offsetgroup=1,
        text=[f"{v:.1f} min" for v in aft],
        textposition="inside", textfont=dict(color="white", size=13, family="Barlow Condensed"),
        hovertemplate="<b>%{x}</b><br>Median (after): %{y:.1f} min<extra></extra>",
    ))
    for i, (bv, av) in enumerate(zip(bef, aft)):
        pct = (av - bv) / bv * 100
        fig.add_annotation(
            x=labels[i], y=max(av, max(aft_p)) + 0.8,
            text=f"<b>+{pct:.0f}% longer</b>",
            showarrow=False,
            font=dict(size=14, color=RED_AFTER, family="Barlow Condensed"),
            bgcolor=MID_NAVY,
            bordercolor=RED_AFTER, borderwidth=1,
            borderpad=4,
        )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="<b>Evening Rush Hour (4–7 PM)</b><br><sup>Wait times have more than doubled since the F/M swap</sup>", font=dict(size=15)),
        barmode="group",
        yaxis_title="Wait (min)",
        yaxis_range=[0, max(max(aft_p), max(bef_p)) * 1.5],
        height=530,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    return fig


def weekend_fig(df: pd.DataFrame) -> go.Figure:
    we = df[df["day_type"] == "Weekend"]
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Southbound (→ Manhattan)", "Northbound (→ Queens/Home)"],
    )
    for col_idx, dir_code in enumerate(["S", "N"], start=1):
        sub = we[we["direction"] == dir_code]
        labels, bef_med, aft_med = [], [], []
        for _, __, label in TIME_BUCKETS:
            s = sub[sub["time_bucket"] == label]
            b = s[s["swap_period"] == "Before swap"]["headway_min"]
            a = s[s["swap_period"] == "After swap"]["headway_min"]
            if b.empty or a.empty: continue
            labels.append(label.split(" (")[0])
            bef_med.append(b.median()); aft_med.append(a.median())

        fig.add_trace(go.Bar(
            name="Before (F)" if col_idx == 1 else None,
            x=labels, y=bef_med, marker_color=BLUE_BEFORE,
            offsetgroup=0, showlegend=(col_idx == 1),
            hovertemplate="<b>%{x}</b><br>Median (before): %{y:.1f} min<extra></extra>",
        ), row=1, col=col_idx)
        fig.add_trace(go.Bar(
            name="After (M)" if col_idx == 1 else None,
            x=labels, y=aft_med, marker_color=RED_AFTER,
            offsetgroup=1, showlegend=(col_idx == 1),
            hovertemplate="<b>%{x}</b><br>Median (after): %{y:.1f} min<extra></extra>",
        ), row=1, col=col_idx)

        for i, (bv, av) in enumerate(zip(bef_med, aft_med)):
            pct = (av - bv) / bv * 100
            color = RED_AFTER if pct > 5 else (GREEN_OK if pct < -5 else TEXT_MUTED)
            fig.add_annotation(
                x=labels[i], y=max(av, bv) + 0.8,
                text=f"{pct:+.0f}%", showarrow=False,
                font=dict(size=10, color=color),
                row=1, col=col_idx,
            )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(
            text="<b>Weekend Headways — F Train Both Periods</b><br><sup>Swap is weekday-only. Weekend increases reflect general F-line shifts; weekday increases go far beyond this baseline.</sup>",
            font=dict(size=14),
        ),
        barmode="group",
        height=490,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    fig.update_xaxes(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, tickangle=-45, tickfont=dict(size=10))
    fig.update_yaxes(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, automargin=False)
    fig.update_yaxes(title_text="Wait (min)", col=1)
    return fig


def sensitivity_fig(df: pd.DataFrame) -> go.Figure:
    from datetime import date as date_type
    storm_date = date_type(2026, 1, 25)
    wd_swap = df[df["is_weekday"] & (df["arrival_date"] >= SWAP_DATE) & df["within_swap_window"]]

    pre            = df[df["is_weekday"] & (df["arrival_date"] < SWAP_DATE) & df["within_swap_window"]]
    post_pre_storm = wd_swap[wd_swap["arrival_date"] < storm_date]
    post_storm     = wd_swap[wd_swap["arrival_date"] >= storm_date]

    # Color scheme: Blue (F train) → Light red (M pre-storm) → Dark red (M post-storm)
    # Avoids using orange (MTA brand color) for a data point that's neither "before" nor "after"
    groups = [
        ("Pre-swap<br>(F train)", pre, BLUE_BEFORE),
        ("Post-swap<br>before storm", post_pre_storm, "#E89580"),
        ("Post-storm<br>(Jan 25+)", post_storm, RED_AFTER),
    ]
    labels  = [g[0] for g in groups]
    medians = [g[1]["headway_min"].median() for g in groups]
    colors  = [g[2] for g in groups]
    ns      = [len(g[1]) for g in groups]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=medians,
        marker_color=colors,
        text=[f"{m:.2f} min" for m in medians],
        textposition="inside",
        textfont=dict(color="white", size=13, family="Barlow Condensed"),
        hovertemplate="<b>%{x}</b><br>Median: %{y:.2f} min<br>n=%{customdata:,}<extra></extra>",
        customdata=ns,
    ))
    base = medians[0]
    for i in range(1, len(medians)):
        pct = (medians[i] - base) / base * 100
        fig.add_annotation(
            x=labels[i], y=medians[i] + 1.2,
            text=f"<b>{pct:+.0f}% vs pre-swap</b>",
            showarrow=False,
            font=dict(size=12, color=RED_AFTER),
        )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="<b>Storm Sensitivity Analysis</b><br><sup>All swap-active hours, both directions, weekdays. Storm barely moves the needle.</sup>", font=dict(size=14)),
        yaxis_title="Median headway (minutes)",
        yaxis_range=[0, max(medians) * 1.4],
        height=400,
        showlegend=False,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — THE IMPACT
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<a id="hero"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">Evening Rush Waits Have More Than Doubled</div>', unsafe_allow_html=True)

_, stat_col, _ = st.columns([1, 2, 1])
with stat_col:
    st.markdown(f"""
    <div class="big-stat">
      <div class="big-stat-number">{ev_nb_b:.1f} min &rarr; {ev_nb_a:.1f} min</div>
      <div class="big-stat-label">Median evening northbound wait · 4–7 PM · weekdays</div>
      <div class="big-stat-sub">
        The MTA promised "approximately 1 minute" longer.<br>
        Riders are waiting <strong style="color:{MTA_ORANGE};">{ev_delta:.1f} minutes more</strong> — every single evening.
      </div>
    </div>
    """, unsafe_allow_html=True)

st.plotly_chart(evening_spotlight_fig(df), use_container_width=True, config={"displayModeBar": False})

st.markdown(f"""
<div class="callout alarm">
  The MTA's internal <strong><a href="https://www.mta.info/document/186641" target="_blank"
  style="color:inherit;">Staff Summary (September 15, 2025)</a></strong>, signed by Acting Chief of
  Operations Planning Sarah Wyss, acknowledged that Roosevelt Island riders would face longer waits
  due to the M running less frequently than the F. The MTA committed to increasing peak M service so
  that <strong>"the average additional wait time will be reduced to approximately 1 minute on average."</strong>
  <br><br>
  Our analysis shows the actual median increase is <strong>{am_delta:.1f} minutes in the morning
  and {ev_delta:.1f} minutes in the evening</strong> — the MTA missed its own target by a factor of 3–4×.
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — THE FULL PICTURE
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="pattern"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">This Isn\'t Just Rush Hour — Every Period Got Worse</div>', unsafe_allow_html=True)
st.markdown(f"""
<div class="callout">
  <strong>The swap affects all daytime hours, in both directions.</strong>
  Shaded columns mark swap-active periods (weekdays 6 AM–9:30 PM). Bars show median wait times;
  triangles (▲) mark the worst 1-in-10 wait for each period.
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(direction_overview_fig(df, "S", "Southbound (→ Manhattan)"), use_container_width=True, config={"displayModeBar": False})
with col2:
    st.plotly_chart(direction_overview_fig(df, "N", "Northbound (→ Queens/Home)"), use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — FOR COMMUTERS
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="commuters"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">How Often Do You Wait 10+ Minutes?</div>', unsafe_allow_html=True)

# ── Extreme waits callout ─────────────────────────────────────────────────────
st.markdown(f"""
<div style='background:{MID_NAVY}; border-left:4px solid {MTA_ORANGE}; padding:1.5rem;
            border-radius:0 8px 8px 0; margin:1.5rem 0 0.5rem;'>
  <div style='font-size:0.8rem; font-weight:700; color:{MTA_ORANGE}; letter-spacing:0.1em;
              text-transform:uppercase; margin-bottom:0.75rem;'>
    Extreme Wait Frequency — Both Directions Combined
  </div>
  <div style='font-size:0.88rem; color:{TEXT_MUTED}; margin-bottom:1.25rem;'>
    Swap-active hours (weekdays, 6 AM–7 PM). How often do trains take 15, 20, or 25+ minutes to arrive?
  </div>
</div>
""", unsafe_allow_html=True)

col_before, col_spacer, col_after = st.columns([5, 1, 5])
with col_before:
    st.markdown(f"""
    <div style='background:rgba(58,155,255,0.12); border:2px solid {BLUE_BEFORE};
                border-radius:8px; padding:1.5rem;'>
      <div style='text-align:center; font-size:1rem; font-weight:700; color:{BLUE_BEFORE};
                  margin-bottom:1.5rem; letter-spacing:0.05em;'>F TRAIN (before Dec 8)</div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{BLUE_BEFORE};
                    font-family:"Barlow Condensed",sans-serif;'>
          15+ minutes: {ew_bef[15][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average {ew_bef[15][1]:.0f} intervals per day
        </div>
      </div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{BLUE_BEFORE};
                    font-family:"Barlow Condensed",sans-serif;'>
          20+ minutes: {ew_bef[20][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average {ew_bef[20][1]:.0f} intervals per day
        </div>
      </div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{BLUE_BEFORE};
                    font-family:"Barlow Condensed",sans-serif;'>
          25+ minutes: {ew_bef[25][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average &lt;1 interval per day
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
with col_after:
    st.markdown(f"""
    <div style='background:rgba(232,51,74,0.12); border:2px solid {RED_AFTER};
                border-radius:8px; padding:1.5rem;'>
      <div style='text-align:center; font-size:1rem; font-weight:700; color:{RED_AFTER};
                  margin-bottom:1.5rem; letter-spacing:0.05em;'>M TRAIN (after Dec 8)</div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{RED_AFTER};
                    font-family:"Barlow Condensed",sans-serif;'>
          15+ minutes: {ew_aft[15][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average {ew_aft[15][1]:.0f} intervals per day
        </div>
      </div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{RED_AFTER};
                    font-family:"Barlow Condensed",sans-serif;'>
          20+ minutes: {ew_aft[20][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average {ew_aft[20][1]:.0f} intervals per day
        </div>
      </div>
      <div style='margin:1.2rem 0;'>
        <div style='font-size:1.9rem; font-weight:800; color:{RED_AFTER};
                    font-family:"Barlow Condensed",sans-serif;'>
          25+ minutes: {ew_aft[25][0]:.1f}%
        </div>
        <div style='font-size:0.9rem; color:{TEXT_MUTED}; margin-top:0.3rem;'>
          average {ew_aft[25][1]:.0f} interval per day
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div style='font-size:0.82rem; color:{TEXT_MUTED}; font-style:italic; margin:0.75rem 0 2rem;
            text-align:center;'>
  Both directions combined, weekdays 6 AM–7 PM (swap-active hours).
  "Intervals per day" = average number of train gaps exceeding the threshold across both platforms.
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(long_wait_fig(df, "S", "Southbound (→ Manhattan)"), use_container_width=True, config={"displayModeBar": False})
with col2:
    st.plotly_chart(long_wait_fig(df, "N", "Northbound (→ Queens/Home)"), use_container_width=True, config={"displayModeBar": False})

with st.expander("ℹ️ How to read this chart"):
    st.markdown(f"""
Each bar shows what share of train gaps exceeded a given threshold during swap-active hours
(6 AM–7 PM weekdays). There is now a **1-in-3 chance** of waiting 10+ minutes for the
northbound train home — up from 1-in-5 before the swap. Every evening commute carries
meaningful risk of a long delay. Daily round-trip commuters lose roughly
**{monthly_extra:.0f} extra minutes per month** just standing on the platform.
    """)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — MTA'S BROKEN PROMISE
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="mta-promise"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">What the MTA Committed To vs. What Actually Happened</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
    <div style="background:{MID_NAVY}; border-left:4px solid {BLUE_BEFORE}; padding:1.5rem;
                border-radius:0 8px 8px 0; height:100%;">
      <div class="promise-label" style="color:{BLUE_BEFORE};"><a href="https://www.mta.info/document/186641" target="_blank" style="color:inherit; text-decoration:underline;">MTA Staff Summary · September 2025</a></div>
      <div class="promise-quote">
        "The average additional wait time will be reduced to approximately
        <strong style="color:{TEXT_LIGHT};">1 minute on average.</strong>"
      </div>
      <div class="promise-attribution">— Sarah Wyss, Acting Chief of Operations Planning</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div style="background:rgba(232,51,74,0.07); border-left:4px solid {RED_AFTER}; padding:1.5rem;
                border-radius:0 8px 8px 0; height:100%;">
      <div class="promise-label" style="color:{RED_AFTER};">Observed Impact · Dec 2025 – Feb 2026</div>
      <div class="promise-quote">
        Morning commute: <strong style="color:{TEXT_LIGHT};">+{am_delta:.1f} minutes longer</strong><br>
        Evening commute: <strong style="color:{TEXT_LIGHT};">+{ev_delta:.1f} minutes longer</strong>
      </div>
      <div class="promise-attribution">
        The MTA missed its own target by a factor of 3–4×.<br>
        Roosevelt Island has no alternative subway line.
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown('<div class="section-head">Was It the Storm?</div>', unsafe_allow_html=True)
    st.plotly_chart(sensitivity_fig(df), use_container_width=True, config={"displayModeBar": False})
with col2:
    st.markdown('<div class="section-head">FAQs</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="qa-grid" style="margin-top:1rem;">
      <div class="qa-item">
        <div class="qa-q">Was the January 25 snowstorm responsible?</div>
        <div class="qa-verdict no">No</div>
        <div class="qa-a">Wait times were already up <strong>54%</strong> before the storm hit.
        Including the storm period raises that figure to ~60%. The weather did not cause this.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Is this a general F-line problem, not the swap?</div>
        <div class="qa-verdict no">Not primarily</div>
        <div class="qa-a">Weekends are the control group — and even they show some headway increases,
        reflecting modest F-line drift. But weekday increases are <strong>far larger</strong>, because
        Roosevelt Island residents face that baseline drift <em>plus</em> the M swap.
        The swap is clearly the dominant cause.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Did the MTA deliver its promised ≤1 min improvement?</div>
        <div class="qa-verdict no">No</div>
        <div class="qa-a">Median increase is <strong>{am_delta:.1f} min</strong> (AM) and
        <strong>{ev_delta:.1f} min</strong> (PM) — 3–4× the MTA's stated target.
        See the <a href="https://www.mta.info/document/186641" target="_blank"
        style="color:{TEXT_MUTED};">Staff Summary (Sep 15, 2025)</a>.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Can this analysis be independently verified?</div>
        <div class="qa-verdict no">Open data</div>
        <div class="qa-a">Yes. All {n_obs:,} observations come from the MTA's own GTFS real-time
        feed (via subwaydata.nyc). Scripts, raw data &amp; methodology are on GitHub.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — THE DATA
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="data"></a>', unsafe_allow_html=True)

with st.expander("📊 How We Know This Is Real — Full Data & Methodology", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **Data source**
        [{n_obs:,} train observations](https://subwaydata.nyc) from subwaydata.nyc — complete MTA
        GTFS real-time feed archives. Not a periodic sample. Every train arrival at every station is captured.

        **Station identification**
        Roosevelt Island confirmed as GTFS stop IDs B06N (northbound) and B06S (southbound),
        verified against the official MTA Station & Complexes glossary (data.ny.gov, February 2026).

        **Direction convention**
        - N (B06N) = Northbound = toward Queens (evening commute home)
        - S (B06S) = Southbound = toward Manhattan (morning commute)

        **Headway calculation**
        Time between consecutive train arrivals per direction per day.
        Outliers excluded: values < 1 min or > 60 min (overnight cap: 90 min).
        All headline figures use the **median** (not mean) to reflect the typical rider experience.
        """)
    with col2:
        st.markdown(f"""
        **Analysis periods**
        - Pre-swap: October 1 – December 7, 2025 (68 weekdays, F train)
        - Post-swap: December 8, 2025 – February 15, 2026 (49 weekdays, M train)

        **Holiday weeks**
        December 22 – January 5 are included in post-swap figures. Excluding them
        makes the post-swap numbers marginally worse, not better.

        **January 25 storm**
        The winter storm accounts for ~6 percentage points of the overall increase.
        Excluding it entirely, wait times are still up 54% (vs. 60% including the storm period).
        The weather did not cause this.

        **Reproducibility**
        Complete data, scripts, and methodology are publicly available at
        [github.com/jhk9721/mta-mf-swap](https://github.com/jhk9721/mta-mf-swap).
        We welcome scrutiny and independent replication.
        """)

    st.markdown('<div class="section-head">Weekend Context — The Control Group</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      The F/M swap is <strong>weekday-only</strong>. Weekend F train data is the natural control group —
      any headway changes on weekends <strong>cannot be attributed to the swap</strong>.
      Notably, even weekends show some headway increases, suggesting the overall F line has seen modest
      service degradation. <strong>This makes the weekday situation worse, not better:</strong>
      Roosevelt Island residents face both a general F-line decline <em>and</em> the additional burden
      of the M swap on weekdays. The gap between weekday and weekend increases isolates the swap's impact.
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(weekend_fig(df), use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — TAKE ACTION
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="action"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">Roosevelt Island Deserves Better</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
    <a href="mailto:jmenin@council.nyc.gov?subject=Roosevelt%20Island%20F%2FM%20Swap%20Service%20Impact"
       onclick="
         if (typeof gtag !== 'undefined') {{
           gtag('event', 'cta_click', {{'button': 'contact_menin'}});
         }}
         if (typeof plausible !== 'undefined') {{
           plausible('CTA Click', {{props: {{button: 'contact_menin'}}}});
         }}
         return true;
       "
       style="background:{MTA_ORANGE}; display:block; padding:1.5rem 1.2rem; border-radius:8px;
              text-align:center; text-decoration:none;">
      <div style="font-size:2rem;">📧</div>
      <div style="color:white; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Contact Council Member Menin</div>
      <div style="color:rgba(255,255,255,0.75); font-size:0.78rem; margin-top:0.2rem;">jmenin@council.nyc.gov</div>
    </a>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <a href="https://github.com/jhk9721/mta-mf-swap" target="_blank"
       onclick="
         if (typeof gtag !== 'undefined') {{
           gtag('event', 'cta_click', {{'button': 'github_download'}});
         }}
         if (typeof plausible !== 'undefined') {{
           plausible('CTA Click', {{props: {{button: 'github_download'}}}});
         }}
         return true;
       "
       style="background:{MID_NAVY}; border:2px solid {MTA_ORANGE}; display:block; padding:1.5rem 1.2rem;
              border-radius:8px; text-align:center; text-decoration:none;">
      <div style="font-size:2rem;">📊</div>
      <div style="color:{TEXT_LIGHT}; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Download Full Analysis</div>
      <div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.2rem;">Data, scripts &amp; methodology on GitHub</div>
    </a>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div id="share-btn" style="background:{MID_NAVY}; border:2px solid {MTA_ORANGE}; display:block;
                padding:1.5rem 1.2rem; border-radius:8px; text-align:center; cursor:pointer;"
         onclick="
           navigator.clipboard.writeText(window.location.href).then(function() {{
             if (typeof gtag !== 'undefined') {{
               gtag('event', 'cta_click', {{'button': 'share_link'}});
             }}
             if (typeof plausible !== 'undefined') {{
               plausible('CTA Click', {{props: {{button: 'share_link'}}}});
             }}
             var btn = document.getElementById('share-btn');
             var label = btn.querySelector('.share-label');
             label.textContent = '✓ Link Copied!';
             btn.style.background = '{GREEN_OK}';
             btn.style.borderColor = '{GREEN_OK}';
             setTimeout(function() {{
               label.textContent = 'Share This Analysis';
               btn.style.background = '{MID_NAVY}';
               btn.style.borderColor = '{MTA_ORANGE}';
             }}, 2000);
           }}).catch(function(err) {{
             alert('Could not copy — please copy manually: ' + window.location.href);
           }});
         ">
      <div style="font-size:2rem;">🔗</div>
      <div class="share-label" style="color:{TEXT_LIGHT}; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Share This Analysis</div>
      <div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.2rem;">Copy link to clipboard</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div style="text-align:center; margin:2rem 0 1rem; color:{TEXT_MUTED}; font-size:0.88rem; line-height:1.6;">
  This analysis was prepared by Roosevelt Island residents using publicly available MTA data.<br>
  We welcome scrutiny — all code and data are public.
</div>
""", unsafe_allow_html=True)


# ── Privacy statement ─────────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center; margin:1rem 0; padding:0.75rem; border-top:1px solid {LIGHT_NAVY};">
  <details style="cursor:pointer; display:inline-block; text-align:left;">
    <summary style="color:{TEXT_MUTED}; font-size:0.78rem; cursor:pointer;">Privacy &amp; Analytics</summary>
    <div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.5rem; max-width:560px; line-height:1.55;">
      This site uses privacy-first analytics to understand usage patterns. We collect:
      <ul style="margin:0.4rem 0 0.4rem 1.2rem;">
        <li>Anonymous page views (no IP addresses stored)</li>
        <li>Scroll depth and section views</li>
        <li>Button clicks (email, GitHub, share)</li>
      </ul>
      We do <strong>not</strong> collect personal information, browsing history, or advertising data.
      All data is anonymized and GDPR-compliant. View the
      <a href="https://github.com/jhk9721/mta-mf-swap" style="color:{MTA_ORANGE};">open-source code</a>.
    </div>
  </details>
</div>
""", unsafe_allow_html=True)


# ── Back-to-top button (mobile) ───────────────────────────────────────────────
st.markdown(f"""
<style>
  .back-to-top {{
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: {MTA_ORANGE};
    color: white;
    border-radius: 50%;
    width: 48px;
    height: 48px;
    font-size: 22px;
    line-height: 48px;
    text-align: center;
    text-decoration: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    z-index: 1000;
    display: none;
  }}
  @media (max-width: 768px) {{
    .back-to-top {{ display: block; }}
  }}
</style>
<a href="#the-f-m-swap-is-hurting-roosevelt-island" class="back-to-top" title="Back to top">↑</a>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(f"""
<div style="border-top: 1px solid {LIGHT_NAVY}; padding: 1.2rem 0 0.5rem; text-align: center;
     font-size: 0.78rem; color: {TEXT_MUTED};">
  Prepared by Roosevelt Island Residents for Better Transit ·
  Data: subwaydata.nyc · {n_obs:,} observations · {date_min} – {date_max} ·
  <a href="https://github.com/jhk9721/mta-mf-swap" style="color:{MTA_ORANGE};">View on GitHub</a>
</div>
""", unsafe_allow_html=True)
