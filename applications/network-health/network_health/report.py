"""Verdicts and the report (text and JSON)."""

from __future__ import annotations

import json
from datetime import datetime

from .checks import AREAS, CheckResult
from .models import BAD, GOOD, INFO, SKIPPED, WARN

RANK = {BAD: 0, WARN: 1, INFO: 2, GOOD: 3, SKIPPED: 4}

OVERALL_TEXT = {
    GOOD: "GOOD - the network performs well and nothing in its visible "
          "configuration needs to change.",
    WARN: "WARN - the network works, but some things should be improved "
          "(see the findings).",
    BAD: "BAD - there are problems that should be fixed (see the findings).",
    "unknown": "UNKNOWN - no check could run.",
}


def area_verdict(results: list[CheckResult], area: str) -> str:
    """bad if any check is bad, warn if any is warn, good if any ran
    (info counts as good), otherwise skipped."""
    statuses = {r.status for r in results if r.area == area}
    if BAD in statuses:
        return BAD
    if WARN in statuses:
        return WARN
    if statuses & {GOOD, INFO}:
        return GOOD
    return SKIPPED


def overall_verdict(results: list[CheckResult]) -> str:
    verdicts = {area_verdict(results, a) for a in AREAS}
    if BAD in verdicts:
        return BAD
    if WARN in verdicts:
        return WARN
    if GOOD in verdicts:
        return GOOD
    return "unknown"


def ranked_findings(results: list[CheckResult]) -> list[CheckResult]:
    findings = [r for r in results if r.status in (BAD, WARN, INFO)]
    order = {a: i for i, a in enumerate(AREAS)}
    return sorted(findings, key=lambda r: (RANK[r.status], order.get(r.area, 99)))


def _area_line(results: list[CheckResult], area: str) -> str:
    verdict = area_verdict(results, area)
    in_area = [r for r in results if r.area == area]
    if verdict == SKIPPED:
        reason = in_area[0].summary if in_area else "no checks"
        return f"  {area:<15} SKIPPED  {reason}"
    counts = {s: sum(1 for r in in_area if r.status == s) for s in (BAD, WARN, INFO)}
    parts = [f"{n} {s}" for s, n in counts.items() if n]
    ran = sum(1 for r in in_area if r.status != SKIPPED)
    detail = ", ".join(parts) if parts else "all good"
    return f"  {area:<15} {verdict.upper():<8} {ran} checks, {detail}"


def build_text(results: list[CheckResult], *, contacted: list[str],
               generated: datetime, platform: str, saved_to: str | None = None) -> str:
    overall = overall_verdict(results)
    lines = [
        f"Network health - passive mode - {platform} - "
        f"{generated.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Overall verdict: {OVERALL_TEXT[overall]}",
        "",
    ]
    lines += [_area_line(results, a) for a in AREAS]

    findings = ranked_findings(results)
    lines += ["", "Findings, most serious first:"]
    if not findings:
        lines.append("  None.")
    for r in findings:
        lines.append(f"  [{r.status.upper()}] {r.area} - {r.title}: {r.summary}")
        if r.why:
            lines.append(f"      Why: {r.why}")
        if r.fix:
            lines.append(f"      Fix: {r.fix}")

    passed = [r for r in results if r.status == GOOD]
    if passed:
        lines += ["", "Checks that passed:"]
        lines += [f"  [GOOD] {r.area} - {r.title}: {r.summary}" for r in passed]

    skipped = [r for r in results if r.status == SKIPPED]
    if skipped:
        lines += ["", "Skipped checks:"]
        lines += [f"  [SKIPPED] {r.area} - {r.title}: {r.summary}" for r in skipped]

    lines += ["", "Contacted in this run:"]
    lines += [f"  - {c}" for c in contacted] or ["  - nothing"]
    if saved_to:
        lines += ["", f"Snapshot saved to {saved_to}"]
    return "\n".join(lines) + "\n"


def build_json(results: list[CheckResult], *, contacted: list[str],
               generated: datetime, platform: str) -> dict:
    return {
        "tool": "network-health",
        "mode": "passive",
        "platform": platform,
        "generated": generated.isoformat(timespec="seconds"),
        "overall": overall_verdict(results),
        "areas": {a: area_verdict(results, a) for a in AREAS},
        "findings": [r.id for r in ranked_findings(results)],
        "results": [r.to_dict() for r in results],
        "contacted": contacted,
    }


def to_json_text(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
