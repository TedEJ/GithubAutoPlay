"""Command line: python -m network_health [--skip-bandwidth] [--json] [--save]
[--active [--yes]]"""

from __future__ import annotations

import argparse
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from . import scanner, services, snapshot, thresholds
from .checks import DEVICES, gateway_mac, network_identity, run_checks, skipped
from .collect import collect
from .device_checks import check_devices
from .models import Unavailable
from .netio import RealNetIO
from .platforms import UnsupportedPlatform, get_platform
from .report import build_json, build_text, to_json_text
from .scan_target import (
    MDNS_GROUP,
    SSDP_GROUP,
    ScanGuard,
    ScanRefused,
    ScanTarget,
    choose_scan_target,
)

# Exit codes: 0 a report was printed, 2 unsupported system, 3 the active scan
# was refused or not confirmed (nothing was sent).
EXIT_UNSUPPORTED = 2
EXIT_NOT_ALLOWED = 3

PERMISSION_WARNING = "Only scan networks you own or have permission to test."


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m network_health",
        description="Check the network this computer is on and print a verdict "
                    "with fix tips. By default (passive mode) other devices are "
                    "not scanned; with --active the devices on the local subnet "
                    "are found and their open services checked.",
    )
    parser.add_argument("--skip-bandwidth", action="store_true",
                        help="do not run the bandwidth test (the only check that "
                             "sends noticeable traffic to a third-party server)")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of text")
    parser.add_argument("--save", action="store_true",
                        help="write a snapshot to local-data/ (used to notice a "
                             "changed gateway MAC address and new devices next time)")
    parser.add_argument("--active", action="store_true",
                        help="also scan the local subnet of this computer: ping "
                             "sweep, mDNS and SSDP, and a TCP check of "
                             f"{len(services.PORTS)} ports on every device found. "
                             "Only private ranges this computer is connected to are "
                             "scanned, after you confirm. " + PERMISSION_WARNING)
    parser.add_argument("--yes", action="store_true",
                        help="with --active: do not ask for confirmation (for "
                             "repeated runs on your own network)")
    return parser.parse_args(argv)


def _wrap(label: str, text: str) -> str:
    return textwrap.fill(text, width=92, initial_indent=f"  {label:<17}",
                         subsequent_indent=" " * 19)


def scan_description(target: ScanTarget) -> str:
    """What the active scan will do, for the confirmation."""
    ports = ", ".join(str(p) for p in services.PORTS)
    return "\n".join([
        "Active scan (--active)",
        _wrap("Subnet to scan:", f"{target.network} ({target.host_count} addresses) on "
              f"adapter \"{target.interface}\"; this computer is {target.own_address}."),
        _wrap("What it does:", "Pings each address, asks for names with mDNS and SSDP on "
              "the local link, reads the ARP table, and tries to connect to "
              f"{len(services.PORTS)} ports ({ports}) on each device that answers, "
              "reading what the service says about itself. It does not log in, guess "
              "passwords, send exploits or change anything."),
        _wrap("Limits:", f"At most {thresholds.SCAN_TIME_LIMIT_S / 60:.0f} minutes, "
              f"{thresholds.SWEEP_WORKERS} pings and {thresholds.PORT_WORKERS} devices at "
              "a time, at most 50 operations per second."),
        "",
        textwrap.fill(f"WARNING: {PERMISSION_WARNING} Scanning a network without "
                      "permission can be illegal.", width=92),
    ])


def confirm_scan(target: ScanTarget, *, assume_yes: bool, stdin, stderr) -> bool:
    """Show what the scan will do and ask for confirmation. Anything other than
    y or yes is a no. Without --yes and without a terminal the answer is no
    (it never waits for input that cannot come)."""
    print(scan_description(target), file=stderr)
    if assume_yes:
        print("Continuing without asking, because --yes was given.", file=stderr,
              flush=True)
        return True
    isatty = getattr(stdin, "isatty", None)
    if not (callable(isatty) and isatty()):
        print("network-health: --active needs your confirmation, but standard input is "
              "not a terminal. Run it in a terminal, or add --yes if you own this "
              "network or have permission to scan it.", file=stderr)
        return False
    print("Scan this network? Type y or yes to continue [y/N]: ", end="", file=stderr,
          flush=True)
    try:
        answer = stdin.readline()
    except (OSError, ValueError):
        answer = ""
    if answer.strip().lower() in ("y", "yes"):
        return True
    print("Not confirmed. Nothing was scanned.", file=stderr)
    return False


def _contacted_by_scan(target: ScanTarget) -> list[str]:
    return [
        f"{target.network} (the local subnet, {target.host_count} addresses): ping "
        f"sweep, then TCP connection checks of ports "
        f"{', '.join(str(p) for p in services.PORTS)} on the devices found",
        f"{MDNS_GROUP[0]}:{MDNS_GROUP[1]} (mDNS) and {SSDP_GROUP[0]}:{SSDP_GROUP[1]} "
        "(SSDP): multicast queries on the local link",
    ]


def main(argv=None, *, platform=None, collect_kwargs=None, data_dir: Path | None = None,
         now=None, stdout=None, stderr=None, stdin=None, net_io_factory=None,
         clock=None, scan_limits=None) -> int:
    args = parse_args(argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    stdin = stdin or sys.stdin
    data_dir = Path(data_dir) if data_dir else snapshot.DEFAULT_DATA_DIR
    if platform is None:
        try:
            platform = get_platform()
        except UnsupportedPlatform as exc:
            print(f"network-health: {exc}", file=stderr)
            return EXIT_UNSUPPORTED

    def progress(message: str) -> None:
        print(message, file=stderr, flush=True)

    if args.yes and not args.active:
        print("network-health: --yes only matters together with --active.", file=stderr)

    # The target is worked out and confirmed first, before anything is sent.
    target = None
    if args.active:
        try:
            adapters = platform.ip_configuration()
        except Unavailable as exc:
            adapters = exc
        try:
            target = choose_scan_target(adapters)
        except ScanRefused as exc:
            print(f"network-health: {exc}", file=stderr)
            return EXIT_NOT_ALLOWED
        if not confirm_scan(target, assume_yes=args.yes, stdin=stdin, stderr=stderr):
            return EXIT_NOT_ALLOWED

    facts = collect(platform, skip_bandwidth=args.skip_bandwidth, progress=progress,
                    **(collect_kwargs or {}))
    previous = snapshot.load_latest(data_dir)
    results = run_checks(facts, previous)

    scan = None
    if target is not None:
        scan = _run_scan(platform, target, facts, results, data_dir, progress,
                         net_io_factory, clock, scan_limits)

    generated = now or datetime.now()
    data = build_json(results, contacted=facts.contacted, generated=generated,
                      platform=facts.platform, scan=scan)

    saved_to = None
    if args.save:
        snap = dict(data)
        snap["network"] = network_identity(facts)
        snap["gateway_mac"] = gateway_mac(facts)
        saved_to = str(snapshot.save(snap, generated, data_dir))

    if args.json:
        if saved_to:
            data["saved_to"] = saved_to
        stdout.write(to_json_text(data))
    else:
        stdout.write(build_text(results, contacted=facts.contacted, generated=generated,
                                platform=facts.platform, saved_to=saved_to, scan=scan))
    return 0


def _run_scan(platform, target, facts, results, data_dir, progress, net_io_factory,
              clock, scan_limits):
    """Run the device scan and add its results to `results`. Returns the
    DeviceScan, or None when the scan could not run (a skipped result says why)."""
    title = "Device scan"
    try:
        # The network may have changed since the confirmation: scan only the
        # network that was confirmed.
        if choose_scan_target(facts.adapters).network != target.network:
            raise ScanRefused("The network changed after you confirmed the scan, so "
                              "it was not run. Run the tool again.")
        guard = ScanGuard(target)
        io = (net_io_factory or RealNetIO)(guard)
        scan = scanner.scan(platform, target, guard, io, gateway=facts.gateway,
                            clock=clock, limits=scan_limits, progress=progress)
    except ScanRefused as exc:
        results.append(skipped("dev.scan", DEVICES, title, Unavailable("error", str(exc))))
        return None
    except Exception as exc:  # the report must still come
        results.append(skipped("dev.scan", DEVICES, title, Unavailable(
            "error", f"The device scan failed: {type(exc).__name__}: {exc}")))
        return None
    network = scan.network
    previous_scan = snapshot.load_latest(
        data_dir, accept=lambda d: (isinstance(d.get("devices"), list)
                                    and isinstance(d.get("scan"), dict)
                                    and d["scan"].get("network") == network))
    results.extend(check_devices(scan, previous_scan))
    facts.contacted.extend(_contacted_by_scan(target))
    return scan
