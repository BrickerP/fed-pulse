"""Locate, download and parse the latest FOMC minutes from federalreserve.gov."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser

from .fetch import FetchError, http_get

BASE_URL = "https://www.federalreserve.gov"
CALENDAR_URL = f"{BASE_URL}/monetarypolicy/fomccalendars.htm"

_LINK_RE = re.compile(r'href="(?P<path>/monetarypolicy/fomcminutes(?P<ymd>\d{8})\.htm)"')
_RELEASED_RE = re.compile(r"\(Released\s+([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})\)")
_MEETING_RE = re.compile(r"<p>\s*<strong>\s*([^<]{3,60}?\d{4})\s*</strong>")
_DECISION_RE = re.compile(
    r"[^.]*?\b(?:decided|agreed|voted)\s+to\s+(?P<action>raise|increase|lower|reduce|maintain|keep)"
    r"\s+the\s+target\s+range\s+for\s+the\s+federal\s+funds\s+rate[^.]*\.",
    re.IGNORECASE,
)
_ABBREVIATIONS = ("U.S.", "e.g.", "i.e.", "a.m.", "p.m.", "No.", "Mr.", "Ms.", "Dr.", "vs.", "St.")
# Text after these section headings is procedural (votes, attendance, footnotes).
_END_MARKERS = ("<strong>Notation Vote", 'id="lastUpdate"', "<hr")
# Footnote markers and bold section headings are not part of the prose.
_SKIP_TAGS = ("sup", "strong", "script", "style")


@dataclass
class MinutesLink:
    url: str
    meeting_date: date
    released: str | None = None


@dataclass
class Minutes:
    url: str
    meeting_date: date | None
    meeting_label: str | None
    released: str | None
    paragraphs: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def sentences(self) -> list[str]:
        out: list[str] = []
        for para in self.paragraphs:
            out.extend(split_sentences(para))
        return out

    @property
    def decision(self) -> str | None:
        return extract_decision(self.text)


def find_minutes_links(calendar_html: str) -> list[MinutesLink]:
    """Return all HTML minutes links on the calendar page, newest meeting first."""
    seen: dict[str, MinutesLink] = {}
    for m in _LINK_RE.finditer(calendar_html):
        path = m.group("path")
        if path in seen:
            continue
        try:
            meeting = datetime.strptime(m.group("ymd"), "%Y%m%d").date()
        except ValueError:
            continue
        rel = _RELEASED_RE.search(calendar_html, m.end(), m.end() + 400)
        seen[path] = MinutesLink(BASE_URL + path, meeting, rel.group(1) if rel else None)
    return sorted(seen.values(), key=lambda link: link.meeting_date, reverse=True)


class _ParagraphParser(HTMLParser):
    """Collect visible text of <p> elements, skipping footnote markers (<sup>)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._buf: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._flush()
            self._buf = []
        elif tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "br" and self._buf is not None:
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag == "p":
            self._flush()
        elif tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._buf is not None and not self._skip:
            self._buf.append(data)

    def _flush(self):
        if self._buf is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.paragraphs.append(text)
        self._buf = None

    def close(self):
        super().close()
        self._flush()


def parse_minutes_html(
    html: str,
    url: str = "",
    meeting_date: date | None = None,
    released: str | None = None,
) -> Minutes:
    """Extract the substantive paragraphs of an FOMC minutes HTML page."""
    start = html.find('id="article"')
    body = html[start:] if start != -1 else html
    cut = [i for i in (body.find(mk) for mk in _END_MARKERS) if i > 0]
    if cut:
        body = body[: min(cut)]
    label_match = _MEETING_RE.search(body)
    parser = _ParagraphParser()
    parser.feed(body)
    parser.close()
    paragraphs = [p for p in parser.paragraphs if len(p.split()) >= 6]
    if not paragraphs:
        raise ValueError("no minutes text found in page")
    if meeting_date is None:
        m = re.search(r"fomcminutes(\d{8})", url)
        if m:
            meeting_date = datetime.strptime(m.group(1), "%Y%m%d").date()
    label = unescape(label_match.group(1)).strip() if label_match else None
    return Minutes(url, meeting_date, label, released, paragraphs)


def split_sentences(text: str) -> list[str]:
    """Naive sentence splitter that keeps common abbreviations (e.g. "U.S.") intact."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\u201c(])", text.strip())
    out: list[str] = []
    for part in parts:
        if out and out[-1].endswith(_ABBREVIATIONS):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return [s.strip() for s in out if s.strip()]


def extract_decision(text: str) -> str | None:
    """Return the sentence announcing the federal funds target-range decision, if any."""
    m = _DECISION_RE.search(text)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def decision_direction(decision: str | None) -> int:
    """+1 for a hike, -1 for a cut, 0 for a hold/unknown."""
    if not decision:
        return 0
    m = _DECISION_RE.search(decision)
    action = (m.group("action") if m else "").lower()
    if action in ("raise", "increase"):
        return 1
    if action in ("lower", "reduce"):
        return -1
    return 0


def fetch_latest_minutes(timeout: float = 45.0) -> Minutes:
    """Find the newest minutes on the FOMC calendar and parse them."""
    links = find_minutes_links(http_get(CALENDAR_URL, timeout=timeout))
    if not links:
        raise FetchError(f"no minutes links found on {CALENDAR_URL}")
    errors = []
    for link in links[:3]:  # fall back to older minutes if the newest page misbehaves
        try:
            html = http_get(link.url, timeout=timeout)
            return parse_minutes_html(html, link.url, link.meeting_date, link.released)
        except (FetchError, ValueError) as exc:
            errors.append(f"{link.url}: {exc}")
    raise FetchError("could not parse recent minutes: " + "; ".join(errors))
