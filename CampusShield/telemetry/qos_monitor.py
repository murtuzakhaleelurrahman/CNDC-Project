"""Read per-class Linux traffic-control counters without changing QoS state."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any


QOS_CLASS_METADATA = {
    10: ("emergency", 46),
    20: ("academic", 18),
    30: ("bulk", 8),
}


@dataclass(frozen=True)
class QosClassMetrics:
    """One cumulative HTB class counter snapshot from ``tc -s class``."""

    class_name: str
    class_id: int
    dscp_value: int
    sent_bytes: int
    sent_packets: int
    dropped_packets: int
    overlimits: int
    requeues: int
    backlog_bytes: int
    backlog_packets: int


def _backlog_bytes(value: str, suffix: str) -> int:
    multipliers = {"b": 1, "kb": 1_000, "mb": 1_000_000, "gb": 1_000_000_000}
    return int(float(value) * multipliers.get(suffix.lower(), 1))


def parse_tc_class_stats(output: str) -> dict[str, QosClassMetrics]:
    """Parse the three CampusShield HTB class blocks from ``tc`` output."""
    results: dict[str, QosClassMetrics] = {}
    blocks = re.split(r"(?=^class\s)", output, flags=re.MULTILINE)
    for block in blocks:
        header = re.match(r"class\s+\S+\s+10:(\d+)\b", block)
        if not header:
            continue
        class_id = int(header.group(1))
        metadata = QOS_CLASS_METADATA.get(class_id)
        if metadata is None:
            continue

        sent = re.search(
            r"Sent\s+(\d+)\s+bytes\s+(\d+)\s+pkt\s+"
            r"\(dropped\s+(\d+),\s+overlimits\s+(\d+)\s+requeues\s+(\d+)\)",
            block,
        )
        backlog = re.search(r"backlog\s+([\d.]+)([KMG]?b)\s+(\d+)p", block, re.I)
        name, dscp = metadata
        results[name] = QosClassMetrics(
            class_name=name,
            class_id=class_id,
            dscp_value=dscp,
            sent_bytes=int(sent.group(1)) if sent else 0,
            sent_packets=int(sent.group(2)) if sent else 0,
            dropped_packets=int(sent.group(3)) if sent else 0,
            overlimits=int(sent.group(4)) if sent else 0,
            requeues=int(sent.group(5)) if sent else 0,
            backlog_bytes=(
                _backlog_bytes(backlog.group(1), backlog.group(2)) if backlog else 0
            ),
            backlog_packets=int(backlog.group(3)) if backlog else 0,
        )
    return results


def collect_qos_class_metrics(
    node: Any, interface: str
) -> dict[str, QosClassMetrics]:
    """Read cumulative queue evidence for all configured CampusShield classes."""
    output = node.cmd(f"tc -s class show dev {shlex.quote(interface)}")
    return parse_tc_class_stats(output)
