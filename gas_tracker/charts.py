"""Plotly chart for price history, forecast and event markers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .events import Event

PRICE_COLOR = "#2a78d6"
FORECAST_COLOR = "#eb6834"
BAND_COLOR = "rgba(235, 104, 52, 0.16)"
SCENARIO_COLOR = "#4a3aa7"
SCENARIO_BAND = "rgba(74, 58, 167, 0.16)"
EVENT_COLORS = {"up": "#e34948", "down": "#1baf7a"}
EVENT_SYMBOLS = {"up": "triangle-up", "down": "triangle-down"}
EVENT_LABELS = {"up": "Event: pushed prices up", "down": "Event: pushed prices down"}


def _price_at(series: pd.Series, when: pd.Timestamp) -> float:
    pos = series.index.get_indexer([when], method="nearest")[0]
    return float(series.iloc[pos])


def build_chart(
    history: pd.Series,
    forecast: pd.DataFrame | None,
    events: list[Event],
    chart_type: str,
    resolution: str,
    scenario: pd.DataFrame | None = None,
    scenario_marks: list[tuple[pd.Timestamp, str]] | None = None,
) -> go.Figure:
    fig = go.Figure()
    period = "Month of" if resolution == "Monthly" else "Week of"
    hover = f"{period} %{{x|%b %d, %Y}}<br><b>$%{{y:.3f}}</b>/gal<extra></extra>"

    if chart_type == "Bar":
        fig.add_bar(x=history.index, y=history.values, name="Actual price",
                    marker_color=PRICE_COLOR, hovertemplate=hover)
    else:
        fig.add_scatter(x=history.index, y=history.values, name="Actual price", mode="lines",
                        line=dict(color=PRICE_COLOR, width=2), hovertemplate=hover)

    if forecast is not None and len(forecast):
        if scenario is None:
            _add_forecast(fig, history, forecast, "Forecast", FORECAST_COLOR, BAND_COLOR, chart_type, period)
        else:
            # Baseline stays visible as a thin reference line; the scenario gets the bars/band.
            _add_forecast(fig, history, forecast, "Baseline forecast", FORECAST_COLOR, None, "Line", period)
            _add_forecast(fig, history, scenario, "Your scenario", SCENARIO_COLOR, SCENARIO_BAND,
                          chart_type, period)
        for when, label in scenario_marks or []:
            fig.add_vline(x=when, line=dict(color=SCENARIO_COLOR, width=1, dash="dot"), opacity=0.6)
            fig.add_annotation(x=when, y=1, yref="paper", text=f"<b>{label}</b>", showarrow=False,
                               yanchor="bottom", font=dict(size=11, color=SCENARIO_COLOR))

    if events:
        span = float(history.max() - history.min()) or 0.5
        for impact in ("up", "down"):
            group = [(i, e) for i, e in enumerate(events, start=1) if e.impact == impact]
            if not group:
                continue
            xs = [e.timestamp for _, e in group]
            # Bars fill down to zero, so in bar mode every marker sits above the bar.
            above = impact == "up" or chart_type == "Bar"
            offset = span * 0.06 if above else -span * 0.06
            ys = [_price_at(history, e.timestamp) + offset for _, e in group]
            fig.add_scatter(
                x=xs, y=ys, mode="markers+text", name=EVENT_LABELS[impact],
                text=[str(i) for i, _ in group],
                textposition="top center" if above else "bottom center",
                textfont=dict(size=11),
                marker=dict(symbol=EVENT_SYMBOLS[impact], size=12, color=EVENT_COLORS[impact],
                            line=dict(width=1.5, color="white")),
                customdata=[[e.title, e.category, e.date] for _, e in group],
                hovertemplate="<b>#%{text} %{customdata[0]}</b><br>%{customdata[2]} · %{customdata[1]}<extra></extra>",
            )

    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="closest",
        bargap=0.15,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="$ per gallon", tickprefix="$", tickformat=".2f", zeroline=False),
        xaxis=dict(title=None, showspikes=True, spikemode="across", spikethickness=1, spikedash="dot"),
    )
    return fig


def _add_forecast(fig: go.Figure, history: pd.Series, frame: pd.DataFrame, name: str, color: str,
                  band_color: str | None, chart_type: str, period: str) -> None:
    hover = (f"{period} %{{x|%b %d, %Y}}<br>{name} <b>$%{{y:.3f}}</b>"
             "<br>95% range $%{customdata[0]:.2f} - $%{customdata[1]:.2f}<extra></extra>")
    custom = frame[["lower", "upper"]].to_numpy()
    if chart_type == "Bar":
        fig.add_bar(
            x=frame.index, y=frame["yhat"], name=name,
            marker=dict(color=color, opacity=0.7),
            error_y=dict(type="data", symmetric=False,
                         array=frame["upper"] - frame["yhat"],
                         arrayminus=frame["yhat"] - frame["lower"],
                         color=color, thickness=1),
            customdata=custom, hovertemplate=hover,
        )
        return
    if band_color:
        fig.add_scatter(x=frame.index, y=frame["upper"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=frame.index, y=frame["lower"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor=band_color, name=f"95% range ({name.lower()})",
                        hoverinfo="skip")
    # Start the line at the last actual point so it connects to the history.
    last = float(history.iloc[-1])
    fig.add_scatter(x=[history.index[-1], *frame.index], y=[last, *frame["yhat"]], name=name, mode="lines",
                    line=dict(color=color, width=2 if band_color else 1.5, dash="dash"),
                    customdata=[[last, last], *custom], hovertemplate=hover)
