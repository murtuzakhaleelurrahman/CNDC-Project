#!/usr/bin/env python3
"""Run reproducible CampusShield core experiments and persist real results."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import site
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Mininet is installed by Ubuntu in the system dist-packages directory, while
# plotting libraries live in the CampusShield virtual environment. Adding the
# existing system package directory lets one interpreter use both installations.
SYSTEM_DIST_PACKAGES = Path("/usr/lib/python3/dist-packages")
if SYSTEM_DIST_PACKAGES.is_dir():
    site.addsitedir(str(SYSTEM_DIST_PACKAGES))

from mininet.log import info, setLogLevel  # noqa: E402

from controller.anre import AnreStateMachine  # noqa: E402
from controller.calibration import summarize_baseline_snapshots  # noqa: E402
from controller.health_score import (  # noqa: E402
    HealthMetrics,
    HealthThresholds,
    calculate_health_score,
)
from controller.qos_manager import (  # noqa: E402
    apply_static_qos,
    update_qos_policy,
    validate_qos_policy,
    validate_static_qos,
)
from controller.routing_manager import (  # noqa: E402
    apply_tuned_ospf_profile,
    validate_tuned_ospf_profile,
)
from database.storage import (  # noqa: E402
    DEFAULT_DATABASE_PATH,
    CampusShieldDatabase,
    EventRecord,
    TelemetryRecord,
)
from experiments.congestion_design import (  # noqa: E402
    SCENARIOS,
    TrafficPhase,
    build_phase_plan,
    initial_policy_for_scenario,
    queue_counter_delta,
    scenario_order_for_repetition,
)
from experiments.statistics_utils import describe_95  # noqa: E402
from experiments.ospf_design import (  # noqa: E402
    SCENARIOS as OSPF_SCENARIOS,
    TUNED_DEAD_INTERVAL_SECONDS,
    TUNED_HELLO_MULTIPLIER,
    TUNED_SPF_DELAY_MS,
    TUNED_SPF_INITIAL_HOLD_MS,
    TUNED_SPF_MAX_HOLD_MS,
    h7_supported,
    recovery_improvement_percent,
    scenario_order_for_repetition as ospf_scenario_order,
)
from telemetry.telemetry_worker import collect_snapshot  # noqa: E402
from topology.campus_topology import (  # noqa: E402
    CORE_BANDWIDTH_MBPS,
    build_network,
    route_uses,
    start_frr,
    stop_frr,
    vtysh_command,
    wait_for_ospf,
)


RESULTS_ROOT = PROJECT_ROOT / "results"
EXPERIMENT_LOCK_PATH = Path("/tmp/campusshield-experiment.lock")


def acquire_experiment_lock():
    """Prevent two experiment runners from sharing Mininet namespaces."""
    lock_file = EXPERIMENT_LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_file.close()
        raise RuntimeError(
            "Another CampusShield experiment is already running. "
            "Wait for it to finish before starting a new one."
        ) from error
    lock_file.write(f"{os.getpid()}\n")
    lock_file.flush()
    return lock_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="experiment", required=True)
    baseline = subcommands.add_parser(
        "baseline", help="run Experiment 1 under a controlled low load"
    )
    baseline.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="measurement duration in seconds (default: 30)",
    )
    baseline.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path",
    )
    congestion = subcommands.add_parser(
        "congestion", help="compare the same congestion with ANRE OFF and ON"
    )
    congestion.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="congested phase duration per scenario in seconds (default: 30)",
    )
    congestion.add_argument(
        "--healthy-duration",
        type=float,
        default=10.0,
        help="healthy pre-congestion phase in seconds (default: 10)",
    )
    congestion.add_argument(
        "--recovery-duration",
        type=float,
        default=20.0,
        help="post-congestion recovery phase in seconds (default: 20)",
    )
    congestion.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="matched three-arm repetitions (default: 10)",
    )
    congestion.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path",
    )
    failure = subcommands.add_parser(
        "failure", help="measure physical R1-R2 failure and OSPF recovery"
    )
    failure.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="fresh-topology repetitions (default: 10)",
    )
    failure.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="maximum seconds to wait for each route change (default: 20)",
    )
    failure.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path",
    )
    ospf = subcommands.add_parser(
        "ospf", help="compare default and tuned OSPF recovery under silent failure"
    )
    ospf.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="matched, order-rotated repetitions per profile (default: 10)",
    )
    ospf.add_argument(
        "--timeout",
        type=float,
        default=55.0,
        help="maximum seconds to wait for each route change (default: 55)",
    )
    ospf.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path",
    )
    return parser.parse_args()


def _queue_evidence_fields(snapshot: dict[str, Any]) -> dict[str, int]:
    """Flatten per-class queue evidence for human-readable experiment CSVs."""
    fields: dict[str, int] = {
        "probe_dscp_value": int(snapshot["probe"].get("dscp_value", 0)),
    }
    for class_name in ("emergency", "academic", "bulk"):
        stats = snapshot.get("qos_classes", {}).get(class_name, {})
        for metric in (
            "sent_bytes",
            "sent_packets",
            "dropped_packets",
            "overlimits",
            "backlog_bytes",
            "backlog_packets",
        ):
            fields[f"{class_name}_{metric}"] = int(stats.get(metric, 0))
    return fields


def _parse_udp_result(raw_output: str) -> dict[str, float]:
    try:
        result = json.loads(raw_output)
        summary = result.get("end", {}).get("sum_received") or result.get(
            "end", {}
        ).get("sum", {})
        return {
            "throughput_mbps": float(summary["bits_per_second"]) / 1_000_000,
            "jitter_ms": float(summary.get("jitter_ms", 0.0)),
            "packet_loss_percent": float(summary.get("lost_percent", 0.0)),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Could not parse the baseline iPerf3 result") from error


def _parse_flow_result(raw_output: str, protocol: str) -> dict[str, float]:
    try:
        result = json.loads(raw_output)
        end = result.get("end", {})
        summary = end.get("sum_received") or end.get("sum", {})
        metrics = {
            "throughput_mbps": float(summary["bits_per_second"]) / 1_000_000,
        }
        if protocol == "UDP":
            metrics["jitter_ms"] = float(summary.get("jitter_ms", 0.0))
            metrics["packet_loss_percent"] = float(
                summary.get("lost_percent", 0.0)
            )
        return metrics
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"Could not parse the {protocol} iPerf3 result") from error


def _latest_baseline_thresholds(
    database_path: Path,
) -> tuple[int, HealthThresholds]:
    with CampusShieldDatabase(database_path) as database:
        run = database.connection.execute(
            """
            SELECT id FROM experiment_runs
            WHERE run_type = 'BASELINE' AND is_experimental = 1
              AND status = 'COMPLETED'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if run is None:
            raise RuntimeError("Run Experiment 1 before the congestion comparison")
        values = {
            row["metric_name"]: float(row["metric_value"])
            for row in database.connection.execute(
                """
                SELECT metric_name, metric_value FROM experiment_results
                WHERE run_id = ? AND metric_name IN (
                    'rtt_threshold_ms', 'loss_threshold_percent',
                    'jitter_threshold_ms'
                )
                """,
                (run["id"],),
            )
        }
    required = {
        "rtt_threshold_ms", "loss_threshold_percent", "jitter_threshold_ms"
    }
    if required - values.keys():
        raise RuntimeError("The latest baseline is missing calibrated thresholds")
    return int(run["id"]), HealthThresholds(
        rtt_ms=values["rtt_threshold_ms"],
        loss_percent=values["loss_threshold_percent"],
        jitter_ms=values["jitter_threshold_ms"],
        capacity_mbps=CORE_BANDWIDTH_MBPS,
    )


def _save_baseline_artifacts(
    run_id: int,
    rows: list[dict[str, Any]],
) -> tuple[Path, Path]:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_ROOT / f"baseline_run_{run_id}.csv"
    graph_path = RESULTS_ROOT / f"baseline_run_{run_id}.png"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False)

    timestamps = pd.to_datetime(frame["timestamp_utc"], utc=True)
    elapsed = (timestamps - timestamps.iloc[0]).dt.total_seconds()
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    figure.suptitle(f"CampusShield Experiment 1 - Baseline Run {run_id}")
    axes[0, 0].plot(elapsed, frame["rtt_ms"], color="#0f766e")
    axes[0, 0].set(title="RTT", ylabel="Milliseconds")
    axes[0, 1].plot(elapsed, frame["jitter_ms"], color="#2563eb")
    axes[0, 1].set(title="Jitter", ylabel="Milliseconds")
    axes[1, 0].plot(elapsed, frame["utilization_percent"], color="#d97706")
    axes[1, 0].set(title="R1-R2 utilization", ylabel="Percent", xlabel="Seconds")
    axes[1, 1].plot(elapsed, frame["nhs"], color="#15803d")
    axes[1, 1].set(title="Network Health Score", ylabel="NHS", xlabel="Seconds")
    axes[1, 1].set_ylim(0, 100)
    for axis in axes.flat:
        axis.grid(alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)
    return csv_path, graph_path


def run_baseline(duration_seconds: float, database_path: Path) -> bool:
    if duration_seconds < 3:
        raise ValueError("Baseline duration must be at least 3 seconds")
    if os.geteuid() != 0:
        raise PermissionError("Mininet experiments must be run with sudo")

    net = None
    nodes: dict[str, Any] = {}
    database: CampusShieldDatabase | None = None
    run_id: int | None = None
    try:
        database = CampusShieldDatabase(database_path)
        run_id = database.start_run(
            "Experiment 1 - Baseline calibration",
            "BASELINE",
            is_experimental=True,
            notes=(
                "Real measurements under a controlled 10 Mbps emergency UDP "
                "flow on the 100 Mbps R1-R2 primary path."
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="EXPERIMENT_START",
                message="Baseline calibration started",
                metadata={"duration_seconds": duration_seconds},
            ),
        )

        info("*** Building the CampusShield baseline topology\n")
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            start_frr(router)
        info("*** Waiting for all OSPF neighbors to reach FULL state\n")
        if not wait_for_ospf(routers):
            raise RuntimeError("OSPF did not converge before the baseline experiment")
        database.log_event(
            run_id,
            EventRecord(
                component="OSPF",
                event_type="OSPF_FULL",
                message="All router adjacencies reached FULL state",
            ),
        )

        # A 10 Mbps EF-marked flow uses only 10% of the enforced core link and
        # provides a real, measurable baseline throughput without congestion.
        nodes["admin1"].cmd("iperf3 -s -1 -D -B 10.10.20.10 -p 6101")
        time.sleep(0.5)
        flow = nodes["emergency1"].popen(
            [
                "iperf3", "-c", "10.10.20.10", "-p", "6101", "-u",
                "-b", "10M", "-t", str(int(duration_seconds) + 2),
                "-O", "1", "-S", "184", "-J",
            ]
        )
        time.sleep(0.5)

        snapshots: list[dict[str, Any]] = []
        started = time.monotonic()
        while time.monotonic() - started < duration_seconds:
            snapshot = collect_snapshot(
                nodes=nodes,
                router_name="r1",
                source_host="emergency1",
                interface="r1-eth0",
                target_ip="10.10.20.10",
                capacity_mbps=CORE_BANDWIDTH_MBPS,
                interval_seconds=0.75,
            )
            snapshots.append(snapshot)
            info(
                f"Sample {len(snapshots)}: "
                f"RTT={snapshot['probe']['average_rtt_ms']:.3f} ms, "
                f"loss={snapshot['probe']['packet_loss_percent']:.2f}%, "
                f"jitter={snapshot['probe']['jitter_ms']:.3f} ms, "
                f"util={snapshot['interface']['tx_utilization_percent']:.2f}%\n"
            )
        elapsed = time.monotonic() - started
        stdout, _ = flow.communicate()
        raw_output = stdout.decode() if isinstance(stdout, bytes) else stdout
        flow_metrics = _parse_udp_result(raw_output)

        calibration = summarize_baseline_snapshots(
            snapshots,
            duration_seconds=elapsed,
            capacity_mbps=CORE_BANDWIDTH_MBPS,
        )
        artifact_rows: list[dict[str, Any]] = []
        scores = []
        for snapshot in snapshots:
            metrics = HealthMetrics(
                rtt_ms=snapshot["probe"]["average_rtt_ms"],
                loss_percent=snapshot["probe"]["packet_loss_percent"],
                jitter_ms=snapshot["probe"]["jitter_ms"],
                bandwidth_used_mbps=snapshot["interface"]["tx_mbps"],
            )
            score = calculate_health_score(metrics, calibration.thresholds)
            scores.append(score.nhs)
            record = TelemetryRecord.from_snapshot(
                snapshot,
                nhs=score.nhs,
                anre_state="NORMAL",
                link_name="R1-R2",
                link_health=score.nhs,
                qos_policy="BASELINE_LOW_LOAD",
            )
            database.log_telemetry(run_id, record)
            artifact_rows.append(
                {
                    "timestamp_utc": record.timestamp_utc,
                    "rtt_ms": record.rtt_ms,
                    "packet_loss_percent": record.packet_loss_percent,
                    "jitter_ms": record.jitter_ms,
                    "tx_mbps": record.tx_mbps,
                    "rx_mbps": record.rx_mbps,
                    "utilization_percent": record.utilization_percent,
                    "nhs": record.nhs,
                    "route_next_hop": record.route_next_hop,
                    "route_interface": record.route_interface,
                    **_queue_evidence_fields(snapshot),
                }
            )

        mean_nhs = sum(scores) / len(scores)
        result_values = {
            "rtt_ms": (calibration.rtt_base_ms, "ms"),
            "packet_loss_percent": (calibration.loss_base_percent, "percent"),
            "jitter_ms": (calibration.jitter_base_ms, "ms"),
            "utilization_percent": (
                calibration.utilization_base_percent,
                "percent",
            ),
            "emergency_throughput_mbps": (
                flow_metrics["throughput_mbps"],
                "Mbps",
            ),
            "iperf_udp_jitter_ms": (flow_metrics["jitter_ms"], "ms"),
            "iperf_udp_loss_percent": (
                flow_metrics["packet_loss_percent"],
                "percent",
            ),
            "mean_nhs": (mean_nhs, "score"),
            "rtt_threshold_ms": (calibration.thresholds.rtt_ms, "ms"),
            "loss_threshold_percent": (
                calibration.thresholds.loss_percent,
                "percent",
            ),
            "jitter_threshold_ms": (
                calibration.thresholds.jitter_ms,
                "ms",
            ),
        }
        for metric_name, (metric_value, unit) in result_values.items():
            database.log_result(
                run_id,
                scenario="CONTROLLED_LOW_LOAD",
                traffic_class=(
                    "emergency" if metric_name.startswith(("emergency", "iperf"))
                    else None
                ),
                metric_name=metric_name,
                metric_value=metric_value,
                unit=unit,
            )

        csv_path, graph_path = _save_baseline_artifacts(run_id, artifact_rows)
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="BASELINE_COMPLETE",
                message="Baseline measurements and artifacts saved",
                metadata={
                    "sample_count": len(snapshots),
                    "csv": str(csv_path),
                    "graph": str(graph_path),
                },
            ),
        )
        database.finish_run(run_id, "COMPLETED")

        info("\n*** Experiment 1 measured summary\n")
        info(f"Run ID: {run_id}\n")
        info(f"Samples: {len(snapshots)} over {elapsed:.2f} seconds\n")
        info(f"Mean RTT: {calibration.rtt_base_ms:.3f} ms\n")
        info(f"Mean packet loss: {calibration.loss_base_percent:.3f}%\n")
        info(f"Mean jitter: {calibration.jitter_base_ms:.3f} ms\n")
        info(f"Mean utilization: {calibration.utilization_base_percent:.3f}%\n")
        info(f"Emergency throughput: {flow_metrics['throughput_mbps']:.3f} Mbps\n")
        info(f"Mean NHS: {mean_nhs:.2f}/100\n")
        info(f"CSV: {csv_path}\n")
        info(f"Graph: {graph_path}\n")
        info("*** BASELINE EXPERIMENT PASSED\n")
        return True
    except Exception as error:
        info(f"*** BASELINE EXPERIMENT FAILED: {error}\n")
        if database is not None and run_id is not None:
            try:
                database.log_event(
                    run_id,
                    EventRecord(
                        component="EXPERIMENT",
                        event_type="EXPERIMENT_FAILURE",
                        severity="ERROR",
                        message=str(error),
                    ),
                )
                database.finish_run(run_id, "FAILED")
            except Exception:
                pass
        return False
    finally:
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()
        if database is not None:
            database.close()


def _start_phase_flows(
    nodes: dict[str, Any], phase: TrafficPhase
) -> list[tuple[str, str, Any]]:
    port_base = {"HEALTHY": 6200, "CONGESTION": 6300, "RECOVERY": 6400}[
        phase.name
    ]
    profiles = [("emergency", "UDP", port_base + 1, 184)]
    if phase.competing_tcp:
        profiles.extend(
            [
                ("academic", "TCP", port_base + 2, 72),
                ("bulk", "TCP", port_base + 3, 32),
            ]
        )
    for _, _, port, _ in profiles:
        nodes["admin1"].cmd(
            f"iperf3 -s -1 -D -B 10.10.20.10 -p {port}"
        )
    time.sleep(0.5)

    processes = []
    flow_duration = str(max(3, int(phase.duration_seconds) + 1))
    for name, protocol, port, tos_byte in profiles:
        command = [
            "iperf3", "-c", "10.10.20.10", "-p", str(port),
            "-t", flow_duration, "-O", "1", "-S", str(tos_byte), "-J",
        ]
        if protocol == "UDP":
            command.extend(["-u", "-b", f"{phase.emergency_udp_mbps}M"])
        processes.append((name, protocol, nodes["emergency1"].popen(command)))
    return processes


def _finish_phase_flows(
    processes: list[tuple[str, str, Any]],
) -> dict[str, dict[str, float]]:
    measurements: dict[str, dict[str, float]] = {}
    for name, protocol, process in processes:
        stdout, _ = process.communicate()
        raw_output = stdout.decode() if isinstance(stdout, bytes) else stdout
        measurements[name] = _parse_flow_result(raw_output, protocol)
    return measurements


def _run_congestion_scenario(
    *,
    database_path: Path,
    thresholds: HealthThresholds,
    baseline_run_id: int,
    group_id: str,
    repetition: int,
    scenario: str,
    phase_plan: tuple[TrafficPhase, ...],
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown congestion scenario: {scenario}")
    anre_enabled = scenario == "ANRE_ON"
    net = None
    nodes: dict[str, Any] = {}
    database: CampusShieldDatabase | None = None
    run_id: int | None = None
    processes: list[tuple[str, str, Any]] = []
    try:
        database = CampusShieldDatabase(database_path)
        run_id = database.start_run(
            f"Experiment 2 - {scenario} - repetition {repetition}",
            f"CONGESTION_{scenario}",
            is_experimental=True,
            notes=(
                f"comparison_group={group_id}; repetition={repetition}; "
                f"baseline_run_id={baseline_run_id}; three_phase_workload="
                "healthy, congestion, recovery; congestion workload="
                "60 Mbps emergency UDP plus academic and bulk TCP"
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="EXPERIMENT_START",
                message=f"Congestion scenario {scenario} started",
                metadata={
                    "comparison_group": group_id,
                    "repetition": repetition,
                    "phase_durations": {
                        phase.name: phase.duration_seconds for phase in phase_plan
                    },
                    "baseline_run_id": baseline_run_id,
                },
            ),
        )

        info(f"\n*** Building fresh topology for {scenario} repetition {repetition}\n")
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            start_frr(router)
        if not wait_for_ospf(routers):
            raise RuntimeError("OSPF did not converge before congestion testing")
        if not apply_static_qos(nodes, CORE_BANDWIDTH_MBPS, "5ms"):
            raise RuntimeError("Could not apply the initial NORMAL QoS policy")
        if not validate_static_qos(nodes):
            raise RuntimeError("The initial QoS policy did not validate")

        machine = AnreStateMachine()
        current_policy = initial_policy_for_scenario(scenario)
        if current_policy != "NORMAL":
            if not update_qos_policy(nodes, current_policy):
                raise RuntimeError(
                    f"Could not apply the {scenario} fixed QoS policy"
                )
            if not validate_qos_policy(nodes, current_policy):
                raise RuntimeError(
                    f"The {scenario} fixed QoS policy did not validate"
                )
        controller_response_seconds: float | None = None
        recovery_to_normal_seconds: float | None = None
        rows: list[dict[str, Any]] = []
        phase_flow_metrics: dict[str, dict[str, dict[str, float]]] = {}
        scenario_started = time.monotonic()
        congestion_started: float | None = None
        recovery_started: float | None = None

        for phase in phase_plan:
            phase_started = time.monotonic()
            if phase.name == "CONGESTION":
                congestion_started = phase_started
            elif phase.name == "RECOVERY":
                recovery_started = phase_started
            database.log_event(
                run_id,
                EventRecord(
                    component="EXPERIMENT",
                    event_type="TRAFFIC_PHASE_START",
                    message=f"{scenario} entered {phase.name.lower()} phase",
                    metadata={
                        "phase": phase.name,
                        "duration_seconds": phase.duration_seconds,
                        "emergency_udp_mbps": phase.emergency_udp_mbps,
                        "competing_tcp": phase.competing_tcp,
                    },
                ),
            )
            processes = _start_phase_flows(nodes, phase)
            time.sleep(0.5)

            while time.monotonic() - phase_started < phase.duration_seconds:
                snapshot = collect_snapshot(
                    nodes=nodes,
                    router_name="r1",
                    source_host="emergency1",
                    interface="r1-eth0",
                    target_ip="10.10.20.10",
                    capacity_mbps=CORE_BANDWIDTH_MBPS,
                    interval_seconds=0.75,
                )
                metrics = HealthMetrics(
                    rtt_ms=snapshot["probe"]["average_rtt_ms"],
                    loss_percent=snapshot["probe"]["packet_loss_percent"],
                    jitter_ms=snapshot["probe"]["jitter_ms"],
                    bandwidth_used_mbps=snapshot["interface"]["tx_mbps"],
                )
                score = calculate_health_score(metrics, thresholds)
                state_name = "DISABLED"
                if anre_enabled:
                    decision = machine.evaluate_score(score.nhs)
                    state_name = decision.current_state.value
                    if decision.changed:
                        current_policy = state_name
                        if not update_qos_policy(nodes, current_policy):
                            raise RuntimeError(
                                f"Could not apply {current_policy} QoS policy"
                            )
                        if not validate_qos_policy(nodes, current_policy):
                            raise RuntimeError(
                                f"The {current_policy} QoS policy did not validate"
                            )
                        now = time.monotonic()
                        response: float | None = None
                        if (
                            phase.name == "CONGESTION"
                            and controller_response_seconds is None
                            and decision.current_state.value != "NORMAL"
                            and congestion_started is not None
                        ):
                            controller_response_seconds = now - congestion_started
                            response = controller_response_seconds
                        if (
                            phase.name == "RECOVERY"
                            and decision.current_state.value == "NORMAL"
                            and recovery_to_normal_seconds is None
                            and recovery_started is not None
                        ):
                            recovery_to_normal_seconds = now - recovery_started
                        database.log_event(
                            run_id,
                            EventRecord(
                                component="ANRE",
                                event_type="STATE_TRANSITION",
                                message=(
                                    f"ANRE changed {decision.previous_state.value} "
                                    f"to {decision.current_state.value} during "
                                    f"{phase.name.lower()}"
                                ),
                                previous_state=decision.previous_state.value,
                                current_state=decision.current_state.value,
                                action="APPLY_QOS",
                                old_value=decision.previous_state.value,
                                new_value=current_policy,
                                metadata={
                                    "phase": phase.name,
                                    "response_seconds": response,
                                    "nhs": score.nhs,
                                },
                            ),
                        )

                record = TelemetryRecord.from_snapshot(
                    snapshot,
                    nhs=score.nhs,
                    anre_state=state_name,
                    link_name="R1-R2",
                    link_health=score.nhs,
                    qos_policy=current_policy,
                )
                database.log_telemetry(run_id, record)
                row = {
                    "elapsed_seconds": time.monotonic() - scenario_started,
                    "phase_elapsed_seconds": time.monotonic() - phase_started,
                    "phase": phase.name,
                    "timestamp_utc": record.timestamp_utc,
                    "scenario": scenario,
                    "repetition": repetition,
                    "rtt_ms": record.rtt_ms,
                    "packet_loss_percent": record.packet_loss_percent,
                    "jitter_ms": record.jitter_ms,
                    "tx_mbps": record.tx_mbps,
                    "utilization_percent": record.utilization_percent,
                    "nhs": record.nhs,
                    "anre_state": record.anre_state,
                    "qos_policy": record.qos_policy,
                    **_queue_evidence_fields(snapshot),
                }
                rows.append(row)
                info(
                    f"{scenario} {phase.name} sample {len(rows)}: "
                    f"NHS={score.nhs:.2f}, state={state_name}, "
                    f"policy={current_policy}, RTT={record.rtt_ms:.2f} ms, "
                    f"util={record.utilization_percent:.1f}%\n"
                )

            phase_flow_metrics[phase.name] = _finish_phase_flows(processes)
            processes = []
            database.log_event(
                run_id,
                EventRecord(
                    component="EXPERIMENT",
                    event_type="TRAFFIC_PHASE_COMPLETE",
                    message=f"{scenario} completed {phase.name.lower()} phase",
                    metadata={"phase": phase.name},
                ),
            )

        congestion_rows = [row for row in rows if row["phase"] == "CONGESTION"]
        healthy_rows = [row for row in rows if row["phase"] == "HEALTHY"]
        recovery_rows = [row for row in rows if row["phase"] == "RECOVERY"]
        if not congestion_rows or not healthy_rows or not recovery_rows:
            raise RuntimeError("One or more traffic phases produced no telemetry")

        def phase_mean(phase_rows: list[dict[str, Any]], field: str) -> float:
            return sum(float(row[field]) for row in phase_rows) / len(phase_rows)

        flow_metrics = phase_flow_metrics["CONGESTION"]
        final_state = machine.state.value if anre_enabled else "DISABLED"
        summary: dict[str, Any] = {
            "group_id": group_id,
            "repetition": repetition,
            "scenario": scenario,
            "run_id": run_id,
            "sample_count": len(rows),
            "healthy_sample_count": len(healthy_rows),
            "congestion_sample_count": len(congestion_rows),
            "recovery_sample_count": len(recovery_rows),
            "mean_rtt_ms": phase_mean(congestion_rows, "rtt_ms"),
            "mean_probe_loss_percent": phase_mean(
                congestion_rows, "packet_loss_percent"
            ),
            "mean_probe_jitter_ms": phase_mean(congestion_rows, "jitter_ms"),
            "mean_utilization_percent": phase_mean(
                congestion_rows, "utilization_percent"
            ),
            "mean_nhs": phase_mean(congestion_rows, "nhs"),
            "healthy_mean_nhs": phase_mean(healthy_rows, "nhs"),
            "recovery_mean_nhs": phase_mean(recovery_rows, "nhs"),
            "recovery_nhs_change": (
                phase_mean(recovery_rows, "nhs")
                - phase_mean(congestion_rows, "nhs")
            ),
            "emergency_throughput_mbps": flow_metrics["emergency"]["throughput_mbps"],
            "emergency_udp_loss_percent": flow_metrics["emergency"]["packet_loss_percent"],
            "emergency_udp_jitter_ms": flow_metrics["emergency"]["jitter_ms"],
            "academic_throughput_mbps": flow_metrics["academic"]["throughput_mbps"],
            "bulk_throughput_mbps": flow_metrics["bulk"]["throughput_mbps"],
            "controller_response_seconds": controller_response_seconds,
            "recovery_to_normal_seconds": recovery_to_normal_seconds,
            "emergency_queue_drops_congestion": queue_counter_delta(
                congestion_rows, "emergency_dropped_packets"
            ),
            "academic_queue_drops_congestion": queue_counter_delta(
                congestion_rows, "academic_dropped_packets"
            ),
            "bulk_queue_drops_congestion": queue_counter_delta(
                congestion_rows, "bulk_dropped_packets"
            ),
            "peak_emergency_backlog_bytes": max(
                int(row["emergency_backlog_bytes"]) for row in congestion_rows
            ),
            "healthy_emergency_throughput_mbps": phase_flow_metrics["HEALTHY"][
                "emergency"
            ]["throughput_mbps"],
            "recovery_emergency_throughput_mbps": phase_flow_metrics["RECOVERY"][
                "emergency"
            ]["throughput_mbps"],
            "final_anre_state": final_state,
            "final_policy": current_policy,
        }

        result_units = {
            "mean_rtt_ms": "ms",
            "mean_probe_loss_percent": "percent",
            "mean_probe_jitter_ms": "ms",
            "mean_utilization_percent": "percent",
            "mean_nhs": "score",
            "healthy_mean_nhs": "score",
            "recovery_mean_nhs": "score",
            "recovery_nhs_change": "score",
            "emergency_throughput_mbps": "Mbps",
            "emergency_udp_loss_percent": "percent",
            "emergency_udp_jitter_ms": "ms",
            "academic_throughput_mbps": "Mbps",
            "bulk_throughput_mbps": "Mbps",
            "controller_response_seconds": "seconds",
            "recovery_to_normal_seconds": "seconds",
            "emergency_queue_drops_congestion": "packets",
            "academic_queue_drops_congestion": "packets",
            "bulk_queue_drops_congestion": "packets",
            "peak_emergency_backlog_bytes": "bytes",
            "healthy_emergency_throughput_mbps": "Mbps",
            "recovery_emergency_throughput_mbps": "Mbps",
        }
        for metric_name, unit in result_units.items():
            value = summary[metric_name]
            if value is None:
                continue
            traffic_class = None
            if metric_name.startswith("emergency"):
                traffic_class = "emergency"
            elif metric_name.startswith("academic"):
                traffic_class = "academic"
            elif metric_name.startswith("bulk"):
                traffic_class = "bulk"
            database.log_result(
                run_id,
                scenario=scenario,
                traffic_class=traffic_class,
                metric_name=metric_name,
                metric_value=float(value),
                unit=unit,
            )

        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        sample_path = RESULTS_ROOT / (
            f"congestion_{group_id}_{scenario.lower()}_rep{repetition}_run{run_id}.csv"
        )
        pd.DataFrame(rows).to_csv(sample_path, index=False)
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="CONGESTION_SCENARIO_COMPLETE",
                message=f"Congestion scenario {scenario} completed",
                metadata={
                    "sample_csv": str(sample_path),
                    "final_policy": current_policy,
                    "final_anre_state": final_state,
                    "recovery_to_normal_seconds": recovery_to_normal_seconds,
                },
            ),
        )
        database.finish_run(run_id, "COMPLETED")
        info(
            f"*** {scenario} repetition {repetition} complete: emergency="
            f"{summary['emergency_throughput_mbps']:.2f} Mbps, bulk="
            f"{summary['bulk_throughput_mbps']:.2f} Mbps, mean NHS="
            f"{summary['mean_nhs']:.2f}\n"
        )
        return summary
    except Exception as error:
        info(f"*** {scenario} repetition {repetition} FAILED: {error}\n")
        if database is not None and run_id is not None:
            try:
                database.log_event(
                    run_id,
                    EventRecord(
                        component="EXPERIMENT",
                        event_type="EXPERIMENT_FAILURE",
                        severity="ERROR",
                        message=str(error),
                    ),
                )
                database.finish_run(run_id, "FAILED")
            except Exception:
                pass
        raise
    finally:
        for _, _, process in processes:
            try:
                process.terminate()
                process.communicate(timeout=2)
            except Exception:
                pass
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()
        if database is not None:
            database.close()


def _save_congestion_comparison(
    group_id: str, summaries: list[dict[str, Any]]
) -> tuple[Path, Path]:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_ROOT / f"congestion_comparison_{group_id}.csv"
    graph_path = RESULTS_ROOT / f"congestion_comparison_{group_id}.png"
    frame = pd.DataFrame(summaries)
    frame.to_csv(csv_path, index=False)

    metrics = (
        ("emergency_throughput_mbps", "Emergency throughput", "Mbps"),
        ("emergency_udp_loss_percent", "Emergency UDP loss", "Percent"),
        ("emergency_udp_jitter_ms", "Emergency UDP jitter", "Milliseconds"),
        ("mean_rtt_ms", "Probe RTT", "Milliseconds"),
        ("mean_nhs", "Network Health Score", "Score"),
        ("bulk_throughput_mbps", "Bulk throughput", "Mbps"),
    )
    colors = {
        "ANRE_OFF": "#94a3b8",
        "STATIC_TUNED": "#2563eb",
        "ANRE_ON": "#0f766e",
    }
    labels = {
        "ANRE_OFF": "Basic static",
        "STATIC_TUNED": "Tuned static",
        "ANRE_ON": "Adaptive ANRE",
    }
    figure, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    figure.suptitle(
        f"CampusShield Experiment 2 - Three-arm congestion comparison ({group_id})"
    )
    for axis, (metric, title, unit) in zip(axes.flat, metrics):
        grouped = frame.groupby("scenario")[metric]
        order = [scenario for scenario in SCENARIOS if scenario in grouped.groups]
        statistics = [describe_95(grouped.get_group(scenario).dropna()) for scenario in order]
        means = [item.mean for item in statistics]
        errors = [item.ci95_high - item.mean for item in statistics]
        axis.bar(
            [labels[item] for item in order],
            means,
            yerr=errors,
            capsize=4,
            color=[colors[item] for item in order],
        )
        for index, scenario in enumerate(order):
            values = grouped.get_group(scenario).tolist()
            axis.scatter([index] * len(values), values, color="#111827", s=18, zorder=3)
        axis.set(title=title, ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)
    return csv_path, graph_path


def run_congestion_comparison(
    congestion_seconds: float,
    healthy_seconds: float,
    recovery_seconds: float,
    repetitions: int,
    database_path: Path,
) -> bool:
    if os.geteuid() != 0:
        raise PermissionError("Mininet experiments must be run with sudo")
    if repetitions < 1:
        raise ValueError("Repetitions must be at least 1")
    phase_plan = build_phase_plan(
        healthy_seconds, congestion_seconds, recovery_seconds
    )

    baseline_run_id, thresholds = _latest_baseline_thresholds(database_path)
    group_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    info(
        f"*** Experiment 2 group {group_id}; baseline run {baseline_run_id}; "
        f"{repetitions} matched three-arm repetition(s); phases="
        f"{healthy_seconds:.0f}s healthy, {congestion_seconds:.0f}s congestion, "
        f"{recovery_seconds:.0f}s recovery\n"
    )
    summaries: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for scenario in scenario_order_for_repetition(repetition):
            summaries.append(
                _run_congestion_scenario(
                    database_path=database_path,
                    thresholds=thresholds,
                    baseline_run_id=baseline_run_id,
                    group_id=group_id,
                    repetition=repetition,
                    scenario=scenario,
                    phase_plan=phase_plan,
                )
            )

    csv_path, graph_path = _save_congestion_comparison(group_id, summaries)
    frame = pd.DataFrame(summaries)
    means = frame.groupby("scenario").mean(numeric_only=True)
    info("\n*** Experiment 2 measured comparison\n")
    for scenario in SCENARIOS:
        row = means.loc[scenario]
        nhs_ci = describe_95(
            frame.loc[frame["scenario"] == scenario, "mean_nhs"]
        )
        info(
            f"{scenario}: emergency={row['emergency_throughput_mbps']:.2f} Mbps, "
            f"loss={row['emergency_udp_loss_percent']:.2f}%, "
            f"jitter={row['emergency_udp_jitter_ms']:.3f} ms, "
            f"RTT={row['mean_rtt_ms']:.3f} ms, NHS={row['mean_nhs']:.2f} "
            f"(95% CI {nhs_ci.ci95_low:.2f}-{nhs_ci.ci95_high:.2f}), "
            f"bulk={row['bulk_throughput_mbps']:.2f} Mbps\n"
        )
    info(f"Comparison CSV: {csv_path}\n")
    info(f"Comparison graph: {graph_path}\n")
    info("*** CONGESTION COMPARISON EXPERIMENT PASSED\n")
    return True


def _ping_replies(output: str) -> list[dict[str, float | int]]:
    replies = []
    pattern = re.compile(
        r"\[(\d+\.\d+)\].*icmp_seq=(\d+).*time[=<]([\d.]+)\s*ms"
    )
    for timestamp, sequence, rtt in pattern.findall(output):
        replies.append(
            {
                "timestamp": float(timestamp),
                "sequence": int(sequence),
                "rtt_ms": float(rtt),
            }
        )
    return replies


def _failure_gap(
    replies: list[dict[str, float | int]],
    failure_epoch: float,
    backup_epoch: float,
) -> tuple[float, int, dict[str, float | int], dict[str, float | int]]:
    if len(replies) < 2:
        raise RuntimeError("Continuous probe returned too few successful replies")
    candidates = [
        (previous, current)
        for previous, current in zip(replies, replies[1:])
        if float(current["timestamp"]) >= failure_epoch
        and float(previous["timestamp"]) <= backup_epoch + 1.0
    ]
    if not candidates:
        raise RuntimeError("No probe replies bracketed the failure event")
    previous, current = max(
        candidates,
        key=lambda pair: float(pair[1]["timestamp"]) - float(pair[0]["timestamp"]),
    )
    interruption = float(current["timestamp"]) - float(previous["timestamp"])
    lost = max(0, int(current["sequence"]) - int(previous["sequence"]) - 1)
    return interruption, lost, previous, current


def _store_failure_snapshot(
    database: CampusShieldDatabase,
    run_id: int,
    snapshot: dict[str, Any],
    thresholds: HealthThresholds,
    route_label: str,
) -> float:
    metrics = HealthMetrics(
        rtt_ms=snapshot["probe"]["average_rtt_ms"],
        loss_percent=snapshot["probe"]["packet_loss_percent"],
        jitter_ms=snapshot["probe"]["jitter_ms"],
        bandwidth_used_mbps=snapshot["interface"]["tx_mbps"],
    )
    score = calculate_health_score(metrics, thresholds)
    database.log_telemetry(
        run_id,
        TelemetryRecord.from_snapshot(
            snapshot,
            nhs=score.nhs,
            anre_state="NORMAL",
            link_name=route_label,
            link_health=score.nhs,
            qos_policy="NO_CONGESTION",
        ),
    )
    return score.nhs


def _run_failure_repetition(
    *,
    database_path: Path,
    thresholds: HealthThresholds,
    baseline_run_id: int,
    group_id: str,
    repetition: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    net = None
    nodes: dict[str, Any] = {}
    database: CampusShieldDatabase | None = None
    run_id: int | None = None
    ping_process = None
    link_is_down = False
    try:
        database = CampusShieldDatabase(database_path)
        run_id = database.start_run(
            f"Experiment 3 - Link failure - repetition {repetition}",
            "FAILURE_RECOVERY",
            is_experimental=True,
            notes=(
                f"failure_group={group_id}; repetition={repetition}; "
                f"baseline_run_id={baseline_run_id}; physical R1-R2 link down/up"
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="EXPERIMENT_START",
                message="Physical R1-R2 failure experiment started",
                metadata={"group_id": group_id, "repetition": repetition},
            ),
        )

        info(f"\n*** Building fresh topology for failure repetition {repetition}\n")
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            start_frr(router)
        if not wait_for_ospf(routers):
            raise RuntimeError("OSPF did not converge before failure injection")

        direct_ok, route_before = route_uses(
            nodes["r1"], "10.10.20.10", "via 10.10.255.2"
        )
        if not direct_ok:
            raise RuntimeError("R1-R2 was not the route before failure")
        neighbors_before = vtysh_command(
            nodes["r1"], "show ip ospf neighbor"
        ).count("Full")
        pre_snapshot = collect_snapshot(
            nodes, "r1", "emergency1", "r1-eth0", "10.10.20.10",
            CORE_BANDWIDTH_MBPS, 0.5,
        )
        pre_nhs = _store_failure_snapshot(
            database, run_id, pre_snapshot, thresholds, "R1-R2_PRIMARY"
        )

        ping_process = nodes["emergency1"].popen(
            ["ping", "-D", "-n", "-i", "0.1", "10.10.20.10"]
        )
        time.sleep(2.0)
        failure_epoch = time.time()
        failure_started = time.monotonic()
        failure_timestamp = datetime.fromtimestamp(
            failure_epoch, tz=timezone.utc
        ).isoformat()
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="LINK_FAILURE",
                timestamp_utc=failure_timestamp,
                message="Physical R1-R2 link disabled",
                action="LINK_DOWN",
                link_name="R1-R2",
                old_value="up",
                new_value="down",
                metadata={"route_before": route_before},
            ),
        )
        net.configLinkStatus("r1", "r2", "down")
        link_is_down = True

        deadline = time.monotonic() + timeout_seconds
        route_after_failure = ""
        while time.monotonic() < deadline:
            backup_ok, route_after_failure = route_uses(
                nodes["r1"], "10.10.20.10", "via 10.10.255.6"
            )
            if backup_ok:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("OSPF did not install the backup route in time")
        backup_monotonic = time.monotonic()
        backup_epoch = time.time()
        route_convergence_seconds = backup_monotonic - failure_started
        neighbors_after_failure = vtysh_command(
            nodes["r1"], "show ip ospf neighbor"
        ).count("Full")
        database.log_event(
            run_id,
            EventRecord(
                component="OSPF",
                event_type="ROUTE_CONVERGED",
                message="OSPF installed the R1-R3-R2 backup route",
                action="OSPF_FAILOVER",
                link_name="R1-R2",
                metadata={
                    "route_after_failure": route_after_failure,
                    "convergence_seconds": route_convergence_seconds,
                    "full_neighbors_before": neighbors_before,
                    "full_neighbors_after": neighbors_after_failure,
                },
            ),
        )
        time.sleep(1.0)
        backup_snapshot = collect_snapshot(
            nodes, "r1", "emergency1", "r1-eth1", "10.10.20.10",
            CORE_BANDWIDTH_MBPS, 0.5,
        )
        backup_nhs = _store_failure_snapshot(
            database, run_id, backup_snapshot, thresholds, "R1-R3-R2_BACKUP"
        )

        restore_started = time.monotonic()
        net.configLinkStatus("r1", "r2", "up")
        link_is_down = False
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="LINK_RESTORED",
                message="Physical R1-R2 link enabled",
                action="LINK_UP",
                link_name="R1-R2",
                old_value="down",
                new_value="up",
            ),
        )
        if not wait_for_ospf(routers, timeout=int(timeout_seconds)):
            raise RuntimeError("OSPF adjacency did not return after link restoration")
        deadline = time.monotonic() + timeout_seconds
        route_restored = ""
        while time.monotonic() < deadline:
            restored_ok, route_restored = route_uses(
                nodes["r1"], "10.10.20.10", "via 10.10.255.2"
            )
            if restored_ok:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Direct R1-R2 route did not return in time")
        primary_restoration_seconds = time.monotonic() - restore_started
        database.log_event(
            run_id,
            EventRecord(
                component="OSPF",
                event_type="PRIMARY_ROUTE_RESTORED",
                message="OSPF restored the direct R1-R2 route",
                action="ROUTE_RESTORE",
                link_name="R1-R2",
                metadata={
                    "route_restored": route_restored,
                    "restoration_seconds": primary_restoration_seconds,
                },
            ),
        )

        time.sleep(1.0)
        ping_process.terminate()
        stdout, _ = ping_process.communicate(timeout=3)
        ping_process = None
        ping_output = stdout.decode() if isinstance(stdout, bytes) else stdout
        replies = _ping_replies(ping_output)
        interruption_seconds, packets_lost, last_success, first_success = _failure_gap(
            replies, failure_epoch, backup_epoch
        )

        summary = {
            "group_id": group_id,
            "repetition": repetition,
            "run_id": run_id,
            "failure_timestamp_utc": failure_timestamp,
            "packets_lost_during_convergence": packets_lost,
            "service_interruption_ms": interruption_seconds * 1_000,
            "route_convergence_ms": route_convergence_seconds * 1_000,
            "primary_restoration_ms": primary_restoration_seconds * 1_000,
            "last_success_before_outage_utc": datetime.fromtimestamp(
                float(last_success["timestamp"]), tz=timezone.utc
            ).isoformat(),
            "first_success_after_outage_utc": datetime.fromtimestamp(
                float(first_success["timestamp"]), tz=timezone.utc
            ).isoformat(),
            "route_before": route_before,
            "route_after_failure": route_after_failure,
            "route_after_restoration": route_restored,
            "full_neighbors_before": neighbors_before,
            "full_neighbors_after_failure": neighbors_after_failure,
            "pre_failure_nhs": pre_nhs,
            "backup_path_nhs": backup_nhs,
        }
        units = {
            "packets_lost_during_convergence": "packets",
            "service_interruption_ms": "ms",
            "route_convergence_ms": "ms",
            "primary_restoration_ms": "ms",
            "full_neighbors_before": "count",
            "full_neighbors_after_failure": "count",
            "pre_failure_nhs": "score",
            "backup_path_nhs": "score",
        }
        for metric_name, unit in units.items():
            database.log_result(
                run_id,
                scenario="PHYSICAL_R1_R2_FAILURE",
                metric_name=metric_name,
                metric_value=float(summary[metric_name]),
                unit=unit,
            )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="FAILURE_EXPERIMENT_COMPLETE",
                message="Failure, backup convergence, and restoration measured",
                metadata={
                    "packets_lost": packets_lost,
                    "service_interruption_ms": interruption_seconds * 1_000,
                },
            ),
        )
        database.finish_run(run_id, "COMPLETED")
        info(
            f"*** Failure repetition {repetition}: lost={packets_lost}, "
            f"interruption={interruption_seconds * 1000:.1f} ms, "
            f"route convergence={route_convergence_seconds * 1000:.1f} ms, "
            f"primary restoration={primary_restoration_seconds * 1000:.1f} ms\n"
        )
        return summary
    except Exception as error:
        info(f"*** Failure repetition {repetition} FAILED: {error}\n")
        if database is not None and run_id is not None:
            try:
                database.log_event(
                    run_id,
                    EventRecord(
                        component="EXPERIMENT",
                        event_type="EXPERIMENT_FAILURE",
                        severity="ERROR",
                        message=str(error),
                    ),
                )
                database.finish_run(run_id, "FAILED")
            except Exception:
                pass
        raise
    finally:
        if ping_process is not None:
            try:
                ping_process.terminate()
                ping_process.communicate(timeout=2)
            except Exception:
                pass
        if net is not None and link_is_down:
            try:
                net.configLinkStatus("r1", "r2", "up")
            except Exception:
                pass
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()
        if database is not None:
            database.close()


def _save_failure_artifacts(
    group_id: str, summaries: list[dict[str, Any]]
) -> tuple[Path, Path]:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_ROOT / f"failure_recovery_{group_id}.csv"
    graph_path = RESULTS_ROOT / f"failure_recovery_{group_id}.png"
    frame = pd.DataFrame(summaries)
    frame.to_csv(csv_path, index=False)
    metrics = (
        ("packets_lost_during_convergence", "Packets lost", "Packets"),
        ("service_interruption_ms", "Service interruption", "Milliseconds"),
        ("route_convergence_ms", "Backup route convergence", "Milliseconds"),
        ("primary_restoration_ms", "Primary route restoration", "Milliseconds"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    figure.suptitle(f"CampusShield Experiment 3 - R1-R2 Failure ({group_id})")
    for axis, (metric, title, unit) in zip(axes.flat, metrics):
        axis.bar(frame["repetition"].astype(str), frame[metric], color="#0f766e")
        axis.set(title=title, xlabel="Repetition", ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)
    return csv_path, graph_path


def run_failure_experiment(
    repetitions: int, timeout_seconds: float, database_path: Path
) -> bool:
    if os.geteuid() != 0:
        raise PermissionError("Mininet experiments must be run with sudo")
    if repetitions < 1:
        raise ValueError("Repetitions must be at least 1")
    if timeout_seconds < 5:
        raise ValueError("Failure timeout must be at least 5 seconds")
    baseline_run_id, thresholds = _latest_baseline_thresholds(database_path)
    group_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    info(
        f"*** Experiment 3 group {group_id}; baseline run {baseline_run_id}; "
        f"{repetitions} repetition(s)\n"
    )
    summaries = [
        _run_failure_repetition(
            database_path=database_path,
            thresholds=thresholds,
            baseline_run_id=baseline_run_id,
            group_id=group_id,
            repetition=repetition,
            timeout_seconds=timeout_seconds,
        )
        for repetition in range(1, repetitions + 1)
    ]
    csv_path, graph_path = _save_failure_artifacts(group_id, summaries)
    frame = pd.DataFrame(summaries)
    info("\n*** Experiment 3 measured summary\n")
    info(
        f"Mean packets lost: {frame['packets_lost_during_convergence'].mean():.2f}\n"
        f"Mean service interruption: {frame['service_interruption_ms'].mean():.2f} ms\n"
        f"Mean route convergence: {frame['route_convergence_ms'].mean():.2f} ms\n"
        f"Mean primary restoration: {frame['primary_restoration_ms'].mean():.2f} ms\n"
        f"Results CSV: {csv_path}\n"
        f"Results graph: {graph_path}\n"
    )
    info("*** LINK FAILURE EXPERIMENT PASSED\n")
    return True


PRIMARY_SILENT_FAILURE_ENDPOINTS = (("r1", "r1-eth0"), ("r2", "r2-eth0"))


def _set_primary_silent_failure(nodes: dict[str, Any], enabled: bool) -> None:
    """Blackhole the direct link without changing its carrier state."""
    rules = (
        ("INPUT", "-i"),
        ("OUTPUT", "-o"),
        ("FORWARD", "-i"),
        ("FORWARD", "-o"),
    )
    operation = "-I" if enabled else "-D"
    for router_name, interface in PRIMARY_SILENT_FAILURE_ENDPOINTS:
        node = nodes[router_name]
        for chain, direction in rules:
            output = node.cmd(
                f"iptables -w {operation} {chain} "
                f"{direction} {interface} -j DROP 2>&1"
            )
            if enabled and output.strip():
                raise RuntimeError(
                    f"Could not inject silent failure on {router_name}: {output.strip()}"
                )


def _wait_for_route(
    router: Any, destination: str, expected: str, timeout_seconds: float
) -> tuple[str, float]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    latest = ""
    while time.monotonic() < deadline:
        matched, latest = route_uses(router, destination, expected)
        if matched:
            return latest, time.monotonic() - started
        time.sleep(0.05)
    raise RuntimeError(
        f"Route containing '{expected}' was not installed within "
        f"{timeout_seconds:.1f} seconds; last route: {latest or 'none'}"
    )


def _run_ospf_profile_repetition(
    *,
    database_path: Path,
    group_id: str,
    repetition: int,
    scenario: str,
    execution_order: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    net = None
    nodes: dict[str, Any] = {}
    database: CampusShieldDatabase | None = None
    run_id: int | None = None
    ping_process = None
    failure_active = False
    try:
        database = CampusShieldDatabase(database_path)
        profile_name = "Tuned" if scenario == "OSPF_TUNED" else "Default"
        run_id = database.start_run(
            f"Experiment 4 - {profile_name} OSPF - repetition {repetition}",
            scenario,
            is_experimental=True,
            notes=(
                f"ospf_group={group_id}; repetition={repetition}; "
                f"execution_order={execution_order}; silent R1-R2 blackhole"
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="OSPF_PROFILE_EXPERIMENT_START",
                message=f"{profile_name} OSPF silent-failure trial started",
                metadata={
                    "group_id": group_id,
                    "repetition": repetition,
                    "execution_order": execution_order,
                    "scenario": scenario,
                },
            ),
        )

        info(
            f"\n*** Phase 3 repetition {repetition}, order {execution_order}: "
            f"{scenario}\n"
        )
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            start_frr(router)
        if scenario == "OSPF_TUNED":
            if not apply_tuned_ospf_profile(nodes):
                raise RuntimeError("FRR rejected the tuned OSPF profile")
        if not wait_for_ospf(routers, timeout=60):
            raise RuntimeError("OSPF did not converge before failure injection")
        if scenario == "OSPF_TUNED" and not validate_tuned_ospf_profile(nodes):
            raise RuntimeError("Tuned OSPF profile could not be verified")

        direct_ok, route_before = route_uses(
            nodes["r1"], "10.10.20.10", "via 10.10.255.2"
        )
        if not direct_ok:
            raise RuntimeError("R1-R2 was not the primary route before failure")
        neighbors_before = vtysh_command(
            nodes["r1"], "show ip ospf neighbor"
        ).count("Full")

        ping_process = nodes["emergency1"].popen(
            ["ping", "-D", "-n", "-i", "0.1", "10.10.20.10"]
        )
        time.sleep(2.0)
        failure_epoch = time.time()
        failure_timestamp = datetime.fromtimestamp(
            failure_epoch, tz=timezone.utc
        ).isoformat()
        _set_primary_silent_failure(nodes, True)
        failure_active = True
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="SILENT_LINK_FAILURE",
                timestamp_utc=failure_timestamp,
                message="R1-R2 traffic silently blackholed while carrier remained up",
                action="BLACKHOLE_ENABLE",
                link_name="R1-R2",
                old_value="forwarding",
                new_value="silent_drop",
                metadata={"route_before": route_before, "scenario": scenario},
            ),
        )

        route_after_failure, convergence_seconds = _wait_for_route(
            nodes["r1"], "10.10.20.10", "via 10.10.255.6", timeout_seconds
        )
        backup_epoch = time.time()
        neighbors_after_failure = vtysh_command(
            nodes["r1"], "show ip ospf neighbor"
        ).count("Full")
        database.log_event(
            run_id,
            EventRecord(
                component="OSPF",
                event_type="BACKUP_ROUTE_CONVERGED",
                message="OSPF installed the R1-R3-R2 route after silent failure",
                action="OSPF_FAILOVER",
                link_name="R1-R2",
                metadata={
                    "convergence_seconds": convergence_seconds,
                    "route": route_after_failure,
                },
            ),
        )

        time.sleep(1.0)
        restore_started = time.monotonic()
        _set_primary_silent_failure(nodes, False)
        failure_active = False
        route_restored, restoration_seconds = _wait_for_route(
            nodes["r1"], "10.10.20.10", "via 10.10.255.2", timeout_seconds
        )
        restoration_seconds = time.monotonic() - restore_started
        database.log_event(
            run_id,
            EventRecord(
                component="OSPF",
                event_type="PRIMARY_ROUTE_RESTORED",
                message="OSPF restored the direct route after silent failure removal",
                action="ROUTE_RESTORE",
                link_name="R1-R2",
                metadata={"restoration_seconds": restoration_seconds},
            ),
        )

        time.sleep(1.0)
        ping_process.terminate()
        stdout, _ = ping_process.communicate(timeout=3)
        ping_process = None
        ping_output = stdout.decode() if isinstance(stdout, bytes) else stdout
        replies = _ping_replies(ping_output)
        interruption_seconds, packets_lost, last_success, first_success = _failure_gap(
            replies, failure_epoch, backup_epoch
        )

        if scenario == "OSPF_TUNED":
            dead_interval = TUNED_DEAD_INTERVAL_SECONDS
            hello_multiplier = TUNED_HELLO_MULTIPLIER
            spf_delay = TUNED_SPF_DELAY_MS
            spf_initial = TUNED_SPF_INITIAL_HOLD_MS
            spf_maximum = TUNED_SPF_MAX_HOLD_MS
        else:
            dead_interval = 40.0
            hello_multiplier = 0
            spf_delay = 0
            spf_initial = 50
            spf_maximum = 5_000

        summary = {
            "group_id": group_id,
            "repetition": repetition,
            "execution_order": execution_order,
            "scenario": scenario,
            "run_id": run_id,
            "failure_timestamp_utc": failure_timestamp,
            "dead_interval_seconds": dead_interval,
            "hello_multiplier": hello_multiplier,
            "spf_delay_ms": spf_delay,
            "spf_initial_hold_ms": spf_initial,
            "spf_max_hold_ms": spf_maximum,
            "packets_lost_during_convergence": packets_lost,
            "service_interruption_ms": interruption_seconds * 1_000,
            "route_convergence_ms": convergence_seconds * 1_000,
            "primary_restoration_ms": restoration_seconds * 1_000,
            "last_success_before_outage_utc": datetime.fromtimestamp(
                float(last_success["timestamp"]), tz=timezone.utc
            ).isoformat(),
            "first_success_after_outage_utc": datetime.fromtimestamp(
                float(first_success["timestamp"]), tz=timezone.utc
            ).isoformat(),
            "route_before": route_before,
            "route_after_failure": route_after_failure,
            "route_after_restoration": route_restored,
            "full_neighbors_before": neighbors_before,
            "full_neighbors_after_failure": neighbors_after_failure,
        }
        units = {
            "packets_lost_during_convergence": "packets",
            "service_interruption_ms": "ms",
            "route_convergence_ms": "ms",
            "primary_restoration_ms": "ms",
            "full_neighbors_before": "count",
            "full_neighbors_after_failure": "count",
        }
        for metric_name, unit in units.items():
            database.log_result(
                run_id,
                scenario=scenario,
                metric_name=metric_name,
                metric_value=float(summary[metric_name]),
                unit=unit,
            )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="OSPF_PROFILE_EXPERIMENT_COMPLETE",
                message=f"{profile_name} OSPF recovery measured",
                metadata={
                    "packets_lost": packets_lost,
                    "service_interruption_ms": interruption_seconds * 1_000,
                },
            ),
        )
        database.finish_run(run_id, "COMPLETED")
        info(
            f"*** {scenario}: lost={packets_lost}, "
            f"interruption={interruption_seconds * 1000:.1f} ms, "
            f"convergence={convergence_seconds * 1000:.1f} ms\n"
        )
        return summary
    except Exception as error:
        info(f"*** {scenario} repetition {repetition} FAILED: {error}\n")
        if database is not None and run_id is not None:
            try:
                database.log_event(
                    run_id,
                    EventRecord(
                        component="EXPERIMENT",
                        event_type="EXPERIMENT_FAILURE",
                        severity="ERROR",
                        message=str(error),
                    ),
                )
                database.finish_run(run_id, "FAILED")
            except Exception:
                pass
        raise
    finally:
        if ping_process is not None:
            try:
                ping_process.terminate()
                ping_process.communicate(timeout=2)
            except Exception:
                pass
        if failure_active and nodes:
            try:
                _set_primary_silent_failure(nodes, False)
            except Exception:
                pass
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()
        if database is not None:
            database.close()


def _save_ospf_artifacts(
    group_id: str, summaries: list[dict[str, Any]]
) -> tuple[Path, Path]:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_ROOT / f"ospf_optimization_{group_id}.csv"
    graph_path = RESULTS_ROOT / f"ospf_optimization_{group_id}.png"
    frame = pd.DataFrame(summaries)
    frame.to_csv(csv_path, index=False)
    matched_repetitions = int(frame["repetition"].nunique())
    evidence_label = "Formal" if matched_repetitions >= 10 else "Pilot"

    metrics = (
        ("service_interruption_ms", "Service interruption", "Milliseconds"),
        ("packets_lost_during_convergence", "Packets lost", "Packets"),
        ("route_convergence_ms", "Backup convergence", "Milliseconds"),
        ("primary_restoration_ms", "Primary restoration", "Milliseconds"),
    )
    colors = {"OSPF_DEFAULT": "#64748b", "OSPF_TUNED": "#38bdf8"}
    figure, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    figure.suptitle(
        f"CampusShield Experiment 4 - OSPF Optimization ({evidence_label}, "
        f"n={matched_repetitions}; {group_id})"
    )
    for axis, (metric, title, unit) in zip(axes.flat, metrics):
        for scenario in OSPF_SCENARIOS:
            sample = frame.loc[frame["scenario"] == scenario, metric]
            stats = describe_95(sample)
            axis.bar(
                scenario.replace("OSPF_", ""),
                stats.mean,
                yerr=[[stats.mean - stats.ci95_low], [stats.ci95_high - stats.mean]],
                capsize=5,
                color=colors[scenario],
            )
        axis.set(title=title, ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)
    return csv_path, graph_path


def run_ospf_optimization(
    repetitions: int, timeout_seconds: float, database_path: Path
) -> bool:
    if os.geteuid() != 0:
        raise PermissionError("Mininet experiments must be run with sudo")
    if repetitions < 1:
        raise ValueError("Repetitions must be at least 1")
    if timeout_seconds < 45:
        raise ValueError("OSPF timeout must be at least 45 seconds for the default profile")

    group_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    info(
        f"*** Experiment 4 group {group_id}; {repetitions} matched repetition(s) "
        "of default and tuned OSPF\n"
    )
    summaries: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for execution_order, scenario in enumerate(
            ospf_scenario_order(repetition), start=1
        ):
            summaries.append(
                _run_ospf_profile_repetition(
                    database_path=database_path,
                    group_id=group_id,
                    repetition=repetition,
                    scenario=scenario,
                    execution_order=execution_order,
                    timeout_seconds=timeout_seconds,
                )
            )

    csv_path, graph_path = _save_ospf_artifacts(group_id, summaries)
    frame = pd.DataFrame(summaries)
    means = frame.groupby("scenario").mean(numeric_only=True)
    default_ms = float(means.loc["OSPF_DEFAULT", "service_interruption_ms"])
    tuned_ms = float(means.loc["OSPF_TUNED", "service_interruption_ms"])
    improvement = recovery_improvement_percent(default_ms, tuned_ms)
    outcome = "SUPPORTED" if h7_supported(default_ms, tuned_ms) else "NOT SUPPORTED"
    info("\n*** Experiment 4 measured comparison\n")
    for scenario in OSPF_SCENARIOS:
        sample = frame.loc[frame["scenario"] == scenario, "service_interruption_ms"]
        stats = describe_95(sample)
        lost = means.loc[scenario, "packets_lost_during_convergence"]
        info(
            f"{scenario}: interruption={stats.mean:.2f} ms "
            f"(95% CI {stats.ci95_low:.2f}-{stats.ci95_high:.2f}), "
            f"packets lost={lost:.2f}\n"
        )
    info(
        f"H7: {outcome}; tuned recovery change={improvement:.2f}%\n"
        f"Results CSV: {csv_path}\n"
        f"Results graph: {graph_path}\n"
        "*** OSPF OPTIMIZATION EXPERIMENT PASSED\n"
    )
    return True


def main() -> int:
    args = parse_args()
    setLogLevel("info")
    try:
        lock_file = acquire_experiment_lock()
    except RuntimeError as error:
        info(f"*** EXPERIMENT NOT STARTED: {error}\n")
        return 1
    try:
        if args.experiment == "baseline":
            return 0 if run_baseline(args.duration, args.database) else 1
        if args.experiment == "congestion":
            return 0 if run_congestion_comparison(
                args.duration,
                args.healthy_duration,
                args.recovery_duration,
                args.repetitions,
                args.database,
            ) else 1
        if args.experiment == "failure":
            return 0 if run_failure_experiment(
                args.repetitions, args.timeout, args.database
            ) else 1
        if args.experiment == "ospf":
            return 0 if run_ospf_optimization(
                args.repetitions, args.timeout, args.database
            ) else 1
        return 1
    finally:
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
