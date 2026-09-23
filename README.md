# ⛽ Gas Price Tracker

A Streamlit app that tracks gas prices for an area (default **Sacramento, CA**), shows the trend,
marks the news events that moved prices, and predicts where prices are heading.

## Features

- **Area & grade** – Sacramento, other California cities, West Coast, major US cities/states, and
  the US average; regular, midgrade, premium or diesel.
- **Timeframe** – last year by default; switch to 1M, 3M, 6M, 2Y, 5Y or pick a custom date range.
- **Prediction** – 3 months ahead by default, adjustable from 1 to 12 months. Shown with a 95%
  range that widens over time, plus a backtest error so you can judge how much to trust it.
- **Line or bar chart**, weekly or monthly resolution.
- **News events** – a curated, sourced timeline (refinery closures, the 2026 Iran war and
  ceasefires, OPEC+ decisions, California policy) plotted on the chart as numbered ▲/▼ markers,
  with a table showing how prices moved in the four weeks after each event. Optional seasonal
  events (summer/winter blend, July 1 gas-tax adjustment) and a live Google News headline feed.
- **Data table & CSV download** of the history and forecast.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Data sources

1. **EIA (recommended)** – get a free API key at <https://www.eia.gov/opendata/register.php>, then
   either paste it into the sidebar, set `EIA_API_KEY` in your environment, or copy
   `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. **Your own CSV** – upload a file with a date column and a price column (daily or weekly rows,
   e.g. exported from GasBuddy or AAA). Handy for true city-level prices.
3. **Built-in sample** – with neither of the above the app shows *approximate* California sample
   data, clearly labeled, so you can try it out.

> **About Sacramento:** EIA doesn't publish a Sacramento series, so with EIA data the app uses the
> California statewide average. Sacramento usually runs slightly above it; use the
> *Local adjustment (¢/gal)* setting or upload local prices for a closer match.

## How the prediction works

Holt-Winters exponential smoothing (damped trend + yearly seasonality) trained on all available
weekly history, not just the visible window. It extrapolates trends and seasonal patterns; it
can't anticipate new shocks such as refinery outages or wars.

## Adding events

Edit `EVENTS` in `gas_tracker/events.py`. Each event has a date, title, description, direction
(`up`/`down`), scope (`global`, `us`, `west_coast`, `california`) and an optional source URL.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
