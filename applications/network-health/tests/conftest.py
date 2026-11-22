"""Shared test helpers: a fake Runner fed with recorded, made-up output.

No test starts a real command or opens a network connection. All addresses
in the fixtures are from the documentation ranges (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32), the MAC addresses are from
the RFC 7042 documentation range 00:00:5e:00:53:xx, and the names are made up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from network_health.collect import collect
from network_health.models import BandwidthResult, DnsTiming
from network_health.platforms.windows import WindowsPlatform
from network_health.runner import CommandResult

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "windows"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok(name: str, returncode: int = 0) -> CommandResult:
    """A CommandResult whose stdout is a fixture file."""
    return CommandResult(args=(), returncode=returncode, stdout=fixture_text(name))


def out(text: str, returncode: int = 0, stderr: str = "", error=None) -> CommandResult:
    """A CommandResult with the given text."""
    return CommandResult(args=(), returncode=returncode, stdout=text,
                         stderr=stderr, error=error)


class FakeRunner:
    """Answers commands from rules: the first rule whose text is part of the
    command line wins. Unknown commands fail the test."""

    def __init__(self, rules):
        self.rules = list(rules)
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, *, timeout=30.0, encoding=None):
        args = tuple(args)
        self.calls.append(args)
        line = " ".join(args)
        for needle, answer in self.rules:
            if needle in line:
                result = answer(args) if callable(answer) else answer
                return CommandResult(args, result.returncode, result.stdout,
                                     result.stderr, result.error, result.elapsed_s)
        raise AssertionError(f"unexpected command in a test: {line}")


HOME_RULES = [
    ("ping -n 20 -w 1000 192.0.2.1", ok("ping_gateway.txt")),
    ("ping -n 20 -w 1000 1.1.1.1", ok("ping_cloudflare.txt")),
    ("ping -n 20 -w 1000 8.8.8.8", ok("ping_google.txt")),
    ("-f -l", ok("ping_df_ok.txt")),
    ("netsh wlan show interfaces", ok("wlan_interfaces_connected.txt")),
    ("netsh wlan show networks", ok("wlan_networks.txt")),
    ("Get-NetIPConfiguration", ok("ps_ipconfig.json")),
    ("Get-NetConnectionProfile", ok("ps_profiles.json")),
    ("Get-NetFirewallProfile", ok("ps_firewall.json")),
    ("Get-NetTCPConnection", ok("ps_listening.json")),
    ("reg query", ok("reg_internet_settings.txt")),
    ("netsh winhttp show proxy", ok("winhttp_direct.txt")),
    ("arp -a", ok("arp.txt")),
]


def home_platform(*overrides, environ=None) -> tuple[WindowsPlatform, FakeRunner]:
    """The made-up home network; overrides (needle, result) come first."""
    runner = FakeRunner(list(overrides) + HOME_RULES)
    return WindowsPlatform(runner, environ=environ or {}), runner


def fake_dns(server, names):
    return DnsTiming(server=server, times_ms=[12.0, 15.0, 11.0])


def fake_bandwidth():
    return BandwidthResult(
        server="Cloudflare speed test (speed.cloudflare.com)",
        download_mbps=180.0, upload_mbps=40.0,
        download_bytes=25_000_000, upload_bytes=10_000_000,
        loaded_latency_ms=[20.0, 22.0, 25.0],
    )


def home_facts(*overrides, skip_bandwidth=False, bandwidth=fake_bandwidth,
               dns_probe=fake_dns, environ=None):
    platform, runner = home_platform(*overrides, environ=environ)
    facts = collect(platform, skip_bandwidth=skip_bandwidth, dns_probe=dns_probe,
                    bandwidth=bandwidth)
    return facts, runner


@pytest.fixture
def home():
    return home_facts()
