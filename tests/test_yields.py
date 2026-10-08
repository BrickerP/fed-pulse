from datetime import date

import pytest

from fed_pulse import yields
from fed_pulse.fetch import FetchError
from fed_pulse.yields import merge_fred, parse_fred_csv, parse_treasury_csv


def test_parse_treasury_csv_sorted_with_spread(fixture_text):
    pts = parse_treasury_csv(fixture_text("treasury.csv"))
    assert [p.date for p in pts] == [date(2026, 7, 10), date(2026, 10, 6), date(2026, 10, 7)]
    last = pts[-1]
    assert (last.y2, last.y10, last.y30) == (4.77, 5.28, 5.67)
    assert last.spread_bp == 51.0


def test_parse_fred_csv_skips_missing(fixture_text):
    s = parse_fred_csv(fixture_text("fred_dgs10.csv"))
    assert s == {date(2026, 10, 1): 5.20, date(2026, 10, 5): 5.31}


def test_merge_fred_aligns_dates():
    pts = merge_fred({date(2026, 1, 2): 4.0}, {date(2026, 1, 2): 4.5, date(2026, 1, 5): 4.6}, {})
    assert len(pts) == 2 and pts[0].spread_bp == 50.0 and pts[1].y2 is None and pts[1].spread_bp is None


def test_fetch_yields_falls_back_to_fred(monkeypatch, fixture_text):
    def fake_get(url, timeout=0):
        if "treasury.gov" in url:
            raise FetchError("boom")
        return fixture_text("fred_dgs10.csv")

    monkeypatch.setattr(yields, "http_get", fake_get)
    s = yields.fetch_yields(days=30, today=date(2026, 10, 8))
    assert s.source.startswith("FRED") and s.latest.date == date(2026, 10, 5)
    assert "fallback" in s.notes[0]


def test_fetch_yields_raises_when_all_sources_fail(monkeypatch):
    def fake_get(url, timeout=0):
        raise FetchError("offline")

    monkeypatch.setattr(yields, "http_get", fake_get)
    with pytest.raises(FetchError):
        yields.fetch_yields(days=30, today=date(2026, 10, 8))
