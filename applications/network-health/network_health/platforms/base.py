"""The platform layer: what the checks need from the operating system.

A platform reads facts with the operating system's own commands, through a
Runner, and returns objects from network_health.models. Every method raises
models.Unavailable when the fact cannot be read; it never crashes on output it
does not understand. Windows is implemented in windows.py; Linux (#152) will
be a second class with the same methods, and the checks stay as they are.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import (
    AdapterConfig,
    FirewallProfile,
    ListeningPort,
    Neighbour,
    NetworkProfile,
    PingStats,
    ProxySettings,
    WifiNetwork,
    WifiStatus,
)


class NetworkPlatform(ABC):
    name = "unknown"

    @abstractmethod
    def ping(self, target: str, count: int, timeout_ms: int = 1000) -> PingStats:
        """Ping target count times with the system ping."""

    @abstractmethod
    def ping_dont_fragment(self, target: str, payload: int) -> bool:
        """One ping with do-not-fragment set; True when a reply came back."""

    @abstractmethod
    def ip_configuration(self) -> list[AdapterConfig]:
        """Adapters that are up, with addresses, gateways and DNS servers."""

    @abstractmethod
    def wifi_status(self) -> WifiStatus:
        """The current Wi-Fi connection (connected=False when not on Wi-Fi)."""

    @abstractmethod
    def wifi_networks(self) -> list[WifiNetwork]:
        """Wi-Fi networks the adapter already sees (no active scan is sent)."""

    @abstractmethod
    def network_profiles(self) -> list[NetworkProfile]:
        """The network profile (Public or Private) of each connection."""

    @abstractmethod
    def firewall_profiles(self) -> list[FirewallProfile]:
        """Whether the firewall is on, per profile."""

    @abstractmethod
    def proxy_settings(self) -> ProxySettings:
        """Proxy settings of the current user and the system."""

    @abstractmethod
    def listening_ports(self) -> list[ListeningPort]:
        """TCP ports that listen on this computer."""

    @abstractmethod
    def neighbours(self) -> list[Neighbour]:
        """The ARP (neighbour) table, as the computer already has it."""
