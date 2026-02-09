# WayBack Machine Stock Scraper

Recover historical stock price data for **delisted tickers** by scraping archived Yahoo Finance CSV downloads from the Internet Archive's [Wayback Machine](https://web.archive.org/).

## The Problem

Free financial data APIs (Yahoo Finance, Stooq, Investing.com) remove delisted stocks from their databases. If a company was acquired, went bankrupt, or was taken private, its historical price data disappears. This creates gaps in backtests that rely on historical index compositions.

## The Solution

Before Yahoo killed their CSV download endpoint in 2017, the Wayback Machine archived many of these files. This scraper finds those snapshots and extracts complete OHLCV + Adjusted Close data — often spanning the **full lifetime** of the company.

**Proof of concept:** Yahoo (YHOO) — 5,142 rows from IPO (1996) through delisting (2016), recovered from a single Wayback snapshot.

## How It Works

1. Queries the [Wayback CDX API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server) to find archived snapshots of `real-chart.finance.yahoo.com/table.csv?s=TICKER`
2. Selects the snapshot with the most data (largest file size)
3. Downloads and parses the archived CSV
4. Saves clean OHLCV data to `data/{TICKER}.csv`
5. Optionally merges recovered data into an existing price cache

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
| ... | [48 more] | See `NDX_DELISTED_TICKERS` in scraper.py |

## Limitations

- **Wayback Machine availability**: Not all tickers were archived. Coverage depends on whether someone/something crawled the Yahoo Finance CSV endpoint for that specific ticker before 2017.
- **Rate limiting**: The Wayback Machine is a free public service. The scraper includes configurable delays (default 2s) between requests. Be respectful.
- **Snapshot age**: Data ends at the date of the last Wayback snapshot (typically 2014-2017), not present day. This is fine for delisted stocks since they stopped trading before that.
- **Adjusted prices**: The `Adj Close` column reflects adjustments as of the snapshot date, not today. For stocks that were later acquired at a premium, the final adjustment may differ from what Yahoo would show today (if they still had the data).

## Integration with NDX Simulation

This tool was built to fill data gaps in the [Testfol-MarginStresser](https://github.com/Acelogic/Testfol-MarginStresser) NDX simulation pipeline. The `--merge` flag directly updates the simulation's price cache:

```bash
# 1. Scrape all missing tickers
python scraper.py --all

# 2. Merge into the NDX simulation price cache
python scraper.py --merge
```

This can improve early-period (2000-2010) coverage from ~80% to potentially 90%+, making the 25-year backtest significantly more accurate.

## License

MIT
