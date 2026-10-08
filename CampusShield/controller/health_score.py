"""Normalized Network Health Score calculation from the proposal."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthThresholds:
    rtt_ms: float
    loss_percent: float
    jitter_ms: float
    capacity_mbps: float


@dataclass(frozen=True)
class HealthMetrics:
    rtt_ms: float
    loss_percent: float
    jitter_ms: float
    bandwidth_used_mbps: float


@dataclass(frozen=True)
class HealthScore:
    latency_normalized: float
    loss_normalized: float
    jitter_normalized: float
    utilization_normalized: float
    nhs: float


RTT_WEIGHT = 0.30
LOSS_WEIGHT = 0.30
JITTER_WEIGHT = 0.20
UTILIZATION_WEIGHT = 0.20


def _normalize(value: float, threshold: float) -> float:
    if threshold <= 0:
        raise ValueError("Health thresholds must be greater than zero")
    return min(100.0, max(0.0, (value / threshold) * 100.0))


def calculate_health_score(
    metrics: HealthMetrics, thresholds: HealthThresholds
) -> HealthScore:
    """Calculate the exact normalized weighted NHS defined in the proposal."""
    latency = _normalize(metrics.rtt_ms, thresholds.rtt_ms)
    loss = _normalize(metrics.loss_percent, thresholds.loss_percent)
    jitter = _normalize(metrics.jitter_ms, thresholds.jitter_ms)
    utilization = _normalize(
        metrics.bandwidth_used_mbps, thresholds.capacity_mbps
    )
    degradation = (
        RTT_WEIGHT * latency
        + LOSS_WEIGHT * loss
        + JITTER_WEIGHT * jitter
        + UTILIZATION_WEIGHT * utilization
    )
    return HealthScore(
        latency_normalized=latency,
        loss_normalized=loss,
        jitter_normalized=jitter,
        utilization_normalized=utilization,
        nhs=max(0.0, min(100.0, 100.0 - degradation)),
    )


def validate_health_score_formula() -> bool:
    """Check two known boundary cases without claiming experiment results."""
    thresholds = HealthThresholds(30.0, 2.0, 5.0, 100.0)
    perfect = calculate_health_score(
        HealthMetrics(0.0, 0.0, 0.0, 0.0), thresholds
    )
    fully_degraded = calculate_health_score(
        HealthMetrics(30.0, 2.0, 5.0, 100.0), thresholds
    )
    return abs(perfect.nhs - 100.0) < 0.001 and abs(fully_degraded.nhs) < 0.001

