"""Command-line entry point: ``fed-pulse``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .dashboard import render_dashboard
from .fetch import FetchError
from .heuristic import assess, heuristic_brief
from .llm import DEFAULT_MODEL, LLMError, generate_brief
from .minutes import fetch_latest_minutes
from .report import build_report
from .yields import fetch_yields


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(f"[fed-pulse] {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fed-pulse",
        description="Brief on Fed rate-hike pressure from the latest FOMC minutes and Treasury yields.",
        epilog="Set ANTHROPIC_API_KEY to have Claude write the brief; otherwise an offline heuristic is used. "
        "Not financial advice.",
    )
    p.add_argument("-o", "--output", metavar="PATH", help="HTML dashboard path (default: fed-pulse.html)")
    p.add_argument("--json", action="store_true", help="print the full report as JSON to stdout (no HTML unless -o is given)")
    p.add_argument("--days", type=int, default=90, help="calendar days of yield history (default: 90)")
    p.add_argument(
        "--model",
        default=os.environ.get("FED_PULSE_MODEL", DEFAULT_MODEL),
        help=f"Anthropic model id (default: $FED_PULSE_MODEL or {DEFAULT_MODEL})",
    )
    p.add_argument("--no-llm", action="store_true", help="always use the offline heuristic brief")
    p.add_argument("--timeout", type=float, default=60.0, help="per-request timeout in seconds (default: 60)")
    p.add_argument("--open", action="store_true", help="open the dashboard in your browser when done")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress messages on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    q = args.quiet
    warnings: list[str] = []

    _log("fetching latest FOMC minutes from federalreserve.gov ...", q)
    try:
        minutes = fetch_latest_minutes(timeout=args.timeout)
        _log(f"minutes: {minutes.meeting_label or minutes.meeting_date} ({minutes.word_count:,} words)", q)
    except (FetchError, ValueError) as exc:
        minutes = None
        warnings.append(f"FOMC minutes unavailable: {exc}")
        _log(warnings[-1], q)

    _log(f"fetching {args.days} days of Treasury yields ...", q)
    try:
        series = fetch_yields(days=args.days, timeout=args.timeout)
        warnings.extend(series.notes)
        last = series.latest
        _log(f"yields: {series.source}, {len(series.points)} days through {last.date} (10Y {last.y10}%)", q)
    except FetchError as exc:
        series = None
        warnings.append(f"Treasury yields unavailable: {exc}")
        _log(warnings[-1], q)

    if minutes is None and series is None:
        print("fed-pulse: could not fetch any data; check your network connection.", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        return 2

    assessment = assess(minutes, series)
    brief, method, model = heuristic_brief(assessment, minutes), "heuristic", None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key and not args.no_llm:
        _log(f"asking Claude ({args.model}) for the brief ...", q)
        try:
            brief, method, model = generate_brief(minutes, series, assessment, api_key, args.model), "claude", args.model
        except LLMError as exc:
            warnings.append(f"Claude brief failed, using heuristic instead: {exc}")
            _log(warnings[-1], q)

    report = build_report(minutes, series, assessment, brief, method, model, warnings)

    out = args.output or (None if args.json else "fed-pulse.html")
    if out:
        path = Path(out).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_dashboard(report), encoding="utf-8")
        _log(f"dashboard written to {path}", q)
        if args.open:
            webbrowser.open(path.as_uri())
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _log(f"hike-pressure index {assessment.index:+d} ({assessment.label}) [{method}]", q)
        if not q:
            print("\n" + brief + "\n", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
