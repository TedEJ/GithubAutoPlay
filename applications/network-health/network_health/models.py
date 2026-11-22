"""Plain data classes shared by the platform layer, the checks and the report.

The platform layer turns command output into these objects; the checks only
read these objects. A Linux implementation (issue #152) returns the same
objects, so the checks do not change.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# Status of one check result. "info" counts as good for the verdict: it is a
# note worth reading, not a problem.
GOOD = "good"
INFO = "info"
WARN = "warn"
BAD = "bad"
SKIPPED = "skipped"


class Unavailable(Exception):
    """A fact could not be collected. The check that needs it is skipped.

    kind is one of:
      missing-tool    a system command was not found
      rights          the command needs more rights than a normal user has
      unrecognized    the output was not understood (for example a Windows
                      that is not in English)
      not-applicable  the check does not apply (for example no Wi-Fi)
      turned-off      the user turned the check off (--skip-bandwidth)
      error           anything else (time-out, network error, ...)
    """

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


class UnrecognizedOutput(Unavailable):
    def __init__(self, tool: str, hint: str = ""):
        reason = (
            f"The output of `{tool}` was not recognised. The tool reads English "
            "Windows output; on a Windows in another language this check is "
            "skipped."
        )
        if hint:
            reason += f" ({hint})"
        super().__init__("unrecognized", reason)


@dataclass
class PingStats:
    target: str
    sent: int
    times_ms: list[float] = field(default_factory=list)

    @property
    def received(self) -> int:
        return len(self.times_ms)

    @property
    def loss_pct(self) -> float:
        if self.sent <= 0:
            return 0.0
        lost = max(self.sent - self.received, 0)
        return 100.0 * lost / self.sent

    @property
    def avg_ms(self) -> float | None:
        return statistics.fmean(self.times_ms) if self.times_ms else None

    @property
    def jitter_ms(self) -> float | None:
        """Mean absolute difference between consecutive replies."""
        if len(self.times_ms) < 2:
            return None
        diffs = [abs(b - a) for a, b in zip(self.times_ms, self.times_ms[1:])]
        return statistics.fmean(diffs)


@dataclass
class IPv4Entry:
    address: str
    prefix_length: int
    origin: str  # "Dhcp", "Manual", "WellKnown", ... as Windows reports it
    valid_lifetime_s: int | None = None


@dataclass
class AdapterConfig:
    alias: str
    index: int | None = None
    metric: int | None = None
    ipv4: list[IPv4Entry] = field(default_factory=list)
    ipv6_global: list[str] = field(default_factory=list)
    ipv4_gateways: list[str] = field(default_factory=list)
    ipv6_gateways: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)


@dataclass
class WifiStatus:
    connected: bool
    name: str = ""
    ssid: str = ""
    bssid: str = ""
    band: str | None = None  # "2.4 GHz", "5 GHz" or "6 GHz"
    channel: int | None = None
    radio_type: str = ""
    authentication: str = ""
    cipher: str = ""
    receive_mbps: float | None = None
    transmit_mbps: float | None = None
    signal_pct: int | None = None
    rssi_dbm: int | None = None


@dataclass
class WifiNetwork:
    ssid: str
    authentication: str
    encryption: str
    bssid: str
    signal_pct: int | None
    band: str | None
    channel: int | None


@dataclass
class NetworkProfile:
    name: str
    interface_alias: str
    category: str  # "Public", "Private" or "DomainAuthenticated"


@dataclass
class FirewallProfile:
    name: str
    enabled: bool


@dataclass
class ProxySettings:
    user_proxy_enabled: bool = False
    user_proxy_server: str | None = None
    auto_config_url: str | None = None
    winhttp_proxy: str | None = None
    winhttp_known: bool = True
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class ListeningPort:
    address: str
    port: int
    pid: int | None = None
    process: str | None = None


@dataclass
class Neighbour:
    interface_ip: str
    ip: str
    mac: str  # lower case, colon separated


@dataclass
class DnsTiming:
    server: str
    times_ms: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def median_ms(self) -> float | None:
        return statistics.median(self.times_ms) if self.times_ms else None


@dataclass
class MtuResult:
    target: str
    mtu: int


@dataclass
class BandwidthResult:
    server: str
    download_mbps: float | None = None
    upload_mbps: float | None = None
    download_bytes: int = 0
    upload_bytes: int = 0
    download_seconds: float | None = None
    upload_seconds: float | None = None
    download_error: str | None = None
    upload_error: str | None = None
    loaded_latency_ms: list[float] = field(default_factory=list)
