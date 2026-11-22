"""Data classes of the device scan (--active)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ServiceInfo:
    """What one open port told us. Every text is cleaned (safe_text)."""

    port: int
    name: str
    banner: str = ""            # the first line a service volunteered
    http_status: int | None = None
    http_server: str = ""       # the Server header
    http_location: str = ""     # the Location header of a redirect
    http_auth: bool = False     # the page asks for a login (WWW-Authenticate)
    tls_version: str = ""       # set when a TLS handshake worked (HTTPS offered)

    @property
    def is_http(self) -> bool:
        return self.http_status is not None

    @property
    def is_https(self) -> bool:
        return bool(self.tls_version)


@dataclass
class Device:
    ip: str
    mac: str | None = None
    name: str = ""              # from mDNS
    vendor: str = ""            # from the MAC prefix
    kind: str = ""              # category key, see oui.KIND_TEXT
    kind_source: str = ""       # what the guess is based on
    found_by: list[str] = field(default_factory=list)   # ping, arp, mdns, ssdp
    open_ports: list[int] = field(default_factory=list)
    services: dict[int, ServiceInfo] = field(default_factory=dict)
    mdns_services: list[str] = field(default_factory=list)
    ssdp_server: str = ""       # the SERVER header of the SSDP answer
    upnp: bool = False          # answered the SSDP search
    is_gateway: bool = False
    private_mac: bool = False   # locally administered MAC (a phone's private address)
    ports_complete: bool = True  # False when the time limit stopped the port checks
    hazards: list[str] = field(default_factory=list)    # rule ids, set by the checks
    new: bool | None = None     # None: no earlier scan to compare with

    def to_dict(self) -> dict:
        data = asdict(self)
        data["services"] = {str(p): asdict(s) for p, s in sorted(self.services.items())}
        return data


@dataclass
class DeviceScan:
    network: str                # for example "192.0.2.0/24"
    own_address: str
    interface: str
    gateway: str | None = None
    addresses_total: int = 0    # usable addresses of the subnet, minus this computer
    addresses_pinged: int = 0   # pings that ran (a reply or no reply)
    addresses_failed: int = 0   # pings that could not run (time-out of the command, ...)
    addresses_skipped: int = 0  # not pinged because the time limit was reached
    ports: tuple[int, ...] = ()
    devices: list[Device] = field(default_factory=list)
    complete: bool = True       # False when the time limit stopped the scan
    stopped: str = ""           # which part was cut short
    elapsed_s: float = 0.0
    notes: list[str] = field(default_factory=list)
    mdns_answers: int = 0
    ssdp_answers: int = 0

    def meta_dict(self) -> dict:
        return {
            "network": self.network,
            "own_address": self.own_address,
            "interface": self.interface,
            "gateway": self.gateway,
            "addresses_total": self.addresses_total,
            "addresses_pinged": self.addresses_pinged,
            "addresses_failed": self.addresses_failed,
            "addresses_skipped": self.addresses_skipped,
            "ports": list(self.ports),
            "complete": self.complete,
            "stopped": self.stopped,
            "elapsed_s": round(self.elapsed_s, 1),
            "notes": list(self.notes),
            "mdns_answers": self.mdns_answers,
            "ssdp_answers": self.ssdp_answers,
        }
