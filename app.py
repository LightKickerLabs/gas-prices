"""Gas Price Tracker - Streamlit app.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import streamlit as st

from gas_tracker import charts, data, events, forecast, scenario_ui, scenarios

st.set_page_config(page_title="Gas Price Tracker", page_icon="⛽", layout="wide")

TIMEFRAMES = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "2Y": 24, "5Y": 60, "Custom": None}
FORECAST_MONTHS = [1, 2, 3, 4, 6, 9, 12]


def _secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.environ.get(name, "")
    except Exception:  # no secrets.toml present
        return os.environ.get(name, "")


@st.cache_data(ttl=6 * 3600, show_spinner="Fetching prices from EIA…")
def load_eia(api_key: str, area_code: str, product: str) -> pd.Series:
    return data.fetch_eia(api_key, area_code, product)


@st.cache_data(ttl=3600, show_spinner=False)
def load_headlines(query: str) -> list[dict]:
    return events.fetch_headlines(query)


@st.cache_data(show_spinner="Building forecast…")
def run_forecast(series: pd.Series, horizon_weeks: int) -> forecast.Forecast:
    return forecast.forecast(series, horizon_weeks)


# ---------------------------------------------------------------- sidebar: where & what
with st.sidebar:
    st.header("⛽ Area & data")
    area_name = st.selectbox("Area", list(data.AREAS), index=list(data.AREAS).index(data.DEFAULT_AREA), key="area")
    area = data.AREAS[area_name]
    grade = st.selectbox("Fuel grade", list(data.GRADES))

    st.subheader("Data source")
    upload = st.file_uploader("Upload your own local prices (CSV)", type="csv",
                              help="Two columns: a date and a price in $/gal. Daily or weekly rows are fine.")
    api_key = _secret("EIA_API_KEY")
    if not api_key:
        api_key = st.text_input("EIA API key (free)", type="password",
                                help="Get one at https://www.eia.gov/opendata/register.php. "
                                     "You can also set EIA_API_KEY as an env var or in .streamlit/secrets.toml.")
    offset_cents = st.number_input("Local adjustment (¢/gal)", value=0, step=5, min_value=-200, max_value=200,
                                   help="Shift the series up or down, e.g. +20 to approximate Sacramento "
                                        "from the California average.")

    st.subheader("What-if AI")
    anthropic_key = _secret("ANTHROPIC_API_KEY")
    if not anthropic_key:
        anthropic_key = st.text_input("Anthropic API key (optional)", type="password",
                                      help="Lets Claude turn scenarios written in your own words into price "
                                           "effects. Or set ANTHROPIC_API_KEY.")

# ---------------------------------------------------------------- load the series
source_label, notice = "", None
series: pd.Series | None = None
if upload is not None:
    try:
        series = data.parse_uploaded_csv(upload.getvalue())
        source_label = f"Your upload ({upload.name})"
    except (data.DataSourceError, ValueError) as exc:
        st.sidebar.error(f"Couldn't read that CSV: {exc}")
if series is None and api_key:
    try:
        series = load_eia(api_key, area.eia_code, data.GRADES[grade])
        source_label = f"U.S. EIA weekly retail prices · {grade}"
        if area.proxy_note:
            notice = area.proxy_note
    except data.DataSourceError as exc:
        st.sidebar.error(str(exc))
if series is None:
    series = data.sample_series()
    source_label = "Built-in sample data (approximate California regular)"
    notice = ("Showing **approximate sample data** for California regular gasoline, not live prices. "
              "Add a free EIA API key or upload a CSV in the sidebar for real prices"
              f"{' in ' + area_name if area_name != 'California' else ''}.")

if offset_cents:
    series = series + offset_cents / 100
    source_label += f" · adjusted {offset_cents:+d}¢"

latest_date = series.index[-1]

# ---------------------------------------------------------------- header & controls
st.title(f"Gas prices in {area_name}")
st.caption(f"{grade} · {source_label} · latest data: week of {latest_date:%b %d, %Y}")
if notice:
    st.info(notice, icon="ℹ️")

c1, c2, c3, c4 = st.columns([3, 2, 1.3, 1.3])
with c1:
    timeframe = st.segmented_control("Timeframe", list(TIMEFRAMES), default="1Y", key="timeframe") or "1Y"
with c2:
    horizon_months = st.select_slider("Prediction horizon", options=FORECAST_MONTHS, value=3,
                                      format_func=lambda m: f"{m} mo")
with c3:
    chart_type = st.segmented_control("Chart", ["Line", "Bar"], default="Line", key="chart") or "Line"
with c4:
    resolution = st.segmented_control("Show", ["Weekly", "Monthly"], default="Weekly", key="res") or "Weekly"

if TIMEFRAMES[timeframe] is None:
    earliest = series.index[0].date()
    default_start = max(earliest, (latest_date - pd.DateOffset(months=12)).date())
    picked = st.date_input("Custom date range", value=(default_start, latest_date.date()),
                           min_value=earliest, max_value=latest_date.date())
    start_d, end_d = (picked if isinstance(picked, tuple) and len(picked) == 2
                      else (default_start, latest_date.date()))
    window_start, window_end = pd.Timestamp(start_d), pd.Timestamp(end_d)
else:
    window_start = latest_date - pd.DateOffset(months=TIMEFRAMES[timeframe])
    window_end = latest_date

o1, o2, o3 = st.columns([1, 1, 2])
show_forecast = o1.toggle("Show prediction", value=True)
show_events = o2.toggle("Show news events", value=True)
include_seasonal = o3.toggle("Include seasonal/tax events", value=False,
                             help="Summer/winter blend switches and the July 1 gas-tax adjustment (California areas).")

window = data.slice_window(series, window_start, window_end)
if len(window) < 2:
    st.warning("Not enough data in that date range. Pick a wider range.")
    st.stop()

# The forecast always trains on the full history (not just the visible window) and only makes
# sense when the window ends at the latest data point.
fc = None
forecast_allowed = window_end >= latest_date
if show_forecast and forecast_allowed:
    fc = run_forecast(series, forecast.months_to_weeks(horizon_months))

display = data.aggregate(window, resolution)
window_events = events.events_for(area.region, window_start, window_end, include_seasonal) if show_events else []

# Metrics and chart depend on the what-if panel below them, so reserve their slots first.
metrics_slot = st.container()
chart_slot = st.container()

actives: list[scenarios.Active] = []
scenario_fc = contributions = None
if fc is not None:
    recent = events.events_for(area.region, latest_date - pd.DateOffset(months=12), latest_date, False)
    actives = scenario_ui.render(
        area, latest_date, float(series.iloc[-1]), fc.frame.index[-1],
        [f"{e.date}: {e.title}" for e in recent], anthropic_key,
    )
    if actives:
        scenario_fc, contributions = scenarios.apply(fc.frame, actives)
else:
    st.caption("🔮 Turn on **Show prediction** (with a timeframe ending at the latest data) to explore "
               "what-if scenarios.")


def _for_display(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is not None and resolution == "Monthly":
        return frame.resample("MS").mean()
    return frame


# ---------------------------------------------------------------- headline numbers
with metrics_slot:
    m1, m2, m3, m4 = st.columns(4)
    now, first = float(window.iloc[-1]), float(window.iloc[0])
    m1.metric(f"Price, week of {window.index[-1]:%b %d}", f"${now:.2f}",
              f"{now - first:+.2f} vs {window.index[0]:%b %d, %Y}", delta_color="inverse")
    m2.metric("High in range", f"${window.max():.2f}", f"{window.idxmax():%b %d, %Y}", delta_color="off")
    m3.metric("Low in range", f"${window.min():.2f}", f"{window.idxmin():%b %d, %Y}", delta_color="off")
    if fc is not None:
        base_end = fc.frame.iloc[-1]
        label = f"Predicted in {horizon_months} mo ({fc.frame.index[-1]:%b %d})"
        if scenario_fc is not None:
            end = scenario_fc.iloc[-1]
            m4.metric(f"Your scenario in {horizon_months} mo ({fc.frame.index[-1]:%b %d})", f"${end.yhat:.2f}",
                      f"{end.yhat - base_end.yhat:+.2f} vs baseline \\${base_end.yhat:.2f}", delta_color="inverse")
        else:
            m4.metric(label, f"${base_end.yhat:.2f}",
                      f"{base_end.yhat - float(series.iloc[-1]):+.2f} · range "
                      f"\\${base_end.lower:.2f}–\\${base_end.upper:.2f}",
                      delta_color="inverse")
    else:
        m4.metric("Prediction", "Off" if not show_forecast else "n/a",
                  None if show_forecast is False else "Range must end at latest data", delta_color="off")

# ---------------------------------------------------------------- chart
fc_display = _for_display(fc.frame if fc is not None else None)
scenario_display = _for_display(scenario_fc)
# Scenarios that start inside the horizon get a lettered marker, matching the table below.
in_horizon = sorted((a for a in actives if fc is not None and latest_date < a.start <= fc.frame.index[-1]),
                    key=lambda a: a.start)
letters = {a.name: chr(ord("A") + i) for i, a in enumerate(in_horizon)}
marks = [(a.start, letters[a.name]) for a in actives if a.name in letters]
with chart_slot:
    fig = charts.build_chart(display, fc_display, window_events, chart_type, resolution,
                             scenario=scenario_display, scenario_marks=marks)
    st.plotly_chart(fig, width="stretch", theme="streamlit")

if contributions is not None:
    horizon_end = fc.frame.index[-1]
    rows = []
    for a in actives:
        col = contributions[a.name]
        peak = col.iloc[col.abs().to_numpy().argmax()] if len(col) else 0.0
        after = a.start > horizon_end
        rows.append({
            "Mark": letters.get(a.name, ""),
            "Scenario": a.name,
            "Starts": f"{a.start:%Y-%m-%d}" + (" (after horizon)" if after else ""),
            f"Effect by {horizon_end:%b %d, %Y}": float(col.iloc[-1]),
            "Peak effect": float(peak),
            "Assumption": a.assumption,
        })
    total = contributions.sum(axis=1)
    rows.append({"Mark": "", "Scenario": "Total", "Starts": "",
                 f"Effect by {horizon_end:%b %d, %Y}": float(total.iloc[-1]),
                 "Peak effect": float(total.iloc[total.abs().to_numpy().argmax()]), "Assumption": ""})
    st.markdown("**How your scenario changes the prediction** ($/gal vs. baseline)")
    if any(a.start > horizon_end for a in actives):
        st.caption("Some scenarios start after your prediction horizon. Lengthen the horizon to see them.")
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch",
        column_config={
            f"Effect by {horizon_end:%b %d, %Y}": st.column_config.NumberColumn(format="%+.2f"),
            "Peak effect": st.column_config.NumberColumn(format="%+.2f"),
            "Assumption": st.column_config.TextColumn(width="large"),
        },
    )

# ---------------------------------------------------------------- events
if show_events:
    st.subheader(f"What moved prices ({window_start:%b %Y} – {window_end:%b %Y})")
    if window_events:
        rows = []
        for i, e in enumerate(window_events, start=1):
            before = data.slice_window(series, e.timestamp - pd.Timedelta(days=7), e.timestamp)
            after = data.slice_window(series, e.timestamp + pd.Timedelta(days=21), e.timestamp + pd.Timedelta(days=35))
            move = (float(after.iloc[0]) - float(before.iloc[-1])) if len(before) and len(after) else None
            rows.append({
                "#": i,
                "Date": e.timestamp.date(),
                "Effect": "▲ Up" if e.impact == "up" else "▼ Down",
                "Event": e.title,
                "Why it matters": e.description,
                "Δ 4 wks later": move,
                "Category": e.category,
                "Source": e.source,
            })
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width="stretch",
            column_config={
                "#": st.column_config.NumberColumn(width="small"),
                "Why it matters": st.column_config.TextColumn(width="large"),
                "Δ 4 wks later": st.column_config.NumberColumn(
                    format="%+.2f", help="Change in $/gal from the week before the event to ~4 weeks after."),
                "Source": st.column_config.LinkColumn(display_text="link"),
            },
        )
    else:
        st.caption("No curated events in this range. Try a longer timeframe.")

    with st.expander(f"Latest headlines: {area.news_query} gas prices"):
        headlines = load_headlines(area.news_query)
        if headlines:
            for h in headlines:
                when = f" · {h['published']:%b %d, %Y}" if h["published"] else ""
                title = h["title"].replace("$", "\\$")
                st.markdown(f"- [{title}]({h['link']}){when}")
        else:
            st.caption("Couldn't reach Google News right now.")

# ---------------------------------------------------------------- data & method
with st.expander("Data table & download"):
    table = display.rename("Price ($/gal)").to_frame()
    table.index.name = "Month" if resolution == "Monthly" else "Week"
    if fc_display is not None:
        f = fc_display.rename(columns={"yhat": "Forecast ($/gal)", "lower": "Low (95%)", "upper": "High (95%)"})
        if scenario_display is not None:
            f["Your scenario ($/gal)"] = scenario_display["yhat"]
        table = pd.concat([table, f])
    st.dataframe(table.round(3), width="stretch")
    st.download_button("Download CSV", table.round(3).to_csv().encode(),
                       file_name=f"gas-prices-{area_name.split(',')[0].lower().replace(' ', '-')}-{date.today()}.csv",
                       mime="text/csv")

with st.expander("How the prediction works"):
    if fc is not None:
        mape = f"{fc.backtest_mape:.1f}%" if fc.backtest_mape is not None else "n/a"
        st.markdown(
            f"**Model:** {fc.method}, trained on all {len(series)} weeks of history.\n\n"
            f"**Backtest:** hiding the last {horizon_months} month(s) and predicting them gave an average "
            f"error of **{mape}**.\n\n"
            "The shaded band is a 95% range that widens the further out it goes. The model extrapolates "
            "past trends and seasonal patterns; it cannot foresee new shocks like refinery outages, wars "
            "or policy changes - which is exactly what the news events above show can move prices fast."
        )
    else:
        st.markdown("Turn on **Show prediction** with a timeframe that ends at the latest data.")
