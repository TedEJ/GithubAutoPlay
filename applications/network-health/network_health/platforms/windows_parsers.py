"""Parsers for the output of Windows commands.

Each parser takes the text a command printed and returns objects from
network_health.models. When the text is not understood, the parser raises
UnrecognizedOutput, so the check is skipped with a clear message instead of
crashing.

Where it can, a parser relies on parts that do not change with the language
of Windows (addresses, "TTL=", JSON from PowerShell, registry value names).
netsh wlan output is only understood in English.
"""

from __future__ import annotations

import ipaddress
import json
import re

from ..models import (
    AdapterConfig,
    FirewallProfile,
    IPv4Entry,
    ListeningPort,
    Neighbour,
    NetworkProfile,
    PingStats,
    Unavailable,
    UnrecognizedOutput,
    WifiNetwork,
    WifiStatus,
)

# ---------------------------------------------------------------- ping

# "time=12ms", "time<1ms", and in other languages "Zeit=12ms", "tid<1ms".
_PING_TIME = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


def parse_ping(text: str, target: str, sent: int) -> PingStats:
    """Count the replies of `ping -n <sent> <target>`.

    A reply is a line with "TTL=", which every language of Windows prints.
    A reply of "<1ms" counts as 0.5 ms.
    """
    if not text.strip():
        raise UnrecognizedOutput("ping", "no output")
    if "could not find host" in text.lower():
        raise Unavailable("error", f"ping could not find the host {target}.")
    times: list[float] = []
    for line in text.splitlines():
        if "TTL=" not in line.upper():
            continue
        match = _PING_TIME.search(line)
        if not match:
            continue
        value = float(match.group(1).replace(",", "."))
        if match.group(0).startswith("<"):
            value = 0.5
        times.append(value)
    if not times and target not in text:
        # Neither replies nor the target in the text: not ping output we know.
        raise UnrecognizedOutput("ping")
    return PingStats(target=target, sent=sent, times_ms=times)


def ping_succeeded(text: str) -> bool:
    return any("TTL=" in line.upper() and _PING_TIME.search(line)
               for line in text.splitlines())


# ---------------------------------------------------------------- netsh wlan

_KV = re.compile(r"^\s*([^:]+?)\s*:\s?(.*?)\s*$")


def _key_values(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in block.splitlines():
        match = _KV.match(line)
        if match:
            values.setdefault(match.group(1).strip().lower(), match.group(2).strip())
    return values


def _no_wifi_message(text: str) -> str | None:
    lower = text.lower()
    if "there is no wireless interface" in lower:
        return "This computer has no Wi-Fi adapter."
    if "wlansvc" in lower and "not running" in lower:
        return "The Windows Wi-Fi service (WLAN AutoConfig) is not running."
    return None


def _check_location_permission(text: str) -> None:
    if "location permission" in text.lower():
        raise Unavailable(
            "rights",
            "Windows needs location permission before netsh may read Wi-Fi "
            "details. Turn on Settings > Privacy & security > Location (and "
            "'Let desktop apps access your location'), then run again.",
        )


def _band(value: str | None, channel: int | None) -> str | None:
    if value:
        number = re.search(r"(\d+(?:[.,]\d+)?)", value)
        if number:
            ghz = float(number.group(1).replace(",", "."))
            if ghz < 3:
                return "2.4 GHz"
            if ghz < 5.9:
                return "5 GHz"
            return "6 GHz"
    if channel is not None:
        # Older Windows does not print the band. Channels 1-14 are 2.4 GHz;
        # without a band line the rest is taken as 5 GHz.
        return "2.4 GHz" if channel <= 14 else "5 GHz"
    return None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    return float(match.group(0).replace(",", ".")) if match else None


def parse_wlan_interfaces(text: str) -> WifiStatus:
    """Parse `netsh wlan show interfaces`. Returns connected=False when the
    computer is not on Wi-Fi."""
    if _no_wifi_message(text):
        return WifiStatus(connected=False)
    _check_location_permission(text)
    # One block per interface; a block starts with "Name".
    blocks = re.split(r"(?m)^(?=\s*Name\s*:)", text)
    interfaces = [_key_values(b) for b in blocks if re.search(r"(?m)^\s*Name\s*:", b)]
    if not interfaces:
        raise UnrecognizedOutput("netsh wlan show interfaces")
    if not any("state" in kv for kv in interfaces):
        raise UnrecognizedOutput("netsh wlan show interfaces", "no 'State' line")
    for kv in interfaces:
        if kv.get("state", "").lower() != "connected":
            continue
        channel = _int(kv.get("channel"))
        return WifiStatus(
            connected=True,
            name=kv.get("name", ""),
            ssid=kv.get("ssid", ""),
            bssid=kv.get("ap bssid", kv.get("bssid", "")).lower(),
            band=_band(kv.get("band"), channel),
            channel=channel,
            radio_type=kv.get("radio type", ""),
            authentication=kv.get("authentication", ""),
            cipher=kv.get("cipher", ""),
            receive_mbps=_float(kv.get("receive rate (mbps)")),
            transmit_mbps=_float(kv.get("transmit rate (mbps)")),
            signal_pct=_int(kv.get("signal")),
            rssi_dbm=_int(kv.get("rssi")),
        )
    return WifiStatus(connected=False)


def parse_wlan_networks(text: str) -> list[WifiNetwork]:
    """Parse `netsh wlan show networks mode=bssid`."""
    if _no_wifi_message(text):
        return []
    _check_location_permission(text)
    ssid_blocks = re.split(r"(?m)^(?=SSID \d+\s*:)", text)
    networks: list[WifiNetwork] = []
    seen_ssid_block = False
    for block in ssid_blocks:
        head = re.match(r"SSID \d+\s*:\s?(.*)", block)
        if not head:
            continue
        seen_ssid_block = True
        ssid = head.group(1).strip()
        before_bssid = re.split(r"(?m)^\s*BSSID \d+", block, maxsplit=1)[0]
        common = _key_values(before_bssid)
        for bblock in re.split(r"(?m)^(?=\s*BSSID \d+\s*:)", block)[1:]:
            kv = _key_values(bblock)
            bssid_key = next((k for k in kv if k.startswith("bssid")), None)
            channel = _int(kv.get("channel"))
            networks.append(WifiNetwork(
                ssid=ssid,
                authentication=common.get("authentication", ""),
                encryption=common.get("encryption", ""),
                bssid=(kv.get(bssid_key, "") if bssid_key else "").lower(),
                signal_pct=_int(kv.get("signal")),
                band=_band(kv.get("band"), channel),
                channel=channel,
            ))
    if not seen_ssid_block and "network" not in text.lower():
        raise UnrecognizedOutput("netsh wlan show networks mode=bssid")
    if networks and all(n.channel is None for n in networks):
        raise UnrecognizedOutput("netsh wlan show networks mode=bssid",
                                 "no 'Channel' lines")
    return networks


# ---------------------------------------------------------------- PowerShell JSON

def parse_json_list(text: str, tool: str) -> list[dict]:
    text = text.strip().lstrip("﻿")
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UnrecognizedOutput(tool, "not valid JSON") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(d, dict) for d in data):
        raise UnrecognizedOutput(tool, "unexpected JSON shape")
    return data


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None]
    return [value]


_CATEGORIES = {"0": "Public", "1": "Private", "2": "DomainAuthenticated",
               "public": "Public", "private": "Private",
               "domainauthenticated": "DomainAuthenticated"}


def parse_connection_profiles(text: str) -> list[NetworkProfile]:
    tool = "Get-NetConnectionProfile"
    profiles = []
    for item in parse_json_list(text, tool):
        category = _CATEGORIES.get(str(item.get("NetworkCategory", "")).lower())
        if category is None:
            raise UnrecognizedOutput(tool, "unknown NetworkCategory")
        profiles.append(NetworkProfile(
            name=str(item.get("Name") or ""),
            interface_alias=str(item.get("InterfaceAlias") or ""),
            category=category,
        ))
    return profiles


def _bool(value, tool: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    raise UnrecognizedOutput(tool, f"unexpected value {value!r}")


def parse_firewall_profiles(text: str) -> list[FirewallProfile]:
    tool = "Get-NetFirewallProfile"
    items = parse_json_list(text, tool)
    if not items:
        raise UnrecognizedOutput(tool, "no profiles")
    return [FirewallProfile(name=str(i.get("Name") or "?"),
                            enabled=_bool(i.get("Enabled"), tool))
            for i in items]


def parse_ip_configuration(text: str) -> list[AdapterConfig]:
    tool = "Get-NetIPConfiguration"
    adapters = []
    for item in parse_json_list(text, tool):
        if "InterfaceAlias" not in item:
            raise UnrecognizedOutput(tool, "no InterfaceAlias")
        ipv4 = []
        for entry in _as_list(item.get("IPv4")):
            if not isinstance(entry, dict) or "Address" not in entry:
                continue
            lifetime = entry.get("ValidLifetimeSeconds")
            ipv4.append(IPv4Entry(
                address=str(entry["Address"]),
                prefix_length=int(entry.get("PrefixLength") or 0),
                origin=str(entry.get("PrefixOrigin") or ""),
                valid_lifetime_s=int(lifetime) if lifetime is not None else None,
            ))
        adapters.append(AdapterConfig(
            alias=str(item["InterfaceAlias"]),
            index=item.get("InterfaceIndex"),
            metric=item.get("Metric"),
            ipv4=ipv4,
            ipv6_global=[str(a) for a in _as_list(item.get("IPv6Global"))],
            ipv4_gateways=[str(a) for a in _as_list(item.get("IPv4Gateway"))],
            ipv6_gateways=[str(a) for a in _as_list(item.get("IPv6Gateway"))],
            dns_servers=[str(a) for a in _as_list(item.get("DnsServers"))],
        ))
    return adapters


def parse_listening_ports(text: str) -> list[ListeningPort]:
    tool = "Get-NetTCPConnection"
    ports = []
    for item in parse_json_list(text, tool):
        if "LocalAddress" not in item or "LocalPort" not in item:
            raise UnrecognizedOutput(tool, "missing LocalAddress or LocalPort")
        pid = item.get("ProcessId")
        ports.append(ListeningPort(
            address=str(item["LocalAddress"]),
            port=int(item["LocalPort"]),
            pid=int(pid) if pid is not None else None,
            process=item.get("ProcessName") or None,
        ))
    return ports


# ---------------------------------------------------------------- proxy

_REG_VALUE = re.compile(r"^\s+(.+?)\s{2,}(REG_[A-Z_]+)\s*(.*?)\s*$")


def parse_reg_values(text: str) -> dict[str, tuple[str, str]]:
    """Parse `reg query <key>`: value name -> (type, data). The format does
    not depend on the language of Windows."""
    if "HKEY_" not in text.upper():
        raise UnrecognizedOutput("reg query")
    values = {}
    for line in text.splitlines():
        match = _REG_VALUE.match(line)
        if match:
            values[match.group(1)] = (match.group(2), match.group(3))
    return values


def reg_dword(values: dict[str, tuple[str, str]], name: str) -> int | None:
    if name not in values:
        return None
    _, data = values[name]
    try:
        return int(data, 16) if data.lower().startswith("0x") else int(data)
    except ValueError:
        return None


def parse_winhttp_proxy(text: str) -> str | None:
    """Parse `netsh winhttp show proxy`. Returns the proxy server or None."""
    if "direct access" in text.lower():
        return None
    match = re.search(r"(?im)^\s*Proxy Server\(s\)\s*:\s*(\S.*?)\s*$", text)
    if match:
        return match.group(1)
    raise UnrecognizedOutput("netsh winhttp show proxy")


# ---------------------------------------------------------------- arp

_ARP_INTERFACE = re.compile(r"^\S.*?:\s+(\d{1,3}(?:\.\d{1,3}){3})\s+---\s+0x[0-9a-fA-F]+")
_ARP_ENTRY = re.compile(
    r"^\s+(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})\b")


def parse_arp(text: str) -> list[Neighbour]:
    """Parse `arp -a`. Only addresses are read, so every language works.

    Broadcast, multicast and incomplete entries are left out: they are not
    devices.
    """
    neighbours: list[Neighbour] = []
    interface_ip = ""
    seen_interface = False
    for line in text.splitlines():
        head = _ARP_INTERFACE.match(line)
        if head:
            interface_ip = head.group(1)
            seen_interface = True
            continue
        entry = _ARP_ENTRY.match(line)
        if not entry or not interface_ip:
            continue
        ip_text, mac_text = entry.group(1), entry.group(2).lower().replace("-", ":")
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        first_octet = int(mac_text[:2], 16)
        if (ip.is_multicast or ip_text == "255.255.255.255"
                or mac_text in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00")
                or first_octet & 1):  # group (multicast) MAC address
            continue
        neighbours.append(Neighbour(interface_ip=interface_ip, ip=ip_text, mac=mac_text))
    if not seen_interface:
        if "no arp entries" in text.lower():
            return []
        raise UnrecognizedOutput("arp -a")
    return neighbours
