"""Messages of the two multicast discovery protocols: mDNS and SSDP.

Both are plain UDP datagrams sent to a multicast group on the local link. This
module only builds the query and reads the answers (pure functions, tested
with made-up packets); netio.py sends and receives. An answer can come from
any device, so every parser is bounded: it never reads outside the packet,
follows at most a few name pointers and keeps at most a few hundred records,
and every text is cleaned (safe_text).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import thresholds
from .safe_text import clean_text

# ---------------------------------------------------------------- mDNS (RFC 6762)

# Service types asked for. "_services._dns-sd._udp.local" lists the service
# types a device offers; the others make devices of that kind answer with
# their name (SRV and A records come in the same answer).
MDNS_QUESTIONS = (
    "_services._dns-sd._udp.local",
    "_workstation._tcp.local",
    "_http._tcp.local",
    "_ipp._tcp.local",
    "_printer._tcp.local",
    "_airplay._tcp.local",
    "_googlecast._tcp.local",
    "_hap._tcp.local",
    "_smb._tcp.local",
    "_ssh._tcp.local",
    "_device-info._tcp.local",
)

TYPE_A, TYPE_PTR, TYPE_TXT, TYPE_SRV, TYPE_AAAA = 1, 12, 16, 33, 28
MAX_RECORDS = 200
MAX_NAME_JUMPS = 16
MAX_NAME_BYTES = 255


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.strip(".").split("."):
        raw = label.encode("ascii")
        if not raw or len(raw) > 63:
            raise ValueError("bad label")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def build_mdns_query(questions=MDNS_QUESTIONS) -> bytes:
    """One standard query (type PTR, class IN) with several questions. The
    source port is not 5353, so devices answer this sender directly."""
    header = struct.pack("!HHHHHH", 0, 0, len(questions), 0, 0, 0)
    body = b"".join(_encode_name(q) + struct.pack("!HH", TYPE_PTR, 1) for q in questions)
    return header + body


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    """The name at offset and the offset after it in the record (compression
    pointers followed; ValueError on anything malformed)."""
    labels: list[str] = []
    jumps = 0
    end = None
    total = 0
    while True:
        if offset >= len(data):
            raise ValueError("name outside the packet")
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError("pointer outside the packet")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if end is None:
                end = offset + 2
            jumps += 1
            if jumps > MAX_NAME_JUMPS or pointer >= len(data):
                raise ValueError("bad name pointer")
            offset = pointer
            continue
        if length & 0xC0:
            raise ValueError("bad label type")
        offset += 1
        if offset + length > len(data):
            raise ValueError("label outside the packet")
        total += length + 1
        if total > MAX_NAME_BYTES:
            raise ValueError("name too long")
        labels.append(data[offset:offset + length].decode("utf-8", errors="replace"))
        offset += length
    return ".".join(labels), (end if end is not None else offset)


@dataclass
class MdnsAnswer:
    """What one device told us in one mDNS packet."""

    addresses: set[str] = field(default_factory=set)   # A records
    host_names: dict[str, str] = field(default_factory=dict)  # address -> host name
    services: set[str] = field(default_factory=set)    # service types (PTR targets of the
                                                       # service list, PTR owners)
    instances: set[str] = field(default_factory=set)   # instance names
    srv_targets: set[str] = field(default_factory=set)


def parse_mdns(data: bytes) -> MdnsAnswer | None:
    """Read an mDNS answer; None when it is not an answer or is malformed."""
    try:
        return _parse_mdns(data)
    except (ValueError, struct.error, IndexError):
        return None


def _parse_mdns(data: bytes) -> MdnsAnswer | None:
    if len(data) < 12:
        return None
    _ident, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    if not flags & 0x8000:      # not a response
        return None
    offset = 12
    for _ in range(min(qd, MAX_RECORDS)):
        _name, offset = _read_name(data, offset)
        offset += 4
    answer = MdnsAnswer()
    for _ in range(min(an + ns + ar, MAX_RECORDS)):
        if offset >= len(data):
            break
        name, offset = _read_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError("record outside the packet")
        rtype, _rclass, _ttl, rdlength = struct.unpack("!HHIH", data[offset:offset + 10])
        offset += 10
        rdata_start, offset = offset, offset + rdlength
        if offset > len(data):
            raise ValueError("record data outside the packet")
        if rtype == TYPE_A and rdlength == 4:
            address = ".".join(str(b) for b in data[rdata_start:offset])
            answer.addresses.add(address)
            answer.host_names.setdefault(address, name)
        elif rtype == TYPE_PTR:
            target, _ = _read_name(data, rdata_start)
            lower = name.lower()
            if lower == "_services._dns-sd._udp.local":
                answer.services.add(target.lower())
            elif lower.startswith("_") or "._" in lower:
                answer.services.add(_service_type(name))
                answer.instances.add(_instance_label(target))
        elif rtype == TYPE_SRV and rdlength >= 7:
            target, _ = _read_name(data, rdata_start + 6)
            answer.srv_targets.add(target)
            answer.services.add(_service_type(name))
            answer.instances.add(_instance_label(name))
    return answer


def _service_type(name: str) -> str:
    """"Example._ipp._tcp.local" -> "_ipp._tcp.local"; a bare type stays."""
    labels = name.split(".")
    for i, label in enumerate(labels):
        if label.startswith("_"):
            return ".".join(labels[i:]).lower()
    return name.lower()


def _instance_label(name: str) -> str:
    """The instance part of "Example Printer._ipp._tcp.local"."""
    labels = name.split(".")
    if labels and not labels[0].startswith("_"):
        return labels[0]
    return ""


def mdns_device_name(answer: MdnsAnswer, source_ip: str) -> str:
    """The best name for the device that sent the answer: the host name of an
    A record for its own address, then an SRV host name, then an instance
    name. Only records about the sender itself count, so one device cannot
    name another."""
    candidates: list[str] = []
    own = answer.host_names.get(source_ip)
    if own:
        candidates.append(own)
    candidates += sorted(answer.srv_targets)
    candidates += sorted(i for i in answer.instances if i)
    for candidate in candidates:
        label = candidate[:-len(".local")] if candidate.lower().endswith(".local") else candidate
        label = clean_text(label, thresholds.MAX_NAME_CHARS)
        if label:
            return label
    return ""


# ---------------------------------------------------------------- SSDP (UPnP)

SSDP_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 1\r\n"
    "ST: ssdp:all\r\n"
    "USER-AGENT: network-health\r\n"
    "\r\n"
).encode("ascii")


@dataclass
class SsdpAnswer:
    server: str = ""
    search_targets: list[str] = field(default_factory=list)


def parse_ssdp(data: bytes) -> SsdpAnswer | None:
    """Read an answer to the M-SEARCH (a "HTTP/1.1 200 OK" with headers).
    The LOCATION address is not followed. None when it is not an answer."""
    text = data[:4096].decode("utf-8", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].upper().startswith("HTTP/1."):
        return None
    answer = SsdpAnswer()
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        if key == "server" and not answer.server:
            answer.server = clean_text(value, thresholds.MAX_BANNER_CHARS)
        elif key == "st":
            st = clean_text(value, 80)
            if st and st not in answer.search_targets and len(answer.search_targets) < 8:
                answer.search_targets.append(st)
    return answer
