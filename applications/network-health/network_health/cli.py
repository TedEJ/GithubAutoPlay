"""Command line: python -m network_health [--skip-bandwidth] [--json] [--save]"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import snapshot
from .checks import gateway_mac, network_identity, run_checks
from .collect import collect
from .platforms import UnsupportedPlatform, get_platform
from .report import build_json, build_text, to_json_text


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m network_health",
        description="Check the network this computer is on (passive mode: no "
                    "scanning of other devices) and print a verdict with fix tips.",
    )
    parser.add_argument("--skip-bandwidth", action="store_true",
                        help="do not run the bandwidth test (the only check that "
                             "sends noticeable traffic to a third-party server)")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of text")
    parser.add_argument("--save", action="store_true",
                        help="write a snapshot to local-data/ (used to notice a "
                             "changed gateway MAC address next time)")
    return parser.parse_args(argv)


def main(argv=None, *, platform=None, collect_kwargs=None, data_dir: Path | None = None,
         now=None, stdout=None, stderr=None) -> int:
    args = parse_args(argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    data_dir = Path(data_dir) if data_dir else snapshot.DEFAULT_DATA_DIR
    if platform is None:
        try:
            platform = get_platform()
        except UnsupportedPlatform as exc:
            print(f"network-health: {exc}", file=stderr)
            return 2

    def progress(message: str) -> None:
        print(message, file=stderr, flush=True)

    facts = collect(platform, skip_bandwidth=args.skip_bandwidth, progress=progress,
                    **(collect_kwargs or {}))
    previous = snapshot.load_latest(data_dir)
    results = run_checks(facts, previous)
    generated = now or datetime.now()
    data = build_json(results, contacted=facts.contacted, generated=generated,
                      platform=facts.platform)

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
                                platform=facts.platform, saved_to=saved_to))
    return 0
