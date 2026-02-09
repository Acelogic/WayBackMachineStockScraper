# WayBack Machine Stock Scraper

Recover historical stock price data for **delisted tickers** by scraping archived Yahoo Finance pages from the Internet Archive's [Wayback Machine](https://web.archive.org/).

## The Problem

Free financial data APIs (Yahoo Finance, Stooq, Investing.com) remove delisted stocks from their databases. If a company was acquired, went bankrupt, or was taken private, its historical price data disappears. This creates gaps in backtests that rely on historical index compositions.

## The Solution

Two recovery strategies, tried in order:

1. **CSV endpoint** (best case): Before Yahoo killed their CSV download endpoint in 2017, the Wayback Machine archived many of these files. When available, this gives complete OHLCV history in one shot — often spanning the full lifetime of the company.

2. **HTML multi-snapshot stitching** (fallback): When no CSV archive exists, the scraper finds all archived snapshots of Yahoo Finance's historical prices page (`/q/hp?s=TICKER`). Each snapshot shows ~66 rows from a different time period. By downloading and merging multiple snapshots, the scraper stitches together hundreds of rows of coverage.

**Results from testing:**

| Ticker | Rows | Strategy | Date Range |
|--------|------|----------|------------|
| YHOO | 5,142 | CSV | 1996-04 to 2016-09 |
| JNPR | 651 | HTML stitch (11 snapshots) | 2003-09 to 2009-07 |
| SUNW | 639 | HTML stitch (16 snapshots) | 2003-07 to 2007-02 |
| XMSR | 623 | HTML stitch (11 snapshots) | 2003-08 to 2008-03 |
| APOL | 567 | HTML stitch (12 snapshots) | 2004-08 to 2009-02 |
| MEDI | 432 | HTML stitch (10 snapshots) | 2004-06 to 2007-05 |
| PIXR | 304 | HTML stitch (5 snapshots) | 2003-07 to 2005-11 |
| GENZ | 198 | HTML stitch (3 snapshots) | 2003-07 to 2004-08 |

## How It Works

### Strategy 1: CSV Endpoint
1. Queries the [Wayback CDX API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server) to find archived snapshots of `real-chart.finance.yahoo.com/table.csv?s=TICKER`
2. Tries multiple archived endpoints (`real-chart`, `ichart`, `chart`)
3. Selects the snapshot with the most data (largest file size)
4. Downloads and parses the archived CSV

### Strategy 2: HTML Multi-Snapshot Stitching
1. Queries CDX API for all archived snapshots of `finance.yahoo.com/q/hp?s=TICKER`
2. Downloads each snapshot (typically 8-28 archived pages per ticker)
3. Parses the `yfnc_tabledata1` HTML table — each page has ~66 rows of OHLCV data
4. Deduplicates by date and merges all snapshots into a single timeline
5. Handles Wayback Machine rate limiting with automatic retries and backoff

### Output
- Saves clean OHLCV data to `data/{TICKER}.csv`
- Tracks progress in `data/manifest.json` (crash-safe, saves after each ticker)
- Optionally merges recovered data into an existing price cache

## Installation

```bash
pip install pandas requests
```

No API keys required. No authentication. Just the Wayback Machine's public API.

## Usage

### Scrape specific tickers
```bash
python scraper.py YHOO SUNW CTXS WCOM
```

### Scrape from a file
```bash
python scraper.py --file tickers.txt
```

### Scrape all known NDX delisted tickers (51 tickers)
```bash
python scraper.py --all
```

### Custom output directory
```bash
python scraper.py YHOO --output-dir ./my_data
```

### Force re-scrape (skip cache check)
```bash
python scraper.py YHOO --force
```

### Adjust rate limiting (default 2s between requests)
```bash
python scraper.py --all --delay 5.0  # Be more conservative
```

### Merge into NDX simulation price cache
```bash
python scraper.py --merge --output-dir ./data
python scraper.py --merge --cache-path /path/to/prices_cache.pkl
```

## Output Format

Each ticker is saved as `data/{TICKER}.csv`:

```csv
Date,Open,High,Low,Close,Volume,Adj Close
2016-09-14,42.91,43.62,42.86,43.46,11617300,43.46
2016-09-13,43.19,43.52,42.69,43.04,10120800,43.04
...
1996-04-12,25.25,43.00,24.50,33.00,408720000,1.38
```

A `manifest.json` tracks what's been scraped:
```json
{
  "YHOO": {
    "rows": 5142,
    "start": "1996-04-12",
    "end": "2016-09-14",
    "columns": ["Date", "Open", "High", "Low", "Close", "Volume", "Adj Close"],
    "file": "YHOO.csv"
  }
}
```

## Progress Indicators

During HTML stitching, progress is shown with dot characters:
- `.` — snapshot fetched and parsed successfully
- `x` — page fetched but no table data found (newer Yahoo layout)
- `C` — connection error (Wayback rate limiting)
- `T` — timeout
- `R` — HTTP 429 rate limited, backing off
- `!` — unexpected error

## Known NDX Delisted Tickers

The scraper includes a built-in list of 51 delisted Nasdaq-100 tickers from the 2000-2010 era, sorted by weight impact:

| Ticker | Company | Fate |
|--------|---------|------|
| YHOO | Yahoo! Inc. | Acquired by Verizon 2017 |
| JNPR | Juniper Networks | Acquired by HPE 2025 |
| WCOM | WorldCom | Bankrupt 2002 |
| CTXS | Citrix Systems | Taken private 2022 |
| SUNW | Sun Microsystems | Acquired by Oracle 2010 |
| PIXR | Pixar | Acquired by Disney 2006 |
| XMSR | XM Satellite Radio | Merged with Sirius 2008 |
| ... | [44 more] | See `NDX_DELISTED_TICKERS` in scraper.py |

## Limitations

- **Wayback Machine coverage varies**: CSV archives give complete history but are rare (~5% of tickers). HTML stitching is more common (~50% of tickers) but gives partial coverage (typically 200-700 rows from a ~4-year window).
- **Rate limiting**: The Wayback Machine is a free public service. The scraper includes automatic retry/backoff logic, but aggressive scraping will result in temporary blocks. Use `--delay 5.0` or higher for large batches.
- **Snapshot age**: Data ends at the date of the last Wayback snapshot (typically 2004-2009 for HTML, 2014-2017 for CSV). This is fine for delisted stocks since they stopped trading before that.
- **Adjusted prices**: The `Adj Close` column reflects adjustments as of the snapshot date, not today. For stocks that were later acquired at a premium, the final adjustment may differ.

## Integration with NDX Simulation

This tool was built to fill data gaps in the [Testfol-MarginStresser](https://github.com/Acelogic/Testfol-MarginStresser) NDX simulation pipeline. The `--merge` flag directly updates the simulation's price cache:

```bash
# 1. Scrape all missing tickers
python scraper.py --all

# 2. Merge into the NDX simulation price cache
python scraper.py --merge
```

This improves early-period (2000-2010) data coverage, making the 25-year backtest significantly more accurate for periods when many Nasdaq-100 constituents have since been delisted.

## License

MIT
