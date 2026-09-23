"""Plotly chart for price history, forecast and event markers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .events import Event

PRICE_COLOR = "#2a78d6"
FORECAST_COLOR = "#eb6834"
BAND_COLOR = "rgba(235, 104, 52, 0.16)"
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
        fc_hover = (f"{period} %{{x|%b %d, %Y}}<br>Forecast <b>$%{{y:.3f}}</b>"
                    "<br>95% range $%{customdata[0]:.2f} - $%{customdata[1]:.2f}<extra></extra>")
        custom = forecast[["lower", "upper"]].to_numpy()
        if chart_type == "Bar":
            fig.add_bar(
                x=forecast.index, y=forecast["yhat"], name="Forecast",
                marker=dict(color=FORECAST_COLOR, opacity=0.7),
                error_y=dict(type="data", symmetric=False,
                             array=forecast["upper"] - forecast["yhat"],
                             arrayminus=forecast["yhat"] - forecast["lower"],
                             color=FORECAST_COLOR, thickness=1),
                customdata=custom, hovertemplate=fc_hover,
            )
        else:
            fig.add_scatter(x=forecast.index, y=forecast["upper"], mode="lines", line=dict(width=0),
                            showlegend=False, hoverinfo="skip")
            fig.add_scatter(x=forecast.index, y=forecast["lower"], mode="lines", line=dict(width=0),
                            fill="tonexty", fillcolor=BAND_COLOR, name="95% forecast range",
                            hoverinfo="skip")
            # Start the forecast line at the last actual point so the two lines connect.
            fx = [history.index[-1], *forecast.index]
            fy = [history.iloc[-1], *forecast["yhat"]]
            fcd = [[history.iloc[-1], history.iloc[-1]], *custom]
            fig.add_scatter(x=fx, y=fy, name="Forecast", mode="lines",
                            line=dict(color=FORECAST_COLOR, width=2, dash="dash"),
                            customdata=fcd, hovertemplate=fc_hover)

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
