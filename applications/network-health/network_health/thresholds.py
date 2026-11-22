"""Verdict thresholds. The reason for each value is in network-health-design.md
(section "Verdict rules"); change both together.

A value at or below a "good" limit is good, at or below a "warn" limit is
warn, above it is bad (for the "higher is better" values the other way round).
"""

# Ping count per target (20 replies give 5 % steps for packet loss).
PING_COUNT = 20

# Latency (average round trip, ms).
GATEWAY_LATENCY_GOOD_MS = 10
GATEWAY_LATENCY_WARN_MS = 30
INTERNET_LATENCY_GOOD_MS = 50
INTERNET_LATENCY_WARN_MS = 100

# Jitter (mean difference between consecutive replies, ms).
JITTER_GOOD_MS = 10
JITTER_WARN_MS = 30

# Packet loss (%). With 20 pings, one lost reply is 5 %.
LOSS_GOOD_PCT = 0
LOSS_WARN_PCT = 5

# DNS answer time (median, ms).
DNS_GOOD_MS = 50
DNS_WARN_MS = 150

# Path MTU (bytes). 1500 is full Ethernet; 1492 is normal for PPPoE.
MTU_FULL = 1500
MTU_WARN_BELOW = 1400
MTU_PROBE_MIN_PAYLOAD = 1200
MTU_PROBE_MAX_PAYLOAD = 1472  # 1472 + 28 bytes of headers = 1500
ICMP_IPV4_OVERHEAD = 28

# Bandwidth (Mbit/s), higher is better.
DOWNLOAD_GOOD_MBPS = 25
DOWNLOAD_WARN_MBPS = 10
UPLOAD_GOOD_MBPS = 5
UPLOAD_WARN_MBPS = 2

# Bufferbloat: extra latency under load (ms).
BUFFERBLOAT_GOOD_MS = 30
BUFFERBLOAT_WARN_MS = 100
BUFFERBLOAT_MIN_SAMPLES = 3
# Below this total transfer time (s) a lack of samples is put down to a very
# fast link that finished the size-capped test too quickly.
BUFFERBLOAT_SHORT_LOAD_S = 3.0

# Wi-Fi signal (%, as Windows shows it; roughly dBm = % / 2 - 100).
SIGNAL_GOOD_PCT = 70
SIGNAL_WARN_PCT = 50

# Wi-Fi link rate (Mbit/s), higher is better.
LINK_RATE_GOOD_MBPS = 100
LINK_RATE_WARN_MBPS = 30

# Channel congestion: other networks on the same or an overlapping channel.
CONGESTION_GOOD_MAX = 3
CONGESTION_WARN_MAX = 7
OVERLAP_24GHZ_CHANNELS = 4  # 2.4 GHz channels closer than 5 apart overlap

# DHCP lease (seconds) below which the lease is called short.
SHORT_LEASE_S = 3600
