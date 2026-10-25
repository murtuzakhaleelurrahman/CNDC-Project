#!/usr/bin/env python3
"""CampusShield milestone 1: Mininet + FRRouting OSPF foundation."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import time
from pathlib import Path

from mininet.cli import CLI
from mininet.link import Link, TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSSwitch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRR_ROOT = PROJECT_ROOT / "frr"
RUNTIME_ROOT = Path("/tmp/campusshield-frr")

# The topology is launched as a script from topology/. Add the project root so
# phase modules such as traffic/ can be imported without installing a package.
sys.path.insert(0, str(PROJECT_ROOT))
from controller.qos_manager import (  # noqa: E402
    apply_static_qos,
    qos_class_bytes,
    update_qos_policy,
    validate_qos_policy,
    validate_static_qos,
)
from controller.anre import (  # noqa: E402
    AnreStateMachine,
    validate_hysteresis_logic,
)
from controller.routing_manager import (  # noqa: E402
    AdaptiveRoutingController,
    PENALIZED_COST,
    PRIMARY_COST,
    RoutingAction,
    read_primary_link_costs,
    set_primary_link_cost,
    validate_routing_hold_down_logic,
)
from controller.calibration import calibrate_baseline  # noqa: E402
from controller.health_score import (  # noqa: E402
    calculate_health_score,
    validate_health_score_formula,
)
from traffic.traffic_generator import (  # noqa: E402
    run_qos_contention_validation,
    run_traffic_validation,
)
from telemetry.telemetry_worker import (  # noqa: E402
    collect_snapshot,
    validate_snapshot,
)
from telemetry.link_health import (  # noqa: E402
    collect_link_health,
    thresholds_from_healthy_link,
)
from telemetry.probe_monitor import collect_probe_metrics  # noqa: E402
from security.firewall import (  # noqa: E402
    apply_security_policy,
    validate_security_policy,
)

# Phase 3 core-link emulation. Mininet/TCLink applies these limits in both
# directions using Linux traffic control. Change these values in one place
# when an experiment requires a different core capacity or propagation delay.
CORE_BANDWIDTH_MBPS = 100
CORE_DELAY = "5ms"

# switch, host, host address, gateway, router, router interface
SEGMENTS = (
    ("s10", "emergency1", "10.10.10.10/26", "10.10.10.1", "r1", "r1-eth2"),
    ("s20", "admin1", "10.10.20.10/24", "10.10.20.1", "r2", "r2-eth2"),
    ("s30", "academic1", "10.10.30.10/23", "10.10.30.1", "r2", "r2-eth3"),
    ("s40", "hostel1", "10.10.40.10/22", "10.10.40.1", "r3", "r3-eth2"),
    ("s50", "iot1", "10.10.50.10/25", "10.10.50.1", "r3", "r3-eth3"),
)


class LinuxRouter(Node):
    """A Mininet node that forwards IPv4 packets like a router."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -q -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -q -w net.ipv4.ip_forward=0")
        super().terminate()


def build_network() -> tuple[Mininet, dict[str, Node]]:
    """Create the three-router core and one host per campus segment."""
    net = Mininet(controller=None, switch=OVSSwitch, link=Link, build=False)

    routers = {
        name: net.addHost(name, cls=LinuxRouter, ip=None)
        for name in ("r1", "r2", "r3")
    }

    # Core transit links. Interface names are explicit so FRR configuration is
    # easy to read and does not depend on the order in which links are added.
    net.addLink(
        routers["r1"], routers["r2"],
        intfName1="r1-eth0", params1={"ip": "10.10.255.1/30"},
        intfName2="r2-eth0", params2={"ip": "10.10.255.2/30"},
        cls=TCLink, bw=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY,
    )
    net.addLink(
        routers["r1"], routers["r3"],
        intfName1="r1-eth1", params1={"ip": "10.10.255.5/30"},
        intfName2="r3-eth0", params2={"ip": "10.10.255.6/30"},
        cls=TCLink, bw=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY,
    )
    net.addLink(
        routers["r2"], routers["r3"],
        intfName1="r2-eth1", params1={"ip": "10.10.255.9/30"},
        intfName2="r3-eth1", params2={"ip": "10.10.255.10/30"},
        cls=TCLink, bw=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY,
    )

    # A small access switch and one representative host are sufficient to
    # advertise and test each full campus subnet at this stage.
    hosts: dict[str, Node] = {}
    for switch_name, host_name, host_ip, gateway, router_name, router_intf in SEGMENTS:
        # There is intentionally no SDN controller in CampusShield. Standalone
        # mode makes OVS act as a conventional learning Ethernet switch.
        switch = net.addSwitch(switch_name, failMode="standalone")
        host = net.addHost(host_name, ip=host_ip, defaultRoute=f"via {gateway}")
        net.addLink(host, switch)
        net.addLink(
            routers[router_name], switch,
            intfName1=router_intf,
            params1={"ip": f"{gateway}/{host_ip.split('/')[1]}"},
        )
        hosts[host_name] = host

    net.build()
    net.start()
    return net, {**routers, **hosts}


def router_runtime(router_name: str) -> Path:
    return RUNTIME_ROOT / router_name


def vtysh_command(router: Node, command: str) -> str:
    """Run one FRR command against only this router's daemon sockets."""
    vty_dir = router_runtime(router.name) / "vty"
    return router.cmd(
        f"vtysh --vty_socket {shlex.quote(str(vty_dir))} "
        f"-c {shlex.quote(command)} 2>&1"
    )


def start_frr(router: Node) -> None:
    """Start isolated Zebra and OSPF processes inside a router namespace."""
    name = router.name
    runtime = router_runtime(name)
    vty_dir = runtime / "vty"
    config_dir = FRR_ROOT / name
    zebra_socket = runtime / "zserv.api"

    router.cmd(f"rm -rf {shlex.quote(str(runtime))}")
    router.cmd(f"install -d -o frr -g frr {shlex.quote(str(runtime))}")
    router.cmd(f"install -d -o frr -g frr {shlex.quote(str(vty_dir))}")

    zebra_command = (
        f"/usr/lib/frr/zebra -d "
        f"-f {shlex.quote(str(config_dir / 'zebra.conf'))} "
        f"-i {shlex.quote(str(runtime / 'zebra.pid'))} "
        f"-z {shlex.quote(str(zebra_socket))} "
        f"--vty_socket {shlex.quote(str(vty_dir))} "
        f"--log file:{shlex.quote(str(runtime / 'zebra.log'))}"
    )
    ospf_command = (
        f"/usr/lib/frr/ospfd -d "
        f"-f {shlex.quote(str(config_dir / 'ospfd.conf'))} "
        f"-i {shlex.quote(str(runtime / 'ospfd.pid'))} "
        f"-z {shlex.quote(str(zebra_socket))} "
        f"--vty_socket {shlex.quote(str(vty_dir))} "
        f"--log file:{shlex.quote(str(runtime / 'ospfd.log'))}"
    )

    zebra_output = router.cmd(f"{zebra_command} 2>&1")
    if zebra_output.strip():
        info(f"*** {name} zebra: {zebra_output}")
    time.sleep(0.3)
    ospf_output = router.cmd(f"{ospf_command} 2>&1")
    if ospf_output.strip():
        info(f"*** {name} ospfd: {ospf_output}")


def stop_frr(router: Node) -> None:
    """Stop the router's FRR processes without affecting system FRR."""
    runtime = router_runtime(router.name)
    for daemon in ("ospfd", "zebra"):
        pid_file = runtime / f"{daemon}.pid"
        router.cmd(
            f"if test -f {shlex.quote(str(pid_file))}; then "
            f"kill $(cat {shlex.quote(str(pid_file))}) 2>/dev/null || true; fi"
        )


def wait_for_ospf(routers: list[Node], timeout: int = 20) -> bool:
    """Wait until every router sees the other two routers in FULL state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        states = [vtysh_command(router, "show ip ospf neighbor") for router in routers]
        if all(output.count("Full") >= 2 for output in states):
            return True
        time.sleep(1)
    return False


def print_ospf_status(routers: list[Node]) -> None:
    for router in routers:
        info(f"\n*** {router.name.upper()} OSPF neighbors\n")
        info(vtysh_command(router, "show ip ospf neighbor"))


def route_uses(router: Node, destination: str, expected: str) -> tuple[bool, str]:
    # Force plain output because newer iproute2 releases may add ANSI colors,
    # which makes an otherwise correct route difficult to verify reliably.
    output = router.cmd(
        f"ip -color=never route get {shlex.quote(destination)} 2>&1"
    )
    normalized_output = "\n".join(
        line.rstrip() for line in output.strip().splitlines()
    )
    return expected in normalized_output, normalized_output


def validate_segmentation(nodes: dict[str, Node]) -> bool:
    """Check every campus address, gateway, and locally attached interface."""
    info("\n*** Validating the five campus segments\n")
    all_valid = True

    for _, host_name, host_ip, gateway, router_name, router_intf in SEGMENTS:
        prefix_length = host_ip.split("/")[1]
        expected_router_ip = f"{gateway}/{prefix_length}"
        host_interface = f"{host_name}-eth0"

        actual_host = nodes[host_name].cmd(
            f"ip -color=never -4 -o addr show dev {host_interface}"
        )
        actual_default = nodes[host_name].cmd(
            "ip -color=never route show default"
        )
        actual_router = nodes[router_name].cmd(
            f"ip -color=never -4 -o addr show dev {router_intf}"
        )
        gateway_ping = nodes[host_name].cmd(
            f"ping -c 1 -W 1 {shlex.quote(gateway)}"
        )

        checks = (
            host_ip in actual_host,
            f"default via {gateway}" in actual_default,
            expected_router_ip in actual_router,
            "0% packet loss" in gateway_ping,
        )
        status = "PASS" if all(checks) else "FAIL"
        info(
            f"{status}: {host_name} {host_ip} -> {router_name} "
            f"gateway {expected_router_ip}\n"
        )
        all_valid = all_valid and all(checks)

    if not all_valid:
        info("*** FAIL: one or more campus segment checks failed\n")
    return all_valid


def validate_ospf_campus_routes(nodes: dict[str, Node]) -> bool:
    """Confirm each router learns the campus networks it does not own."""
    info("\n*** Validating learned OSPF campus routes\n")
    expected_routes = {
        "r1": ("10.10.20.0/24", "10.10.30.0/23", "10.10.40.0/22", "10.10.50.0/25"),
        "r2": ("10.10.10.0/26", "10.10.40.0/22", "10.10.50.0/25"),
        "r3": ("10.10.10.0/26", "10.10.20.0/24", "10.10.30.0/23"),
    }

    all_valid = True
    for router_name, prefixes in expected_routes.items():
        for prefix in prefixes:
            route = nodes[router_name].cmd(
                f"ip -color=never route show {shlex.quote(prefix)}"
            ).strip()
            valid = prefix in route and "proto ospf" in route
            status = "PASS" if valid else "FAIL"
            info(f"{status}: {router_name} learned {prefix}\n")
            all_valid = all_valid and valid

    if not all_valid:
        info("*** FAIL: one or more campus routes were not learned through OSPF\n")
    return all_valid


def validate_link_emulation(nodes: dict[str, Node]) -> bool:
    """Verify tc shaping, one-link RTT, and the enforced bandwidth ceiling."""
    info("\n*** Validating core-link bandwidth and delay emulation\n")
    core_interfaces = (
        ("r1", "r1-eth0"),
        ("r2", "r2-eth0"),
        ("r1", "r1-eth1"),
        ("r3", "r3-eth0"),
        ("r2", "r2-eth1"),
        ("r3", "r3-eth1"),
    )

    all_valid = True
    for router_name, interface in core_interfaces:
        qdiscs = nodes[router_name].cmd(
            f"tc qdisc show dev {shlex.quote(interface)}"
        )
        classes = nodes[router_name].cmd(
            f"tc class show dev {shlex.quote(interface)}"
        )
        # TCLink uses HTB for the rate ceiling and netem for propagation delay.
        valid = (
            "htb" in qdiscs
            and "netem" in qdiscs
            and f"{CORE_BANDWIDTH_MBPS}Mbit" in classes
        )
        status = "PASS" if valid else "FAIL"
        info(
            f"{status}: {router_name} {interface} -> "
            f"{CORE_BANDWIDTH_MBPS} Mbps, {CORE_DELAY}\n"
        )
        all_valid = all_valid and valid

    ping_output = nodes["r1"].cmd("ping -c 4 -W 1 10.10.255.2")
    match = re.search(r"= [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms", ping_output)
    average_rtt = float(match.group(1)) if match else -1.0
    # A 5 ms one-way delay on each end of the direct link should produce an
    # RTT near 10 ms. The wider range avoids false failures under host load.
    delay_valid = 8.0 <= average_rtt <= 30.0
    info(
        f"{'PASS' if delay_valid else 'FAIL'}: direct R1-R2 average RTT "
        f"{average_rtt:.3f} ms (expected approximately 10 ms)\n"
    )
    all_valid = all_valid and delay_valid

    # iPerf3 is used here only to validate the emulated ceiling. Controlled
    # campus workload generation is a separate phase.
    nodes["r2"].cmd("iperf3 -s -1 -D -B 10.10.255.2")
    time.sleep(0.5)
    iperf_output = nodes["r1"].cmd(
        "iperf3 -c 10.10.255.2 -t 3 -O 1 -J 2>/dev/null"
    )
    measured_mbps = -1.0
    try:
        result = json.loads(iperf_output)
        measured_mbps = result["end"]["sum_received"]["bits_per_second"] / 1_000_000
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # The measured value should be below the configured ceiling, with a small
    # tolerance for scheduler/accounting variation, and high enough to prove
    # that the link is functioning normally.
    bandwidth_valid = 50.0 <= measured_mbps <= CORE_BANDWIDTH_MBPS * 1.10
    info(
        f"{'PASS' if bandwidth_valid else 'FAIL'}: measured R1-R2 throughput "
        f"{measured_mbps:.2f} Mbps (configured {CORE_BANDWIDTH_MBPS} Mbps)\n"
    )
    all_valid = all_valid and bandwidth_valid

    if not all_valid:
        info("*** FAIL: one or more core-link emulation checks failed\n")
    return all_valid


def run_foundation_test(net: Mininet, nodes: dict[str, Node]) -> bool:
    """Verify adjacency, routes, normal path, and backup-path failover."""
    routers = [nodes["r1"], nodes["r2"], nodes["r3"]]

    info("*** Waiting for all OSPF neighbors to reach FULL state\n")
    if not wait_for_ospf(routers):
        print_ospf_status(routers)
        info("*** FAIL: OSPF did not form all expected adjacencies\n")
        return False
    print_ospf_status(routers)

    if not validate_segmentation(nodes):
        return False
    if not validate_ospf_campus_routes(nodes):
        return False
    if not validate_link_emulation(nodes):
        return False

    info("\n*** Checking the preferred R1-R2 route\n")
    direct_ok, direct_route = route_uses(nodes["r1"], "10.10.20.10", "via 10.10.255.2")
    info(f"R1 route to Admin host: {direct_route}\n")
    if not direct_ok:
        info("*** FAIL: R1 is not using the direct R1-R2 path\n")
        return False

    info("\n*** Checking cross-campus connectivity\n")
    initial_loss = net.ping([
        nodes["emergency1"], nodes["admin1"], nodes["academic1"],
        nodes["hostel1"], nodes["iot1"],
    ])
    if initial_loss != 0:
        info(f"*** FAIL: campus ping test lost {initial_loss}% of packets\n")
        return False

    info("\n*** Disabling R1-R2 to verify the R1-R3-R2 backup path\n")
    net.configLinkStatus("r1", "r2", "down")
    try:
        deadline = time.monotonic() + 15
        forward_ok = False
        reverse_ok = False
        forward_route = "route not available"
        reverse_route = "route not available"
        while time.monotonic() < deadline:
            forward_ok, forward_route = route_uses(
                nodes["r1"], "10.10.20.10", "via 10.10.255.6"
            )
            reverse_ok, reverse_route = route_uses(
                nodes["r2"], "10.10.10.10", "via 10.10.255.10"
            )
            if forward_ok and reverse_ok:
                break
            time.sleep(1)
        info(f"R1 backup route to Admin host: {forward_route}\n")
        info(f"R2 backup route to Emergency host: {reverse_route}\n")
        if not (forward_ok and reverse_ok):
            info("*** FAIL: OSPF did not install both backup directions\n")
            return False

        # A packet already in flight during convergence may legitimately be
        # lost. Wait for the first successful probe, then require a clean
        # three-packet validation once both directions have recovered.
        recovered = False
        while time.monotonic() < deadline:
            probe = nodes["emergency1"].cmd("ping -c 1 -W 1 10.10.20.10")
            if "1 received" in probe or "1 packets received" in probe:
                recovered = True
                break
            time.sleep(0.5)
        if not recovered:
            info("*** FAIL: host traffic did not recover before the timeout\n")
            return False

        result = nodes["emergency1"].cmd("ping -c 3 -W 1 10.10.20.10")
        info(result)
        if "0% packet loss" not in result:
            info("*** FAIL: backup path remained unstable after recovery\n")
            return False
    finally:
        net.configLinkStatus("r1", "r2", "up")

    info("\n*** FOUNDATION AND LINK EMULATION TEST PASSED\n")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--test",
        action="store_true",
        help="run automated OSPF/connectivity/failover checks and exit",
    )
    mode.add_argument(
        "--traffic-test",
        action="store_true",
        help="run foundation checks plus the three traffic profiles and exit",
    )
    mode.add_argument(
        "--qos-test",
        action="store_true",
        help="run foundation checks plus static QoS contention checks and exit",
    )
    mode.add_argument(
        "--telemetry-test",
        action="store_true",
        help="run foundation checks plus a live telemetry snapshot and exit",
    )
    mode.add_argument(
        "--baseline-test",
        action="store_true",
        help="run healthy-network calibration and NHS calculation, then exit",
    )
    mode.add_argument(
        "--anre-test",
        action="store_true",
        help="validate ANRE hysteresis and dynamic QoS state changes, then exit",
    )
    mode.add_argument(
        "--routing-test",
        action="store_true",
        help="validate per-link health, OSPF cost action, and hold-down, then exit",
    )
    mode.add_argument(
        "--security-test",
        action="store_true",
        help="apply and validate the inter-segment firewall policy, then exit",
    )
    parser.add_argument(
        "--enable-qos",
        action="store_true",
        help="apply static QoS before opening the interactive Mininet CLI",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=4,
        help="traffic-test duration in seconds per concurrent flow (default: 4)",
    )
    parser.add_argument(
        "--calibration-duration",
        type=float,
        default=30.0,
        help="baseline calibration duration in seconds (default: 30)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setLogLevel("info")
    net = None
    nodes: dict[str, Node] = {}

    try:
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            info(f"*** Starting FRR on {router.name}\n")
            start_frr(router)

        if (
            args.test
            or args.traffic_test
            or args.qos_test
            or args.telemetry_test
            or args.baseline_test
            or args.anre_test
            or args.routing_test
            or args.security_test
        ):
            foundation_ok = run_foundation_test(net, nodes)
            if not foundation_ok:
                return 1
            if args.traffic_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before traffic test\n")
                    return 1
                if not run_traffic_validation(nodes, duration=max(2, args.duration)):
                    return 1
            if args.qos_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before QoS test\n")
                    return 1
                if not apply_static_qos(
                    nodes, capacity_mbps=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY
                ):
                    return 1
                if not validate_static_qos(nodes):
                    return 1
                qos_ok, _ = run_qos_contention_validation(
                    nodes, duration=max(5, args.duration)
                )
                counters = qos_class_bytes(nodes["r1"], "r1-eth0")
                counters_valid = all(value > 0 for value in counters.values())
                info(
                    f"{'PASS' if counters_valid else 'FAIL'}: R1-R2 QoS class "
                    f"counters {counters}\n"
                )
                if not qos_ok or not counters_valid:
                    return 1
                info("*** STATIC QOS TEST PASSED\n")
            if args.telemetry_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before telemetry test\n")
                    return 1
                info("\n*** Starting a temporary 10 Mbps emergency telemetry flow\n")
                nodes["admin1"].cmd(
                    "iperf3 -s -1 -D -B 10.10.20.10 -p 5401"
                )
                time.sleep(0.5)
                telemetry_flow = nodes["emergency1"].popen(
                    [
                        "iperf3", "-c", "10.10.20.10", "-p", "5401",
                        "-u", "-b", "10M", "-t", "5", "-S", "184",
                    ]
                )
                time.sleep(0.5)
                snapshot = collect_snapshot(
                    nodes=nodes,
                    router_name="r1",
                    source_host="emergency1",
                    interface="r1-eth0",
                    target_ip="10.10.20.10",
                    capacity_mbps=CORE_BANDWIDTH_MBPS,
                    interval_seconds=1.5,
                )
                telemetry_flow.communicate()
                telemetry_ok, failures = validate_snapshot(
                    snapshot,
                    expected_interface="r1-eth0",
                    expected_next_hop="10.10.255.2",
                )
                interface_data = snapshot["interface"]
                probe_data = snapshot["probe"]
                route_data = snapshot["route"]
                info(
                    f"Telemetry TX: {interface_data['tx_mbps']:.2f} Mbps "
                    f"({interface_data['tx_utilization_percent']:.2f}% utilization)\n"
                    f"Telemetry RX: {interface_data['rx_mbps']:.2f} Mbps "
                    f"({interface_data['rx_utilization_percent']:.2f}% utilization)\n"
                    f"Probe RTT: {probe_data['average_rtt_ms']:.3f} ms\n"
                    f"Probe loss: {probe_data['packet_loss_percent']:.2f}%\n"
                    f"Probe jitter estimate: {probe_data['jitter_ms']:.3f} ms\n"
                    f"Route: via {route_data['next_hop']} dev "
                    f"{route_data['interface']} ({route_data['interface_state']})\n"
                )
                if not telemetry_ok:
                    for failure in failures:
                        info(f"FAIL: {failure}\n")
                    return 1
                info("*** TELEMETRY TEST PASSED\n")
            if args.baseline_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before calibration\n")
                    return 1

                calibration_duration = max(3.0, args.calibration_duration)
                info(
                    f"\n*** Calibrating healthy baseline for "
                    f"{calibration_duration:.0f} seconds\n"
                )

                def provide_baseline_snapshot():
                    return collect_snapshot(
                        nodes=nodes,
                        router_name="r1",
                        source_host="emergency1",
                        interface="r1-eth0",
                        target_ip="10.10.20.10",
                        capacity_mbps=CORE_BANDWIDTH_MBPS,
                        interval_seconds=0.75,
                    )

                def show_calibration_progress(sample_number, snapshot):
                    info(
                        f"Sample {sample_number}: "
                        f"RTT={snapshot['probe']['average_rtt_ms']:.3f} ms, "
                        f"loss={snapshot['probe']['packet_loss_percent']:.2f}%, "
                        f"jitter={snapshot['probe']['jitter_ms']:.3f} ms, "
                        f"util={snapshot['interface']['tx_utilization_percent']:.3f}%\n"
                    )

                calibration = calibrate_baseline(
                    snapshot_provider=provide_baseline_snapshot,
                    duration_seconds=calibration_duration,
                    capacity_mbps=CORE_BANDWIDTH_MBPS,
                    progress_callback=show_calibration_progress,
                )
                baseline_score = calculate_health_score(
                    calibration.as_health_metrics(), calibration.thresholds
                )
                formula_ok = validate_health_score_formula()
                calibration_ok = (
                    calibration.sample_count >= 2
                    and calibration.rtt_base_ms > 0
                    and 0 <= baseline_score.nhs <= 100
                    and baseline_score.nhs >= 80
                    and formula_ok
                )
                info(
                    "\n*** Baseline vector\n"
                    f"Samples: {calibration.sample_count}\n"
                    f"RTT_base: {calibration.rtt_base_ms:.3f} ms\n"
                    f"Loss_base: {calibration.loss_base_percent:.3f}%\n"
                    f"Jitter_base: {calibration.jitter_base_ms:.3f} ms\n"
                    f"Utilization_base: "
                    f"{calibration.utilization_base_percent:.3f}%\n"
                    "*** Derived thresholds\n"
                    f"RTT_T: {calibration.thresholds.rtt_ms:.3f} ms\n"
                    f"Loss_T: {calibration.thresholds.loss_percent:.3f}%\n"
                    f"Jitter_T: {calibration.thresholds.jitter_ms:.3f} ms\n"
                    "*** Normalized baseline degradation\n"
                    f"L_n: {baseline_score.latency_normalized:.2f}\n"
                    f"P_n: {baseline_score.loss_normalized:.2f}\n"
                    f"J_n: {baseline_score.jitter_normalized:.2f}\n"
                    f"C_n: {baseline_score.utilization_normalized:.2f}\n"
                    f"Baseline NHS: {baseline_score.nhs:.2f}/100\n"
                    f"Formula boundary check: "
                    f"{'PASS' if formula_ok else 'FAIL'}\n"
                )
                if not calibration_ok:
                    info("*** FAIL: baseline calibration or NHS validation failed\n")
                    return 1
                info("*** BASELINE AND NHS TEST PASSED\n")
            if args.anre_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before ANRE test\n")
                    return 1
                if not apply_static_qos(
                    nodes, capacity_mbps=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY
                ) or not validate_static_qos(nodes):
                    return 1

                logic_ok = validate_hysteresis_logic()
                info(
                    f"{'PASS' if logic_ok else 'FAIL'}: deterministic "
                    "hysteresis boundary test\n"
                )
                if not logic_ok:
                    return 1

                machine = AnreStateMachine()

                anre_calibration_duration = max(3.0, args.calibration_duration)
                info(
                    f"*** ANRE initial calibration for "
                    f"{anre_calibration_duration:.0f} seconds\n"
                )

                def provide_anre_baseline_snapshot():
                    return collect_snapshot(
                        nodes=nodes,
                        router_name="r1",
                        source_host="emergency1",
                        interface="r1-eth0",
                        target_ip="10.10.20.10",
                        capacity_mbps=CORE_BANDWIDTH_MBPS,
                        interval_seconds=0.75,
                    )

                anre_calibration = calibrate_baseline(
                    snapshot_provider=provide_anre_baseline_snapshot,
                    duration_seconds=anre_calibration_duration,
                    capacity_mbps=CORE_BANDWIDTH_MBPS,
                )
                initial_score, initial_decision = machine.evaluate_metrics(
                    anre_calibration.as_health_metrics(),
                    anre_calibration.thresholds,
                )
                initial_ok = (
                    initial_score.nhs >= 80
                    and initial_decision.current_state.value == "NORMAL"
                )
                info(
                    f"{'PASS' if initial_ok else 'FAIL'}: real calibrated "
                    f"NHS={initial_score.nhs:.2f}, "
                    f"initial state={initial_decision.current_state.value}\n"
                )
                if not initial_ok:
                    return 1

                def evaluate_and_act(score_value):
                    decision = machine.evaluate_score(score_value)
                    candidate = (
                        decision.candidate_state.value
                        if decision.candidate_state else "none"
                    )
                    info(
                        f"NHS={score_value:.1f}: state={decision.current_state.value}, "
                        f"candidate={candidate}, confirmations="
                        f"{decision.confirmation_count}/"
                        f"{decision.confirmation_required}\n"
                    )
                    if decision.changed:
                        state_name = decision.current_state.value
                        if not update_qos_policy(nodes, state_name):
                            return False
                        if not validate_qos_policy(nodes, state_name):
                            return False
                    return True

                # Deterministic validation sequence, not experiment data.
                sequence = [
                    65, 65,       # NORMAL -> DEGRADED
                    40, 40,       # DEGRADED -> CRITICAL
                    85, 40,       # reject one noisy recovery sample
                    65, 65, 65, 65, 65,  # CRITICAL -> DEGRADED
                    85, 85, 85, 85, 85,  # DEGRADED -> NORMAL
                ]
                if not all(evaluate_and_act(value) for value in sequence):
                    return 1
                if machine.state.value != "NORMAL":
                    info("*** FAIL: ANRE did not finish in NORMAL state\n")
                    return 1
                info("*** ANRE DYNAMIC QOS TEST PASSED\n")
            if args.routing_test:
                info("*** Waiting for the restored R1-R2 OSPF adjacency\n")
                if not wait_for_ospf(routers):
                    info("*** FAIL: OSPF did not reconverge before routing test\n")
                    return 1

                healthy_probe = collect_probe_metrics(
                    nodes["r1"], "10.10.255.2", count=5
                )
                link_thresholds = thresholds_from_healthy_link(
                    healthy_probe, CORE_BANDWIDTH_MBPS
                )
                link_health = collect_link_health(
                    node=nodes["r1"],
                    link_name="R1-R2",
                    interface="r1-eth0",
                    peer_ip="10.10.255.2",
                    capacity_mbps=CORE_BANDWIDTH_MBPS,
                    thresholds=link_thresholds,
                )
                healthy_link_ok = link_health.score.nhs >= 80
                info(
                    f"{'PASS' if healthy_link_ok else 'FAIL'}: real R1-R2 "
                    f"link health={link_health.score.nhs:.2f}, "
                    f"RTT={link_health.probe_metrics.average_rtt_ms:.3f} ms, "
                    f"loss={link_health.probe_metrics.packet_loss_percent:.2f}%\n"
                )
                if not healthy_link_ok:
                    return 1

                hold_down_ok = validate_routing_hold_down_logic()
                info(
                    f"{'PASS' if hold_down_ok else 'FAIL'}: deterministic "
                    "persistent-degradation and 45-second hold-down test\n"
                )
                if not hold_down_ok:
                    return 1

                routing = AdaptiveRoutingController()
                for timestamp in (0, 1, 2):
                    decision = routing.observe(40, now=timestamp)
                    info(
                        f"Link health=40 at t={timestamp}s: "
                        f"degradation confirmations="
                        f"{decision.degradation_count}/3, "
                        f"action={decision.action.value}\n"
                    )
                if decision.action is not RoutingAction.PENALIZE:
                    return 1
                if not set_primary_link_cost(nodes, PENALIZED_COST):
                    return 1
                time.sleep(2)
                penalized_costs = read_primary_link_costs(nodes)
                deadline = time.monotonic() + 15
                backup_forward = backup_reverse = False
                while time.monotonic() < deadline:
                    backup_forward, _ = route_uses(
                        nodes["r1"], "10.10.20.10", "via 10.10.255.6"
                    )
                    backup_reverse, _ = route_uses(
                        nodes["r2"], "10.10.10.10", "via 10.10.255.10"
                    )
                    if backup_forward and backup_reverse:
                        break
                    time.sleep(1)
                penalty_ok = (
                    penalized_costs == {"r1": 100, "r2": 100}
                    and backup_forward and backup_reverse
                )
                info(
                    f"{'PASS' if penalty_ok else 'FAIL'}: primary costs "
                    f"{penalized_costs}, route moved to R1-R3-R2\n"
                )
                if not penalty_ok:
                    return 1

                early_recovery = routing.observe(90, now=20)
                hold_ok = (
                    early_recovery.action is RoutingAction.NONE
                    and early_recovery.hold_down_remaining > 0
                    and read_primary_link_costs(nodes)
                    == {"r1": 100, "r2": 100}
                )
                info(
                    f"{'PASS' if hold_ok else 'FAIL'}: early recovery blocked; "
                    f"{early_recovery.hold_down_remaining:.0f}s hold-down remains\n"
                )
                if not hold_ok:
                    return 1

                for timestamp in (48, 49, 50):
                    recovery = routing.observe(90, now=timestamp)
                    info(
                        f"Link health=90 at t={timestamp}s: recovery "
                        f"confirmations={recovery.recovery_count}/3, "
                        f"action={recovery.action.value}\n"
                    )
                if recovery.action is not RoutingAction.RESTORE:
                    return 1
                if not set_primary_link_cost(nodes, PRIMARY_COST):
                    return 1
                time.sleep(2)
                restored_costs = read_primary_link_costs(nodes)
                deadline = time.monotonic() + 15
                direct_forward = direct_reverse = False
                while time.monotonic() < deadline:
                    direct_forward, _ = route_uses(
                        nodes["r1"], "10.10.20.10", "via 10.10.255.2"
                    )
                    direct_reverse, _ = route_uses(
                        nodes["r2"], "10.10.10.10", "via 10.10.255.1"
                    )
                    if direct_forward and direct_reverse:
                        break
                    time.sleep(1)
                restore_ok = (
                    restored_costs == {"r1": 10, "r2": 10}
                    and direct_forward and direct_reverse
                )
                info(
                    f"{'PASS' if restore_ok else 'FAIL'}: primary costs "
                    f"{restored_costs}, direct R1-R2 route restored\n"
                )
                if not restore_ok:
                    return 1
                info("*** ADAPTIVE ROUTING TEST PASSED\n")
            if args.security_test:
                info("\n*** Applying CampusShield security-isolation policy\n")
                if not apply_security_policy(nodes):
                    return 1
                if not validate_security_policy(nodes):
                    info("*** SECURITY ISOLATION TEST FAILED\n")
                    return 1
                info("*** SECURITY ISOLATION TEST PASSED\n")
            return 0

        if args.enable_qos:
            if not apply_static_qos(
                nodes, capacity_mbps=CORE_BANDWIDTH_MBPS, delay=CORE_DELAY
            ) or not validate_static_qos(nodes):
                info("*** Static QoS setup failed; not opening the CLI\n")
                return 1

        info("*** Waiting for OSPF convergence before opening the CLI\n")
        if not wait_for_ospf(routers):
            info("*** Warning: OSPF is not fully converged; inspect with vtysh\n")
        print_ospf_status(routers)
        CLI(net)
        return 0
    except KeyboardInterrupt:
        info("\n*** Interrupted by user\n")
        return 130
    finally:
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()


if __name__ == "__main__":
    sys.exit(main())

