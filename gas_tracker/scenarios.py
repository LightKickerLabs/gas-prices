"""What-if scenarios: user-chosen outcomes of future events, applied on top of the baseline forecast.

Every effect is a rough, editable assumption in cents per gallon relative to the baseline forecast.
The baseline already reflects conditions as of the latest data (e.g. today's war premium), so
"status quo" outcomes are zero and the other outcomes describe a change from there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CENTS_PER_CRUDE_DOLLAR = 100 / 42  # $1/bbl spread over 42 gallons ≈ 2.4¢/gal at the pump


@dataclass(frozen=True)
class Impact:
    cents: float  # full effect on the pump price, ¢/gal (positive = higher prices)
    ramp_weeks: int = 4  # weeks to reach the full effect
    hold_weeks: int | None = None  # weeks at full effect, then it fades; None = lasts
    fade_weeks: int = 8
    uncertainty: float = 0.5  # 95% band as a fraction of the effect
    start: str | None = None  # fixed start date (overrides the question's date / user timing)


@dataclass(frozen=True)
class Outcome:
    label: str
    rationale: str
    impact: Impact | None = None  # None = no change from the baseline


@dataclass(frozen=True)
class Question:
    key: str
    title: str
    group: str  # "local", "national" or "global"
    outcomes: tuple[Outcome, ...]
    date: str | None = None  # when it is decided; None = the user picks the timing
    regions: frozenset[str] = frozenset({"california", "west_coast", "us"})
    region_scale: dict[str, float] = field(default_factory=dict)  # dampen for some regions
    note: str = ""

    def scale_for(self, region: str) -> float:
        return self.region_scale.get(region, 1.0)


def crude(dollars: float) -> float:
    return round(dollars * CENTS_PER_CRUDE_DOLLAR)


BASELINE = Outcome("No view (use the baseline)", "")
CA = frozenset({"california"})

QUESTIONS: tuple[Question, ...] = (
    # ------------------------------------------------------------------ local (California)
    Question(
        "ca_governor", "California governor race", "local", date="2026-11-03", regions=CA,
        note="Newsom is term-limited; the winner takes office in January 2027.",
        outcomes=(
            BASELINE,
            Outcome("Democrat wins",
                    "Continuity: refinery-oversight and climate fuel rules keep tightening. Little short-term "
                    "change; a slow upward drift in compliance costs is possible.",
                    Impact(3, ramp_weeks=26, uncertainty=1.0, start="2027-01-04")),
            Outcome("Republican wins",
                    "Likely pushes to ease refinery rules and keep refineries open, but a Democratic "
                    "legislature limits how much changes, and slowly.",
                    Impact(-5, ramp_weeks=26, uncertainty=1.0, start="2027-01-04")),
        ),
    ),
    Question(
        "ca_refinery", "Another California refinery disruption?", "local", regions=CA,
        note="With Wilmington and Benicia gone, the state has less spare refining capacity.",
        outcomes=(
            BASELINE,
            Outcome("Major unplanned outage (a few weeks)",
                    "Outages in 2022 and 2023 sent California prices up roughly 50¢ to $1 within weeks, "
                    "then faded as imports arrived.",
                    Impact(60, ramp_weeks=2, hold_weeks=3, fade_weeks=6, uncertainty=0.5)),
            Outcome("Another refinery announces permanent closure",
                    "Less in-state capacity means more reliance on costlier imported gasoline.",
                    Impact(25, ramp_weeks=8, uncertainty=0.6)),
            Outcome("Supply eases (imports ramp up / capacity restored)",
                    "More import terminals and shipping capacity narrow California's premium.",
                    Impact(-20, ramp_weeks=6, uncertainty=0.6)),
        ),
    ),
    Question(
        "ca_gas_tax", "California gas tax", "local", regions=CA,
        note="The state excise tax is about 61¢/gal and rises with inflation every July 1.",
        outcomes=(
            BASELINE,
            Outcome("Suspended for 6 months",
                    "Assumes ~80% of the tax cut reaches drivers at the pump.",
                    Impact(-50, ramp_weeks=1, hold_weeks=26, fade_weeks=2, uncertainty=0.3)),
            Outcome("Scheduled inflation increase (July 1, 2027)",
                    "The annual adjustment is typically 1-2¢/gal.",
                    Impact(2, ramp_weeks=1, uncertainty=0.5, start="2027-07-01")),
        ),
    ),
    Question(
        "ca_climate", "California climate fuel rules (LCFS / cap-and-invest)", "local", regions=CA,
        outcomes=(
            BASELINE,
            Outcome("Credit prices climb / rules tighten",
                    "Higher compliance costs are passed through to fuel prices.",
                    Impact(15, ramp_weeks=12, uncertainty=0.7)),
            Outcome("Rules paused or relaxed",
                    "Lower compliance costs; effect depends on how credit markets react.",
                    Impact(-15, ramp_weeks=12, uncertainty=0.7)),
        ),
    ),
    # ------------------------------------------------------------------ national
    Question(
        "midterms", "2026 midterm elections (control of Congress)", "national", date="2026-11-03",
        note="Congress has little short-term control over pump prices, which mostly follow crude oil. "
             "Effects here are small, mainly market expectations about drilling, permitting and trade policy.",
        outcomes=(
            BASELINE,
            Outcome("Republicans keep the House and Senate",
                    "Markets expect continued pro-production policy; a slight downward nudge.",
                    Impact(-3, ramp_weeks=12, uncertainty=1.5)),
            Outcome("Democrats win the House (split Congress)",
                    "Gridlock; energy policy largely unchanged.",
                    Impact(2, ramp_weeks=12, uncertainty=1.5)),
            Outcome("Democrats win the House and Senate",
                    "More oversight of drilling and trade policy; a slight upward nudge.",
                    Impact(4, ramp_weeks=12, uncertainty=1.5)),
        ),
    ),
    Question(
        "fed_gas_tax", "Federal gas-tax holiday (18.4¢/gal)", "national",
        outcomes=(
            BASELINE,
            Outcome("Congress passes a 3-month holiday",
                    "Assumes ~75% of the 18.4¢ tax cut reaches drivers.",
                    Impact(-14, ramp_weeks=1, hold_weeks=13, fade_weeks=1, uncertainty=0.4)),
        ),
    ),
    Question(
        "spr", "Strategic Petroleum Reserve", "national",
        outcomes=(
            BASELINE,
            Outcome("Large emergency release",
                    "The Treasury estimated the 2022 release cut prices by roughly 17-42¢; assumes a smaller one.",
                    Impact(-10, ramp_weeks=4, hold_weeks=12, fade_weeks=8, uncertainty=0.6)),
            Outcome("Government buys oil to refill it",
                    "Adds a little demand to the crude market.",
                    Impact(3, ramp_weeks=4, uncertainty=0.8)),
        ),
    ),
    Question(
        "economy", "US economy", "national",
        outcomes=(
            BASELINE,
            Outcome("Mild recession",
                    "Lower driving and freight demand; crude weakens.",
                    Impact(-30, ramp_weeks=12, uncertainty=0.6)),
            Outcome("Severe recession",
                    "Like 2008 or 2020 on a smaller scale: a sharp demand drop.",
                    Impact(-80, ramp_weeks=16, uncertainty=0.5)),
            Outcome("Strong growth",
                    "More travel and freight; higher demand for fuel.",
                    Impact(15, ramp_weeks=12, uncertainty=0.6)),
        ),
    ),
    Question(
        "hurricane", "Gulf Coast hurricane hits refineries", "national",
        note="Hurricane season runs to Nov 30. California is on a separate fuel market, so it feels less of it.",
        region_scale={"california": 0.25, "west_coast": 0.4},
        outcomes=(
            BASELINE,
            Outcome("Major hurricane shuts Gulf refineries",
                    "Harvey (2017) and Katrina (2005) spiked national prices 25-50¢ for weeks.",
                    Impact(40, ramp_weeks=1, hold_weeks=2, fade_weeks=6, uncertainty=0.6)),
        ),
    ),
    # ------------------------------------------------------------------ global
    Question(
        "iran", "US–Iran war and the Strait of Hormuz", "global",
        note="Over 20% of the world's oil passes through Hormuz. Crude-driven effects use ≈2.4¢/gal per $1/bbl.",
        outcomes=(
            BASELINE,
            Outcome("Lasting peace; Hormuz fully reopens",
                    "The war premium comes out of crude: about -$20/bbl.",
                    Impact(crude(-20), ramp_weeks=6, uncertainty=0.5)),
            Outcome("Fragile ceasefire",
                    "Part of the premium unwinds: about -$8/bbl.",
                    Impact(crude(-8), ramp_weeks=4, uncertainty=0.6)),
            Outcome("Escalation; Hormuz effectively closed",
                    "A major supply shock: about +$30/bbl.",
                    Impact(crude(30), ramp_weeks=3, uncertainty=0.6)),
        ),
    ),
    Question(
        "opec", "OPEC+ production decision", "global",
        outcomes=(
            BASELINE,
            Outcome("OPEC+ raises output", "More supply: about -$6/bbl.",
                    Impact(crude(-6), ramp_weeks=6, uncertainty=0.6)),
            Outcome("OPEC+ cuts output", "Less supply: about +$8/bbl.",
                    Impact(crude(8), ramp_weeks=6, uncertainty=0.6)),
        ),
    ),
    Question(
        "russia", "Russia–Ukraine war", "global",
        outcomes=(
            BASELINE,
            Outcome("Peace deal; sanctions ease", "More Russian barrels on the market: about -$5/bbl.",
                    Impact(crude(-5), ramp_weeks=8, uncertainty=0.7)),
            Outcome("Escalating attacks on Russian refineries and ports",
                    "Export disruptions: about +$6/bbl.",
                    Impact(crude(6), ramp_weeks=4, uncertainty=0.7)),
        ),
    ),
    Question(
        "china", "China's oil demand", "global",
        outcomes=(
            BASELINE,
            Outcome("Stimulus-driven rebound", "Stronger demand from the world's top importer: about +$5/bbl.",
                    Impact(crude(5), ramp_weeks=12, uncertainty=0.7)),
            Outcome("Slowdown", "Weaker demand: about -$5/bbl.",
                    Impact(crude(-5), ramp_weeks=12, uncertainty=0.7)),
        ),
    ),
)

GROUPS = {"local": "Local (California)", "national": "National", "global": "Global"}


def questions_for(region: str, group: str) -> list[Question]:
    return [q for q in QUESTIONS if q.group == group and region in q.regions]


@dataclass(frozen=True)
class Active:
    """A scenario the user switched on, resolved to a concrete start date and size."""
    name: str
    assumption: str
    start: pd.Timestamp
    impact: Impact


def effect_path(impact: Impact, start: pd.Timestamp, index: pd.DatetimeIndex) -> np.ndarray:
    """Effect in $/gal at each date: ramps up, optionally holds then fades, otherwise persists."""
    weeks = (index - start).days.to_numpy() / 7
    ramp = max(impact.ramp_weeks, 1)
    level = np.clip((weeks + 1) / ramp, 0, 1)
    if impact.hold_weeks is not None:
        after = weeks - ramp - impact.hold_weeks
        fade = np.clip(1 - after / max(impact.fade_weeks, 1), 0, 1)
        level = np.where(after > 0, fade, level)
    level = np.where(weeks < 0, 0, level)
    return level * impact.cents / 100


def apply(baseline: pd.DataFrame, actives: list[Active]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scenario forecast (yhat/lower/upper) and per-scenario contributions ($/gal) by week."""
    contributions = pd.DataFrame(
        {a.name: effect_path(a.impact, a.start, baseline.index) for a in actives}, index=baseline.index
    )
    total = contributions.sum(axis=1) if actives else pd.Series(0.0, index=baseline.index)
    base_half = (baseline["upper"] - baseline["lower"]) / 2
    scen_half_sq = sum(
        (contributions[a.name].abs() * a.impact.uncertainty) ** 2 for a in actives
    ) if actives else 0
    half = np.sqrt(base_half**2 + scen_half_sq)
    yhat = baseline["yhat"] + total
    frame = pd.DataFrame({"yhat": yhat, "lower": np.maximum(yhat - half, 0), "upper": yhat + half})
    return frame, contributions
