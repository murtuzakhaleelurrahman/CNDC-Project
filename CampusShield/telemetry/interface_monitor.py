"""Low-overhead interface telemetry from Linux kernel byte counters."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InterfaceMetrics:
    interface: str
    interval_seconds: float
    tx_bytes_delta: int
    rx_bytes_delta: int
    tx_mbps: float
    rx_mbps: float
    tx_utilization_percent: float
    rx_utilization_percent: float


def _read_counter(node: Any, interface: str, counter: str) -> int:
    path = f"/sys/class/net/{interface}/statistics/{counter}"
    output = node.cmd(f"cat {path} 2>/dev/null").strip()
    if not output.isdigit():
        raise RuntimeError(f"Could not read {counter} for {interface}: {output}")
    return int(output)


def collect_interface_metrics(
    node: Any,
    interface: str,
    capacity_mbps: float,
    interval_seconds: float = 1.0,
) -> InterfaceMetrics:
    """Sample TX/RX byte counters and convert their change into bit rates."""
    tx_before = _read_counter(node, interface, "tx_bytes")
    rx_before = _read_counter(node, interface, "rx_bytes")
    started = time.monotonic()
    time.sleep(interval_seconds)
    elapsed = time.monotonic() - started
    tx_after = _read_counter(node, interface, "tx_bytes")
    rx_after = _read_counter(node, interface, "rx_bytes")

    tx_delta = max(0, tx_after - tx_before)
    rx_delta = max(0, rx_after - rx_before)
    tx_mbps = (tx_delta * 8) / elapsed / 1_000_000
    rx_mbps = (rx_delta * 8) / elapsed / 1_000_000

    return InterfaceMetrics(
        interface=interface,
        interval_seconds=elapsed,
        tx_bytes_delta=tx_delta,
        rx_bytes_delta=rx_delta,
        tx_mbps=tx_mbps,
        rx_mbps=rx_mbps,
        tx_utilization_percent=(tx_mbps / capacity_mbps) * 100,
        rx_utilization_percent=(rx_mbps / capacity_mbps) * 100,
    )

