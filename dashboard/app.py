"""
app.py — Roosevelt Island Transit Dashboard
============================================
Run locally:  streamlit run app.py
Deploy:       Push to GitHub → connect to Render or Streamlit Community Cloud

Data:  Place roosevelt_island_headways.csv alongside this file (or in data/).
       Run scripts/3_analyze.py first if you don't have the CSV.
"""

import os
from datetime import date, timedelta
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
  .header-stamp {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {TEXT_MUTED};
    margin-top: 0.9rem;
  }}
  .header-stamp strong {{ color: {MTA_ORANGE}; }}

  /* ── Navigation bar ── */
  .nav-bar {{
    background: {MID_NAVY};
    border-bottom: 2px solid {LIGHT_NAVY};
    padding: 0.65rem 2rem;
    text-align: center;
    margin: 0 -1rem 2rem -1rem;
    position: sticky;
    top: 0;
    z-index: 999;
    overflow-x: auto;
    white-space: nowrap;
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

  /* ── Commitment scorecard ── */
  .score-tally {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 1rem 0 1.4rem;
  }}
  .score-tally-item {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-radius: 8px;
    padding: 0.7rem 1.2rem;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.5rem;
    font-weight: 800;
    color: {TEXT_LIGHT};
  }}
  .score-tally-item span {{
    display: block;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {TEXT_MUTED};
    margin-top: 0.2rem;
  }}
  .score-row {{
    background: {MID_NAVY};
    border: 1px solid {LIGHT_NAVY};
    border-left: 4px solid {LIGHT_NAVY};
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem;
    margin-bottom: 0.7rem;
  }}
  .score-row.fail    {{ border-left-color: {RED_AFTER}; }}
  .score-row.partial {{ border-left-color: {MTA_ORANGE}; }}
  .score-row.pass    {{ border-left-color: {GREEN_OK}; }}
  .score-chip {{
    display: inline-block;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    border-radius: 4px;
    padding: 0.15rem 0.55rem;
    margin-right: 0.6rem;
    color: white;
  }}
  .score-chip.fail    {{ background: {RED_AFTER}; }}
  .score-chip.partial {{ background: {MTA_ORANGE}; }}
  .score-chip.pass    {{ background: {GREEN_OK}; }}
  .score-chip.unknown {{ background: {LIGHT_NAVY}; color: {TEXT_MUTED}; }}
  .score-title {{
    font-weight: 600;
    color: {TEXT_LIGHT};
    font-size: 0.92rem;
  }}
  .score-quote {{
    font-size: 0.84rem;
    color: {TEXT_MUTED};
    font-style: italic;
    line-height: 1.5;
    margin: 0.55rem 0 0.45rem;
  }}
  .score-measure {{
    font-size: 0.84rem;
    color: {TEXT_LIGHT};
    line-height: 1.5;
  }}
  .score-measure b {{ color: {RED_AFTER}; }}
  .score-source {{
    font-size: 0.72rem;
    color: {TEXT_MUTED};
    opacity: 0.8;
    margin-top: 0.45rem;
    font-family: monospace;
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

    /* Sticky nav — tighter padding on mobile */
    .nav-bar {{ padding: 0.5rem 0.75rem; }}
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


_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@st.cache_data(ttl=3600)
def load_supplement(name: str):
    """
    Load a small CSV produced by the analysis scripts (scorecard, DiD summary).
    Returns None if the file isn't shipped, so the page degrades to its other
    sections instead of erroring out.
    """
    path = os.path.join(_DATA_DIR, name)
    return pd.read_csv(path) if os.path.exists(path) else None


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
# Added wait on a weekday round trip (one morning wait + one evening wait),
# in the MTA's wait terms, across a 22-day working month.
monthly_extra = (am_delta / 2 + ev_delta / 2) * 22

# Difference-in-differences summary (scripts/11) — loaded up front because the
# FAQ cites it before the section that plots it.
_did = load_supplement("did_summary.csv")
if _did is not None:
    did_mean       = _did["did"].mean()
    did_ctrl_mean  = _did["ctrl_delta"].mean()
    did_treat_mean = _did["treat_delta"].mean()
    did_cells_pos  = int((_did["did_ci_low"] > 0).sum())
    did_cells_over = int((_did["did_ci_low"] > 1.0).sum())
    did_n_cells    = len(_did)

# The MTA's commitment is about *wait*, and its own formula is
# average wait = headway / 2. Compare like with like: convert the headway
# change into added average wait before measuring the promise against it.
ev_wait_delta = ev_delta / 2
am_wait_delta = am_delta / 2
miss_factor   = ((ev_wait_delta + am_wait_delta) / 2) / 1.0

# ── Peak train supply ─────────────────────────────────────────────────────────
# Headways are a derived statistic; this is a raw count of trains that stopped at
# the platform. It needs no baseline argument, no outlier rule and no
# median-vs-mean discussion, which makes it the hardest figure here to contest.
# It is also the direct test of the Staff Summary's promise that "AM and PM
# peak-hour M service will be increased".
PEAK_HOURS = 6  # 6-9 AM plus 4-7 PM

def trains_per_hour(direction: str, period: str) -> float:
    """Average weekday peak arrivals per hour at Roosevelt Island.

    Divides by the number of distinct weekday dates actually present in the
    data, so missing days never inflate the rate.
    """
    sub = df[
        (df["day_type"]    == "Weekday") &
        (df["direction"]   == direction) &
        (df["swap_period"] == period) &
        (df["time_bucket"].isin(["Morning Rush (6–9 AM)", "Evening Rush (4–7 PM)"]))
    ]
    n_days = sub["arrival_date"].nunique()
    return len(sub) / n_days / PEAK_HOURS if n_days else 0.0

tph_nb_b, tph_nb_a = trains_per_hour("N", "Before swap"), trains_per_hour("N", "After swap")
tph_sb_b, tph_sb_a = trains_per_hour("S", "Before swap"), trains_per_hour("S", "After swap")
tph_nb_pct = (tph_nb_a - tph_nb_b) / tph_nb_b * 100 if tph_nb_b else 0.0
tph_sb_pct = (tph_sb_a - tph_sb_b) / tph_sb_b * 100 if tph_sb_b else 0.0
tph_worst_pct = min(tph_nb_pct, tph_sb_pct)

# Extreme wait statistics — both directions, swap-active hours, weekdays
_ew_bef = df[df["within_swap_window"] & (df["day_type"] == "Weekday") & (df["swap_period"] == "Before swap")]["headway_min"]
_ew_aft = df[df["within_swap_window"] & (df["day_type"] == "Weekday") & (df["swap_period"] == "After swap")]["headway_min"]
_bef_days = df[df["is_weekday"] & (df["arrival_date"] < SWAP_DATE)]["arrival_date"].nunique()
_aft_days = df[df["is_weekday"] & (df["arrival_date"] >= SWAP_DATE)]["arrival_date"].nunique()
ew_bef = {t: (100*(_ew_bef > t).mean(), (_ew_bef > t).sum()/_bef_days) for t in [15, 20, 25]}
ew_aft = {t: (100*(_ew_aft > t).mean(), (_ew_aft > t).sum()/_aft_days) for t in [15, 20, 25]}

# How to describe the evening-rush change in words. Derived from the data so the
# copy can't outrun the numbers as more months land.
if ev_pct >= 100:
    ev_phrase = "more than doubled"
elif ev_pct >= 85:
    ev_phrase = "nearly doubled"
elif ev_pct >= 50:
    ev_phrase = f"risen by {ev_pct:.0f}%"
else:
    ev_phrase = f"risen {ev_pct:.0f}%"

# "1-in-N chance of a 10+ minute wait" — derived, never hardcoded
one_in_before = round(100 / pct_over_10_before) if pct_over_10_before else 0
one_in_after  = round(100 / pct_over_10_after)  if pct_over_10_after  else 0

# Period labels — everything downstream reads these instead of literal dates
pre_start   = df[df["arrival_date"] < SWAP_DATE]["arrival_date"].min()
post_start  = SWAP_DATE
pre_label   = f"{pre_start:%b %-d, %Y} – {SWAP_DATE - timedelta(days=1):%b %-d, %Y}"
post_label  = f"{post_start:%b %-d, %Y} – {date_max:%b %-d, %Y}"
post_months = f"{post_start:%b %Y} – {date_max:%b %Y}"
updated_str = date.today().strftime("%B %-d, %Y")

# Weekend control (the swap is weekday-only) and the holiday-week check —
# both recomputed so the prose follows the data rather than an older vintage.
_we = df[(df["day_type"] == "Weekend") & (df["hour"] >= 6) & (df["hour"] < 19)]
_we_b = _we[_we["swap_period"] == "Before swap"]["headway_min"].median()
_we_a = _we[_we["swap_period"] == "After swap"]["headway_min"].median()
weekend_pct = (_we_a - _we_b) / _we_b * 100

_post_peak = df[df["is_weekday"] & df["within_swap_window"] & (df["arrival_date"] >= SWAP_DATE)]
_hol = pd.date_range("2025-12-22", "2026-01-05").date
post_med_all = _post_peak["headway_min"].median()
post_med_nohol = _post_peak[~_post_peak["arrival_date"].isin(_hol)]["headway_min"].median()

# Storm sensitivity — recomputed here so the prose can never drift from the chart
_storm_date  = date(2026, 1, 25)
_sw          = df[df["is_weekday"] & df["within_swap_window"]]
_sw_pre      = _sw[_sw["arrival_date"] < SWAP_DATE]["headway_min"].median()
_sw_prestorm = _sw[(_sw["arrival_date"] >= SWAP_DATE) & (_sw["arrival_date"] < _storm_date)]["headway_min"].median()
_sw_poststorm= _sw[_sw["arrival_date"] >= _storm_date]["headway_min"].median()
storm_pct_before = (_sw_prestorm - _sw_pre) / _sw_pre * 100    # degradation before the storm hit
storm_pct_after  = (_sw_poststorm - _sw_pre) / _sw_pre * 100   # degradation once the storm is included


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="header-strip">
  <div class="header-tag">🚇 Independent Community Analysis · Roosevelt Island, NYC</div>
  <div class="header-title">The F/M Swap Is Hurting Roosevelt Island</div>
  <div class="header-subtitle">
    Since December 8, 2025, the MTA replaced the F train with the M on weekdays.
    Median evening rush wait times have {ev_phrase}. This dashboard documents the impact
    using {n_obs:,} train observations across {n_weekdays} weekdays.
  </div>
  <div class="header-stamp">
    Data through <strong>{date_max:%B %-d, %Y}</strong> · dashboard updated {updated_str}
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
  <a href="#trend">Since Then</a>
  <a href="#response">MTA's Response</a>
  <a href="#scorecard">Scorecard</a>
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
  On December 8, 2025, the MTA replaced the F train with the less-frequent M train on Roosevelt Island.
  Median evening gaps between trains have <strong>{ev_phrase}</strong>. The MTA did promise extra peak M
  service to hold the added wait to "approximately 1 minute" — peak M arrivals on the shared Queens Blvd
  stations are up about 3%, nowhere near enough, and the added wait at Roosevelt Island is
  {am_wait_delta:.1f}–{ev_wait_delta:.1f} minutes.
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

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(metric_card(
        "Peak Trains Per Hour ↓",
        f"{tph_worst_pct:.0f}%",
        f"Northbound {tph_nb_b:.1f} → {tph_nb_a:.1f} · southbound {tph_sb_b:.1f} → {tph_sb_a:.1f} per hour",
        "alarm"
    ), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card(
        "Evening Commute Home ↑",
        f"+{ev_pct:.0f}%",
        f"Median: {ev_nb_b:.1f} → {ev_nb_a:.1f} min northbound (4–7 PM)",
        "alarm"
    ), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card(
        "Morning Commute to Manhattan ↑",
        f"+{am_pct:.0f}%",
        f"Median: {am_sb_b:.1f} → {am_sb_a:.1f} min southbound (6–9 AM)",
        "alarm"
    ), unsafe_allow_html=True)
with c4:
    st.markdown(metric_card(
        "Extra Wait Time Per Month",
        f"{monthly_extra:.0f} min",
        f"Added wait on a weekday round trip (AM + PM), 22 working days",
        "warning"
    ), unsafe_allow_html=True)
with c5:
    st.markdown(metric_card(
        "Evening Waits Over 10 Minutes",
        f"{pct_over_10_after:.0f}%",
        f"1-in-{one_in_after} northbound trains — up from {pct_over_10_before:.0f}% (1-in-{one_in_before})",
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
    # Angled tick labels need room, or the horizontal legend lands on top of them
    fig.update_layout(margin=dict(l=10, r=10, t=60, b=90))
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
        title=dict(text=f"<b>Evening Rush Hour (4–7 PM)</b><br><sup>Wait times have {ev_phrase} since the F/M swap</sup>", font=dict(size=15)),
        barmode="group",
        yaxis_title="Wait (min)",
        yaxis_range=[0, max(max(aft_p), max(bef_p)) * 1.5],
        height=530,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    # Two-line tick labels need the extra bottom margin to clear the legend
    fig.update_layout(margin=dict(l=10, r=10, t=70, b=80))
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
            text="<b>Weekend Headways — F Train Both Periods</b><br><sup>Swap is weekday-only, so weekends are the control group: F service here did not degrade over the same months.</sup>",
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


def did_fig(did: pd.DataFrame) -> go.Figure:
    """Treatment Δ vs. control Δ vs. swap-attributable residual, per peak cell."""
    cells, treat, ctrl, resid, lo, hi = [], [], [], [], [], []
    for (bucket, direction), grp in did.groupby(["time_bucket", "direction"], sort=False):
        cells.append(f"{direction}<br>{bucket.split(' (')[0]}")
        treat.append(grp["treat_delta"].mean())
        ctrl.append(grp["ctrl_delta"].mean())
        resid.append(grp["did"].mean())
        lo.append(grp["did"].mean() - grp["did_ci_low"].mean())
        hi.append(grp["did_ci_high"].mean() - grp["did"].mean())

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Roosevelt Island (F → M)", x=cells, y=treat, marker_color=RED_AFTER,
        hovertemplate="<b>%{x}</b><br>Roosevelt Island: %{y:+.2f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Control stations (R, 7)", x=cells, y=ctrl, marker_color=BLUE_BEFORE,
        hovertemplate="<b>%{x}</b><br>Controls: %{y:+.2f} min<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Swap-attributable (difference-in-differences)", x=cells, y=resid,
        marker_color=MTA_ORANGE,
        error_y=dict(type="data", symmetric=False, array=hi, arrayminus=lo,
                     color=TEXT_LIGHT, thickness=1.2, width=5),
        hovertemplate="<b>%{x}</b><br>DiD: %{y:+.2f} min<extra></extra>",
    ))
    fig.add_hline(
        y=1.0, line_dash="dash", line_color=TEXT_MUTED,
        annotation_text="MTA commitment: ~1 min", annotation_position="top left",
        annotation_font=dict(size=11, color=TEXT_MUTED),
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="<b>Change in Average Wait — Roosevelt Island vs. Unaffected Lines</b>"
                        "<br><sup>Controls stayed flat, so the gap is the swap, not the weather. "
                        "Bars show minutes added per trip; whiskers are 95% bootstrap CIs.</sup>",
                   font=dict(size=14)),
        barmode="group",
        yaxis_title="Change in average wait (minutes)",
        height=470,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.30, yanchor="top"),
    )
    fig.update_layout(margin=dict(l=10, r=10, t=60, b=90))
    return fig


TREND_SERIES = [
    ("Evening rush · northbound (commute home)", "Evening Rush (4–7 PM)", "N"),
    ("Morning rush · southbound (to Manhattan)", "Morning Rush (6–9 AM)", "S"),
]


@st.cache_data(ttl=3600)
def monthly_peak_medians(bucket: str, direction: str) -> pd.DataFrame:
    """Monthly median headway for one peak cell, weekdays, from Oct 2025 on.
    Months with fewer than 5 observed weekdays are dropped so a part-month
    can't read as a trend."""
    sub = df[df["is_weekday"] & (df["time_bucket"] == bucket) & (df["direction"] == direction)].copy()
    sub["month"] = pd.to_datetime(sub["arrival_date"]).values.astype("datetime64[M]")
    sub = sub[sub["month"] >= pd.Timestamp("2025-10-01")]
    g = sub.groupby("month").agg(median=("headway_min", "median"),
                                 days=("arrival_date", "nunique")).reset_index()
    return g[g["days"] >= 5]


def monthly_trend_fig(df: pd.DataFrame) -> go.Figure:
    """Month-by-month peak medians — does the post-swap picture improve over time?"""
    series = [
        (TREND_SERIES[0][0], TREND_SERIES[0][1], TREND_SERIES[0][2], RED_AFTER, ev_nb_b),
        (TREND_SERIES[1][0], TREND_SERIES[1][1], TREND_SERIES[1][2], MTA_ORANGE, am_sb_b),
    ]

    fig = go.Figure()
    for label, bucket, direction, color, baseline in series:
        g = monthly_peak_medians(bucket, direction)
        fig.add_trace(go.Scatter(
            name=label, x=g["month"], y=g["median"], mode="lines+markers",
            line=dict(color=color, width=3), marker=dict(size=8),
            hovertemplate="<b>%{x|%b %Y}</b><br>Median wait between trains: %{y:.1f} min<extra></extra>",
        ))
        fig.add_hline(y=baseline, line_dash="dot", line_color=color, opacity=0.45)

    # Plotly's autorange pads this axis far too generously; pin it to the data
    _months = monthly_peak_medians(*TREND_SERIES[0][1:3])["month"]
    fig.update_xaxes(range=[_months.min() - pd.DateOffset(days=20),
                            _months.max() + pd.DateOffset(days=20)])
    fig.add_vline(x=pd.Timestamp(SWAP_DATE), line_dash="dash", line_color=TEXT_MUTED)
    fig.add_annotation(x=pd.Timestamp(SWAP_DATE), y=1.0, yref="paper", yanchor="bottom",
                       text="F → M swap", showarrow=False,
                       font=dict(size=11, color=TEXT_MUTED))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="<b>Median Wait Between Trains, Month by Month</b>"
                        "<br><sup>Dotted lines mark the pre-swap F baseline for each commute. "
                        "Weekdays only; months with fewer than 5 observed weekdays omitted.</sup>",
                   font=dict(size=14)),
        yaxis_title="Median minutes between trains",
        yaxis_rangemode="tozero",
        height=470,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.25, yanchor="top"),
    )
    # Left margin must hold the y tick labels; automargin can't expand a pinned margin
    fig.update_layout(margin=dict(l=55, r=10, t=60, b=80))
    return fig


def train_supply_fig() -> go.Figure:
    """Peak trains per hour, before vs. after, by direction.

    Deliberately a raw count rather than a derived statistic: it tests the Staff
    Summary's promise that "AM and PM peak-hour M service will be increased"
    without needing a baseline argument, an outlier rule, or a median-vs-mean
    discussion.
    """
    groups = ["Northbound<br>(→ Queens/home)", "Southbound<br>(→ Manhattan)"]
    before = [tph_nb_b, tph_sb_b]
    after  = [tph_nb_a, tph_sb_a]
    pct    = [tph_nb_pct, tph_sb_pct]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Before (F)", x=groups, y=before,
        marker_color=BLUE_BEFORE, offsetgroup=0,
        hovertemplate="<b>%{x}</b><br>Before the swap: %{y:.1f} trains/hour<extra></extra>",
        text=[f"{v:.1f}" for v in before],
        textposition="outside", textfont=dict(color=BLUE_BEFORE, size=12),
    ))
    fig.add_trace(go.Bar(
        name="After (M)", x=groups, y=after,
        marker_color=RED_AFTER, offsetgroup=1,
        hovertemplate="<b>%{x}</b><br>After the swap: %{y:.1f} trains/hour<extra></extra>",
        text=[f"{v:.1f}" for v in after],
        textposition="outside", textfont=dict(color=RED_AFTER, size=12),
    ))
    top = max(before + after)
    for g, p in zip(groups, pct):
        fig.add_annotation(x=g, y=top * 1.22, text=f"<b>{p:+.0f}%</b>",
                           showarrow=False, font=dict(size=13, color=RED_AFTER))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(
            text="<b>Peak Trains Per Hour at Roosevelt Island</b><br>"
                 "<sup>Weekday rush hours (6–9 AM and 4–7 PM). A count of trains that stopped — "
                 "not a modelled statistic.</sup>",
            font=dict(size=14),
        ),
        barmode="group", bargap=0.52, bargroupgap=0.04,
        yaxis_title="Trains per hour",
        yaxis_range=[0, top * 1.38],
        height=420,
        legend=dict(**LEGEND_BASE, orientation="h", x=0.5, xanchor="center", y=-0.18, yanchor="top"),
    )
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
        (f"Post-storm<br>(Jan 25 – {date_max:%b %Y})", post_storm, RED_AFTER),
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
st.markdown(f'<div class="section-head">Evening Rush Waits Have {ev_phrase.title()}</div>', unsafe_allow_html=True)

_, stat_col, _ = st.columns([1, 2, 1])
with stat_col:
    st.markdown(f"""
    <div class="big-stat">
      <div class="big-stat-number">{ev_nb_b:.1f} min &rarr; {ev_nb_a:.1f} min</div>
      <div class="big-stat-label">Median gap between evening northbound trains · 4–7 PM · weekdays</div>
      <div class="big-stat-sub">
        The MTA promised about <strong>1 extra minute</strong> of waiting.<br>
        On the MTA's own arithmetic — average wait is half the gap between trains — riders are waiting
        <strong style="color:{MTA_ORANGE};">{ev_wait_delta:.1f} minutes more</strong> every evening,
        and the gap itself grew by {ev_delta:.1f} minutes.
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
  Measured the MTA's own way — average wait equals half the gap between trains — the added wait is
  <strong>{am_wait_delta:.1f} minutes in the morning and {ev_wait_delta:.1f} minutes in the evening</strong>,
  {miss_factor:.1f}× the commitment. The gap between trains itself grew by {am_delta:.1f} minutes
  (morning) and {ev_delta:.1f} minutes (evening).
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
(6 AM–7 PM weekdays). There is now a **1-in-{one_in_after} chance** of waiting 10+ minutes for the
northbound train home — up from 1-in-{one_in_before} before the swap. Every evening commute carries
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
      <div class="promise-label" style="color:{RED_AFTER};">Observed Impact · {post_months}</div>
      <div class="promise-quote">
        Added wait, morning: <strong style="color:{TEXT_LIGHT};">+{am_wait_delta:.1f} minutes</strong><br>
        Added wait, evening: <strong style="color:{TEXT_LIGHT};">+{ev_wait_delta:.1f} minutes</strong>
      </div>
      <div class="promise-attribution">
        Computed the MTA's own way: average wait = half the gap between trains.
        That is {miss_factor:.1f}× the commitment — and Roosevelt Island has no alternative subway line.
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# The same Staff Summary promised MORE peak service, not just a capped wait.
# Train counts test that promise directly, without any derived statistic.
st.markdown('<div class="section-head">The Promise Was More Trains. There Are Fewer.</div>', unsafe_allow_html=True)

col1, col2 = st.columns([3, 2])
with col1:
    st.plotly_chart(train_supply_fig(), use_container_width=True, config={"displayModeBar": False})
with col2:
    st.markdown(f"""
    <div style="background:{MID_NAVY}; border-left:4px solid {MTA_ORANGE}; padding:1.5rem;
                border-radius:0 8px 8px 0; margin-top:2.5rem;">
      <div class="promise-label" style="color:{MTA_ORANGE};">The simplest test</div>
      <div class="promise-quote" style="font-size:1rem; line-height:1.6;">
        The Staff Summary committed that <strong style="color:{TEXT_LIGHT};">"AM and PM peak-hour
        M service will be increased."</strong><br><br>
        Counting the trains that actually stopped at Roosevelt Island during rush hour,
        service fell <strong style="color:{TEXT_LIGHT};">{abs(tph_nb_pct):.0f}%</strong> northbound and
        <strong style="color:{TEXT_LIGHT};">{abs(tph_sb_pct):.0f}%</strong> southbound.
      </div>
      <div class="promise-attribution">
        This is a count of arrivals, not a modelled statistic — no baseline choice,
        no outlier rule, no median-versus-mean question. It is the same real-time feed
        the MTA publishes.
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
        <div class="qa-a">Wait times were already up <strong>{storm_pct_before:.0f}%</strong> before the
        storm hit, and the whole post-storm stretch runs {storm_pct_after:.0f}% above the pre-swap
        baseline — the degradation has now persisted for
        {(date_max.year - post_start.year) * 12 + date_max.month - post_start.month} months,
        through spring and summer. One winter storm cannot explain that.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Didn't the MTA say this was systemwide, not the swap?</div>
        <div class="qa-verdict no">The controls say otherwise</div>
        <div class="qa-a">Unaffected lines — the R at Queens Plaza and the 7 at Queensboro Plaza —
        stayed flat across the same months. Netting them out still leaves
        <strong>{did_mean:+.2f} min</strong> of added wait attributable to the swap. See
        <a href="#response" style="color:{TEXT_MUTED};">the MTA's response</a> below.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Is this a general F-line problem, not the swap?</div>
        <div class="qa-verdict no">No</div>
        <div class="qa-a">Weekends are the control group — the F still serves Roosevelt Island then, and
        weekend daytime gaps are <strong>{'down' if weekend_pct < 0 else 'up'} {abs(weekend_pct):.0f}%</strong>
        since the swap ({_we_b:.1f} → {_we_a:.1f} min). The F line did not get worse; weekday service did, and weekdays
        are when the M replaced it.</div>
      </div>
      <div class="qa-item">
        <div class="qa-q">Did the MTA deliver its promised ≤1 min improvement?</div>
        <div class="qa-verdict no">No</div>
        <div class="qa-a">Added average wait is <strong>{am_wait_delta:.1f} min</strong> (AM) and
        <strong>{ev_wait_delta:.1f} min</strong> (PM) — {miss_factor:.1f}× the MTA's stated target, using
        the MTA's own wait formula.
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
# SECTION 4b — HAS IT GOTTEN BETTER?
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="trend"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">Has It Gotten Better?</div>', unsafe_allow_html=True)

_ev_trend    = monthly_peak_medians(TREND_SERIES[0][1], TREND_SERIES[0][2])
_ev_worst    = _ev_trend[_ev_trend["month"] >= pd.Timestamp(SWAP_DATE)]["median"].max()
_ev_latest   = _ev_trend.iloc[-1]
_latest_pct  = (_ev_latest["median"] - ev_nb_b) / ev_nb_b * 100

st.markdown(f"""
<div class="callout">
  The MTA's commitment was not a one-month promise — peak M service was to be increased so the added
  wait settled at about a minute. This chart tracks every month since the swap against the pre-swap
  F-train baseline, so improvement (or its absence) is visible without taking anyone's word for it.
  <br><br>
  The evening commute peaked at a median of <strong>{_ev_worst:.1f} minutes</strong> between trains
  and stood at <strong>{_ev_latest['median']:.1f} minutes in {_ev_latest['month']:%B %Y}</strong> —
  still <strong>{_latest_pct:.0f}% above</strong> the {ev_nb_b:.1f}-minute F-train baseline. Whatever
  drift there has been since winter, the gap the MTA promised to close is still open
  {(date_max.year - post_start.year) * 12 + date_max.month - post_start.month} months on.
</div>
""", unsafe_allow_html=True)
st.plotly_chart(monthly_trend_fig(df), use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4c — THE MTA'S RESPONSE
# ═══════════════════════════════════════════════════════════════════════════════
if _did is not None:
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown('<a id="response"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-head">The MTA Responded — Here\'s What the Data Says</div>',
                unsafe_allow_html=True)

    st.markdown(f"""
    <div class="callout">
      In its <strong>April 23, 2026 response</strong>, the MTA attributed the longer waits at Roosevelt
      Island to systemwide incidents and an unusually severe winter rather than to the swap itself.
      That claim is testable. If citywide conditions were the cause, lines that were <em>not</em> swapped
      should have degraded too. We compared Roosevelt Island against two controls — the
      <strong>R at Queens Plaza</strong> (same Queens Blvd corridor, route unchanged) and the
      <strong>7 at Queensboro Plaza</strong> (a separate division entirely) — using the same peak
      windows and the MTA's own wait-time formula.
    </div>
    """, unsafe_allow_html=True)

    st.plotly_chart(did_fig(_did), use_container_width=True, config={"displayModeBar": False})

    st.markdown(f"""
    <div class="callout alarm">
      Control stations moved <strong>{did_ctrl_mean:+.2f} minutes</strong> on average — essentially flat.
      Roosevelt Island moved <strong>{did_treat_mean:+.2f} minutes</strong>. Subtracting one from the other
      leaves <strong>{did_mean:+.2f} minutes of added wait attributable to the swap itself</strong>,
      with {did_cells_pos} of {did_n_cells} peak cells statistically above zero and {did_cells_over} of
      {did_n_cells} above the promised one minute. The systemwide explanation does not survive the comparison.
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4d — COMMITMENT SCORECARD
# ═══════════════════════════════════════════════════════════════════════════════
_score = load_supplement("commitment_scorecard.csv")
if _score is not None:
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown('<a id="scorecard"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Every Written Commitment, Scored</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="callout">
      Each row quotes a commitment the MTA made in writing, states the benchmark that would satisfy it,
      and reports what the data measured. Verdicts come straight from
      <code>scripts/14_commitment_scorecard.py</code>, which reads the CSV outputs of the analysis
      scripts — the source file for every row is printed beneath it, so any verdict can be traced back
      and checked.
    </div>
    """, unsafe_allow_html=True)

    _tally = _score["verdict"].value_counts()
    _tally_html = "".join(
        f'<div class="score-tally-item">{int(_tally.get(v, 0))}<span>{label}</span></div>'
        for v, label in [("FAIL", "commitments broken"), ("PARTIAL", "partly supported"),
                         ("PASS", "commitments met"), ("UNKNOWN", "not yet measurable")]
        if int(_tally.get(v, 0)) > 0
    )
    st.markdown(f'<div class="score-tally">{_tally_html}</div>', unsafe_allow_html=True)

    def _clean_quote(text: str) -> str:
        """The scorecard CSV carries a 'Verbatim:' prefix and nested quoting on
        some rows — strip both so the page shows the commitment as written."""
        t = str(text).strip()
        for prefix in ("Verbatim:", "(Implied)"):
            if t.startswith(prefix):
                t = t[len(prefix):].strip()
        return t.strip('"').strip()

    for _, row in _score.iterrows():
        verdict = str(row["verdict"]).strip().lower()
        measured, benchmark = row.get("measured_value"), row.get("benchmark_value")
        measure_html = (
            f'Measured <b>{measured}</b> against a benchmark of {benchmark}.'
            if pd.notna(measured) and pd.notna(benchmark) else ""
        )
        st.markdown(f"""
        <div class="score-row {verdict}">
          <div>
            <span class="score-chip {verdict}">{row['verdict']}</span>
            <span class="score-title">{row['title']}</span>
          </div>
          <div class="score-quote">"{_clean_quote(row['commitment_text'])}"
            <span style="font-style:normal;">— {row['commitment_source']}</span></div>
          <div class="score-measure">{measure_html} {_clean_quote(row['benchmark_text'])}</div>
          <div class="score-source">{row['evidence_source']}</div>
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
        verified against the official
        [MTA Subway Stations and Complexes](https://data.ny.gov/Transportation/MTA-Subway-Stations-and-Complexes/5f5g-n3cz/about_data)
        glossary on data.ny.gov (re-checked July 2026).

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
        - Pre-swap (F train): {pre_label} — {_bef_days} weekdays
        - Post-swap (M train): {post_label} — {_aft_days} weekdays

        The pre-swap baseline is **every F-train weekday in the archive before December 8, 2025**.
        That deliberately includes the January–April 2025 data we pulled for the seasonality test,
        so the baseline spans two seasons rather than one. Restricting it to the tighter
        October 1 – December 7, 2025 window produces *larger* increases (about +100% evening and
        +71% morning), so the figures published here are the conservative ones.

        **Holiday weeks**
        December 22 – January 5 are included in post-swap figures. Excluding them moves the post-swap
        peak median from {post_med_all:.2f} to {post_med_nohol:.2f} minutes — immaterial either way.

        **January 25, 2026 storm**
        Waits were already {storm_pct_before:.0f}% above baseline before the storm; including it and
        everything since leaves the figure at {storm_pct_after:.0f}%. With the post-swap record now
        running through {date_max:%B %Y}, weather is not a plausible explanation.

        **Reproducibility**
        Complete data, scripts, and methodology are publicly available at
        [github.com/jhk9721/mta-mf-swap](https://github.com/jhk9721/mta-mf-swap).
        We welcome scrutiny and independent replication.
        """)

    st.markdown('<div class="section-head">Weekend Context — The Control Group</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="callout">
      The F/M swap is <strong>weekday-only</strong>, so weekend F service is the natural control:
      any change there <strong>cannot be attributed to the swap</strong>. Across daytime hours the median
      weekend gap between trains went from <strong>{_we_b:.1f} to {_we_a:.1f} minutes
      ({weekend_pct:+.0f}%)</strong> — the F serving Roosevelt Island on weekends did not deteriorate over
      these months. That is precisely why the weekday numbers cannot be waved away as general F-line
      decline: the degradation shows up on exactly the days, and in exactly the hours, that the M
      replaced the F.
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(weekend_fig(df), use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — TAKE ACTION
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown('<a id="action"></a>', unsafe_allow_html=True)
st.markdown('<div class="section-head">Roosevelt Island Deserves Better</div>', unsafe_allow_html=True)

st.markdown(f"""
<div style="display:flex; gap:1rem; margin-bottom:2rem; flex-wrap:wrap;">
  <div id="contact-btn" style="flex:1; min-width:200px; background:{MTA_ORANGE}; padding:1.5rem 1.2rem;
       border-radius:8px; text-align:center; cursor:pointer;"
       onclick="window.location.href='mailto:jmenin@council.nyc.gov?subject=Roosevelt%20Island%20F%2FM%20Swap%20Service%20Impact';">
    <div style="font-size:2rem;">📧</div>
    <div style="color:white; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Contact Council Member Menin</div>
    <div style="color:rgba(255,255,255,0.75); font-size:0.78rem; margin-top:0.2rem;">jmenin@council.nyc.gov</div>
  </div>
  <div id="download-btn" style="flex:1; min-width:200px; background:{MID_NAVY}; border:2px solid {MTA_ORANGE};
       padding:1.5rem 1.2rem; border-radius:8px; text-align:center; cursor:pointer;"
       onclick="window.open('https://github.com/jhk9721/mta-mf-swap','_blank');">
    <div style="font-size:2rem;">📊</div>
    <div style="color:{TEXT_LIGHT}; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Download Full Analysis</div>
    <div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.2rem;">Data, scripts &amp; methodology on GitHub</div>
  </div>
  <div id="share-btn" style="flex:1; min-width:200px; background:{MID_NAVY}; border:2px solid {MTA_ORANGE};
       padding:1.5rem 1.2rem; border-radius:8px; text-align:center; cursor:pointer;"
       onclick="navigator.clipboard.writeText(window.location.href).then(function(){{var b=document.getElementById('share-btn');var l=b.querySelector('.share-label');l.textContent='✓ Link Copied!';b.style.background='{GREEN_OK}';b.style.borderColor='{GREEN_OK}';setTimeout(function(){{l.textContent='Share This Analysis';b.style.background='{MID_NAVY}';b.style.borderColor='{MTA_ORANGE}';}},2000);}}).catch(function(){{alert('Could not copy — please copy manually: '+window.location.href);}});">
    <div style="font-size:2rem;">🔗</div>
    <div class="share-label" style="color:{TEXT_LIGHT}; font-weight:700; margin-top:0.5rem; font-size:0.95rem;">Share This Analysis</div>
    <div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.2rem;">Copy link to clipboard</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="callout">
  <strong>Where this has already gone.</strong> The findings on this page have been filed with elected
  officials and the MTA, and the record is public:
  <ul style="margin:0.6rem 0 0 1.1rem; line-height:1.7;">
    <li>Community Board 8 resolution calling for improved Roosevelt Island subway frequency</li>
    <li>Joint letter to MTA Board Chair Janno Lieber</li>
    <li>Briefing packets for Council Member Julie Menin, State Senator Liz Krueger, and
        Assembly Member Rebecca Seawright</li>
    <li>The MTA's written response of <strong>April 23, 2026</strong> — answered with data in
        <a href="#response" style="color:{MTA_ORANGE};">the section above</a></li>
  </ul>
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
