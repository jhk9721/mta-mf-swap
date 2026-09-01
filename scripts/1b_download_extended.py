"""
SCRIPT 1b: DOWNLOAD — GAP FILL / VERIFY
=========================================================
Second pass over the same window 1_download.py covers: January 1, 2025
through today. 1_download.py now pulls the entire range in one go, so this
script no longer adds new months — it exists to close gaps:

  - Days that 404'd on the earlier run because subwaydata.nyc had not
    published them yet (the site runs a day or two behind).
  - Days lost to a network error or an interrupted run.
  - Days published since the last time you downloaded.

Files already on disk are skipped, so this is cheap to run and safe to repeat.
It finishes by listing exactly which dates are still missing, so you know
whether the corpus is complete before running the analysis.

WHY THE WINDOW STARTS IN JANUARY 2025:
  Krueger's office asked whether Jan/Feb are simply worse months for subway
  service regardless of the swap. Jan-Feb 2025 (F train, same season) vs
  Jan-Feb 2026 (M train, post-swap) answers that directly. The rest of 2025
  extends the trend window and supports the seasonality controls.

HOW TO RUN:
  1. Run 1_download.py first.
  2. Then run this script:
         python3 1b_download_extended.py
  3. All files land in the "raw_data" folder at the project root, the same
     place 1_download.py writes to. The analysis scripts pick up everything
     in that folder automatically.
  4. Re-run 3_analyze.py and 5_seasonality_analysis.py to incorporate
     any new data.
"""

import requests
import os
import time
from datetime import date, timedelta

# ── Configuration ─────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "raw_data")   # Same folder as 1_download.py — intentional.

# Same window as 1_download.py — keep these two in sync if the study period
# changes. END_DATE is resolved at run time, so "today" always means today.
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
    Returns: "ok" | "skipped" | "missing" | "failed"
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
            print(f"  [MISS] {filename} — 404, not yet available, skipping.")
            return "missing"
        else:
            print(f"  [ERR]  {filename} — HTTP {response.status_code}")
            return "failed"
    except requests.RequestException as e:
        print(f"  [ERR]  {filename} — {e}")
        return "failed"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Roosevelt Island MTA Analysis — Extended Download")
    print("=" * 55)
    print(f"Saving files to: {os.path.abspath(OUTPUT_DIR)}")
    print(f"Date range:      {START_DATE} to {END_DATE} "
          f"({(END_DATE - START_DATE).days + 1} days)\n")
    print("Purpose: fill any dates missing from the study window —")
    print("         days not yet published on the earlier run, days lost to")
    print("         network errors, and days published since.\n")

    downloaded, skipped, missing, failed = 0, 0, 0, 0
    total_dates = 0
    gaps = []

    for year, month, dates in iter_months(START_DATE, END_DATE):
        total_dates += len(dates)
        month_label = date(year, month, 1).strftime("%B %Y")
        print(f"── {month_label}  ({len(dates)} days) ──────────────────────")
        for d in dates:
            result = download_file(d, OUTPUT_DIR)
            if result == "ok":       downloaded += 1
            elif result == "skipped": skipped += 1
            elif result == "missing": missing += 1; gaps.append(d)
            else:                    failed += 1; gaps.append(d)
            if result != "skipped":
                time.sleep(0.5)   # polite rate limit; no need to pause on skips

    available = downloaded + skipped
    coverage = 100 * available / total_dates if total_dates > 0 else 0

    print(f"\n── Download Summary ──────────────────────────────────────────")
    print(f"  Total dates expected : {total_dates}")
    print(f"  Downloaded (new)     : {downloaded}")
    print(f"  Already on disk      : {skipped}")
    print(f"  Not yet available    : {missing}")
    print(f"  Errors               : {failed}")
    print(f"  Coverage             : {available}/{total_dates} days ({coverage:.0f}%)")
    print(f"  Files are in         : {os.path.abspath(OUTPUT_DIR)}")

    if gaps:
        print(f"\n── Dates still missing ({len(gaps)}) ─────────────────────────")
        print("  The most recent day or two is normally just publication lag.")
        for d in gaps:
            print(f"    {d}")

    if failed > 0:
        print(f"\n  [WARN] {failed} file(s) failed. Re-run to retry.")
    if coverage < 80:
        print(f"\n  [WARN] Low coverage ({coverage:.0f}%). "
              "Seasonality results may be unreliable.")
    else:
        print(f"\n  Ready for analysis.")
        print(f"  Next steps: python3 3_analyze.py")
        print(f"              python3 5_seasonality_analysis.py")


if __name__ == "__main__":
    main()
