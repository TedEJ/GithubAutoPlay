# Network health

A command-line tool for Windows that checks the network the computer is on and prints an overall verdict (good, warn or bad), one line per area (Performance, Wi-Fi, Configuration, Local network), and a ranked list of findings, each with a plain explanation and a concrete fix tip.

The default mode is **passive**: the tool reads what the computer already knows and does not scan other devices. The only traffic it sends is ping to the default gateway and to two public addresses (1.1.1.1 and 8.8.8.8), DNS queries to the DNS servers the computer already uses, and a bandwidth test against the Cloudflare speed test (speed.cloudflare.com), which `--skip-bandwidth` turns off.

With **`--active`** the tool also scans your local network for devices and their open services (see "Active scan" below). It is never the default, and it only scans a network after you confirm. Router login (#151) is a later issue; Linux support is #152.

The design, all checks, the verdict rules with their reasons, and the safety rules are in [network-health-design.md](network-health-design.md).

## Requirements
- Windows 10 or 11, as a normal user (no administrator rights needed).
- Python 3.10 or newer. Only the standard library is used; nothing has to be installed to run the tool.
- The tool calls commands that ship with Windows: `ping`, `netsh`, `arp`, `reg` and Windows PowerShell.
- For the Wi-Fi checks Windows 11 needs location permission: Settings > Privacy & security > Location, with "Let desktop apps access your location" on. Without it those checks are skipped with a message.
- Wi-Fi and proxy output is read in English. On a Windows in another language those checks are skipped with a clear message; the other checks still work.

## Run it

From this folder (`applications/network-health`):

```
python -m network_health
python -m network_health --skip-bandwidth
python -m network_health --json
python -m network_health --save
python -m network_health --active
python -m network_health --active --yes --save
```

| Option | Effect |
|--------|--------|
| `--skip-bandwidth` | Do not run the bandwidth test (the only check that sends noticeable traffic to a third party: at most 25 MB down and 10 MB up, and less on a slow link). The bufferbloat check is skipped with it. |
| `--json` | Print the report as JSON instead of text. |
| `--save` | Also write a snapshot to `local-data/`. The next run compares the gateway's MAC address with it, to notice a possible ARP spoofing attack, and (with `--active`) the devices, to name new ones. |
| `--active` | Also scan the local subnet for devices and open services. Asks for confirmation first. See below. |
| `--yes` | With `--active`: do not ask for confirmation (for repeated runs on your own network). The description of the scan is still printed. |

A passive run takes about a minute. Progress messages go to the screen while it runs; the report comes at the end. The report ends with "Contacted in this run", which lists every address and server the run used.

## Active scan (`--active`)

**Only scan networks you own or have permission to test.** Scanning someone else's network can be illegal. This is why `--active` is never the default and why the tool asks before it starts.

`--active` runs the passive checks and then looks at the devices on your local network:

1. It works out the subnet from this computer's own network address. You cannot choose another range. The subnet must be a private range (10.0.0.0/8, 172.16.0.0/12 or 192.168.0.0/16) that this computer is connected to, and at most a /22 (1022 addresses; a home network is usually a /24 with 254). Anything else (a public range, the provider's 100.64.0.0/10 range, a self-assigned 169.254.x.x address, a larger subnet) is refused with a message, and nothing is sent. IPv6 is not scanned.
2. It prints the subnet, the number of addresses, what the scan does and the permission warning, and asks `[y/N]`. Only `y` or `yes` continues. `--yes` skips the question (use it for repeated runs on your own network). Without a terminal and without `--yes` it stops instead of waiting.
3. It pings every address (the system `ping`, 32 at a time), asks for names and types with mDNS and SSDP on the local link, reads the ARP table, and then tries a plain TCP connection to 14 ports (21, 22, 23, 80, 443, 445, 554, 1900, 3389, 5000, 5900, 7547, 8080, 8443) on every device that answered. For an open port it only reads what the service says about itself (a banner, one HTTP `HEAD` request, or a TLS handshake to see that HTTPS is offered). It never logs in, guesses passwords, sends exploits or changes anything, and it needs no administrator rights.
4. The report gets a **Devices** section (IP, MAC address, name, vendor, open ports, hazards) and findings with a fix tip for: Telnet or FTP open, file sharing (SMB) on a device that is not a known file server (a NAS), remote desktop or VNC open, router, camera, NAS or printer admin pages on plain HTTP, UPnP answering, TR-069 (port 7547) reachable, unknown devices, and new devices compared with the last saved scan. `--json` and `--save` include the devices.

**How long it takes:** usually one to two minutes on a home /24 (a few seconds to 30 s for the sweep, 4 s for mDNS and SSDP, a few seconds per device for the ports) on top of the passive checks. The scan never runs longer than 5 minutes; if it is cut short the report says so. Rates are limited (at most 50 pings and 50 port checks per second).

**Names and vendors are guesses.** A name comes from mDNS only. The vendor comes from a list of MAC prefixes of common home-device makers (`network_health/oui_data.py`, about 12,000 prefixes, generated from the public IEEE registry by `tools/build_oui_data.py`); a MAC address with the "private" (random) bit set, as phones use, never has a vendor. To rebuild the list, download the registry yourself into `local-data/` (never commit it) and run `python tools/build_oui_data.py local-data/<file>`; see section 13.5 of the design document. Devices without a name or known vendor are listed as unknown, which only means that the tool could not tell. To judge "new devices", run `--active --save` once when you know every device on the network.

The details (what is sent, all limits, the hazard rules and why each exists) are in section 13 of [network-health-design.md](network-health-design.md). `nmap` is not used.

## Your data stays local
The report and snapshots contain real data about your network (IP and MAC addresses, the Wi-Fi name and, with `--active`, the names, vendors and open ports of your devices). Snapshots are written to `local-data/` in this folder, which git ignores (`.gitignore` in the repository root). If you save a report, put it there too. Never paste real output into an issue, a pull request or a commit: the repository is public. The privacy guard catches real-looking addresses and secrets, but real Wi-Fi names, host names and device vendors cannot be detected automatically; they rely on review.

## Run the tests

```
python -m pip install -r requirements.txt
python -m pytest
```

or, from the repository root, `scripts/check.sh applications/network-health`. The tests use recorded, made-up command output (documentation addresses such as 192.0.2.1, the made-up MAC range 00:00:5e:00:53:xx, names such as ExampleHome) and never touch the network (the tests of `--active` use a fake network layer, and any real socket fails the test), so they run on Linux too. Because `--active` refuses documentation ranges, those tests build a private range at run time instead of writing it in a file. The privacy guard `scripts/tests/test_network_health_privacy.py` runs with the tests of `scripts/` (and in the required check `checks`) and fails if real-looking addresses, MAC addresses or secrets appear anywhere in this folder.

## Files
- `network_health/` - the package: `cli.py` (options), `collect.py` (gathers facts), `checks.py` (verdicts and fix tips), `report.py`, `snapshot.py`, `dnsprobe.py`, `bandwidth.py`, `known_hosts.py` (the external servers), and for `--active`: `scan_target.py` (what may be scanned), `scanner.py` (steps and limits), `netio.py` (the only code that opens sockets), `discovery.py`, `services.py`, `oui.py` and `oui_data.py` (generated vendor prefixes), and `tools/build_oui_data.py` (the generator), `device_checks.py` (hazard rules), `thresholds.py` (the verdict limits), `models.py`, `runner.py` (the only place that starts system commands) and `platforms/` (the Windows implementation and its parsers).
- `tests/` - pytest tests; `tests/fixtures/windows/` holds the made-up command output.
- `network-health-design.md` - the design.
- `local-data/` - created by `--save`; ignored by git.

## Owner check
Run the tool on your home network (`python -m network_health`, then once with `--save`), read the verdict and the findings, and confirm that they match how the network feels. If a threshold seems wrong for your network, note which check and value, so the rule in the design document can be tuned.

For `--active`: run `python -m network_health --active --save` on your home network, answer `y`, and check that the device list is complete (compare with your router's client list) and that the findings make sense. Note devices that are missing or wrongly named, and any vendor that is wrong, so the list and the rules can be improved. Keep the result in `local-data/`; never post it.
