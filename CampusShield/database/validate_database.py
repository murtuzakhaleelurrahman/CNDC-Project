#!/usr/bin/env python3
"""Validate the Phase 10 schema without creating experimental results."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database.storage import (  # noqa: E402
    DEFAULT_DATABASE_PATH,
    CampusShieldDatabase,
    EventRecord,
    TelemetryRecord,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="database path (default: database/campusshield.db)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    notes = (
        "Synthetic validation rows only. This run is not experimental data."
    )
    with CampusShieldDatabase(args.database) as database:
        run_id = database.start_run(
            "SQLite persistence validation",
            "VALIDATION",
            is_experimental=False,
            notes=notes,
        )
        database.log_telemetry(
            run_id,
            TelemetryRecord(
                timestamp_utc=utc_now(),
                router="r1",
                source_host="emergency1",
                target_ip="10.10.20.10",
                interface="r1-eth0",
                rtt_ms=10.0,
                packet_loss_percent=0.0,
                jitter_ms=0.2,
                tx_mbps=5.0,
                rx_mbps=1.0,
                utilization_percent=5.0,
                nhs=90.0,
                anre_state="NORMAL",
                link_name="R1-R2",
                link_health=92.0,
                qos_policy="NORMAL",
                route_next_hop="10.10.255.2",
                route_interface="r1-eth0",
                route_state="up",
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="ANRE",
                event_type="STATE_TRANSITION",
                message="Validation of ANRE event persistence",
                previous_state="NORMAL",
                current_state="DEGRADED",
                action="APPLY_QOS",
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="OSPF_COST_CHANGE",
                message="Validation of routing action persistence",
                action="PENALIZE",
                link_name="R1-R2",
                old_value="10",
                new_value="100",
            ),
        )
        database.log_event(
            run_id,
            EventRecord(
                component="ROUTING",
                event_type="RECOVERY",
                message="Validation of recovery event persistence",
                action="RESTORE",
                link_name="R1-R2",
                old_value="100",
                new_value="10",
            ),
        )
        database.log_result(
            run_id,
            scenario="VALIDATION_ONLY",
            traffic_class="emergency",
            metric_name="rtt_ms",
            metric_value=10.0,
            unit="ms",
        )
        database.log_result(
            run_id,
            scenario="VALIDATION_ONLY",
            traffic_class="emergency",
            metric_name="packet_loss_percent",
            metric_value=0.0,
            unit="percent",
        )
        database.finish_run(run_id)

        counts = {
            table: database.count_rows(table, run_id)
            for table in (
                "telemetry_samples", "controller_events", "experiment_results"
            )
        }
        run = database.connection.execute(
            "SELECT * FROM experiment_runs WHERE id = ?", (run_id,)
        ).fetchone()
        checks = {
            "WAL mode": database.journal_mode() == "wal",
            "validation run is non-experimental": run["is_experimental"] == 0,
            "run completed": run["status"] == "COMPLETED",
            "one telemetry row": counts["telemetry_samples"] == 1,
            "three event rows": counts["controller_events"] == 3,
            "two result rows": counts["experiment_results"] == 2,
        }

    # The dashboard will be a separate reader process. Opening another
    # connection here verifies that it can read the committed WAL data.
    reader = sqlite3.connect(args.database, timeout=5)
    try:
        visible = reader.execute(
            "SELECT COUNT(*) FROM telemetry_samples WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        checks["independent reader sees committed data"] = visible == 1
    finally:
        reader.close()

    for description, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {description}")
    print(f"Database: {args.database.resolve()}")
    print(f"Validation run ID: {run_id}")
    print(f"Rows written for this run: {counts}")
    if not all(checks.values()):
        return 1
    print("SQLITE PERSISTENCE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
