"""Pure design helpers for the Phase 3 OSPF optimization experiment."""

from __future__ import annotations


SCENARIOS = ("OSPF_DEFAULT", "OSPF_TUNED")
TUNED_DEAD_INTERVAL_SECONDS = 1.0
TUNED_HELLO_MULTIPLIER = 5
TUNED_SPF_DELAY_MS = 0
TUNED_SPF_INITIAL_HOLD_MS = 50
TUNED_SPF_MAX_HOLD_MS = 1_000


def scenario_order_for_repetition(repetition: int) -> tuple[str, str]:
    """Alternate scenario order to reduce systematic warm-up bias."""
    if repetition < 1:
        raise ValueError("Repetition must be at least 1")
    return SCENARIOS if repetition % 2 else tuple(reversed(SCENARIOS))


def h7_supported(default_recovery_ms: float, tuned_recovery_ms: float) -> bool:
    """Evaluate the proposal's directional H7 without assuming its result."""
    return tuned_recovery_ms < default_recovery_ms


def recovery_improvement_percent(
    default_recovery_ms: float, tuned_recovery_ms: float
) -> float:
    """Return positive improvement when tuning reduces recovery time."""
    if default_recovery_ms <= 0:
        raise ValueError("Default recovery time must be positive")
    return (
        (default_recovery_ms - tuned_recovery_ms) / default_recovery_ms
    ) * 100.0
