"""Gas price data sources: EIA weekly retail prices, user CSV uploads, and bundled sample data."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
HISTORY_START = "2019-01-01"


@dataclass(frozen=True)
class Area:
    name: str
    eia_code: str
    region: str  # "california", "west_coast" or "us" - decides which regional events apply
    news_query: str
    proxy_note: str | None = None  # set when EIA has no series for the area itself


AREAS: dict[str, Area] = {
    a.name: a
    for a in [
        Area(
            "Sacramento, CA",
            "SCA",
            "california",
            "Sacramento",
            "EIA does not publish a Sacramento series, so the California statewide average is used. "
            "Sacramento usually runs a little above the state average; use the local adjustment "
            "in the sidebar or upload local prices to correct for it.",
        ),
        Area("California", "SCA", "california", "California"),
        Area("San Francisco, CA", "Y05SF", "california", "San Francisco"),
        Area("Los Angeles, CA", "Y05LA", "california", "Los Angeles"),
        Area("West Coast (PADD 5)", "R50", "west_coast", "West Coast"),
        Area("Seattle, WA", "Y48SE", "west_coast", "Seattle"),
        Area("Washington State", "SWA", "west_coast", "Washington state"),
        Area("Denver, CO", "YDEN", "us", "Denver"),
        Area("Colorado", "SCO", "us", "Colorado"),
        Area("Houston, TX", "Y44HO", "us", "Houston"),
        Area("Texas", "STX", "us", "Texas"),
        Area("Chicago, IL", "YORD", "us", "Chicago"),
        Area("Miami, FL", "YMIA", "us", "Miami"),
        Area("Florida", "SFL", "us", "Florida"),
        Area("New York City, NY", "Y35NY", "us", "New York City"),
        Area("New York State", "SNY", "us", "New York"),
        Area("Boston, MA", "YBOS", "us", "Boston"),
        Area("Cleveland, OH", "YCLE", "us", "Cleveland"),
        Area("United States", "NUS", "us", "US"),
    ]
}
DEFAULT_AREA = "Sacramento, CA"

GRADES = {
    "Regular": "EPMR",
    "Midgrade": "EPMM",
    "Premium": "EPMP",
    "Diesel": "EPD2D",
}


class DataSourceError(RuntimeError):
    pass


def fetch_eia(api_key: str, area_code: str, product: str, start: str = HISTORY_START) -> pd.Series:
    """Weekly retail prices ($/gal) from the EIA v2 API, indexed by week date."""
    params = [
        ("api_key", api_key),
        ("frequency", "weekly"),
        ("data[0]", "value"),
        ("facets[duoarea][]", area_code),
        ("facets[product][]", product),
        ("start", start),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("length", "5000"),
    ]
    try:
        resp = requests.get(EIA_URL, params=params, timeout=20)
        resp.raise_for_status()
        rows = resp.json()["response"]["data"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise DataSourceError(f"EIA request failed: {exc}") from exc
    if not rows:
        raise DataSourceError("EIA returned no data for this area and grade.")
    df = pd.DataFrame(rows)
    series = pd.Series(
        pd.to_numeric(df["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(df["period"]),
        name="price",
    )
    return _clean(series)


def parse_uploaded_csv(raw: bytes) -> pd.Series:
    """Parse a user CSV with a date column and a price column (names are matched loosely)."""
    df = pd.read_csv(io.BytesIO(raw))
    cols = {c.lower().strip(): c for c in df.columns}
    date_col = next((cols[c] for c in cols if c in ("date", "week", "period", "day")), df.columns[0])
    price_col = next(
        (cols[c] for c in cols if any(k in c for k in ("price", "value", "regular", "usd"))),
        df.columns[1] if len(df.columns) > 1 else None,
    )
    if price_col is None or price_col == date_col:
        raise DataSourceError("CSV needs a date column and a price column.")
    series = pd.Series(
        pd.to_numeric(df[price_col].astype(str).str.replace("$", "", regex=False), errors="coerce").to_numpy(),
        index=pd.to_datetime(df[date_col], errors="coerce"),
        name="price",
    )
    series = _clean(series[series.index.notna()])
    if len(series) < 8:
        raise DataSourceError("CSV needs at least 8 dated price rows.")
    # Resample daily/irregular data to weekly (Monday) averages so it lines up with the forecast model.
    return series.resample("W-MON").mean().interpolate().rename("price")


def _clean(series: pd.Series) -> pd.Series:
    series = series.dropna()
    series = series[series > 0]
    return series[~series.index.duplicated(keep="last")].sort_index()


# Approximate California regular-gasoline levels ($/gal) at points in time. Used only when no
# live data source is available, and always labeled "sample" in the UI. Recent anchors follow
# figures reported in the news (e.g. $5.16 on 2026-03-08, ~$6.15 in May 2026, >$6 in Sept 2026).
_SAMPLE_ANCHORS = [
    ("2019-01-07", 3.30), ("2019-05-06", 4.10), ("2019-10-14", 4.15), ("2020-02-03", 3.60),
    ("2020-04-27", 2.95), ("2020-09-07", 3.25), ("2021-01-04", 3.35), ("2021-06-07", 4.20),
    ("2021-11-15", 4.70), ("2022-02-21", 4.75), ("2022-03-14", 5.80), ("2022-06-13", 6.44),
    ("2022-08-29", 5.35), ("2022-10-10", 6.42), ("2022-12-26", 4.60), ("2023-03-06", 4.85),
    ("2023-06-19", 4.85), ("2023-09-25", 6.05), ("2023-12-25", 4.75), ("2024-04-15", 5.45),
    ("2024-07-15", 4.85), ("2024-10-07", 5.00), ("2024-12-30", 4.35), ("2025-03-10", 4.55),
    ("2025-06-23", 4.75), ("2025-09-01", 4.60), ("2025-10-20", 4.85), ("2025-12-15", 4.45),
    ("2026-01-19", 4.40), ("2026-02-23", 4.55), ("2026-03-09", 5.16), ("2026-04-06", 5.95),
    ("2026-04-20", 5.75), ("2026-05-18", 6.15), ("2026-06-22", 5.65), ("2026-07-06", 5.55),
    ("2026-07-20", 5.80), ("2026-08-24", 5.70), ("2026-09-14", 5.72), ("2026-09-21", 6.02),
]


def sample_series() -> pd.Series:
    """Weekly sample series for California regular gasoline, interpolated between anchors."""
    anchors = pd.Series(
        [p for _, p in _SAMPLE_ANCHORS], index=pd.to_datetime([d for d, _ in _SAMPLE_ANCHORS])
    )
    weeks = pd.date_range(anchors.index[0], anchors.index[-1], freq="W-MON")
    series = anchors.reindex(anchors.index.union(weeks)).interpolate(method="time").reindex(weeks)
    rng = np.random.default_rng(7)  # fixed seed: sample data is the same on every run
    wiggle = rng.normal(0, 0.025, len(series))
    wiggle[-1] = 0  # keep the latest anchor exact
    return (series + wiggle).round(3).rename("price")


def slice_window(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return series[(series.index >= start) & (series.index <= end)]


def aggregate(series: pd.Series, resolution: str) -> pd.Series:
    if resolution == "Monthly":
        monthly = series.resample("MS").mean().dropna()
        return monthly.rename("price")
    return series
