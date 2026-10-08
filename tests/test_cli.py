import json

from fed_pulse import cli
from fed_pulse.minutes import parse_minutes_html
from fed_pulse.yields import YieldSeries, parse_treasury_csv


def _patch(monkeypatch, fixture_text):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        cli, "fetch_latest_minutes",
        lambda timeout=0: parse_minutes_html(fixture_text("minutes.html"), "https://x/fomcminutes20260916.htm"),
    )
    monkeypatch.setattr(
        cli, "fetch_yields",
        lambda days=90, timeout=0: YieldSeries(parse_treasury_csv(fixture_text("treasury.csv")), "Treasury", "https://t"),
    )


def test_cli_json_and_dashboard(monkeypatch, fixture_text, tmp_path, capsys):
    _patch(monkeypatch, fixture_text)
    out = tmp_path / "dash.html"
    assert cli.main(["--json", "-q", "-o", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["brief"]["method"] == "heuristic"
    assert report["minutes"]["meeting_date"] == "2026-09-16"
    assert report["yields"]["latest"]["y10"] == 5.28
    html = out.read_text()
    assert "Fed Pulse" in html and "chart.umd.min.js" in html and "not a probability model" in html
    assert html.count("</script>") == 2  # embedded JSON cannot break out of its <script> tag


def test_dashboard_escapes_untrusted_text(monkeypatch, fixture_text, tmp_path):
    _patch(monkeypatch, fixture_text)
    from fed_pulse.dashboard import render_dashboard
    from fed_pulse.heuristic import assess
    from fed_pulse.report import build_report

    a = assess(None, None)
    html = render_dashboard(build_report(None, None, a, "<script>alert(1)</script>", "heuristic"))
    assert "<script>alert(1)</script>" not in html


def test_cli_exits_2_when_everything_fails(monkeypatch):
    from fed_pulse.fetch import FetchError

    def boom(*a, **k):
        raise FetchError("offline")

    monkeypatch.setattr(cli, "fetch_latest_minutes", boom)
    monkeypatch.setattr(cli, "fetch_yields", boom)
    assert cli.main(["-q", "--json"]) == 2
