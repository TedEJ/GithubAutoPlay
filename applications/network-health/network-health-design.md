# network-health: design

Issues #149 (passive mode) and #150 (active mode, section 13). This document describes what the tool does, how it decides a verdict, and the rules it keeps. The thresholds in "Verdict rules" are in `network_health/thresholds.py` as well; change both together.

## 1. Goal

Run the tool on any network (first the owner's home network) and get a clear answer to three questions:

1. Does the network perform well (latency, loss, DNS, bandwidth, Wi-Fi)?
2. Should anything in its visible configuration be changed (firewall, profile, DNS, proxy, open ports)?
3. Is anything on it a security hazard (weak Wi-Fi security, signs of ARP spoofing)?

The output is an overall verdict, one line per area, and a list of findings, each with a plain explanation and a concrete fix tip. There is no numeric score.

network-health is not a traffic analyser. #136 analyses traffic logs; the two tools share ideas, not code.

## 2. Modes

| Mode | Flag | What it may do | Issue |
|------|------|----------------|-------|
| Passive | (default) | Read what the computer already knows; ping the default gateway and two public addresses; send DNS queries to the configured resolvers; ping with do-not-fragment to one public address; run the bandwidth test against one public server. | #149 (this one) |
| Active | `--active` | Everything passive mode does, and in addition scan the local subnet: ping sweep, mDNS and SSDP queries, the ARP table, and a TCP check of 14 ports on every device found, with hazard rules for what is found. Only after confirmation, only a private range this computer is connected to. Section 13. | #150 |
| Live router | `--live-router` | Log in to the router to read its settings. | #151 |

Passive mode (#149) and active mode (#150) exist. `--live-router` is not accepted yet; it is added by its own issue, with the safety rules in section 9.

## 3. What is checked (passive mode)

Every check gives a result with status good, warn or bad (or info, see section 5), or skipped with a reason.

### Performance
| Check | How | Notes |
|-------|-----|-------|
| Latency, jitter and packet loss to the default gateway | `ping -n 20 -w 1000 <gateway>` | Jitter is the mean difference between consecutive replies. A router that ignores ping (while the internet answers) is info, not bad. |
| The same to two public addresses | `ping -n 20` to 1.1.1.1 and 8.8.8.8, in parallel with the gateway | See section 6. |
| DNS lookup time per configured resolver | A DNS query (type A) over UDP straight to each resolver, with Python's `socket`, for three names (example.com, www.iana.org, www.wikipedia.org); the median counts. | No program start in the measured time. The Windows placeholder servers `fec0:0:0:ffff::1`, `::2`, `::3` are left out. |
| Path MTU | `ping -n 1 -f -l <size> 1.1.1.1`; first 1472 bytes (= MTU 1500), then a binary search down to 1200. | A reply means the size passed without fragmentation. |
| Bandwidth down and up | `urllib` against the speed-test server (section 6). | Limits in section 6. Off with `--skip-bandwidth`. |
| Bufferbloat | While the download and the upload run, `ping -n 1` to 1.1.1.1 again and again (0.05 s pause between pings); the median loaded latency is compared with the idle average. | Needs at least three samples. On a very fast link the size-capped test can finish in well under a second; then the check is skipped and says so, instead of guessing. |

### Wi-Fi (only when connected over Wi-Fi)
| Check | How |
|-------|-----|
| Signal strength | `netsh wlan show interfaces` (Signal %, and Rssi where Windows prints it) |
| Link rate | the same (receive and transmit rate; the lower counts) |
| Band (2.4 / 5 / 6 GHz) | the same (Band line; older Windows: from the channel) |
| Channel congestion | `netsh wlan show networks mode=bssid`: other networks (not the own SSID) on the same channel (5/6 GHz) or an overlapping channel (2.4 GHz: fewer than 5 channels apart). The tip names the least crowded of channels 1, 6 and 11. |
| Security of the current network | Authentication and cipher from `show interfaces`. |

`show networks` lists what the adapter has already heard; it does not send an extra scan. Windows 11 needs location permission for both commands; without it the checks are skipped with a tip on how to turn it on.

### Configuration of this computer
| Check | How |
|-------|-----|
| Network profile (Public, Private, Domain) | PowerShell `Get-NetConnectionProfile` |
| Windows Firewall on for every profile | PowerShell `Get-NetFirewallProfile` |
| DNS servers and who they are | PowerShell `Get-NetIPConfiguration`; each server is named the router, a device on the local network, a known public resolver (section 6), a private address outside the network (VPN, ISP or company), or "your ISP or another public resolver" |
| IPv6 present | the same (global IPv6 address on the main adapter) |
| DHCP lease | the same (address origin and remaining valid lifetime; 169.254.x.x means no DHCP answer) |
| Proxy settings | `reg query "HKCU\...\Internet Settings"` (ProxyEnable, ProxyServer, AutoConfigURL), `netsh winhttp show proxy`, and the variables HTTP_PROXY, HTTPS_PROXY, ALL_PROXY. User names and passwords inside proxy addresses are hidden in the report. |
| Listening ports open to the network | PowerShell `Get-NetTCPConnection -State Listen` with the process name; ports that listen only on loopback are left out. |

The main adapter is the one with an IPv4 default gateway and the lowest interface metric.

PowerShell is called through the runner as `powershell -NoProfile -NonInteractive -Command ...` (by its full path, see section 8), and every command ends in `ConvertTo-Json` with enums turned into strings, so the output does not depend on the language of Windows.

### Local network (from data the computer already has)
| Check | How |
|-------|-----|
| Number of known neighbours | `arp -a`, entries of the main adapter; broadcast and multicast entries are left out. |
| Duplicate MAC address for different IP addresses | the same |
| Gateway MAC changed since the last snapshot | the gateway's MAC now compared with the newest snapshot in `local-data/` for the same network (same gateway address and SSID) |

### Not checked in passive mode
- Other devices on the network (open ports, services, vendors): that is active mode (`--active`, section 13).
- Router settings (UPnP, WPS, firmware, remote admin): that is `--live-router` (#151).
- UDP listening ports (Windows has many harmless ones), IPv6 neighbours, and the firewall rules for single programs.
- Whether the firewall rules for file sharing are on: the file sharing ports are reported as info with an explanation.

## 4. Rights and failures

Everything runs as a normal user; raw ICMP from Python would need administrator rights, so the system `ping` is used. A check that cannot run says why and is skipped, never failed and never crashes:

| Situation | Result |
|-----------|--------|
| A command is missing | skipped: "`<tool>` was not found on this computer." |
| The command needs more rights ("Access is denied", "requires elevation") | skipped: needs administrator rights |
| Wi-Fi location permission is off | skipped, with how to turn it on |
| Output not understood (for example a non-English Windows for netsh) | skipped: "The output of `<tool>` was not recognised. The tool reads English Windows output; ..." |
| Not on Wi-Fi | the Wi-Fi area is skipped: "This computer is not connected over Wi-Fi." |
| Any other error | skipped with the error text |

Parsers lean on parts that are the same in every language where they can: ping replies are lines with `TTL=` and a time in `ms`; `arp -a` is read by its addresses only; `reg query` output and the PowerShell JSON do not change with the language. Only `netsh wlan` and `netsh winhttp` are read in English.

## 5. Verdict levels

- Every result has a status: **good**, **info** (fine, with a note worth reading; counts as good), **warn** (should be improved), **bad** (should be fixed), or **skipped**.
- Area verdict (Performance, Wi-Fi, Configuration, Local network): bad if any result is bad, else warn if any is warn, else good if any ran, else skipped.
- Overall verdict: the worst area verdict; "unknown" when no check could run.
- Findings in the report: bad first, then warn, then info, each in area order, each with "Why" and "Fix". Good results are listed after the findings, skipped results last.

## 6. External servers

These are the only external addresses the tool knows. They are in `network_health/known_hosts.py`, and the privacy guard (section 10) allows exactly these public addresses.

| Server | Used for | Why this one |
|--------|----------|--------------|
| 1.1.1.1 (Cloudflare) | ping (latency, jitter, loss), path MTU, latency under load | Anycast, close to almost every network, run for public use, answers ping. |
| 8.8.8.8 (Google) | ping (latency, jitter, loss) | A second, independent operator, so one target's problem is not taken for the connection's. |
| Cloudflare speed test, `https://speed.cloudflare.com/__down?bytes=N` and `https://speed.cloudflare.com/__up` | bandwidth down and up | Public HTTPS endpoints made for speed tests, no account, no install, work with `urllib`, served from a nearby data centre. |
| The configured DNS servers | DNS lookup time | Only the resolvers the computer already uses are asked. |

Bandwidth limits: the download stops at 25 MB or after 10 seconds, whichever comes first (it reads in 16 kB blocks, so a slow link overshoots the 10 seconds by little). The upload first sends a 100 kB probe; if that takes 4 seconds or more (slow link) it stops there, otherwise it sends as much as takes about 8 seconds at the measured rate, at most 10 MB. Even at about 0.1 Mbit/s the whole test stays near 30 seconds. The report names the server, and `--skip-bandwidth` turns the test off.

Bandwidth timing: neither direction counts connection set-up (DNS, TCP, TLS). The download clock starts when the response headers have arrived. The upload body is a file-like object, and its clock starts when urllib reads the first block, which happens after the connection is open and the request headers are sent; it stops when the server's answer has arrived.

Known public resolvers (used only to name a DNS server, never contacted unless the computer is configured with them):

| Operator | IPv4 | IPv6 |
|----------|------|------|
| Cloudflare | 1.1.1.1, 1.0.0.1 | 2606:4700:4700::1111, 2606:4700:4700::1001 |
| Google Public DNS | 8.8.8.8, 8.8.4.4 | 2001:4860:4860::8888, 2001:4860:4860::8844 |
| Quad9 | 9.9.9.9, 149.112.112.112 | 2620:fe::fe, 2620:fe::9 |
| OpenDNS (Cisco) | 208.67.222.222, 208.67.220.220 | 2620:119:35::35, 2620:119:53::53 |

Traffic in passive mode, in full:

- 20 pings each to the default gateway, 1.1.1.1 and 8.8.8.8;
- DNS queries (three names) to each configured resolver;
- path MTU: pings with do-not-fragment to 1.1.1.1 (one when 1500 bytes pass, otherwise up to about ten for the search);
- the bandwidth test against speed.cloudflare.com (unless `--skip-bandwidth`), and during it repeated single pings to 1.1.1.1 to measure latency under load.

Nothing is sent to any other device on the local network.

## 7. Verdict rules

| Value | Good | Warn | Bad | Reason |
|-------|------|------|-----|--------|
| Latency to the gateway (average) | at most 10 ms | at most 30 ms | above 30 ms | A wired or healthy Wi-Fi link to the own router is a few ms; tens of ms mean a weak or busy link. |
| Latency to a public address | at most 50 ms | at most 100 ms | above 100 ms | Under 50 ms feels instant for calls and games; above 100 ms is noticeable. |
| Jitter | at most 10 ms | at most 30 ms | above 30 ms | Voice and video handle up to about 30 ms with their buffers. |
| Packet loss (20 pings) | 0 % | at most 5 % (one lost) | above 5 % | One lost ping can be chance; two or more of 20 hurt calls and TCP speed. |
| DNS answer time (median) | at most 50 ms | at most 150 ms | above 150 ms | Every new name waits for DNS; above 150 ms pages feel slow. A resolver that misses some answers is at least warn; one that never answers is bad. |
| Path MTU | 1500 | 1400 to 1499 is info | below 1400 is warn | 1492 is normal for PPPoE and VPNs lower it a bit; much lower suggests a misconfiguration. |
| Download | at least 25 Mbit/s | at least 10 | below 10 | 25 Mbit/s carries a 4K stream; below 10 even HD streaming and updates struggle. |
| Upload | at least 5 Mbit/s | at least 2 | below 2 | 5 Mbit/s carries an HD video call; below 2 calls and backups suffer. |
| Bufferbloat (extra latency under load) | at most 30 ms | at most 100 ms | above 100 ms | The common bufferbloat grades: below 30 ms nobody notices; above 100 ms calls lag while someone downloads. |
| Wi-Fi signal | at least 70 % | at least 50 % | below 50 % | Windows' signal % is roughly (dBm + 100) x 2: 70 % is about -65 dBm (good for full speed), 50 % about -75 dBm (usable, slower). |
| Wi-Fi link rate (lower of receive and transmit) | at least 100 Mbit/s | at least 30 | below 30 | Real throughput is about half the link rate. |
| Band | 5 or 6 GHz | 2.4 GHz is info | | 2.4 GHz reaches further but is slower and more crowded. |
| Channel congestion (other networks on the channel) | at most 3 | at most 7 | 8 or more | Networks on one channel take turns to send. |
| Wi-Fi security | WPA2 with AES (CCMP/GCMP), WPA3 | Enhanced Open (OWE) | open, WEP, first WPA, TKIP | WEP, WPA and TKIP are broken; open networks are unencrypted. |
| Network profile | Public or Domain; Private is info | Private on an open or weakly secured Wi-Fi | | Private makes the computer visible to others on the network. |
| Firewall | on for every profile | | off for any profile | |
| DNS servers | router, local device, known public resolver | an unknown public server is info | none configured | An unknown server is usually the ISP's, but malware also changes DNS. |
| IPv6 | present | absent is info | | Everything works over IPv4. |
| DHCP | DHCP lease of 1 hour or more | shorter lease, or a static address, is info | no IPv4 address, or 169.254.x.x | |
| Proxy | none | any proxy is warn | | Malware and adware set proxies; companies set them on purpose. |
| Listening ports | none open to the network | remote access (21, 22, 23, 3389, 5900, 5985, 5986) is warn; file sharing (139, 445) and other ports are info | | Remote access is a common attack target; Windows always listens on 139/445. |
| Duplicate MAC | none | one MAC for several IP addresses | the gateway's IP shares a MAC with another IP | Extenders and virtual machines explain the first; the second is how ARP spoofing looks. |
| Gateway MAC | same as the snapshot | changed is warn; no snapshot is info | | A changed MAC without a new router suggests spoofing. |

## 8. Platform layer

```
network_health/
  cli.py            command line, options, exit codes
  collect.py        collects the facts in passive mode (platform independent)
  scan_target.py    what --active may scan, and the guard for every address (section 13)
  scanner.py        the device scan: sweep, discovery, port checks, limits (section 13)
  netio.py          the one place where the device scan opens a socket (section 13)
  discovery.py      mDNS and SSDP messages: build the query, read the answers
  services.py       the port list and how a banner, HTTP head or TLS handshake is read
  oui.py, oui_data.py  the vendor prefixes (generated) and the kind guess
tools/
  build_oui_data.py  generates oui_data.py from a local copy of the IEEE registry (section 13.5)
  device_checks.py  the hazard rules for devices (section 13)
  devices.py        data classes of the device scan
  safe_text.py      cleans text that came from the network before it is shown
  checks.py         turns facts into results with status, why and fix (platform independent)
  report.py         verdicts, text report, JSON
  snapshot.py       snapshots in local-data/
  dnsprobe.py       DNS timing over UDP (standard library)
  bandwidth.py      bandwidth and latency under load (urllib)
  known_hosts.py    the external servers of section 6
  thresholds.py     the numbers of section 7
  models.py         data classes shared by all parts
  runner.py         the only place where a system command is started
  platforms/
    base.py         NetworkPlatform: the methods the checks need
    windows.py      WindowsPlatform: the commands
    windows_parsers.py  the parsers for their output
```

- `NetworkPlatform` (in `platforms/base.py`) has one method per fact: `ping`, `ping_dont_fragment`, `ping_host` (one ping, for the sweep of `--active`), `ip_configuration`, `wifi_status`, `wifi_networks`, `network_profiles`, `firewall_profiles`, `proxy_settings`, `listening_ports`, `neighbours`. Each returns objects from `models.py` or raises `Unavailable` with a kind and a reason.
- `WindowsPlatform` implements them with commands that ship with Windows 11 (ping, netsh, arp, reg, Windows PowerShell). All of them go through the `Runner` passed to it, started by their full path under `%SystemRoot%\System32` (`ping.exe`, `netsh.exe`, `arp.exe`, `reg.exe`, `WindowsPowerShell\v1.0\powershell.exe`), so a program of the same name earlier in `PATH` is not run instead. Without `SystemRoot` the bare name is used.
- Linux (#152) adds a `LinuxPlatform` with the same methods (for example `ip`, `ping -M do`, `nmcli` or `iw`, `ss`, `nft` or `ufw`) and an entry in `platforms/get_platform`. `collect.py`, `checks.py` and `report.py` do not change; a Linux concept that does not exist (such as the network profile) raises `Unavailable("not-applicable", ...)`.
- On any other system the tool says it supports Windows only for now (#152) and exits with code 2.
- Optional tools such as nmap are not used, in passive or in active mode (section 13); every check works without them.

## 9. Safety rules for active scanning and router access (for #150 and #151)

These rules are fixed now so the later issues build on them.

Active scanning (`--active`), implemented by #150 as described in section 13:
- Only with the flag, never by default, and only on the subnet of the main adapter, never on a public range.
- Before the scan the tool prints what it will do and asks for confirmation (a `--yes` flag for scripted use).
- Rate limited (at most 50 pings and 50 port checks per second, one port of a device at a time), a small fixed port list, no exploits, no password guessing, no denial of service.
- The user must own the network or have permission; the README says so.
- Results with device names and MAC addresses go to `local-data/` only.

Router access (`--live-router`):
- Only with the flag. Read-only: the tool never changes a router setting.
- The password is asked with `getpass` at run time and never stored, logged or printed; no password is ever written to a file or passed on the command line.
- Only the router at the default gateway address, over the protocol the router offers (prefer HTTPS); certificate problems are shown, not silently ignored.
- Router model and settings tied to the owner never leave `local-data/`.

## 10. Privacy

- The repository is public. No real network data (IP or MAC addresses, SSIDs, host or device names, vendors, public IP, router details tied to the owner, credentials) may be written in code, fixtures, commits, issues, pull requests or comments.
- Snapshots (`--save`) go to `applications/network-health/local-data/`, which `.gitignore` excludes. The text and JSON reports go to the screen; if you save them, save them in `local-data/` as well.
- Fixtures use the documentation ranges 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 and 2001:db8::/32, MAC addresses from the RFC 7042 range 00:00:5e:00:53:xx, and made-up names such as ExampleHome. The one exception is the tests of `--active`: the scan refuses documentation ranges (they are not private), so those tests build addresses in a private range at run time, in memory, from the allowed base 10.0.0.0 (`conftest.private_ip(10)`), and MAC addresses with a vendor prefix from the 6-digit prefix plus a made-up suffix (`conftest.mac_with_prefix`). No such address is written in a file, so the guard needs no new rule. The bundled vendor list holds 3-byte prefixes only (the guard allows them).
- Real SSIDs, host names and device vendors cannot be told apart from made-up ones automatically. The privacy guard does not detect them; they rely on review of every change in this folder.
- The tool never reads Wi-Fi passwords (`netsh wlan show profile key=clear` is not used).
- The privacy guard `scripts/tests/test_network_health_privacy.py` runs in the required check `checks`. It scans every file under `applications/network-health/` that git tracks or would add (`git ls-files -co --exclude-standard`, so ignored files such as `local-data/` are left out; without git it walks the folder), reads UTF-8 and UTF-16 files (what Windows PowerShell 5.1 writes with `>`), and fails on other addresses (also with leading zeros), other MAC addresses (also as 12 bare hex digits) and anything that looks like a password, key or token, quoted or as an unquoted `NAME=value` line. Its allowlist is the list in section 6 plus the documentation and special ranges; its docstring describes the exact rules and the narrow exception marker.

## 11. Report and options

```
python -m network_health [--skip-bandwidth] [--json] [--save] [--active [--yes]]
```

- Text report: a header, the overall verdict with one sentence, one line per area (verdict, number of checks, counts of bad/warn/info), the findings ranked bad, warn, info with "Why" and "Fix", the checks that passed, the skipped checks with reasons, and "Contacted in this run" (which addresses were pinged and which servers were used, including the speed-test server).
- `--json`: the same as one JSON object (`overall`, `areas`, `findings`, `results`, `contacted`).
- `--save`: also writes `local-data/snapshot-YYYYMMDD-HHMMSS.json` with the report, the network identity (gateway address and SSID) and the gateway MAC.
- Progress messages go to standard error, the report to standard output.
- Exit code 0 when a report was printed (whatever the verdict), 2 on an unsupported system, 3 when `--active` was refused or not confirmed (nothing was sent).
- The whole run takes about a minute: 20 s of ping, a few seconds of DNS and MTU, up to about 30 s of bandwidth test, and a few seconds of PowerShell. `--active` adds the device scan (section 13): about one to two minutes on a /24 at home, never more than 5 minutes.

## 12. Tests

- Every parser and check is tested with recorded, made-up command output in `tests/fixtures/windows/` (English Windows, plus Swedish samples for the "not recognised" path).
- A fake runner answers the commands; a test fails on any command it does not know. The DNS probe gets a fake socket and clock, the bandwidth test a fake opener and clock. No test opens a network connection or starts a real command, and the tests run on Linux as well.
- A test checks that passive mode pings only the gateway and the two public targets and sends DNS queries only to the configured resolvers.
- The tests of `--active` replace the network layer (`netio.NetIO`) with a fake that answers from made-up data and records every call, the ping and ARP table with a stub platform, and the clock with a fake clock. `tests/conftest.py` makes any real socket (`connect`, `sendto`, `create_connection`) fail the test, so a test cannot reach the network by mistake. `test_netio.py` tests the real network layer against fake sockets. Section 13 lists what is checked.
- Run them with `scripts/check.sh applications/network-health`. CI steps for these tests are a later owner change to `ci.yml`; the privacy guard already runs in `checks` with the tests of `scripts/`.

## 13. Active mode (`--active`, issue #150)

`--active` runs everything of passive mode and then scans the local network. It is never the default. The code is in `scan_target.py` (the rules), `scanner.py` (the steps and limits), `netio.py` (all sockets), `discovery.py`, `services.py`, `oui.py`, `device_checks.py` and `report.py`.

### 13.1 What may be scanned

The target is never typed by the user and there is no option to choose another range. It is worked out from the IPv4 address and prefix length of this computer's main adapter (the one with an IPv4 default gateway and the lowest metric; other adapters, such as virtual switches, are not scanned) and accepted only when all of this holds:

| Rule | What happens when it fails |
|------|----------------------------|
| The subnet lies inside 10.0.0.0/8, 172.16.0.0/12 or 192.168.0.0/16 (RFC 1918). | Refused: "it is not a private range" (public and documentation ranges). Loopback (127.0.0.0/8), self-assigned 169.254.0.0/16 (no DHCP answer) and multicast get their own wording. |
| It is not the shared range 100.64.0.0/10 (carrier-grade NAT, RFC 6598). | Refused: it is the provider's range, not the user's own network. |
| It is directly attached: the subnet is computed from this computer's own address, so this computer is in it. The main adapter must have an IPv4 default gateway (the fallback of the passive checks to any adapter is not used for a scan). | Refused when the adapter has no IPv4 address, no IPv4 default gateway, or the configuration cannot be read. |
| It has at most 1022 usable addresses (a /22 or smaller) and at least one address besides this computer's. | Refused with: "A home network is usually a /24 (254 addresses). Use a smaller subnet on the router, or connect to a smaller network. The tool has no option to choose another range." |

IPv6 is never swept: a /64 has 2^64 addresses. Devices are found over IPv4 (ping sweep, ARP table, and mDNS and SSDP answers that arrive over IPv4). IPv6 neighbours are not read and no IPv6 port is checked; a device that is reachable over IPv6 only is not listed, and the report says so. (Reading the IPv6 neighbour table and checking the on-link neighbours found that way is a possible follow-up.)

`ScanGuard` repeats the rules for every single destination, right before it is used: a unicast address must be a usable address of the confirmed subnet (not the network or broadcast address, not another subnet), a multicast destination must be exactly 224.0.0.251:5353 (mDNS) or 239.255.255.250:1900 (SSDP), and the multicast query leaves from this computer's own address in the subnet. `ScanGuard` cannot even be created for a public, CGNAT or too large subnet. The scan stops with an error if any code asks it to send elsewhere. Answers that come from an address outside the subnet are ignored and counted in a note, so a device cannot make the tool probe another address by answering from it. After the confirmation the passive checks read the network configuration again; when the network is not the confirmed one any more, the scan is not run.

### 13.2 Confirmation

Before anything is sent the tool prints, on standard error, the subnet and the number of addresses, what the scan does, the limits, and "WARNING: Only scan networks you own or have permission to test. Scanning a network without permission can be illegal." Then it asks `Scan this network? Type y or yes to continue [y/N]`. Anything other than `y` or `yes` (also an empty line or end of input) aborts with exit code 3 and nothing sent. `--yes` skips the question, but the description is still printed. When standard input is not a terminal and `--yes` is not given, the tool aborts with a message instead of waiting. Refused scans also exit with 3.

### 13.3 What is sent, in full

1. **Ping sweep:** one system `ping -n 1 -w 500 <address>` for every usable address of the subnet except this computer's, through the platform layer and the Runner (no raw sockets, no administrator rights).
2. **mDNS and SSDP:** one UDP datagram each, sent twice, to the multicast groups on the local link (time-to-live 1, so it does not pass the router): an mDNS query for 11 service types (`_services._dns-sd._udp`, `_workstation`, `_http`, `_ipp`, `_printer`, `_airplay`, `_googlecast`, `_hap`, `_smb`, `_ssh`, `_device-info`) to 224.0.0.251:5353, and an SSDP `M-SEARCH` (`ST: ssdp:all`, `MX: 1`) to 239.255.255.250:1900. The tool listens for 2 seconds after each send. The `LOCATION` address in an SSDP answer is not followed.
3. **ARP table:** `arp -a` once, after the sweep, so devices that ignore ping but answer ARP are found too.
4. **Port checks** on every device found: a TCP connect to each port below, one port of a device at a time. Nothing else is sent to a device except what the third column says.

| Port | Service | What is done after a connection is accepted | Why it matters |
|------|---------|---------------------------------------------|----------------|
| 21 | FTP | Nothing is sent; waits up to 1 s for the banner, reads at most 256 bytes. | Files and passwords without encryption. |
| 22 | SSH | The same. | Remote login (encrypted). |
| 23 | Telnet | The same; the telnet option bytes are removed. | Remote login without encryption. |
| 80 | HTTP | One `HEAD / HTTP/1.0` request (no cookie, no login), reads the answer head, at most 2048 bytes, 2 s. | Web interface without encryption. |
| 443 | HTTPS | A TLS handshake without checking the certificate (home devices use self-signed ones); nothing is sent after it, no request, no credentials. Only to learn that HTTPS is offered. | Web interface with encryption. |
| 445 | SMB | Connect only. | Windows file sharing. |
| 554 | RTSP | Connect only. | Camera video stream. |
| 1900 | UPnP (TCP) | Connect only. | UPnP (the main UPnP traffic is UDP, answered in step 2). |
| 3389 | RDP | Connect only. | Windows remote desktop. |
| 5000 | HTTP | One `HEAD /` as for port 80. | NAS web interfaces, UPnP descriptions. |
| 5900 | VNC | The same as port 21: waits for the banner. | Remote desktop. |
| 7547 | TR-069 | Connect only. | The provider's router management. |
| 8080 | HTTP | One `HEAD /` as for port 80. | Web interface on another port. |
| 8443 | HTTPS | A TLS handshake as for port 443. | Web interface with encryption on another port. |

The list is `services.PORT_PLAN`. No login, no password guessing, no exploit, no UDP flood, nothing that changes a device, no retries. Text from the network (names, banners, Server headers) is cleaned before it is stored or printed: control characters, including the escape character of terminal commands, are replaced and the length is cut (`safe_text.py`).

### 13.4 Limits and time

| Limit | Value |
|-------|-------|
| Subnet size | at most 1022 addresses (a /22) |
| Time limit for the whole device scan | 300 seconds (5 minutes). No new operation is started when less than 6 seconds (the longest single operation) are left, checked before and after the rate-limit wait of every operation, and the ARP table is not read when the deadline has passed, so the scan ends within the limit; the result is then marked incomplete and a warning says which part was cut short. |
| Share of that for the ping sweep | at most 120 seconds |
| Pings at the same time | 32 |
| Devices checked at the same time | 16 (the ports of one device one after the other) |
| Rate | operations of all workers start at least 0.02 s apart: at most 50 pings and at most 50 port checks per second |
| One ping | waits 500 ms for the reply; the command is stopped after 6 s |
| One port check | connect time-out 1 s; banner wait 1 s; HTTP wait 2 s; TLS time-out 2 s |
| mDNS and SSDP | sent 2 times, 2 s of listening after each, at most 512 answers |

Expected time on a /24 at home: ping sweep 10 to 30 s (an address that does not answer can take about 3 s while Windows asks for its ARP answer, 32 at a time), mDNS and SSDP 4 s, port checks a few seconds per device (a closed port answers at once; a filtered port takes 1 s; 16 devices in parallel). Typically one to two minutes in all. The test `test_full_slash_24_scan_ends_within_the_time_limit` runs a full /24 with 60 devices through the fake layer and a fake clock, charging the slowest answers a network can give (every dead address 3 s, every port filtered, 2 s per port check); it ends after about 137 simulated seconds, and the test requires at most 300. Two more tests cut the sweep and the port checks short with one worker, to show that the limit is enforced and the scan is marked incomplete. The time limit applies to the device scan; the passive checks before it (about a minute) are not part of it.

### 13.5 Names, vendors and kinds

- **Name:** only from mDNS, and only from records about the sending device itself (its own A record, then its SRV host name, then the service instance name). No reverse DNS lookup is made, because Windows may use LLMNR or NetBIOS for that, which sends multicast and broadcast.
- **Vendor:** from the first 3 bytes of the MAC address (the OUI). The list `network_health/oui_data.py` is **generated** from the public IEEE registry by `tools/build_oui_data.py`: every 24-bit prefix whose registry vendor name matches a pattern of the mapping in that script (display name, kind of device, case-insensitive patterns for the makers found on home networks: phones and computers, PC network chips, routers and provider boxes, consoles, TVs, printers, cameras, NAS, smart-home devices, boards and virtual machines) is written, sorted, so the same registry always gives the same file. At the time of writing that is about 12,000 prefixes of 94 vendors (about 98 kB). Only 24-bit prefixes are used; the 28-bit and 36-bit blocks of the registry are shared between small companies and ignored. The file holds prefixes only, never full MAC addresses, so the privacy guard allows it unchanged. To rebuild it, download the registry yourself into `local-data/` (the IEEE `oui.txt` from https://standards-oui.ieee.org/oui/oui.txt, or the Wireshark `manuf` file from https://www.wireshark.org/download/automated/data/manuf.gz, unpacked; both formats are read; git ignores `local-data/` and the registry must never be committed) and run `python tools/build_oui_data.py local-data/<file>` from `applications/network-health`. To add a maker, add an entry to the mapping and run the script again. **A MAC address with the "locally administered" bit set is a private (random) address (phones and computers use these); it never gets a vendor** and is marked as a private MAC address. A vendor says who made the network chip, not what the device is, so the report calls every vendor-based type a guess ("probably"). For a maker with several kinds of product the most likely or a neutral kind is used (for example "a computer or a built-in network card" for Intel, Realtek and similar, "a computer or a printer" for HP).
- **Kind** (probably a printer, camera, router, NAS, game console, media player, smart-home device, computer, phone ...): from the strongest hint: the default gateway is a router; then a word in the name (nas, printer, cam ...); then the mDNS service types (`_ipp` is a printer); then words in the Server header (SSDP or HTTP); then the vendor.
- **Known file server** (for the SMB rule): a device whose kind is "nas", that is, a NAS maker's vendor prefix (Synology, QNAP), a name with nas, diskstation, storage, fileserver, mycloud, truenas and the like, or a Server header that says so. This computer is not scanned, so its own file sharing is judged by the passive check "Listening ports", not here.
- **nmap** is not used. Everything works without it, and one code path is easier to keep safe.

### 13.6 Hazard rules

Each rule gives one result in the area **Devices** with a status, a "Why" and a "Fix", and marks the devices it names in the Devices table. When nothing matches, the rule shows as a passed check.

| Rule (result id) | Status | Applies when | Why it matters (short) |
|------------------|--------|--------------|------------------------|
| Telnet open (`dev.telnet`) | bad | port 23 accepts a connection | The login is in plain text and Mirai-type malware takes over devices with default passwords. |
| FTP open (`dev.ftp`) | warn | port 21 open | Passwords and files without encryption. |
| SMB on a device that is not a known file server (`dev.smb`) | warn | port 445 open and the device is not a known file server (13.5) | Shares and a spreading route for ransomware and worms. |
| Remote desktop or VNC open (`dev.remote`) | warn | port 3389 or 5900 open | Full control for anyone with the password; common target. |
| Admin page on plain HTTP (`dev.http_admin`) | warn; info when HTTPS is offered as well | a router (the gateway), camera, NAS, printer, or any page that asks for a login (WWW-Authenticate) answers HTTP on 80, 5000 or 8080 without redirecting to https:// | The admin password travels unencrypted. |
| UPnP answering (`dev.upnp`) | warn when the router answers; otherwise info | a device answers the SSDP search | UPnP lets programs open router ports without a password; other devices announce themselves. |
| TR-069 reachable (`dev.tr069`) | warn | port 7547 open | The provider's management port, reachable from the whole LAN. |
| Unknown devices (`dev.unknown`) | info | no name from mDNS and no vendor in the list (the gateway is left out) | May be a guest or something that should not be there. The list is short, so a real device can be missing; private MAC addresses are named. |
| New devices (`dev.new`) | warn; info when there is no earlier scan | the MAC address (or the IP address when there is none) is not in the newest snapshot of the same network that holds devices | A new phone of yours, or someone who should not be on the network. |
| Scan cut short (`dev.incomplete`) | warn | the time limit stopped the sweep or the port checks | The list may be incomplete. |

Also, one result "Devices found" (good, or info when none were found, with the usual reasons: guest network, AP isolation, firewall), and an info result for each note of the scan (for example the ping command was missing, mDNS could not be sent). Pings that could not run (for example the command timed out) are counted apart from addresses skipped because of the time limit; only the second makes the scan "cut short", the first gives a note. The status of the area is worked out as in section 5: bad if any is bad, else warn, and so on; the area is part of the report and of the overall verdict only when `--active` ran.

### 13.7 Report, JSON and snapshots

- The text report gets a **Devices** section after the findings: a table with IP, MAC, name, vendor (with "probably <kind>"), open ports (with service names) and hazards, and a note that the vendor and type are guesses and that only IPv4 is scanned. The findings are in the normal ranked list, in the area Devices.
- `--json` adds `"mode": "active"`, `"scan"` (subnet, adapter, counts, ports, complete, what was cut short, notes) and `"devices"` (the same fields as the table plus banners, Server headers and the rule ids in `hazards`).
- `--save` writes the same into the snapshot in `local-data/`. The next `--active` run compares with the newest snapshot of the same subnet that holds devices, by MAC address. Snapshots stay in the git-ignored `local-data/`; the report goes to the screen.
- "Contacted in this run" names the subnet and the two multicast groups.
