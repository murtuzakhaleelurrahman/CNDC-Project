#!/usr/bin/env python3
"""Router firewall policy and live isolation checks for CampusShield."""

from __future__ import annotations

import re
import shlex
import time
from typing import Mapping

from mininet.log import info
from mininet.node import Node


EMERGENCY_NET = "10.10.10.0/26"
ADMIN_NET = "10.10.20.0/24"
ACADEMIC_NET = "10.10.30.0/23"
HOSTEL_NET = "10.10.40.0/22"
IOT_NET = "10.10.50.0/25"
EXTERNAL_TEST_IP = "198.51.100.1"
TABLE = "campusshield"


def _run(node: Node, command: str) -> tuple[bool, str]:
    output = node.cmd(f"{command}; printf '\\n__STATUS__%s' $?")
    body, _, status = output.rpartition("__STATUS__")
    return status.strip() == "0", body.strip()


def _install_table(router: Node, rules: list[str]) -> bool:
    """Install an idempotent, project-owned nftables forward hook."""
    commands = [
        f"nft delete table inet {TABLE} 2>/dev/null || true",
        f"nft add table inet {TABLE}",
        f"nft 'add chain inet {TABLE} forward "
        "{ type filter hook forward priority -10; policy accept; }'",
        f"nft add rule inet {TABLE} forward ct state established,related accept",
        *[f"nft add rule inet {TABLE} forward {rule}" for rule in rules],
    ]
    ok, output = _run(router, " && ".join(commands))
    if not ok:
        info(f"FAIL: could not install firewall policy on {router.name}: {output}\n")
    return ok


def apply_security_policy(nodes: Mapping[str, Node]) -> bool:
    """Apply the proposal's least-privilege inter-segment policy."""
    r2_rules = [
        f"ip saddr {EMERGENCY_NET} ip daddr {ADMIN_NET} accept",
        f"ip saddr {HOSTEL_NET} ip daddr {ADMIN_NET} drop",
        f"ip saddr {ACADEMIC_NET} ip daddr {ADMIN_NET} tcp dport 443 accept",
        f"ip saddr {ACADEMIC_NET} ip daddr {ADMIN_NET} drop",
        f"ip saddr {IOT_NET} ip daddr {ADMIN_NET} tcp dport 8443 accept",
        f"ip saddr {IOT_NET} ip daddr {ADMIN_NET} drop",
    ]
    r3_rules = [
        f"ip saddr {IOT_NET} ip daddr {EXTERNAL_TEST_IP} drop",
    ]
    return _install_table(nodes["r2"], r2_rules) and _install_table(nodes["r3"], r3_rules)


def _ping_succeeds(host: Node, destination: str) -> bool:
    output = host.cmd(f"ping -c 2 -W 1 {shlex.quote(destination)}")
    match = re.search(r"([\d.]+)% packet loss", output)
    return match is not None and float(match.group(1)) == 0.0


def _tcp_connects(host: Node, destination: str, port: int) -> bool:
    ok, _ = _run(host, f"nc -z -w 2 {shlex.quote(destination)} {port}")
    return ok


def _start_tcp_service(host: Node, port: int) -> None:
    host.cmd(f"iperf3 -s -1 -D -p {port}")
    time.sleep(0.2)


def _report(label: str, actual: bool, expected: bool) -> bool:
    passed = actual is expected
    disposition = "allowed" if actual else "blocked"
    info(f"{'PASS' if passed else 'FAIL'}: {label} -> {disposition}\n")
    return passed


def validate_security_policy(nodes: Mapping[str, Node]) -> bool:
    """Exercise every allow, restricted-service, and deny rule with real packets."""
    # A documentation-only TEST-NET address represents an external endpoint.
    # The temporary route makes it reachable in the lab before the IoT egress
    # rule is evaluated; it does not claim to emulate the public Internet.
    nodes["r1"].cmd(f"ip address replace {EXTERNAL_TEST_IP}/32 dev lo")
    nodes["r3"].cmd(
        f"ip route replace {EXTERNAL_TEST_IP}/32 via 10.10.255.6 dev r3-eth0"
    )

    _start_tcp_service(nodes["admin1"], 443)
    academic_https = _tcp_connects(nodes["academic1"], "10.10.20.10", 443)
    _start_tcp_service(nodes["admin1"], 8443)
    iot_monitoring = _tcp_connects(nodes["iot1"], "10.10.20.10", 8443)
    _start_tcp_service(nodes["admin1"], 443)
    iot_https = _tcp_connects(nodes["iot1"], "10.10.20.10", 443)
    # Prove that the denied IoT attempt did not merely encounter a missing
    # listener: the same waiting service must remain reachable from Emergency.
    denied_service_alive = _tcp_connects(nodes["emergency1"], "10.10.20.10", 443)

    checks = [
            _report(
                "Emergency to required Admin service (ICMP)",
                _ping_succeeds(nodes["emergency1"], "10.10.20.10"), True,
            ),
            _report(
                "Hostel to Admin", _ping_succeeds(nodes["hostel1"], "10.10.20.10"), False,
            ),
            _report(
                "Academic to Admin general access",
                _ping_succeeds(nodes["academic1"], "10.10.20.10"), False,
            ),
            _report(
                "Academic to approved Admin HTTPS service",
                academic_https, True,
            ),
            _report(
                "IoT/CCTV to monitoring/NVR service",
                iot_monitoring, True,
            ),
            _report(
                "IoT/CCTV to non-monitoring Admin service",
                iot_https, False,
            ),
            _report(
                "Denied IoT test had a live Admin service",
                denied_service_alive, True,
            ),
            _report(
                "IoT/CCTV to simulated external endpoint",
                _ping_succeeds(nodes["iot1"], EXTERNAL_TEST_IP), False,
            ),
            _report(
                "Admin to IoT/CCTV management direction",
                _ping_succeeds(nodes["admin1"], "10.10.50.10"), True,
            ),
        ]

    rule_dump = nodes["r2"].cmd(f"nft list table inet {TABLE}")
    required_fragments = (
        EMERGENCY_NET, HOSTEL_NET, ACADEMIC_NET, IOT_NET, "tcp dport 443", "tcp dport 8443",
    )
    rules_present = all(fragment in rule_dump for fragment in required_fragments)
    info(f"{'PASS' if rules_present else 'FAIL'}: expected R2 firewall rules installed\n")
    return all(checks) and rules_present
