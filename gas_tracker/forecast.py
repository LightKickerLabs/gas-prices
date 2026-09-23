"""Gas price forecast: Holt-Winters exponential smoothing with a damped trend."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

WEEKS_PER_MONTH = 52 / 12
SEASON = 52  # weekly data, yearly seasonality


@dataclass
class Forecast:
    frame: pd.DataFrame  # columns: yhat, lower, upper (95% interval), indexed by week
    method: str
    backtest_mape: float | None  # mean absolute % error when re-run on held-out recent history


def months_to_weeks(months: int) -> int:
    return max(1, round(months * WEEKS_PER_MONTH))


def _fit(series: pd.Series):
    seasonal = len(series) >= 2 * SEASON + 4
    model = ExponentialSmoothing(
        series.to_numpy(),
        trend="add",
        damped_trend=True,
        seasonal="add" if seasonal else None,
        seasonal_periods=SEASON if seasonal else None,
        initialization_method="estimated",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = model.fit(optimized=True)
    method = "Holt-Winters (damped trend + yearly seasonality)" if seasonal else "Holt (damped trend)"
    return fitted, method


def forecast(series: pd.Series, horizon_weeks: int, backtest: bool = True) -> Forecast:
    series = series.dropna().asfreq("W-MON").interpolate()
    fitted, method = _fit(series)
    mean = np.asarray(fitted.forecast(horizon_weeks))
    resid_sd = float(np.nanstd(np.asarray(fitted.resid)[1:], ddof=1))
    # Uncertainty grows with the horizon (random-walk style), so the band widens week by week.
    spread = 1.96 * resid_sd * np.sqrt(np.arange(1, horizon_weeks + 1))
    index = pd.date_range(series.index[-1] + pd.Timedelta(weeks=1), periods=horizon_weeks, freq="W-MON")
    frame = pd.DataFrame(
        {"yhat": mean, "lower": np.maximum(mean - spread, 0), "upper": mean + spread}, index=index
    )
    mape = _backtest(series, horizon_weeks) if backtest else None
    return Forecast(frame=frame, method=method, backtest_mape=mape)


def _backtest(series: pd.Series, horizon_weeks: int) -> float | None:
    """Hold out the last `horizon_weeks`, forecast them from the earlier data, and score."""
    if len(series) < horizon_weeks + 30:
        return None
    train, test = series.iloc[:-horizon_weeks], series.iloc[-horizon_weeks:]
    fitted, _ = _fit(train)
    pred = np.asarray(fitted.forecast(horizon_weeks))
    return float(np.mean(np.abs(pred - test.to_numpy()) / test.to_numpy()) * 100)
