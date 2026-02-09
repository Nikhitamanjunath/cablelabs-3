"""
Synthesize: fill blanks using previous value + time-of-day delta; also synthesize missing days.
Reads work_dir/transformed/<band>/transformed_<YYYYMMDD>.parquet.
- For days with data: fill missing (hour, freq) per threshold using value(prev hour, same freq) + delta(hour),
  where delta(hour) is the mean (AU at hour - AU at prev hour) from observed data.
- For missing days (e.g. 5th): generate full grid from mean AU profile (mean over other days per hour/freq/threshold).
Writes work_dir/final/<band>/final_<YYYYMMDD>.parquet. Does not modify transformed data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

SCHEMA = ["date", "hour", "band", "freq_center_ghz", "threshold_dbm", "au_pct"]


def _yyyymmdd_to_dash(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _compute_deltas_and_profile(
    band_str: str,
    band_dfs: list[tuple[str, pd.DataFrame]],
) -> tuple[dict, dict]:
    """
    band_dfs: list of (yyyymmdd, df) for this band.
    Returns:
      delta_by_hour: (band_str, threshold) -> { hour: mean_delta } for hour 1..23
      mean_profile: (hour, freq, threshold) -> mean au_pct (for missing days)
    """
    all_dfs = [df for _, df in band_dfs]
    if not all_dfs:
        return {}, {}

    combined = pd.concat(all_dfs, ignore_index=True)
    thresholds = sorted(combined["threshold_dbm"].unique())
    freqs_all = sorted(combined["freq_center_ghz"].unique())
    hours_all = sorted(combined["hour"].unique())

    # Mean profile: (hour, freq, threshold) -> mean au_pct (for missing days)
    mean_profile: dict[tuple[int, float, int], float] = {}
    for th in thresholds:
        sub = combined[combined["threshold_dbm"] == th]
        for (h, f), g in sub.groupby(["hour", "freq_center_ghz"]):
            mean_profile[(h, float(f), th)] = g["au_pct"].mean()

    # Delta by hour: for each (band, threshold, hour h in 1..23), mean( AU at h - AU at h-1 )
    delta_by_key: dict[tuple[str, int, int], list[float]] = {}  # (band, th, hour) -> list of deltas
    for th in thresholds:
        key = (band_str, th)
        for h in range(1, 24):
            # Rows at hour h and hour h-1, same (date, freq)
            # We need pairs (date, freq) that have both h and h-1
            deltas = []
            for _, df in band_dfs:
                s_h = df[(df["threshold_dbm"] == th) & (df["hour"] == h)]
                s_prev = df[(df["threshold_dbm"] == th) & (df["hour"] == h - 1)]
                if s_h.empty or s_prev.empty:
                    continue
                merge = s_h[["freq_center_ghz", "au_pct"]].merge(
                    s_prev[["freq_center_ghz", "au_pct"]],
                    on="freq_center_ghz",
                    suffixes=("_h", "_prev"),
                )
                if not merge.empty:
                    d = (merge["au_pct_h"] - merge["au_pct_prev"]).values
                    deltas.extend(d.tolist())
            if deltas:
                delta_by_key.setdefault((band_str, th, h), []).extend(deltas)

    # Convert to mean delta per (band, threshold), array index = hour (0..23), hour 0 = 0
    delta_by_hour: dict[tuple[str, int], float] = {}
    for (b, th, h), vals in delta_by_key.items():
        k = (b, th)
        if k not in delta_by_hour:
            delta_by_hour[k] = 0.0  # placeholder; we store per-hour in a different structure
    # Better: return a dict (band, threshold, hour) -> mean_delta for hour in 1..23
    delta_map: dict[tuple[str, int], float] = {}
    for (b, th, h), vals in delta_by_key.items():
        delta_map[(b, th, h)] = float(np.mean(vals))
    # Expose as (band, threshold) -> dict hour -> delta for hour 1..23
    delta_by_hour = {}  # (band, threshold) -> { hour: mean_delta }
    for (b, th, h), v in delta_map.items():
        k = (b, th)
        if k not in delta_by_hour:
            delta_by_hour[k] = {}
        delta_by_hour[k][h] = v

    return delta_by_hour, mean_profile


def _fill_with_prev_plus_delta(
    df: pd.DataFrame,
    band_str: str,
    hours_full: list[int],
    freqs_full: list[float],
    thresholds_full: list[int],
    delta_by_hour: dict,
    mean_profile: dict,
) -> pd.DataFrame:
    """
    Build full grid for this df (one date, one band). Fill missing (hour, freq) per threshold
    using value(prev hour, same freq) + delta(hour). Hour 0: use observed or mean_profile or 0.
    """
    date_dash = df["date"].iloc[0]
    rows: list[dict] = []
    for th in thresholds_full:
        sub = df[df["threshold_dbm"] == th]
        # Matrix: hour x freq, init with nan
        mat = np.full((len(hours_full), len(freqs_full)), np.nan)
        hour_to_idx = {h: i for i, h in enumerate(hours_full)}
        freq_to_idx = {f: j for j, f in enumerate(freqs_full)}
        for _, r in sub.iterrows():
            i = hour_to_idx.get(r["hour"])
            j = freq_to_idx.get(r["freq_center_ghz"])
            if i is not None and j is not None:
                mat[i, j] = float(r["au_pct"])

        deltas = delta_by_hour.get((band_str, th), {})

        for i, hour in enumerate(hours_full):
            for j, freq in enumerate(freqs_full):
                if not np.isnan(mat[i, j]):
                    val = mat[i, j]
                else:
                    h_int, f_float = int(hour), float(freq)
                    if hour == 0:
                        val = mean_profile.get((h_int, f_float, th), 0.0)
                    else:
                        prev_idx = hour_to_idx.get(hour - 1)
                        if prev_idx is not None and not np.isnan(mat[prev_idx, j]):
                            prev_val = mat[prev_idx, j]
                        else:
                            prev_val = mean_profile.get((h_int - 1, f_float, th), 0.0)
                        delta = deltas.get(h_int, 0.0)
                        val = max(0.0, min(100.0, prev_val + delta))
                    mat[i, j] = val
                rows.append({
                    "date": date_dash,
                    "hour": hour,
                    "band": band_str,
                    "freq_center_ghz": freq,
                    "threshold_dbm": th,
                    "au_pct": round(float(mat[i, j]), 6),
                })
    return pd.DataFrame(rows)


def run_synthesize(work_dir: Path) -> list[Path]:
    work_dir = work_dir.resolve()
    transformed_dir = work_dir / "transformed"
    out_base = work_dir / "final"
    if not transformed_dir.exists():
        raise FileNotFoundError("Transformed directory not found: " + str(transformed_dir))

    band_dirs = sorted([d for d in transformed_dir.iterdir() if d.is_dir()])
    if not band_dirs:
        print("No band directories in transformed.")
        return []

    written: list[Path] = []

    for band_dir in tqdm(band_dirs, desc="Finalize bands", unit="band"):
        band_str = band_dir.name
        parquet_files = sorted(band_dir.glob("transformed_*.parquet"))
        if not parquet_files:
            continue

        band_dfs_with_date: list[tuple[str, pd.DataFrame]] = []
        for p in parquet_files:
            yyyymmdd = p.stem.replace("transformed_", "")
            if len(yyyymmdd) != 8:
                continue
            try:
                df = pd.read_parquet(p)
            except Exception:
                continue
            if df.empty or not all(c in df.columns for c in SCHEMA):
                continue
            df = df.copy()
            df["date"] = _yyyymmdd_to_dash(yyyymmdd)
            band_dfs_with_date.append((yyyymmdd, df))

        if not band_dfs_with_date:
            continue

        combined = pd.concat([df for _, df in band_dfs_with_date], ignore_index=True)
        hours_full = sorted(combined["hour"].unique())
        freqs_full = sorted(combined["freq_center_ghz"].unique())
        thresholds_full = sorted(combined["threshold_dbm"].unique())
        if not hours_full or not freqs_full or not thresholds_full:
            continue

        delta_by_hour, mean_profile = _compute_deltas_and_profile(
            band_str, band_dfs_with_date
        )
        dates_with_data = {yyyymmdd for yyyymmdd, _ in band_dfs_with_date}
        date_min = min(dates_with_data)
        date_max = max(dates_with_data)
        d_min = datetime.strptime(date_min, "%Y%m%d")
        d_max = datetime.strptime(date_max, "%Y%m%d")
        date_range: list[str] = []
        d = d_min
        while d <= d_max:
            date_range.append(d.strftime("%Y%m%d"))
            d += timedelta(days=1)

        out_dir = out_base / band_str
        out_dir.mkdir(parents=True, exist_ok=True)
        df_by_date = {yyyymmdd: df for yyyymmdd, df in band_dfs_with_date}

        for date_yyyymmdd in date_range:
            date_dash = _yyyymmdd_to_dash(date_yyyymmdd)
            if date_yyyymmdd in df_by_date:
                df = df_by_date[date_yyyymmdd]
                out_df = _fill_with_prev_plus_delta(
                    df, band_str, hours_full, freqs_full, thresholds_full,
                    delta_by_hour, mean_profile,
                )
            else:
                # Missing day: full grid from mean profile
                rows = []
                for hour in hours_full:
                    for freq in freqs_full:
                        for th in thresholds_full:
                            au = mean_profile.get((int(hour), float(freq), th), 0.0)
                            rows.append({
                                "date": date_dash,
                                "hour": hour,
                                "band": band_str,
                                "freq_center_ghz": freq,
                                "threshold_dbm": th,
                                "au_pct": round(float(au), 6),
                            })
                out_df = pd.DataFrame(rows)
            out_path = out_dir / f"final_{date_yyyymmdd}.parquet"
            out_df.to_parquet(out_path, index=False)
            written.append(out_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize: previous value + time-of-day delta; fill missing days. Write to work_dir/final"
    )
    parser.add_argument("--work-dir", type=Path, default=Path("work_dir"), help="Work directory (transformed, final)")
    args = parser.parse_args()
    work_dir = args.work_dir.resolve()
    paths = run_synthesize(work_dir)
    for p in paths:
        print(p)
    if not paths:
        print("No final parquet files written.")


if __name__ == "__main__":
    main()
