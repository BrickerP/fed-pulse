"""Render the report as a single self-contained HTML file (Chart.js via CDN)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"


def _fmt(v, suffix="%", digits=2):
    return "n/a" if v is None else f"{v:.{digits}f}{suffix}"


def _delta(v):
    if v is None:
        return '<span class="muted">n/a</span>'
    cls = "up" if v > 0 else "down" if v < 0 else "muted"
    return f'<span class="{cls}">{v:+.0f} bp</span>'


def _highlight(text: str, phrases: list[str], cls: str) -> str:
    for p in sorted(set(phrases), key=len, reverse=True):
        text = re.sub(re.escape(escape(p)), lambda m: f'<mark class="{cls}">{m.group(0)}</mark>', text, flags=re.I)
    return text


def _pretty_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    off = dt.strftime("%z")
    return dt.strftime("%Y-%m-%d %H:%M") + (f" UTC{off[:3]}:{off[3:]}" if off else "")


def _safe_json(data) -> str:
    return json.dumps(data).replace("</", "<\\/")


def render_dashboard(report: dict) -> str:
    a = report["assessment"]
    mins = report.get("minutes") or {}
    ylds = report.get("yields") or {}
    latest = ylds.get("latest") or {}
    trend = ylds.get("trend") or {}
    chg = trend.get("change_bp") or {}
    brief = report["brief"]
    idx = a["index"]
    pos = (idx + 100) / 2  # 0..100 for the gauge marker

    if brief["method"] == "claude":
        badge = f'<span class="badge ai">Written by Claude &middot; {escape(brief["model"] or "")}</span>'
    else:
        badge = '<span class="badge heur">Offline heuristic &middot; not a probability model</span>'

    quotes = []
    for s in a["key_sentences"]:
        body = escape(s["text"])
        body = _highlight(body, s["hawkish"], "hawk")
        body = _highlight(body, s["dovish"], "dove")
        quotes.append(f'<blockquote class="{s["tag"]}"><span class="chip {s["tag"]}">{s["tag"]}</span> {body}</blockquote>')
    quotes_html = "\n".join(quotes) or '<p class="muted">No key sentences (minutes unavailable).</p>'
    phrases_html = " ".join(
        f'<span class="phrase">{escape(p["phrase"])} <b>{p["count"]}</b></span>' for p in a["top_phrases"]
    )
    comp = a["components"]
    comp_rows = "".join(
        f"<tr><td>{name}</td><td>{'n/a' if comp.get(key) is None else f'{comp[key]:+.2f}'}</td><td>{w}</td></tr>"
        for key, name, w in (
            ("minutes_tone", "Minutes tone (hawkish&minus;dovish)/(total)", "50%"),
            ("yield_trend", "2Y yield trend (&plusmn;50 bp = &plusmn;1)", "30%"),
            ("decision", "Recorded decision (hike +1 / hold 0 / cut &minus;1)", "20%"),
        )
    )
    warnings = "".join(f"<li>{escape(w)}</li>" for w in report.get("warnings", []))
    warnings_html = f'<div class="card warn"><b>Warnings</b><ul>{warnings}</ul></div>' if warnings else ""
    decision_html = (
        f'<p class="decision"><b>Decision recorded in the minutes:</b> {escape(mins["decision"])}</p>'
        if mins.get("decision")
        else ""
    )
    brief_html = "".join(f"<p>{escape(p)}</p>" for p in brief["text"].split("\n") if p.strip())

    minutes_src = (
        f'<li><b>FOMC minutes:</b> <a href="{escape(mins["url"])}">{escape(mins.get("meeting") or mins.get("meeting_date") or "")}</a>'
        f' (meeting date {escape(mins.get("meeting_date") or "n/a")}, released {escape(mins.get("released") or "n/a")}, '
        f'{mins.get("word_count", 0):,} words analysed) &mdash; Board of Governors of the Federal Reserve System</li>'
        if mins
        else "<li><b>FOMC minutes:</b> unavailable</li>"
    )
    yields_src = (
        f'<li><b>Yields:</b> <a href="{escape(ylds["source_url"])}">{escape(ylds["source"])}</a>, '
        f'{escape(trend.get("start_date", ""))} to {escape(latest.get("date", ""))} '
        f'({len(ylds.get("series", []))} trading days)</li>'
        if ylds
        else "<li><b>Yields:</b> unavailable</li>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fed Pulse &middot; rate-hike pressure brief</title>
<script src="{CHART_JS}"></script>
<style>
:root {{ --bg:#f6f7fb; --card:#fff; --ink:#1b2333; --muted:#6b7385; --line:#e4e7ef;
  --hawk:#c2410c; --dove:#1d4ed8; --accent:#0f766e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg); color:var(--ink); }}
.wrap {{ max-width:1120px; margin:0 auto; padding:28px 20px 40px; }}
header h1 {{ margin:0; font-size:28px; letter-spacing:-.5px; }}
header p {{ margin:4px 0 0; color:var(--muted); }}
.grid {{ display:grid; gap:16px; }}
.stats {{ grid-template-columns:1.4fr 1fr 1fr 1fr; margin:22px 0 16px; }}
.two {{ grid-template-columns:2fr 1fr; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px 20px; }}
.card h2 {{ margin:0 0 10px; font-size:15px; text-transform:uppercase; letter-spacing:.6px; color:var(--muted); }}
.big {{ font-size:34px; font-weight:700; letter-spacing:-1px; }}
.sub {{ color:var(--muted); font-size:13px; }}
.gauge {{ position:relative; height:10px; border-radius:6px; margin:12px 0 4px;
  background:linear-gradient(90deg,var(--dove),#cbd5e1 50%,var(--hawk)); }}
.gauge i {{ position:absolute; top:-5px; width:4px; height:20px; background:var(--ink); border-radius:2px; left:calc({pos:.1f}% - 2px); }}
.scale {{ display:flex; justify-content:space-between; font-size:11px; color:var(--muted); }}
.up {{ color:var(--hawk); font-weight:600; }} .down {{ color:var(--dove); font-weight:600; }} .muted {{ color:var(--muted); }}
.badge {{ display:inline-block; font-size:12px; padding:3px 10px; border-radius:999px; margin-bottom:8px; }}
.badge.ai {{ background:#ecfdf5; color:#047857; }} .badge.heur {{ background:#fff7ed; color:#9a3412; }}
.brief p {{ margin:0 0 10px; font-size:16px; }}
.decision {{ background:#f1f5f9; padding:10px 12px; border-radius:10px; font-size:14px; }}
canvas {{ max-height:300px; }}
blockquote {{ margin:0 0 12px; padding:10px 14px; border-left:4px solid var(--line); background:#fafbfd; border-radius:0 10px 10px 0; font-size:14px; }}
blockquote.hawkish {{ border-color:var(--hawk); }} blockquote.dovish {{ border-color:var(--dove); }}
.chip {{ font-size:11px; text-transform:uppercase; font-weight:700; letter-spacing:.5px; margin-right:6px; }}
.chip.hawkish {{ color:var(--hawk); }} .chip.dovish {{ color:var(--dove); }} .chip.mixed {{ color:var(--muted); }}
mark.hawk {{ background:#ffedd5; color:inherit; }} mark.dove {{ background:#dbeafe; color:inherit; }}
.phrase {{ display:inline-block; background:#f1f5f9; border-radius:999px; padding:3px 10px; margin:3px 2px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
td {{ padding:6px 4px; border-bottom:1px solid var(--line); }} td:nth-child(n+2) {{ text-align:right; white-space:nowrap; }}
.warn {{ border-color:#fcd34d; background:#fffbeb; margin-bottom:16px; }}
.sources li {{ margin-bottom:4px; }} a {{ color:var(--accent); }}
footer {{ margin-top:18px; font-size:12px; color:var(--muted); }}
@media (max-width:820px) {{ .stats,.two {{ grid-template-columns:1fr 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Fed Pulse</h1>
  <p>Rate-hike pressure brief from the latest FOMC minutes and the Treasury yield curve &middot; generated {escape(_pretty_ts(report["generated_at"]))}</p>
</header>
<div class="grid stats">
  <div class="card"><h2>Hike-pressure index</h2>
    <div class="big">{idx:+d} <span style="font-size:18px">{escape(a["label"])}</span></div>
    <div class="gauge"><i></i></div><div class="scale"><span>&minus;100 easing</span><span>0</span><span>+100 hike</span></div>
  </div>
  <div class="card"><h2>2-year</h2><div class="big">{_fmt(latest.get("y2"))}</div><div class="sub">{_delta(chg.get("y2"))} over window</div></div>
  <div class="card"><h2>10-year</h2><div class="big">{_fmt(latest.get("y10"))}</div><div class="sub">{_delta(chg.get("y10"))} over window</div></div>
  <div class="card"><h2>10Y&ndash;2Y spread</h2><div class="big">{_fmt(latest.get("spread_10y_2y_bp"), " bp", 0)}</div><div class="sub">{_delta(trend.get("spread_change_bp"))} over window</div></div>
</div>
{warnings_html}
<div class="card brief" style="margin-bottom:16px"><h2>The brief</h2>{badge}{brief_html}{decision_html}</div>
<div class="grid two" style="margin-bottom:16px">
  <div class="card"><h2>Treasury par yields (%)</h2><canvas id="yields"></canvas></div>
  <div class="card"><h2>How the index is built</h2>
    <table><tr><td><b>Component</b></td><td><b>Signal</b></td><td><b>Weight</b></td></tr>{comp_rows}</table>
    <p class="sub">{a["hawkish_hits"]} hawkish vs. {a["dovish_hits"]} dovish phrase matches. Missing components are dropped and weights re-normalised.</p>
  </div>
</div>
<div class="card" style="margin-bottom:16px"><h2>10Y &minus; 2Y spread (bp)</h2><canvas id="spread"></canvas></div>
<div class="grid two">
  <div class="card"><h2>Key sentences from the minutes</h2>{quotes_html}</div>
  <div class="card"><h2>Most frequent signal phrases</h2><div>{phrases_html or '<span class="muted">none</span>'}</div></div>
</div>
<div class="card sources" style="margin-top:16px"><h2>Sources &amp; timestamps</h2><ul>
  {minutes_src}
  {yields_src}
  <li><b>Generated:</b> {escape(_pretty_ts(report["generated_at"]))} by {escape(report["tool"])}</li>
</ul></div>
<footer>{escape(report["disclaimer"])} The hike-pressure index is a transparent keyword-and-trend heuristic, not a forecast or probability. Data from public U.S. government sources.</footer>
</div>
<script>
const REPORT = {_safe_json(report)};
(function () {{
  if (typeof Chart === "undefined" || !REPORT.yields) return;
  const s = REPORT.yields.series, labels = s.map(p => p.date);
  const line = (label, key, color) => ({{ label, data: s.map(p => p[key]), borderColor: color, backgroundColor: color,
    borderWidth: 2, pointRadius: 0, tension: .2, spanGaps: true }});
  const common = {{ responsive: true, maintainAspectRatio: true, animation: false, interaction: {{ mode: "index", intersect: false }},
    scales: {{ x: {{ ticks: {{ maxTicksLimit: 8 }}, grid: {{ display: false }} }} }} }};
  new Chart(document.getElementById("yields"), {{ type: "line", data: {{ labels, datasets: [
    line("2Y", "y2", "#c2410c"), line("10Y", "y10", "#0f766e"), line("30Y", "y30", "#1d4ed8")] }}, options: common }});
  new Chart(document.getElementById("spread"), {{ type: "bar", data: {{ labels, datasets: [{{ label: "10Y-2Y (bp)",
    data: s.map(p => p.spread_bp), backgroundColor: s.map(p => (p.spread_bp ?? 0) >= 0 ? "#0f766e99" : "#c2410c99") }}] }},
    options: {{ ...common, plugins: {{ legend: {{ display: false }} }},
      scales: {{ ...common.scales, y: {{ beginAtZero: true }} }} }} }});
}})();
</script>
</body>
</html>
"""
