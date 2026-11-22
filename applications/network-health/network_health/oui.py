"""Look up the vendor of a MAC address and guess what the device is.

The guess is deliberately weak and always shown as "probably": a vendor
prefix says who made the network chip. Hints in the name and in the answers
of the device itself are stronger and are tried first.
"""

from __future__ import annotations

import re

from .oui_data import VENDORS

# kind key -> text after "probably ".
KIND_TEXT = {
    "router": "a router, access point or network device",
    "printer": "a printer",
    "camera": "a camera",
    "nas": "a network storage device (NAS)",
    "console": "a game console",
    "media": "a media player, smart speaker or phone",
    "iot": "a smart-home or IoT device",
    "lighting": "a smart lighting bridge",
    "board": "a small computer (Raspberry Pi)",
    "computer": "a computer",
    "mobile": "a phone, tablet, computer or TV box",
    "consumer": "a phone, TV or home appliance",
    "vm": "a virtual machine",
}

# The same kinds, short, for the table of the report.
KIND_SHORT = {
    "router": "router or network device", "printer": "printer", "camera": "camera",
    "nas": "NAS", "console": "game console", "media": "media player or speaker",
    "iot": "smart-home device", "lighting": "lighting bridge",
    "board": "Raspberry Pi", "computer": "computer", "mobile": "phone or computer",
    "consumer": "phone, TV or appliance", "vm": "virtual machine",
}

_PREFIX_RE = re.compile(r"^[0-9A-F]{6}$")


def _build() -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    for vendor, (kind, text) in VENDORS.items():
        if kind not in KIND_TEXT:
            raise ValueError(f"unknown kind {kind!r} for {vendor}")
        for prefix in text.split():
            if not _PREFIX_RE.match(prefix):
                raise ValueError(f"bad prefix {prefix!r} for {vendor}")
            table.setdefault(prefix, (vendor, kind))  # the first vendor wins
    return table


PREFIXES = _build()


def prefix_of(mac: str) -> str | None:
    """The 6-digit upper-case prefix of a MAC in any common notation."""
    digits = re.sub(r"[^0-9A-Fa-f]", "", mac or "").upper()
    return digits[:6] if len(digits) >= 6 else None


def is_private_mac(mac: str) -> bool:
    """True for a locally administered MAC address (second-lowest bit of the
    first byte set). Phones and PCs use these as a private Wi-Fi address, so
    they have no vendor and change over time."""
    prefix = prefix_of(mac)
    return bool(prefix and int(prefix[:2], 16) & 0x02)


def lookup_vendor(mac: str) -> tuple[str, str] | None:
    """(vendor, kind) for a MAC address, or None."""
    prefix = prefix_of(mac)
    return PREFIXES.get(prefix) if prefix else None


# Words in a device name, a service type or a Server header that say what the
# device is. Whole words (split at anything that is not a letter or digit),
# or, for the long ones, a word that starts with it (diskstation1).
_NAME_WORDS = {
    "nas": "nas", "diskstation": "nas", "synology": "nas", "qnap": "nas",
    "readynas": "nas", "mycloud": "nas", "truenas": "nas", "freenas": "nas",
    "fileserver": "nas", "storage": "nas", "unraid": "nas",
    "printer": "printer", "laserjet": "printer", "officejet": "printer",
    "deskjet": "printer", "pixma": "printer",
    "camera": "camera", "cam": "camera", "ipcam": "camera", "doorbell": "camera",
    "nvr": "camera", "dvr": "camera", "hikvision": "camera", "dahua": "camera",
    "router": "router", "gateway": "router", "fritz": "router",
    "fritzbox": "router", "routeros": "router", "mikrotik": "router",
    "accesspoint": "router",
    "chromecast": "media", "sonos": "media", "roku": "media",
    "appletv": "media", "firetv": "media",
    "playstation": "console", "xbox": "console", "nintendo": "console",
}

# mDNS service types that say what a device is.
_SERVICE_KINDS = {
    "_ipp._tcp": "printer", "_printer._tcp": "printer",
    "_pdl-datastream._tcp": "printer", "_ipps._tcp": "printer",
    "_scanner._tcp": "printer",
    "_airplay._tcp": "media", "_googlecast._tcp": "media", "_raop._tcp": "media",
    "_spotify-connect._tcp": "media",
    "_hap._tcp": "iot", "_homekit._tcp": "iot",
    "_rtsp._tcp": "camera",
}


def kind_from_words(text: str) -> str | None:
    text = text or ""
    # ExampleCam is read as "Example Cam" and as "examplecam", so that
    # camel-case names and long words such as DiskStation2 both match.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    for variant in (spaced, text):
        for word in re.split(r"[^a-z0-9]+", variant.lower()):
            if word in _NAME_WORDS:
                return _NAME_WORDS[word]
            for start, kind in _NAME_WORDS.items():
                if len(start) >= 6 and word.startswith(start):
                    return kind
    return None


def kind_from_services(services) -> str | None:
    for service in services:
        base = service.lower().rstrip(".")
        if base.endswith(".local"):
            base = base[: -len(".local")]
        if base in _SERVICE_KINDS:
            return _SERVICE_KINDS[base]
    return None


def kind_text(kind: str) -> str:
    return KIND_TEXT.get(kind, "")
