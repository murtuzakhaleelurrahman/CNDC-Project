"""Concurrent collection of a single CampusShield telemetry snapshot."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from telemetry.interface_monitor import collect_interface_metrics
from telemetry.probe_monitor import collect_probe_metrics
from telemetry.qos_monitor import collect_qos_class_metrics
from telemetry.route_monitor import collect_route_metrics


def collect_snapshot(
    nodes: dict[str, Any],
    router_name: str,
    source_host: str,
    interface: str,
    target_ip: str,
    capacity_mbps: float,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Collect interface and probe data concurrently, plus current route state."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        interface_future = executor.submit(
            collect_interface_metrics,
            nodes[router_name],
            interface,
            capacity_mbps,
            interval_seconds,
        )
        probe_future = executor.submit(
            collect_probe_metrics,
            nodes[source_host],
            target_ip,
        )
        interface_metrics = interface_future.result()
        probe_metrics = probe_future.result()

    route_metrics = collect_route_metrics(
        nodes[router_name], target_ip, expected_interface=interface
    )
    qos_classes = collect_qos_class_metrics(nodes[router_name], interface)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "router": router_name,
        "source_host": source_host,
        "interface": asdict(interface_metrics),
        "probe": asdict(probe_metrics),
        "qos_classes": {
            name: asdict(metrics) for name, metrics in qos_classes.items()
        },
        "route": asdict(route_metrics),
    }


def validate_snapshot(
    snapshot: dict[str, Any], expected_interface: str, expected_next_hop: str
) -> tuple[bool, list[str]]:
    """Apply broad sanity checks without inventing performance targets."""
    interface = snapshot["interface"]
    probe = snapshot["probe"]
    route = snapshot["route"]
    checks = {
        "interface transmitted traffic": interface["tx_mbps"] > 1.0,
        "utilization is normalized": 0.0 <= interface["tx_utilization_percent"] <= 110.0,
        "probe received packets": probe["packets_received"] > 0,
        "RTT is positive": probe["average_rtt_ms"] > 0.0,
        "jitter is non-negative": probe["jitter_ms"] >= 0.0,
        "selected interface is correct": route["interface"] == expected_interface,
        "selected next hop is correct": route["next_hop"] == expected_next_hop,
        "selected interface is up": route["interface_state"] == "up",
    }
    failures = [description for description, passed in checks.items() if not passed]
    return not failures, failures

