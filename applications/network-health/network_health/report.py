"""Verdicts and the report (text and JSON)."""

from __future__ import annotations

import json
from datetime import datetime

from .checks import AREAS, DEVICES, CheckResult
from .device_checks import HAZARD_LABELS
from .devices import Device, DeviceScan
from .models import BAD, GOOD, INFO, SKIPPED, WARN
from .oui import KIND_SHORT

RANK = {BAD: 0, WARN: 1, INFO: 2, GOOD: 3, SKIPPED: 4}

OVERALL_TEXT = {
    GOOD: "GOOD - the network performs well and nothing in its visible "
          "configuration needs to change.",
    WARN: "WARN - the network works, but some things should be improved "
          "(see the findings).",
    BAD: "BAD - there are problems that should be fixed (see the findings).",
    "unknown": "UNKNOWN - no check could run.",
}


def areas_of(results: list[CheckResult]) -> tuple[str, ...]:
    """The four areas of passive mode, plus Devices when the device scan ran."""
    if any(r.area == DEVICES for r in results):
        return AREAS + (DEVICES,)
    return AREAS


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
    verdicts = {area_verdict(results, a) for a in areas_of(results)}
    if BAD in verdicts:
        return BAD
    if WARN in verdicts:
        return WARN
    if GOOD in verdicts:
        return GOOD
    return "unknown"


def ranked_findings(results: list[CheckResult]) -> list[CheckResult]:
    findings = [r for r in results if r.status in (BAD, WARN, INFO)]
    order = {a: i for i, a in enumerate(areas_of(results))}
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


def _port_text(device: Device) -> str:
    if not device.open_ports:
        return "none" if device.ports_complete else "none found (not fully checked)"
    text = ", ".join(f"{p} {device.services[p].name}" if p in device.services else str(p)
                     for p in device.open_ports)
    return text if device.ports_complete else text + " (not fully checked)"


def _vendor_text(device: Device) -> str:
    parts = []
    if device.vendor:
        parts.append(device.vendor)
    elif device.private_mac:
        parts.append("private MAC address")
    kind = KIND_SHORT.get(device.kind)
    if kind:
        parts.append(f"probably {kind}")
    return ", ".join(parts) or "-"


def devices_table(scan: DeviceScan) -> list[str]:
    """The Devices section: one row per device with IP, MAC, name, vendor,
    open ports and hazards."""
    lines = ["", f"Devices on {scan.network} ({len(scan.devices)} found; this computer, "
                 f"{scan.own_address}, is not listed; the scan took "
                 f"{scan.elapsed_s:.0f} s):"]
    if not scan.devices:
        lines.append("  None found.")
    else:
        header = ("IP", "MAC", "Name", "Vendor", "Open ports", "Hazards")
        rows = [header]
        for d in scan.devices:
            name = d.name or ("(default gateway)" if d.is_gateway else "-")
            hazards = ", ".join(HAZARD_LABELS[h] for h in d.hazards if h in HAZARD_LABELS)
            rows.append((d.ip, d.mac or "-", name, _vendor_text(d), _port_text(d),
                         hazards or "-"))
        widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
        for index, row in enumerate(rows):
            line = "  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
            lines.append(line.rstrip())
            if index == 0:
                lines.append("  " + "  ".join("-" * w for w in widths))
    lines.append("  Vendor and type come from a short list of MAC prefixes and from what "
                 "the device says about itself; they are guesses.")
    lines.append("  Only IPv4 addresses are scanned; devices that are reachable over IPv6 "
                 "only are not listed.")
    return lines


def build_text(results: list[CheckResult], *, contacted: list[str],
               generated: datetime, platform: str, saved_to: str | None = None,
               scan: DeviceScan | None = None) -> str:
    overall = overall_verdict(results)
    mode = "active mode (device scan)" if scan is not None else "passive mode"
    lines = [
        f"Network health - {mode} - {platform} - "
        f"{generated.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Overall verdict: {OVERALL_TEXT[overall]}",
        "",
    ]
    lines += [_area_line(results, a) for a in areas_of(results)]

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

    if scan is not None:
        lines += devices_table(scan)

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
               generated: datetime, platform: str,
               scan: DeviceScan | None = None) -> dict:
    data = {
        "tool": "network-health",
        "mode": "active" if scan is not None else "passive",
        "platform": platform,
        "generated": generated.isoformat(timespec="seconds"),
        "overall": overall_verdict(results),
        "areas": {a: area_verdict(results, a) for a in areas_of(results)},
        "findings": [r.id for r in ranked_findings(results)],
        "results": [r.to_dict() for r in results],
        "contacted": contacted,
    }
    if scan is not None:
        data["scan"] = scan.meta_dict()
        data["devices"] = [d.to_dict() for d in scan.devices]
    return data


def to_json_text(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
