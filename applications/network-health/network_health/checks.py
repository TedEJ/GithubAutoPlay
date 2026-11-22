"""The checks: turn collected facts into results with a status and a fix tip.

The checks do not know which operating system the facts came from. Every
check returns at least one CheckResult; a fact that could not be collected
gives a result with status "skipped" and the reason.
"""

from __future__ import annotations

import ipaddress
import re
import statistics
from dataclasses import asdict, dataclass, field

from . import known_hosts
from . import thresholds as t
from .collect import Facts, usable_dns_servers
from .models import (
    BAD,
    GOOD,
    INFO,
    SKIPPED,
    WARN,
    PingStats,
    Unavailable,
)

PERFORMANCE = "Performance"
WIFI = "Wi-Fi"
CONFIGURATION = "Configuration"
LOCAL_NETWORK = "Local network"
AREAS = (PERFORMANCE, WIFI, CONFIGURATION, LOCAL_NETWORK)
# The area of the device scan (--active). It is part of the report only when
# the scan ran, so the passive report keeps its four areas.
DEVICES = "Devices"


@dataclass
class CheckResult:
    id: str
    area: str
    title: str
    status: str
    summary: str
    why: str = ""
    fix: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def skipped(check_id: str, area: str, title: str, reason: Unavailable) -> CheckResult:
    return CheckResult(check_id, area, title, SKIPPED, reason.reason,
                       details={"kind": reason.kind})


def grade_low(value: float, good: float, warn: float) -> str:
    """Lower is better."""
    if value <= good:
        return GOOD
    if value <= warn:
        return WARN
    return BAD


def grade_high(value: float, good: float, warn: float) -> str:
    """Higher is better."""
    if value >= good:
        return GOOD
    if value >= warn:
        return WARN
    return BAD


def plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _ms(value: float) -> str:
    return f"{value:.0f} ms" if value >= 1 else f"{value:.1f} ms"


# ====================================================================== performance

def _ping_targets(facts: Facts):
    yield ("gateway", f"the default gateway ({facts.gateway or 'not found'})",
           facts.ping_gateway, t.GATEWAY_LATENCY_GOOD_MS, t.GATEWAY_LATENCY_WARN_MS)
    for target, owner in known_hosts.PING_TARGETS:
        yield (target, f"{target} ({owner})", facts.ping_public.get(target),
               t.INTERNET_LATENCY_GOOD_MS, t.INTERNET_LATENCY_WARN_MS)


def _internet_answers(facts: Facts) -> bool:
    return any(isinstance(s, PingStats) and s.received
               for s in facts.ping_public.values())


def check_ping(facts: Facts) -> list[CheckResult]:
    results = []
    for key, label, stats, good, warn in _ping_targets(facts):
        is_gateway = key == "gateway"
        base = f"perf.ping.{key}"
        if stats is None:
            stats = Unavailable("error", "No ping result.")
        if isinstance(stats, Unavailable):
            results.append(skipped(base, PERFORMANCE, f"Ping to {label}", stats))
            continue
        if stats.received == 0:
            if is_gateway and _internet_answers(facts):
                results.append(CheckResult(
                    f"{base}.loss", PERFORMANCE, f"Ping to {label}", INFO,
                    "The router does not answer ping, but the internet does.",
                    why="Many routers ignore ping on purpose. That is not a fault, "
                        "but latency to the router cannot be measured.",
                    fix="Nothing to fix. The internet ping results show how the "
                        "connection performs."))
            else:
                results.append(CheckResult(
                    f"{base}.loss", PERFORMANCE, f"Packet loss to {label}", BAD,
                    f"No replies from {label} ({stats.sent} pings sent).",
                    why="Without replies the connection to this address is down "
                        "or ping is blocked on the way.",
                    fix="Check that the computer is connected (cable or Wi-Fi), "
                        "restart the router and the modem, and contact your ISP "
                        "if the internet stays unreachable."))
            continue
        avg = stats.avg_ms
        status = grade_low(avg, good, warn)
        if is_gateway:
            why = ("Latency to your own router should be a few milliseconds. High "
                   "values usually mean a weak or busy Wi-Fi link, or a router "
                   "under heavy load.")
            fix = ("Move closer to the router or use a cable, switch to 5 GHz if "
                   "you can, and restart the router if it has run for a long time.")
        else:
            why = ("High latency makes video calls, games and web pages feel slow.")
            fix = ("Compare with the latency to the gateway: if that is low, the "
                   "delay is in the internet connection (contact your ISP, or "
                   "look for large uploads or downloads on the network). If the "
                   "gateway latency is high as well, fix the local link first.")
        results.append(CheckResult(
            f"{base}.latency", PERFORMANCE, f"Latency to {label}", status,
            f"Average {_ms(avg)} over {stats.received} replies.",
            why=why if status != GOOD else "", fix=fix if status != GOOD else "",
            details={"average_ms": round(avg, 2), "replies": stats.received}))

        jitter = stats.jitter_ms
        if jitter is not None:
            status = grade_low(jitter, t.JITTER_GOOD_MS, t.JITTER_WARN_MS)
            results.append(CheckResult(
                f"{base}.jitter", PERFORMANCE, f"Jitter to {label}", status,
                f"Jitter {_ms(jitter)}.",
                why=("Uneven latency causes choppy calls and lag spikes."
                     if status != GOOD else ""),
                fix=("Usually Wi-Fi interference or other traffic on the network. "
                     "Try a cable or 5 GHz, pause large downloads, and see the "
                     "bufferbloat result." if status != GOOD else ""),
                details={"jitter_ms": round(jitter, 2)}))

        loss = stats.loss_pct
        status = grade_low(loss, t.LOSS_GOOD_PCT, t.LOSS_WARN_PCT)
        if is_gateway:
            fix = ("Loss to your own router points at the Wi-Fi link or a bad "
                   "cable: move closer, change the Wi-Fi channel, or replace the "
                   "cable.")
        else:
            fix = ("If the gateway shows no loss, the loss is beyond your router: "
                   "restart the modem and router, and contact your ISP if it stays.")
        results.append(CheckResult(
            f"{base}.loss", PERFORMANCE, f"Packet loss to {label}", status,
            f"{loss:.0f} % loss ({stats.sent - stats.received} of {stats.sent} lost).",
            why=("Lost packets cause stutter, slow pages and dropped calls."
                 if status != GOOD else ""),
            fix=fix if status != GOOD else "",
            details={"loss_pct": round(loss, 1), "sent": stats.sent,
                     "received": stats.received}))
    return results


def classify_dns(server: str, facts: Facts) -> tuple[str, str]:
    """Return (kind, label) for a DNS server address."""
    address = server.split("%")[0]
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unknown", "an address that could not be read"
    primary = facts.primary
    gateways = (primary.ipv4_gateways + primary.ipv6_gateways) if primary else []
    if any(_same_ip(ip, g) for g in gateways):
        return "router", "the router"
    if primary:
        for entry in primary.ipv4:
            try:
                network = ipaddress.ip_interface(
                    f"{entry.address}/{entry.prefix_length}").network
            except ValueError:
                continue
            if ip.version == 4 and ip in network:
                return "local", "a device on your local network"
    name = known_hosts.resolver_name(address)
    if name:
        return "public", f"public resolver {name}"
    if ip.version == 6 and ip.is_link_local:
        return "router", "the router (IPv6 link-local address)"
    if known_hosts.is_private_range(address):
        return "private", "a private address outside your network (VPN, ISP or company)"
    return "isp", "your ISP or another public resolver"


def _same_ip(ip, other: str) -> bool:
    try:
        return ip == ipaddress.ip_address(other.split("%")[0])
    except ValueError:
        return False


def check_dns_time(facts: Facts) -> list[CheckResult]:
    title = "DNS lookup time"
    if isinstance(facts.dns, Unavailable):
        return [skipped("perf.dns", PERFORMANCE, title, facts.dns)]
    if not facts.dns:
        return [skipped("perf.dns", PERFORMANCE, title,
                        Unavailable("not-applicable", "No DNS servers were found."))]
    results = []
    for server, timing in facts.dns.items():
        _, label = classify_dns(server, facts)
        check_id = f"perf.dns.{server}"
        if isinstance(timing, Unavailable):
            results.append(skipped(check_id, PERFORMANCE, f"{title} ({server})", timing))
            continue
        median = timing.median_ms
        if median is None:
            results.append(CheckResult(
                check_id, PERFORMANCE, f"{title} ({server})", BAD,
                f"{server} ({label}) did not answer any of "
                f"{timing.failures} DNS queries.",
                why="A DNS server that does not answer makes every new web "
                    "address slow or fail to open.",
                fix="Restart the router. If it keeps failing, set two working DNS "
                    "servers in the router's DHCP settings (for example your "
                    "ISP's or a public resolver)."))
            continue
        status = grade_low(median, t.DNS_GOOD_MS, t.DNS_WARN_MS)
        summary = f"{server} ({label}) answered in {_ms(median)} (median)."
        if timing.failures:
            status = BAD if status == BAD else WARN
            summary += f" {timing.failures} queries got no answer."
        results.append(CheckResult(
            check_id, PERFORMANCE, f"{title} ({server})", status, summary,
            why=("Slow or unreliable DNS makes every new web address slow to open."
                 if status != GOOD else ""),
            fix=("Restart the router. If the delay stays, try a faster resolver: "
                 "set it in the router so every device gets it." if status != GOOD else ""),
            details={"median_ms": round(median, 2), "failures": timing.failures}))
    return results


def check_mtu(facts: Facts) -> list[CheckResult]:
    title = "Path MTU"
    if isinstance(facts.mtu, Unavailable) or facts.mtu is None:
        return [skipped("perf.mtu", PERFORMANCE, title,
                        facts.mtu or Unavailable("error", "Not measured."))]
    mtu = facts.mtu.mtu
    if mtu >= t.MTU_FULL:
        return [CheckResult("perf.mtu", PERFORMANCE, title, GOOD,
                            f"Packets of {mtu} bytes reach {facts.mtu.target} unfragmented.",
                            details={"mtu": mtu})]
    if mtu >= t.MTU_WARN_BELOW:
        return [CheckResult(
            "perf.mtu", PERFORMANCE, title, INFO,
            f"The path MTU is {mtu} bytes.",
            why="Slightly below 1500 is normal for PPPoE connections (1492) and "
                "many VPNs.",
            fix="Nothing to do unless some websites hang while loading; then "
                "check the MTU setting on the router's internet (WAN) page.",
            details={"mtu": mtu})]
    return [CheckResult(
        "perf.mtu", PERFORMANCE, title, WARN, f"The path MTU is only {mtu} bytes.",
        why="A small MTU means more packets per transfer, and when it is not "
            "announced correctly some websites hang while loading.",
        fix="Check the MTU setting on the router's internet (WAN or PPPoE) page "
            "and in any VPN. Most connections allow 1500, PPPoE 1492.",
        details={"mtu": mtu})]


def check_bandwidth(facts: Facts) -> list[CheckResult]:
    bw = facts.bandwidth
    if isinstance(bw, Unavailable) or bw is None:
        reason = bw or Unavailable("error", "Not measured.")
        return [skipped("perf.download", PERFORMANCE, "Download speed", reason),
                skipped("perf.upload", PERFORMANCE, "Upload speed", reason),
                skipped("perf.bufferbloat", PERFORMANCE, "Bufferbloat", reason)]
    results = []
    for check_id, title, value, error, good, warn, size in (
        ("perf.download", "Download speed", bw.download_mbps, bw.download_error,
         t.DOWNLOAD_GOOD_MBPS, t.DOWNLOAD_WARN_MBPS, bw.download_bytes),
        ("perf.upload", "Upload speed", bw.upload_mbps, bw.upload_error,
         t.UPLOAD_GOOD_MBPS, t.UPLOAD_WARN_MBPS, bw.upload_bytes),
    ):
        if value is None:
            results.append(skipped(check_id, PERFORMANCE, title,
                                   Unavailable("error", (error or "Not measured.").capitalize())))
            continue
        status = grade_high(value, good, warn)
        direction = title.split()[0].lower()
        results.append(CheckResult(
            check_id, PERFORMANCE, title, status,
            f"{value:.1f} Mbit/s ({size / 1e6:.1f} MB against {bw.server}).",
            why=(f"A low {direction} speed makes streaming, video calls, backups "
                 "and updates slow." if status != GOOD else ""),
            fix=("Compare with the speed of your subscription. Test again with a "
                 "cable next to the router: if it is fast there, the Wi-Fi is the "
                 "bottleneck; if it is slow there too, contact your ISP."
                 if status != GOOD else ""),
            details={"mbps": round(value, 2), "bytes": size, "server": bw.server}))
    results.append(_bufferbloat(facts, bw))
    return results


def _too_few_samples_reason(bw) -> str:
    count = len(bw.loaded_latency_ms)
    durations = [s for s in (bw.download_seconds, bw.upload_seconds) if s is not None]
    if durations and sum(durations) < t.BUFFERBLOAT_SHORT_LOAD_S:
        parts = []
        if bw.download_seconds is not None:
            parts.append(f"{bw.download_seconds:.1f} s down")
        if bw.upload_seconds is not None:
            parts.append(f"{bw.upload_seconds:.1f} s up")
        return (f"Only {count} latency samples: the link is so fast that the "
                f"size-capped bandwidth test took just {' and '.join(parts)}, "
                "too short to measure latency under load.")
    return (f"Only {count} latency samples during the bandwidth test: ping got "
            "no replies while the test ran.")


def _bufferbloat(facts: Facts, bw) -> CheckResult:
    title = "Bufferbloat (latency under load)"
    idle_stats = facts.ping_public.get(known_hosts.BUFFERBLOAT_TARGET)
    if not isinstance(idle_stats, PingStats) or idle_stats.avg_ms is None:
        return skipped("perf.bufferbloat", PERFORMANCE, title, Unavailable(
            "error", "No idle latency to compare with."))
    if len(bw.loaded_latency_ms) < t.BUFFERBLOAT_MIN_SAMPLES:
        return skipped("perf.bufferbloat", PERFORMANCE, title,
                       Unavailable("error", _too_few_samples_reason(bw)))
    idle = idle_stats.avg_ms
    loaded = statistics.median(bw.loaded_latency_ms)
    increase = max(loaded - idle, 0.0)
    status = grade_low(increase, t.BUFFERBLOAT_GOOD_MS, t.BUFFERBLOAT_WARN_MS)
    return CheckResult(
        "perf.bufferbloat", PERFORMANCE, title, status,
        f"Latency rose by {_ms(increase)} under load ({_ms(idle)} idle, "
        f"{_ms(loaded)} loaded).",
        why=("When the line is full, a large buffer in the router or modem "
             "delays everything else: calls and games lag while someone "
             "downloads." if status != GOOD else ""),
        fix=("Turn on Smart Queue Management (SQM) or QoS with fq_codel or CAKE "
             "in the router, set a little below your line speed. If the router "
             "has no such setting, a newer router may help." if status != GOOD else ""),
        details={"idle_ms": round(idle, 2), "loaded_ms": round(loaded, 2),
                 "increase_ms": round(increase, 2),
                 "samples": len(bw.loaded_latency_ms)})


# ====================================================================== Wi-Fi

def classify_security(authentication: str, cipher: str) -> tuple[str, str] | None:
    """Return (status, description) or None when not recognised."""
    auth = authentication.lower()
    ciph = cipher.lower()
    if "wep" in ciph or "shared" in auth:
        return BAD, "WEP, which can be broken in minutes"
    if auth.startswith("open") and ("none" in ciph or not ciph):
        return BAD, "an open network without encryption"
    if "owe" in auth or "enhanced open" in auth:
        return WARN, "Enhanced Open (encrypted, but anyone can join)"
    if "tkip" in ciph:
        return BAD, f"{authentication} with TKIP, which is outdated and weak"
    if auth.startswith("wpa3"):
        return GOOD, f"{authentication} ({cipher}), the best available"
    if auth.startswith("wpa2"):
        if "ccmp" in ciph or "gcmp" in ciph or "aes" in ciph:
            return GOOD, f"{authentication} with AES ({cipher}), which is fine"
        return None
    if auth.startswith("wpa"):
        return BAD, f"{authentication} (the first WPA), which is outdated"
    return None


def _overlaps(band: str | None, mine: int, other: int) -> bool:
    if band == "2.4 GHz":
        return abs(mine - other) <= t.OVERLAP_24GHZ_CHANNELS
    return mine == other


def check_wifi(facts: Facts) -> list[CheckResult]:
    wifi = facts.wifi
    if isinstance(wifi, Unavailable) or wifi is None:
        return [skipped("wifi", WIFI, "Wi-Fi", wifi or Unavailable("error", "Not read."))]
    if not wifi.connected:
        return [skipped("wifi", WIFI, "Wi-Fi", Unavailable(
            "not-applicable", "This computer is not connected over Wi-Fi."))]
    results = []

    # Signal strength
    if wifi.signal_pct is None:
        results.append(skipped("wifi.signal", WIFI, "Signal strength",
                               Unavailable("unrecognized", "No signal value was found.")))
    else:
        status = grade_high(wifi.signal_pct, t.SIGNAL_GOOD_PCT, t.SIGNAL_WARN_PCT)
        rssi = f" ({wifi.rssi_dbm} dBm)" if wifi.rssi_dbm is not None else ""
        results.append(CheckResult(
            "wifi.signal", WIFI, "Signal strength", status,
            f"Signal {wifi.signal_pct} %{rssi}.",
            why=("A weak signal gives lower speed and more retries."
                 if status != GOOD else ""),
            fix=("Move closer to the router or remove obstacles; place the router "
                 "high and central; a mesh system or an extra access point helps "
                 "distant rooms." if status != GOOD else ""),
            details={"signal_pct": wifi.signal_pct, "rssi_dbm": wifi.rssi_dbm}))

    # Link rate
    rates = [r for r in (wifi.receive_mbps, wifi.transmit_mbps) if r is not None]
    if not rates:
        results.append(skipped("wifi.link_rate", WIFI, "Link rate",
                               Unavailable("unrecognized", "No link rate was found.")))
    else:
        rate = min(rates)
        status = grade_high(rate, t.LINK_RATE_GOOD_MBPS, t.LINK_RATE_WARN_MBPS)
        results.append(CheckResult(
            "wifi.link_rate", WIFI, "Link rate", status,
            f"{wifi.receive_mbps or 0:g} Mbit/s receive, "
            f"{wifi.transmit_mbps or 0:g} Mbit/s transmit ({wifi.radio_type or 'radio type unknown'}).",
            why=("The link rate is the speed the Wi-Fi radio negotiated; real "
                 "throughput is about half of it." if status != GOOD else ""),
            fix=("Move closer to the router, use 5 GHz or 6 GHz, and check that "
                 "the router supports Wi-Fi 5 or Wi-Fi 6." if status != GOOD else ""),
            details={"receive_mbps": wifi.receive_mbps, "transmit_mbps": wifi.transmit_mbps}))

    # Band
    if wifi.band is None:
        results.append(skipped("wifi.band", WIFI, "Band",
                               Unavailable("unrecognized", "The band was not found.")))
    elif wifi.band == "2.4 GHz":
        results.append(CheckResult(
            "wifi.band", WIFI, "Band", INFO,
            f"Connected on 2.4 GHz (channel {wifi.channel}).",
            why="2.4 GHz reaches further but is slower and more crowded than "
                "5 GHz or 6 GHz.",
            fix="If the router and this computer support 5 GHz, connect to the "
                "5 GHz network (or turn on band steering) when you are not far "
                "from the router.",
            details={"band": wifi.band, "channel": wifi.channel}))
    else:
        results.append(CheckResult(
            "wifi.band", WIFI, "Band", GOOD,
            f"Connected on {wifi.band} (channel {wifi.channel}).",
            details={"band": wifi.band, "channel": wifi.channel}))

    results.append(_congestion(facts, wifi))

    # Security
    security = classify_security(wifi.authentication, wifi.cipher)
    if security is None:
        results.append(skipped("wifi.security", WIFI, "Wi-Fi security", Unavailable(
            "unrecognized", f"Unknown security '{wifi.authentication}' / "
                            f"'{wifi.cipher}'.")))
    else:
        status, description = security
        fixes = {
            BAD: "Change the router's Wi-Fi security to WPA2-Personal (AES) or, "
                 "better, WPA3-Personal, with a long passphrase. Replace devices "
                 "that only support WEP, WPA or TKIP.",
            WARN: "Anyone in range can join. Use WPA2 or WPA3 with a passphrase "
                  "on a network you own.",
        }
        results.append(CheckResult(
            "wifi.security", WIFI, "Wi-Fi security", status,
            f"The network uses {description}.",
            why=("Weak Wi-Fi security lets others read the traffic or join the "
                 "network." if status != GOOD else ""),
            fix=fixes.get(status, ""),
            details={"authentication": wifi.authentication, "cipher": wifi.cipher}))
    return results


def _congestion(facts: Facts, wifi) -> CheckResult:
    title = "Channel congestion"
    networks = facts.wifi_networks
    if isinstance(networks, Unavailable) or networks is None:
        return skipped("wifi.congestion", WIFI, title,
                       networks or Unavailable("error", "Not read."))
    if wifi.channel is None:
        return skipped("wifi.congestion", WIFI, title,
                       Unavailable("unrecognized", "The channel was not found."))
    others = [n for n in networks
              if n.ssid != wifi.ssid and n.bssid != wifi.bssid
              and n.channel is not None and n.band == wifi.band
              and _overlaps(wifi.band, wifi.channel, n.channel)]
    count = len(others)
    status = (GOOD if count <= t.CONGESTION_GOOD_MAX
              else WARN if count <= t.CONGESTION_WARN_MAX else BAD)
    fix = ""
    if status != GOOD:
        fix = ("Choose a less used channel in the router's Wi-Fi settings (or "
               "let it pick automatically), or use 5 GHz, which has more channels.")
        if wifi.band == "2.4 GHz":
            load = {c: sum(1 for n in networks if n.band == "2.4 GHz"
                           and n.ssid != wifi.ssid and n.channel is not None
                           and _overlaps("2.4 GHz", c, n.channel))
                    for c in (1, 6, 11)}
            best = min(load, key=load.get)
            fix += f" On 2.4 GHz use 1, 6 or 11; channel {best} looks least crowded."
    overlap = "share or overlap" if wifi.band == "2.4 GHz" else "share"
    return CheckResult(
        "wifi.congestion", WIFI, title, status,
        f"{plural(count, 'other network')} {overlap} channel {wifi.channel} "
        f"({wifi.band}).",
        why=("Networks on the same channel take turns to send, which lowers "
             "speed and raises latency." if status != GOOD else ""),
        fix=fix, details={"other_networks": count, "channel": wifi.channel})


# ====================================================================== configuration

def check_profile(facts: Facts) -> CheckResult:
    title = "Network profile"
    profiles = facts.profiles
    if isinstance(profiles, Unavailable) or profiles is None:
        return skipped("config.profile", CONFIGURATION, title,
                       profiles or Unavailable("error", "Not read."))
    if not profiles:
        return skipped("config.profile", CONFIGURATION, title,
                       Unavailable("not-applicable", "No connection profile was found."))
    summary = "; ".join(f"{p.interface_alias}: {p.category}" for p in profiles)
    private = [p for p in profiles if p.category == "Private"]
    open_wifi = (not isinstance(facts.wifi, Unavailable) and facts.wifi is not None
                 and facts.wifi.connected
                 and (classify_security(facts.wifi.authentication, facts.wifi.cipher)
                      or (None,))[0] == BAD)
    if private and open_wifi:
        return CheckResult(
            "config.profile", CONFIGURATION, title, WARN, summary,
            why="The profile is Private on a Wi-Fi network without proper "
                "security, so others nearby may see and reach this computer.",
            fix="Set the network to Public: Settings > Network & internet > "
                "Wi-Fi > (the network) > Network profile type > Public.")
    if private:
        return CheckResult(
            "config.profile", CONFIGURATION, title, INFO, summary,
            why="Private lets other devices on the network find this computer "
                "and use its shared files and printers.",
            fix="Fine on a home network you trust. On any other network choose "
                "Public in Settings > Network & internet.")
    return CheckResult("config.profile", CONFIGURATION, title, GOOD, summary)


def check_firewall(facts: Facts) -> CheckResult:
    title = "Windows Firewall"
    fw = facts.firewall
    if isinstance(fw, Unavailable) or fw is None:
        return skipped("config.firewall", CONFIGURATION, title,
                       fw or Unavailable("error", "Not read."))
    off = [p.name for p in fw if not p.enabled]
    if off:
        return CheckResult(
            "config.firewall", CONFIGURATION, title, BAD,
            "The firewall is OFF for: " + ", ".join(off) + ".",
            why="Without the firewall, every program that listens on the network "
                "can be reached by other devices.",
            fix="Turn it on: Windows Security > Firewall & network protection, "
                "for Domain, Private and Public. If another security product "
                "manages the firewall, check its settings instead.",
            details={"off": off})
    return CheckResult("config.firewall", CONFIGURATION, title, GOOD,
                       "The firewall is on for every profile ("
                       + ", ".join(p.name for p in fw) + ").")


def check_dns_servers(facts: Facts) -> CheckResult:
    title = "DNS servers"
    if isinstance(facts.adapters, Unavailable) or facts.adapters is None:
        return skipped("config.dns_servers", CONFIGURATION, title,
                       facts.adapters or Unavailable("error", "Not read."))
    servers = usable_dns_servers(facts.primary)
    if not servers:
        return CheckResult(
            "config.dns_servers", CONFIGURATION, title, BAD,
            "No DNS server is configured.",
            why="Without DNS, names such as websites cannot be looked up.",
            fix="Set the adapter to get DNS servers automatically (DHCP), or "
                "enter the router's address as DNS server.")
    kinds = {s: classify_dns(s, facts) for s in servers}
    summary = "; ".join(f"{s} ({label})" for s, (_, label) in kinds.items())
    if any(kind == "isp" for kind, _ in kinds.values()):
        return CheckResult(
            "config.dns_servers", CONFIGURATION, title, INFO, summary,
            why="A DNS server that is neither the router nor a well-known public "
                "resolver is usually your ISP's. If you did not choose it, "
                "malware or a changed router could have set it.",
            fix="Check that the address belongs to your ISP (the router's status "
                "page usually lists the ISP's DNS servers). If not, set DNS back "
                "to automatic and check the router's DNS settings.",
            details={"servers": {s: k for s, (k, _) in kinds.items()}})
    return CheckResult("config.dns_servers", CONFIGURATION, title, GOOD, summary,
                       details={"servers": {s: k for s, (k, _) in kinds.items()}})


def check_ipv6(facts: Facts) -> CheckResult:
    title = "IPv6"
    if facts.primary is None:
        reason = (facts.adapters if isinstance(facts.adapters, Unavailable)
                  else Unavailable("not-applicable", "No active network adapter."))
        return skipped("config.ipv6", CONFIGURATION, title, reason)
    if facts.primary.ipv6_global:
        return CheckResult("config.ipv6", CONFIGURATION, title, GOOD,
                           "IPv6 is available (the adapter has a global IPv6 address).")
    return CheckResult(
        "config.ipv6", CONFIGURATION, title, INFO,
        "No global IPv6 address: the network uses IPv4 only.",
        why="Everything works over IPv4, but IPv6 can give more direct "
            "connections, for example for games and calls.",
        fix="Optional: turn on IPv6 in the router if your ISP offers it.")


def check_dhcp(facts: Facts) -> CheckResult:
    title = "IP address and DHCP lease"
    primary = facts.primary
    if primary is None:
        reason = (facts.adapters if isinstance(facts.adapters, Unavailable)
                  else Unavailable("not-applicable", "No active network adapter."))
        return skipped("config.dhcp", CONFIGURATION, title, reason)
    if not primary.ipv4:
        return CheckResult(
            "config.dhcp", CONFIGURATION, title, BAD,
            f"{primary.alias} has no IPv4 address.",
            why="Without an address the computer cannot use the network.",
            fix="Restart the router, then reconnect (or run 'ipconfig /renew').")
    entry = primary.ipv4[0]
    try:
        link_local = ipaddress.ip_address(entry.address).is_link_local
    except ValueError:
        link_local = False
    if link_local:
        return CheckResult(
            "config.dhcp", CONFIGURATION, title, BAD,
            f"{primary.alias} has a self-assigned address ({entry.address}).",
            why="Windows gives itself a 169.254 address when no DHCP server "
                "answers, so the computer has no working network address.",
            fix="Restart the router and reconnect. Check that the router's DHCP "
                "server is on and that its address pool is not full.")
    if entry.origin.lower() == "dhcp":
        lifetime = entry.valid_lifetime_s
        hours = f"{lifetime / 3600:.1f} hours" if lifetime is not None else "unknown time"
        if lifetime is not None and lifetime < t.SHORT_LEASE_S:
            return CheckResult(
                "config.dhcp", CONFIGURATION, title, INFO,
                f"Address {entry.address}/{entry.prefix_length} from DHCP; the "
                f"lease runs out in {hours}.",
                why="A short lease is normal on guest and public networks; at "
                    "home it can mean the router renews addresses very often.",
                fix="On your own router, a lease time of 12 to 24 hours is common.",
                details={"lease_remaining_s": lifetime})
        return CheckResult(
            "config.dhcp", CONFIGURATION, title, GOOD,
            f"Address {entry.address}/{entry.prefix_length} from DHCP; the lease "
            f"runs out in {hours}.",
            details={"lease_remaining_s": lifetime})
    if entry.origin.lower() == "manual":
        return CheckResult(
            "config.dhcp", CONFIGURATION, title, INFO,
            f"Static address {entry.address}/{entry.prefix_length} (not from DHCP).",
            why="A fixed address is fine when set on purpose, but it can clash "
                "with an address the router hands out.",
            fix="Keep it outside the router's DHCP range, or use a DHCP "
                "reservation in the router instead.")
    return CheckResult("config.dhcp", CONFIGURATION, title, GOOD,
                       f"Address {entry.address}/{entry.prefix_length} ({entry.origin}).")


def hide_credentials(value: str) -> str:
    """Hide a user name and password in a proxy address (user:pass@host)."""
    return re.sub(r"(^|//)[^/@\s]+@", lambda m: m.group(1) + "***@", value)


def check_proxy(facts: Facts) -> CheckResult:
    title = "Proxy settings"
    proxy = facts.proxy
    if isinstance(proxy, Unavailable) or proxy is None:
        return skipped("config.proxy", CONFIGURATION, title,
                       proxy or Unavailable("error", "Not read."))
    found = []
    if proxy.user_proxy_enabled and proxy.user_proxy_server:
        found.append(f"proxy server {hide_credentials(proxy.user_proxy_server)} (Windows settings)")
    elif proxy.user_proxy_enabled:
        found.append("a proxy is switched on in Windows settings")
    if proxy.auto_config_url:
        found.append(f"automatic configuration script {hide_credentials(proxy.auto_config_url)}")
    if proxy.winhttp_proxy:
        found.append(f"system (WinHTTP) proxy {hide_credentials(proxy.winhttp_proxy)}")
    for name, value in proxy.environment.items():
        found.append(f"environment variable {name}={hide_credentials(value)}")
    if found:
        return CheckResult(
            "config.proxy", CONFIGURATION, title, WARN,
            "Proxy in use: " + "; ".join(found) + ".",
            why="A proxy sees the web traffic that goes through it. Companies and "
                "schools set one on purpose, but malware and adware also set "
                "proxies.",
            fix="If you did not set it, remove it: Settings > Network & internet "
                "> Proxy (and 'netsh winhttp reset proxy' for the system proxy), "
                "then run a malware scan.",
            details={"found": found})
    note = "" if proxy.winhttp_known else " (the system WinHTTP proxy could not be read)"
    return CheckResult("config.proxy", CONFIGURATION, title, GOOD,
                       "No proxy is set." + note)


REMOTE_ACCESS_PORTS = {21: "FTP", 22: "SSH", 23: "Telnet", 3389: "Remote Desktop",
                       5900: "VNC", 5985: "WinRM", 5986: "WinRM (HTTPS)"}
FILE_SHARING_PORTS = {139: "NetBIOS file sharing", 445: "SMB file sharing"}


def _exposed(address: str) -> bool:
    try:
        return not ipaddress.ip_address(address.split("%")[0]).is_loopback
    except ValueError:
        return True


def _port_text(ports) -> str:
    return ", ".join(f"{p.port}" + (f" ({p.process})" if p.process else "")
                     for p in sorted(ports, key=lambda p: p.port))


def check_listening_ports(facts: Facts) -> list[CheckResult]:
    title = "Ports open to the network"
    listening = facts.listening
    if isinstance(listening, Unavailable) or listening is None:
        return [skipped("config.ports", CONFIGURATION, title,
                        listening or Unavailable("error", "Not read."))]
    exposed = {}
    for port in listening:
        if _exposed(port.address):
            exposed.setdefault(port.port, port)
    if not exposed:
        return [CheckResult("config.ports", CONFIGURATION, title, GOOD,
                            "No TCP port listens on the network (only on this "
                            "computer itself).")]
    results = []
    remote = [p for n, p in exposed.items() if n in REMOTE_ACCESS_PORTS]
    sharing = [p for n, p in exposed.items() if n in FILE_SHARING_PORTS]
    other = [p for n, p in exposed.items()
             if n not in REMOTE_ACCESS_PORTS and n not in FILE_SHARING_PORTS]
    if remote:
        names = ", ".join(f"{p.port} {REMOTE_ACCESS_PORTS[p.port]}" for p in remote)
        results.append(CheckResult(
            "config.ports.remote", CONFIGURATION, "Remote access ports", WARN,
            f"Remote access listens on the network: {names}.",
            why="Remote access services are a common target for password "
                "guessing and attacks from other devices on the network.",
            fix="Turn the service off if you do not use it (for Remote Desktop: "
                "Settings > System > Remote Desktop). If you need it, keep the "
                "firewall on, use strong passwords and never forward the port "
                "in the router.",
            details={"ports": sorted(p.port for p in remote)}))
    if sharing:
        # Windows always listens on these ports; whether other devices can
        # reach them depends on the firewall rules, which are not read here.
        private = (isinstance(facts.profiles, list)
                   and any(p.category == "Private" for p in facts.profiles))
        results.append(CheckResult(
            "config.ports.sharing", CONFIGURATION, "File sharing ports", INFO,
            "File sharing listens on the network: "
            + ", ".join(f"{p.port}" for p in sharing) + ".",
            why=("Windows always listens on these ports. With a Private profile "
                 "and 'File and printer sharing' turned on, other devices on "
                 "the network can reach them." if private else
                 "Windows always listens on these ports; with a Public profile "
                 "the firewall blocks them from other devices."),
            fix=("If you do not share files or printers, turn off 'File and "
                 "printer sharing' in Settings > Network & internet > Advanced "
                 "network settings > Advanced sharing settings." if private else
                 "Nothing to do while the profile is Public and the firewall is on."),
            details={"ports": sorted(p.port for p in sharing), "private": private}))
    if other:
        results.append(CheckResult(
            "config.ports.other", CONFIGURATION, "Other listening ports", INFO,
            f"{plural(len(other), 'other TCP port')} listening on the network: "
            f"{_port_text(other)}.",
            why="Programs that listen on all network addresses can be reached "
                "from the network when the firewall allows it.",
            fix="Check that you know each program. Uninstall or turn off what "
                "you do not use; the firewall blocks the rest on a Public network.",
            details={"ports": sorted(p.port for p in other)}))
    return results


# ====================================================================== local network

def _primary_ipv4(facts: Facts) -> set[str]:
    return {e.address for e in facts.primary.ipv4} if facts.primary else set()


def check_local_network(facts: Facts, previous: dict | None) -> list[CheckResult]:
    neighbours = facts.neighbours
    if isinstance(neighbours, Unavailable) or neighbours is None:
        reason = neighbours or Unavailable("error", "Not read.")
        return [skipped("lan.neighbours", LOCAL_NETWORK, "Known neighbours", reason)]
    own = _primary_ipv4(facts)
    on_lan = [n for n in neighbours if not own or n.interface_ip in own]
    results = [CheckResult(
        "lan.neighbours", LOCAL_NETWORK, "Known neighbours", GOOD,
        f"{plural(len(on_lan), 'device')} in this computer's ARP table (devices "
        "it talked to recently; not a full scan).",
        details={"count": len(on_lan)})]

    by_mac: dict[str, list[str]] = {}
    for n in on_lan:
        by_mac.setdefault(n.mac, []).append(n.ip)
    duplicates = {mac: ips for mac, ips in by_mac.items() if len(ips) > 1}
    if not duplicates:
        results.append(CheckResult(
            "lan.duplicate_mac", LOCAL_NETWORK, "Duplicate MAC addresses", GOOD,
            "Every MAC address in the ARP table belongs to one IP address."))
    else:
        gateway_involved = any(facts.gateway in ips for ips in duplicates.values())
        text = "; ".join(f"{mac} is used by {', '.join(ips)}"
                         for mac, ips in duplicates.items())
        results.append(CheckResult(
            "lan.duplicate_mac", LOCAL_NETWORK, "Duplicate MAC addresses",
            BAD if gateway_involved else WARN, text + ".",
            why=("Another device answers for the gateway's address. That is how "
                 "ARP spoofing (a man-in-the-middle attack) looks."
                 if gateway_involved else
                 "One device answers for several addresses. Wi-Fi extenders and "
                 "virtual machines do this; it can also be ARP spoofing."),
            fix=("Disconnect unknown devices, restart the router, and run the "
                 "check again. If it persists, look up the MAC address in the "
                 "router's client list." if gateway_involved else
                 "If you have a Wi-Fi extender or a device with several "
                 "addresses, this is expected. Otherwise find the device in the "
                 "router's client list."),
            details={"duplicates": duplicates}))

    results.append(_gateway_mac(facts, on_lan, previous))
    return results


def gateway_mac(facts: Facts, neighbours=None) -> str | None:
    if not facts.gateway:
        return None
    entries = neighbours if neighbours is not None else (
        facts.neighbours if isinstance(facts.neighbours, list) else [])
    for n in entries:
        if n.ip == facts.gateway:
            return n.mac
    return None


def network_identity(facts: Facts) -> dict:
    ssid = (facts.wifi.ssid if not isinstance(facts.wifi, Unavailable)
            and facts.wifi is not None and facts.wifi.connected else "")
    return {"gateway": facts.gateway, "ssid": ssid}


def _gateway_mac(facts: Facts, on_lan, previous: dict | None) -> CheckResult:
    title = "Gateway MAC address"
    mac = gateway_mac(facts, on_lan)
    if mac is None:
        return skipped("lan.gateway_mac", LOCAL_NETWORK, title, Unavailable(
            "not-applicable", "The gateway is not in the ARP table."))
    if not previous:
        return CheckResult(
            "lan.gateway_mac", LOCAL_NETWORK, title, INFO,
            f"Gateway {facts.gateway} has MAC {mac}. No earlier snapshot to "
            "compare with.",
            why="A changed gateway MAC address can be a sign of ARP spoofing.",
            fix="Run with --save once on this network, so later runs can "
                "compare.")
    same_network = previous.get("network") == network_identity(facts)
    if not same_network:
        return CheckResult(
            "lan.gateway_mac", LOCAL_NETWORK, title, INFO,
            f"Gateway {facts.gateway} has MAC {mac}. The last snapshot is from "
            "another network.",
            fix="Run with --save on this network to compare next time.")
    old = previous.get("gateway_mac")
    if old and old != mac:
        return CheckResult(
            "lan.gateway_mac", LOCAL_NETWORK, title, WARN,
            f"The gateway's MAC address changed from {old} to {mac} since the "
            f"snapshot of {previous.get('generated', 'an earlier run')}.",
            why="If the router was not replaced or reset, another device may "
                "pretend to be the router (ARP spoofing).",
            fix="If you did not change the router, restart it, disconnect unknown "
                "devices, and run the check again. If the router was replaced, "
                "run with --save to store the new address.",
            details={"old": old, "new": mac})
    return CheckResult("lan.gateway_mac", LOCAL_NETWORK, title, GOOD,
                       f"Gateway {facts.gateway} has the same MAC address as in "
                       "the last snapshot.")


# ====================================================================== all

def run_checks(facts: Facts, previous: dict | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    results += check_ping(facts)
    results += check_dns_time(facts)
    results += check_mtu(facts)
    results += check_bandwidth(facts)
    results += check_wifi(facts)
    results.append(check_profile(facts))
    results.append(check_firewall(facts))
    results.append(check_dns_servers(facts))
    results.append(check_ipv6(facts))
    results.append(check_dhcp(facts))
    results.append(check_proxy(facts))
    results += check_listening_ports(facts)
    results += check_local_network(facts, previous)
    return results
