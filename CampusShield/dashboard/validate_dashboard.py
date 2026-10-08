#!/usr/bin/env python3
"""Check dashboard queries and render the Streamlit app without a browser."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.queries import (  # noqa: E402
    load_latest_telemetry,
    load_recent_events,
    load_results,
    load_runs,
    load_telemetry_history,
)


def main() -> int:
    database_path = PROJECT_ROOT / "database" / "campusshield.db"
    checks: dict[str, bool] = {"database exists": database_path.is_file()}
    if not checks["database exists"]:
        print("FAIL: database exists")
        print("Run: python3 database/validate_database.py")
        return 1

    runs = load_runs(database_path)
    checks["run list loaded"] = bool(runs)
    if not runs:
        print("FAIL: run list loaded")
        return 1

    run_id = int(runs[0]["id"])
    checks["latest telemetry loaded"] = (
        load_latest_telemetry(database_path, run_id) is not None
    )
    checks["telemetry history loaded"] = bool(
        load_telemetry_history(database_path, run_id)
    )
    checks["recent events loaded"] = bool(
        load_recent_events(database_path, run_id)
    )
    checks["result rows loaded"] = bool(load_results(database_path, run_id))

    os.environ["CAMPUSSHIELD_DB_PATH"] = str(database_path)
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"))
    app.run(timeout=15)
    checks["Streamlit rendered without exception"] = not list(app.exception)
    checks["dashboard title rendered"] = any(
        "CampusShield" in item.value for item in app.markdown
    )
    rendered_markup = "\n".join(item.value for item in app.markdown)
    checks["nine NOC sections available"] = bool(app.radio) and set(
        app.radio[0].options
    ) == {
        "Overview", "Topology", "Telemetry", "Routing", "QoS", "ANRE",
        "Experiments", "Events", "System",
    }
    checks["primary health evidence rendered"] = all(
        label in rendered_markup
        for label in (
            "Network health", "cs-score", "RTT", "Packet loss", "Jitter",
            "Utilization",
        )
    )

    for description, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {description}")
    if app.exception:
        for exception in app.exception:
            print(exception.value)
    if not all(checks.values()):
        return 1
    print("STREAMLIT DASHBOARD TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
