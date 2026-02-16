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

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Roosevelt Island Transit — F/M Swap Analysis",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme constants ───────────────────────────────────────────────────────────
MTA_ORANGE  = "#FF6319"
DARK_NAVY   = "#0D1B2A"
MID_NAVY    = "#1B2E44"
LIGHT_NAVY  = "#243B55"
BLUE_BEFORE = "#4C8BE0"
RED_AFTER   = "#E05C4C"
TEXT_LIGHT  = "#F0F4F8"
TEXT_MUTED  = "#8CA0B3"
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

  /* Main header strip */
  .header-strip {{
    background: linear-gradient(135deg, {DARK_NAVY} 0%, {MID_NAVY} 100%);
    border-bottom: 3px solid {MTA_ORANGE};
    padding: 2rem 2.5rem 1.5rem;
    margin: -1rem -1rem 2rem -1rem;
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
    color: {TEXT_MUTED};
    margin-top: 0.5rem;
    max-width: 680px;
  }}

  /* Metric cards */
  .metric-card {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    border-left: 4px solid {MTA_ORANGE};
  }}
  .metric-card.alarm {{
    border-left-color: {RED_AFTER};
  }}
  .metric-card.ok {{
    border-left-color: {GREEN_OK};
  }}
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
  .metric-value.red {{ color: {RED_AFTER}; }}
  .metric-value.orange {{ color: {MTA_ORANGE}; }}
  .metric-value.green {{ color: {GREEN_OK}; }}
  .metric-sub {{
    font-size: 0.78rem;
    color: {TEXT_MUTED};
    margin-top: 0.3rem;
  }}

  /* Section headers */
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

  /* Callout box */
  .callout {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-left: 4px solid {MTA_ORANGE};
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.4rem;
    margin: 1rem 0;
    font-size: 0.9rem;
    color: {TEXT_MUTED};
  }}
  .callout strong {{ color: {TEXT_LIGHT}; }}

  /* Hide Streamlit chrome */
  #MainMenu, footer, header {{ visibility: hidden; }}
  .stTabs [data-baseweb="tab-list"] {{
    background-color: {MID_NAVY};
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
  }}
  .stTabs [data-baseweb="tab"] {{
    border-radius: 6px;
    color: {TEXT_MUTED};
    font-weight: 500;
    padding: 8px 18px;
  }}
  .stTabs [aria-selected="true"] {{
    background-color: {MTA_ORANGE} !important;
    color: white !important;
    font-weight: 600;
  }}
  div[data-testid="stVerticalBlock"] > div {{
    padding-top: 0;
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


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="header-strip">
  <div class="header-tag">🚇 Independent Community Analysis · Roosevelt Island, NYC</div>
  <div class="header-title">The F/M Swap Is Hurting Roosevelt Island</div>
  <div class="header-subtitle">
    Since December 8, 2025, the MTA replaced the F train with the M on weekdays.
    Evening rush wait times have more than doubled. This dashboard documents the impact
    using {n_obs:,} train observations across {n_weekdays} weekdays.
  </div>
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

ev_nb_b = get_median(df, day_type="Weekday", bucket="Evening Rush (4–7 PM)", direction="N", period="Before swap")
ev_nb_a = get_median(df, day_type="Weekday", bucket="Evening Rush (4–7 PM)", direction="N", period="After swap")
am_sb_b = get_median(df, day_type="Weekday", bucket="Morning Rush (6–9 AM)", direction="S", period="Before swap")
am_sb_a = get_median(df, day_type="Weekday", bucket="Morning Rush (6–9 AM)", direction="S", period="After swap")
pct_over_10_before = get_pct_over(df, 10.0, direction="N", period="Before swap")
pct_over_10_after  = get_pct_over(df, 10.0, direction="N", period="After swap")

ev_pct  = (ev_nb_a - ev_nb_b) / ev_nb_b * 100
am_pct  = (am_sb_a - am_sb_b) / am_sb_b * 100
monthly_extra = (am_sb_a - am_sb_b) * 2 * 22

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(metric_card(
        "Evening Commute Home ↑",
        f"+{ev_pct:.0f}%",
        f"{ev_nb_b:.1f} → {ev_nb_a:.1f} min northbound (4–7 PM)",
        "alarm"
    ), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card(
        "Morning Commute to Manhattan ↑",
        f"+{am_pct:.0f}%",
        f"{am_sb_b:.1f} → {am_sb_a:.1f} min southbound (6–9 AM)",
        "alarm"
    ), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card(
        "Extra Wait Time Per Month",
        f"{monthly_extra:.0f} min",
        f"Based on daily round-trip, 22 working days",
        "warning"
    ), unsafe_allow_html=True)
with c4:
    st.markdown(metric_card(
        "Waits > 10 Min (Evening, NB)",
        f"{pct_over_10_after:.0f}%",
        f"Up from {pct_over_10_before:.0f}% — nearly doubled",
        "alarm"
    ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ── Plotting helpers ──────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=MID_NAVY,
    font=dict(family="DM Sans, sans-serif", color=TEXT_LIGHT),
    xaxis=dict(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, tickfont=dict(size=11)),
    yaxis=dict(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, tickfont=dict(size=11)),
    margin=dict(l=10, r=10, t=50, b=10),
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
        tick_labels.append(label.replace(" (", "<br>("))
        bef_med.append(b.median()); aft_med.append(a.median())
        bef_p90.append(b.quantile(0.90)); aft_p90.append(a.quantile(0.90))
        active.append(label in SWAP_ACTIVE_BUCKETS)

    # Use numeric x-axis so scatter markers can be offset to sit over their bar
    n = len(tick_labels)
    x_pos = list(range(n))
    width = 0.35  # half-gap between before/after bars

    fig = go.Figure()

    # Before bars — centred at x - width/2
    fig.add_trace(go.Bar(
        name="F Train (before Dec 8)",
        x=[xi - width / 2 for xi in x_pos], y=bef_med,
        width=width, marker_color=BLUE_BEFORE,
        hovertemplate="<b>Before swap</b><br>Median: %{y:.1f} min<extra></extra>",
    ))
    # After bars — centred at x + width/2
    fig.add_trace(go.Bar(
        name="M Train (after Dec 8)",
        x=[xi + width / 2 for xi in x_pos], y=aft_med,
        width=width, marker_color=RED_AFTER,
        hovertemplate="<b>After swap</b><br>Median: %{y:.1f} min<extra></extra>",
    ))

    # 90th percentile markers — offset to match their bar
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

    # Percentage change annotations — centred over each pair
    for i, (bv, av) in enumerate(zip(bef_med, aft_med)):
        pct = (av - bv) / bv * 100
        color = RED_AFTER if pct > 0 else GREEN_OK
        fig.add_annotation(
            x=x_pos[i], y=max(aft_p90[i], bef_p90[i]) + 1.2,
            text=f"<b>{pct:+.0f}%</b>",
            showarrow=False, font=dict(size=12, color=color),
            bgcolor="rgba(0,0,0,0)",
        )

    # Swap-active shading using numeric x positions
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
        barmode="overlay",  # bars are already manually offset; overlay prevents double-grouping
        yaxis_title="Median minutes between trains",
        height=420,
        legend=dict(**LEGEND_BASE, orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    # Set tick labels separately to avoid conflict with PLOTLY_LAYOUT's xaxis key
    fig.update_xaxes(
        tickmode="array",
        tickvals=x_pos,
        ticktext=tick_labels,
    )
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
        name="F Train (before)", x=labels, y=bef_pcts,
        marker_color=BLUE_BEFORE, offsetgroup=0,
        hovertemplate="<b>%{x}</b><br>Before: %{y:.0f}% of waits<extra></extra>",
        text=[f"{v:.0f}%" for v in bef_pcts],
        textposition="outside", textfont=dict(color=BLUE_BEFORE, size=11),
    ))
    fig.add_trace(go.Bar(
        name="M Train (after)", x=labels, y=aft_pcts,
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
        yaxis_range=[0, max(max(bef_pcts), max(aft_pcts)) * 1.35],
        height=400,
        legend=dict(**LEGEND_BASE, orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
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
        name="F Train (before Dec 8)", x=labels, y=bef,
        marker_color=BLUE_BEFORE, offsetgroup=0,
        text=[f"{v:.1f} min" for v in bef],
        textposition="inside", textfont=dict(color="white", size=13, family="Barlow Condensed"),
        hovertemplate="<b>%{x}</b><br>Before: %{y:.1f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="M Train (after Dec 8)", x=labels, y=aft,
        marker_color=RED_AFTER, offsetgroup=1,
        text=[f"{v:.1f} min" for v in aft],
        textposition="inside", textfont=dict(color="white", size=13, family="Barlow Condensed"),
        hovertemplate="<b>%{x}</b><br>After: %{y:.1f} min<extra></extra>",
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
        yaxis_title="Median minutes between trains",
        height=480,
        legend=dict(**LEGEND_BASE, orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
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
            name="F before Dec 8" if col_idx == 1 else None,
            x=labels, y=bef_med, marker_color=BLUE_BEFORE,
            offsetgroup=0, showlegend=(col_idx == 1),
            hovertemplate="<b>%{x}</b><br>Before: %{y:.1f} min<extra></extra>",
        ), row=1, col=col_idx)
        fig.add_trace(go.Bar(
            name="F after Dec 8" if col_idx == 1 else None,
            x=labels, y=aft_med, marker_color=RED_AFTER,
            offsetgroup=1, showlegend=(col_idx == 1),
            hovertemplate="<b>%{x}</b><br>After: %{y:.1f} min<extra></extra>",
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
            text="<b>Weekend Headways — F Train Both Periods</b><br><sup>Swap is weekday-only. Changes here suggest systemwide F service shifts independent of the swap.</sup>",
            font=dict(size=14),
        ),
        barmode="group",
        height=440,
        legend=dict(**LEGEND_BASE, orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
    )
    fig.update_xaxes(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY)
    fig.update_yaxes(gridcolor=LIGHT_NAVY, linecolor=LIGHT_NAVY, title_text="Median minutes between trains", col=1)
    return fig


def sensitivity_fig(df: pd.DataFrame) -> go.Figure:
    from datetime import date as date_type
    storm_date = date_type(2026, 1, 25)
    wd_swap = df[df["is_weekday"] & (df["arrival_date"] >= SWAP_DATE) & df["within_swap_window"]]

    pre     = df[df["is_weekday"] & (df["arrival_date"] < SWAP_DATE) & df["within_swap_window"]]
    post_pre_storm = wd_swap[wd_swap["arrival_date"] < storm_date]
    post_storm     = wd_swap[wd_swap["arrival_date"] >= storm_date]

    groups = [
        ("Pre-swap<br>(F train)", pre, BLUE_BEFORE),
        ("Post-swap<br>before storm", post_pre_storm, MTA_ORANGE),
        ("Post-storm<br>(Jan 25+)", post_storm, RED_AFTER),
    ]
    labels = [g[0] for g in groups]
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
    # Annotate % change
    base = medians[0]
    for i in range(1, len(medians)):
        pct = (medians[i] - base) / base * 100
        fig.add_annotation(
            x=labels[i], y=medians[i] + 0.3,
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


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_overview, tab_morning, tab_evening, tab_waits, tab_weekend, tab_methodology = st.tabs([
    "📊 Overview",
    "🌅 Morning Commute",
    "🌆 Evening Commute",
    "⏱ Long Waits",
    "📅 Weekends",
    "🔬 Methodology",
])


# ── Tab: Overview ─────────────────────────────────────────────────────────────
with tab_overview:
    st.markdown('<div class="section-head">The Headline Finding</div>', unsafe_allow_html=True)
    st.plotly_chart(evening_spotlight_fig(df), use_container_width=True)

    st.markdown('<div class="section-head">The MTA\'s Own Admission</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      The MTA's internal <strong>Staff Summary (September 15, 2025)</strong>, signed by Acting Chief of
      Operations Planning Sarah Wyss, acknowledged that Roosevelt Island riders would face longer waits
      due to the M running less frequently than the F. The MTA committed to increasing peak M service so
      that <strong>"the average additional wait time will be reduced to approximately 1 minute on average."</strong>
      <br><br>
      Our analysis shows the actual increase is <strong>3.2 minutes in the morning and 4.2 minutes in
      the evening</strong> — the MTA missed its own target by a factor of 3–4×.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-head">Storm Sensitivity</div>', unsafe_allow_html=True)
        st.plotly_chart(sensitivity_fig(df), use_container_width=True)
    with col2:
        st.markdown('<div class="section-head">About This Analysis</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <br>
        <div class="callout">
          <strong>Data:</strong> {n_obs:,} train observations from
          <a href="https://subwaydata.nyc" style="color:{MTA_ORANGE}">subwaydata.nyc</a> —
          complete MTA GTFS real-time feed archives. Not a periodic sample.<br><br>
          <strong>Station:</strong> Roosevelt Island (GTFS stop IDs: B06N/B06S), verified against
          the official MTA Station & Complexes glossary on data.ny.gov.<br><br>
          <strong>Period:</strong> Oct 1 – Dec 7, 2025 (pre-swap) vs.
          Dec 8, 2025 – Feb 15, 2026 (post-swap). {n_weekdays} weekdays total.<br><br>
          <strong>Full methodology and data</strong> available on
          <a href="https://github.com/[GITHUB-REPO-LINK]" style="color:{MTA_ORANGE}">GitHub</a>.
        </div>
        """, unsafe_allow_html=True)


# ── Tab: Morning commute ──────────────────────────────────────────────────────
with tab_morning:
    st.markdown('<div class="section-head">Southbound (→ Manhattan) — All Weekday Periods</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      <strong>Direction note:</strong> Roosevelt Island is on the 63rd Street line.
      "Southbound" means toward Manhattan — the direction that matters for the morning commute.
      The swap is active weekdays 6 AM–9:30 PM (shaded columns).
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(
        direction_overview_fig(df, "S", "Southbound (→ Manhattan)"),
        use_container_width=True
    )


# ── Tab: Evening commute ──────────────────────────────────────────────────────
with tab_evening:
    st.markdown('<div class="section-head">Northbound (→ Queens/Home) — All Weekday Periods</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      <strong>Direction note:</strong> "Northbound" means toward Queens — the direction that matters
      for the evening commute home. The +111% evening rush finding is the strongest data point
      in this analysis.
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(
        direction_overview_fig(df, "N", "Northbound (→ Queens/Home)"),
        use_container_width=True
    )


# ── Tab: Long waits ───────────────────────────────────────────────────────────
with tab_waits:
    st.markdown('<div class="section-head">How Often Do Riders Face a Long Wait?</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            long_wait_fig(df, "S", "Southbound (→ Manhattan)"),
            use_container_width=True
        )
    with col2:
        st.plotly_chart(
            long_wait_fig(df, "N", "Northbound (→ Queens/Home)"),
            use_container_width=True
        )
    st.markdown(f"""
    <div class="callout">
      <strong>Reading this chart:</strong> Each bar shows the percentage of train intervals
      that exceeded a given wait time threshold, during swap-active hours (6 AM–7 PM weekdays).
      A 1-in-3 chance of waiting more than 10 minutes for the northbound train
      (up from 1-in-5) means every evening commute carries meaningful risk of a long delay.
    </div>
    """, unsafe_allow_html=True)


# ── Tab: Weekends ─────────────────────────────────────────────────────────────
with tab_weekend:
    st.markdown('<div class="section-head">Weekend F Train — Systemwide Signal</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      The F/M swap is <strong>weekday-only</strong>. The F train serves Roosevelt Island on weekends
      in both periods. Any headway increases on weekends <strong>cannot be attributed to the swap</strong>
      — they suggest the F line has experienced some independent service drift since December.
      This actually strengthens the weekday case: it isolates the swap's contribution and shows
      Roosevelt Island residents are being affected on two fronts.
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(weekend_fig(df), use_container_width=True)


# ── Tab: Methodology ─────────────────────────────────────────────────────────
with tab_methodology:
    st.markdown('<div class="section-head">Methodology & Data Sources</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **Data source**
        [subwaydata.nyc](https://subwaydata.nyc) archives the complete MTA GTFS real-time feed
        daily — not a periodic sample. Every train arrival at every station is captured.

        **Station identification**
        Roosevelt Island confirmed as GTFS stop IDs B06N (northbound) and B06S (southbound),
        verified against the official MTA Station & Complexes glossary (data.ny.gov, February 2026).

        **Direction convention**
        - N (B06N) = Northbound = toward Queens (evening commute home)
        - S (B06S) = Southbound = toward Manhattan (morning commute)

        **Headway calculation**
        Time between consecutive train arrivals per direction per day.
        Outliers excluded: values < 1 min or > 60 min (overnight cap: 90 min).
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
        [github.com/[GITHUB-REPO-LINK]](https://github.com/[GITHUB-REPO-LINK]).
        We welcome scrutiny and independent replication.
        """)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(f"""
<div style="border-top: 1px solid {LIGHT_NAVY}; padding: 1.2rem 0 0.5rem; text-align: center;
     font-size: 0.78rem; color: {TEXT_MUTED};">
  Prepared by Roosevelt Island Residents for Better Transit ·
  Data: subwaydata.nyc · {n_obs:,} observations · {date_min} – {date_max} ·
  <a href="https://github.com/[GITHUB-REPO-LINK]" style="color:{MTA_ORANGE};">View on GitHub</a>
</div>
""", unsafe_allow_html=True)
