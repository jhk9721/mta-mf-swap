"""
SCRIPT 1b: DOWNLOAD — EXTENDED (Seasonality + Gap Fill)
=========================================================
Downloads CSV data from subwaydata.nyc for months not covered by
1_download.py, and fills gaps left by that script:

  NEW months (downloaded by this script):
    - January 2025    <- year-ago F train baseline (seasonality test)
    - February 2025   <- year-ago F train baseline (seasonality test)
    - March 2025      <- optional: extends trend window
    - April 2025      <- optional: extends trend window
    - February 2026   <- gap fill (1_download.py may have cut off at Feb 15;
                         files already on disk are skipped automatically)
    - March 2026      <- post-swap trend through today (Mar 12, 2026)

  ALREADY downloaded by 1_download.py (not re-downloaded here):
    - October 2025, November 2025, December 2025  (pre-swap)
    - January 2026                                (post-swap)

WHY THIS MATTERS:
  1. Seasonality test: Krueger's office asked whether Jan/Feb are simply
     worse months for subway service regardless of the swap. Jan-Feb 2025
     (F train, same season) vs Jan-Feb 2026 (M train, post-swap) answers
     that directly.
  2. Gap fill: subwaydata.nyc data may not have been available past Feb 15
     when 1_download.py was last run. This script completes the picture
     through today.

HOW TO RUN:
  1. Run 1_download.py first if you haven't already.
  2. Run this script from the same directory:
         python3 1b_download_extended.py
  3. All files land in the same "raw_data/" folder as 1_download.py.
     The analysis scripts pick up everything in that folder automatically.
  4. Re-run 3_analyze.py and 5_seasonality_analysis.py to incorporate
     the new data.

ESTIMATED DOWNLOAD:
  ~130 days of new data -> roughly 260-520 MB compressed.
  Allow 15-30 minutes depending on your connection.
  Files already on disk are skipped, so re-runs are safe.
"""

import requests
import os
import time
from datetime import date, timedelta

# ── Configuration ─────────────────────────────────────────────────────────────

OUTPUT_DIR = "raw_data"   # Same folder as 1_download.py — intentional.

# Months to download. Files already on disk are skipped automatically.
MONTHS = [
    (2025,  1),   # January 2025   ← year-ago F train baseline (seasonality)
    (2025,  2),   # February 2025  ← year-ago F train baseline (seasonality)
    (2025,  3),   # March 2025     ← optional: extends trend window
    (2025,  4),   # April 2025     ← optional: extends trend window
    (2026,  2),   # February 2026  ← completes Feb (1_download.py may have cut off at Feb 15)
    (2026,  3),   # March 2026     ← post-swap trend through today (Mar 12)
]

BASE_URL = "https://subwaydata.nyc/data"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_all_dates(year: int, month: int) -> list:
    """Return every date in the given year/month."""
    d = date(year, month, 1)
    dates = []
    while d.month == month:
        dates.append(d)
        d += timedelta(days=1)
    return dates


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
    print(f"Saving files to: {os.path.abspath(OUTPUT_DIR)}\n")
    print("Purpose: (1) Jan/Feb 2025 baseline for seasonality test")
    print("         (2) Fill Feb 16-28 2026 gap from 1_download.py")
    print("         (3) Extend post-swap trend through Mar 12, 2026\n")

    downloaded, skipped, missing, failed = 0, 0, 0, 0
    total_dates = 0

    for year, month in MONTHS:
        dates = get_all_dates(year, month)
        total_dates += len(dates)
        month_label = date(year, month, 1).strftime("%B %Y")
        purpose = {
            (2025, 1): "year-ago F train baseline",
            (2025, 2): "year-ago F train baseline",
            (2025, 3): "extended trend window",
            (2025, 4): "extended trend window",
            (2026, 2): "gap fill (complete Feb 2026)",
            (2026, 3): "post-swap trend through today",
        }.get((year, month), "")
        print(f"── {month_label}  [{purpose}]  ({len(dates)} days) ──────────")
        for d in dates:
            result = download_file(d, OUTPUT_DIR)
            if result == "ok":       downloaded += 1
            elif result == "skipped": skipped += 1
            elif result == "missing": missing += 1
            else:                    failed += 1
            time.sleep(0.5)   # polite rate limit

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

    if failed > 0:
        print(f"\n  [WARN] {failed} file(s) failed. Re-run to retry.")
    if coverage < 80:
        print(f"\n  [WARN] Low coverage ({coverage:.0f}%). "
              "Seasonality results may be unreliable.")
    if coverage >= 80:
        print(f"\n  Ready for seasonality analysis.")
        print(f"  Next step: python3 5_seasonality_analysis.py")


if __name__ == "__main__":
    main()
