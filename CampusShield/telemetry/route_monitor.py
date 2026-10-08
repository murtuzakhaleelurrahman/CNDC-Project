"""Route choice and interface operational-state monitoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RouteMetrics:
    destination: str
    next_hop: str
    interface: str
    interface_state: str
    raw_route: str


def collect_route_metrics(
    node: Any, destination: str, expected_interface: str | None = None
) -> RouteMetrics:
    """Read the kernel's selected route and the chosen link's state."""
    route = node.cmd(
        f"ip -color=never route get {destination} 2>/dev/null"
    ).strip()
    interface_match = re.search(r"\bdev\s+(\S+)", route)
    next_hop_match = re.search(r"\bvia\s+(\S+)", route)
    interface = interface_match.group(1) if interface_match else ""
    next_hop = next_hop_match.group(1) if next_hop_match else "direct"

    state_interface = interface or expected_interface or ""
    state = node.cmd(
        f"cat /sys/class/net/{state_interface}/operstate 2>/dev/null"
    ).strip()
    return RouteMetrics(
        destination=destination,
        next_hop=next_hop,
        interface=interface,
        interface_state=state or "unknown",
        raw_route=route,
    )

