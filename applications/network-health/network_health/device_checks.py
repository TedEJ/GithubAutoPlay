"""Hazard rules for the devices found by --active.

Every rule gives one result in the area "Devices" with a status (good, info,
warn or bad), a plain reason (why) and a fix tip (fix), like the checks of
passive mode. A rule names all devices it applies to; each device also gets
the rule ids in Device.hazards, which the Devices table of the report shows.

Known file server (for the SMB rule): a device whose kind is "nas". The kind
comes from the vendor prefix (Synology, QNAP), from the name (nas, diskstation,
storage, fileserver ...), from the Server header or from an mDNS service
type. This computer is not scanned, so its own file sharing is not judged
here (passive mode reports its listening ports).
"""

from __future__ import annotations

from . import oui, services
from .checks import DEVICES, CheckResult, plural
from .devices import Device, DeviceScan
from .models import BAD, GOOD, INFO, WARN

HAZARD_LABELS = {
    "dev.telnet": "Telnet open",
    "dev.ftp": "FTP open",
    "dev.smb": "SMB open",
    "dev.remote": "remote desktop open",
    "dev.http_admin": "admin page on plain HTTP",
    "dev.upnp": "answers UPnP",
    "dev.tr069": "TR-069 open",
    "dev.unknown": "unknown device",
    "dev.new": "NEW",
}

ADMIN_KINDS = ("router", "camera", "nas", "printer")


def describe(device: Device) -> str:
    label = device.name or device.vendor or ""
    return f"{device.ip} ({label})" if label else device.ip


def describe_all(devices: list[Device]) -> str:
    return ", ".join(describe(d) for d in devices)


def is_known_file_server(device: Device) -> bool:
    return device.kind == "nas"


def device_key(mac: str | None, ip: str) -> str:
    """A device is told apart by its MAC address (the IP address can change);
    without a MAC address by its IP address."""
    return mac.lower() if mac else "ip:" + ip


def _mark(devices: list[Device], rule: str) -> None:
    for device in devices:
        if rule not in device.hazards:
            device.hazards.append(rule)


def _open(devices: list[Device], port: int) -> list[Device]:
    return [d for d in devices if port in d.open_ports]


def _result(rule: str, title: str, status: str, summary: str, devices: list[Device],
            why: str = "", fix: str = "") -> CheckResult:
    return CheckResult(rule, DEVICES, title, status, summary, why=why, fix=fix,
                       details={"devices": [d.ip for d in devices]})


def _good(rule: str, title: str, summary: str) -> CheckResult:
    return CheckResult(rule, DEVICES, title, GOOD, summary, details={"devices": []})


# ---------------------------------------------------------------- the rules

def _telnet(devices):
    title = "Telnet open"
    hit = _open(devices, services.TELNET)
    if not hit:
        return _good("dev.telnet", title, "No device has Telnet (port 23) open.")
    _mark(hit, "dev.telnet")
    return _result(
        "dev.telnet", title, BAD,
        f"{plural(len(hit), 'device')} with Telnet (port 23) open: {describe_all(hit)}.",
        hit,
        why="Telnet sends the login in plain text, and many cameras, routers and "
            "other gadgets ship with a default password. Malware such as Mirai "
            "scans networks for open Telnet and takes over those devices.",
        fix="Turn Telnet off in the device's settings (use SSH if you need remote "
            "login), change its password, and update its firmware. If Telnet "
            "cannot be turned off, replace the device or keep it off the network.")


def _ftp(devices):
    title = "FTP open"
    hit = _open(devices, services.FTP)
    if not hit:
        return _good("dev.ftp", title, "No device has FTP (port 21) open.")
    _mark(hit, "dev.ftp")
    return _result(
        "dev.ftp", title, WARN,
        f"{plural(len(hit), 'device')} with FTP (port 21) open: {describe_all(hit)}.",
        hit,
        why="FTP sends passwords and files without encryption. On a router, camera "
            "or NAS it often gives access to files or recordings, and many devices "
            "allow a guessed or default login.",
        fix="Turn FTP off in the device's settings, or switch to SFTP or FTPS. If you "
            "need it, use a strong password and no anonymous access.")


def _smb(devices):
    title = "File sharing (SMB) on a device that is not a file server"
    hit = [d for d in _open(devices, services.SMB) if not is_known_file_server(d)]
    if not hit:
        return _good("dev.smb", title, "No device that is not a known file server has "
                                       "SMB (port 445) open.")
    _mark(hit, "dev.smb")
    return _result(
        "dev.smb", title, WARN,
        f"{plural(len(hit), 'device')} not known as a file server with SMB (port 445) "
        f"open: {describe_all(hit)}.",
        hit,
        why="Windows file sharing on a device that is not meant to share files lets "
            "everyone on the network try its shares and passwords, and it is the way "
            "ransomware and worms spread between computers. A file server is "
            "recognised by its maker (for example Synology, QNAP) or a name such as "
            "nas or storage.",
        fix="If you do not share files from the device, turn file sharing off (on a "
            "Windows computer: Settings, Network & internet, Advanced sharing "
            "settings, or set the network to Public; on a router or printer: turn "
            "off the USB or network share). If it is a file server, nothing needs "
            "to change; name it with 'nas' or 'storage' to have it recognised.")


def _remote(devices):
    title = "Remote desktop or VNC open"
    rdp = _open(devices, services.RDP)
    vnc = _open(devices, services.VNC)
    hit = sorted({d.ip: d for d in rdp + vnc}.values(), key=lambda d: d.ip)
    if not hit:
        return _good("dev.remote", title, "No device has remote desktop (3389) or "
                                          "VNC (5900) open.")
    _mark(hit, "dev.remote")
    parts = []
    if rdp:
        parts.append("remote desktop (3389): " + describe_all(rdp))
    if vnc:
        parts.append("VNC (5900): " + describe_all(vnc))
    return _result(
        "dev.remote", title, WARN,
        f"{plural(len(hit), 'device')} with remote control open. " + "; ".join(parts) + ".",
        hit,
        why="Remote desktop and VNC give full control of a computer to anyone who "
            "learns the password, and both are a common target of password guessing "
            "and of known security holes.",
        fix="Turn remote desktop or VNC off if you do not use it (Windows: Settings, "
            "System, Remote Desktop). If you use it, require a strong password and "
            "network level authentication, keep the system updated, and never "
            "forward the port from the router to the internet.")


def _http_admin(devices):
    title = "Admin page on plain HTTP"
    warn, info = [], []
    for device in devices:
        plain = [s for p, s in device.services.items()
                 if p in services.HTTP_PORTS and s.is_http
                 and not services.redirects_to_https(s)]
        if not plain:
            continue
        admin_like = (device.is_gateway or device.kind in ADMIN_KINDS
                      or any(s.http_auth for s in plain))
        if not admin_like:
            continue
        https = any(p in services.HTTPS_PORTS and s.is_https
                    for p, s in device.services.items())
        (info if https else warn).append(device)
    if not warn and not info:
        return _good("dev.http_admin", title,
                     "No router, camera, NAS or printer offers its web page only on "
                     "plain HTTP.")
    _mark(warn + info, "dev.http_admin")
    parts = []
    if warn:
        parts.append(f"only plain HTTP, no HTTPS: {describe_all(warn)}")
    if info:
        parts.append(f"HTTP and HTTPS both offered: {describe_all(info)}")
    return _result(
        "dev.http_admin", title, WARN if warn else INFO,
        "Web interface of a router, camera, NAS, printer or a page that asks for a "
        "login is reachable over plain HTTP. " + "; ".join(parts) + ".",
        warn + info,
        why="Plain HTTP sends the admin login and everything on the page without "
            "encryption, so anyone on the same network (or Wi-Fi) can read the "
            "password.",
        fix="Open the device's page with https:// instead, and in its settings turn "
            "on 'HTTPS only' or 'redirect HTTP to HTTPS' if it has that option. If "
            "it has no HTTPS, update the firmware and do not log in from a shared "
            "or guest network.")


def _upnp(devices):
    title = "UPnP answering"
    hit = [d for d in devices if d.upnp]
    if not hit:
        return _good("dev.upnp", title, "No device answered the UPnP (SSDP) search.")
    _mark(hit, "dev.upnp")
    gateway = [d for d in hit if d.is_gateway]
    others = [d for d in hit if not d.is_gateway]
    if gateway:
        summary = ("The router answers UPnP: " + describe_all(gateway) + "."
                   + (f" {plural(len(others), 'other device')} answer as well: "
                      f"{describe_all(others)}." if others else ""))
        status = WARN
    else:
        summary = (f"{plural(len(hit), 'device')} answer the UPnP search: "
                   f"{describe_all(hit)}.")
        status = INFO
    return _result(
        "dev.upnp", title, status, summary, hit,
        why="UPnP lets a program on the network ask the router to open ports to the "
            "internet without a password, and malware uses that to make a computer "
            "reachable from outside. Other devices that answer (TVs, speakers, "
            "printers) announce themselves to everyone on the network, which is "
            "normal for them but shows what is there.",
        fix="Turn UPnP off in the router's settings unless a game or program needs "
            "it, and forward the ports you need by hand. For other devices, turn off "
            "UPnP, DLNA or media sharing that you do not use.")


def _tr069(devices):
    title = "TR-069 (port 7547) reachable"
    hit = _open(devices, services.TR069)
    if not hit:
        return _good("dev.tr069", title, "No device has TR-069 (port 7547) open.")
    _mark(hit, "dev.tr069")
    return _result(
        "dev.tr069", title, WARN,
        f"Port 7547 (TR-069, the provider's router management) answers on "
        f"{describe_all(hit)}.",
        hit,
        why="TR-069 lets the internet provider configure the router. It should only "
            "be reachable from the provider, but here every device on the local "
            "network can reach it. Security holes in this service have been used "
            "to take over hundreds of thousands of routers.",
        fix="Update the router's firmware, and turn off 'remote management' or "
            "TR-069 in its settings if it allows that. If it does not, ask the "
            "provider, and make sure the port is not forwarded or reachable from "
            "the internet.")


def _unknown(devices):
    title = "Unknown devices"
    hit = [d for d in devices if not d.name and not d.vendor and not d.is_gateway]
    if not hit:
        return _good("dev.unknown", title,
                     "Every device has a name or a known vendor.")
    _mark(hit, "dev.unknown")
    private = [d for d in hit if d.private_mac]
    return _result(
        "dev.unknown", title, INFO,
        f"{plural(len(hit), 'device')} with no name and no known vendor: "
        f"{describe_all(hit)}."
        + (f" {len(private)} of them use a private (randomised) MAC address, as "
           "phones and computers do." if private else ""),
        hit,
        why="A device that does not say what it is may be a guest's phone or a "
            "gadget of yours, or something that should not be on the network. The "
            "bundled vendor list is short, so a real device can also be missing "
            "from it.",
        fix="Match the MAC address against the router's client list or the Wi-Fi "
            "settings of your phones (a phone's own page shows its Wi-Fi address; "
            "with 'private address' on, it differs per network). If you do not "
            "recognise a device, remove it in the router and change the Wi-Fi "
            "password.")


def _new(devices, previous: dict | None, scan: DeviceScan):
    title = "New devices since the last scan"
    old = None
    if previous:
        old = {device_key(d.get("mac"), d.get("ip", "")) for d in previous.get("devices", [])
               if isinstance(d, dict)}
    if old is None:
        return CheckResult(
            "dev.new", DEVICES, title, INFO,
            "There is no saved scan of this network to compare with, so new "
            "devices cannot be told.",
            why="New devices are found by comparing with the devices of the last "
                "saved scan of the same network.",
            fix="Run with --active --save once, when you know every device on the "
                "network. Later scans then name the devices that are new.",
            details={"devices": []})
    new = [d for d in devices if device_key(d.mac, d.ip) not in old]
    new_ids = {id(d) for d in new}
    for device in devices:
        device.new = id(device) in new_ids
    if not new:
        return _good("dev.new", title, "No device is new compared with the last saved scan"
                                        + (f" of {previous.get('generated')}"
                                           if previous.get("generated") else "") + ".")
    _mark(new, "dev.new")
    return _result(
        "dev.new", title, WARN,
        f"{plural(len(new), 'device')} not in the last saved scan"
        + (f" ({previous.get('generated')})" if previous.get("generated") else "")
        + f": {describe_all(new)}.",
        new,
        why="A device that was not there before may be a new phone or gadget of "
            "yours, or someone who should not be on the network. Phones with a "
            "private MAC address look new when the address changes.",
        fix="If you know the device, run with --active --save to remember it. If you "
            "do not, find it in the router's client list by its MAC address, block "
            "or remove it, and change the Wi-Fi password.")


# ---------------------------------------------------------------- all

def check_devices(scan: DeviceScan, previous: dict | None = None) -> list[CheckResult]:
    """All results of the Devices area. previous is the newest saved snapshot
    of the same network that holds devices, or None."""
    devices = scan.devices
    results: list[CheckResult] = []
    count = plural(len(devices), "device")
    if not devices:
        results.append(CheckResult(
            "dev.summary", DEVICES, "Devices found", INFO,
            f"No other device was found on {scan.network}.",
            why="Either nothing else is connected, or the network isolates devices "
                "from each other (guest Wi-Fi, 'AP isolation'), or a firewall blocks "
                "the ping and the ARP answers.",
            fix="Connect to the main network instead of a guest network and run again.",
            details={"devices": []}))
    else:
        results.append(CheckResult(
            "dev.summary", DEVICES, "Devices found", GOOD,
            f"{count} found on {scan.network} (this computer, {scan.own_address}, "
            "is not counted).", details={"devices": [d.ip for d in devices]}))
    if not scan.complete:
        results.append(CheckResult(
            "dev.incomplete", DEVICES, "Scan was cut short", WARN,
            f"The scan stopped at the time limit: {scan.stopped}. The device list "
            "may be incomplete.",
            why="The scan never runs longer than its time limit, so a slow or very "
                "large network may not be fully checked.",
            fix="Run the scan again; if it keeps stopping, check that the network is "
                "not slow or overloaded.",
            details={"devices": []}))
    for number, note in enumerate(scan.notes, start=1):
        results.append(CheckResult(
            f"dev.note{number}", DEVICES, "Scan note", INFO, note, details={"devices": []}))
    results += [
        _telnet(devices), _ftp(devices), _smb(devices), _remote(devices),
        _http_admin(devices), _upnp(devices), _tr069(devices), _unknown(devices),
        _new(devices, previous, scan),
    ]
    for device in devices:
        device.hazards.sort(key=list(HAZARD_LABELS).index)
    return results


def kind_description(device: Device) -> str:
    text = oui.kind_text(device.kind)
    return f"probably {text}" if text else ""
