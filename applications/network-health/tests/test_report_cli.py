import io
import json
from datetime import datetime

from conftest import fake_bandwidth, fake_dns, home_platform, ok
from network_health import cli, snapshot
from network_health.checks import AREAS, CheckResult, run_checks
from network_health.models import BAD, GOOD, INFO, SKIPPED, WARN
from network_health.report import (
    area_verdict,
    build_json,
    build_text,
    overall_verdict,
    ranked_findings,
)

NOW = datetime(2026, 11, 22, 12, 30, 0)


def r(check_id, area, status, summary="s", why="w", fix="f"):
    return CheckResult(check_id, area, check_id, status, summary, why, fix)


# ---------------------------------------------------------------- verdicts

def test_area_and_overall_verdicts():
    results = [r("a", "Performance", GOOD), r("b", "Performance", INFO),
               r("c", "Wi-Fi", WARN), r("d", "Configuration", BAD),
               r("e", "Local network", SKIPPED)]
    assert area_verdict(results, "Performance") == GOOD
    assert area_verdict(results, "Wi-Fi") == WARN
    assert area_verdict(results, "Configuration") == BAD
    assert area_verdict(results, "Local network") == SKIPPED
    assert overall_verdict(results) == BAD
    assert overall_verdict(results[:3]) == WARN
    assert overall_verdict(results[:2]) == GOOD
    assert overall_verdict([r("e", "Wi-Fi", SKIPPED)]) == "unknown"


def test_findings_ranked_bad_warn_info_then_area_order():
    results = [r("i", "Performance", INFO), r("w2", "Local network", WARN),
               r("g", "Wi-Fi", GOOD), r("b", "Wi-Fi", BAD), r("w1", "Performance", WARN)]
    assert [x.id for x in ranked_findings(results)] == ["b", "w1", "w2", "i"]


def test_text_report_layout():
    results = [r("b", "Configuration", BAD, "Firewall off", "Why text", "Fix text"),
               r("g", "Performance", GOOD, "Latency fine"),
               r("s", "Wi-Fi", SKIPPED, "This computer is not connected over Wi-Fi.")]
    text = build_text(results, contacted=["1.1.1.1 (Cloudflare): ping"],
                      generated=NOW, platform="Windows")
    lines = text.splitlines()
    assert lines[0] == "Network health - passive mode - Windows - 2026-11-22 12:30"
    assert lines[2].startswith("Overall verdict: BAD")
    for area in AREAS:
        assert any(line.strip().startswith(area) for line in lines)
    assert "[BAD] Configuration - b: Firewall off" in text
    assert "Why: Why text" in text and "Fix: Fix text" in text
    assert "[GOOD] Performance - g: Latency fine" in text
    assert "SKIPPED  This computer is not connected over Wi-Fi." in text
    assert "1.1.1.1 (Cloudflare): ping" in text


def test_json_report():
    results = [r("w", "Wi-Fi", WARN), r("g", "Performance", GOOD)]
    data = build_json(results, contacted=["x"], generated=NOW, platform="Windows")
    assert data["overall"] == WARN
    assert data["areas"]["Wi-Fi"] == WARN
    assert data["findings"] == ["w"]
    assert data["results"][0]["id"] == "w"
    assert data["generated"] == "2026-11-22T12:30:00"
    json.dumps(data)


# ---------------------------------------------------------------- CLI

def run_cli(argv, tmp_path, *overrides):
    platform, runner = home_platform(*overrides)
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli.main(argv, platform=platform,
                    collect_kwargs={"dns_probe": fake_dns, "bandwidth": fake_bandwidth},
                    data_dir=tmp_path, now=NOW, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_cli_text_report(tmp_path):
    code, text, progress = run_cli([], tmp_path)
    assert code == 0
    assert "Overall verdict:" in text
    assert "Findings, most serious first:" in text
    assert "Fix:" in text
    assert "speed.cloudflare.com" in text
    assert "Measuring" in progress
    assert not list(tmp_path.iterdir())  # nothing saved without --save


def test_cli_skip_bandwidth(tmp_path):
    code, text, _ = run_cli(["--skip-bandwidth"], tmp_path)
    assert code == 0
    assert "Turned off with --skip-bandwidth." in text
    assert "bandwidth test" not in text


def test_cli_json(tmp_path):
    code, text, _ = run_cli(["--json"], tmp_path)
    data = json.loads(text)
    assert code == 0
    assert data["mode"] == "passive"
    assert set(data["areas"]) == set(AREAS)
    assert data["overall"] in (GOOD, WARN, BAD)


def test_cli_save_then_detect_changed_gateway_mac(tmp_path):
    code, text, _ = run_cli(["--save"], tmp_path)
    assert code == 0
    saved = list(tmp_path.glob("snapshot-*.json"))
    assert len(saved) == 1
    assert "Snapshot saved to" in text
    data = json.loads(saved[0].read_text(encoding="utf-8"))
    assert data["gateway_mac"] == "00:00:5e:00:53:01"
    assert data["network"] == {"gateway": "192.0.2.1", "ssid": "ExampleHome"}

    # Same network, same router: good.
    _, text, _ = run_cli(["--json"], tmp_path)
    results = {x["id"]: x for x in json.loads(text)["results"]}
    assert results["lan.gateway_mac"]["status"] == GOOD

    # The gateway now answers with another MAC address: warn.
    _, text, _ = run_cli(["--json"], tmp_path, ("arp -a", ok("arp_spoofed.txt")))
    results = {x["id"]: x for x in json.loads(text)["results"]}
    assert results["lan.gateway_mac"]["status"] == WARN


def test_cli_json_with_save_names_the_file(tmp_path):
    _, text, _ = run_cli(["--json", "--save"], tmp_path)
    assert json.loads(text)["saved_to"].endswith(".json")


def test_cli_on_unsupported_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "get_platform", _raise_unsupported)
    stderr = io.StringIO()
    assert cli.main([], data_dir=tmp_path, stderr=stderr, stdout=io.StringIO()) == 2
    assert "#152" in stderr.getvalue()


def _raise_unsupported():
    from network_health.platforms import UnsupportedPlatform
    raise UnsupportedPlatform("network-health runs on Windows for now (#152).")


def test_snapshot_load_latest_ignores_broken_files(tmp_path):
    assert snapshot.load_latest(tmp_path / "missing") is None
    (tmp_path / "snapshot-20261121-100000.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "snapshot-20261122-100000.json").write_text("{broken", encoding="utf-8")
    assert snapshot.load_latest(tmp_path) == {"a": 1}


def test_everything_skipped_still_gives_a_report(tmp_path):
    from network_health.runner import CommandResult
    missing = CommandResult((), None, error="not-found")
    code, text, _ = run_cli(["--skip-bandwidth"], tmp_path,
                            ("ping", missing), ("netsh", missing), ("powershell", missing),
                            ("reg", missing), ("arp", missing))
    assert code == 0
    assert "Overall verdict: UNKNOWN" in text
    assert "was not found on this computer" in text


def test_home_network_overall_verdict_is_good_with_notes():
    platform, _ = home_platform()
    from network_health.collect import collect
    facts = collect(platform, dns_probe=fake_dns, bandwidth=fake_bandwidth)
    results = run_checks(facts)
    assert overall_verdict(results) == GOOD
