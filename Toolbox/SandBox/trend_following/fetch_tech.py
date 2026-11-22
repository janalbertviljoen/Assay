"""Fetch the series of design.md, "Second test", through the market_data Yahoo source.

Usage (repository root):
``.venv/bin/python -m Toolbox.SandBox.trend_following.fetch_tech data 2026-11-22``

Uses its own snapshot root (``<data_dir>/raw/trend_tech``) so that it never reuses the
main pipeline's snapshots, which start in 2006; writes the parsed daily prices to
``<data_dir>/interim/trend_tech/<as_of>/prices.parquet``.
"""

import sys
import tomllib
from datetime import date
from pathlib import Path

from Toolbox.market_data.sources.prices import YahooChart, load_chart, yahoo_client
from Toolbox.skatkis.io.snapshots import SnapshotStore

TICKERS = ["QQQ", "XLK", "NVDA", "SPY"]
START = date(1993, 1, 1)  # before the first of them (SPY, 1993-01)

data_dir = Path(sys.argv[1])
as_of = date.fromisoformat(sys.argv[2])
settings = tomllib.loads(Path("config/market_data.toml").read_text())["sources"][
    "yahoo"
]
client = yahoo_client(
    max_requests_per_second=settings["max_requests_per_second"],
    timeout_seconds=settings["timeout_seconds"],
    max_retries=settings["max_retries"],
    backoff_seconds=settings["backoff_seconds"],
)
tables = load_chart(
    TICKERS,
    provider=YahooChart(client, START),
    store=SnapshotStore(data_dir / "raw" / "trend_tech"),
    as_of=as_of,
)
out = data_dir / "interim" / "trend_tech" / as_of.isoformat()
out.mkdir(parents=True, exist_ok=True)
tables.prices.to_parquet(out / "prices.parquet")
for t, g in tables.prices.groupby("symbol"):
    print(
        f"{t:5} {g['date'].min():%Y-%m-%d} .. {g['date'].max():%Y-%m-%d}  {len(g)} days"
    )
