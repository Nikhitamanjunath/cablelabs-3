# Scripts

## integrate_raw_data.py

Copies or **moves** parquet files from source dir(s) into `work_dir/raw_data/<band>/`, with:

1. **Rename** to the standard format: `Band_<band>_WO_meta_YYYYMMDD_HHMMSS.parquet` (4-digit time → 6-digit with `00` seconds).
2. **Rename date/time** in the filename (YYYYMMDD_HHMMSS) comes from the **source file's OS last-modified time** (so 7:35 PM → `193500`, not `003500`). The destination file's last-modified time is also set from the source file's OS mtime.

**Usage:**

```bash
# Copy from default sources (Data1 2, Data1, Data2 under cwd)
python3 scripts/integrate_raw_data.py

# From Desktop: Data, Data1, Data2 — move (delete source) and keep ~100 samples on Desktop
python3 scripts/integrate_raw_data.py \
  --sources ~/Desktop/Data ~/Desktop/Data1 ~/Desktop/Data2 \
  --move \
  --samples-dir ~/Desktop/samples \
  --samples-n 100

# Dry-run (print what would be done, no writes/deletes)
python3 scripts/integrate_raw_data.py --sources ~/Desktop/Data --move --dry-run
```

**Options:**

- `--work-dir` — raw_data parent (default: `work_dir`)
- `--sources` — source folders: names under cwd or paths (e.g. `~/Desktop/Data`)
- `--move` — delete source file after copying (move)
- `--samples-dir` — copy ~N renamed samples here for verification (e.g. `~/Desktop/samples`)
- `--samples-n` — number of samples (default 100), spread evenly across sources

**Task:**

```bash
task integrate-raw      # run integration (copy only, default sources)
task integrate-raw-dry  # dry-run
```
