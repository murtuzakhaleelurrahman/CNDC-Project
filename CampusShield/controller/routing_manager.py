"""Controlled OSPF cost actuation and routing hold-down logic."""

from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from mininet.log import info


VTY_ROOT = Path("/tmp/campusshield-frr")
PRIMARY_LINK_ENDPOINTS = (("r1", "r1-eth0"), ("r2", "r2-eth0"))
PRIMARY_COST = 10
PENALIZED_COST = 100


class RoutingAction(str, Enum):
    NONE = "NONE"
    PENALIZE = "PENALIZE"
    RESTORE = "RESTORE"


@dataclass(frozen=True)
class RoutingDecision:
    action: RoutingAction
    link_health: float
    penalized: bool
    degradation_count: int
    recovery_count: int
    hold_down_remaining: float


class AdaptiveRoutingController:
    """Persistent-degradation detector with recovery hold-down."""

    def __init__(
        self,
        degradation_threshold: float = 50.0,
        recovery_threshold: float = 80.0,
        degradation_confirmations: int = 3,
        recovery_confirmations: int = 3,
        hold_down_seconds: float = 45.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.degradation_threshold = degradation_threshold
        self.recovery_threshold = recovery_threshold
        self.degradation_confirmations = degradation_confirmations
        self.recovery_confirmations = recovery_confirmations
        self.hold_down_seconds = hold_down_seconds
        self.clock = clock
        self.penalized = False
        self.penalized_at: float | None = None
        self.degradation_count = 0
        self.recovery_count = 0

    def observe(
        self, link_health: float, now: float | None = None
    ) -> RoutingDecision:
        current_time = self.clock() if now is None else now

        if not self.penalized:
            if link_health < self.degradation_threshold:
                self.degradation_count += 1
            else:
                self.degradation_count = 0

            if self.degradation_count >= self.degradation_confirmations:
                self.penalized = True
                self.penalized_at = current_time
                self.degradation_count = 0
                return RoutingDecision(
                    RoutingAction.PENALIZE,
                    link_health,
                    True,
                    0,
                    0,
                    self.hold_down_seconds,
                )

            return RoutingDecision(
                RoutingAction.NONE,
                link_health,
                False,
                self.degradation_count,
                0,
                0.0,
            )

        elapsed = current_time - (self.penalized_at or current_time)
        remaining = max(0.0, self.hold_down_seconds - elapsed)
        if remaining > 0:
            self.recovery_count = 0
            return RoutingDecision(
                RoutingAction.NONE,
                link_health,
                True,
                0,
                0,
                remaining,
            )

        if link_health > self.recovery_threshold:
            self.recovery_count += 1
        else:
            self.recovery_count = 0

        if self.recovery_count >= self.recovery_confirmations:
            self.penalized = False
            self.penalized_at = None
            self.recovery_count = 0
            return RoutingDecision(
                RoutingAction.RESTORE,
                link_health,
                False,
                0,
                0,
                0.0,
            )

        return RoutingDecision(
            RoutingAction.NONE,
            link_health,
            True,
            0,
            self.recovery_count,
            0.0,
        )


def _vtysh(node: Any, command_list: list[str]) -> str:
    vty_socket = VTY_ROOT / node.name / "vty"
    commands = " ".join(
        f"-c {shlex.quote(command)}" for command in command_list
    )
    return node.cmd(
        f"vtysh --vty_socket {shlex.quote(str(vty_socket))} "
        f"{commands} 2>&1"
    )


def set_primary_link_cost(nodes: dict[str, Any], cost: int) -> bool:
    """Set the runtime OSPF cost at both ends of the direct R1-R2 link."""
    all_valid = True
    for router_name, interface in PRIMARY_LINK_ENDPOINTS:
        output = _vtysh(
            nodes[router_name],
            ["configure terminal", f"interface {interface}", f"ip ospf cost {cost}"],
        )
        if "%" in output or "failed" in output.lower():
            info(f"FAIL: setting {router_name} {interface} cost {cost}: {output}\n")
            all_valid = False
    return all_valid


def read_primary_link_costs(nodes: dict[str, Any]) -> dict[str, int]:
    costs: dict[str, int] = {}
    for router_name, interface in PRIMARY_LINK_ENDPOINTS:
        output = _vtysh(
            nodes[router_name], [f"show ip ospf interface {interface}"]
        )
        match = re.search(r"Cost:\s*(\d+)", output)
        costs[router_name] = int(match.group(1)) if match else -1
    return costs


def validate_routing_hold_down_logic() -> bool:
    """Verify persistence and the full 45-second hold-down without sleeping."""
    controller = AdaptiveRoutingController()
    checks: list[bool] = []
    checks.append(controller.observe(40, now=0).action is RoutingAction.NONE)
    checks.append(controller.observe(40, now=1).action is RoutingAction.NONE)
    checks.append(controller.observe(40, now=2).action is RoutingAction.PENALIZE)
    checks.append(controller.observe(90, now=20).action is RoutingAction.NONE)
    checks.append(controller.observe(90, now=46).action is RoutingAction.NONE)
    checks.append(controller.observe(90, now=48).action is RoutingAction.NONE)
    checks.append(controller.observe(90, now=49).action is RoutingAction.NONE)
    checks.append(controller.observe(90, now=50).action is RoutingAction.RESTORE)
    return all(checks)

