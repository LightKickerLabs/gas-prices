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
- **What-if scenarios** – say how upcoming events will go and the prediction adjusts. Pick outcomes for
  local (California governor race, refinery outages, state gas tax, climate fuel rules), national
  (2026 midterms, federal gas-tax holiday, Strategic Petroleum Reserve, recession, Gulf hurricanes) and
  global questions (US–Iran war / Hormuz, OPEC+, Russia–Ukraine, China demand). Each outcome comes
  with an editable ¢/gal effect and timing; the chart shows your scenario against the baseline, with
  a breakdown of each assumption. You can also add your own events, or **describe them in plain English
  and have Claude estimate the effects** (needs an Anthropic API key).
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

## How what-if scenarios work

Each outcome is an assumed change in cents per gallon relative to the baseline forecast (which
already reflects today's conditions). Effects ramp in over a few weeks and either persist or fade
after a set period; crude-oil events convert at ≈2.4¢/gal per $1/bbl. Uncertainty from each scenario
widens the forecast band. The default sizes are rough starting points drawn from past episodes; edit
them in the app or in `gas_tracker/scenarios.py`. Political outcomes deliberately carry small effects:
pump prices mostly follow crude oil and refining, not who controls Congress.

For the plain-English option, set `ANTHROPIC_API_KEY` (env var or `.streamlit/secrets.toml`) or paste
a key in the sidebar. The app sends your text plus the area, latest price and recent events to Claude
and gets back structured effects you can review and remove.

## Adding events

Edit `EVENTS` in `gas_tracker/events.py`. Each event has a date, title, description, direction
(`up`/`down`), scope (`global`, `us`, `west_coast`, `california`) and an optional source URL.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
