# Transform

Reads parquet files in `work_dir/raw_data/<band>/` for the **date** (and optional **band**) in config, computes AU per (hour, frequency bin, power threshold) using **cbw per band** for frequency binning, and writes one parquet per (date, band) under `work_dir/transformed/<band>/` so the folder structure mirrors `raw_data`.

- **Input:** `work_dir/raw_data/<band>/*.parquet` (e.g. `Band_195MHz_WO_meta_20260201_0037.parquet` in `work_dir/raw_data/195MHz/`)
- **Output:** `work_dir/transformed/<band>/transformed_<YYYYMMDD>.parquet` (same category subfolders as raw_data)  
  Schema: `date`, `hour`, `band`, `freq_center_ghz`, `threshold_dbm`, `au_pct`

**AU (airtime utilization):** Matches MATLAB `StatisticsPerHour_v3.m`. For each hour, time is split into **1-second** bins (3600 bins/hour), aligned to the hour boundary. AU % = (number of 1-sec bins with at least one detection above threshold) / N_denominator × 100, with N_denominator = min(unique timestamps in hour, 3600), so 0–100% per (hour, freq bin, threshold).

Run: `task transform` (or `python -m transform.transform --work-dir work_dir`).

**Config** (`transform/config.yaml` or `work_dir/config.yaml`):

- **date_filter**: Single date to process (e.g. `"2026-02-03"` or `"20260203"`). If set, overrides **date_from** / **date_to**. If **null** and no range, all days present in raw_data are transformed.
- **date_from** / **date_to**: Optional inclusive range. Same format as date_filter. If only **date_from** is set, process from that day onward; if only **date_to**, up to that day; if both, only dates in `[date_from, date_to]`. Ignored when **date_filter** is set.
- **band**: optional. If set (e.g. `"195MHz"`), only that band; if `null`, all bands under `raw_data`.
- **cbw**: channel bandwidth in Hz per band. Either a single number (used for all bands) or a map (e.g. `195MHz: 1000000`, `3765MHz: 5000000`). Bands not listed use **cbw_default**.
- **cbw_default**: Hz used when a band is not in **cbw** (e.g. `1000000` = 1 MHz).
- **power_threshold**: dBm per band. Either a single value or list (used for all bands) or a map (e.g. `195MHz: -100`, `3765MHz: [-90, -95, -100]`). Bands not listed use **power_threshold_default**.
- **power_threshold_default**: dBm used when a band is not in **power_threshold** (e.g. `-100`).
