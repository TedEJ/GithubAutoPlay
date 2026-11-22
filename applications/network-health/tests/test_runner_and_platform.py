"""The Runner (with subprocess replaced) and the Windows platform's error
handling. No real command is started."""

import subprocess

import pytest

from conftest import FakeRunner, home_platform, ok, out
from network_health import runner as runner_module
from network_health.models import Unavailable
from network_health.platforms import UnsupportedPlatform, get_platform
from network_health.platforms.windows import WindowsPlatform
from network_health.runner import CommandResult, Runner


# ---------------------------------------------------------------- Runner

def _fake_run(result=None, raises=None):
    calls = []

    def fake(args, **kwargs):
        calls.append((args, kwargs))
        if raises:
            raise raises
        return result
    return fake, calls


def test_runner_decodes_output(monkeypatch):
    fake, calls = _fake_run(subprocess.CompletedProcess(
        ["x"], 0, stdout="Svar från".encode("utf-8"), stderr=b""))
    monkeypatch.setattr(runner_module.subprocess, "run", fake)
    result = Runner().run(["x", "y"], timeout=5, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout == "Svar från"
    assert result.error is None
    assert calls[0][0] == ["x", "y"]
    assert calls[0][1]["timeout"] == 5


def test_runner_replaces_undecodable_bytes(monkeypatch):
    fake, _ = _fake_run(subprocess.CompletedProcess(["x"], 1, stdout=b"\xff\xfe ok", stderr=None))
    monkeypatch.setattr(runner_module.subprocess, "run", fake)
    result = Runner().run(["x"], encoding="utf-8")
    assert result.stdout.endswith(" ok")
    assert result.returncode == 1


def test_runner_unknown_encoding_falls_back_to_utf8(monkeypatch):
    fake, _ = _fake_run(subprocess.CompletedProcess(["x"], 0, stdout=b"ok", stderr=b""))
    monkeypatch.setattr(runner_module.subprocess, "run", fake)
    assert Runner().run(["x"], encoding="no-such-codec").stdout == "ok"


@pytest.mark.parametrize("exc,error", [
    (FileNotFoundError(), "not-found"),
    (PermissionError(), "permission"),
    (subprocess.TimeoutExpired(["x"], 1), "timeout"),
    (OSError("boom"), "os-error"),
])
def test_runner_never_raises(monkeypatch, exc, error):
    fake, _ = _fake_run(raises=exc)
    monkeypatch.setattr(runner_module.subprocess, "run", fake)
    result = Runner().run(["x"])
    assert result.error == error
    assert result.returncode is None


# ---------------------------------------------------------------- platform choice

def test_get_platform_windows_and_unsupported():
    assert isinstance(get_platform("win32", runner=FakeRunner([])), WindowsPlatform)
    with pytest.raises(UnsupportedPlatform) as info:
        get_platform("linux")
    assert "#152" in str(info.value)


# ---------------------------------------------------------------- error mapping

@pytest.mark.parametrize("result,kind", [
    (out("", error="not-found"), "missing-tool"),
    (out("", error="permission"), "rights"),
    (out("", error="timeout"), "error"),
    (out("", error="os-error"), "error"),
    (out("", returncode=1, stderr="Access is denied."), "rights"),
    (out("", returncode=1, stderr="Something failed"), "error"),
])
def test_command_problems_become_unavailable(result, kind):
    platform, _ = home_platform(("Get-NetFirewallProfile", result))
    with pytest.raises(Unavailable) as info:
        platform.firewall_profiles()
    assert info.value.kind == kind
    assert info.value.reason


def test_location_permission_message_is_not_mistaken_for_admin_rights():
    platform, _ = home_platform(("netsh wlan show interfaces",
                                 ok("wlan_location_permission.txt", returncode=1)))
    with pytest.raises(Unavailable) as info:
        platform.wifi_status()
    assert "Location" in info.value.reason


def test_ping_with_no_replies_returns_stats():
    platform, _ = home_platform(("ping -n 20 -w 1000 192.0.2.1",
                                 ok("ping_all_lost.txt", returncode=1)))
    assert platform.ping("192.0.2.1", 20).received == 0


def test_powershell_commands_are_json_and_non_interactive():
    platform, runner = home_platform()
    platform.firewall_profiles()
    args = runner.calls[-1]
    assert args[:4] == ("powershell", "-NoProfile", "-NonInteractive", "-Command")
    assert "ConvertTo-Json" in args[4]


def test_proxy_settings_none():
    platform, _ = home_platform()
    proxy = platform.proxy_settings()
    assert not proxy.user_proxy_enabled
    assert proxy.winhttp_proxy is None and proxy.winhttp_known
    assert proxy.environment == {}


def test_proxy_settings_all_sources():
    platform, _ = home_platform(
        ("reg query", ok("reg_internet_settings_proxy.txt")),
        ("netsh winhttp show proxy", ok("winhttp_proxy.txt")),
        environ={"HTTPS_PROXY": "http://proxy.example.invalid:3128", "PATH": "x"},
    )
    proxy = platform.proxy_settings()
    assert proxy.user_proxy_enabled
    assert proxy.user_proxy_server == "proxy.example.invalid:8080"
    assert proxy.auto_config_url == "http://wpad.example.invalid/proxy.pac"
    assert proxy.winhttp_proxy == "proxy.example.invalid:3128"
    assert proxy.environment == {"HTTPS_PROXY": "http://proxy.example.invalid:3128"}


def test_proxy_winhttp_in_other_language_is_noted_not_fatal():
    platform, _ = home_platform(("netsh winhttp show proxy", ok("winhttp_swedish.txt")))
    proxy = platform.proxy_settings()
    assert proxy.winhttp_known is False


def test_fake_runner_refuses_unknown_commands():
    with pytest.raises(AssertionError):
        FakeRunner([]).run(["nmap", "-sn", "192.0.2.0/24"])


def test_command_result_defaults():
    result = CommandResult(("x",), 0)
    assert result.stdout == "" and result.error is None
