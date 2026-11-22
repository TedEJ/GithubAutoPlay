"""The generator of oui_data.py (tools/build_oui_data.py), on made-up registry
samples in both formats. The real registry is never read by a test."""

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import build_oui_data as gen  # noqa: E402

from network_health import oui, oui_data  # noqa: E402

# Wireshark manuf: prefix, short name, full name, separated by tabs. The 28-bit
# and 36-bit blocks are shared prefixes and must be ignored.
MANUF = "\n".join([
    "# comment line",
    "AA:00:01\tAppleX\tApple, Inc.",
    "AA:00:02\tApple\tApple Inc",
    "AA:00:03\tAppliedMi\tApplied Micro Circuits Corporation",
    "AA:00:04\tPineappl\tPineapple Computing Ltd",
    "AA:00:05\tSonos\tSonos, Inc.",
    "AA:00:06\tSonoSite\tSonoSite, Inc.",
    "AA:00:07\tIntel\tIntel Corporate",
    "AA:00:08\tIntelliG\tIntelligent Systems",
    "AA:00:09\tTP-Link\tTP-LINK TECHNOLOGIES CO.,LTD.",
    "AA:00:0A\tShort",
    "AA:00:0B" ":00:00:00/36\tGuest\tApple, Inc. shared block",
    "AA:00:0C" ":80:00:00/28\tGuest\tTP-Link shared block",
    "AA:00:0D\tCanon\tCanon Inc.",
    "AA:00:0E\tMicrosoft\tMicrosoft Corporation",
    "AA:00:0F\tMicrosoft\tMicrosoft Corporation",
    "",
])

# IEEE oui.txt: "(hex)" lines give the 24-bit prefixes; the "(base 16)" lines
# repeat them; shared prefixes are assigned to the IEEE Registration Authority.
IEEE = "\n".join([
    "OUI/MA-L\t\t\tOrganization",
    "company_id\t\t\tOrganization",
    "",
    "AA-00-01   (hex)\t\tApple, Inc.",
    "AA0001     (base 16)\t\tApple, Inc.",
    "\t\t\t\tOne Apple Park Way",
    "",
    "AA-00-03   (hex)\t\tApplied Micro Circuits Corporation",
    "AA0003     (base 16)\t\tApplied Micro Circuits Corporation",
    "",
    "AA-00-0B   (hex)\t\tIEEE Registration Authority",
    "AA000B     (base 16)\t\tIEEE Registration Authority",
    "",
    "AA-00-09   (hex)\t\tTP-LINK TECHNOLOGIES CO.,LTD.",
    "AA0009     (base 16)\t\tTP-LINK TECHNOLOGIES CO.,LTD.",
    "",
])

MAPPING = {
    "Apple": ("mobile", [r"^apple[, ]\s*(inc|computer)"]),
    "Sonos": ("media", [r"^sonos\b"]),
    "Intel": ("netcard", [r"^intel (corporate|corporation|corp)\b"]),
    "TP-Link": ("router", [r"^tp-?link"]),
    "Canon": ("printer", [r"^canon\b"]),
    "Microsoft": ("computer", [r"^microsoft"]),
}


def test_manuf_format_reads_only_24_bit_prefixes():
    entries = gen.parse_registry(MANUF)
    assert entries["AA0001"] == "Apple, Inc."
    assert entries["AA000A"] == "Short"                   # no full name: the short name
    assert "AA000B" not in entries and "AA000C" not in entries     # 36- and 28-bit blocks
    assert len(entries) == 13


def test_ieee_format_reads_hex_lines_and_skips_shared_prefixes():
    entries = gen.parse_registry(IEEE)
    assert entries == {"AA0001": "Apple, Inc.", "AA0003": "Applied Micro Circuits Corporation",
                       "AA0009": "TP-LINK TECHNOLOGIES CO.,LTD."}


def test_patterns_are_specific_enough():
    vendors = gen.build_vendors(gen.parse_registry(MANUF), MAPPING, extra={}, extra_first=())
    got = {name: prefixes for name, (_, prefixes) in vendors.items()}
    assert got["Apple"] == ["AA0001", "AA0002"]           # not Applied, not Pineapple
    assert got["Sonos"] == ["AA0005"]                     # not SonoSite
    assert got["Intel"] == ["AA0007"]                     # not Intelligent Systems
    assert got["TP-Link"] == ["AA0009"]                   # case-insensitive
    assert got["Canon"] == ["AA000D"]
    assert vendors["Apple"][0] == "mobile" and vendors["Intel"][0] == "netcard"
    listed = {p for _, ps in vendors.values() for p in ps}
    assert not listed & {"AA0003", "AA0004", "AA0006", "AA0008", "AA000A"}


def test_first_matching_entry_wins_and_extra_prefixes_are_checked_in_the_registry():
    extra = {"Microsoft Xbox": ("console", ["AA000E", "AA00FF"])}      # AA00FF is not in it
    vendors = gen.build_vendors(gen.parse_registry(MANUF), MAPPING, extra=extra,
                                extra_first=("Microsoft Xbox",))
    assert vendors["Microsoft Xbox"] == ("console", ["AA000E"])
    assert vendors["Microsoft"] == ("computer", ["AA000F"])            # the other one
    taken = [p for _, ps in vendors.values() for p in ps]
    assert len(taken) == len(set(taken))                               # no prefix twice


def test_output_is_deterministic_sorted_and_compact():
    entries = gen.parse_registry(MANUF)
    first = gen.render(gen.build_vendors(entries, MAPPING, extra={}, extra_first=()),
                       "manuf-sample", "2026-01-02")
    reordered = dict(reversed(list(entries.items())))
    second = gen.render(gen.build_vendors(reordered, MAPPING, extra={}, extra_first=()),
                        "manuf-sample", "2026-01-02")
    assert first == second
    assert "THIS FILE IS GENERATED" in first and "manuf-sample" in first
    assert "2026-01-02" in first and "python tools/build_oui_data.py" in first
    assert max(len(line) for line in first.splitlines()) <= 100
    namespace = {}
    exec(compile(first, "oui_data_sample.py", "exec"), namespace)     # valid Python
    assert namespace["VENDORS"]["Apple"][0] == "mobile"
    assert namespace["VENDORS"]["Apple"][1].split() == ["AA0001", "AA0002"]


def test_wrapped_lines_stay_within_the_width():
    text = gen._wrap([f"{n:06X}" for n in range(500)])
    assert all(len(line) <= 100 for line in text.splitlines()) and len(text.splitlines()) > 3
    assert text.split() == [f"{n:06X}" for n in range(500)]


def test_main_writes_the_file_from_both_formats(tmp_path):
    for name, text in (("manuf.txt", MANUF), ("oui.txt", IEEE)):
        source, target = tmp_path / name, tmp_path / (name + ".py")
        source.write_text(text, encoding="utf-8")
        assert gen.main([str(source), "--output", str(target), "--date", "2026-01-02"]) == 0
        assert "VENDORS = {" in target.read_text(encoding="utf-8")
    empty = tmp_path / "empty.txt"
    empty.write_text("nothing here\n", encoding="utf-8")
    assert gen.main([str(empty), "--output", str(tmp_path / "x.py")]) == 1


# ---------------------------------------------------------------- the generated file

def test_generated_file_is_big_valid_and_has_only_prefixes():
    assert len(oui.PREFIXES) > 5000
    text = Path(oui_data.__file__).read_text(encoding="utf-8")
    assert "THIS FILE IS GENERATED" in text and "build_oui_data.py" in text
    assert not re.search(r"[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-]", text)
    for kind, prefixes in oui_data.VENDORS.values():
        assert kind in oui.KIND_TEXT and kind in oui.KIND_SHORT
        assert all(re.fullmatch(r"[0-9A-F]{6}", p) for p in prefixes.split())


@pytest.mark.parametrize("prefix,vendor", [
    ("546009", "Google"), ("3C5AB4", "Google"), ("001132", "Synology"),
    ("00155D", "Microsoft (Hyper-V virtual machine)"), ("14CC20", "TP-Link"),
    ("B827EB", "Raspberry Pi"), ("1868CB", "Hikvision")])
def test_known_prefixes_are_in_the_generated_list(prefix, vendor):
    assert oui.lookup_vendor(prefix + "000000")[0] == vendor


def test_known_wrong_prefixes_are_not_in_the_list_under_that_vendor():
    assert oui.lookup_vendor("540609") is None or oui.lookup_vendor("540609")[0] != "Google"
    assert oui.lookup_vendor("80F503") is None or oui.lookup_vendor("80F503")[0] != "Hikvision"


def test_private_mac_never_gets_a_vendor():
    from conftest import private_mac
    from network_health import scanner
    from network_health.devices import Device
    device = Device("192.0.2.5", mac=private_mac())           # locally administered bit set
    scanner.identify(device)
    assert device.private_mac and device.vendor == ""
