import pandas as pd

from gas_tracker import data, events, forecast


def test_sample_series_is_weekly_and_ends_on_latest_anchor():
    s = data.sample_series()
    assert s.index.freqstr == "W-MON"
    assert s.iloc[-1] == 6.02
    assert s.between(2, 8).all()


def test_forecast_default_three_months():
    s = data.sample_series()
    weeks = forecast.months_to_weeks(3)
    assert weeks == 13
    fc = forecast.forecast(s, weeks)
    assert len(fc.frame) == weeks
    assert fc.frame.index[0] > s.index[-1]
    assert (fc.frame["lower"] <= fc.frame["yhat"]).all()
    assert (fc.frame["yhat"] <= fc.frame["upper"]).all()
    # the band widens with the horizon
    width = fc.frame["upper"] - fc.frame["lower"]
    assert width.iloc[-1] > width.iloc[0]
    assert fc.backtest_mape is not None


def test_short_history_falls_back_to_non_seasonal():
    s = data.sample_series().iloc[-60:]
    fc = forecast.forecast(s, 4)
    assert "seasonality" not in fc.method


def test_events_scoped_by_region():
    start, end = pd.Timestamp("2025-09-01"), pd.Timestamp("2026-09-30")
    ca = events.events_for("california", start, end, include_seasonal=False)
    us = events.events_for("us", start, end, include_seasonal=False)
    assert any(e.scope == "california" for e in ca)
    assert all(e.scope in {"global", "us"} for e in us)
    assert len(us) < len(ca)
    assert ca == sorted(ca, key=lambda e: e.timestamp)


def test_parse_uploaded_csv_daily_to_weekly():
    days = pd.date_range("2026-01-01", periods=90, freq="D")
    csv = pd.DataFrame({"Date": days, "Regular ($)": [f"${4 + i / 100:.2f}" for i in range(90)]}).to_csv(index=False)
    s = data.parse_uploaded_csv(csv.encode())
    assert s.index.freqstr == "W-MON"
    assert 4 <= s.min() and s.max() <= 5


def test_monthly_aggregation():
    s = data.sample_series()
    m = data.aggregate(s, "Monthly")
    assert m.index.freqstr == "MS"
