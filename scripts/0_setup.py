"""
SCRIPT 0: SETUP — Environment Verification
===========================================
Run this before any other script to confirm your environment is ready.

Checks:
  1. Python version (≥ 3.9)
  2. Required packages (and their minimum versions)
  3. Available disk space (≥ 1 GB recommended)
  4. Internet connectivity to subwaydata.nyc
  5. Output directories exist (creates them if not)

HOW TO RUN:
    python3 0_setup.py

All checks print [OK] or [WARN]/[FAIL]. A failing check exits with code 1.
"""

import sys
import os
import importlib
import subprocess
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
RAW_DATA_DIR = SCRIPTS_DIR / "raw_data"
RESULTS_DIR  = SCRIPTS_DIR / "results"

REQUIRED_PACKAGES = [
    ("requests",    "2.31.0"),
    ("pandas",      "2.0.0"),
    ("numpy",       "1.24.0"),
    ("matplotlib",  "3.7.0"),
    ("tqdm",        "4.65.0"),
]

MIN_DISK_GB = 1.0
CHECK_URL   = "https://subwaydata.nyc"


def _version_tuple(v: str):
    return tuple(int(x) for x in v.split(".")[:3])


def check_python_version():
    print("── Python Version ──────────────────────────────────────────────")
    current = sys.version_info
    print(f"  Python {current.major}.{current.minor}.{current.micro}")
    if (current.major, current.minor) < (3, 9):
        print("  [FAIL] Python ≥ 3.9 required.")
        return False
    print("  [OK]")
    return True


def check_packages():
    print("\n── Required Packages ───────────────────────────────────────────")
    all_ok = True
    for pkg, min_ver in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", None)
            if ver is None:
                print(f"  [WARN] {pkg}: installed but version unknown")
                continue
            if _version_tuple(ver) < _version_tuple(min_ver):
                print(f"  [WARN] {pkg} {ver} < required {min_ver}  "
                      f"(run: pip install --upgrade {pkg})")
                all_ok = False
            else:
                print(f"  [OK]   {pkg} {ver}")
        except ImportError:
            print(f"  [FAIL] {pkg} not installed  "
                  f"(run: pip install {pkg}>={min_ver})")
            all_ok = False
    return all_ok


def check_disk_space():
    print("\n── Disk Space ──────────────────────────────────────────────────")
    try:
        stat = os.statvfs(SCRIPTS_DIR)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        print(f"  Free disk space: {free_gb:.1f} GB")
        if free_gb < MIN_DISK_GB:
            print(f"  [WARN] Low disk space — recommend ≥ {MIN_DISK_GB} GB free.")
            return False
        print("  [OK]")
        return True
    except AttributeError:
        # Windows fallback
        import ctypes
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            str(SCRIPTS_DIR), None, None, ctypes.byref(free_bytes)
        )
        free_gb = free_bytes.value / (1024 ** 3)
        print(f"  Free disk space: {free_gb:.1f} GB")
        if free_gb < MIN_DISK_GB:
            print(f"  [WARN] Low disk space — recommend ≥ {MIN_DISK_GB} GB free.")
            return False
        print("  [OK]")
        return True


def check_internet():
    print("\n── Internet Connectivity ───────────────────────────────────────")
    try:
        with urllib.request.urlopen(CHECK_URL, timeout=10) as resp:
            status = resp.status
        if status == 200:
            print(f"  [OK]   {CHECK_URL} reachable (HTTP {status})")
            return True
        else:
            print(f"  [WARN] {CHECK_URL} returned HTTP {status}")
            return False
    except Exception as e:
        print(f"  [FAIL] Cannot reach {CHECK_URL}: {e}")
        print("         Check your internet connection before running 1_download.py.")
        return False


def check_directories():
    print("\n── Output Directories ──────────────────────────────────────────")
    for d in [RAW_DATA_DIR, RESULTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [OK]   {d}  (exists or created)")
    return True


def main():
    print("Roosevelt Island MTA Analysis — Setup Check")
    print("=" * 55)

    results = [
        check_python_version(),
        check_packages(),
        check_disk_space(),
        check_internet(),
        check_directories(),
    ]

    print("\n" + "=" * 55)
    if all(results):
        print("All checks passed. You are ready to run the analysis scripts.")
        print("\nNext steps:")
        print("  1. python3 1_download.py   — download raw GTFS data")
        print("  2. python3 3_analyze.py    — compute headways and generate charts")
        print("  3. python3 4_community_output.py — generate community-facing outputs")
        sys.exit(0)
    else:
        print("One or more checks failed or warned. Fix the issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
