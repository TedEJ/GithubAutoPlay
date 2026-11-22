"""--active from the command line: refusal, confirmation, the report, and the
promise that nothing is scanned without the flag.

The made-up home network of the other tests lives in a documentation range,
which --active refuses (that is one of the tests below). For the tests that
need an allowed network, the fixture text is copied with its addresses moved to
a private range at run time (see conftest.py).
"""

import io
import json
import ntpath
from datetime import datetime

import pytest
from conftest import (
    HOME_RULES,
    FakeClock,
    FakeNetIO,
    FakeRunner,
    doc_mac,
    fake_bandwidth,
    fake_dns,
    fixture_text,
    home_platform,
    mac_with_prefix,
    out,
    private_ip,
)

from network_health import cli, scanner, snapshot
from network_health.models import BAD, GOOD, INFO, WARN
from network_health.netio import ProbeResult
from network_health.platforms.windows import WindowsPlatform
from network_health.runner import CommandResult

NOW = datetime(2026, 11, 22, 12, 30, 0)
PRIV = private_ip(0).rsplit(".", 1)[0] + "."        # the first three parts, with a dot
DOC = "192.0.2."
WINDOWS_ROOT = ntpath.join("C:" + ntpath.sep, "Windows")


def moved(text: str, prefix: str = PRIV) -> str:
    return text.replace(DOC, prefix)


def ping_answer(alive):
    def answer(args):
        target = args[-1]
        if target in alive:
            return out(f"Pinging {target} with 32 bytes of data:\n"
                       f"Reply from {target}: bytes=32 time<1ms TTL=64\n")
        return out(f"Pinging {target} with 32 bytes of data:\nRequest timed out.\n",
                   returncode=1)
    return answer


def private_platform(*overrides, alive=(), prefix: str = PRIV, ipconfig=None):
    """The home network moved to a private range. Sweep pings are answered by
    `alive`; overrides come first."""
    rules = [("-n 1 -w 500", ping_answer(set(alive)))] + list(overrides)
    for needle, result in HOME_RULES:
        text = moved(result.stdout, prefix)
        if needle == "Get-NetIPConfiguration" and ipconfig:
            text = ipconfig(text)
        rules.append((moved(needle, prefix),
                      CommandResult(result.args, result.returncode, text, result.stderr,
                                    result.error)))
    # The gateway ping rule of the fixture is for the moved gateway address.
    runner = FakeRunner(rules)
    return WindowsPlatform(runner, environ={}), runner


class Stdin(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class NoInput:
    """A stdin that fails the test when it is read."""

    def isatty(self):
        return True

    def readline(self):
        raise AssertionError("--yes must not ask")


def run_cli(argv, tmp_path, platform, *, stdin=None, io_=None, factory=None, limits=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    made = []

    def default_factory(guard):
        made.append(guard)
        return io_ or FakeNetIO()

    code = cli.main(
        argv, platform=platform,
        collect_kwargs={"dns_probe": fake_dns, "bandwidth": fake_bandwidth},
        data_dir=tmp_path, now=NOW, stdout=stdout, stderr=stderr,
        stdin=stdin if stdin is not None else Stdin("y\n"),
        net_io_factory=factory or default_factory, clock=FakeClock(),
        scan_limits=limits)
    return code, stdout.getvalue(), stderr.getvalue(), made


def mdns_for(host, address):
    import socket
    import struct

    def name(text):
        return b"".join(bytes([len(p)]) + p.encode() for p in text.split(".")) + b"\x00"

    rec = (name(f"{host}.local")
           + struct.pack("!HHIH", 1, 1, 120, 4) + socket.inet_aton(address))
    return struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + rec


# ---------------------------------------------------------------- no flag, no scan

def test_without_active_nothing_is_discovered_swept_or_scanned(tmp_path):
    platform, runner = private_platform(alive=[private_ip(20)])
    io_ = FakeNetIO(ports={private_ip(20): {23: True}})
    code, text, _, made = run_cli(["--json"], tmp_path, platform, io_=io_)
    data = json.loads(text)
    assert code == 0 and data["mode"] == "passive"
    assert "devices" not in data and "scan" not in data
    assert "Devices" not in data["areas"]
    assert made == [], "no network layer may even be created without --active"
    assert io_.calls == [], "no port check, mDNS or SSDP query without --active"
    pings = [c for c in runner.calls if "ping" in c[0].lower()]
    targets = {c[-1] for c in pings if "-f" not in c}
    assert targets == {private_ip(1), "1.1.1.1", "8.8.8.8"}      # gateway and two public
    assert not any("-w" in c and "500" in c for c in runner.calls)   # no sweep ping


def test_active_flag_is_off_by_default():
    assert cli.parse_args([]).active is False and cli.parse_args([]).yes is False
    assert cli.parse_args(["--active", "--yes"]).active is True


# ---------------------------------------------------------------- refusal

def test_active_on_a_public_range_is_refused_and_nothing_is_sent(tmp_path):
    platform, runner = home_platform()                 # the documentation range 192.0.2.0/24
    code, text, stderr, made = run_cli(["--active", "--yes"], tmp_path, platform)
    assert code == cli.EXIT_NOT_ALLOWED
    assert "Refusing to scan 192.0.2.0/24" in stderr and "not a private range" in stderr
    assert "never the internet" in stderr
    assert text == "" and made == []
    # Only the configuration was read; no ping, no DNS, no scan.
    assert len(runner.calls) == 1 and "Get-NetIPConfiguration" in " ".join(runner.calls[0])


def test_active_on_carrier_grade_nat_is_refused(tmp_path):
    cgnat = private_ip(0, "100.64.0.0").rsplit(".", 1)[0] + "."
    platform, runner = private_platform(prefix=cgnat)
    code, _, stderr, made = run_cli(["--active", "--yes"], tmp_path, platform)
    assert code == cli.EXIT_NOT_ALLOWED and "carrier-grade NAT" in stderr and made == []


def test_active_on_a_subnet_larger_than_a_slash_22_is_refused_with_advice(tmp_path):
    platform, _ = private_platform(
        ipconfig=lambda text: text.replace('"PrefixLength":  24', '"PrefixLength":  16', 1))
    code, _, stderr, made = run_cli(["--active", "--yes"], tmp_path, platform)
    assert code == cli.EXIT_NOT_ALLOWED
    assert "1022" in stderr and "/22" in stderr and "smaller subnet" in stderr
    assert made == []


def test_unreadable_configuration_refuses_the_scan(tmp_path):
    platform, runner = private_platform(
        ("Get-NetIPConfiguration", CommandResult((), None, error="not-found")))
    code, _, stderr, _ = run_cli(["--active", "--yes"], tmp_path, platform)
    assert code == cli.EXIT_NOT_ALLOWED and "could not be read" in stderr


# ---------------------------------------------------------------- confirmation

def test_confirmation_prompt_names_the_subnet_the_size_and_the_permission_rule(tmp_path):
    platform, _ = private_platform()
    _, _, stderr, _ = run_cli(["--active"], tmp_path, platform, stdin=Stdin("n\n"))
    flat = " ".join(stderr.split())          # the prompt is wrapped over several lines
    assert f"{PRIV}0/24 (254 addresses)" in flat
    assert "Only scan networks you own or have permission to test." in flat
    assert "[y/N]" in flat
    assert "does not log in, guess passwords" in flat and "5 minutes" in flat


@pytest.mark.parametrize("answer", ["n\n", "\n", "", "no\n", "maybe\n", "yy\n", "yes please\n"])
def test_anything_but_y_or_yes_aborts_before_anything_is_sent(tmp_path, answer):
    platform, runner = private_platform(alive=[private_ip(20)])
    io_ = FakeNetIO()
    code, text, stderr, made = run_cli(["--active"], tmp_path, platform,
                                       stdin=Stdin(answer), io_=io_)
    assert code == cli.EXIT_NOT_ALLOWED and text == ""
    assert "Nothing was scanned" in stderr
    assert made == [] and io_.calls == []
    assert len(runner.calls) == 1            # only the configuration was read
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("answer", ["y\n", "yes\n", "Y\n", " YES \n"])
def test_y_and_yes_start_the_scan(tmp_path, answer):
    platform, _ = private_platform(alive=[private_ip(20)])
    code, text, _, made = run_cli(["--active"], tmp_path, platform, stdin=Stdin(answer))
    assert code == 0 and len(made) == 1 and "Devices on" in text


def test_without_a_terminal_and_without_yes_it_aborts_instead_of_waiting(tmp_path):
    platform, runner = private_platform()
    code, text, stderr, made = run_cli(["--active"], tmp_path, platform,
                                       stdin=Stdin("y\n", tty=False))
    assert code == cli.EXIT_NOT_ALLOWED and text == "" and made == []
    assert "not a terminal" in stderr and "--yes" in stderr
    assert len(runner.calls) == 1


def test_yes_skips_the_question_but_still_shows_what_will_happen(tmp_path):
    platform, _ = private_platform()
    code, text, stderr, made = run_cli(["--active", "--yes"], tmp_path, platform,
                                       stdin=NoInput())
    assert code == 0 and len(made) == 1
    assert "Only scan networks you own or have permission to test." in stderr
    assert "because --yes was given" in stderr


def test_yes_without_active_is_noted(tmp_path):
    platform, _ = private_platform()
    code, text, stderr, made = run_cli(["--yes"], tmp_path, platform)
    assert code == 0 and made == [] and "--yes only matters together with --active" in stderr


# ---------------------------------------------------------------- the report

def scenario(tmp_path, argv=("--active", "--yes"), extra_alive=(), extra_ports=None):
    alive = [private_ip(1), private_ip(20), private_ip(40)] + list(extra_alive)
    platform, runner = private_platform(alive=alive)
    ports = {
        private_ip(1): {80: ProbeResult(True, b"HTTP/1.1 200 OK\r\nServer: ExampleHTTPd\r\n\r\n"),
                        7547: True},
        private_ip(20): {445: True},
        private_ip(40): {23: ProbeResult(True, b"login:"), 21: True},
    }
    ports.update(extra_ports or {})
    io_ = FakeNetIO(ports=ports, ssdp=[(private_ip(1), b"HTTP/1.1 200 OK\r\nST: upnp:rootdevice\r\n\r\n")],
                    mdns=[(private_ip(40), mdns_for("examplecam", private_ip(40)))])
    return platform, runner, io_


def test_active_report_lists_devices_and_every_hazard_with_a_fix(tmp_path):
    platform, runner, io_ = scenario(tmp_path)
    code, text, _, _ = run_cli(list(("--active", "--yes")), tmp_path, platform, io_=io_)
    assert code == 0
    assert "active mode (device scan)" in text.splitlines()[0]
    section = text.split("Devices on ")[1].split("\n\n")[0]
    assert f"{PRIV}0/24" in section
    rows = {ip: next(line for line in section.splitlines() if line.split()[:1] == [ip])
            for ip in (private_ip(1), private_ip(20), private_ip(40))}
    assert "(default gateway)" in rows[private_ip(1)] and "7547 tr-069" in rows[private_ip(1)]
    assert "examplecam" in rows[private_ip(40)] and "23 telnet" in rows[private_ip(40)]
    assert "SMB open" in rows[private_ip(20)]
    for finding in ("[BAD] Devices - Telnet open", "[WARN] Devices - FTP open",
                    "[WARN] Devices - File sharing (SMB)", "[WARN] Devices - TR-069",
                    "[WARN] Devices - UPnP answering", "[WARN] Devices - Admin page on plain HTTP"):
        assert finding in text, finding
    assert text.count("Fix: ") >= 6
    assert f"{PRIV}0/24 (the local subnet" in text           # what was contacted
    assert "224.0.0.251:5353 (mDNS)" in text and "239.255.255.250:1900 (SSDP)" in text
    assert "Overall verdict: BAD" in text


def test_active_json_has_scan_devices_and_hazards(tmp_path):
    platform, _, io_ = scenario(tmp_path)
    code, text, _, _ = run_cli(["--active", "--yes", "--json"], tmp_path, platform, io_=io_)
    data = json.loads(text)
    assert data["mode"] == "active" and data["areas"]["Devices"] == BAD
    assert data["scan"]["complete"] is True and data["scan"]["network"] == f"{PRIV}0/24"
    assert data["scan"]["ports"] == [21, 22, 23, 80, 443, 445, 554, 1900, 3389, 5000,
                                     5900, 7547, 8080, 8443]
    by_ip = {d["ip"]: d for d in data["devices"]}
    assert set(by_ip) >= {private_ip(1), private_ip(20), private_ip(40)}
    assert "dev.tr069" in by_ip[private_ip(1)]["hazards"]
    assert "dev.telnet" in by_ip[private_ip(40)]["hazards"]
    ids = {r["id"] for r in data["results"]}
    assert {"dev.telnet", "dev.ftp", "dev.smb", "dev.remote", "dev.http_admin", "dev.upnp",
            "dev.tr069", "dev.unknown", "dev.new"} <= ids
    for result in data["results"]:
        if result["area"] == "Devices" and result["status"] in (BAD, WARN):
            assert result["fix"] and result["why"], result["id"]


def test_save_stores_the_devices_and_the_next_run_names_new_ones(tmp_path):
    platform, _, io_ = scenario(tmp_path)
    run_cli(["--active", "--yes", "--save"], tmp_path, platform, io_=io_)
    [saved] = list(tmp_path.glob("snapshot-*.json"))
    snap = json.loads(saved.read_text(encoding="utf-8"))
    assert snap["scan"]["network"] == f"{PRIV}0/24" and len(snap["devices"]) >= 3
    assert snap["gateway_mac"] == "00:00:5e:00:53:01"

    # Same devices again: nothing is new.
    platform, _, io_ = scenario(tmp_path)
    _, text, _, _ = run_cli(["--active", "--yes", "--json"], tmp_path, platform, io_=io_)
    results = {r["id"]: r for r in json.loads(text)["results"]}
    assert results["dev.new"]["status"] == GOOD

    # A device with another MAC address appears: it is new.
    newcomer = private_ip(90)
    platform, runner = private_platform(
        ("arp -a", out(moved(fixture_text("arp.txt")) +
                       f"\nInterface: {PRIV}10 --- 0xc\n  {newcomer}   00-00-5e-00-53-90   dynamic\n")))
    _, text, _, _ = run_cli(["--active", "--yes", "--json"], tmp_path, platform,
                            io_=FakeNetIO(ports={newcomer: {80: True}}))
    results = {r["id"]: r for r in json.loads(text)["results"]}
    assert results["dev.new"]["status"] == WARN
    assert results["dev.new"]["details"]["devices"] == [newcomer]


def test_no_devices_are_saved_without_save(tmp_path):
    platform, _, io_ = scenario(tmp_path)
    run_cli(["--active", "--yes"], tmp_path, platform, io_=io_)
    assert not list(tmp_path.iterdir())


def test_the_scan_only_runs_on_the_network_that_was_confirmed(tmp_path):
    """The network configuration is read again by the passive checks; if it
    changed by then, the scan is skipped."""
    calls = []
    other = private_ip(0, "172.16.0.0").rsplit(".", 1)[0] + "."
    first = moved(fixture_text("ps_ipconfig.json"))
    second = moved(fixture_text("ps_ipconfig.json"), other)

    def ipconfig(args):
        calls.append(1)
        return out(first if len(calls) == 1 else second)

    platform, _ = private_platform(("Get-NetIPConfiguration", ipconfig),
                                   ("ping -n 20 -w 1000 " + other + "1",
                                    out(fixture_text("ping_gateway.txt"))))
    io_ = FakeNetIO()
    code, text, _, _ = run_cli(["--active", "--yes"], tmp_path, platform, io_=io_)
    assert code == 0 and io_.calls == []
    assert "network changed after you confirmed" in text
    assert "Device scan" in text


def test_a_failing_scan_still_gives_the_report(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scanner, "scan", boom)
    platform, _ = private_platform()
    code, text, _, _ = run_cli(["--active", "--yes"], tmp_path, platform)
    assert code == 0 and "The device scan failed: RuntimeError: boom" in text
    # The traffic of the scan is listed even though the scan stopped with an error.
    assert f"{PRIV}0/24 (the local subnet" in text
    assert "224.0.0.251:5353 (mDNS)" in text
    assert "Overall verdict:" in text


def test_scan_progress_goes_to_stderr_and_the_prompt_never_pollutes_json(tmp_path):
    platform, _, io_ = scenario(tmp_path)
    code, text, stderr, _ = run_cli(["--active", "--json"], tmp_path, platform, io_=io_,
                                    stdin=Stdin("y\n"))
    json.loads(text)                               # pure JSON on stdout
    assert "Ping sweep of" in stderr and "Checking 14 ports" in stderr
    assert "[y/N]" in stderr


def test_windows_ping_host_runs_one_system_ping_by_its_full_path():
    target = private_ip(20)
    runner = FakeRunner([("-n 1 -w 500", ping_answer({target}))])
    platform = WindowsPlatform(runner, environ={"SystemRoot": WINDOWS_ROOT})
    assert platform.ping_host(target, 500) is True
    assert platform.ping_host(private_ip(21), 500) is False
    assert runner.calls[0] == (ntpath.join(WINDOWS_ROOT, "System32", "ping.exe"),
                               "-n", "1", "-w", "500", target)
