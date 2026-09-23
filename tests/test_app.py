from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run(**changes):
    at = AppTest.from_file(APP, default_timeout=60).run()
    for key, value in changes.items():
        at.segmented_control(key=key).set_value(value)
    at.run()
    assert not at.exception, at.exception
    return at


def test_default_view_sacramento_line_one_year_three_month_forecast():
    at = run()
    assert at.title[0].value == "Gas prices in Sacramento, CA"
    assert at.select_slider[0].value == 3
    assert any(m.label.startswith("Predicted in 3 mo") for m in at.metric)


def test_bar_monthly_five_years():
    run(chart="Bar", res="Monthly", timeframe="5Y")


def test_custom_range_and_other_area():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.selectbox(key="area").set_value("Houston, TX")
    at.segmented_control(key="timeframe").set_value("Custom")
    at.select_slider[0].set_value(12)
    at.run()
    assert not at.exception
    assert at.date_input


def test_choosing_scenarios_moves_prediction():
    at = AppTest.from_file(APP, default_timeout=60).run()
    base = next(m for m in at.metric if m.label.startswith("Predicted"))
    at.selectbox(key="scn_iran").set_value("Escalation; Hormuz effectively closed")
    at.selectbox(key="scn_midterms").set_value("Democrats win the House and Senate")
    at.run()
    assert not at.exception, at.exception
    moved = next(m for m in at.metric if m.label.startswith("Your scenario"))
    assert float(moved.value.strip("$")) > float(base.value.strip("$"))


def test_custom_scenario_and_non_california_area():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.selectbox(key="area").set_value("Houston, TX")
    at.run()
    assert not at.exception
    assert not any(sb.key == "scn_ca_governor" for sb in at.selectbox)
    assert any(sb.key == "scn_hurricane" for sb in at.selectbox)
