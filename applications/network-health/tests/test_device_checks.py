"""The hazard rules of the device scan, with made-up devices."""

import json
from datetime import datetime

import pytest
from conftest import doc_mac, mac_with_prefix, make_device, private_ip, private_mac

from network_health import scanner
from network_health.checks import DEVICES, AREAS
from network_health.device_checks import check_devices, describe, is_known_file_server
from network_health.devices import DeviceScan, ServiceInfo
from network_health.models import BAD, GOOD, INFO, WARN
from network_health.report import (
    area_verdict,
    build_json,
    build_text,
    overall_verdict,
    ranked_findings,
)

NOW = datetime(2026, 11, 22, 12, 30, 0)


def http(port=80, status=200, server="ExampleHTTPd/1.0", location="", auth=False):
    return ServiceInfo(port, "http", http_status=status, http_server=server,
                       http_location=location, http_auth=auth)


def https(port=443):
    return ServiceInfo(port, "https", tls_version="TLSv1.2")


def device(offset, ports=(), services=None, **fields):
    d = make_device(offset, **fields)
    d.open_ports = sorted(set(ports) | set((services or {}).keys()))
    d.services = dict(services or {})
    scanner.identify(d)
    return d


def scan_of(*devices, complete=True, stopped="", notes=()):
    return DeviceScan(network=f"{private_ip(0)}/24", own_address=private_ip(10),
                      interface="Wi-Fi", devices=list(devices), complete=complete,
                      stopped=stopped, notes=list(notes), elapsed_s=42.0,
                      ports=(21, 22, 23), addresses_total=253, addresses_pinged=253)


def by_id(results):
    return {r.id: r for r in results}


def rule(devices, rule_id, previous=None, **scan_fields):
    return by_id(check_devices(scan_of(*devices, **scan_fields), previous))[rule_id]


def test_without_any_problem_every_rule_is_good():
    quiet = device(20, ports=[80], services={80: http()}, mac=doc_mac(1), name="tv-livingroom")
    results = check_devices(scan_of(quiet), previous=None)
    got = by_id(results)
    assert got["dev.summary"].status == GOOD
    for rule_id in ("dev.telnet", "dev.ftp", "dev.smb", "dev.remote", "dev.http_admin",
                    "dev.upnp", "dev.tr069", "dev.unknown"):
        assert got[rule_id].status == GOOD, rule_id
    assert got["dev.new"].status == INFO          # nothing saved to compare with
    assert quiet.hazards == []
    assert all(r.area == DEVICES for r in results)


def test_telnet_is_bad_with_why_and_fix():
    cam = device(40, ports=[23, 80], services={23: ServiceInfo(23, "telnet"), 80: http()},
                 name="ExampleCam")
    r = rule([cam], "dev.telnet")
    assert r.status == BAD and f"{private_ip(40)} (ExampleCam)" in r.summary
    assert "plain text" in r.why and "Turn Telnet off" in r.fix
    assert r.details["devices"] == [private_ip(40)] and "dev.telnet" in cam.hazards


def test_ftp_is_warn_with_fix():
    r = rule([device(41, ports=[21])], "dev.ftp")
    assert r.status == WARN and "SFTP" in r.fix and "without encryption" in r.why


def test_smb_on_a_device_that_is_not_a_known_file_server_is_warn():
    printer = device(42, ports=[445], mac=mac_with_prefix("000085"))     # Canon
    unnamed = device(43, ports=[445])
    r = rule([printer, unnamed], "dev.smb")
    assert r.status == WARN
    assert private_ip(42) in r.summary and private_ip(43) in r.summary
    assert "turn file sharing off" in r.fix.lower() and "nas" in r.fix.lower()


@pytest.mark.parametrize("fields", [
    {"mac": mac_with_prefix("001132")},                   # vendor: Synology
    {"mac": mac_with_prefix("245EBE")},                   # vendor: QNAP
    {"name": "Example-NAS"},                              # name hint
    {"name": "storage1"},
    {"mdns_services": [], "ssdp_server": "Linux UPnP/1.0 Synology/7.0"},  # Server header
])
def test_smb_on_a_known_file_server_is_not_a_finding(fields):
    nas = device(44, ports=[445], **fields)
    assert is_known_file_server(nas), fields
    r = rule([nas], "dev.smb")
    assert r.status == GOOD and "dev.smb" not in nas.hazards


def test_remote_desktop_and_vnc_are_warn():
    rdp = device(45, ports=[3389])
    vnc = device(46, ports=[5900], services={5900: ServiceInfo(5900, "vnc", banner="RFB 003.008")})
    both = device(47, ports=[3389, 5900])
    r = rule([rdp, vnc, both], "dev.remote")
    assert r.status == WARN and r.details["devices"] == [private_ip(n) for n in (45, 46, 47)]
    assert "remote desktop (3389)" in r.summary and "VNC (5900)" in r.summary
    assert "network level authentication" in r.fix and "never forward" in r.fix


def test_admin_page_on_plain_http_without_https_is_warn():
    router = device(1, services={80: http()}, is_gateway=True)
    scanner.identify(router)
    camera = device(48, services={8080: http(8080)}, mac=mac_with_prefix("1868CB"))  # Hikvision
    login = device(49, services={80: http(status=401, auth=True)})
    r = rule([router, camera, login], "dev.http_admin")
    assert r.status == WARN
    assert all(private_ip(n) in r.summary for n in (1, 48, 49))
    assert "https://" in r.fix and "password" in r.why


def test_admin_page_with_https_as_well_is_only_info_and_redirects_are_fine():
    both = device(1, services={80: http(), 443: https()}, is_gateway=True)
    scanner.identify(both)
    assert rule([both], "dev.http_admin").status == INFO
    redirect = device(1, services={80: http(status=301, location="https://x/")},
                      is_gateway=True)
    scanner.identify(redirect)
    assert rule([redirect], "dev.http_admin").status == GOOD
    tv = device(50, services={80: http()}, mac=mac_with_prefix("001C62"))   # LG
    assert rule([tv], "dev.http_admin").status == GOOD       # not an admin-type device


def test_upnp_on_the_router_is_warn_and_on_other_devices_info():
    router = device(1, ports=[], upnp=True, is_gateway=True)
    scanner.identify(router)
    tv = device(51, upnp=True, name="tv")
    r = rule([router, tv], "dev.upnp")
    assert r.status == WARN and "router answers UPnP" in r.summary
    assert "Turn UPnP off in the router" in r.fix
    r = rule([tv], "dev.upnp")
    assert r.status == INFO and "answer the UPnP search" in r.summary
    assert "dev.upnp" in tv.hazards


def test_tr069_on_the_local_network_is_warn():
    router = device(1, ports=[7547], is_gateway=True)
    r = rule([router], "dev.tr069")
    assert r.status == WARN and "7547" in r.summary
    assert "firmware" in r.fix and "provider" in r.fix


def test_unknown_device_without_name_or_vendor_is_info_and_gateway_is_excluded():
    mystery = device(52, mac=doc_mac(0x52))
    phone = device(53, mac=private_mac())
    named = device(54, mac=doc_mac(0x54), name="Example-TV")
    vendor = device(55, mac=mac_with_prefix("14CC20"))
    gateway = device(1, mac=doc_mac(1), is_gateway=True)
    r = rule([mystery, phone, named, vendor, gateway], "dev.unknown")
    assert r.status == INFO
    assert r.details["devices"] == [private_ip(52), private_ip(53)]
    assert "private (randomised) MAC" in r.summary
    assert "router's client list" in r.fix


def snapshot_with(*macs, network=None, generated="2026-11-21T10:00:00"):
    return {"generated": generated,
            "scan": {"network": network or f"{private_ip(0)}/24"},
            "devices": [{"ip": private_ip(100 + i), "mac": mac} for i, mac in enumerate(macs)]}


def test_new_devices_compared_with_the_last_snapshot():
    known = device(60, mac=doc_mac(0x60), name="a")
    fresh = device(61, mac=doc_mac(0x61), name="b")
    previous = snapshot_with(doc_mac(0x60), doc_mac(0x99))     # 0x99 left the network
    r = rule([known, fresh], "dev.new", previous)
    assert r.status == WARN and r.details["devices"] == [private_ip(61)]
    assert "2026-11-21T10:00:00" in r.summary and "--save" in r.fix
    assert known.new is False and fresh.new is True
    assert fresh.hazards == ["dev.new"]


def test_new_device_check_uses_the_mac_not_the_ip_address():
    moved = device(70, mac=doc_mac(0x60), name="a")       # same MAC, another IP address
    previous = snapshot_with(doc_mac(0x60))
    assert rule([moved], "dev.new", previous).status == GOOD


def test_new_device_check_without_snapshot_says_so():
    r = rule([device(60, mac=doc_mac(0x60), name="a")], "dev.new", None)
    assert r.status == INFO and "no saved scan" in r.summary.lower()
    assert "--active --save" in r.fix


def test_a_cut_short_scan_is_a_warning():
    r = rule([], "dev.incomplete", complete=False, stopped="the port checks (3 of 9 devices)")
    assert r.status == WARN and "time limit" in r.summary and "3 of 9" in r.summary
    assert r.fix


def test_no_devices_found_is_info_with_a_tip():
    r = rule([], "dev.summary")
    assert r.status == INFO and "guest" in r.why and r.fix


def test_scan_notes_become_info_results():
    results = by_id(check_devices(scan_of(notes=["The ARP table could not be read: x"])))
    assert results["dev.note1"].status == INFO


def test_every_rule_that_fires_has_a_why_and_a_fix_tip():
    worst = [
        device(1, ports=[7547, 80], services={80: http()}, is_gateway=True, upnp=True),
        device(40, ports=[23, 21, 445, 3389], mac=doc_mac(0x40)),
        device(41, ports=[5900], mac=doc_mac(0x41), name="x"),
    ]
    results = check_devices(scan_of(*worst), snapshot_with(doc_mac(0x99)))
    firing = {r.id: r for r in results if r.status in (BAD, WARN, INFO)}
    for rule_id in ("dev.telnet", "dev.ftp", "dev.smb", "dev.remote", "dev.http_admin",
                    "dev.upnp", "dev.tr069", "dev.unknown", "dev.new"):
        assert rule_id in firing, rule_id
        assert firing[rule_id].why and firing[rule_id].fix, rule_id
    assert len(describe(worst[1])) > 0


# ---------------------------------------------------------------- the report

def test_text_report_has_a_devices_section_with_findings_and_fix_tips():
    cam = device(40, ports=[23, 80], services={23: ServiceInfo(23, "telnet", banner="login:"),
                                              80: http()},
                 mac=mac_with_prefix("1868CB"), name="ExampleCam")
    nas = device(41, ports=[445], mac=mac_with_prefix("001132"))
    results = check_devices(scan_of(cam, nas), None)
    text = build_text(results, contacted=["x"], generated=NOW, platform="Windows",
                      scan=scan_of(cam, nas))
    assert text.splitlines()[0] == ("Network health - active mode (device scan) - Windows - "
                                    "2026-11-22 12:30")
    assert any(line.strip().startswith("Devices") and "BAD" in line
               for line in text.splitlines())
    assert f"[BAD] Devices - Telnet open:" in text
    assert "Fix: Turn Telnet off" in text
    section = text.split("Devices on ")[1].split("\n\n")[0]
    header, rule_line, *rows = section.splitlines()[1:]
    for column in ("IP", "MAC", "Name", "Vendor", "Open ports", "Hazards"):
        assert column in header
    cam_row = next(r for r in rows if private_ip(40) in r)
    assert "ExampleCam" in cam_row and "Hikvision" in cam_row and "probably camera" in cam_row
    assert "23 telnet, 80 http" in cam_row
    assert "Telnet open" in cam_row and "admin page on plain HTTP" in cam_row
    nas_row = next(r for r in rows if private_ip(41) in r)
    assert "Synology" in nas_row and "445" in nas_row and "SMB open" not in nas_row
    assert "IPv4" in section                                    # the note about IPv6


def test_devices_area_is_only_in_the_report_when_the_scan_ran():
    passive = build_text([], contacted=[], generated=NOW, platform="Windows")
    assert "Devices" not in passive
    cam = device(40, ports=[23])
    results = check_devices(scan_of(cam), None)
    assert area_verdict(results, DEVICES) == BAD
    assert overall_verdict(results) == BAD
    ranked = ranked_findings(results)
    assert ranked[0].id == "dev.telnet"
    data = build_json(results, contacted=[], generated=NOW, platform="Windows")
    assert set(data["areas"]) == set(AREAS) | {DEVICES}
    assert data["mode"] == "passive"          # no scan object given


def test_json_report_holds_the_devices_and_the_scan():
    cam = device(40, ports=[23, 80], services={23: ServiceInfo(23, "telnet"), 80: http()},
                 mac=mac_with_prefix("1868CB"), name="ExampleCam")
    scan = scan_of(cam)
    results = check_devices(scan, None)
    data = build_json(results, contacted=[], generated=NOW, platform="Windows", scan=scan)
    parsed = json.loads(json.dumps(data))
    assert parsed["mode"] == "active"
    assert parsed["scan"]["network"] == scan.network and parsed["scan"]["complete"] is True
    [entry] = parsed["devices"]
    assert entry["ip"] == private_ip(40) and entry["vendor"] == "Hikvision"
    assert entry["open_ports"] == [23, 80] and "dev.telnet" in entry["hazards"]
    assert entry["services"]["23"]["name"] == "telnet"
    assert "dev.telnet" in parsed["findings"]
