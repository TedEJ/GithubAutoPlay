"""The device scan of --active: find the devices on the subnet and check their
ports.

Steps (all limits are in thresholds.py and in the design document):

1. Ping sweep of the subnet with the system ping (platform.ping_host), 32 at
   a time, one echo request per address, at most 50 per second.
2. mDNS and SSDP queries to their multicast groups, in parallel, two sends
   each, for device names and types.
3. The ARP table (the sweep has just filled it, so devices that do not answer
   ping but do answer ARP are found too).
4. A TCP connect check of the ports of services.PORT_PLAN on every device
   found, 16 devices at the same time, the ports of one device one after the
   other, at most 50 checks per second, and a banner or HTTP head or TLS
   handshake for the ports that are open.
5. Name, vendor and a guess of the kind of each device.

The whole scan stops starting new work when the time limit is used up
(Deadline); the result then says it is incomplete. Every address is checked by
the ScanGuard before anything is sent to it. Only addresses of the subnet are
ever probed: devices that answer mDNS or SSDP from another address are
ignored.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import discovery, oui, services, thresholds
from .devices import Device, DeviceScan
from .models import Unavailable
from .netio import NetIO, NetIOError, ProbeResult
from .safe_text import clean_text
from .scan_target import MDNS_GROUP, SSDP_GROUP, ScanGuard, ScanRefused, ScanTarget


SKIPPED = "skipped"   # a sweep address that was not pinged because of the time limit
FAILED = "failed"     # a sweep address whose ping could not run


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep_until(self, moment: float) -> None:
        delay = moment - time.monotonic()
        if delay > 0:
            time.sleep(delay)


@dataclass
class ScanLimits:
    time_limit_s: float = thresholds.SCAN_TIME_LIMIT_S
    max_operation_s: float = thresholds.SCAN_MAX_OPERATION_S
    sweep_budget_s: float = thresholds.SCAN_SWEEP_BUDGET_S
    sweep_workers: int = thresholds.SWEEP_WORKERS
    port_workers: int = thresholds.PORT_WORKERS
    sweep_interval_s: float = thresholds.SWEEP_INTERVAL_S
    port_interval_s: float = thresholds.PORT_INTERVAL_S
    sweep_ping_timeout_ms: int = thresholds.SWEEP_PING_TIMEOUT_MS
    connect_timeout_s: float = thresholds.CONNECT_TIMEOUT_S
    banner_wait_s: float = thresholds.BANNER_WAIT_S
    http_wait_s: float = thresholds.HTTP_WAIT_S
    tls_timeout_s: float = thresholds.TLS_TIMEOUT_S
    multicast_sends: int = thresholds.MULTICAST_SENDS
    multicast_wait_s: float = thresholds.MULTICAST_WAIT_S


class Deadline:
    """Stops new work in time: no operation is started when it could run past
    the end (the longest operation takes max_operation_s)."""

    def __init__(self, clock, start: float, limit_s: float, max_operation_s: float):
        self.clock = clock
        self.end = start + limit_s
        self.max_operation_s = max_operation_s

    def can_start(self, duration_s: float) -> bool:
        return self.clock.monotonic() + duration_s <= self.end

    def expired(self) -> bool:
        return not self.can_start(self.max_operation_s)


class Pacer:
    """The rate limit: operations of all workers start at least `interval_s`
    apart."""

    def __init__(self, clock, interval_s: float):
        self.clock = clock
        self.interval_s = interval_s
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self.clock.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval_s
        if start > now:
            self.clock.sleep_until(start)


def scan(platform, target: ScanTarget, guard: ScanGuard, io: NetIO, *,
         gateway: str | None = None, clock=None, limits: ScanLimits | None = None,
         progress=None) -> DeviceScan:
    """Run the device scan. ScanRefused comes out when something would be sent
    outside the subnet (a bug); every other problem ends up in result.notes."""
    clock = clock or RealClock()
    limits = limits or ScanLimits()
    say = progress or (lambda _message: None)
    start = clock.monotonic()
    deadline = Deadline(clock, start, limits.time_limit_s, limits.max_operation_s)
    hosts = target.hosts()
    result = DeviceScan(
        network=str(target.network), own_address=target.own_address,
        interface=target.interface, gateway=gateway,
        addresses_total=len(hosts), ports=services.PORTS)
    own = set(target.own_addresses) | {target.own_address}
    stopped: list[str] = []

    say(f"Ping sweep of {target.network} ({len(hosts)} addresses, "
        f"{limits.sweep_workers} at a time) ...")
    responders = _sweep(platform, guard, hosts, limits, clock, start, deadline, result)
    if result.addresses_skipped:
        stopped.append(f"the ping sweep ({result.addresses_pinged} of {len(hosts)} "
                       "addresses were pinged)")

    mdns, ssdp = {}, {}
    wanted = limits.multicast_sends * limits.multicast_wait_s
    if deadline.can_start(wanted):
        say("Asking for names and types with mDNS and SSDP on the local link ...")
        mdns, ssdp = _discover(guard, io, target, limits, result)
    else:
        stopped.append("the mDNS and SSDP queries")

    if deadline.expired():
        stopped.append("the ARP table (not read)")
        neighbours = []
    else:
        say("Reading the ARP table ...")
        neighbours = _neighbours(platform, result)

    found = _collect_devices(guard, own, responders, neighbours, mdns, ssdp, result)
    result.devices = [found[ip] for ip in sorted(found, key=_ip_key)]
    for device in result.devices:
        device.is_gateway = device.ip == gateway

    say(f"Checking {len(services.PORTS)} ports on {len(result.devices)} devices "
        f"({limits.port_workers} devices at a time) ...")
    if not _check_ports(guard, io, result.devices, limits, clock, deadline):
        unchecked = sum(1 for d in result.devices if not d.ports_complete)
        stopped.append(f"the port checks ({unchecked} of {len(result.devices)} "
                       "devices were not fully checked)")

    for device in result.devices:
        identify(device)

    result.elapsed_s = clock.monotonic() - start
    if stopped:
        result.complete = False
        result.stopped = "; ".join(stopped)
    return result


# ---------------------------------------------------------------- steps

def _ip_key(ip: str) -> int:
    return int(ipaddress.ip_address(ip))


def _sweep(platform, guard, hosts, limits, clock, start, deadline, result) -> set[str]:
    sweep_deadline = Deadline(clock, start,
                              min(limits.sweep_budget_s, limits.time_limit_s),
                              limits.max_operation_s)
    pacer = Pacer(clock, limits.sweep_interval_s)
    errors: list[str] = []

    def one(host):
        """True or False for a reply; SKIPPED when the time limit was reached
        before the ping started; FAILED when the ping could not run."""
        ip = str(host)
        guard.check_host(ip)
        if sweep_deadline.expired() or deadline.expired():
            return SKIPPED
        pacer.wait()
        if sweep_deadline.expired() or deadline.expired():  # the wait may have been long
            return SKIPPED
        try:
            return bool(platform.ping_host(ip, limits.sweep_ping_timeout_ms))
        except Unavailable as exc:
            errors.append(exc.reason)
        except Exception as exc:  # never crash on one address
            errors.append(f"{type(exc).__name__}: {exc}")
        return FAILED

    with ThreadPoolExecutor(max_workers=max(1, limits.sweep_workers)) as pool:
        answers = list(pool.map(one, hosts))
    result.addresses_skipped = sum(1 for a in answers if a is SKIPPED)
    result.addresses_failed = sum(1 for a in answers if a is FAILED)
    result.addresses_pinged = sum(1 for a in answers if isinstance(a, bool))
    if errors and result.addresses_pinged == 0:
        result.notes.append("The ping sweep could not run: " + errors[0]
                            + " Devices were looked for in the ARP table and with "
                              "mDNS and SSDP only.")
    elif errors:
        result.notes.append(f"{result.addresses_failed} pings could not run (for example: "
                            f"{errors[0]}), so those addresses may have been missed by "
                            "the sweep.")
    return {str(h) for h, a in zip(hosts, answers) if a is True}


def _discover(guard, io, target, limits, result):
    """mDNS and SSDP in parallel: {ip: MdnsAnswer}, {ip: SsdpAnswer}."""
    out: dict[str, list] = {"mdns": [], "ssdp": []}
    problems: dict[str, str] = {}
    refused: list[ScanRefused] = []

    def ask(key: str, group, payload: bytes) -> None:
        try:
            out[key] = io.multicast_query(
                group[0], group[1], payload, local_ip=target.own_address,
                sends=limits.multicast_sends, wait=limits.multicast_wait_s,
                max_packets=thresholds.MULTICAST_MAX_PACKETS)
        except NetIOError as exc:
            problems[key] = str(exc)
        except ScanRefused as exc:      # a bug: re-raised below, in the main thread
            refused.append(exc)
        except Exception as exc:        # never crash on one query
            problems[key] = f"{type(exc).__name__}: {exc}"

    threads = [
        threading.Thread(target=ask, args=("mdns", MDNS_GROUP, discovery.build_mdns_query())),
        threading.Thread(target=ask, args=("ssdp", SSDP_GROUP, discovery.SSDP_SEARCH)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if refused:
        raise refused[0]
    for key, label in (("mdns", "mDNS"), ("ssdp", "SSDP")):
        if key in problems:
            result.notes.append(f"The {label} query could not be sent: {problems[key]}")

    ignored = 0
    mdns: dict[str, discovery.MdnsAnswer] = {}
    for sender, data in out["mdns"]:
        if not guard.in_target(sender):
            ignored += 1
            continue
        answer = discovery.parse_mdns(data)
        if answer is None:
            continue
        result.mdns_answers += 1
        known = mdns.setdefault(sender, discovery.MdnsAnswer())
        known.addresses |= answer.addresses
        known.host_names.update({a: n for a, n in answer.host_names.items()
                                 if a not in known.host_names})
        known.services |= answer.services
        known.instances |= answer.instances
        known.srv_targets |= answer.srv_targets
    ssdp: dict[str, discovery.SsdpAnswer] = {}
    for sender, data in out["ssdp"]:
        if not guard.in_target(sender):
            ignored += 1
            continue
        answer = discovery.parse_ssdp(data)
        if answer is None:
            continue
        result.ssdp_answers += 1
        known = ssdp.setdefault(sender, discovery.SsdpAnswer())
        known.server = known.server or answer.server
        for st in answer.search_targets:
            if st not in known.search_targets and len(known.search_targets) < 8:
                known.search_targets.append(st)
    if ignored:
        result.notes.append(f"{ignored} mDNS or SSDP answers came from addresses outside "
                            f"{result.network} and were ignored.")
    return mdns, ssdp


def _neighbours(platform, result):
    try:
        return list(platform.neighbours())
    except Unavailable as exc:
        result.notes.append(f"The ARP table could not be read: {exc.reason}")
    except Exception as exc:
        result.notes.append(f"The ARP table could not be read: {type(exc).__name__}: {exc}")
    return []


def _collect_devices(guard, own, responders, neighbours, mdns, ssdp, result):
    found: dict[str, Device] = {}

    def device(ip: str) -> Device | None:
        if ip in own or not guard.in_target(ip):
            return None
        return found.setdefault(ip, Device(ip))

    for ip in responders:
        dev = device(ip)
        if dev:
            dev.found_by.append("ping")
    for entry in neighbours:
        dev = device(entry.ip)
        if dev:
            dev.mac = entry.mac
            dev.found_by.append("arp")
    for ip, answer in mdns.items():
        dev = device(ip)
        if dev:
            dev.found_by.append("mdns")
            dev.name = discovery.mdns_device_name(answer, ip)
            dev.mdns_services = sorted(clean_text(s, 60) for s in answer.services)[:12]
    for ip, answer in ssdp.items():
        dev = device(ip)
        if dev:
            dev.found_by.append("ssdp")
            dev.upnp = True
            dev.ssdp_server = answer.server
    order = {"ping": 0, "arp": 1, "mdns": 2, "ssdp": 3}
    for dev in found.values():
        dev.found_by.sort(key=order.get)
    return found


def _check_ports(guard, io, devices, limits, clock, deadline) -> bool:
    """Check the ports of every device; False when the time limit cut it short."""
    pacer = Pacer(clock, limits.port_interval_s)

    def one_device(dev: Device) -> None:
        for spec in services.PORT_PLAN:
            if deadline.expired():
                dev.ports_complete = False
                return
            guard.check_host(dev.ip)
            pacer.wait()
            if deadline.expired():  # the wait may have been long
                dev.ports_complete = False
                return
            probe = _probe(io, dev.ip, spec, limits)
            if probe.open:
                dev.open_ports.append(spec.port)
                dev.services[spec.port] = services.service_from_probe(spec, probe)

    with ThreadPoolExecutor(max_workers=max(1, limits.port_workers)) as pool:
        list(pool.map(one_device, devices))
    return all(d.ports_complete for d in devices)


def _probe(io: NetIO, ip: str, spec: services.PortSpec, limits: ScanLimits) -> ProbeResult:
    try:
        if spec.method == services.BANNER:
            return io.banner(ip, spec.port, limits.connect_timeout_s, limits.banner_wait_s,
                             thresholds.BANNER_MAX_BYTES)
        if spec.method == services.HTTP:
            return io.http_head(ip, spec.port, limits.connect_timeout_s, limits.http_wait_s,
                                thresholds.HTTP_MAX_BYTES)
        if spec.method == services.TLS:
            return io.tls_handshake(ip, spec.port, limits.tls_timeout_s)
        return io.connect(ip, spec.port, limits.connect_timeout_s)
    except OSError:
        return ProbeResult(False)


# ---------------------------------------------------------------- identification

def identify(device: Device) -> None:
    """Fill in vendor, the private-MAC flag and the kind of a device."""
    kind, source = "", ""
    if device.mac:
        device.private_mac = oui.is_private_mac(device.mac)
        found = oui.lookup_vendor(device.mac) if not device.private_mac else None
        if found:
            device.vendor, vendor_kind = found
            kind, source = vendor_kind, "vendor"
    hints = [device.ssdp_server] + [s.http_server for s in device.services.values()]
    from_server = oui.kind_from_words(" ".join(h for h in hints if h))
    from_services = oui.kind_from_services(device.mdns_services)
    from_name = oui.kind_from_words(device.name)
    for candidate, label in ((from_server, "Server header"), (from_services, "mDNS service"),
                             (from_name, "name")):
        if candidate:
            kind, source = candidate, label
    if device.is_gateway:
        kind, source = "router", "default gateway"
    device.kind, device.kind_source = kind, source
