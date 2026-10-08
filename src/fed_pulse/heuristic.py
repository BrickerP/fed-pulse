"""Transparent, offline rate-hike-pressure heuristic.

This is deliberately simple and explainable. It is NOT a probability model:
it counts hawkish vs. dovish phrases in the minutes, looks at the recent
direction of the policy-sensitive 2-year yield, and notes the policy decision
recorded in the minutes. Each component is scaled to [-1, 1] and blended.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .minutes import Minutes, decision_direction
from .yields import YieldSeries

_RAW_HAWKISH = [
    r"upside risks? to (?:the )?(?:inflation|outlook for inflation)",
    r"inflation (?:had )?(?:remained|remains|was|stayed) (?:elevated|high|persistent|stubborn|sticky)",
    r"persistent(?:ly)? (?:high |elevated )?inflation",
    r"elevated inflation",
    r"inflation(?:ary)? pressures?",
    r"(?:further|additional) (?:policy )?(?:firming|tightening)",
    r"policy firming",
    r"(?:raise|raising|increase in|increasing|hike in) the target range",
    r"(?:higher|restrictive) for longer",
    r"remain (?:sufficiently )?restrictive",
    r"(?:tight|strong|robust|resilient) (?:labor market|economy|economic activity|demand|consumer spending)",
    r"not yet confident",
    r"inflation expectations (?:had )?(?:risen|rose|moved up|increased|drifted up)",
    r"(?:wage|price) pressures",
    r"premature to (?:ease|cut|lower)",
    r"overheat(?:ing)?",
]
_RAW_DOVISH = [
    r"downside risks? to (?:the )?(?:economic activity|employment|growth|labor market|outlook)",
    r"(?:lower|lowering|reduce|reducing|reduction in|cut in|cutting) the target range",
    r"policy easing",
    r"rate cuts?",
    r"(?:labor market|labor demand|hiring|economic activity|economic growth|demand|consumer spending) (?:had )?(?:softened|slowed|weakened|cooled|moderated)",
    r"(?:softening|weakening|cooling|slowing) (?:in |of )?(?:the )?(?:labor market|economy|economic activity|growth|demand)",
    r"inflation (?:had |has )?(?:eased|moderated|declined|slowed|come down|fell|fallen)",
    r"disinflation(?:ary)?",
    r"unemployment rate (?:had )?(?:moved up|rose|increased|edged up|risen)",
    r"(?:financial|credit) conditions (?:had )?tightened",
    r"less restrictive",
    r"accommodative",
    r"recession",
]
HAWKISH = [re.compile(rf"\b{p}\b", re.IGNORECASE) for p in _RAW_HAWKISH]
DOVISH = [re.compile(rf"\b{p}\b", re.IGNORECASE) for p in _RAW_DOVISH]

# Blend weights for the three components (sum to 1).
WEIGHTS = {"minutes_tone": 0.5, "yield_trend": 0.3, "decision": 0.2}
# A 50 bp move in the 2Y over the window maps to a full +/-1 yield signal.
YIELD_FULL_SCALE_BP = 50.0


@dataclass
class ScoredSentence:
    text: str
    hawkish: list[str] = field(default_factory=list)
    dovish: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return len(self.hawkish) - len(self.dovish)

    @property
    def tag(self) -> str:
        return "hawkish" if self.score > 0 else "dovish" if self.score < 0 else "mixed"


@dataclass
class YieldTrend:
    start_date: str
    end_date: str
    days: int
    change_bp: dict[str, float | None]
    latest: dict[str, float | None]
    spread_bp: float | None
    spread_change_bp: float | None


@dataclass
class Assessment:
    index: int  # -100 (strong easing bias) .. +100 (strong hike pressure)
    label: str
    components: dict[str, float | None]
    hawkish_hits: int
    dovish_hits: int
    top_phrases: list[tuple[str, int]]
    key_sentences: list[ScoredSentence]
    trend: YieldTrend | None
    decision: str | None
    method: str = "heuristic"


def score_sentence(text: str) -> ScoredSentence:
    hawk = [m.group(0).lower() for rx in HAWKISH for m in rx.finditer(text)]
    dove = [m.group(0).lower() for rx in DOVISH for m in rx.finditer(text)]
    return ScoredSentence(text, hawk, dove)


def minutes_tone(scored: list[ScoredSentence]) -> float | None:
    """(hawkish - dovish) / (hawkish + dovish), in [-1, 1]; None if no hits."""
    h = sum(len(s.hawkish) for s in scored)
    d = sum(len(s.dovish) for s in scored)
    return None if h + d == 0 else (h - d) / (h + d)


def _delta_bp(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round((b - a) * 100, 1)


def yield_trend(series: YieldSeries) -> YieldTrend | None:
    pts = series.points
    if len(pts) < 2:
        return None
    first, last = pts[0], pts[-1]
    return YieldTrend(
        start_date=first.date.isoformat(),
        end_date=last.date.isoformat(),
        days=(last.date - first.date).days,
        change_bp={k: _delta_bp(getattr(first, k), getattr(last, k)) for k in ("y2", "y10", "y30")},
        latest={k: getattr(last, k) for k in ("y2", "y10", "y30")},
        spread_bp=last.spread_bp,
        spread_change_bp=(
            None
            if first.spread_bp is None or last.spread_bp is None
            else round(last.spread_bp - first.spread_bp, 1)
        ),
    )


def label_for(index: int) -> str:
    if index >= 35:
        return "High"
    if index >= 15:
        return "Elevated"
    if index > -15:
        return "Neutral"
    if index > -35:
        return "Low"
    return "Easing bias"


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def assess(minutes: Minutes | None, series: YieldSeries | None, n_quotes: int = 6) -> Assessment:
    """Blend minutes tone, 2Y yield trend and the recorded decision into one index."""
    scored = [score_sentence(s) for s in minutes.sentences] if minutes else []
    tone = minutes_tone(scored)
    trend = yield_trend(series) if series else None
    y_sig = None
    if trend and trend.change_bp.get("y2") is not None:
        y_sig = _clamp(trend.change_bp["y2"] / YIELD_FULL_SCALE_BP)
    decision = minutes.decision if minutes else None
    dec_sig = float(decision_direction(decision)) if decision else None

    components = {"minutes_tone": tone, "yield_trend": y_sig, "decision": dec_sig}
    used = {k: v for k, v in components.items() if v is not None}
    if used:  # re-normalise weights over the components we actually have
        total_w = sum(WEIGHTS[k] for k in used)
        blended = sum(WEIGHTS[k] * v for k, v in used.items()) / total_w
    else:
        blended = 0.0
    index = int(round(100 * blended))

    phrases = Counter(p for s in scored for p in s.hawkish + s.dovish)
    ranked = sorted(
        (s for s in scored if s.hawkish or s.dovish),
        key=lambda s: (abs(s.score), len(s.hawkish) + len(s.dovish)),
        reverse=True,
    )
    return Assessment(
        index=index,
        label=label_for(index),
        components={k: (None if v is None else round(v, 3)) for k, v in components.items()},
        hawkish_hits=sum(len(s.hawkish) for s in scored),
        dovish_hits=sum(len(s.dovish) for s in scored),
        top_phrases=phrases.most_common(8),
        key_sentences=ranked[:n_quotes],
        trend=trend,
        decision=decision,
    )


def _fmt_bp(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.0f} bp"


def heuristic_brief(a: Assessment, minutes: Minutes | None) -> str:
    """Plain-English summary of the heuristic result."""
    parts = []
    if minutes:
        tone = a.components["minutes_tone"]
        lean = "balanced"
        if tone is not None and tone > 0.15:
            lean = "hawkish"
        elif tone is not None and tone < -0.15:
            lean = "dovish"
        when = minutes.meeting_label or (minutes.meeting_date.isoformat() if minutes.meeting_date else "latest")
        parts.append(
            f"The minutes of the {when} FOMC meeting read {lean}: {a.hawkish_hits} hawkish vs. "
            f"{a.dovish_hits} dovish phrase matches."
        )
        direction = decision_direction(a.decision) if a.decision else None
        if direction is not None:
            verb = {1: "an increase in", -1: "a cut to", 0: "no change to"}[direction]
            parts.append(f"They record {verb} the federal funds target range.")
    else:
        parts.append("The FOMC minutes could not be retrieved, so this read uses yields only.")
    t = a.trend
    if t:
        y2, y10 = t.latest.get("y2"), t.latest.get("y10")
        parts.append(
            f"Over the {t.days} days to {t.end_date}, the 2-year Treasury yield moved "
            f"{_fmt_bp(t.change_bp['y2'])} to {y2:.2f}% and the 10-year {_fmt_bp(t.change_bp['y10'])} "
            f"to {y10:.2f}%; the 10Y-2Y spread is {t.spread_bp:+.0f} bp."
            if y2 is not None and y10 is not None and t.spread_bp is not None
            else f"Yield data covers {t.start_date} to {t.end_date}."
        )
        c2 = t.change_bp.get("y2")
        if c2 is not None and abs(c2) >= 10:
            parts.append(
                "A rising 2-year yield suggests markets are pricing a higher policy path."
                if c2 > 0
                else "A falling 2-year yield suggests markets are pricing a lower policy path."
            )
    else:
        parts.append("Treasury yield data was unavailable, so this read uses the minutes only.")
    parts.append(
        f"Heuristic rate-hike pressure index: {a.index:+d} on a -100..+100 scale ({a.label}). "
        "This is a transparent keyword-and-trend heuristic, not a probability model."
    )
    return " ".join(parts)
