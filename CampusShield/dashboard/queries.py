"""Read-only SQLite queries used by the CampusShield dashboard."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _connect_read_only(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"CampusShield database not found: {path}")
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _rows(connection: sqlite3.Connection, sql: str, values=()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, values).fetchall()]


def load_runs(database_path: str | Path) -> list[dict[str, Any]]:
    with _connect_read_only(database_path) as connection:
        return _rows(
            connection,
            """
            SELECT
                r.*,
                (SELECT COUNT(*) FROM telemetry_samples t WHERE t.run_id = r.id)
                    AS telemetry_count,
                (SELECT COUNT(*) FROM controller_events e WHERE e.run_id = r.id)
                    AS event_count,
                (SELECT COUNT(*) FROM experiment_results x WHERE x.run_id = r.id)
                    AS result_count
            FROM experiment_runs r
            ORDER BY r.id DESC
            """,
        )


def load_latest_telemetry(
    database_path: str | Path, run_id: int
) -> dict[str, Any] | None:
    with _connect_read_only(database_path) as connection:
        rows = _rows(
            connection,
            """
            SELECT * FROM telemetry_samples
            WHERE run_id = ?
            ORDER BY timestamp_utc DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        )
    return rows[0] if rows else None


def load_telemetry_history(
    database_path: str | Path, run_id: int, limit: int = 300
) -> list[dict[str, Any]]:
    with _connect_read_only(database_path) as connection:
        return _rows(
            connection,
            """
            SELECT * FROM (
                SELECT * FROM telemetry_samples
                WHERE run_id = ?
                ORDER BY timestamp_utc DESC, id DESC
                LIMIT ?
            )
            ORDER BY timestamp_utc ASC, id ASC
            """,
            (run_id, limit),
        )


def load_recent_events(
    database_path: str | Path, run_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    with _connect_read_only(database_path) as connection:
        return _rows(
            connection,
            """
            SELECT * FROM controller_events
            WHERE run_id = ?
            ORDER BY timestamp_utc DESC, id DESC
            LIMIT ?
            """,
            (run_id, limit),
        )


def load_results(
    database_path: str | Path, run_id: int
) -> list[dict[str, Any]]:
    with _connect_read_only(database_path) as connection:
        return _rows(
            connection,
            """
            SELECT * FROM experiment_results
            WHERE run_id = ?
            ORDER BY scenario, traffic_class, metric_name
            """,
            (run_id,),
        )

