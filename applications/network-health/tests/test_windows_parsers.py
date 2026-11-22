import pytest

from conftest import fixture_text
from network_health.models import Unavailable, UnrecognizedOutput
from network_health.platforms import windows_parsers as p


# ---------------------------------------------------------------- ping

def test_ping_counts_replies_and_less_than_one_ms():
    stats = p.parse_ping(fixture_text("ping_gateway.txt"), "192.0.2.1", 20)
    assert stats.sent == 20
    assert stats.received == 20
    assert stats.loss_pct == 0
    assert 0.5 in stats.times_ms  # "time<1ms"
    assert 1.5 < stats.avg_ms < 3


def test_ping_with_timeouts_gives_loss_and_jitter():
    stats = p.parse_ping(fixture_text("ping_gateway_bad.txt"), "192.0.2.1", 20)
    assert stats.received == 17
    assert stats.loss_pct == pytest.approx(15.0)
    assert stats.jitter_ms > 30


def test_ping_all_lost_is_a_result_not_an_error():
    stats = p.parse_ping(fixture_text("ping_all_lost.txt"), "192.0.2.1", 20)
    assert stats.received == 0
    assert stats.loss_pct == 100
    assert stats.avg_ms is None
    assert stats.jitter_ms is None


def test_ping_in_swedish_still_parses_because_it_reads_ttl_and_ms():
    stats = p.parse_ping(fixture_text("ping_swedish.txt"), "192.0.2.1", 4)
    assert stats.times_ms == [3.0, 0.5, 4.0]
    assert stats.loss_pct == 25


def test_ping_unknown_output_and_empty_output_are_unrecognized():
    with pytest.raises(UnrecognizedOutput):
        p.parse_ping("Something else entirely", "192.0.2.1", 4)
    with pytest.raises(UnrecognizedOutput):
        p.parse_ping("", "192.0.2.1", 4)


def test_ping_unknown_host_is_unavailable():
    with pytest.raises(Unavailable) as info:
        p.parse_ping(fixture_text("ping_unknown_host.txt"), "nosuchhost.example", 4)
    assert info.value.kind == "error"


def test_ping_dont_fragment_success_and_fragment_needed():
    assert p.ping_succeeded(fixture_text("ping_df_ok.txt"))
    assert not p.ping_succeeded(fixture_text("ping_df_fragment.txt"))


# ---------------------------------------------------------------- netsh wlan

def test_wlan_interfaces_connected():
    wifi = p.parse_wlan_interfaces(fixture_text("wlan_interfaces_connected.txt"))
    assert wifi.connected
    assert wifi.ssid == "ExampleHome"
    assert wifi.bssid == "00:00:5e:00:53:01"
    assert wifi.band == "5 GHz"
    assert wifi.channel == 36
    assert wifi.authentication == "WPA2-Personal"
    assert wifi.cipher == "CCMP"
    assert wifi.receive_mbps == 1201
    assert wifi.signal_pct == 88
    assert wifi.rssi_dbm == -52


def test_wlan_interfaces_without_band_line_uses_channel():
    wifi = p.parse_wlan_interfaces(fixture_text("wlan_interfaces_weak_open_24.txt"))
    assert wifi.band == "2.4 GHz"
    assert wifi.transmit_mbps == 19.5
    assert wifi.rssi_dbm is None
    assert wifi.bssid == "00:00:5e:00:53:41"


@pytest.mark.parametrize("name", ["wlan_interfaces_disconnected.txt",
                                  "wlan_no_interface.txt"])
def test_wlan_not_connected(name):
    assert not p.parse_wlan_interfaces(fixture_text(name)).connected


def test_wlan_location_permission_is_a_rights_message_with_a_tip():
    with pytest.raises(Unavailable) as info:
        p.parse_wlan_interfaces(fixture_text("wlan_location_permission.txt"))
    assert info.value.kind == "rights"
    assert "Location" in info.value.reason


def test_wlan_interfaces_in_swedish_is_unrecognized_with_clear_message():
    with pytest.raises(UnrecognizedOutput) as info:
        p.parse_wlan_interfaces(fixture_text("wlan_interfaces_swedish.txt"))
    assert "English" in info.value.reason


def test_wlan_networks():
    networks = p.parse_wlan_networks(fixture_text("wlan_networks.txt"))
    assert len(networks) == 5
    home = [n for n in networks if n.ssid == "ExampleHome"]
    assert {(n.band, n.channel) for n in home} == {("5 GHz", 36), ("2.4 GHz", 6)}
    hidden = [n for n in networks if n.ssid == ""]
    assert hidden and hidden[0].channel == 149
    assert all(n.bssid.startswith("00:00:5e:00:53:") for n in networks)


def test_wlan_networks_none_visible_and_location_permission():
    assert p.parse_wlan_networks(
        "\nInterface name : Wi-Fi\nThere are 0 networks currently visible.\n") == []
    with pytest.raises(Unavailable):
        p.parse_wlan_networks(fixture_text("wlan_location_permission.txt"))


def test_wlan_networks_without_channel_lines_is_unrecognized():
    text = ("SSID 1 : ExampleHome\n    Autentisering : WPA2-Personal\n"
            "    BSSID 1 : 00:00:5e:00:53:01\n         Kanal : 36\n")
    with pytest.raises(UnrecognizedOutput):
        p.parse_wlan_networks(text)


# ---------------------------------------------------------------- PowerShell JSON

def test_ip_configuration_list():
    adapters = p.parse_ip_configuration(fixture_text("ps_ipconfig.json"))
    assert [a.alias for a in adapters] == ["Wi-Fi", "vEthernet (Default Switch)"]
    wifi = adapters[0]
    assert wifi.ipv4[0].address == "192.0.2.10"
    assert wifi.ipv4[0].prefix_length == 24
    assert wifi.ipv4[0].origin == "Dhcp"
    assert wifi.ipv4[0].valid_lifetime_s == 84211
    assert wifi.ipv4_gateways == ["192.0.2.1"]
    assert wifi.ipv6_global == ["2001:db8:1::10"]
    assert "192.0.2.1" in wifi.dns_servers


def test_ip_configuration_single_object_and_nulls():
    adapters = p.parse_ip_configuration(fixture_text("ps_ipconfig_single.json"))
    assert len(adapters) == 1
    assert adapters[0].ipv4[0].origin == "Manual"
    assert adapters[0].ipv6_global == []
    assert adapters[0].ipv4_gateways == ["203.0.113.1"]


def test_ip_configuration_bad_json_is_unrecognized():
    with pytest.raises(UnrecognizedOutput):
        p.parse_ip_configuration("Get-NetIPConfiguration : something went wrong")
    with pytest.raises(UnrecognizedOutput):
        p.parse_ip_configuration('[{"Name": "x"}]')


def test_connection_profiles_string_and_number_categories():
    assert p.parse_connection_profiles(fixture_text("ps_profiles.json"))[0].category == "Private"
    assert p.parse_connection_profiles(fixture_text("ps_profiles_public.json"))[0].category == "Public"
    with pytest.raises(UnrecognizedOutput):
        p.parse_connection_profiles('[{"Name": "x", "NetworkCategory": "Offentlig"}]')


def test_firewall_profiles():
    on = p.parse_firewall_profiles(fixture_text("ps_firewall.json"))
    assert all(f.enabled for f in on) and len(on) == 3
    off = {f.name: f.enabled for f in p.parse_firewall_profiles(fixture_text("ps_firewall_off.json"))}
    assert off == {"Domain": True, "Private": False, "Public": False}
    with pytest.raises(UnrecognizedOutput):
        p.parse_firewall_profiles("[]")
    with pytest.raises(UnrecognizedOutput):
        p.parse_firewall_profiles('[{"Name": "Public", "Enabled": "Ja"}]')


def test_listening_ports():
    ports = p.parse_listening_ports(fixture_text("ps_listening.json"))
    assert (ports[0].address, ports[0].port, ports[0].process) == ("::", 135, "svchost")
    assert len(ports) == 6
    rdp = p.parse_listening_ports(fixture_text("ps_listening_rdp.json"))
    assert rdp[2].process is None


# ---------------------------------------------------------------- proxy

def test_reg_values_and_dword():
    values = p.parse_reg_values(fixture_text("reg_internet_settings_proxy.txt"))
    assert p.reg_dword(values, "ProxyEnable") == 1
    assert values["ProxyServer"][1] == "proxy.example.invalid:8080"
    assert values["User Agent"][0] == "REG_SZ"
    assert p.reg_dword(values, "Missing") is None
    with pytest.raises(UnrecognizedOutput):
        p.parse_reg_values("ERROR: something")


def test_winhttp_proxy():
    assert p.parse_winhttp_proxy(fixture_text("winhttp_direct.txt")) is None
    assert p.parse_winhttp_proxy(fixture_text("winhttp_proxy.txt")) == "proxy.example.invalid:3128"
    with pytest.raises(UnrecognizedOutput):
        p.parse_winhttp_proxy(fixture_text("winhttp_swedish.txt"))


# ---------------------------------------------------------------- arp

def test_arp_keeps_unicast_devices_only():
    neighbours = p.parse_arp(fixture_text("arp.txt"))
    pairs = [(n.interface_ip, n.ip, n.mac) for n in neighbours]
    assert ("192.0.2.10", "192.0.2.1", "00:00:5e:00:53:01") in pairs
    assert len([n for n in neighbours if n.interface_ip == "192.0.2.10"]) == 3
    assert not any(n.mac.startswith("01:") or n.mac == "ff:ff:ff:ff:ff:ff" for n in neighbours)


def test_arp_in_swedish_parses_because_it_reads_addresses_only():
    neighbours = p.parse_arp(fixture_text("arp_swedish.txt"))
    assert [(n.ip, n.mac) for n in neighbours] == [("192.0.2.1", "00:00:5e:00:53:01")]


def test_arp_unknown_output_and_empty_table():
    with pytest.raises(UnrecognizedOutput):
        p.parse_arp("garbage")
    assert p.parse_arp("No ARP Entries Found.") == []
