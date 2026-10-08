from datetime import date

from fed_pulse.minutes import (
    decision_direction,
    extract_decision,
    find_minutes_links,
    parse_minutes_html,
    split_sentences,
)


def test_find_minutes_links_newest_first(fixture_text):
    links = find_minutes_links(fixture_text("calendar.html"))
    assert [link.meeting_date for link in links] == [date(2026, 9, 16), date(2026, 1, 28), date(2025, 12, 10)]
    assert links[0].url == "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260916.htm"
    assert links[0].released == "October 07, 2026"


def test_parse_minutes_extracts_article_prose_only(fixture_text):
    m = parse_minutes_html(fixture_text("minutes.html"), url="https://x/fomcminutes20260916.htm")
    assert m.meeting_date == date(2026, 9, 16)
    assert m.meeting_label == "September 15\u201316, 2026"
    text = m.text
    assert text.startswith("A joint meeting")  # bold heading dropped
    assert "Navigation paragraph" not in text  # outside #article
    assert "Notation Vote" not in text and "Attendance" not in text  # procedural tail cut
    assert "referenced as the FOMC" not in text  # footnotes cut
    assert "Governors.1" not in text  # <sup> footnote markers removed


def test_split_sentences_keeps_abbreviations():
    s = split_sentences("The manager noted that U.S. Treasury yields rose. Inflation stayed high.")
    assert s == ["The manager noted that U.S. Treasury yields rose.", "Inflation stayed high."]


def test_extract_decision(fixture_text):
    m = parse_minutes_html(fixture_text("minutes.html"))
    assert m.decision.startswith("The Committee decided to raise the target range")
    assert decision_direction(m.decision) == 1
    assert decision_direction(extract_decision("Members voted to lower the target range for the federal funds rate.")) == -1
    assert decision_direction(extract_decision("The Committee decided to maintain the target range for the federal funds rate.")) == 0
    assert extract_decision("Nothing about rates here.") is None
