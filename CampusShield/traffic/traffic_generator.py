"""Controlled iPerf3 traffic profiles for CampusShield.

This module deliberately generates traffic without applying QoS. Phase 5 will
use the DSCP markings defined here to place packets into Linux QoS classes.
"""

from __future__ import annotations

import json
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from mininet.log import info


@dataclass(frozen=True)
class TrafficProfile:
    name: str
    source: str
    destination: str
    destination_ip: str
    port: int
    protocol: str
    dscp_name: str
    dscp_value: int
    rate_mbps: int | None = None

    @property
    def tos_byte(self) -> int:
        """Return the full IPv4 ToS byte expected by iPerf3's -S option."""
        return self.dscp_value << 2


TRAFFIC_PROFILES = (
    TrafficProfile(
        name="emergency",
        source="emergency1",
        destination="admin1",
        destination_ip="10.10.20.10",
        port=5201,
        protocol="UDP",
        dscp_name="EF",
        dscp_value=46,
        rate_mbps=10,
    ),
    TrafficProfile(
        name="academic",
        source="academic1",
        destination="emergency1",
        destination_ip="10.10.10.10",
        port=5202,
        protocol="TCP",
        dscp_name="AF21",
        dscp_value=18,
    ),
    TrafficProfile(
        name="bulk",
        source="hostel1",
        destination="admin1",
        destination_ip="10.10.20.10",
        port=5203,
        protocol="TCP",
        dscp_name="CS1",
        dscp_value=8,
    ),
)


def _start_server(nodes: dict[str, Any], profile: TrafficProfile) -> None:
    """Start a one-client iPerf3 server inside the destination host."""
    destination = nodes[profile.destination]
    command = (
        f"iperf3 -s -1 -D -B {shlex.quote(profile.destination_ip)} "
        f"-p {profile.port}"
    )
    output = destination.cmd(f"{command} 2>&1")
    if output.strip():
        info(f"*** {profile.name} server: {output}")


def _run_client(
    nodes: dict[str, Any], profile: TrafficProfile, duration: int
) -> tuple[TrafficProfile, dict[str, Any]]:
    """Run one marked flow and return its parsed iPerf3 JSON result."""
    protocol_options = ""
    if profile.protocol == "UDP":
        protocol_options = f"-u -b {profile.rate_mbps}M"

    command = (
        f"iperf3 -c {shlex.quote(profile.destination_ip)} "
        f"-p {profile.port} -t {duration} -O 1 {protocol_options} "
        f"-S {profile.tos_byte} -J"
    )
    raw_output = nodes[profile.source].cmd(f"{command} 2>/dev/null")
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        result = {"error": "iPerf3 did not return valid JSON", "raw": raw_output}
    return profile, result


def _extract_metrics(
    profile: TrafficProfile, result: dict[str, Any]
) -> dict[str, float | int | str]:
    """Normalize TCP and UDP JSON into a small common result structure."""
    if "error" in result:
        return {"error": str(result["error"])}

    test_start = result.get("start", {}).get("test_start", {})
    observed_tos = int(test_start.get("tos", -1))
    end = result.get("end", {})

    if profile.protocol == "UDP":
        # Prefer the receiver summary: the sender can continue offering the
        # requested UDP rate even when HTB intentionally drops/excludes it.
        summary = end.get("sum_received") or end.get("sum", {})
    else:
        summary = end.get("sum_received", {})

    metrics: dict[str, float | int | str] = {
        "throughput_mbps": float(summary.get("bits_per_second", 0.0)) / 1_000_000,
        "observed_tos": observed_tos,
    }
    if profile.protocol == "UDP":
        metrics["jitter_ms"] = float(summary.get("jitter_ms", 0.0))
        metrics["loss_percent"] = float(summary.get("lost_percent", 0.0))
    return metrics


def run_traffic_validation(
    nodes: dict[str, Any], duration: int = 4
) -> bool:
    """Generate all three traffic classes concurrently and validate them."""
    info("\n*** Starting controlled emergency, academic, and bulk traffic\n")
    for profile in TRAFFIC_PROFILES:
        _start_server(nodes, profile)
    time.sleep(0.5)

    with ThreadPoolExecutor(max_workers=len(TRAFFIC_PROFILES)) as executor:
        futures = [
            executor.submit(_run_client, nodes, profile, duration)
            for profile in TRAFFIC_PROFILES
        ]
        completed = [future.result() for future in futures]

    all_valid = True
    for profile, result in completed:
        metrics = _extract_metrics(profile, result)
        if "error" in metrics:
            info(f"FAIL: {profile.name} traffic - {metrics['error']}\n")
            all_valid = False
            continue

        throughput = float(metrics["throughput_mbps"])
        observed_tos = int(metrics["observed_tos"])
        marking_valid = observed_tos == profile.tos_byte
        throughput_valid = throughput > 0.5
        valid = marking_valid and throughput_valid

        details = (
            f"{throughput:.2f} Mbps, DSCP {profile.dscp_name} "
            f"({profile.dscp_value})"
        )
        if profile.protocol == "UDP":
            details += (
                f", jitter {float(metrics['jitter_ms']):.3f} ms, "
                f"loss {float(metrics['loss_percent']):.2f}%"
            )

        info(f"{'PASS' if valid else 'FAIL'}: {profile.name} - {details}\n")
        if not marking_valid:
            info(
                f"      expected ToS byte {profile.tos_byte}, "
                f"iPerf3 reported {observed_tos}\n"
            )
        all_valid = all_valid and valid

    if all_valid:
        info("*** TRAFFIC GENERATION TEST PASSED\n")
    else:
        info("*** FAIL: one or more traffic profiles failed\n")
    return all_valid


def run_qos_contention_validation(
    nodes: dict[str, Any], duration: int = 8
) -> tuple[bool, dict[str, float]]:
    """Saturate one egress link with three marked classes and measure shares."""
    info("\n*** Starting same-link QoS contention test on R1-R2\n")
    profiles = (
        TrafficProfile(
            "emergency", "emergency1", "admin1", "10.10.20.10",
            5301, "UDP", "EF", 46, rate_mbps=60,
        ),
        TrafficProfile(
            "academic", "emergency1", "admin1", "10.10.20.10",
            5302, "TCP", "AF21", 18,
        ),
        TrafficProfile(
            "bulk", "emergency1", "admin1", "10.10.20.10",
            5303, "TCP", "CS1", 8,
        ),
    )

    for profile in profiles:
        _start_server(nodes, profile)
    time.sleep(0.5)

    processes = []
    for profile in profiles:
        command = [
            "iperf3", "-c", profile.destination_ip,
            "-p", str(profile.port), "-t", str(duration),
            "-O", "1", "-S", str(profile.tos_byte), "-J",
        ]
        if profile.protocol == "UDP":
            command.extend(["-u", "-b", f"{profile.rate_mbps}M"])
        processes.append((profile, nodes[profile.source].popen(command)))

    measurements: dict[str, float] = {}
    all_valid = True
    for profile, process in processes:
        stdout, _ = process.communicate()
        try:
            result = json.loads(stdout.decode() if isinstance(stdout, bytes) else stdout)
        except (json.JSONDecodeError, AttributeError):
            result = {"error": "iPerf3 did not return valid JSON"}
        metrics = _extract_metrics(profile, result)
        if "error" in metrics:
            info(f"FAIL: {profile.name} contention test - {metrics['error']}\n")
            measurements[profile.name] = 0.0
            all_valid = False
            continue
        throughput = float(metrics.get("throughput_mbps", 0.0))
        measurements[profile.name] = throughput
        marking_valid = int(metrics.get("observed_tos", -1)) == profile.tos_byte
        all_valid = all_valid and throughput > 0.5 and marking_valid
        info(
            f"{'PASS' if throughput > 0.5 and marking_valid else 'FAIL'}: "
            f"{profile.name} contention throughput {throughput:.2f} Mbps\n"
        )

    # Broad ranges make the check robust to WSL scheduling variation while
    # still proving that the configured 20/50/30 policy controls contention.
    expected_ranges = {
        "emergency": (12.0, 28.0),
        "academic": (35.0, 65.0),
        "bulk": (18.0, 42.0),
    }
    allocation_valid = all(
        minimum <= measurements.get(name, 0.0) <= maximum
        for name, (minimum, maximum) in expected_ranges.items()
    )
    info(
        f"{'PASS' if allocation_valid else 'FAIL'}: measured allocation "
        "matches the static 20/50/30 policy\n"
    )
    return all_valid and allocation_valid, measurements


