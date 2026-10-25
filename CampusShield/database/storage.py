"""Persistent SQLite storage for CampusShield telemetry and events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "campusshield.db"
SCHEMA_VERSION = 2


def utc_now() -> str:
    """Return a timezone-aware timestamp suitable for ordering and display."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TelemetryRecord:
    timestamp_utc: str
    router: str
    source_host: str
    target_ip: str
    interface: str
    rtt_ms: float
    packet_loss_percent: float
    jitter_ms: float
    tx_mbps: float
    rx_mbps: float
    utilization_percent: float
    probe_dscp_value: int | None = None
    qos_classes: Mapping[str, Mapping[str, Any]] | None = None
    nhs: float | None = None
    anre_state: str | None = None
    link_name: str | None = None
    link_health: float | None = None
    qos_policy: str | None = None
    route_next_hop: str | None = None
    route_interface: str | None = None
    route_state: str | None = None

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        nhs: float | None = None,
        anre_state: str | None = None,
        link_name: str | None = None,
        link_health: float | None = None,
        qos_policy: str | None = None,
    ) -> "TelemetryRecord":
        """Convert the telemetry worker's nested snapshot into a database row."""
        interface = snapshot["interface"]
        probe = snapshot["probe"]
        route = snapshot["route"]
        return cls(
            timestamp_utc=str(snapshot["timestamp_utc"]),
            router=str(snapshot["router"]),
            source_host=str(snapshot["source_host"]),
            target_ip=str(probe["target"]),
            interface=str(interface["interface"]),
            rtt_ms=float(probe["average_rtt_ms"]),
            packet_loss_percent=float(probe["packet_loss_percent"]),
            jitter_ms=float(probe["jitter_ms"]),
            tx_mbps=float(interface["tx_mbps"]),
            rx_mbps=float(interface["rx_mbps"]),
            utilization_percent=float(interface["tx_utilization_percent"]),
            probe_dscp_value=(
                int(probe["dscp_value"])
                if probe.get("dscp_value") is not None
                else None
            ),
            qos_classes=snapshot.get("qos_classes") or {},
            nhs=nhs,
            anre_state=anre_state,
            link_name=link_name,
            link_health=link_health,
            qos_policy=qos_policy,
            route_next_hop=str(route["next_hop"]),
            route_interface=str(route["interface"]),
            route_state=str(route["interface_state"]),
        )


@dataclass(frozen=True)
class EventRecord:
    component: str
    event_type: str
    message: str
    timestamp_utc: str = ""
    severity: str = "INFO"
    previous_state: str | None = None
    current_state: str | None = None
    action: str | None = None
    link_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    metadata: Mapping[str, Any] | None = None


class CampusShieldDatabase:
    """One short-transaction SQLite connection for one CampusShield process."""

    def __init__(
        self,
        path: str | Path = DEFAULT_DATABASE_PATH,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.path,
            timeout=busy_timeout_ms / 1_000,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    run_type TEXT NOT NULL,
                    is_experimental INTEGER NOT NULL DEFAULT 1
                        CHECK (is_experimental IN (0, 1)),
                    started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT,
                    status TEXT NOT NULL DEFAULT 'RUNNING',
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS telemetry_samples (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES experiment_runs(id),
                    timestamp_utc TEXT NOT NULL,
                    router TEXT NOT NULL,
                    source_host TEXT NOT NULL,
                    target_ip TEXT NOT NULL,
                    interface TEXT NOT NULL,
                    rtt_ms REAL NOT NULL,
                    packet_loss_percent REAL NOT NULL,
                    jitter_ms REAL NOT NULL,
                    tx_mbps REAL NOT NULL,
                    rx_mbps REAL NOT NULL,
                    utilization_percent REAL NOT NULL,
                    probe_dscp_value INTEGER,
                    nhs REAL,
                    anre_state TEXT,
                    link_name TEXT,
                    link_health REAL,
                    qos_policy TEXT,
                    route_next_hop TEXT,
                    route_interface TEXT,
                    route_state TEXT
                );

                CREATE TABLE IF NOT EXISTS qos_class_samples (
                    id INTEGER PRIMARY KEY,
                    telemetry_sample_id INTEGER NOT NULL
                        REFERENCES telemetry_samples(id) ON DELETE CASCADE,
                    class_name TEXT NOT NULL,
                    class_id INTEGER NOT NULL,
                    dscp_value INTEGER NOT NULL,
                    sent_bytes INTEGER NOT NULL,
                    sent_packets INTEGER NOT NULL,
                    dropped_packets INTEGER NOT NULL,
                    overlimits INTEGER NOT NULL,
                    requeues INTEGER NOT NULL,
                    backlog_bytes INTEGER NOT NULL,
                    backlog_packets INTEGER NOT NULL,
                    UNIQUE (telemetry_sample_id, class_id)
                );

                CREATE TABLE IF NOT EXISTS controller_events (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER REFERENCES experiment_runs(id),
                    timestamp_utc TEXT NOT NULL,
                    component TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    previous_state TEXT,
                    current_state TEXT,
                    action TEXT,
                    link_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_results (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES experiment_runs(id),
                    timestamp_utc TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    traffic_class TEXT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    unit TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_run_time
                    ON telemetry_samples(run_id, timestamp_utc);
                CREATE INDEX IF NOT EXISTS idx_qos_sample_class
                    ON qos_class_samples(telemetry_sample_id, class_name);
                CREATE INDEX IF NOT EXISTS idx_events_run_time
                    ON controller_events(run_id, timestamp_utc);
                CREATE INDEX IF NOT EXISTS idx_events_type
                    ON controller_events(event_type, timestamp_utc);
                CREATE INDEX IF NOT EXISTS idx_results_run_metric
                    ON experiment_results(run_id, metric_name);
                """
            )
            telemetry_columns = {
                row[1]
                for row in self.connection.execute(
                    "PRAGMA table_info(telemetry_samples)"
                )
            }
            if "probe_dscp_value" not in telemetry_columns:
                self.connection.execute(
                    "ALTER TABLE telemetry_samples ADD COLUMN probe_dscp_value INTEGER"
                )
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CampusShieldDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start_run(
        self,
        name: str,
        run_type: str,
        *,
        is_experimental: bool = True,
        notes: str | None = None,
    ) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO experiment_runs
                    (name, run_type, is_experimental, started_at_utc, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, run_type, int(is_experimental), utc_now(), notes),
            )
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str = "COMPLETED") -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE experiment_runs
                SET ended_at_utc = ?, status = ?
                WHERE id = ?
                """,
                (utc_now(), status, run_id),
            )

    def log_telemetry(self, run_id: int, record: TelemetryRecord) -> int:
        values = (
            run_id,
            record.timestamp_utc,
            record.router,
            record.source_host,
            record.target_ip,
            record.interface,
            record.rtt_ms,
            record.packet_loss_percent,
            record.jitter_ms,
            record.tx_mbps,
            record.rx_mbps,
            record.utilization_percent,
            record.probe_dscp_value,
            record.nhs,
            record.anre_state,
            record.link_name,
            record.link_health,
            record.qos_policy,
            record.route_next_hop,
            record.route_interface,
            record.route_state,
        )
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO telemetry_samples (
                    run_id, timestamp_utc, router, source_host, target_ip,
                    interface, rtt_ms, packet_loss_percent, jitter_ms,
                    tx_mbps, rx_mbps, utilization_percent, probe_dscp_value,
                    nhs, anre_state,
                    link_name, link_health, qos_policy, route_next_hop,
                    route_interface, route_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            telemetry_sample_id = int(cursor.lastrowid)
            for class_name, stats in (record.qos_classes or {}).items():
                self.connection.execute(
                    """
                    INSERT INTO qos_class_samples (
                        telemetry_sample_id, class_name, class_id, dscp_value,
                        sent_bytes, sent_packets, dropped_packets, overlimits,
                        requeues, backlog_bytes, backlog_packets
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telemetry_sample_id,
                        str(class_name),
                        int(stats["class_id"]),
                        int(stats["dscp_value"]),
                        int(stats["sent_bytes"]),
                        int(stats["sent_packets"]),
                        int(stats["dropped_packets"]),
                        int(stats["overlimits"]),
                        int(stats["requeues"]),
                        int(stats["backlog_bytes"]),
                        int(stats["backlog_packets"]),
                    ),
                )
        return telemetry_sample_id

    def log_event(self, run_id: int | None, event: EventRecord) -> int:
        timestamp = event.timestamp_utc or utc_now()
        metadata_json = (
            json.dumps(event.metadata, sort_keys=True)
            if event.metadata is not None
            else None
        )
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO controller_events (
                    run_id, timestamp_utc, component, event_type, severity,
                    message, previous_state, current_state, action, link_name,
                    old_value, new_value, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timestamp,
                    event.component,
                    event.event_type,
                    event.severity,
                    event.message,
                    event.previous_state,
                    event.current_state,
                    event.action,
                    event.link_name,
                    event.old_value,
                    event.new_value,
                    metadata_json,
                ),
            )
        return int(cursor.lastrowid)

    def log_result(
        self,
        run_id: int,
        *,
        scenario: str,
        metric_name: str,
        metric_value: float,
        unit: str,
        traffic_class: str | None = None,
    ) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO experiment_results (
                    run_id, timestamp_utc, scenario, traffic_class,
                    metric_name, metric_value, unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    utc_now(),
                    scenario,
                    traffic_class,
                    metric_name,
                    metric_value,
                    unit,
                ),
            )
        return int(cursor.lastrowid)

    def count_rows(self, table: str, run_id: int) -> int:
        allowed = {
            "telemetry_samples", "controller_events", "experiment_results"
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM {table} WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["count"])

    def journal_mode(self) -> str:
        row = self.connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower()

