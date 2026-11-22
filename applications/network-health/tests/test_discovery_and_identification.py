"""Made-up mDNS and SSDP packets, banners, HTTP heads and vendor prefixes."""

import socket
import struct

import pytest
from conftest import mac_with_prefix, private_mac

from network_health import discovery, oui, oui_data, services
from network_health.devices import ServiceInfo
from network_health.netio import ProbeResult
from network_health.safe_text import clean_text

# ---------------------------------------------------------------- safe text


def test_clean_text_removes_control_characters_and_cuts_length():
    assert clean_text("Example\x1b[31mRED\x00\x07 name") == "Example [31mRED name"
    assert "\x1b" not in clean_text("\x1b]0;title\x07x")
    assert clean_text(b"abc\xff\xfedef") == "abc��def"
    assert clean_text("x" * 100, 20) == "x" * 17 + "..."
    assert clean_text("  many   spaces\t\nhere ") == "many spaces here"


# ---------------------------------------------------------------- mDNS


def name(text: str) -> bytes:
    out = b""
    for label in text.split("."):
        out += bytes([len(label)]) + label.encode()
    return out + b"\x00"


def record(owner: bytes, rtype: int, rdata: bytes) -> bytes:
    return owner + struct.pack("!HHIH", rtype, 0x8001, 120, len(rdata)) + rdata


def response(*records: bytes, flags: int = 0x8400, additional: int = 0) -> bytes:
    header = struct.pack("!HHHHHH", 0, flags, 0, len(records) - additional, 0, additional)
    return header + b"".join(records)


def test_mdns_query_is_one_standard_query_with_all_questions():
    packet = discovery.build_mdns_query()
    ident, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", packet[:12])
    assert (flags, qd, an, ns, ar) == (0, len(discovery.MDNS_QUESTIONS), 0, 0, 0)
    assert b"\x09_services\x07_dns-sd\x04_udp\x05local\x00" in packet
    assert len(packet) < 512


def test_mdns_answer_gives_name_services_and_ignores_other_devices_records():
    own = "192.0.2.40"
    other = "192.0.2.41"
    packet = response(
        record(name("_ipp._tcp.local"), discovery.TYPE_PTR, name("Example Printer._ipp._tcp.local")),
        record(name("Example Printer._ipp._tcp.local"), discovery.TYPE_SRV,
               struct.pack("!HHH", 0, 0, 631) + name("exampleprinter.local")),
        record(name("exampleprinter.local"), discovery.TYPE_A, socket.inet_aton(own)),
        record(name("someoneelse.local"), discovery.TYPE_A, socket.inet_aton(other)),
        additional=3)
    answer = discovery.parse_mdns(packet)
    assert answer.addresses == {own, other}
    assert "_ipp._tcp.local" in answer.services
    assert discovery.mdns_device_name(answer, own) == "exampleprinter"
    # Only the A record for the sender's own address names it; without one
    # the SRV host name is used.
    assert discovery.mdns_device_name(answer, other) == "someoneelse"
    assert discovery.mdns_device_name(answer, "192.0.2.99") == "exampleprinter"


def test_mdns_service_list_answer():
    packet = response(record(name("_services._dns-sd._udp.local"), discovery.TYPE_PTR,
                             name("_hap._tcp.local")))
    answer = discovery.parse_mdns(packet)
    assert answer.services == {"_hap._tcp.local"}


def test_mdns_name_pointer_compression_is_followed():
    # "host.local" at offset 12 of the packet; the A record's owner points to it.
    header = struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0)
    first = name("host.local")
    pointer = struct.pack("!H", 0xC000 | 12)
    packet = header + record(first, discovery.TYPE_A, socket.inet_aton("192.0.2.5"))
    packet += record(pointer, discovery.TYPE_A, socket.inet_aton("192.0.2.6"))
    packet = header[:6] + struct.pack("!HHH", 2, 0, 0) + packet[12:]
    answer = discovery.parse_mdns(packet)
    assert answer.host_names == {"192.0.2.5": "host.local", "192.0.2.6": "host.local"}


@pytest.mark.parametrize("data", [
    b"",
    b"\x00" * 5,
    response(flags=0x0000),                                         # a query, not an answer
    struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c",   # pointer to itself
    struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\x3fabc",    # label past the end
    struct.pack("!HHHHHH", 0, 0x8400, 0, 5, 0, 0) + name("a.local") + b"\x00\x01",
    struct.pack("!HHHHHH", 0, 0x8400, 9, 9, 9, 9) + b"\xff" * 40,
    bytes(range(256)),
])
def test_malformed_mdns_packets_never_crash(data):
    result = discovery.parse_mdns(data)
    assert result is None or isinstance(result, discovery.MdnsAnswer)


def test_mdns_names_are_cleaned():
    packet = response(record(name("evil\x1b[2Jhost.local"), discovery.TYPE_A,
                             socket.inet_aton("192.0.2.7")))
    answer = discovery.parse_mdns(packet)
    assert "\x1b" not in discovery.mdns_device_name(answer, "192.0.2.7")


# ---------------------------------------------------------------- SSDP


def test_ssdp_search_goes_to_the_group_with_a_short_wait():
    text = discovery.SSDP_SEARCH.decode("ascii")
    assert text.startswith("M-SEARCH * HTTP/1.1\r\n")
    assert "HOST: 239.255.255.250:1900" in text and "MX: 1" in text
    assert text.endswith("\r\n\r\n")


def test_ssdp_answer_is_read_and_location_is_not_kept():
    packet = (b"HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\n"
              b"LOCATION: http://192.0.2.50:49152/desc.xml\r\n"
              b"SERVER: Linux/4.9 UPnP/1.0 ExampleRouter/1.0\x1b[0m\r\n"
              b"ST: upnp:rootdevice\r\nUSN: uuid:made-up\r\n\r\n")
    answer = discovery.parse_ssdp(packet)
    assert answer.server == "Linux/4.9 UPnP/1.0 ExampleRouter/1.0 [0m"
    assert answer.search_targets == ["upnp:rootdevice"]
    assert not hasattr(answer, "location")


@pytest.mark.parametrize("data", [b"", b"NOTIFY * HTTP/1.1\r\n\r\n", b"garbage", b"\xff" * 10])
def test_ssdp_non_answers_are_ignored(data):
    assert discovery.parse_ssdp(data) is None


# ---------------------------------------------------------------- vendors


def test_bundled_vendor_list_has_only_prefixes_in_the_right_format():
    assert len(oui.PREFIXES) > 200
    for prefix in oui.PREFIXES:
        assert len(prefix) == 6 and prefix == prefix.upper()
        int(prefix, 16)
    for vendor, (kind, text) in oui_data.VENDORS.items():
        assert kind in oui.KIND_TEXT and kind in oui.KIND_SHORT
        assert all(len(p) == 6 for p in text.split()), vendor
    # No prefix is listed for two vendors.
    all_prefixes = [p for _, (_, text) in oui_data.VENDORS.items() for p in text.split()]
    assert len(all_prefixes) == len(set(all_prefixes))


def test_vendor_lookup_in_any_notation_and_kind():
    mac = mac_with_prefix("001132")                      # made-up suffix
    assert oui.lookup_vendor(mac) == ("Synology", "nas")
    assert oui.lookup_vendor(mac.upper().replace(":", "-")) == ("Synology", "nas")
    assert oui.lookup_vendor(mac.replace(":", "")) == ("Synology", "nas")
    assert oui.lookup_vendor("00:00:5e:00:53:01") is None    # documentation range
    assert oui.lookup_vendor("") is None and oui.lookup_vendor("zz") is None


def test_private_mac_has_no_vendor_and_is_flagged():
    assert oui.is_private_mac(private_mac())
    assert not oui.is_private_mac("00:00:5e:00:53:01")
    assert not oui.is_private_mac("")


@pytest.mark.parametrize("text,kind", [
    ("Example-NAS-1", "nas"), ("DiskStation2", "nas"), ("ExampleCam", "camera"),
    ("Living room printer", "printer"), ("fritzbox", "router"),
    ("Chromecast-1", "media"), ("Living room TV", None), ("banana", None), ("", None)])
def test_kind_from_words(text, kind):
    assert oui.kind_from_words(text) == kind


def test_kind_from_mdns_service():
    assert oui.kind_from_services(["_ipp._tcp.local"]) == "printer"
    assert oui.kind_from_services(["_hap._tcp.local", "_http._tcp.local"]) == "iot"
    assert oui.kind_from_services(["_http._tcp.local"]) is None


# ---------------------------------------------------------------- services


def test_port_plan_is_the_documented_list():
    assert services.PORTS == (21, 22, 23, 80, 443, 445, 554, 1900, 3389, 5000, 5900,
                              7547, 8080, 8443)
    assert len(set(services.PORTS)) == len(services.PORTS)
    assert all(spec.why for spec in services.PORT_PLAN)


def test_banner_is_the_first_clean_line_and_telnet_negotiation_is_removed():
    assert services.parse_banner(b"SSH-2.0-OpenSSH_9.0\r\nmore", 22) == "SSH-2.0-OpenSSH_9.0"
    assert services.parse_banner(b"\xff\xfd\x18\xff\xfd\x20ExampleCam login: ", 23) \
        == "ExampleCam login:"
    assert "\x1b" not in services.parse_banner(b"\x1b[2J\x00\x07", 21)
    assert services.parse_banner(b"", 21) == ""


def test_http_head_is_read_for_status_server_location_and_login():
    head = (b"HTTP/1.0 401 Unauthorized\r\nServer: ExampleHTTPd/1.2\r\n"
            b"WWW-Authenticate: Basic realm=\"x\"\r\n\r\nbody")
    info = services.parse_http(head)
    assert info == {"status": 401, "server": "ExampleHTTPd/1.2", "location": "", "auth": True}
    redirect = services.parse_http(b"HTTP/1.1 301 Moved\r\nLocation: https://example.invalid/\r\n\r\n")
    assert redirect["status"] == 301 and redirect["location"].startswith("https://")
    assert services.parse_http(b"SSH-2.0-x\r\n") is None
    assert services.parse_http(b"") is None


def test_service_from_probe_by_method():
    http_spec = services.SPEC_BY_PORT[80]
    info = services.service_from_probe(
        http_spec, ProbeResult(True, b"HTTP/1.1 200 OK\r\nServer: X\r\n\r\n"))
    assert info.is_http and info.http_status == 200 and not info.is_https
    tls = services.service_from_probe(services.SPEC_BY_PORT[443],
                                      ProbeResult(True, tls_version="TLSv1.2"))
    assert tls.is_https and not tls.is_http
    plain = services.service_from_probe(services.SPEC_BY_PORT[445], ProbeResult(True))
    assert plain == ServiceInfo(445, "smb")
    https_redirect = services.service_from_probe(
        http_spec, ProbeResult(True, b"HTTP/1.1 302 Found\r\nLocation: https://x/\r\n\r\n"))
    assert services.redirects_to_https(https_redirect)
    assert not services.redirects_to_https(info)
