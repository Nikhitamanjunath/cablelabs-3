# CSV Data Structure and How the Heatmap Is Built

This document explains the CSV files produced by the transform and exactly how notebook 5 uses them to create the airtime utilization (AU) heatmap.

---

## Part 1: Where the CSVs Come From

1. **Raw data** lives in Parquet files under `work_dir/raw_data/`. Each file has columns like `timestamp`, `freqs`, `trace_max` — one row per measurement (a time and a frequency where the scanner saw activity above a power threshold).

2. **The transform** (`transform/transform.py`) reads those Parquet files and, for each **(date, hour, frequency band)**:
   - Splits the band into **frequency channels** (e.g. 20 MHz wide).
   - For each channel, computes **Airtime Utilization (AU)** for that hour: “what percent of the hour had at least one detection in this channel?”
   - Writes:
     - **One Data CSV** per (date, hour, band, power threshold) — contains the AU values and extra rows for occupancy-over-time (we only use row 0 for the heatmap).
     - **One Legend CSV** per (date, hour, band) — lists each channel’s frequency range in Hz. Same for all power thresholds for that hour/band.

3. **Notebook 5** then reads only the Data and Legend CSVs (not the Parquet files) to build the heatmap.

---

## Part 2: The Two Kinds of CSVs (With Your Real Files)

There are **no column headers** in these CSVs — everything is numbers.

---

### A. Data CSV (Channel Occupancy)

**Path pattern:** `work_dir/csvs/channel_occupancy/Data_YYYY_MM_DD_HH_<band>_<pow>dBm.csv`  
Example: `Data_2026_02_01_00_539MHz_85dBm.csv` = Feb 1, 2026, hour 00 (midnight), band 539 MHz, power threshold −85 dBm.

**Row 0 is special — the “summary row” used for the heatmap:**

| Column index | Meaning | Example (539 MHz) | Example (3765 MHz) |
|-------------|---------|-------------------|--------------------|
| 0 | Year | 2026.0 | 2026.0 |
| 1 | Month | 2.0 | 2.0 |
| 2 | Day | 1.0 | 1.0 |
| 3 | Hour (0–23) | 0.0 | 0.0 |
| 4 | Start of hour (Unix time) | 1769904000.0 | 1769904000.0 |
| 5 | **AU % for channel 1** | 0.5758… | 7.307… |
| 6 | **AU % for channel 2** | *(none; only 1 channel)* | 8.076… |
| … | **AU % for channel 3, 4, …** | … | … |
| 5 + N − 1 | **AU % for channel N** | — | 2.884… |
| 5 + N | Denominator (number of time samples) | 521.0 | 520.0 |

So:
- **First 5 columns** = date/time metadata.
- **Next N columns (indices 5 through 5+N−1)** = one AU percentage per frequency channel for that hour. That’s the only part the heatmap uses from the Data CSV.
- **Last column** = denominator (used when computing AU in the transform; the heatmap ignores it).

**Real examples:**

**539 MHz (1 channel) — `Data_2026_02_01_00_539MHz_85dBm.csv` row 0:**
```
2026.0, 2.0, 1.0, 0.0, 1769904000.0, 0.5758157389635317, 521.0
```
So: 2026-02-01, hour 0, **one** AU value = 0.576% (column 5), denominator 521.

**3765 MHz (12 channels) — `Data_2026_02_01_00_3765MHz_85dBm.csv` row 0:**
```
2026.0, 2.0, 1.0, 0.0, 1769904000.0, 7.307..., 8.076..., 2.307..., 1.153..., 4.230..., 0.576..., 0.769..., 0.0, 38.84..., 4.423..., 7.115..., 2.884..., 520.0
```
So: 2026-02-01, hour 0, **12** AU values in columns 5–16 (e.g. 7.3%, 8.0%, …, 38.8%, …, 2.88%), then 520.

**Rows 1, 2, 3, …** in the Data CSV are different: they describe “channel occupancy over time” (one time bin per row, 0/1 per channel). The heatmap **does not use these rows**; it uses **only row 0** and only the AU columns (5 to 5+N−1).

---

### B. Legend CSV (Frequency Ranges)

**Path pattern:** `work_dir/csvs/frequency_legends/Legend_YYYY_MM_DD_HH_<band>.csv`  
Example: `Legend_2026_02_01_00_539MHz.csv`.

**Every row = one frequency channel.** Columns:

| Column index | Meaning | Units |
|-------------|---------|--------|
| 0 | Channel number (1, 2, 3, …) | — |
| 1 | Channel start frequency | Hz |
| 2 | Channel end frequency | Hz |

From that we get **center frequency** = (start + end) / 2. For the heatmap we convert to GHz: center_Hz / 1e9.

**Real examples:**

**539 MHz (1 channel) — `Legend_2026_02_01_00_539MHz.csv`:**
```
1.0, 480000000.0, 500000000.0
```
One channel: 480–500 MHz → center 490 MHz = **0.49 GHz**.

**3765 MHz (12 channels) — `Legend_2026_02_01_00_3765MHz.csv`:**
```
1.0, 3700000000.0, 3720000000.0   → center 3.71 GHz
2.0, 3720000000.0, 3740000000.0   → center 3.73 GHz
...
12.0, 3920000000.0, 3940000000.0  → center 3.93 GHz
```
So we get 12 center frequencies: 3.71, 3.73, …, 3.93 GHz. These become the **x-axis** of the heatmap.

---

## Part 3: How the Heatmap Is Built (Step by Step)

You pick a **date** (e.g. `2026-02-01`) and a **band** (e.g. `3765MHz`).

### Step 1: Find all Data files for that date and band

The notebook looks for files like:
`Data_2026_02_01_*_3765MHz_*.csv`  
Each filename encodes the **hour** (e.g. `Data_2026_02_01_00_3765MHz_85dBm.csv` = hour 0, `Data_2026_02_01_14_3765MHz_85dBm.csv` = hour 14). So you get one “row” of the heatmap per hour that has data.

### Step 2: For each Data file (each hour)

1. Open the CSV, **read only row 0**.
2. Compute **N** = number of AU values:  
   `N = (number of columns in row 0) − 6`  
   (6 = year, month, day, hour, ts_start, denominator).
3. The **AU values for that hour** are:  
   `row0[5], row0[6], …, row0[5+N−1]`.  
   So we have one number per frequency channel for this hour.

### Step 3: Get frequency labels (x-axis) from the Legend

For that same (date, hour, band), open the Legend CSV, e.g.  
`Legend_2026_02_01_00_3765MHz.csv`.  
For each row:  
`center_Hz = (column1 + column2) / 2`  
`center_GHz = center_Hz / 1e9`.  
The notebook assumes the channel layout is the same for every hour in that band, so it typically uses the first Legend it finds and gets a list like `[3.71, 3.73, …, 3.93]` (GHz). That list is the **x-axis**: one position per channel.

### Step 4: Build the matrix

- **Rows** = hours (0, 1, 2, …), sorted.
- **Columns** = channels (same order as in the Data and Legend).
- **Cell (i, j)** = AU % for hour i, channel j = the j-th AU value from row 0 of the Data file for hour i.

Example for 3765 MHz on 2026-02-01 with hours 0 and 1:

|            | Ch1 (3.71 GHz) | Ch2 (3.73 GHz) | … | Ch12 (3.93 GHz) |
|------------|-----------------|-----------------|---|-----------------|
| **00:00**  | 7.31            | 8.08            | … | 2.88            |
| **01:00**  | *(from Data_…_01_… row 0)* | … | … | … |

So the matrix is literally “hour × channel” and each cell is one AU percentage.

### Step 5: Draw the heatmap

- **X-axis:** the list of center frequencies in GHz (from the Legend).
- **Y-axis:** time labels like "00:00", "01:00", … (one per hour in the matrix).
- **Color:** the matrix value (AU %) — e.g. 0 = dark, 38.8 = bright.

Plotly’s `go.Heatmap(x=freq_centers_ghz, y=hour_labels, z=matrix, ...)` does exactly that: one rectangle per (frequency, hour), colored by the AU value. The hover tooltip shows that same (freq, time, AU %) for the cell under the mouse.

---

## Part 4: Short Summary

| What | Where | Used for heatmap? |
|------|--------|--------------------|
| **Data CSV row 0, cols 0–4** | Date/hour/Unix time | Only to know which hour; AU comes from later columns. |
| **Data CSV row 0, cols 5…5+N−1** | AU % per channel for that hour | **Yes** — these become one row of the heatmap. |
| **Data CSV row 0, last col** | Denominator | No. |
| **Data CSV rows 1+** | Occupancy over time (0/1 per channel per time bin) | No. |
| **Legend CSV** | Start/end Hz per channel | **Yes** — converted to center GHz for the x-axis. |

So: **one Data file per hour** gives **one row** of the heatmap (the AU values for that hour). The **Legend** gives the **column** labels (frequency in GHz). Together they form the (hour × channel) AU matrix that the heatmap displays.
