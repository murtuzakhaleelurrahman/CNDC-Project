"""Pure experiment-design helpers for the Phase 2 congestion comparison."""

from __future__ import annotations

from dataclasses import dataclass


SCENARIOS = ("ANRE_OFF", "STATIC_TUNED", "ANRE_ON")


@dataclass(frozen=True)
class TrafficPhase:
    name: str
    duration_seconds: float
    emergency_udp_mbps: int
    competing_tcp: bool


def build_phase_plan(
    healthy_seconds: float,
    congestion_seconds: float,
    recovery_seconds: float,
) -> tuple[TrafficPhase, ...]:
    """Return matched healthy, congestion, and recovery windows."""
    if healthy_seconds < 3:
        raise ValueError("Healthy phase must be at least 3 seconds")
    if congestion_seconds < 8:
        raise ValueError("Congestion phase must be at least 8 seconds")
    if recovery_seconds < 5:
        raise ValueError("Recovery phase must be at least 5 seconds")
    return (
        TrafficPhase("HEALTHY", healthy_seconds, 10, False),
        TrafficPhase("CONGESTION", congestion_seconds, 60, True),
        TrafficPhase("RECOVERY", recovery_seconds, 10, False),
    )


def initial_policy_for_scenario(scenario: str) -> str:
    """Return the fixed starting policy used by each matched scenario."""
    if scenario in {"ANRE_OFF", "ANRE_ON"}:
        return "NORMAL"
    if scenario == "STATIC_TUNED":
        return "CRITICAL"
    raise ValueError(f"Unknown congestion scenario: {scenario}")


def scenario_order_for_repetition(repetition: int) -> tuple[str, ...]:
    """Rotate scenario order to reduce systematic run-order bias."""
    if repetition < 1:
        raise ValueError("Repetition numbers start at 1")
    offset = (repetition - 1) % len(SCENARIOS)
    return SCENARIOS[offset:] + SCENARIOS[:offset]


def queue_counter_delta(rows: list[dict[str, object]], field: str) -> int:
    """Return the non-negative counter change over one phase."""
    values = [int(row.get(field, 0) or 0) for row in rows]
    return max(0, max(values) - min(values)) if values else 0
