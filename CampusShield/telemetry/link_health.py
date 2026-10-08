"""Per-link health measurement for adaptive routing decisions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from controller.health_score import (
    HealthMetrics,
    HealthScore,
    HealthThresholds,
    calculate_health_score,
)
from telemetry.interface_monitor import (
    InterfaceMetrics,
    collect_interface_metrics,
)
from telemetry.probe_monitor import ProbeMetrics, collect_probe_metrics


@dataclass(frozen=True)
class LinkHealth:
    link_name: str
    interface_metrics: InterfaceMetrics
    probe_metrics: ProbeMetrics
    score: HealthScore


def collect_link_health(
    node: Any,
    link_name: str,
    interface: str,
    peer_ip: str,
    capacity_mbps: float,
    thresholds: HealthThresholds,
    interval_seconds: float = 1.0,
) -> LinkHealth:
    """Measure one routed link without using a high-bandwidth test flow."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        interface_future = executor.submit(
            collect_interface_metrics,
            node,
            interface,
            capacity_mbps,
            interval_seconds,
        )
        probe_future = executor.submit(
            collect_probe_metrics,
            node,
            peer_ip,
        )
        interface_metrics = interface_future.result()
        probe_metrics = probe_future.result()

    score = calculate_health_score(
        HealthMetrics(
            rtt_ms=probe_metrics.average_rtt_ms,
            loss_percent=probe_metrics.packet_loss_percent,
            jitter_ms=probe_metrics.jitter_ms,
            bandwidth_used_mbps=interface_metrics.tx_mbps,
        ),
        thresholds,
    )
    return LinkHealth(
        link_name=link_name,
        interface_metrics=interface_metrics,
        probe_metrics=probe_metrics,
        score=score,
    )


def thresholds_from_healthy_link(
    probe_metrics: ProbeMetrics, capacity_mbps: float
) -> HealthThresholds:
    """Derive conservative per-link thresholds from a healthy probe sample."""
    return HealthThresholds(
        rtt_ms=max(20.0, 3.0 * probe_metrics.average_rtt_ms),
        loss_percent=max(2.0, 3.0 * probe_metrics.packet_loss_percent),
        jitter_ms=max(5.0, 3.0 * probe_metrics.jitter_ms),
        capacity_mbps=capacity_mbps,
    )

