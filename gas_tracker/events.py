"""Newsworthy events that moved gas prices, plus live headlines from Google News."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import pandas as pd
import requests


@dataclass(frozen=True)
class Event:
    date: str
    title: str
    description: str
    impact: str  # "up" or "down": the direction the event pushed pump prices
    scope: str  # "global", "us", "west_coast" or "california"
    category: str
    source: str | None = None

    @property
    def timestamp(self) -> pd.Timestamp:
        return pd.Timestamp(self.date)


# Curated timeline. Dates are when the news broke; pump prices usually react over the following
# days to weeks. Keep entries factual and add a source link when adding new ones.
EVENTS: list[Event] = [
    Event("2020-03-09", "COVID-19 demand collapse and Saudi-Russia price war",
          "Lockdowns cut driving while OPEC+ talks collapsed; crude briefly went negative in April 2020.",
          "down", "global", "Demand"),
    Event("2020-04-12", "OPEC+ agrees record 9.7M bbl/day output cut",
          "Producers cut output to stabilise the market, setting up the 2020-21 price recovery.",
          "up", "global", "Supply"),
    Event("2022-02-24", "Russia invades Ukraine",
          "Sanctions fears sent Brent above $120; California hit its first $5.50+ averages within weeks.",
          "up", "global", "Geopolitics"),
    Event("2022-06-13", "California average hits record ~$6.44",
          "Post-invasion crude prices plus peak summer demand pushed the state average to an all-time high.",
          "up", "california", "Milestone"),
    Event("2022-10-05", "OPEC+ announces 2M bbl/day cut; CA refinery outages",
          "Output cut coincided with unplanned West Coast refinery maintenance, sending CA prices back above $6.",
          "up", "california", "Supply"),
    Event("2023-03-28", "California SB X1-2 signed (refiner price-gouging law)",
          "Created the Division of Petroleum Market Oversight to monitor refiner margins.",
          "down", "california", "Policy"),
    Event("2023-04-02", "Surprise OPEC+ production cut",
          "Saudi Arabia and allies announced ~1.16M bbl/day of voluntary cuts.",
          "up", "global", "Supply"),
    Event("2023-09-18", "California refinery outages drive fall spike",
          "Low inventories and refinery issues pushed CA averages back near $6 in late September.",
          "up", "california", "Supply"),
    Event("2024-10-14", "California AB X2-1 signed (refinery inventory rules)",
          "Lets the state require minimum fuel inventories to cushion refinery outages.",
          "down", "california", "Policy"),
    Event("2024-10-16", "Phillips 66 announces Los Angeles refinery closure",
          "The ~139k bbl/day Wilmington refinery was slated to close in late 2025.",
          "up", "california", "Refining",
          "https://www.eia.gov/todayinenergy/detail.php?id=65704"),
    Event("2025-04-16", "Valero announces Benicia refinery closure",
          "The ~145k bbl/day Bay Area refinery (a key Northern California supplier) set to close in 2026.",
          "up", "california", "Refining",
          "https://www.ogj.com/refining-processing/refining/operations/article/55284361/valero-to-shutter-at-least-one-of-its-california-refineries"),
    Event("2025-06-13", "Israel strikes Iran; oil spikes",
          "Crude jumped on fears of disruption in the Strait of Hormuz before a ceasefire on June 24.",
          "up", "global", "Geopolitics"),
    Event("2025-06-24", "Israel-Iran ceasefire calms oil markets",
          "Crude gave back its war premium within days.",
          "down", "global", "Geopolitics",
          "https://www.aljazeera.com/economy/2025/6/24/fragile-iran-israel-ceasefire-calms-oil-markets"),
    Event("2025-10-17", "Phillips 66 Wilmington refinery shuts down",
          "Roughly 8% of California's refining capacity goes offline, tightening in-state supply.",
          "up", "california", "Refining",
          "https://californiaglobe.com/articles/valero-shut-down-benicia-refinery-jan-31st-ca-gas-prices-already-climbing/"),
    Event("2026-01-31", "Valero begins shutting Benicia refinery",
          "Closure moved up from April; together with Wilmington, nearly 20% of in-state capacity is lost. "
          "Northern California (including Sacramento) relies more on imported gasoline.",
          "up", "california", "Refining",
          "https://californiaglobe.com/articles/valero-shut-down-benicia-refinery-jan-31st-ca-gas-prices-already-climbing/"),
    Event("2026-02-28", "US and Israel strike Iran; war begins",
          "Traffic through the Strait of Hormuz (over 20% of world oil trade) is restricted; "
          "Brent posts its biggest weekly gain since 2020.",
          "up", "global", "Geopolitics",
          "https://www.cbsnews.com/live-updates/iran-war-us-strait-of-hormuz-oil-gas-price-strikes/"),
    Event("2026-03-08", "California average reaches $5.16",
          "State average sits about $1.66 above the national average as crude climbs.",
          "up", "california", "Milestone",
          "https://lodi411.com/lodi-eye/california-fuel-price-projections-amp-analysis-2026"),
    Event("2026-04-07", "US-Iran two-week ceasefire",
          "Brent fell ~13% in a day, its largest one-day drop since 1991, on hopes Hormuz would reopen.",
          "down", "global", "Geopolitics",
          "https://euronews.com/2026/04/08/iran-ceasefire-pushes-oil-prices-down-as-markets-remain-cautious"),
    Event("2026-05-15", "California averages ~$6.15, highest in the nation",
          "Refinery closures plus the war premium keep California prices above $6.",
          "up", "california", "Milestone",
          "https://calmatters.org/environment/2026/05/california-gas-prices-six-weeks/"),
    Event("2026-06-17", "Peace-framework hopes push oil lower",
          "Brent slid to ~$78, its lowest since early March, as a US-Iran memorandum took shape.",
          "down", "global", "Geopolitics",
          "https://www.aljazeera.com/economy/2026/6/17/oil-prices-continue-slide-amid-hopes-for-peace-opening-of-strait-of-hormuz"),
    Event("2026-07-08", "US renews strikes on Iran",
          "Attacks on shipping resume and oil reverses its return toward pre-war prices.",
          "up", "global", "Geopolitics",
          "https://www.aljazeera.com/news/2026/7/8/oil-prices-surge-as-us-strikes-iran-reversing-fall-to-pre-war-levels"),
    Event("2026-09-07", "Strikes intensify in the Strait of Hormuz",
          "Brent climbs toward ~$97 a barrel on escalation fears.",
          "up", "global", "Geopolitics",
          "https://www.aljazeera.com/economy/2026/9/7/oil-prices-surge-as-us-iran-strikes-intensify-in-strait-of-hormuz"),
    Event("2026-09-18", "AAA: California average tops $6 a gallon",
          "Sacramento runs above the state average.",
          "up", "california", "Milestone",
          "https://www.westsacramentosun.com/2026/09/18/584169/california-gas-average-tops-6-a-gallon"),
]


def _seasonal_events(start_year: int, end_year: int) -> list[Event]:
    """Recurring California events: blend switches and the July 1 excise-tax adjustment."""
    out = []
    for year in range(start_year, end_year + 1):
        out.append(Event(f"{year}-04-01", "Summer-blend gasoline season",
                         "Cleaner-burning, costlier summer fuel is phased in each spring as driving demand rises.",
                         "up", "california", "Seasonal"))
        out.append(Event(f"{year}-07-01", "California gas excise tax inflation adjustment",
                         "The state excise tax rises with inflation every July 1.",
                         "up", "california", "Policy"))
        out.append(Event(f"{year}-11-01", "Winter-blend gasoline season",
                         "Cheaper winter blend is allowed and demand eases, typically lowering prices.",
                         "down", "california", "Seasonal"))
    return out


REGION_SCOPES = {
    "california": {"global", "us", "west_coast", "california"},
    "west_coast": {"global", "us", "west_coast"},
    "us": {"global", "us"},
}


def events_for(region: str, start: pd.Timestamp, end: pd.Timestamp, include_seasonal: bool = True) -> list[Event]:
    scopes = REGION_SCOPES.get(region, {"global", "us"})
    pool = list(EVENTS)
    if include_seasonal:
        pool += _seasonal_events(start.year, end.year)
    picked = [e for e in pool if e.scope in scopes and start <= e.timestamp <= end]
    return sorted(picked, key=lambda e: e.timestamp)


def fetch_headlines(query: str, limit: int = 8) -> list[dict]:
    """Latest gas-price headlines from the Google News RSS feed. Returns [] if unreachable."""
    url = f"https://news.google.com/rss/search?q={quote_plus(query + ' gas prices')}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError):
        return []
    items = []
    for item in root.iter("item"):
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            published = None
        items.append({
            "title": item.findtext("title", ""),
            "link": item.findtext("link", ""),
            "source": item.findtext("source", ""),
            "published": published,
        })
        if len(items) >= limit:
            break
    return items
