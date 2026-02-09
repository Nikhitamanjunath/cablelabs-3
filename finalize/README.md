# Finalize

Fills **blanks** in transformed parquet and **fills missing days** (e.g. 5th when 4th and 6th exist). Writes new parquet files under `work_dir/final/`. Does **not** modify `work_dir/transformed/`.

**Method:**

- **Days with data:** For each (date, band), build the full grid (hour × freq × threshold). Keep observed values. For missing (hour, freq) per threshold: set value = **previous value** (same freq, previous hour) **+ delta(hour)**, where **delta(hour)** is the mean (AU at hour − AU at previous hour) from all observed data for that band/threshold. Hour 0 uses the mean profile or 0 when no observation. Values are clipped to 0–100%.
- **Missing days:** For any date in the range [min date, max date] with no transformed file (e.g. Feb 5), output a full grid using the **mean AU profile**: for each (hour, freq, threshold), use the mean `au_pct` across all other days for that band.

**Input:** `work_dir/transformed/<band>/transformed_<YYYYMMDD>.parquet`  
**Output:** Final data is split 70% training / 30% testing by date (deterministic, first 70% of dates = training):
- `work_dir/final/training/<band>/final_<YYYYMMDD>.parquet`
- `work_dir/final/testing/<band>/final_<YYYYMMDD>.parquet`  
Schema: same as transformed (`date`, `hour`, `band`, `freq_center_ghz`, `threshold_dbm`, `au_pct`); no missing cells.

**Run:** `task finalize` or `python -m finalize.finalize --work-dir work_dir`
