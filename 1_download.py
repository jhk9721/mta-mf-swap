"""
SCRIPT 1: DOWNLOAD
==================
Downloads CSV data from subwaydata.nyc for 5 months:
  - October 2025 (pre-swap baseline)
  - November 2025 (pre-swap baseline)
  - December 2025 (swap occurred Dec 8)
  - January 2026  (post-swap)
  - February 2026 (post-swap)

HOW TO RUN:
  1. Make sure you have Python 3 installed.
  2. Install the requests library if you haven't:
         pip install requests
  3. Run this script from your terminal:
         python 1_download.py

Files will be downloaded into a folder called "raw_data" in the same
directory where you run this script. Each file is about 2-10MB compressed.
Total download will be roughly 300-600MB, so give it 10-30 minutes depending
on your connection.
"""

import requests
import os
import time
from datetime import date, timedelta

# ── Configuration ─────────────────────────────────────────────────────────────

OUTPUT_DIR = "raw_data"

# Date ranges to download
MONTHS = [
    (2025, 10),  # October 2025  - pre-swap
    (2025, 11),  # November 2025 - pre-swap
    (2025, 12),  # December 2025 - swap happens Dec 8
    (2026,  1),  # January 2026  - post-swap
    (2026,  2),  # February 2026 - post-swap
]

BASE_URL = "https://subwaydata.nyc/data"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_all_dates(year, month):
    """Return all dates (as date objects) in a given year/month."""
    start = date(year, month, 1)
    dates = []
    d = start
    while d.month == month:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def download_file(d: date, output_dir: str) -> bool:
    """
    Download the CSV tar.xz for a single date.
    Returns True on success, False on failure.
    """
    filename = f"subwaydatanyc_{d.strftime('%Y-%m-%d')}_csv.tar.xz"
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        print(f"  [SKIP] {filename} already exists.")
        return True

    url = f"{BASE_URL}/{filename}"
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024
            print(f"  [OK]   {filename}  ({size_kb:.0f} KB)")
            return True
        elif response.status_code == 404:
            print(f"  [MISS] {filename} not found (404) — skipping.")
            return False
        else:
            print(f"  [ERR]  {filename} HTTP {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"  [ERR]  {filename} failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Saving files to: {os.path.abspath(OUTPUT_DIR)}\n")

    success, skipped, failed = 0, 0, 0

    for year, month in MONTHS:
        dates = get_all_dates(year, month)
        print(f"── {year}-{month:02d}  ({len(dates)} days) ──────────────────")
        for d in dates:
            result = download_file(d, OUTPUT_DIR)
            if result:
                success += 1
            else:
                failed += 1
            # Brief pause to be polite to the server
            time.sleep(0.5)

    print(f"\nDone. {success} downloaded/skipped, {failed} failed.")
    print(f"Files are in: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
