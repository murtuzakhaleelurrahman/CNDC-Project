"""Environment-aware baseline calibration for CampusShield."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from controller.health_score import HealthMetrics, HealthThresholds


# Initial experimental parameters. They remain easy to tune and must be
# documented if changed after pilot experiments.
RTT_THRESHOLD_MULTIPLIER = 3.0
LOSS_THRESHOLD_MULTIPLIER = 3.0
JITTER_THRESHOLD_MULTIPLIER = 3.0
RTT_MINIMUM_MS = 20.0
LOSS_MINIMUM_PERCENT = 2.0
JITTER_MINIMUM_MS = 5.0


@dataclass(frozen=True)
class BaselineCalibration:
    sample_count: int
    duration_seconds: float
    rtt_base_ms: float
    loss_base_percent: float
    jitter_base_ms: float
    utilization_base_percent: float
    thresholds: HealthThresholds

    def as_health_metrics(self) -> HealthMetrics:
        return HealthMetrics(
            rtt_ms=self.rtt_base_ms,
            loss_percent=self.loss_base_percent,
            jitter_ms=self.jitter_base_ms,
            bandwidth_used_mbps=(
                self.utilization_base_percent / 100.0
            ) * self.thresholds.capacity_mbps,
        )


def summarize_baseline_snapshots(
    snapshots: list[dict[str, Any]],
    duration_seconds: float,
    capacity_mbps: float,
) -> BaselineCalibration:
    """Derive the baseline vector and thresholds from collected snapshots."""
    if not snapshots:
        raise ValueError("At least one telemetry snapshot is required")

    rtt_base = sum(item["probe"]["average_rtt_ms"] for item in snapshots) / len(snapshots)
    loss_base = sum(item["probe"]["packet_loss_percent"] for item in snapshots) / len(snapshots)
    jitter_base = sum(item["probe"]["jitter_ms"] for item in snapshots) / len(snapshots)
    utilization_base = sum(
        item["interface"]["tx_utilization_percent"] for item in snapshots
    ) / len(snapshots)

    thresholds = HealthThresholds(
        rtt_ms=max(RTT_MINIMUM_MS, RTT_THRESHOLD_MULTIPLIER * rtt_base),
        loss_percent=max(
            LOSS_MINIMUM_PERCENT,
            LOSS_THRESHOLD_MULTIPLIER * loss_base,
        ),
        jitter_ms=max(
            JITTER_MINIMUM_MS,
            JITTER_THRESHOLD_MULTIPLIER * jitter_base,
        ),
        capacity_mbps=capacity_mbps,
    )
    return BaselineCalibration(
        sample_count=len(snapshots),
        duration_seconds=duration_seconds,
        rtt_base_ms=rtt_base,
        loss_base_percent=loss_base,
        jitter_base_ms=jitter_base,
        utilization_base_percent=utilization_base,
        thresholds=thresholds,
    )


def calibrate_baseline(
    snapshot_provider: Callable[[], dict[str, Any]],
    duration_seconds: float,
    capacity_mbps: float,
    progress_callback: Callable[[int, dict[str, Any]], None] | None = None,
) -> BaselineCalibration:
    """Average repeated healthy-network telemetry over the requested period."""
    if duration_seconds < 3:
        raise ValueError("Calibration duration must be at least 3 seconds")

    started = time.monotonic()
    snapshots: list[dict[str, Any]] = []
    while time.monotonic() - started < duration_seconds:
        snapshot = snapshot_provider()
        snapshots.append(snapshot)
        if progress_callback:
            progress_callback(len(snapshots), snapshot)

    elapsed = time.monotonic() - started
    return summarize_baseline_snapshots(
        snapshots=snapshots,
        duration_seconds=elapsed,
        capacity_mbps=capacity_mbps,
    )

