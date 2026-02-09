"""
WayBack Machine Stock Scraper

Recovers historical stock price data for delisted tickers by scraping
archived Yahoo Finance CSV downloads from the Internet Archive's Wayback Machine.

The old Yahoo Finance endpoint (real-chart.finance.yahoo.com/table.csv) was
archived before Yahoo killed it in 2017. This scraper finds those snapshots
and extracts complete OHLCV + Adj Close data.

Usage:
    python scraper.py YHOO SUNW CTXS          # Fetch specific tickers
    python scraper.py --file tickers.txt       # Fetch from file (one per line)
    python scraper.py --all                    # Fetch all known NDX delisted tickers
    python scraper.py YHOO --output-dir ./data # Custom output directory
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# --- Configuration ---

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_FETCH_URL = "https://web.archive.org/web"

# Yahoo Finance CSV endpoints that were archived (try in order)
YAHOO_CSV_ENDPOINTS = [
    "real-chart.finance.yahoo.com/table.csv?s={ticker}",
    "ichart.finance.yahoo.com/table.csv?s={ticker}",
    "chart.finance.yahoo.com/table.csv?s={ticker}",
]

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "data"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
}

# Known delisted NDX tickers from the 2000-2010 era (sorted by weight impact)
NDX_DELISTED_TICKERS = [
    "YHOO", "JNPR", "WCOM", "APOL", "GLBC", "PMCS", "CEFT", "CTXS",
    "AMCC", "SDLI", "VSTR", "SIAL", "NVLS", "GMST", "NIHD", "NTLI",
    "CEPH", "QLGC", "APCC", "MERQ", "JOY", "FWLT", "XMSR", "PIXR",
    "IVGN", "SEPR", "MWW", "SEBL", "LINTA", "NOVL", "PDCO", "DISCA",
    "CDWC", "DISH", "ISIL", "CKFR", "BRCD", "ICOS", "HGSI", "RFMD",
    "WCRX", "CYTC", "PPDI", "RATL", "PDLI", "ATML", "ESRX", "GENZ",
    "SPLS", "MEDI", "SUNW",
]


def find_wayback_snapshot(ticker: str, endpoint_template: str) -> str | None:
    """Query the Wayback Machine CDX API to find the best archived snapshot."""
    url = endpoint_template.format(ticker=ticker)
    params = {
        "url": url,
        "output": "json",
        "limit": 10,
        "filter": "statuscode:200",
        "sort": "closest",
        "order": "desc",  # Latest snapshots first (most complete data)
    }

    try:
        r = requests.get(WAYBACK_CDX_URL, params=params, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None

        data = r.json()
        if len(data) <= 1:  # First row is header
            return None

        # Pick the snapshot with the largest file size (most complete)
        best = max(data[1:], key=lambda row: int(row[6]) if row[6].isdigit() else 0)
        timestamp = best[1]
        original_url = best[2]

        return f"{WAYBACK_FETCH_URL}/{timestamp}/{original_url}"
    except Exception:
        return None


def fetch_ticker_data(ticker: str, retries: int = 2) -> pd.DataFrame | None:
    """
    Fetch historical price data for a ticker from Wayback Machine.

    Tries multiple archived Yahoo Finance endpoints and returns the
    result with the most data points.
    """
    best_df = None
    best_url = None

    for endpoint in YAHOO_CSV_ENDPOINTS:
        snapshot_url = find_wayback_snapshot(ticker, endpoint)
        if not snapshot_url:
            continue

        for attempt in range(retries + 1):
            try:
                r = requests.get(snapshot_url, headers=HEADERS, timeout=60)
                if r.status_code != 200:
                    continue

                df = pd.read_csv(io.StringIO(r.text))

                # Validate structure
                required_cols = {"Date", "Close"}
                if not required_cols.issubset(set(df.columns)):
                    continue

                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df = df.dropna(subset=["Date"])
                df = df.sort_values("Date").reset_index(drop=True)

                if best_df is None or len(df) > len(best_df):
                    best_df = df
                    best_url = snapshot_url

                break  # Success, no need to retry
            except requests.exceptions.Timeout:
                if attempt < retries:
                    time.sleep(5 * (attempt + 1))
                continue
            except Exception:
                break

        time.sleep(1)  # Rate limit between endpoints

    if best_df is not None:
        print(f"  {ticker}: {len(best_df)} rows "
              f"({best_df['Date'].iloc[0].date()} to {best_df['Date'].iloc[-1].date()})")
    else:
        print(f"  {ticker}: not found on Wayback Machine")

    return best_df


def save_ticker(ticker: str, df: pd.DataFrame, output_dir: Path) -> Path:
    """Save ticker data to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{ticker}.csv"
    df.to_csv(path, index=False)
    return path


def load_manifest(output_dir: Path) -> dict:
    """Load existing manifest of previously scraped tickers."""
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        import json
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict, output_dir: Path):
    """Save manifest of scraped tickers."""
    import json
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)


def scrape_tickers(
    tickers: list[str],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    skip_existing: bool = True,
    delay: float = 2.0,
) -> dict:
    """
    Scrape historical data for a list of tickers.

    Returns a summary dict with results per ticker.
    """
    manifest = load_manifest(output_dir)
    results = {"found": [], "not_found": [], "skipped": []}

    print(f"Scraping {len(tickers)} tickers from Wayback Machine...")
    print(f"Output: {output_dir.resolve()}\n")

    for i, ticker in enumerate(tickers):
        ticker = ticker.upper().strip()
        if not ticker:
            continue

        # Skip if already scraped
        if skip_existing and ticker in manifest:
            existing_path = output_dir / f"{ticker}.csv"
            if existing_path.exists():
                print(f"  {ticker}: skipping (already scraped, {manifest[ticker].get('rows', '?')} rows)")
                results["skipped"].append(ticker)
                continue

        df = fetch_ticker_data(ticker)

        if df is not None and not df.empty:
            path = save_ticker(ticker, df, output_dir)
            manifest[ticker] = {
                "rows": len(df),
                "start": str(df["Date"].iloc[0].date()),
                "end": str(df["Date"].iloc[-1].date()),
                "columns": df.columns.tolist(),
                "file": str(path.name),
            }
            results["found"].append(ticker)
        else:
            manifest[ticker] = {"rows": 0, "error": "not found"}
            results["not_found"].append(ticker)

        # Save manifest after each ticker (crash-safe)
        save_manifest(manifest, output_dir)

        # Rate limiting
        if i < len(tickers) - 1:
            time.sleep(delay)

    # Summary
    print(f"\n{'='*50}")
    print(f"Results: {len(results['found'])} found, "
          f"{len(results['not_found'])} not found, "
          f"{len(results['skipped'])} skipped")

    if results["found"]:
        print(f"\nRecovered data:")
        for ticker in results["found"]:
            info = manifest[ticker]
            print(f"  {ticker}: {info['rows']} rows ({info['start']} to {info['end']})")

    if results["not_found"]:
        print(f"\nNot available on Wayback:")
        print(f"  {', '.join(results['not_found'])}")

    return results


def merge_to_cache(
    data_dir: Path,
    cache_path: str | None = None,
    tickers: list[str] | None = None,
) -> int:
    """
    Merge scraped CSV files into an existing price cache (pickle).

    This integrates recovered data back into the NDX simulation pipeline.
    Returns the number of tickers merged.
    """
    import pickle

    if cache_path is None:
        # Default: NDX simulation price cache
        cache_path = os.path.expanduser(
            "~/Developer/Testfol-MarginStresser/data/ndx_simulation/data/cache/prices_cache.pkl"
        )

    if not os.path.exists(cache_path):
        print(f"Cache not found: {cache_path}")
        return 0

    with open(cache_path, "rb") as f:
        cache_df = pickle.load(f)

    print(f"Existing cache: {cache_df.shape[0]} rows x {cache_df.shape[1]} tickers")

    csv_files = sorted(data_dir.glob("*.csv"))
    if tickers:
        csv_files = [f for f in csv_files if f.stem in [t.upper() for t in tickers]]

    merged_count = 0
    for csv_path in csv_files:
        ticker = csv_path.stem.upper()
        if ticker == "MANIFEST":
            continue

        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")

        # Use Adj Close if available, otherwise Close
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        series = df[price_col].dropna()

        if series.empty:
            continue

        # Add or update the ticker in the cache
        if ticker in cache_df.columns:
            # Fill gaps only — don't overwrite existing data
            existing = cache_df[ticker]
            missing_mask = existing.isna()
            overlap = missing_mask.index.intersection(series.index)
            if len(overlap) > 0:
                filled = missing_mask.loc[overlap] & series.reindex(overlap).notna()
                if filled.any():
                    cache_df.loc[filled[filled].index, ticker] = series.reindex(filled[filled].index)
                    print(f"  {ticker}: filled {filled.sum()} gaps in existing data")
                    merged_count += 1
                else:
                    print(f"  {ticker}: already complete, no gaps to fill")
            else:
                print(f"  {ticker}: no overlapping dates to fill")
        else:
            # New ticker — add to cache
            aligned = series.reindex(cache_df.index)
            cache_df[ticker] = aligned
            non_null = aligned.notna().sum()
            print(f"  {ticker}: added ({non_null} data points)")
            merged_count += 1

    if merged_count > 0:
        with open(cache_path, "wb") as f:
            pickle.dump(cache_df, f)
        print(f"\nSaved updated cache: {cache_df.shape[0]} rows x {cache_df.shape[1]} tickers")
    else:
        print("\nNo changes to merge.")

    return merged_count


def main():
    parser = argparse.ArgumentParser(
        description="Recover historical stock prices for delisted tickers via Wayback Machine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("tickers", nargs="*", help="Ticker symbols to scrape")
    parser.add_argument("--file", "-f", help="File with tickers (one per line)")
    parser.add_argument("--all", action="store_true", help="Scrape all known NDX delisted tickers")
    parser.add_argument("--output-dir", "-o", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--delay", "-d", type=float, default=2.0, help="Delay between requests (seconds)")
    parser.add_argument("--force", action="store_true", help="Re-scrape even if already cached")
    parser.add_argument(
        "--merge", action="store_true",
        help="Merge scraped data into NDX simulation price cache"
    )
    parser.add_argument("--cache-path", help="Path to price cache pickle (for --merge)")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Handle --merge mode
    if args.merge:
        tickers = args.tickers if args.tickers else None
        merge_to_cache(output_dir, args.cache_path, tickers)
        return

    # Collect tickers
    tickers = list(args.tickers) if args.tickers else []

    if args.file:
        with open(args.file) as f:
            tickers.extend(line.strip() for line in f if line.strip())

    if args.all:
        tickers.extend(NDX_DELISTED_TICKERS)

    # Deduplicate while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        t = t.upper().strip()
        if t and t not in seen:
            seen.add(t)
            unique_tickers.append(t)

    if not unique_tickers:
        parser.print_help()
        print("\nError: No tickers specified. Use positional args, --file, or --all.")
        sys.exit(1)

    scrape_tickers(
        unique_tickers,
        output_dir=output_dir,
        skip_existing=not args.force,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
