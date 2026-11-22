# Network health

A command-line tool for Windows that checks the network the computer is on and prints an overall verdict (good, warn or bad), one line per area (Performance, Wi-Fi, Configuration, Local network), and a ranked list of findings, each with a plain explanation and a concrete fix tip.

The default mode is **passive**: the tool reads what the computer already knows and does not scan other devices. The only traffic it sends is ping to the default gateway and to two public addresses (1.1.1.1 and 8.8.8.8), DNS queries to the DNS servers the computer already uses, and a bandwidth test against the Cloudflare speed test (speed.cloudflare.com), which `--skip-bandwidth` turns off. Active scanning (#150) and router login (#151) are later issues; Linux support is #152.

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
```

| Option | Effect |
|--------|--------|
| `--skip-bandwidth` | Do not run the bandwidth test (the only check that sends noticeable traffic to a third party: at most 25 MB down and 10 MB up, and less on a slow link). The bufferbloat check is skipped with it. |
| `--json` | Print the report as JSON instead of text. |
| `--save` | Also write a snapshot to `local-data/`. The next run compares the gateway's MAC address with it, to notice a possible ARP spoofing attack. |

A run takes about a minute. Progress messages go to the screen while it runs; the report comes at the end. The report ends with "Contacted in this run", which lists every address and server the run used.

## Your data stays local
The report and snapshots contain real data about your network (IP and MAC addresses, the Wi-Fi name). Snapshots are written to `local-data/` in this folder, which git ignores (`.gitignore` in the repository root). If you save a report, put it there too. Never paste real output into an issue, a pull request or a commit: the repository is public. The privacy guard catches real-looking addresses and secrets, but real Wi-Fi names, host names and device vendors cannot be detected automatically; they rely on review.

## Run the tests

```
python -m pip install -r requirements.txt
python -m pytest
```

or, from the repository root, `scripts/check.sh applications/network-health`. The tests use recorded, made-up command output (documentation addresses such as 192.0.2.1, the made-up MAC range 00:00:5e:00:53:xx, names such as ExampleHome) and never touch the network, so they run on Linux too. The privacy guard `scripts/tests/test_network_health_privacy.py` runs with the tests of `scripts/` (and in the required check `checks`) and fails if real-looking addresses, MAC addresses or secrets appear anywhere in this folder.

## Files
- `network_health/` - the package: `cli.py` (options), `collect.py` (gathers facts), `checks.py` (verdicts and fix tips), `report.py`, `snapshot.py`, `dnsprobe.py`, `bandwidth.py`, `known_hosts.py` (the external servers), `thresholds.py` (the verdict limits), `models.py`, `runner.py` (the only place that starts system commands) and `platforms/` (the Windows implementation and its parsers).
- `tests/` - pytest tests; `tests/fixtures/windows/` holds the made-up command output.
- `network-health-design.md` - the design.
- `local-data/` - created by `--save`; ignored by git.

## Owner check
Run the tool on your home network (`python -m network_health`, then once with `--save`), read the verdict and the findings, and confirm that they match how the network feels. If a threshold seems wrong for your network, note which check and value, so the rule in the design document can be tuned.
