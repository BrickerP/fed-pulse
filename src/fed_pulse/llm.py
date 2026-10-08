"""Optional Claude-written brief via the Anthropic Messages API (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .heuristic import Assessment
from .minutes import Minutes
from .yields import YieldSeries

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_MINUTES_CHARS = 60_000

SYSTEM_PROMPT = (
    "You are a careful macro analyst. Write a short, plain-English brief (150-220 words) "
    "on the current pressure for the Federal Reserve to raise interest rates, using ONLY the "
    "FOMC minutes and Treasury yield data provided. Cite concrete evidence (quote short phrases "
    "from the minutes, mention yield moves in basis points). Do not invent numbers and do not "
    "state a probability. Finish with a one-line bottom line. No headings, no bullet lists."
)


class LLMError(RuntimeError):
    pass


def build_prompt(minutes: Minutes | None, series: YieldSeries | None, a: Assessment) -> str:
    lines = []
    if minutes:
        label = minutes.meeting_label or minutes.meeting_date
        lines.append(f"FOMC minutes for the {label} meeting (released {minutes.released or 'n/a'}):")
        lines.append(minutes.text[:MAX_MINUTES_CHARS])
    else:
        lines.append("FOMC minutes: unavailable.")
    if a.trend:
        t = a.trend
        lines.append(
            f"\nTreasury par yields, {t.start_date} to {t.end_date}: latest 2Y={t.latest['y2']}%, "
            f"10Y={t.latest['y10']}%, 30Y={t.latest['y30']}%. Change over window: "
            f"2Y {t.change_bp['y2']} bp, 10Y {t.change_bp['y10']} bp, 30Y {t.change_bp['y30']} bp. "
            f"10Y-2Y spread {t.spread_bp} bp (change {t.spread_change_bp} bp)."
        )
    else:
        lines.append("\nTreasury yields: unavailable.")
    lines.append(
        f"\nFor reference, an offline keyword heuristic found {a.hawkish_hits} hawkish and "
        f"{a.dovish_hits} dovish phrase matches (index {a.index:+d}/100, '{a.label}')."
    )
    return "\n".join(lines)


def generate_brief(
    minutes: Minutes | None,
    series: YieldSeries | None,
    assessment: Assessment,
    api_key: str,
    model: str = DEFAULT_MODEL,
    timeout: float = 90.0,
) -> str:
    payload = {
        "model": model,
        "max_tokens": 2000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_prompt(minutes, series, assessment)}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise LLMError(f"Anthropic API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LLMError(f"Anthropic API request failed: {exc}") from exc
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise LLMError("Anthropic API returned no text content")
    return text
