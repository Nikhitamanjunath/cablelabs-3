#!/usr/bin/env python3
"""
Copy or move parquet files from source dir(s) into work_dir/raw_data/<band>/.
Rename to Band_<band>_WO_meta_YYYYMMDD_HHMMSS.parquet where YYYYMMDD and HHMMSS
come from the **source file's OS last-modified time** (so 7:35 PM -> 193500, not 003500).
The destination file's last-modified time is also set from the source file's OS mtime.

Expected source filename: Band_<band>_WO_meta_YYYYMMDD_<time>.parquet (band is taken from name).
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# Default source folders (relative to cwd when not using --sources)
SOURCE_DIRS = ["Data1 2", "Data1", "Data2"]

# Filename pattern: Band_<band>_WO_meta_YYYYMMDD_<time>.parquet
BAND_PATTERN = re.compile(
    r"^Band_(\d+MHz)_WO_meta_(\d{8})_(\d{4}|\d{6})\.parquet$", re.IGNORECASE
)


def parse_filename(name: str) -> tuple[str, str, str] | None:
    """Return (band, yyyymmdd, time_6digits) or None. time_6digits is HHMMSS."""
    m = BAND_PATTERN.match(name)
    if not m:
        return None
    band, yyyymmdd, time_part = m.group(1), m.group(2), m.group(3)
    time_6 = time_part + "00" if len(time_part) == 4 else time_part
    return band, yyyymmdd, time_6


def standard_name(band: str, yyyymmdd: str, time_6: str) -> str:
    """Target filename: Band_<band>_WO_meta_YYYYMMDD_HHMMSS.parquet"""
    return f"Band_{band}_WO_meta_{yyyymmdd}_{time_6}.parquet"


def mtime_to_name_parts(mtime_ts: float) -> tuple[str, str]:
    """Convert OS mtime (Unix ts) to (YYYYMMDD, HHMMSS) in local time for filename."""
    local = datetime.fromtimestamp(mtime_ts)
    return local.strftime("%Y%m%d"), local.strftime("%H%M%S")


def _resolve_sources(
    source_specs: list[str],
    repo_root: Path,
) -> list[Path]:
    """Resolve each spec to an absolute source directory Path (only existing dirs)."""
    out: list[Path] = []
    for spec in source_specs:
        spec = os.path.expanduser(spec.strip())
        p = Path(spec)
        if not p.is_absolute():
            p = repo_root / p
        if p.is_dir():
            out.append(p.resolve())
    return out


def _list_source_mtimes(source_dirs: list[Path], first_n: int = 5, last_n: int = 5) -> None:
    """List first and last N source parquets with OS last-modified date/time (for checking dates)."""
    total = 0
    for d in source_dirs:
        paths = sorted(d.glob("*.parquet"))
        total += len(paths)
        print(f"\n{d.name} ({len(paths)} parquets)")
        if len(paths) <= first_n + last_n:
            show = paths
        else:
            show = paths[:first_n] + paths[-last_n:]
        for i, path in enumerate(show):
            if len(paths) > first_n + last_n and i == first_n:
                print(f"  ... and {len(paths) - first_n - last_n} more ...")
            mtime = path.stat().st_mtime
            local = datetime.fromtimestamp(mtime)
            print(f"  {path.name}  OS mtime: {local.strftime('%Y-%m-%d %H:%M:%S')} (local)")
    print(f"\nTotal: {total} parquets")


def integrate(
    work_dir: Path,
    source_dir_names: list[str] | None = None,
    source_paths: list[Path] | None = None,
    dry_run: bool = False,
    move: bool = False,
    samples_dir: Path | None = None,
    samples_n: int = 100,
) -> tuple[int, int, int]:
    """
    Copy (or move) parquets from source dirs into work_dir/raw_data/<band>/,
    rename to YYYYMMDD_HHMMSS. Destination file mtime = source file's OS last-modified time.
    If samples_dir is set, keep ~samples_n files (evenly across sources) in samples_dir (renamed).
    Returns (files_copied, files_skipped, files_deleted).
    """
    repo_root = Path.cwd()
    if source_paths:
        source_dirs = source_paths
    else:
        names = source_dir_names or SOURCE_DIRS
        source_dirs = [repo_root / d for d in names if (repo_root / d).is_dir()]

    raw_data = work_dir / "raw_data"
    raw_data.mkdir(parents=True, exist_ok=True)
    if samples_dir:
        samples_dir = Path(samples_dir).resolve()
        samples_dir.mkdir(parents=True, exist_ok=True)

    # Collect parquets per source and pick ~samples_n evenly across sources
    parquets_per_dir: list[list[Path]] = [sorted(d.glob("*.parquet")) for d in source_dirs]
    all_parquets: list[Path] = [p for sub in parquets_per_dir for p in sub]
    sample_set: set[Path] = set()
    if samples_dir and samples_n > 0 and parquets_per_dir:
        n_sources = len(parquets_per_dir)
        per_source = max(1, samples_n // n_sources)
        extra = samples_n - per_source * n_sources
        for i, paths in enumerate(parquets_per_dir):
            take = per_source + (1 if i < extra else 0)
            step = max(1, len(paths) // take) if paths else 0
            for j in range(0, min(take * step, len(paths)), step):
                if len(sample_set) >= samples_n:
                    break
                sample_set.add(paths[j])
            if len(sample_set) >= samples_n:
                break

    copied = 0
    skipped = 0
    deleted = 0
    for path in all_parquets:
        parsed = parse_filename(path.name)
        if not parsed:
            skipped += 1
            if dry_run:
                print(f"Skip (no match): {path.name}")
            continue
        band = parsed[0]
        # Build YYYYMMDD_HHMMSS from source file's OS last-modified time (so 7:35 PM -> 193500)
        src_mtime = path.stat().st_mtime
        yyyymmdd, time_6 = mtime_to_name_parts(src_mtime)
        dest_name = standard_name(band, yyyymmdd, time_6)
        band_dir = raw_data / band
        band_dir.mkdir(parents=True, exist_ok=True)
        dest = band_dir / dest_name
        if dest.exists() and dest.stat().st_mtime >= path.stat().st_mtime:
            skipped += 1
            if dry_run:
                print(f"Skip (up to date): {dest_name}")
            continue
        if dry_run:
            print(f"Would copy: {path} -> {dest}")
            if move:
                print(f"  then delete: {path}")
            if path in sample_set and samples_dir:
                print(f"  and copy to samples: {samples_dir / dest_name}")
            copied += 1
            continue
        shutil.copy2(path, dest)
        # Preserve source file's OS last-modified time on destination
        src_mtime = path.stat().st_mtime
        os.utime(str(dest), (src_mtime, src_mtime))
        copied += 1
        if path in sample_set and samples_dir:
            shutil.copy2(dest, samples_dir / dest_name)
        if move:
            path.unlink()
            deleted += 1
    return copied, skipped, deleted


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="Integrate parquets into work_dir/raw_data (rename, Eastern mtime). Optional: move (delete source), keep samples."
    )
    p.add_argument("--work-dir", type=Path, default=Path("work_dir"), help="Work directory (raw_data parent)")
    p.add_argument("--dry-run", action="store_true", help="Only print what would be done")
    p.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Source folders: names (under cwd) or paths e.g. ~/Desktop/Data ~/Desktop/Data1 ~/Desktop/Data2",
    )
    p.add_argument(
        "--move",
        action="store_true",
        help="Delete source file after copying to destination (move).",
    )
    p.add_argument(
        "--samples-dir",
        type=Path,
        default=None,
        help="Copy ~N renamed samples here for verification (e.g. ~/Desktop/samples)",
    )
    p.add_argument("--samples-n", type=int, default=100, help="Number of sample files to keep in samples-dir (default 100)")
    p.add_argument(
        "--list-mtimes",
        action="store_true",
        help="Only list source parquets with OS last-modified date/time (for checking dates); then exit.",
    )
    args = p.parse_args()

    if args.list_mtimes:
        if args.sources is not None:
            source_dirs = _resolve_sources(args.sources, Path.cwd())
        else:
            source_dirs = [Path.cwd() / d for d in SOURCE_DIRS if (Path.cwd() / d).is_dir()]
        _list_source_mtimes(source_dirs)
        return

    work_dir = args.work_dir if args.work_dir.is_absolute() else Path.cwd() / args.work_dir
    work_dir = work_dir.resolve()
    samples_dir = None
    if args.samples_dir is not None:
        samples_dir = args.samples_dir if args.samples_dir.is_absolute() else Path.cwd() / args.samples_dir

    source_paths = None
    if args.sources is not None:
        source_paths = _resolve_sources(args.sources, Path.cwd())

    copied, skipped, deleted = integrate(
        work_dir,
        source_dir_names=None if source_paths else args.sources,
        source_paths=source_paths,
        dry_run=args.dry_run,
        move=args.move,
        samples_dir=samples_dir,
        samples_n=args.samples_n,
    )
    print(f"Copied: {copied}, Skipped: {skipped}", end="")
    if args.move:
        print(f", Deleted (moved): {deleted}", end="")
    if samples_dir:
        print(f", Samples dir: {samples_dir}", end="")
    print()

    if args.dry_run and (args.move or samples_dir):
        print("(Re-run without --dry-run to perform copy/move and create samples.)")


if __name__ == "__main__":
    main()
