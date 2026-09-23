import pandas as pd
import pytest

from gas_tracker import ai_scenarios, data, forecast, scenarios
from gas_tracker.scenarios import Active, Impact


@pytest.fixture(scope="module")
def baseline():
    return forecast.forecast(data.sample_series(), 26, backtest=False).frame


def test_no_scenarios_leaves_baseline_unchanged(baseline):
    frame, contrib = scenarios.apply(baseline, [])
    pd.testing.assert_series_equal(frame["yhat"], baseline["yhat"], check_names=False)
    assert contrib.empty or contrib.shape[1] == 0


def test_persistent_effect_ramps_then_holds(baseline):
    start = baseline.index[4]
    a = Active("Hormuz closes", "", start, Impact(70, ramp_weeks=4))
    frame, contrib = scenarios.apply(baseline, [a])
    path = contrib["Hormuz closes"]
    assert (path[path.index < start] == 0).all()
    assert path.iloc[-1] == pytest.approx(0.70)
    assert path.is_monotonic_increasing
    assert frame["yhat"].iloc[-1] == pytest.approx(baseline["yhat"].iloc[-1] + 0.70)
    # scenario uncertainty widens the band
    assert (frame["upper"] - frame["lower"]).iloc[-1] > (baseline["upper"] - baseline["lower"]).iloc[-1]


def test_temporary_effect_fades_back_to_zero(baseline):
    a = Active("Outage", "", baseline.index[0], Impact(60, ramp_weeks=2, hold_weeks=3, fade_weeks=4))
    _, contrib = scenarios.apply(baseline, [a])
    path = contrib["Outage"]
    assert path.max() == pytest.approx(0.60)
    assert path.iloc[-1] == 0


def test_effects_add_up(baseline):
    s = baseline.index[0]
    up = Active("up", "", s, Impact(20, ramp_weeks=1))
    down = Active("down", "", s, Impact(-5, ramp_weeks=1))
    frame, _ = scenarios.apply(baseline, [up, down])
    assert frame["yhat"].iloc[-1] == pytest.approx(baseline["yhat"].iloc[-1] + 0.15)


def test_question_catalog_is_well_formed():
    keys = [q.key for q in scenarios.QUESTIONS]
    assert len(keys) == len(set(keys))
    for q in scenarios.QUESTIONS:
        assert q.outcomes[0].impact is None, f"{q.key} should start with a no-change option"
        assert q.group in scenarios.GROUPS
    ca_local = scenarios.questions_for("california", "local")
    assert ca_local and not scenarios.questions_for("us", "local")
    assert any(q.key == "midterms" for q in scenarios.questions_for("us", "national"))


def test_crude_rule_of_thumb():
    assert scenarios.crude(42) == 100


def test_ai_output_is_clamped_and_not_before_latest_data():
    latest = pd.Timestamp("2026-09-21")
    item = ai_scenarios.ScenarioImpact(
        name="x", rationale="r", start_date="2020-01-01", cents_per_gallon=900, ramp_weeks=0,
        lasts_weeks=None, fade_weeks=0, uncertainty=9,
    )
    a = ai_scenarios._to_active(item, latest)
    assert a.start == latest
    assert a.impact.cents == 300 and a.impact.ramp_weeks == 1 and a.impact.uncertainty == 2.0


class _FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.beta = type("Beta", (), {"messages": _FakeMessages(response)})()


def test_interpret_builds_request_and_parses(monkeypatch):
    parsed = ai_scenarios.ScenarioInterpretation(summary="ok", impacts=[ai_scenarios.ScenarioImpact(
        name="OPEC cut", rationale="less supply", start_date="2027-03-01", cents_per_gallon=19,
        ramp_weeks=6, lasts_weeks=None, fade_weeks=4, uncertainty=0.6)])
    response = type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()
    fake = _FakeClient(response)
    monkeypatch.setattr(ai_scenarios.anthropic, "Anthropic", lambda **_: fake)
    summary, actives = ai_scenarios.interpret(
        "OPEC cuts in spring", api_key="k", area="Sacramento, CA", latest_date=pd.Timestamp("2026-09-21"),
        latest_price=6.02, horizon_end=pd.Timestamp("2026-12-21"), recent_events=["2026-09-18: CA tops $6"],
    )
    assert summary == "ok"
    assert actives[0].impact.cents == 19 and actives[0].start == pd.Timestamp("2027-03-01")
    kw = fake.beta.messages.kwargs
    assert kw["model"] == ai_scenarios.MODEL and kw["output_format"] is ai_scenarios.ScenarioInterpretation
    assert "<user_scenario>" in kw["messages"][0]["content"]


def test_interpret_reports_refusal(monkeypatch):
    response = type("R", (), {"stop_reason": "refusal", "parsed_output": None})()
    monkeypatch.setattr(ai_scenarios.anthropic, "Anthropic", lambda **_: _FakeClient(response))
    with pytest.raises(ai_scenarios.AIScenarioError):
        ai_scenarios.interpret("x", api_key="k", area="CA", latest_date=pd.Timestamp("2026-09-21"),
                               latest_price=6, horizon_end=pd.Timestamp("2026-12-21"), recent_events=[])
