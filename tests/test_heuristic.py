from datetime import date

from fed_pulse.heuristic import assess, heuristic_brief, label_for, score_sentence
from fed_pulse.minutes import parse_minutes_html
from fed_pulse.yields import YieldPoint, YieldSeries


def _series(y2_start, y2_end):
    return YieldSeries(
        [YieldPoint(date(2026, 7, 1), y2_start, 4.5, 4.9), YieldPoint(date(2026, 9, 30), y2_end, 4.7, 5.0)],
        "test",
        "https://example.test",
    )


def test_score_sentence_hawkish_and_dovish():
    h = score_sentence("Participants noted that inflation remained elevated and upside risks to inflation.")
    assert h.score == 2 and h.tag == "hawkish"
    d = score_sentence("The labor market had softened and inflation has eased.")
    assert d.score == -2 and d.tag == "dovish"
    assert score_sentence("The meeting began at 9 a.m.").score == 0


def test_assess_combines_components(fixture_text):
    m = parse_minutes_html(fixture_text("minutes.html"))
    a = assess(m, _series(4.0, 4.25))
    assert a.hawkish_hits > a.dovish_hits
    assert a.components["decision"] == 1.0
    assert a.components["yield_trend"] == 0.5  # +25 bp / 50 bp full scale
    assert a.trend.change_bp["y2"] == 25.0
    assert a.index > 15 and a.label in ("Elevated", "High")
    assert a.key_sentences and a.key_sentences[0].tag == "hawkish"
    brief = heuristic_brief(a, m)
    assert "not a probability model" in brief and "+25 bp" in brief


def test_assess_handles_missing_minutes():
    a = assess(None, _series(4.5, 4.0))  # 2Y fell 50 bp -> full dovish yield signal
    assert a.components["minutes_tone"] is None and a.index == -100
    assert "yields only" in heuristic_brief(a, None)


def test_label_thresholds():
    assert [label_for(i) for i in (60, 20, 0, -20, -60)] == ["High", "Elevated", "Neutral", "Low", "Easing bias"]
