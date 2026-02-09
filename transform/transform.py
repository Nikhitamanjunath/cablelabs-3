"""
Transform raw parquet files (per day, per band) into a single transformed parquet per (date, band)
suitable for downstream models. Uses config (date_filter, band, cbw, power_threshold) and writes
to work_dir/transformed/.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from tqdm import tqdm


# Default thresholds used in notebook 7 (can be overridden by config power_threshold as list)
DEFAULT_THRESHOLDS = [-90, -95, -100, -105, -110, -115, -120, -125, -130]
# Match MATLAB StatisticsPerHour_v3: AU uses 1-second time bins (3600 bins/hour). CO uses T_INTER_CO.
T_BIN_AU = 1.0  # seconds per time bin for AU (MATLAB: bin_t_AU = Timestamp_start:1:Timestamp_start+3600)
T_INTER_CO = 60.0  # seconds per time bin for channel occupancy (MATLAB: bin_t_CO)


def _date_hour_from_path(path: Path) -> tuple[str, int] | None:
    """Parse (YYYYMMDD, hour) from parquet filename.
    Supports e.g. Band_195MHz_WO_meta_20260201_0037.parquet or ..._20260203_000058.parquet (YYYYMMDD_HHMMSS).
    """
    name = path.name
    # Filename suffix is YYYYMMDD_HHMMSS.parquet (8 + 6 digits); hour is first 2 of HHMMSS
    m = re.search(r"(\d{8})_(\d{2})\d{4}\.parquet", name, re.IGNORECASE)
    if m:
        return m.group(1), int(m.group(2))
    return None


def _statistics_per_hour(
    ts_all: np.ndarray,
    fr_all: np.ndarray,
    cbw: float,
    t_bin_au: float,
    t_bin_co: float,
    n_denominator: int,
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Compute occupancy and AU per frequency channel for one hour (matches MATLAB StatisticsPerHour_v3).

    - AU: 1-second time bins (3600 bins/hour), aligned to hour boundary. AU % = (1-sec bins with detection) / N_denominator * 100.
    - CO: t_bin_co-second bins (e.g. 60). co_ot: (n_time_bins, n_freq_bins) 0/1.
    - ts_start: start of hour (aligned like MATLAB: Timestamp(1) - mod(Timestamp(1), 3600)).
    - bin_t_co: time bin edges for CO.

    Returns:
        (co_ot, au_per_hour, ts_start, bin_t_co)
    """
    if ts_all.size == 0 or fr_all.size == 0:
        return np.array([]), np.array([]), 0.0, np.array([])

    ts_min = float(np.min(ts_all))
    # Align to hour boundary (MATLAB: Timestamp_start = Timestamp(1) - mod(Timestamp(1), 3600))
    ts_start = np.floor(ts_min / 3600.0) * 3600.0
    f_min = np.floor(np.min(fr_all) / cbw) * cbw
    f_max = np.ceil(np.max(fr_all) / cbw) * cbw
    bin_f = np.arange(f_min, f_max + cbw * 0.5, cbw)
    n_freq_bins = len(bin_f) - 1
    if n_freq_bins <= 0:
        return np.array([]), np.array([]), ts_start, np.array([])

    # Restrict to this hour (MATLAB: Timestamp >= bin_t_AU(1) & Timestamp < bin_t_AU(end))
    in_range = (ts_all >= ts_start) & (ts_all < ts_start + 3600.0)
    ts_all = ts_all[in_range]
    fr_all = fr_all[in_range]
    if ts_all.size == 0 or fr_all.size == 0:
        return np.array([]), np.array([]), ts_start, np.array([])

    # AU: 1-second bins (3600 per hour), same as MATLAB bin_t_AU = Timestamp_start:1:Timestamp_start+3600
    time_bin_idx_au = np.floor((ts_all - ts_start) / t_bin_au).astype(int)
    time_bin_idx_au = np.clip(time_bin_idx_au, 0, 3599)
    freq_bin_idx = np.floor((fr_all - f_min) / cbw).astype(int)
    freq_bin_idx = np.clip(freq_bin_idx, 0, n_freq_bins - 1)

    n_bins_au = 3600
    co_au = np.zeros((n_bins_au, n_freq_bins), dtype=np.float64)
    co_au[time_bin_idx_au, freq_bin_idx] = 1.0
    denom = max(n_denominator, 1)
    n_occupied_per_freq = (co_au > 0).sum(axis=0).astype(np.float64)
    au_per_hour = n_occupied_per_freq * (100.0 / denom)

    # CO: t_bin_co-second bins (e.g. 60), same as MATLAB bin_t_CO
    time_bin_idx_co = np.floor((ts_all - ts_start) / t_bin_co).astype(int)
    n_bins_co = int(3600 // t_bin_co)  # 60 for t_bin_co=60
    time_bin_idx_co = np.clip(time_bin_idx_co, 0, n_bins_co - 1)
    co_ot = np.zeros((n_bins_co, n_freq_bins), dtype=np.float64)
    co_ot[time_bin_idx_co, freq_bin_idx] = 1.0
    bin_t_co = np.arange(0, n_bins_co + 1) * t_bin_co + ts_start
    return co_ot, au_per_hour, ts_start, bin_t_co


def _normalize_date(date_input: str | None) -> tuple[str, str] | None:
    """Normalize date to (YYYYMMDD, YYYY-MM-DD). Returns None if date_input is None/empty."""
    if not date_input or not str(date_input).strip():
        return None
    s = str(date_input).replace("-", "_").strip()
    if len(s) == 10 and s[4] == "_" and s[7] == "_":
        yyyymmdd = s[:4] + s[5:7] + s[8:10]
        return yyyymmdd, f"{s[:4]}-{s[5:7]}-{s[8:10]}"
    if len(s) == 8 and s.isdigit():
        return s, f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    s_clean = s.replace("_", "")
    if len(s_clean) == 8 and s_clean.isdigit():
        return s_clean, f"{s_clean[:4]}-{s_clean[4:6]}-{s_clean[6:8]}"
    return None


def _yyyymmdd_to_dash(yyyymmdd: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD."""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _discover_dates(raw_data: Path, band_dirs: list[Path]) -> list[tuple[str, str]]:
    """Find all unique dates (YYYYMMDD) present in parquet filenames across band dirs."""
    seen: set[str] = set()
    for band_dir in band_dirs:
        if not band_dir.is_dir():
            continue
        for path in band_dir.glob("*.parquet"):
            dh = _date_hour_from_path(path)
            if dh:
                seen.add(dh[0])
    return [(d, _yyyymmdd_to_dash(d)) for d in sorted(seen)]


def _normalize_band(band_input: str) -> str:
    """Normalize band to e.g. 195MHz."""
    s = str(band_input).strip()
    if re.search(r"^\d+$", s):
        return f"{s}MHz"
    if not re.search(r"MHz$", s, re.IGNORECASE):
        return f"{s}MHz"
    return s


def load_config(work_dir: Path) -> dict[str, Any]:
    """Load transform config from work_dir/config.yaml or transform/config.yaml."""
    for base in [work_dir, Path(__file__).resolve().parent]:
        path = base / "config.yaml"
        if path.exists():
            with open(path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg
    return {}


def run_transform(work_dir: Path, config: dict[str, Any] | None = None) -> list[Path]:
    """
    Read parquet files for the day and band from config, compute AU per (hour, freq, threshold),
    write one parquet per (date, band) under work_dir/transformed/.
    Returns list of written parquet paths.
    """
    cfg = config or load_config(work_dir)
    date_filter = cfg.get("date_filter")
    date_from = cfg.get("date_from")
    date_to = cfg.get("date_to")
    band_filter = cfg.get("band")
    cbw_cfg = cfg.get("cbw")
    cbw_default = float(cfg.get("cbw_default", 1e6))
    power_threshold_cfg = cfg.get("power_threshold", -100)
    power_threshold_default = cfg.get("power_threshold_default", -100)

    def _cbw_for_band(band_str: str) -> float:
        if isinstance(cbw_cfg, (int, float)):
            return float(cbw_cfg)
        if isinstance(cbw_cfg, dict):
            return float(cbw_cfg.get(band_str, cbw_default))
        return cbw_default

    def _thresholds_for_band(band_str: str) -> list[int]:
        """Return list of power thresholds (dBm) for this band."""
        if isinstance(power_threshold_cfg, dict):
            val = power_threshold_cfg.get(band_str, power_threshold_default)
        else:
            val = power_threshold_cfg
        if isinstance(val, (list, tuple)):
            return [int(v) for v in val]
        return [int(val)]

    raw_data = work_dir / "raw_data"
    if not raw_data.exists():
        raise FileNotFoundError(f"Raw data directory not found: {raw_data}")

    if band_filter:
        band_dirs = [raw_data / _normalize_band(band_filter)]
    else:
        band_dirs = [d for d in raw_data.iterdir() if d.is_dir()]

    if date_filter is not None and str(date_filter).strip():
        norm_date = _normalize_date(date_filter)
        if not norm_date:
            raise ValueError("config date_filter must be a valid date (e.g. '2026-02-03' or '20260203')")
        dates_to_process = [norm_date]
    else:
        dates_to_process = _discover_dates(raw_data, band_dirs)
        if not dates_to_process:
            print("No dates found in raw_data (no parquet files with parseable date in filename).")
            return []
        # Apply optional date range (inclusive)
        _from = _normalize_date(date_from) if date_from and str(date_from).strip() else None
        _to = _normalize_date(date_to) if date_to and str(date_to).strip() else None
        from_yyyymmdd = _from[0] if _from else None
        to_yyyymmdd = _to[0] if _to else None
        if from_yyyymmdd is not None or to_yyyymmdd is not None:
            dates_to_process = [
                (d, dash) for d, dash in dates_to_process
                if (from_yyyymmdd is None or d >= from_yyyymmdd) and (to_yyyymmdd is None or d <= to_yyyymmdd)
            ]

    out_base = work_dir / "transformed"
    out_base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for date_yyyymmdd, date_dash in dates_to_process:
        band_work: list[tuple[Path, list[Path], dict]] = []
        for band_dir in band_dirs:
            if not band_dir.exists():
                continue
            all_parquets = sorted(band_dir.glob("*.parquet"))
            parquet_files = [f for f in all_parquets if _date_hour_from_path(f) and _date_hour_from_path(f)[0] == date_yyyymmdd]
            if not parquet_files:
                continue
            groups: dict[tuple[str, int], list[Path]] = {}
            for f in parquet_files:
                dh = _date_hour_from_path(f)
                if dh is None:
                    continue
                key = (dh[0], dh[1])
                groups.setdefault(key, []).append(f)
            band_work.append((band_dir, parquet_files, groups))

        total_parquets = sum(len(files) for _bd, files, _grp in band_work)
        total_hours = sum(len(grp) for _bd, _files, grp in band_work)
        if not band_work:
            continue
        print(f"Transform {date_dash}: {len(band_work)} band(s), {total_parquets} parquet file(s), {total_hours} hour(s) to process\n")

        for band_dir, parquet_files, groups in tqdm(band_work, desc="Bands", unit="band"):
            band_str = band_dir.name
            cbw = _cbw_for_band(band_str)
            thresholds = _thresholds_for_band(band_str)
            rows: list[dict[str, Any]] = []
            for (yyyymmdd, hour), path_list in tqdm(
                sorted(groups.items()),
                desc=f"  {band_str}",
                unit="hour",
                leave=False,
            ):
                dfs = []
                for path in sorted(path_list):
                    try:
                        df = pd.read_parquet(path)
                        if "timestamp" in df.columns and "freqs" in df.columns and "trace_max" in df.columns:
                            dfs.append(df)
                    except Exception:
                        continue
                if not dfs:
                    continue
                df_all = pd.concat(dfs, ignore_index=True)
                time_all = df_all["timestamp"].values
                unique_times = np.unique(time_all)
                # Match MATLAB Parquet2csv_automated_v3: N_denominator = min(length(unique_times), 3600)
                n_denominator = min(len(unique_times), 3600)

                for th_dbm in thresholds:
                    df_p = df_all[df_all["trace_max"] >= th_dbm]
                    ts_all = df_p["timestamp"].values
                    fr_all = df_p["freqs"].values
                    if ts_all.size == 0 or fr_all.size == 0:
                        continue
                    co_ot, au_per_hour, _ts_start, _bin_t = _statistics_per_hour(
                        ts_all, fr_all, cbw, T_BIN_AU, T_INTER_CO, n_denominator
                    )
                    f_min = np.floor(np.min(fr_all) / cbw) * cbw
                    f_max = np.ceil(np.max(fr_all) / cbw) * cbw
                    bin_f = np.arange(f_min, f_max + cbw * 0.5, cbw)
                    freq_centers_ghz = (bin_f[:-1] + bin_f[1:]) / 2 / 1e9
                    if len(au_per_hour) != len(freq_centers_ghz):
                        continue
                    for fc_ghz, au in zip(freq_centers_ghz, au_per_hour):
                        rows.append({
                            "date": date_dash,
                            "hour": hour,
                            "band": band_str,
                            "freq_center_ghz": float(fc_ghz),
                            "threshold_dbm": th_dbm,
                            "au_pct": float(au),
                        })

            if not rows:
                continue
            band_out = out_base / band_str
            band_out.mkdir(parents=True, exist_ok=True)
            out_path = band_out / f"transformed_{date_yyyymmdd}.parquet"
            pd.DataFrame(rows).to_parquet(out_path, index=False)
            written.append(out_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform raw parquet to model-ready parquet in work_dir/transformed")
    parser.add_argument("--work-dir", type=Path, default=Path("work_dir"), help="Work directory (raw_data, config, transformed)")
    args = parser.parse_args()
    work_dir = args.work_dir.resolve()
    paths = run_transform(work_dir)
    for p in paths:
        print(p)
    if not paths:
        print("No parquet files written (no data for config date/band).")


if __name__ == "__main__":
    main()
