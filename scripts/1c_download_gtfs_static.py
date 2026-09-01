"""
SCRIPT 1c: DOWNLOAD MTA GTFS STATIC SCHEDULE
=============================================
Downloads and unzips MTA's public GTFS static subway schedule into
Resources/gtfs_static/. This is prep for a future schedule-vs-realized
analysis (deferred Item 3) — it does not run any analysis itself.

Idempotent: skips download if Resources/gtfs_static/ already contains
the expected GTFS files. Pass --force to re-download.

HOW TO RUN:
    python3 1c_download_gtfs_static.py
    python3 1c_download_gtfs_static.py --force

OUTPUT:
    Resources/gtfs_static/
      ├── stops.txt
      ├── stop_times.txt
      ├── trips.txt
      ├── routes.txt
      ├── calendar.txt
      ├── calendar_dates.txt
      ├── shapes.txt
      ├── transfers.txt
      └── agency.txt
"""

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

GTFS_URL = "http://web.mta.info/developers/data/nyct/subway/google_transit.zip"

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent   # data + analysis live in the project root
OUT_DIR     = PROJECT_ROOT / "Resources" / "gtfs_static"

EXPECTED_FILES = {
    "stops.txt", "stop_times.txt", "trips.txt", "routes.txt", "calendar.txt",
}


def already_downloaded(out_dir: Path) -> bool:
    if not out_dir.is_dir():
        return False
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    return EXPECTED_FILES.issubset(present)


def download_and_extract(url: str, out_dir: Path) -> None:
    print(f"Downloading: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "roosevelt-island-subway-analysis/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB")

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        print(f"  Archive contains {len(names)} files; extracting to {out_dir}/")
        zf.extractall(out_dir)

    missing = EXPECTED_FILES - {p.name for p in out_dir.iterdir() if p.is_file()}
    if missing:
        print(f"  [WARN] Expected files missing after extract: {sorted(missing)}")
    else:
        print("  [OK] All expected GTFS files present.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if files are already present")
    parser.add_argument("--url", default=GTFS_URL,
                        help=f"GTFS static feed URL (default: {GTFS_URL})")
    args = parser.parse_args()

    if not args.force and already_downloaded(OUT_DIR):
        print(f"GTFS static already present at: {OUT_DIR.resolve()}")
        print("Pass --force to re-download.")
        return 0

    try:
        download_and_extract(args.url, OUT_DIR)
    except Exception as e:
        print(f"  [ERR] Download failed: {e}")
        print("  If MTA's URL has changed, pass --url <new_url>.")
        return 1

    print(f"\nGTFS static schedule available at: {OUT_DIR.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
