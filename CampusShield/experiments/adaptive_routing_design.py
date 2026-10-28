"""Pure constants and checks for the Phase 4 adaptive-routing experiment."""

from __future__ import annotations


DEGRADATION_DELAY_MS = 80
DEGRADATION_LOSS_PERCENT = 30.0
RESTORED_DELAY_MS = 5
RESTORED_LOSS_PERCENT = 0.0
HOLD_DOWN_SECONDS = 45.0


def route_shift_valid(
    before: str, degraded: str, restored: str
) -> bool:
    """Check the expected primary -> backup -> primary route sequence."""
    return (
        "via 10.10.255.2" in before
        and "via 10.10.255.6" in degraded
        and "via 10.10.255.2" in restored
    )


def hold_down_respected(
    penalized_at: float, restored_at: float, hold_down_seconds: float
) -> bool:
    """Verify restoration did not occur before the configured hold-down."""
    return restored_at - penalized_at >= hold_down_seconds
