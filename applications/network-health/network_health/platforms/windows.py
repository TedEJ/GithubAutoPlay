"""The Windows implementation of the platform layer.

Only commands that ship with Windows are used: ping, netsh, arp, reg and
Windows PowerShell. Everything runs as a normal user. All commands go through
the Runner given to the constructor.
"""

from __future__ import annotations

import ntpath
import os

from .. import thresholds
from ..models import (
    AdapterConfig,
    FirewallProfile,
    ListeningPort,
    Neighbour,
    NetworkProfile,
    PingStats,
    ProxySettings,
    Unavailable,
    WifiNetwork,
    WifiStatus,
)
from ..runner import CommandResult, Runner
from . import windows_parsers as parsers
from .base import NetworkPlatform

# PowerShell commands. Each prints JSON (always a list, thanks to -InputObject
# @(...)), so the output does not depend on the language of Windows. Enums are
# turned into strings, and the output encoding is set to UTF-8.
_PS_PREFIX = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "

PS_IP_CONFIGURATION = _PS_PREFIX + (
    "ConvertTo-Json -Depth 4 -InputObject @(Get-NetIPConfiguration | "
    "Where-Object { $_.NetAdapter.Status -eq 'Up' } | ForEach-Object { "
    "[pscustomobject]@{ "
    "InterfaceAlias = $_.InterfaceAlias; "
    "InterfaceIndex = $_.InterfaceIndex; "
    "Metric = [int]$_.NetIPv4Interface.InterfaceMetric; "
    "IPv4 = @($_.IPv4Address | ForEach-Object { [pscustomobject]@{ "
    "Address = $_.IPAddress; PrefixLength = [int]$_.PrefixLength; "
    "PrefixOrigin = [string]$_.PrefixOrigin; "
    "ValidLifetimeSeconds = [int64]$_.ValidLifetime.TotalSeconds } }); "
    "IPv6Global = @($_.IPv6Address | ForEach-Object { $_.IPAddress }); "
    "IPv4Gateway = @($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop }); "
    "IPv6Gateway = @($_.IPv6DefaultGateway | ForEach-Object { $_.NextHop }); "
    "DnsServers = @($_.DNSServer | ForEach-Object { $_.ServerAddresses }) "
    "} })"
)

PS_CONNECTION_PROFILES = _PS_PREFIX + (
    "ConvertTo-Json -Depth 3 -InputObject @(Get-NetConnectionProfile | "
    "ForEach-Object { [pscustomobject]@{ Name = $_.Name; "
    "InterfaceAlias = $_.InterfaceAlias; "
    "NetworkCategory = [string]$_.NetworkCategory } })"
)

PS_FIREWALL_PROFILES = _PS_PREFIX + (
    "ConvertTo-Json -Depth 3 -InputObject @(Get-NetFirewallProfile | "
    "ForEach-Object { [pscustomobject]@{ Name = [string]$_.Name; "
    "Enabled = [string]$_.Enabled } })"
)

PS_LISTENING_PORTS = _PS_PREFIX + (
    "ConvertTo-Json -Depth 3 -InputObject @(Get-NetTCPConnection -State Listen "
    "-ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{ "
    "LocalAddress = $_.LocalAddress; LocalPort = [int]$_.LocalPort; "
    "ProcessId = [int]$_.OwningProcess; "
    "ProcessName = (Get-Process -Id $_.OwningProcess "
    "-ErrorAction SilentlyContinue).ProcessName } })"
)

INTERNET_SETTINGS_KEY = (
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
)

PROXY_ENVIRONMENT = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                     "http_proxy", "https_proxy", "all_proxy")

_RIGHTS_WORDS = ("access is denied", "requires elevation", "run as administrator")


# System commands are started by their full path under %SystemRoot%\System32,
# so a program with the same name earlier in PATH (or in the current folder)
# is not run instead. Without SystemRoot the bare name is used.
SYSTEM_TOOLS = {
    "ping": "ping.exe",
    "netsh": "netsh.exe",
    "arp": "arp.exe",
    "reg": "reg.exe",
    "powershell": ntpath.join("WindowsPowerShell", "v1.0", "powershell.exe"),
}


def system_command(name: str, environ) -> str:
    """Full path of a Windows system command, or the bare name."""
    root = environ.get("SystemRoot") or environ.get("SYSTEMROOT")
    if not root or name not in SYSTEM_TOOLS:
        return name
    return ntpath.join(root, "System32", SYSTEM_TOOLS[name])


def powershell(command: str) -> list[str]:
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]


class WindowsPlatform(NetworkPlatform):
    name = "Windows"

    def __init__(self, runner: Runner | None = None, environ=None):
        self.runner = runner or Runner()
        self.environ = os.environ if environ is None else environ

    # -- helpers

    def _run(self, args: list[str], tool: str, *, timeout: float = 30.0,
             encoding: str | None = None, allow_failure: bool = False) -> str:
        args = [system_command(args[0], self.environ)] + list(args[1:])
        result = self.runner.run(args, timeout=timeout, encoding=encoding)
        return self._output(result, tool, allow_failure)

    @staticmethod
    def _output(result: CommandResult, tool: str, allow_failure: bool) -> str:
        if result.error == "not-found":
            raise Unavailable("missing-tool", f"`{tool}` was not found on this computer.")
        if result.error == "permission":
            raise Unavailable("rights", f"`{tool}` could not be started: it needs "
                                        "more rights than a normal user has.")
        if result.error == "timeout":
            raise Unavailable("error", f"`{tool}` did not finish in time.")
        if result.error:
            raise Unavailable("error", f"`{tool}` could not be started ({result.error}).")
        combined = (result.stdout + "\n" + result.stderr).lower()
        # netsh wlan without location permission also says "requires
        # elevation"; its parser gives the right advice, so let it through.
        if ("location permission" not in combined
                and any(word in combined for word in _RIGHTS_WORDS)):
            raise Unavailable("rights", f"`{tool}` needs administrator rights; "
                                        "this check is skipped for a normal user.")
        if result.returncode not in (0, None) and not allow_failure and not result.stdout.strip():
            detail = result.stderr.strip().splitlines()[:1]
            raise Unavailable("error", f"`{tool}` failed" +
                              (f": {detail[0]}" if detail else "."))
        return result.stdout

    def _powershell(self, command: str, tool: str) -> str:
        return self._run(powershell(command), tool, timeout=60.0, encoding="utf-8")

    # -- performance

    def ping(self, target: str, count: int, timeout_ms: int = 1000) -> PingStats:
        # ping returns 1 when no reply came back; that is a result, not an error.
        text = self._run(["ping", "-n", str(count), "-w", str(timeout_ms), target],
                         "ping", timeout=count * (timeout_ms / 1000 + 1) + 10,
                         allow_failure=True)
        return parsers.parse_ping(text, target, count)

    def ping_dont_fragment(self, target: str, payload: int) -> bool:
        text = self._run(["ping", "-n", "1", "-w", "1000", "-f", "-l", str(payload), target],
                         "ping", timeout=15, allow_failure=True)
        return parsers.ping_succeeded(text)

    def ping_host(self, target: str, timeout_ms: int) -> bool:
        text = self._run(["ping", "-n", "1", "-w", str(timeout_ms), target], "ping",
                         timeout=thresholds.SCAN_MAX_OPERATION_S, allow_failure=True)
        return parsers.ping_succeeded(text)

    # -- configuration

    def ip_configuration(self) -> list[AdapterConfig]:
        return parsers.parse_ip_configuration(
            self._powershell(PS_IP_CONFIGURATION, "Get-NetIPConfiguration"))

    def wifi_status(self) -> WifiStatus:
        text = self._run(["netsh", "wlan", "show", "interfaces"],
                         "netsh wlan show interfaces", allow_failure=True)
        return parsers.parse_wlan_interfaces(text)

    def wifi_networks(self) -> list[WifiNetwork]:
        text = self._run(["netsh", "wlan", "show", "networks", "mode=bssid"],
                         "netsh wlan show networks", allow_failure=True)
        return parsers.parse_wlan_networks(text)

    def network_profiles(self) -> list[NetworkProfile]:
        return parsers.parse_connection_profiles(
            self._powershell(PS_CONNECTION_PROFILES, "Get-NetConnectionProfile"))

    def firewall_profiles(self) -> list[FirewallProfile]:
        return parsers.parse_firewall_profiles(
            self._powershell(PS_FIREWALL_PROFILES, "Get-NetFirewallProfile"))

    def proxy_settings(self) -> ProxySettings:
        values = parsers.parse_reg_values(
            self._run(["reg", "query", INTERNET_SETTINGS_KEY], "reg query"))
        settings = ProxySettings(
            user_proxy_enabled=parsers.reg_dword(values, "ProxyEnable") == 1,
            user_proxy_server=(values.get("ProxyServer") or (None, None))[1] or None,
            auto_config_url=(values.get("AutoConfigURL") or (None, None))[1] or None,
        )
        try:
            settings.winhttp_proxy = parsers.parse_winhttp_proxy(
                self._run(["netsh", "winhttp", "show", "proxy"], "netsh winhttp show proxy"))
        except Unavailable:
            settings.winhttp_known = False
        settings.environment = {k: self.environ[k] for k in PROXY_ENVIRONMENT
                                if self.environ.get(k)}
        return settings

    def listening_ports(self) -> list[ListeningPort]:
        return parsers.parse_listening_ports(
            self._powershell(PS_LISTENING_PORTS, "Get-NetTCPConnection"))

    def neighbours(self) -> list[Neighbour]:
        return parsers.parse_arp(self._run(["arp", "-a"], "arp -a", allow_failure=True))
