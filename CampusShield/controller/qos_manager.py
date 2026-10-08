"""Linux HTB + FQ-CoDel QoS management for CampusShield."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from mininet.log import info


@dataclass(frozen=True)
class QosClass:
    name: str
    class_id: int
    rate_mbps: int
    priority: int
    dscp_value: int

    @property
    def tos_byte(self) -> int:
        return self.dscp_value << 2


NORMAL_QOS_CLASSES = (
    QosClass("emergency", 10, 20, 0, 46),  # EF
    QosClass("academic", 20, 50, 1, 18),   # AF21
    QosClass("bulk", 30, 30, 2, 8),        # CS1
)

QOS_ALLOCATIONS = {
    "NORMAL": {"emergency": 20, "academic": 50, "bulk": 30},
    "DEGRADED": {"emergency": 40, "academic": 45, "bulk": 15},
    "CRITICAL": {"emergency": 55, "academic": 35, "bulk": 10},
}

CORE_INTERFACES = (
    ("r1", "r1-eth0"),
    ("r2", "r2-eth0"),
    ("r1", "r1-eth1"),
    ("r3", "r3-eth0"),
    ("r2", "r2-eth1"),
    ("r3", "r3-eth1"),
)


def _run_tc(node: Any, command: str) -> tuple[bool, str]:
    output = node.cmd(f"tc {command} 2>&1")
    return output.strip() == "", output.strip()


def apply_static_qos(
    nodes: dict[str, Any], capacity_mbps: int = 100, delay: str = "5ms"
) -> bool:
    """Replace TCLink's simple shaper with the static three-class policy."""
    info("\n*** Applying static HTB + FQ-CoDel QoS to core egress interfaces\n")
    all_valid = True

    for router_name, interface in CORE_INTERFACES:
        node = nodes[router_name]
        device = shlex.quote(interface)

        # HTB must classify packets before any shared delay queue; otherwise a
        # high-rate UDP flow can create head-of-line blocking before QoS. Each
        # class therefore gets its own netem delay followed by FQ-CoDel.
        commands = [
            f"qdisc del dev {device} root",
            f"qdisc add dev {device} root handle 10: htb default 30 r2q 1000",
            (
                f"class add dev {device} parent 10: classid 10:1 htb "
                f"rate {capacity_mbps}mbit ceil {capacity_mbps}mbit"
            ),
        ]

        for qos_class in NORMAL_QOS_CLASSES:
            commands.extend(
                [
                    (
                        f"class add dev {device} parent 10:1 "
                        f"classid 10:{qos_class.class_id} htb "
                        f"rate {qos_class.rate_mbps}mbit "
                        f"ceil {qos_class.rate_mbps}mbit "
                        f"prio {qos_class.priority}"
                    ),
                    (
                        f"qdisc add dev {device} parent 10:{qos_class.class_id} "
                        f"handle {qos_class.class_id}0: netem delay {delay}"
                    ),
                    (
                        f"qdisc add dev {device} "
                        f"parent {qos_class.class_id}0:1 "
                        f"handle {qos_class.class_id}1: fq_codel"
                    ),
                    (
                        f"filter add dev {device} parent 10: protocol ip "
                        f"prio {qos_class.priority + 1} u32 "
                        f"match ip dsfield {qos_class.tos_byte:#04x} 0xfc "
                        f"flowid 10:{qos_class.class_id}"
                    ),
                ]
            )

        interface_valid = True
        for command in commands:
            success, output = _run_tc(node, command)
            if not success:
                info(f"FAIL: {router_name} {interface}: tc {command}\n{output}\n")
                interface_valid = False
                break

        info(
            f"{'PASS' if interface_valid else 'FAIL'}: configured QoS on "
            f"{router_name} {interface}\n"
        )
        all_valid = all_valid and interface_valid

    return all_valid


def update_qos_policy(nodes: dict[str, Any], policy_name: str) -> bool:
    """Change only HTB rates, preserving filters and child queue disciplines."""
    policy = QOS_ALLOCATIONS.get(policy_name)
    if policy is None:
        raise ValueError(f"Unknown QoS policy: {policy_name}")

    info(f"*** Applying {policy_name} QoS allocation {policy}\n")
    all_valid = True
    for router_name, interface in CORE_INTERFACES:
        node = nodes[router_name]
        device = shlex.quote(interface)
        for qos_class in NORMAL_QOS_CLASSES:
            rate = policy[qos_class.name]
            command = (
                f"class replace dev {device} parent 10:1 "
                f"classid 10:{qos_class.class_id} htb "
                f"rate {rate}mbit ceil {rate}mbit prio {qos_class.priority}"
            )
            success, output = _run_tc(node, command)
            if not success:
                info(
                    f"FAIL: {router_name} {interface} {qos_class.name}: "
                    f"{output}\n"
                )
                all_valid = False
    return all_valid


def validate_qos_policy(nodes: dict[str, Any], policy_name: str) -> bool:
    """Confirm every core interface has the expected live HTB rates."""
    policy = QOS_ALLOCATIONS.get(policy_name)
    if policy is None:
        raise ValueError(f"Unknown QoS policy: {policy_name}")

    all_valid = True
    for router_name, interface in CORE_INTERFACES:
        classes = nodes[router_name].cmd(
            f"tc class show dev {shlex.quote(interface)}"
        )
        valid = all(
            f"class htb 10:{qos_class.class_id}" in classes
            and f"rate {policy[qos_class.name]}Mbit" in classes
            for qos_class in NORMAL_QOS_CLASSES
        )
        all_valid = all_valid and valid
    info(
        f"{'PASS' if all_valid else 'FAIL'}: all core interfaces use "
        f"the {policy_name} allocation\n"
    )
    return all_valid


def validate_static_qos(nodes: dict[str, Any]) -> bool:
    """Confirm HTB classes, FQ-CoDel leaves, and DSCP filters exist."""
    info("\n*** Validating static QoS structure\n")
    all_valid = True

    for router_name, interface in CORE_INTERFACES:
        node = nodes[router_name]
        device = shlex.quote(interface)
        qdiscs = node.cmd(f"tc qdisc show dev {device}")
        classes = node.cmd(f"tc class show dev {device}")
        filters = node.cmd(f"tc filter show dev {device} parent 10:")

        expected_rates = all(
            f"class htb 10:{item.class_id}" in classes
            and f"rate {item.rate_mbps}Mbit" in classes
            for item in NORMAL_QOS_CLASSES
        )
        expected_filters = all(
            f"flowid 10:{item.class_id}" in filters
            for item in NORMAL_QOS_CLASSES
        )
        valid = (
            "qdisc htb 10: root" in qdiscs
            and qdiscs.count("netem") >= 3
            and qdiscs.count("fq_codel") >= 3
            and expected_rates
            and expected_filters
        )
        info(
            f"{'PASS' if valid else 'FAIL'}: {router_name} {interface} "
            "has HTB 20/50/30, FQ-CoDel, and DSCP filters\n"
        )
        all_valid = all_valid and valid

    return all_valid


def qos_class_bytes(node: Any, interface: str) -> dict[int, int]:
    """Return transmitted byte counters for each configured leaf class."""
    output = node.cmd(f"tc -s class show dev {shlex.quote(interface)}")
    counters: dict[int, int] = {}
    for qos_class in NORMAL_QOS_CLASSES:
        match = re.search(
            rf"class htb 10:{qos_class.class_id}\b.*?Sent (\d+) bytes",
            output,
            flags=re.DOTALL,
        )
        counters[qos_class.class_id] = int(match.group(1)) if match else 0
    return counters

