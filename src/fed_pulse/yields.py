"""Daily Treasury par yields (2Y/10Y/30Y) from Treasury.gov, with FRED as a fallback."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .fetch import FetchError, http_get

TREASURY_CSV = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
TREASURY_PAGE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
FRED_SERIES = {"y2": "DGS2", "y10": "DGS10", "y30": "DGS30"}


@dataclass
class YieldPoint:
    date: date
    y2: float | None
    y10: float | None
    y30: float | None

    @property
    def spread_bp(self) -> float | None:
        """10Y minus 2Y, in basis points."""
        if self.y2 is None or self.y10 is None:
            return None
        return round((self.y10 - self.y2) * 100, 1)


@dataclass
class YieldSeries:
    points: list[YieldPoint]
    source: str
    source_url: str
    notes: list[str] = field(default_factory=list)

    @property
    def latest(self) -> YieldPoint | None:
        return self.points[-1] if self.points else None


def _num(value: str | None) -> float | None:
    value = (value or "").strip()
    if value in ("", ".", "N/A", "NA"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_treasury_csv(text: str) -> list[YieldPoint]:
    """Parse Treasury's daily par yield curve CSV (columns like "2 Yr", "10 Yr")."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    points = []
    for row in reader:
        raw = (row.get("Date") or "").strip()
        try:
            d = datetime.strptime(raw, "%m/%d/%Y").date()
        except ValueError:
            continue
        points.append(YieldPoint(d, _num(row.get("2 Yr")), _num(row.get("10 Yr")), _num(row.get("30 Yr"))))
    return sorted(points, key=lambda p: p.date)


def parse_fred_csv(text: str) -> dict[date, float]:
    """Parse a fredgraph.csv download (first column date, second column value)."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    out: dict[date, float] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        try:
            d = datetime.strptime(row[0].strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        v = _num(row[1])
        if v is not None:
            out[d] = v
    return out


def merge_fred(y2: dict, y10: dict, y30: dict) -> list[YieldPoint]:
    dates = sorted(set(y2) | set(y10) | set(y30))
    return [YieldPoint(d, y2.get(d), y10.get(d), y30.get(d)) for d in dates]


def _window(points: list[YieldPoint], start: date) -> list[YieldPoint]:
    return [p for p in points if p.date >= start and (p.y2 or p.y10 or p.y30)]


def fetch_yields(days: int = 90, timeout: float = 60.0, today: date | None = None) -> YieldSeries:
    """Fetch roughly ``days`` calendar days of 2Y/10Y/30Y yields."""
    today = today or date.today()
    start = today - timedelta(days=days)
    errors: list[str] = []

    try:
        points: list[YieldPoint] = []
        for year in range(start.year, today.year + 1):
            points.extend(parse_treasury_csv(http_get(TREASURY_CSV.format(year=year), timeout=timeout)))
        points = _window(sorted(points, key=lambda p: p.date), start)
        if points:
            return YieldSeries(points, "U.S. Treasury daily par yield curve", TREASURY_PAGE)
        errors.append("Treasury CSV returned no rows in window")
    except FetchError as exc:
        errors.append(str(exc))

    try:
        series = {
            key: parse_fred_csv(http_get(FRED_CSV.format(series=sid, start=start.isoformat()), timeout=timeout))
            for key, sid in FRED_SERIES.items()
        }
        points = _window(merge_fred(series["y2"], series["y10"], series["y30"]), start)
        if points:
            return YieldSeries(
                points,
                "FRED (DGS2, DGS10, DGS30)",
                "https://fred.stlouisfed.org/series/DGS10",
                notes=["Treasury.gov unavailable; used FRED fallback: " + "; ".join(errors)],
            )
        errors.append("FRED returned no rows in window")
    except FetchError as exc:
        errors.append(str(exc))
    raise FetchError("could not fetch yields: " + "; ".join(errors))
