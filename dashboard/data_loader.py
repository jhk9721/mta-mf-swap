"""
data_loader.py — Roosevelt Island Transit Dashboard
=====================================================
Data access layer. All data loading goes through load_headways().

TO SCALE TO MORE STATIONS LATER:
  1. Add a station config dict at the top of this file
  2. Pass station_id to load_headways()
  3. Swap source="csv" for source="supabase" and add credentials to .env

Currently supports: Roosevelt Island (B06N / B06S)
"""

from __future__ import annotations
import os
from datetime import date
import pandas as pd

# ── Station registry ──────────────────────────────────────────────────────────
# Add entries here as you expand to new stations
STATIONS = {
    "roosevelt_island": {
        "name": "Roosevelt Island",
        "stop_ids": ["B06N", "B06S"],
        "line": "F/M",
        "borough": "Manhattan",
        "swap_date": date(2025, 12, 8),
        "swap_description": "M train replaced F train weekdays 6 AM – 9:30 PM",
        "note": "Single-station neighborhood with no alternative subway line.",
    }
}

SWAP_DATE = date(2025, 12, 8)

TIME_BUCKETS = [
    ( 0,  6, "Early AM (12–6 AM)"),
    ( 6,  9, "Morning Rush (6–9 AM)"),
    ( 9, 16, "Midday (9 AM–4 PM)"),
    (16, 19, "Evening Rush (4–7 PM)"),
    (19, 24, "Night (7 PM–midnight)"),
]
SWAP_ACTIVE_BUCKETS = {"Morning Rush (6–9 AM)", "Midday (9 AM–4 PM)", "Evening Rush (4–7 PM)"}


def load_headways(source: str = "csv", csv_path: str | None = None) -> pd.DataFrame:
    """
    Load and prepare headway data.

    Parameters
    ----------
    source : "csv" | "supabase"
        Where to load data from. Switch to "supabase" when scaling up.
    csv_path : str, optional
        Path to CSV file when source="csv". Defaults to data/ directory.

    Returns
    -------
    pd.DataFrame with columns:
        arrival_date, hour, direction, is_weekday, headway_min,
        swap_period, day_type, time_bucket, within_swap_window
    """
    if source == "csv":
        return _load_from_csv(csv_path)
    elif source == "supabase":
        return _load_from_supabase()
    else:
        raise ValueError(f"Unknown source: {source!r}. Use 'csv' or 'supabase'.")


def _load_from_csv(path: str | None) -> pd.DataFrame:
    if path is None:
        # Look in same directory as this file, then data/ subdirectory
        candidates = [
            os.path.join(os.path.dirname(__file__), "roosevelt_island_headways.csv"),
            os.path.join(os.path.dirname(__file__), "data", "roosevelt_island_headways.csv"),
        ]
        for p in candidates:
            if os.path.exists(p):
                path = p
                break
        if path is None:
            raise FileNotFoundError(
                "Cannot find roosevelt_island_headways.csv. "
                "Place it in the same directory as app.py or in a data/ subfolder."
            )
    return _prepare(pd.read_csv(path))


def _load_from_supabase() -> pd.DataFrame:
    """
    Placeholder for Supabase integration.
    Install: pip install supabase
    Add SUPABASE_URL and SUPABASE_KEY to .env / Streamlit secrets.

    Example schema (SQL):
        CREATE TABLE headways (
            arrival_date  DATE,
            hour          INT,
            direction     TEXT,   -- 'N' or 'S'
            is_weekday    BOOL,
            headway_min   FLOAT,
            station_id    TEXT    -- 'B06N' or 'B06S' (add more stations here)
        );
    """
    raise NotImplementedError(
        "Supabase integration not yet configured. "
        "See data_loader.py _load_from_supabase() for setup instructions."
    )


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["arrival_date"] = pd.to_datetime(df["arrival_date"]).dt.date
    df["is_weekday"]   = df["is_weekday"].astype(bool)

    # Clip artifacts
    early_am = df["hour"] < 6
    df = df[((early_am) & (df["headway_min"] <= 90)) |
            ((~early_am) & (df["headway_min"] <= 60))]
    df = df[df["headway_min"] >= 1]

    # Derived columns
    df["swap_period"] = df["arrival_date"].apply(
        lambda d: "After swap" if d >= SWAP_DATE else "Before swap"
    )
    df["day_type"] = df["is_weekday"].map({True: "Weekday", False: "Weekend"})
    df["time_bucket"] = df["hour"].apply(_assign_bucket)
    df["within_swap_window"] = (
        df["is_weekday"] & df["time_bucket"].isin(SWAP_ACTIVE_BUCKETS)
    )

    return df.reset_index(drop=True)


def _assign_bucket(hour: int) -> str:
    for start, end, label in TIME_BUCKETS:
        if start <= hour < end:
            return label
    return "Unknown"


# ── Convenience query helpers ─────────────────────────────────────────────────

def get_median(df: pd.DataFrame, *, day_type: str, bucket: str,
               direction: str, period: str) -> float | None:
    sub = df[
        (df["day_type"]    == day_type) &
        (df["time_bucket"] == bucket) &
        (df["direction"]   == direction) &
        (df["swap_period"] == period)
    ]["headway_min"]
    return float(sub.median()) if not sub.empty else None


def get_pct_over(df: pd.DataFrame, threshold: float, *, direction: str,
                 period: str, day_type: str = "Weekday") -> float | None:
    sub = df[
        df["within_swap_window"] &
        (df["day_type"]    == day_type) &
        (df["direction"]   == direction) &
        (df["swap_period"] == period)
    ]["headway_min"]
    return float(100 * (sub > threshold).mean()) if not sub.empty else None
