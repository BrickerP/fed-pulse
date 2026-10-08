"""Assemble a JSON-serialisable report from the fetched data and assessment."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from . import __version__
from .heuristic import Assessment
from .minutes import CALENDAR_URL, Minutes
from .yields import YieldSeries


def build_report(
    minutes: Minutes | None,
    series: YieldSeries | None,
    assessment: Assessment,
    brief: str,
    brief_method: str,
    model: str | None = None,
    warnings: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc).astimezone()
    latest = series.latest if series else None
    return {
        "tool": f"fed-pulse {__version__}",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "minutes": None
        if minutes is None
        else {
            "meeting": minutes.meeting_label,
            "meeting_date": minutes.meeting_date.isoformat() if minutes.meeting_date else None,
            "released": minutes.released,
            "url": minutes.url,
            "calendar_url": CALENDAR_URL,
            "decision": assessment.decision,
            "word_count": minutes.word_count,
        },
        "yields": None
        if series is None
        else {
            "source": series.source,
            "source_url": series.source_url,
            "notes": series.notes,
            "latest": None
            if latest is None
            else {
                "date": latest.date.isoformat(),
                "y2": latest.y2,
                "y10": latest.y10,
                "y30": latest.y30,
                "spread_10y_2y_bp": latest.spread_bp,
            },
            "trend": asdict(assessment.trend) if assessment.trend else None,
            "series": [
                {"date": p.date.isoformat(), "y2": p.y2, "y10": p.y10, "y30": p.y30, "spread_bp": p.spread_bp}
                for p in series.points
            ],
        },
        "assessment": {
            "method": "heuristic (keyword scan + yield trend + recorded decision); not a probability model",
            "index": assessment.index,
            "scale": "-100 (easing bias) .. +100 (high hike pressure)",
            "label": assessment.label,
            "components": assessment.components,
            "hawkish_hits": assessment.hawkish_hits,
            "dovish_hits": assessment.dovish_hits,
            "top_phrases": [{"phrase": p, "count": c} for p, c in assessment.top_phrases],
            "key_sentences": [
                {"text": s.text, "tag": s.tag, "hawkish": s.hawkish, "dovish": s.dovish}
                for s in assessment.key_sentences
            ],
        },
        "brief": {"method": brief_method, "model": model, "text": brief},
        "warnings": warnings or [],
        "disclaimer": "Informational only. Not financial advice.",
    }
