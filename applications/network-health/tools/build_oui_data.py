"""Generate network_health/oui_data.py (the MAC vendor prefixes) from a local
copy of the public IEEE registry.

Usage (from applications/network-health):

    python tools/build_oui_data.py local-data/registry-manuf.txt
    python tools/build_oui_data.py path/to/oui.txt --date 2026-11-22

Download the registry yourself and keep it in local-data/ (git ignores it; do
not commit it):

* IEEE:      https://standards-oui.ieee.org/oui/oui.txt
* Wireshark: https://www.wireshark.org/download/automated/data/manuf.gz
             (unpack it; it is derived from the IEEE registry)

Both formats are read. Only 24-bit prefixes are used; the 28-bit and 36-bit
blocks of the registry (shared prefixes, assigned to small companies) are
ignored. A prefix is written to oui_data.py when the registry's vendor name
matches a pattern of MAPPING below (a case-insensitive regular expression,
searched in the full vendor name). The first entry of MAPPING that matches a
prefix wins, so more specific entries come first. The output is sorted, so the
same registry always gives the same file.

Standard library only. To add a maker, add an entry to MAPPING and run the
script again, then commit the generated oui_data.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

# display name -> (kind, [patterns]). The kind is a key of oui.KIND_TEXT.
# Several kinds are neutral on purpose (a maker of phones is also a maker of
# TVs): the report says "probably".
MAPPING: dict[str, tuple[str, list[str]]] = {
    # --- game consoles (before their makers' general entries)
    "Sony Interactive Entertainment (PlayStation)": ("console", [r"^sony interactive"]),
    "Nintendo": ("console", [r"^nintendo"]),
    # --- virtual machines
    "VMware (virtual machine)": ("vm", [r"^vmware"]),
    "Oracle VirtualBox (virtual machine)": ("vm", [r"^pcs systemtechnik", r"^pcs computer systems"]),
    "Xen (virtual machine)": ("vm", [r"^xensource"]),
    # --- boards
    "Raspberry Pi": ("board", [r"^raspberry pi"]),
    # --- phones, tablets and computers
    "Apple": ("mobile", [r"^apple[, ]\s*(inc|computer)"]),
    "Samsung": ("consumer", [r"^samsung"]),
    "Google": ("media", [r"^google\b"]),
    "Huawei": ("mobile", [r"^huawei"]),
    "Xiaomi": ("consumer", [r"^xiaomi", r"^beijing xiaomi"]),
    "OnePlus": ("mobile", [r"^oneplus"]),
    "Oppo": ("mobile", [r"^guangdong oppo", r"^oppo mobile"]),
    "Motorola Mobility": ("mobile", [r"^motorola mobility"]),
    "Sony": ("consumer", [r"^sony\b"]),
    "LG Innotek": ("netcard", [r"^lg innotek"]),
    "LG Electronics": ("consumer", [r"^lg electronics"]),
    "Lenovo": ("computer", [r"^lenovo"]),
    "Dell": ("computer", [r"^dell\b"]),
    "HP (Hewlett-Packard)": ("pcprinter", [r"^hewlett[- ]packard", r"^hp inc"]),
    "Microsoft": ("computer", [r"^microsoft"]),
    # --- PC network chips and modules
    "Intel (network card)": ("netcard", [r"^intel (corporate|corporation|corp)\b"]),
    "Realtek": ("netcard", [r"^realtek"]),
    "Qualcomm / Atheros": ("netcard", [r"^qualcomm", r"^atheros"]),
    "MediaTek / Ralink": ("netcard", [r"^mediatek", r"^ralink"]),
    "Broadcom": ("netcard", [r"^broadcom"]),
    "Liteon": ("netcard", [r"^lite-?on"]),
    "AzureWave": ("netcard", [r"^azurewave"]),
    "Hon Hai / Foxconn": ("netcard", [r"^hon hai", r"foxconn"]),
    "Murata": ("netcard", [r"^murata manufacturing"]),
    "Universal Global Scientific": ("netcard", [r"^universal global scientific"]),
    "Chicony": ("netcard", [r"^chicony"]),
    # --- routers and provider boxes
    "TP-Link": ("router", [r"^tp-?link"]),
    "Netgear": ("router", [r"^netgear"]),
    "ASUS": ("router", [r"^asustek"]),
    "Linksys": ("router", [r"linksys"]),
    "D-Link": ("router", [r"^d-?link"]),
    "Ubiquiti": ("router", [r"^ubiquiti"]),
    "MikroTik": ("router", [r"^routerboard", r"^mikrotik"]),
    "AVM (Fritz!Box)": ("router", [r"^avm (gmbh|audiovisuelles)"]),
    "Zyxel": ("router", [r"^zyxel"]),
    "ZTE": ("router", [r"^zte\b"]),
    "Sagemcom": ("router", [r"^sagemcom"]),
    "Technicolor / Vantiva": ("router", [r"^technicolor", r"^vantiva"]),
    "Arcadyan": ("router", [r"^arcadyan"]),
    "Sercomm": ("router", [r"^sercomm"]),
    "Compal Broadband": ("router", [r"^compal broadband"]),
    "Askey": ("router", [r"^askey"]),
    "Belkin": ("router", [r"^belkin"]),
    "Tenda": ("router", [r"\btenda\b"]),
    "Mercusys": ("router", [r"^mercusys"]),
    "eero": ("router", [r"^eero\b"]),
    "Hitron": ("router", [r"^hitron"]),
    "Cisco": ("router", [r"^cisco systems"]),
    # --- TVs and media
    "Roku": ("media", [r"^roku"]),
    "Amazon (Echo, Fire TV, Ring)": ("media", [r"^amazon"]),
    "Sonos": ("media", [r"^sonos\b"]),
    "Bose": ("media", [r"^bose\b"]),
    "Hisense": ("tv", [r"^hisense"]),
    "TCL": ("tv", [r"^tcl\b"]),
    "Vizio": ("tv", [r"^vizio"]),
    "TP Vision (Philips TV)": ("tv", [r"^tp vision"]),
    "Panasonic": ("consumer", [r"^panasonic"]),
    # --- printers
    "Canon": ("printer", [r"^canon\b"]),
    "Epson": ("printer", [r"^seiko epson", r"^epson\b"]),
    "Brother": ("printer", [r"^brother industries"]),
    "Lexmark": ("printer", [r"^lexmark"]),
    "Xerox": ("printer", [r"^xerox", r"^fuji xerox"]),
    "Kyocera": ("printer", [r"^kyocera"]),
    "Ricoh": ("printer", [r"^ricoh"]),
    "Konica Minolta": ("printer", [r"^konica minolta"]),
    # --- cameras
    "Hikvision": ("camera", [r"hikvision"]),
    "Dahua": ("camera", [r"dahua"]),
    "Axis Communications": ("camera", [r"^axis communications"]),
    "Reolink": ("camera", [r"reolink"]),
    "Wyze": ("camera", [r"^wyze"]),
    "Arlo": ("camera", [r"^arlo\b"]),
    "Ring": ("camera", [r"^ring (llc|inc)\b"]),
    "EZVIZ": ("camera", [r"ezviz"]),
    "Foscam": ("camera", [r"foscam"]),
    "Amcrest": ("camera", [r"amcrest"]),
    # --- network storage
    "Synology": ("nas", [r"^synology"]),
    "QNAP": ("nas", [r"^qnap"]),
    "Western Digital": ("nas", [r"^western digital"]),
    "Buffalo": ("nas", [r"^buffalo\b"]),
    "Asustor": ("nas", [r"^asustor"]),
    "TerraMaster": ("nas", [r"terramaster"]),
    # --- smart home and IoT
    "Espressif (smart-home chips)": ("iot", [r"^espressif"]),
    "Tuya": ("iot", [r"\btuya\b"]),
    "Shelly (Allterco)": ("iot", [r"^allterco"]),
    "Philips Hue (Signify)": ("lighting", [r"^signify", r"^philips lighting"]),
    "IKEA": ("iot", [r"^ikea"]),
    "Nest": ("iot", [r"^nest labs"]),
    "ecobee": ("iot", [r"^ecobee"]),
    "Sonoff (ITEAD)": ("iot", [r"^itead"]),
    "LIFX": ("lighting", [r"^lifx"]),
    "iRobot": ("iot", [r"^irobot"]),
    "Roborock": ("iot", [r"roborock"]),
}

# Prefixes the registry cannot tell apart by name, added by hand (the vendor
# name is the same as for a bigger maker). The prefix is checked in the
# registry and must be a 24-bit entry there; otherwise it is not written.
EXTRA_PREFIXES: dict[str, tuple[str, list[str]]] = {
    "Microsoft (Hyper-V virtual machine)": ("vm", ["00155D"]),
    "Microsoft Xbox": ("console", ["0017FA"]),
}
# These come before MAPPING so that they win over the maker's general entry.
EXTRA_FIRST = ("Microsoft (Hyper-V virtual machine)", "Microsoft Xbox")

_MANUF = re.compile(r"^([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2})$")
_IEEE_HEX = re.compile(r"^([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})\s+\(hex\)\s+(.*\S)\s*$")


def parse_registry(text: str) -> dict[str, str]:
    """{6-digit upper-case prefix: vendor name} of the 24-bit entries, from the
    Wireshark manuf format or the IEEE oui.txt format. Shared 28-bit and
    36-bit blocks and the IEEE entries for them are left out."""
    entries: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        ieee = _IEEE_HEX.match(line)
        if ieee:
            name = ieee.group(4)
            if name.lower().startswith("ieee registration authority"):
                continue  # the 24-bit prefix is shared out in smaller blocks
            entries.setdefault("".join(ieee.group(i) for i in (1, 2, 3)).upper(), name)
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 2:
            continue
        match = _MANUF.match(fields[0].strip())
        if not match:  # the 28-bit and 36-bit blocks (a longer prefix, with "/")
            continue
        name = fields[2].strip() if len(fields) > 2 and fields[2].strip() else fields[1].strip()
        entries.setdefault("".join(match.groups()).upper(), name)
    return entries


def build_vendors(entries: dict[str, str], mapping=None, extra=None,
                  extra_first=EXTRA_FIRST) -> dict[str, tuple[str, list[str]]]:
    """{display name: (kind, sorted prefixes)}; the first matching entry wins."""
    mapping = MAPPING if mapping is None else mapping
    extra = EXTRA_PREFIXES if extra is None else extra
    compiled_map = [(display, kind, [re.compile(p, re.IGNORECASE) for p in patterns])
                    for display, (kind, patterns) in mapping.items()]
    vendors: dict[str, tuple[str, list[str]]] = {}
    taken: set[str] = set()

    def add(display: str, kind: str, prefix: str) -> None:
        if prefix in taken:
            return
        taken.add(prefix)
        vendors.setdefault(display, (kind, []))[1].append(prefix)

    for display in extra_first:
        if display in extra:
            kind, prefixes = extra[display]
            for prefix in prefixes:
                if prefix in entries:
                    add(display, kind, prefix)
    for prefix in sorted(entries):
        name = entries[prefix]
        for display, kind, patterns in compiled_map:
            if any(p.search(name) for p in patterns):
                add(display, kind, prefix)
                break
    for display, (kind, prefixes) in extra.items():
        if display not in extra_first:
            for prefix in prefixes:
                if prefix in entries:
                    add(display, kind, prefix)
    return {d: (k, sorted(p)) for d, (k, p) in vendors.items()}


def _wrap(prefixes: list[str], indent: str = "        ", width: int = 100) -> str:
    lines, current = [], indent
    for prefix in prefixes:
        if len(current) + 1 + len(prefix) > width and current.strip():
            lines.append(current.rstrip())
            current = indent
        current += prefix + " "
    lines.append(current.rstrip())
    return "\n".join(lines)


def render(vendors: dict[str, tuple[str, list[str]]], source: str, generated: str) -> str:
    total = sum(len(p) for _, p in vendors.values())
    out = [
        '"""MAC vendor prefixes (OUI, the first 3 bytes of a MAC address) of makers of',
        "devices found on home networks.",
        "",
        "THIS FILE IS GENERATED. Do not edit it by hand.",
        f"Source: {source} (the public IEEE registry); generated {generated};",
        f"{total} prefixes of {len(vendors)} vendors.",
        "Regenerate (from applications/network-health), after downloading the registry",
        "into local-data/ yourself (git ignores that folder; never commit the registry):",
        "",
        "    python tools/build_oui_data.py local-data/registry-manuf.txt",
        "",
        "The makers and the kind of device each one stands for are the MAPPING in",
        "tools/build_oui_data.py. Only 24-bit prefixes are listed, never full MAC",
        "addresses, so the privacy guard allows the file. A vendor says who made the",
        "network chip, not what the device is: the report always says \"probably\".",
        "",
        "Format: vendor name -> (kind, prefixes). The kind is a key of oui.KIND_TEXT.",
        "Prefixes are 6 hex digits separated by spaces, sorted.",
        '"""',
        "",
        "VENDORS = {",
    ]
    for display in sorted(vendors, key=str.lower):
        kind, prefixes = vendors[display]
        out.append(f"    {display!r}: ({kind!r}, \"\"\"")
        out.append(_wrap(prefixes) + '"""),')
    out.append("}")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("registry", type=Path, help="oui.txt (IEEE) or manuf (Wireshark)")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent.parent / "network_health"
                        / "oui_data.py")
    parser.add_argument("--date", help="date of the registry (default: the file's date)")
    args = parser.parse_args(argv)
    text = args.registry.read_text(encoding="utf-8", errors="replace")
    stamp = args.date or datetime.fromtimestamp(args.registry.stat().st_mtime).date().isoformat()
    date.fromisoformat(stamp)  # must be a date
    entries = parse_registry(text)
    if not entries:
        print("No 24-bit entries found: is this an IEEE oui.txt or a Wireshark manuf file?",
              file=sys.stderr)
        return 1
    vendors = build_vendors(entries)
    args.output.write_text(render(vendors, args.registry.name, stamp), encoding="utf-8",
                           newline="\n")
    print(f"{len(entries)} 24-bit registry entries, "
          f"{sum(len(p) for _, p in vendors.values())} prefixes of {len(vendors)} vendors "
          f"written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
