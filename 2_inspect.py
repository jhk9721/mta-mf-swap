"""
SCRIPT 2: INSPECT
=================
Run this AFTER downloading at least one day of data.
It will extract one file, print its column names and a few sample rows,
so you can verify everything looks right before running the full analysis.

HOW TO RUN:
    python 2_inspect.py
"""

import os
import tarfile
import glob
import pandas as pd
import io

RAW_DATA_DIR = "raw_data"

def main():
    files = sorted(glob.glob(os.path.join(RAW_DATA_DIR, "*.tar.xz")))
    if not files:
        print("No .tar.xz files found in raw_data/. Run 1_download.py first.")
        return

    sample_file = files[0]
    print(f"Inspecting: {sample_file}\n")

    with tarfile.open(sample_file, "r:xz") as tar:
        members = tar.getmembers()
        print(f"Files inside the archive:")
        for m in members:
            print(f"  {m.name}  ({m.size / 1024:.0f} KB)")

        # Read each CSV inside
        for member in members:
            if member.name.endswith(".csv"):
                print(f"\n── Reading: {member.name} ──")
                f = tar.extractfile(member)
                if f:
                    df = pd.read_csv(f)
                    print(f"Columns: {list(df.columns)}")
                    print(f"Shape:   {df.shape[0]:,} rows × {df.shape[1]} columns")
                    print(f"\nFirst 5 rows:")
                    print(df.head().to_string())
                    print(f"\nData types:")
                    print(df.dtypes)

                    # Check for Roosevelt Island stop
                    print("\n── Checking for Roosevelt Island data ──")
                    # Common GTFS stop IDs for Roosevelt Island: B06N, B06S
                    for col in df.columns:
                        if "stop" in col.lower():
                            unique_vals = df[col].astype(str).unique()
                            ri_candidates = [v for v in unique_vals if "B06" in v or "roosevelt" in v.lower()]
                            print(f"Column '{col}' — Roosevelt Island candidates: {ri_candidates[:10]}")

if __name__ == "__main__":
    main()
