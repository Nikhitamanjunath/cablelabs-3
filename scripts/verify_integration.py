#!/usr/bin/env python3
"""
Verify that all parquet files from source dir(s) are in work_dir/raw_data with correct
rename (Band_<band>_WO_meta_YYYYMMDD_HHMMSS.parquet) and spot-check that data looks right.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

SOURCE_DIRS_DEFAULT = ["Data1 2", "Data1", "Data2"]
BAND_PATTERN = re.compile(
    r"^Band_(\d+MHz)_WO_meta_(\d{8})_(\d{4}|\d{6})\.parquet$", re.IGNORECASE
)


def parse_filename(name: str) -> tuple[str, str, str] | None:
    m = BAND_PATTERN.match(name)
    if not m:
        return None
    band, yyyymmdd, time_part = m.group(1), m.group(2), m.group(3)
    time_6 = time_part + "00" if len(time_part) == 4 else time_part
    return band, yyyymmdd, time_6


def standard_name(band: str, yyyymmdd: str, time_6: str) -> str:
    return f"Band_{band}_WO_meta_{yyyymmdd}_{time_6}.parquet"


def verify(
    work_dir: Path,
    source_dir_names: list[str],
    check_parquet_content: bool = True,
    sample_size: int = 5,
) -> tuple[int, int, list[str]]:
    """
    Returns (total_source, missing_count, list of missing or errors).
    """
    repo_root = work_dir.parent
    raw_data = work_dir / "raw_data"
    if not raw_data.exists():
        return 0, 0, [f"raw_data not found: {raw_data}"]

    total_src = 0
    missing = []
    for dir_name in source_dir_names:
        src_dir = repo_root / dir_name
        if not src_dir.is_dir():
            continue
        for path in sorted(src_dir.glob("*.parquet")):
            total_src += 1
            parsed = parse_filename(path.name)
            if not parsed:
                missing.append(f"NO_PARSE: {path.name}")
                continue
            band, yyyymmdd, time_6 = parsed
            dest_name = standard_name(band, yyyymmdd, time_6)
            dest = raw_data / band / dest_name
            if not dest.exists():
                missing.append(f"MISSING: {path.name} -> {dest}")
            elif check_parquet_content and pd is not None and total_src <= sample_size:
                try:
                    df = pd.read_parquet(dest)
                    required = {"timestamp", "freqs", "trace_max"}
                    if not required.issubset(df.columns):
                        missing.append(
                            f"BAD_COLS: {dest_name} columns={list(df.columns)}"
                        )
                    elif df.empty:
                        missing.append(f"EMPTY: {dest_name}")
                except Exception as e:
                    missing.append(f"READ_ERR: {dest_name} {e}")

    return total_src, len(missing), missing


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Verify integration: all sources in raw_data, correct rename")
    p.add_argument("--work-dir", type=Path, default=Path("work_dir"))
    p.add_argument("--sources", nargs="*", default=None)
    p.add_argument("--no-content-check", action="store_true", help="Skip parquet column spot-check")
    p.add_argument("--runs", type=int, default=1, help="Number of verification runs (default 1)")
    args = p.parse_args()
    work_dir = args.work_dir if args.work_dir.is_absolute() else Path.cwd() / args.work_dir
    sources = args.sources if args.sources is not None else SOURCE_DIRS_DEFAULT
    # Only existing source dirs
    sources = [s for s in sources if (Path.cwd() / s).is_dir()]

    for run in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"--- Verification run {run}/{args.runs} ---")
        total, missing_count, issues = verify(
            work_dir,
            sources,
            check_parquet_content=not args.no_content_check,
        )
        print(f"Source parquets: {total}")
        print(f"Missing/bad: {missing_count}")
        if issues:
            for x in issues[:30]:
                print(f"  {x}")
            if len(issues) > 30:
                print(f"  ... and {len(issues) - 30} more")
            if run < args.runs:
                print()
        else:
            print("OK: All files present with correct rename; spot-check passed.")
        if run < args.runs:
            print()

    sys.exit(1 if missing_count else 0)


if __name__ == "__main__":
    main()
