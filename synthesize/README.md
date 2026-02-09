# Synthesize

Fills **blanks** in transformed parquet and **synthesizes missing days** (e.g. 5th when 4th and 6th exist). Writes new parquet files under `work_dir/synthesized/`. Does **not** modify `work_dir/transformed/`.

**Method:**

- **Days with data:** For each (date, band), build the full grid (hour × freq × threshold). Keep observed values. For missing (hour, freq) per threshold: set value = **previous value** (same freq, previous hour) **+ delta(hour)**, where **delta(hour)** is the mean (AU at hour − AU at previous hour) from all observed data for that band/threshold. Hour 0 uses the mean profile or 0 when no observation. Values are clipped to 0–100%.
- **Missing days:** For any date in the range [min date, max date] with no transformed file (e.g. Feb 5), output a full grid using the **mean AU profile**: for each (hour, freq, threshold), use the mean `au_pct` across all other days for that band.

**Input:** `work_dir/transformed/<band>/transformed_<YYYYMMDD>.parquet`  
**Output:** `work_dir/synthesized/<band>/synthesized_<YYYYMMDD>.parquet` for every date in the range (including missing days).  
Schema: same as transformed (`date`, `hour`, `band`, `freq_center_ghz`, `threshold_dbm`, `au_pct`); no missing cells.

**Run:** `task synthesize` or `python -m synthesize.synthesize --work-dir work_dir`
