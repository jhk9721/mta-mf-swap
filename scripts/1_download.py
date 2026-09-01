"""
SCRIPT 1: DOWNLOAD
==================
Downloads every day of CSV data from subwaydata.nyc across the full study
window: January 1, 2025 through today. That covers

  - Jan-Sep 2025   year-ago F train baseline (seasonality controls)
  - Oct-Nov 2025   immediate pre-swap baseline
  - Dec 2025       the swap took effect Dec 8 (split month)
  - Jan 2026 on    post-swap period, through the most recent published day

The end of the range is today's date, computed at run time — re-running the
script later picks up whatever days have been published since.

HOW TO RUN:
  1. Make sure you have Python 3 installed.
  2. Install the requests library if you haven't:
         pip install requests
  3. Run this script from your terminal:
         python3 1_download.py

Files land in the "raw_data" folder at the project root, regardless of which
directory you run the script from. Files already on disk are skipped, so
re-runs are safe and only fetch what is missing.

subwaydata.nyc publishes with a lag of a day or two, so the most recent dates
normally return 404 and are reported as "not yet available" — that is expected,
not an error. Re-run in a few days to fill them in.

Each daily file is roughly 0.8-1.5 MB compressed, so the full 20-month range
is about 500 MB. With the built-in rate limit, a complete first run takes
around 30-45 minutes; topping up an existing corpus is much quicker.
"""

import requests
import os
import time
from datetime import date, timedelta

# ── Configuration ─────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "raw_data")

# Date range to download — the full study window, inclusive of both ends.
# END_DATE is resolved at run time, so "today" always means today.
START_DATE = date(2025, 1, 1)
END_DATE   = date.today()

BASE_URL = "https://subwaydata.nyc/data"

# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_months(start: date, end: date):
    """
    Walk the range month by month so progress stays readable.

    Yields (year, month, dates) where `dates` is the list of days of that
    month falling inside [start, end] — the first and last months are
    clipped to the range bounds.
    """
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        nxt = (date(cursor.year + 1, 1, 1) if cursor.month == 12
               else date(cursor.year, cursor.month + 1, 1))
        days = []
        d = max(cursor, start)
        while d < nxt and d <= end:
            days.append(d)
            d += timedelta(days=1)
        if days:
            yield cursor.year, cursor.month, days
        cursor = nxt


def download_file(d: date, output_dir: str) -> str:
    """
    Download the CSV tar.xz for a single date.
    Returns:
      "ok"      — newly downloaded
      "skipped" — file already existed on disk
      "missing" — server returned 404 (date not yet available)
      "failed"  — network error or unexpected HTTP status
    """
    filename = f"subwaydatanyc_{d.strftime('%Y-%m-%d')}_csv.tar.xz"
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        print(f"  [SKIP] {filename} already exists.")
        return "skipped"

    url = f"{BASE_URL}/{filename}"
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024
            print(f"  [OK]   {filename}  ({size_kb:.0f} KB)")
            return "ok"
        elif response.status_code == 404:
            print(f"  [MISS] {filename} not found (404) — skipping.")
            return "missing"
        else:
            print(f"  [ERR]  {filename} HTTP {response.status_code}")
            return "failed"
    except requests.RequestException as e:
        print(f"  [ERR]  {filename} failed: {e}")
        return "failed"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Saving files to: {os.path.abspath(OUTPUT_DIR)}")
    print(f"Date range:      {START_DATE} to {END_DATE} "
          f"({(END_DATE - START_DATE).days + 1} days)\n")

    downloaded, skipped, missing, failed = 0, 0, 0, 0
    total_dates = 0

    for year, month, dates in iter_months(START_DATE, END_DATE):
        total_dates += len(dates)
        print(f"── {year}-{month:02d}  ({len(dates)} days) ──────────────────")
        for d in dates:
            result = download_file(d, OUTPUT_DIR)
            if result == "ok":
                downloaded += 1
            elif result == "skipped":
                skipped += 1
            elif result == "missing":
                missing += 1
            else:
                failed += 1
            # Brief pause to be polite to the server
            time.sleep(0.5)

    available = downloaded + skipped
    coverage  = 100 * available / total_dates if total_dates > 0 else 0

    print(f"\n── Download Summary ──────────────────────────────────────────")
    print(f"  Total dates expected : {total_dates}")
    print(f"  Downloaded (new)     : {downloaded}")
    print(f"  Already on disk      : {skipped}")
    print(f"  Not yet available    : {missing}")
    print(f"  Errors               : {failed}")
    print(f"  Coverage             : {available}/{total_dates} days ({coverage:.0f}%)")
    print(f"  Files are in         : {os.path.abspath(OUTPUT_DIR)}")

    if failed > 0:
        print(f"\n  [WARN] {failed} file(s) failed to download. "
              "Re-run this script to retry.")
    if coverage < 80:
        print(f"\n  [WARN] Low coverage ({coverage:.0f}%). "
              "Analysis results may be incomplete.")


if __name__ == "__main__":
    main()
