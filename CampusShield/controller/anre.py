"""Adaptive Network Response Engine state and hysteresis logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from controller.health_score import (
    HealthMetrics,
    HealthScore,
    HealthThresholds,
    calculate_health_score,
)


class NetworkState(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class StateDecision:
    previous_state: NetworkState
    current_state: NetworkState
    nhs: float
    changed: bool
    candidate_state: NetworkState | None
    confirmation_count: int
    confirmation_required: int


class AnreStateMachine:
    """NHS state selection with entry and recovery confirmation."""

    def __init__(
        self,
        worsening_confirmations: int = 2,
        recovery_confirmations: int = 5,
    ) -> None:
        self.state = NetworkState.NORMAL
        self.worsening_confirmations = worsening_confirmations
        self.recovery_confirmations = recovery_confirmations
        self._candidate: NetworkState | None = None
        self._candidate_count = 0

    def _desired_state(self, nhs: float) -> NetworkState:
        # The gaps between entry and recovery thresholds are hysteresis bands.
        if self.state is NetworkState.NORMAL:
            if nhs < 50:
                return NetworkState.CRITICAL
            if nhs < 70:
                return NetworkState.DEGRADED
            return NetworkState.NORMAL

        if self.state is NetworkState.DEGRADED:
            if nhs < 45:
                return NetworkState.CRITICAL
            if nhs > 80:
                return NetworkState.NORMAL
            return NetworkState.DEGRADED

        # Recovery from CRITICAL is deliberately stepwise, never directly to
        # NORMAL, so one unusually good sample cannot undo protection.
        if nhs > 60:
            return NetworkState.DEGRADED
        return NetworkState.CRITICAL

    @staticmethod
    def _is_recovery(current: NetworkState, desired: NetworkState) -> bool:
        order = {
            NetworkState.CRITICAL: 0,
            NetworkState.DEGRADED: 1,
            NetworkState.NORMAL: 2,
        }
        return order[desired] > order[current]

    def evaluate_score(self, nhs: float) -> StateDecision:
        previous = self.state
        desired = self._desired_state(nhs)
        if desired is self.state:
            self._candidate = None
            self._candidate_count = 0
            return StateDecision(
                previous, self.state, nhs, False, None, 0, 0
            )

        if desired is self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = desired
            self._candidate_count = 1

        required = (
            self.recovery_confirmations
            if self._is_recovery(self.state, desired)
            else self.worsening_confirmations
        )
        changed = self._candidate_count >= required
        if changed:
            self.state = desired
            self._candidate = None
            self._candidate_count = 0

        return StateDecision(
            previous_state=previous,
            current_state=self.state,
            nhs=nhs,
            changed=changed,
            candidate_state=None if changed else desired,
            confirmation_count=0 if changed else self._candidate_count,
            confirmation_required=required,
        )

    def evaluate_metrics(
        self, metrics: HealthMetrics, thresholds: HealthThresholds
    ) -> tuple[HealthScore, StateDecision]:
        score = calculate_health_score(metrics, thresholds)
        return score, self.evaluate_score(score.nhs)


def validate_hysteresis_logic() -> bool:
    """Deterministically verify entry, recovery, and noise rejection."""
    machine = AnreStateMachine()
    checks: list[bool] = []

    checks.append(machine.evaluate_score(65).current_state is NetworkState.NORMAL)
    checks.append(machine.evaluate_score(65).current_state is NetworkState.DEGRADED)
    checks.append(machine.evaluate_score(40).current_state is NetworkState.DEGRADED)
    checks.append(machine.evaluate_score(40).current_state is NetworkState.CRITICAL)

    # One good sample must not recover the state.
    checks.append(machine.evaluate_score(85).current_state is NetworkState.CRITICAL)
    machine.evaluate_score(40)  # cancel the candidate recovery

    for _ in range(4):
        checks.append(machine.evaluate_score(65).current_state is NetworkState.CRITICAL)
    checks.append(machine.evaluate_score(65).current_state is NetworkState.DEGRADED)
    for _ in range(4):
        checks.append(machine.evaluate_score(85).current_state is NetworkState.DEGRADED)
    checks.append(machine.evaluate_score(85).current_state is NetworkState.NORMAL)
    return all(checks)

