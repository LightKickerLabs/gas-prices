"""Streamlit panel where the user says how upcoming events will play out."""

from __future__ import annotations

import os
from dataclasses import replace

import pandas as pd
import streamlit as st

from . import ai_scenarios, scenarios
from .scenarios import Active, Impact

CUSTOM_KEY = "custom_scenarios"
DURATIONS = {"Lasts": None, "2 weeks": 2, "1 month": 4, "3 months": 13, "6 months": 26}


def _fmt(when: pd.Timestamp) -> str:
    return f"{when:%b} {when.day}, {when.year}"


def _custom() -> list[Active]:
    return st.session_state.setdefault(CUSTOM_KEY, [])


def reset() -> None:
    for key in list(st.session_state):
        if key.startswith("scn_") or key in (CUSTOM_KEY, "ai_summary"):
            del st.session_state[key]


def _question(q: scenarios.Question, region: str, latest_date: pd.Timestamp) -> Active | None:
    title = q.title + (f" · {_fmt(pd.Timestamp(q.date))}" if q.date else "")
    labels = [o.label for o in q.outcomes]
    choice = st.selectbox(title, labels, key=f"scn_{q.key}", help=q.note or None)
    outcome = q.outcomes[labels.index(choice)]
    if outcome.impact is None:
        return None
    idx = labels.index(choice)
    scale = q.scale_for(region)
    c1, c2 = st.columns([1, 1])
    cents = c1.number_input(
        "Effect on price (¢/gal)", value=int(round(outcome.impact.cents * scale)), step=1,
        min_value=-300, max_value=300, key=f"scn_{q.key}_cents_{idx}",
        help="A rough starting assumption. Change it if you expect a bigger or smaller effect.",
    )
    if outcome.impact.start or q.date:
        start = pd.Timestamp(outcome.impact.start or q.date)
        c2.caption(f"Takes effect **{_fmt(start)}**")
    else:
        weeks = c2.slider("Starts in (weeks)", 0, 52, 2, key=f"scn_{q.key}_start_{idx}")
        start = latest_date + pd.Timedelta(weeks=weeks)
        c2.caption(f"Starting week of {start:%b %d, %Y}")
    if outcome.rationale:
        st.caption(outcome.rationale)
    return Active(name=f"{q.title}: {outcome.label}", assumption=outcome.rationale,
                  start=start, impact=replace(outcome.impact, cents=float(cents)))


def _custom_tab(latest_date: pd.Timestamp, latest_price: float, horizon_end: pd.Timestamp,
                area_name: str, recent_events: list[str], anthropic_key: str) -> None:
    st.markdown("**Describe it in your own words**")
    text = st.text_area(
        "What do you think will happen?", key="scn_ai_text", height=90,
        placeholder="e.g. Republicans win both houses in November, but OPEC cuts output in the spring "
                    "and another Bay Area refinery has a fire next summer.",
    )
    has_key = bool(anthropic_key or os.environ.get("ANTHROPIC_API_KEY"))
    if st.button("Ask Claude to estimate the effects", disabled=not (has_key and text.strip())):
        with st.spinner("Claude is thinking through your scenario…"):
            try:
                summary, actives = ai_scenarios.interpret(
                    text, api_key=anthropic_key or None, area=area_name, latest_date=latest_date,
                    latest_price=latest_price, horizon_end=horizon_end, recent_events=recent_events,
                )
            except ai_scenarios.AIScenarioError as exc:
                st.error(str(exc))
            else:
                st.session_state["ai_summary"] = summary
                _custom().extend(replace(a, name=f"🤖 {a.name}") for a in actives)
    if not has_key:
        st.caption("Add an Anthropic API key in the sidebar (or set ANTHROPIC_API_KEY) to use this.")
    if st.session_state.get("ai_summary"):
        st.info(st.session_state["ai_summary"], icon="🤖")

    st.markdown("**Or add one by hand**")
    with st.form("add_custom", clear_on_submit=True, border=False):
        c1, c2, c3, c4 = st.columns([2.2, 1.2, 1, 1])
        name = c1.text_input("Event", placeholder="e.g. New pipeline opens")
        start = c2.date_input("Starts", value=(latest_date + pd.Timedelta(weeks=2)).date(),
                              min_value=latest_date.date())
        cents = c3.number_input("¢/gal", value=10, step=1, min_value=-300, max_value=300)
        duration = c4.selectbox("Lasts", list(DURATIONS))
        if st.form_submit_button("Add scenario") and name.strip():
            hold = DURATIONS[duration]
            _custom().append(Active(
                name=name.strip(), assumption="Your own estimate.", start=pd.Timestamp(start),
                impact=Impact(float(cents), ramp_weeks=2, hold_weeks=hold, fade_weeks=4, uncertainty=0.5),
            ))

    items = _custom()
    for i, a in enumerate(items):
        c1, c2 = st.columns([6, 1])
        lasts = "lasting" if a.impact.hold_weeks is None else f"for ~{a.impact.hold_weeks} wks"
        c1.markdown(f"**{a.name}** · {a.impact.cents:+.0f}¢/gal from {a.start:%b %d, %Y}, {lasts}")
        if a.assumption:
            c1.caption(a.assumption)
        if c2.button("Remove", key=f"scn_rm_{i}"):
            items.pop(i)
            st.rerun()


def render(area, latest_date: pd.Timestamp, latest_price: float, horizon_end: pd.Timestamp,
           recent_events: list[str], anthropic_key: str) -> list[Active]:
    """Draw the what-if panel and return the scenarios the user switched on."""
    head, btn = st.columns([5, 1])
    head.subheader("🔮 What-if scenarios")
    if btn.button("Reset all", width="stretch"):
        reset()
        st.rerun()
    st.caption(
        "Say how you think upcoming events will go and the prediction adjusts. Each effect is a rough, "
        "editable estimate in ¢/gal relative to the baseline forecast, which already reflects today's "
        "conditions. Nobody can predict these events; use this to compare possibilities."
    )
    actives: list[Active] = []
    tabs = st.tabs([*scenarios.GROUPS.values(), "Your own / Ask Claude"])
    for tab, group in zip(tabs, scenarios.GROUPS):
        with tab:
            qs = [q for q in scenarios.questions_for(area.region, group)
                  if not q.date or pd.Timestamp(q.date) >= latest_date]
            if not qs:
                st.caption("No local scenarios for this area yet. Add your own in the last tab.")
            for q in qs:
                picked = _question(q, area.region, latest_date)
                if picked:
                    actives.append(picked)
    with tabs[-1]:
        _custom_tab(latest_date, latest_price, horizon_end, area.name, recent_events, anthropic_key)
    return actives + _custom()
