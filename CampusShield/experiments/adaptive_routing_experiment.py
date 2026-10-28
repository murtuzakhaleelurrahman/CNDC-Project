"""Measured closed-loop ANRE and adaptive-routing experiment."""

from __future__ import annotations

import re
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from mininet.log import info

from controller.adaptive_controller import CampusShieldAdaptiveController
from controller.qos_manager import (
    apply_static_qos,
    set_primary_link_impairment,
    update_qos_policy,
    validate_primary_link_impairment,
    validate_qos_policy,
    validate_static_qos,
)
from controller.routing_manager import (
    AdaptiveRoutingController,
    PENALIZED_COST,
    PRIMARY_COST,
    RoutingAction,
    read_primary_link_costs,
    set_primary_link_cost,
)
from database.storage import (
    CampusShieldDatabase,
    EventRecord,
    TelemetryRecord,
)
from experiments.adaptive_routing_design import (
    DEGRADATION_DELAY_MS,
    DEGRADATION_LOSS_PERCENT,
    HOLD_DOWN_SECONDS,
    RESTORED_DELAY_MS,
    RESTORED_LOSS_PERCENT,
    hold_down_respected,
    route_shift_valid,
)
from experiments.statistics_utils import describe_95
from telemetry.link_health import collect_link_health, thresholds_from_healthy_link
from telemetry.probe_monitor import collect_probe_metrics
from topology.campus_topology import (
    CORE_BANDWIDTH_MBPS,
    CORE_DELAY,
    build_network,
    route_uses,
    start_frr,
    stop_frr,
    wait_for_ospf,
)


RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results"
DESTINATION = "10.10.20.10"
PRIMARY_NEXT_HOP = "10.10.255.2"
BACKUP_NEXT_HOP = "10.10.255.6"


def _route_fields(output: str) -> tuple[str | None, str | None]:
    match = re.search(r"(?:via\s+(\S+)\s+)?dev\s+(\S+)", output)
    return (match.group(1), match.group(2)) if match else (None, None)


def _wait_route(router: Any, expected: str, timeout: float = 15.0) -> tuple[str, float]:
    started = time.monotonic()
    deadline = started + timeout
    latest = ""
    while time.monotonic() < deadline:
        matched, latest = route_uses(router, DESTINATION, f"via {expected}")
        if matched:
            return latest, time.monotonic() - started
        time.sleep(0.05)
    raise RuntimeError(f"Route via {expected} was not installed; last route: {latest}")


def _log_controller_sample(
    *,
    database: CampusShieldDatabase,
    run_id: int,
    nodes: dict[str, Any],
    controller: CampusShieldAdaptiveController,
    thresholds: Any,
    phase: str,
    sample_number: int,
) -> tuple[Any, Any, str]:
    health = collect_link_health(
        node=nodes["r1"],
        link_name="R1-R2",
        interface="r1-eth0",
        peer_ip="10.10.255.2",
        capacity_mbps=CORE_BANDWIDTH_MBPS,
        thresholds=thresholds,
        interval_seconds=0.4,
    )
    observed_at = time.monotonic()
    decision = controller.observe(
        network_health=health.score.nhs,
        primary_link_health=health.score.nhs,
        now=observed_at,
    )

    if decision.anre.changed:
        new_policy = decision.anre.current_state.value
        if not update_qos_policy(nodes, new_policy):
            raise RuntimeError(f"Could not apply {new_policy} QoS policy")
        if not validate_qos_policy(nodes, new_policy):
            raise RuntimeError(f"Could not validate {new_policy} QoS policy")
        database.log_event(
            run_id,
            EventRecord(
                component="ANRE",
                event_type="ANRE_STATE_CHANGE",
                previous_state=decision.anre.previous_state.value,
                current_state=decision.anre.current_state.value,
                action="QOS_POLICY_UPDATE",
                message=(
                    f"ANRE changed from {decision.anre.previous_state.value} to "
                    f"{decision.anre.current_state.value}"
                ),
                metadata={"phase": phase, "nhs": health.score.nhs},
            ),
        )

    if decision.routing.action is RoutingAction.PENALIZE:
        if not set_primary_link_cost(nodes, PENALIZED_COST):
            raise RuntimeError("Could not penalize the degraded R1-R2 link")
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="OSPF_COST_PENALIZED",
                action="SET_OSPF_COST",
                link_name="R1-R2",
                old_value=str(PRIMARY_COST),
                new_value=str(PENALIZED_COST),
                message="Persistent degradation raised the R1-R2 OSPF cost",
                metadata={"phase": phase, "link_health": health.score.nhs},
            ),
        )
    elif decision.routing.action is RoutingAction.RESTORE:
        if not set_primary_link_cost(nodes, PRIMARY_COST):
            raise RuntimeError("Could not restore the healthy R1-R2 link cost")
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="OSPF_COST_RESTORED",
                action="SET_OSPF_COST",
                link_name="R1-R2",
                old_value=str(PENALIZED_COST),
                new_value=str(PRIMARY_COST),
                message="Sustained recovery restored the R1-R2 OSPF cost",
                metadata={"phase": phase, "link_health": health.score.nhs},
            ),
        )

    _, route_output = route_uses(nodes["r1"], DESTINATION, "via")
    next_hop, route_interface = _route_fields(route_output)
    interface = health.interface_metrics
    probe = health.probe_metrics
    database.log_telemetry(
        run_id,
        TelemetryRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            router="r1",
            source_host="r1",
            target_ip=probe.target,
            interface=interface.interface,
            rtt_ms=probe.average_rtt_ms,
            packet_loss_percent=probe.packet_loss_percent,
            jitter_ms=probe.jitter_ms,
            tx_mbps=interface.tx_mbps,
            rx_mbps=interface.rx_mbps,
            utilization_percent=interface.tx_utilization_percent,
            probe_dscp_value=probe.dscp_value,
            nhs=health.score.nhs,
            anre_state=decision.anre.current_state.value,
            link_name="R1-R2",
            link_health=health.score.nhs,
            qos_policy=decision.anre.current_state.value,
            route_next_hop=next_hop,
            route_interface=route_interface,
            route_state=phase,
        ),
    )
    info(
        f"Sample {sample_number:02d} [{phase}]: health={health.score.nhs:.1f}, "
        f"loss={probe.packet_loss_percent:.1f}%, RTT={probe.average_rtt_ms:.1f} ms, "
        f"ANRE={decision.anre.current_state.value}, "
        f"routing={decision.routing.action.value}\n"
    )
    return health, decision, route_output


def _run_repetition(
    *,
    database_path: Path,
    group_id: str,
    repetition: int,
    hold_down_seconds: float,
) -> dict[str, Any]:
    net = None
    nodes: dict[str, Any] = {}
    database: CampusShieldDatabase | None = None
    run_id: int | None = None
    impaired = False
    costs_penalized = False
    try:
        database = CampusShieldDatabase(database_path)
        run_id = database.start_run(
            f"Experiment 5 - Adaptive routing - repetition {repetition}",
            "ADAPTIVE_ROUTING",
            is_experimental=True,
            notes=(
                f"adaptive_routing_group={group_id}; repetition={repetition}; "
                f"delay={DEGRADATION_DELAY_MS}ms; loss={DEGRADATION_LOSS_PERCENT}%; "
                f"hold_down={hold_down_seconds}s"
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="ADAPTIVE_ROUTING_EXPERIMENT_START",
                message="Closed-loop ANRE and adaptive-routing experiment started",
                metadata={"group_id": group_id, "repetition": repetition},
            ),
        )

        info(f"\n*** Building Phase 4 topology for repetition {repetition}\n")
        net, nodes = build_network()
        routers = [nodes["r1"], nodes["r2"], nodes["r3"]]
        for router in routers:
            start_frr(router)
        if not wait_for_ospf(routers):
            raise RuntimeError("OSPF did not converge before adaptive routing")
        if not apply_static_qos(nodes, CORE_BANDWIDTH_MBPS, CORE_DELAY):
            raise RuntimeError("Static QoS setup failed")
        if not validate_static_qos(nodes):
            raise RuntimeError("Static QoS validation failed")

        direct_ok, route_before = route_uses(
            nodes["r1"], DESTINATION, f"via {PRIMARY_NEXT_HOP}"
        )
        if not direct_ok:
            raise RuntimeError("R1-R2 was not the initial primary route")

        healthy_probe = collect_probe_metrics(nodes["r1"], "10.10.255.2", count=8)
        thresholds = thresholds_from_healthy_link(healthy_probe, CORE_BANDWIDTH_MBPS)
        controller = CampusShieldAdaptiveController(
            routing=AdaptiveRoutingController(hold_down_seconds=hold_down_seconds)
        )
        sample_number = 1
        healthy, _, _ = _log_controller_sample(
            database=database,
            run_id=run_id,
            nodes=nodes,
            controller=controller,
            thresholds=thresholds,
            phase="HEALTHY",
            sample_number=sample_number,
        )
        if healthy.score.nhs < 80:
            raise RuntimeError("Healthy R1-R2 calibration scored below 80")

        impairment_started = time.monotonic()
        if not set_primary_link_impairment(
            nodes,
            delay_ms=DEGRADATION_DELAY_MS,
            loss_percent=DEGRADATION_LOSS_PERCENT,
        ):
            raise RuntimeError("Could not apply the R1-R2 impairment")
        impaired = True
        if not validate_primary_link_impairment(
            nodes,
            delay_ms=DEGRADATION_DELAY_MS,
            loss_percent=DEGRADATION_LOSS_PERCENT,
        ):
            raise RuntimeError("The R1-R2 impairment was not present on every class")
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="LINK_DEGRADATION_INJECTED",
                message="R1-R2 remained up with controlled delay and packet loss",
                link_name="R1-R2",
                old_value=f"{RESTORED_DELAY_MS}ms, 0% loss",
                new_value=(
                    f"{DEGRADATION_DELAY_MS}ms, "
                    f"{DEGRADATION_LOSS_PERCENT:g}% loss"
                ),
            ),
        )

        degraded_scores: list[float] = []
        penalty_decision_at = 0.0
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            sample_number += 1
            health, decision, _ = _log_controller_sample(
                database=database,
                run_id=run_id,
                nodes=nodes,
                controller=controller,
                thresholds=thresholds,
                phase="DEGRADED",
                sample_number=sample_number,
            )
            degraded_scores.append(health.score.nhs)
            if decision.routing.action is RoutingAction.PENALIZE:
                penalty_decision_at = time.monotonic()
                costs_penalized = True
                break
        else:
            raise RuntimeError("Controller did not penalize persistent degradation")

        route_backup, route_shift_seconds = _wait_route(nodes["r1"], BACKUP_NEXT_HOP)
        degradation_detection_seconds = penalty_decision_at - impairment_started
        penalized_costs = read_primary_link_costs(nodes)
        if penalized_costs != {"r1": PENALIZED_COST, "r2": PENALIZED_COST}:
            raise RuntimeError(f"Unexpected penalized costs: {penalized_costs}")

        if not set_primary_link_impairment(
            nodes,
            delay_ms=RESTORED_DELAY_MS,
            loss_percent=RESTORED_LOSS_PERCENT,
        ):
            raise RuntimeError("Could not remove the R1-R2 impairment")
        impaired = False
        recovery_started = time.monotonic()
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="LINK_DEGRADATION_REMOVED",
                message="R1-R2 delay and loss returned to healthy settings",
                link_name="R1-R2",
            ),
        )

        healthy_recovery_scores: list[float] = []
        premature_restore = False
        restore_decision_at = 0.0
        deadline = recovery_started + hold_down_seconds + 30
        while time.monotonic() < deadline:
            sample_number += 1
            health, decision, _ = _log_controller_sample(
                database=database,
                run_id=run_id,
                nodes=nodes,
                controller=controller,
                thresholds=thresholds,
                phase="HOLD_DOWN_RECOVERY",
                sample_number=sample_number,
            )
            healthy_recovery_scores.append(health.score.nhs)
            if decision.routing.action is RoutingAction.RESTORE:
                restore_decision_at = time.monotonic()
                costs_penalized = False
                if restore_decision_at - penalty_decision_at < hold_down_seconds:
                    premature_restore = True
                break
        else:
            raise RuntimeError("Controller did not restore the primary route in time")

        route_restored, route_restore_seconds = _wait_route(
            nodes["r1"], PRIMARY_NEXT_HOP
        )
        restored_costs = read_primary_link_costs(nodes)
        if restored_costs != {"r1": PRIMARY_COST, "r2": PRIMARY_COST}:
            raise RuntimeError(f"Unexpected restored costs: {restored_costs}")
        if controller.anre.state.value != "NORMAL":
            raise RuntimeError("ANRE did not recover to NORMAL")
        if premature_restore or not hold_down_respected(
            penalty_decision_at, restore_decision_at, hold_down_seconds
        ):
            raise RuntimeError("Routing hold-down was not respected")
        if not route_shift_valid(route_before, route_backup, route_restored):
            raise RuntimeError("The expected primary-backup-primary route sequence failed")

        summary = {
            "group_id": group_id,
            "repetition": repetition,
            "run_id": run_id,
            "degradation_delay_ms": DEGRADATION_DELAY_MS,
            "degradation_loss_percent": DEGRADATION_LOSS_PERCENT,
            "hold_down_seconds": hold_down_seconds,
            "healthy_link_health": healthy.score.nhs,
            "minimum_degraded_link_health": min(degraded_scores),
            "mean_recovery_link_health": sum(healthy_recovery_scores) / len(healthy_recovery_scores),
            "degradation_detection_ms": degradation_detection_seconds * 1_000,
            "route_shift_ms": route_shift_seconds * 1_000,
            "recovery_to_restore_ms": (restore_decision_at - recovery_started) * 1_000,
            "route_restore_ms": route_restore_seconds * 1_000,
            "hold_down_observed_ms": (restore_decision_at - penalty_decision_at) * 1_000,
            "samples": sample_number,
            "final_anre_state": controller.anre.state.value,
            "route_before": route_before,
            "route_after_penalty": route_backup,
            "route_after_restoration": route_restored,
        }
        units = {
            "healthy_link_health": "score",
            "minimum_degraded_link_health": "score",
            "mean_recovery_link_health": "score",
            "degradation_detection_ms": "ms",
            "route_shift_ms": "ms",
            "recovery_to_restore_ms": "ms",
            "route_restore_ms": "ms",
            "hold_down_observed_ms": "ms",
            "samples": "count",
        }
        for metric_name, unit in units.items():
            database.log_result(
                run_id,
                scenario="CLOSED_LOOP_ADAPTIVE_ROUTING",
                metric_name=metric_name,
                metric_value=float(summary[metric_name]),
                unit=unit,
            )
        database.log_event(
            run_id,
            EventRecord(
                component="EXPERIMENT",
                event_type="ADAPTIVE_ROUTING_EXPERIMENT_COMPLETE",
                message="Closed-loop degradation, failover, hold-down, and restoration measured",
                metadata={
                    "degradation_detection_ms": summary["degradation_detection_ms"],
                    "hold_down_observed_ms": summary["hold_down_observed_ms"],
                },
            ),
        )
        database.finish_run(run_id, "COMPLETED")
        info(
            f"*** Repetition {repetition}: detection="
            f"{summary['degradation_detection_ms']:.1f} ms, shift="
            f"{summary['route_shift_ms']:.1f} ms, hold-down="
            f"{summary['hold_down_observed_ms']:.1f} ms\n"
        )
        return summary
    except Exception as error:
        info(f"*** Adaptive-routing repetition {repetition} FAILED: {error}\n")
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
        if nodes and impaired:
            try:
                set_primary_link_impairment(
                    nodes,
                    delay_ms=RESTORED_DELAY_MS,
                    loss_percent=RESTORED_LOSS_PERCENT,
                )
            except Exception:
                pass
        if nodes and costs_penalized:
            try:
                set_primary_link_cost(nodes, PRIMARY_COST)
            except Exception:
                pass
        for router_name in ("r1", "r2", "r3"):
            if router_name in nodes:
                stop_frr(nodes[router_name])
        if net is not None:
            net.stop()
        if database is not None:
            database.close()


def _save_artifacts(
    group_id: str, summaries: list[dict[str, Any]]
) -> tuple[Path, Path]:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_ROOT / f"adaptive_routing_{group_id}.csv"
    graph_path = RESULTS_ROOT / f"adaptive_routing_{group_id}.png"
    frame = pd.DataFrame(summaries)
    frame.to_csv(csv_path, index=False)
    formal = frame["repetition"].nunique() >= 10

    metrics = (
        ("degradation_detection_ms", "Persistent degradation detection", "ms"),
        ("route_shift_ms", "OSPF route shift after cost change", "ms"),
        ("hold_down_observed_ms", "Observed routing hold-down", "ms"),
        ("route_restore_ms", "Primary route restoration", "ms"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    figure.suptitle(
        f"CampusShield Experiment 5 - Closed-loop Adaptive Routing "
        f"({'Formal' if formal else 'Pilot'}, n={len(frame)}; {group_id})"
    )
    for axis, (metric, title, unit) in zip(axes.flat, metrics):
        axis.bar(frame["repetition"].astype(str), frame[metric], color="#0ea5e9")
        axis.set(title=title, xlabel="Repetition", ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)
    return csv_path, graph_path


def run_adaptive_routing_experiment(
    repetitions: int,
    hold_down_seconds: float,
    database_path: Path,
) -> bool:
    if os.geteuid() != 0:
        raise PermissionError("Mininet experiments must be run with sudo")
    if repetitions < 1:
        raise ValueError("Repetitions must be at least 1")
    if hold_down_seconds < 5:
        raise ValueError("Hold-down must be at least 5 seconds")
    group_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    info(
        f"*** Experiment 5 group {group_id}; {repetitions} repetition(s); "
        f"hold-down={hold_down_seconds:.0f}s\n"
    )
    summaries = [
        _run_repetition(
            database_path=database_path,
            group_id=group_id,
            repetition=repetition,
            hold_down_seconds=hold_down_seconds,
        )
        for repetition in range(1, repetitions + 1)
    ]
    csv_path, graph_path = _save_artifacts(group_id, summaries)
    frame = pd.DataFrame(summaries)
    info("\n*** Experiment 5 measured summary\n")
    for metric in (
        "degradation_detection_ms",
        "route_shift_ms",
        "hold_down_observed_ms",
        "route_restore_ms",
    ):
        stats = describe_95(frame[metric])
        info(
            f"{metric}: {stats.mean:.2f} ms "
            f"(95% CI {stats.ci95_low:.2f}-{stats.ci95_high:.2f})\n"
        )
    info(
        f"Results CSV: {csv_path}\nResults graph: {graph_path}\n"
        "*** CLOSED-LOOP ADAPTIVE ROUTING EXPERIMENT PASSED\n"
    )
    return True
