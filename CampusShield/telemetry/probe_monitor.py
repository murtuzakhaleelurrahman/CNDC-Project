"""Small ping probes for RTT, packet loss, and delay variation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProbeMetrics:
    target: str
    dscp_value: int
    packets_sent: int
    packets_received: int
    packet_loss_percent: float
    average_rtt_ms: float
    jitter_ms: float


def collect_probe_metrics(
    node: Any,
    target: str,
    count: int = 5,
    interval_seconds: float = 0.2,
    dscp_value: int = 46,
) -> ProbeMetrics:
    """Send EF-marked ICMP service probes and parse individual RTT values."""
    # Node.cmd() uses Mininet's one-at-a-time interactive shell. A separate
    # process permits a probe and byte-counter sampling to run concurrently on
    # the same router namespace without tripping Mininet's waiting assertion.
    process = node.popen(
        [
            "ping", "-n", "-Q", str(dscp_value << 2), "-c", str(count),
            "-i", str(interval_seconds), "-W", "1", target,
        ]
    )
    stdout, stderr = process.communicate()
    stdout_text = stdout.decode() if isinstance(stdout, bytes) else (stdout or "")
    stderr_text = stderr.decode() if isinstance(stderr, bytes) else (stderr or "")
    output = stdout_text + stderr_text
    loss_match = re.search(r"([\d.]+)% packet loss", output)
    loss_percent = float(loss_match.group(1)) if loss_match else 100.0
    rtt_values = [
        float(value)
        for value in re.findall(r"time[=<]([\d.]+)\s*ms", output)
    ]

    received = len(rtt_values)
    average_rtt = sum(rtt_values) / received if received else 0.0
    # Mean absolute difference between consecutive RTT samples is a simple,
    # low-overhead delay-variation estimate. iPerf3 UDP will validate jitter
    # during formal experiments later in the project.
    differences = [
        abs(current - previous)
        for previous, current in zip(rtt_values, rtt_values[1:])
    ]
    jitter = sum(differences) / len(differences) if differences else 0.0

    return ProbeMetrics(
        target=target,
        dscp_value=dscp_value,
        packets_sent=count,
        packets_received=received,
        packet_loss_percent=loss_percent,
        average_rtt_ms=average_rtt,
        jitter_ms=jitter,
    )

