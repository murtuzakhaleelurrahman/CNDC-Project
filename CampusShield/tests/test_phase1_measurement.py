"""Phase 1 tests for EF probes, queue parsing, and evidence persistence."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
TEST_TMP_ROOT = PROJECT_ROOT / "tmp" / "tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

from dashboard.queries import load_qos_class_history  # noqa: E402
from database.storage import (  # noqa: E402
    CampusShieldDatabase,
    TelemetryRecord,
    utc_now,
)
from experiments.congestion_design import (  # noqa: E402
    SCENARIOS,
    build_phase_plan,
    initial_policy_for_scenario,
    queue_counter_delta,
    scenario_order_for_repetition,
)
from experiments.statistics_utils import describe_95  # noqa: E402
from telemetry.probe_monitor import collect_probe_metrics  # noqa: E402
from telemetry.qos_monitor import parse_tc_class_stats  # noqa: E402


PING_OUTPUT = """PING 10.10.20.10 (10.10.20.10) 56(84) bytes of data.
64 bytes from 10.10.20.10: icmp_seq=1 ttl=63 time=10.2 ms
64 bytes from 10.10.20.10: icmp_seq=2 ttl=63 time=10.6 ms

--- 10.10.20.10 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 200ms
"""


TC_OUTPUT = """class htb 10:1 root rate 100Mbit ceil 100Mbit burst 1597b cburst 1597b
 Sent 9000 bytes 90 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
class htb 10:10 parent 10:1 leaf 100: prio 0 rate 20Mbit ceil 20Mbit
 Sent 4000 bytes 40 pkt (dropped 3, overlimits 9 requeues 1)
 backlog 2Kb 2p requeues 1
class htb 10:20 parent 10:1 leaf 200: prio 1 rate 50Mbit ceil 50Mbit
 Sent 3000 bytes 30 pkt (dropped 2, overlimits 4 requeues 0)
 backlog 512b 1p requeues 0
class htb 10:30 parent 10:1 leaf 300: prio 2 rate 30Mbit ceil 30Mbit
 Sent 2000 bytes 20 pkt (dropped 7, overlimits 12 requeues 2)
 backlog 0b 0p requeues 2
"""


class _Process:
    def communicate(self):
        return PING_OUTPUT, ""


class _ProbeNode:
    def __init__(self):
        self.command: list[str] = []

    def popen(self, command):
        self.command = command
        return _Process()


class Phase1MeasurementTests(unittest.TestCase):
    def test_service_probe_is_ef_marked(self):
        node = _ProbeNode()
        metrics = collect_probe_metrics(node, "10.10.20.10", count=2)

        self.assertIn("-Q", node.command)
        self.assertEqual(node.command[node.command.index("-Q") + 1], "184")
        self.assertEqual(metrics.dscp_value, 46)
        self.assertEqual(metrics.packets_received, 2)
        self.assertAlmostEqual(metrics.average_rtt_ms, 10.4)
        self.assertAlmostEqual(metrics.jitter_ms, 0.4)

    def test_tc_parser_preserves_each_class(self):
        stats = parse_tc_class_stats(TC_OUTPUT)

        self.assertEqual(set(stats), {"emergency", "academic", "bulk"})
        self.assertEqual(stats["emergency"].dscp_value, 46)
        self.assertEqual(stats["emergency"].dropped_packets, 3)
        self.assertEqual(stats["emergency"].backlog_bytes, 2_000)
        self.assertEqual(stats["academic"].backlog_packets, 1)
        self.assertEqual(stats["bulk"].overlimits, 12)

    def test_queue_evidence_is_committed_with_telemetry(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as directory:
            database_path = Path(directory) / "phase1.db"
            with CampusShieldDatabase(database_path) as database:
                run_id = database.start_run("Phase 1", "VALIDATION", is_experimental=False)
                queue_stats = {
                    name: {
                        "class_id": item.class_id,
                        "dscp_value": item.dscp_value,
                        "sent_bytes": item.sent_bytes,
                        "sent_packets": item.sent_packets,
                        "dropped_packets": item.dropped_packets,
                        "overlimits": item.overlimits,
                        "requeues": item.requeues,
                        "backlog_bytes": item.backlog_bytes,
                        "backlog_packets": item.backlog_packets,
                    }
                    for name, item in parse_tc_class_stats(TC_OUTPUT).items()
                }
                sample_id = database.log_telemetry(
                    run_id,
                    TelemetryRecord(
                        timestamp_utc=utc_now(),
                        router="r1",
                        source_host="emergency1",
                        target_ip="10.10.20.10",
                        interface="r1-eth0",
                        rtt_ms=10.4,
                        packet_loss_percent=0.0,
                        jitter_ms=0.4,
                        tx_mbps=10.0,
                        rx_mbps=0.1,
                        utilization_percent=10.0,
                        probe_dscp_value=46,
                        qos_classes=queue_stats,
                    ),
                )
                stored_probe = database.connection.execute(
                    "SELECT probe_dscp_value FROM telemetry_samples WHERE id = ?",
                    (sample_id,),
                ).fetchone()[0]
                self.assertEqual(stored_probe, 46)
                self.assertEqual(
                    database.connection.execute(
                        "SELECT COUNT(*) FROM qos_class_samples WHERE telemetry_sample_id = ?",
                        (sample_id,),
                    ).fetchone()[0],
                    3,
                )

            history = load_qos_class_history(database_path, run_id)
            self.assertEqual(len(history), 3)
            emergency = next(row for row in history if row["class_name"] == "emergency")
            self.assertEqual(emergency["dropped_packets"], 3)

    def test_existing_database_receives_non_destructive_schema_upgrade(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as directory:
            database_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE telemetry_samples (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL,
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
                    nhs REAL,
                    anre_state TEXT,
                    link_name TEXT,
                    link_health REAL,
                    qos_policy TEXT,
                    route_next_hop TEXT,
                    route_interface TEXT,
                    route_state TEXT
                )
                """
            )
            connection.commit()
            connection.close()

            with CampusShieldDatabase(database_path) as database:
                columns = {
                    row[1]
                    for row in database.connection.execute(
                        "PRAGMA table_info(telemetry_samples)"
                    )
                }
                self.assertIn("probe_dscp_value", columns)
                self.assertIsNotNone(
                    database.connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE name = 'qos_class_samples'"
                    ).fetchone()
                )
                self.assertEqual(
                    database.connection.execute("PRAGMA user_version").fetchone()[0],
                    2,
                )

    def test_phase2_design_has_three_matched_scenarios_and_phases(self):
        plan = build_phase_plan(10, 30, 20)
        self.assertEqual(SCENARIOS, ("ANRE_OFF", "STATIC_TUNED", "ANRE_ON"))
        self.assertEqual([phase.name for phase in plan], ["HEALTHY", "CONGESTION", "RECOVERY"])
        self.assertEqual(plan[1].emergency_udp_mbps, 60)
        self.assertTrue(plan[1].competing_tcp)
        self.assertFalse(plan[2].competing_tcp)
        self.assertEqual(initial_policy_for_scenario("STATIC_TUNED"), "CRITICAL")
        self.assertEqual(scenario_order_for_repetition(1), SCENARIOS)
        self.assertEqual(
            scenario_order_for_repetition(2),
            ("STATIC_TUNED", "ANRE_ON", "ANRE_OFF"),
        )

    def test_phase2_statistics_use_sample_sd_and_95_percent_ci(self):
        result = describe_95([1, 2, 3, 4, 5])
        self.assertEqual(result.count, 5)
        self.assertAlmostEqual(result.mean, 3.0)
        self.assertAlmostEqual(result.standard_deviation, 1.58113883)
        self.assertLess(result.ci95_low, result.mean)
        self.assertGreater(result.ci95_high, result.mean)

    def test_phase2_queue_delta_uses_cumulative_counters(self):
        rows = [
            {"emergency_dropped_packets": 4},
            {"emergency_dropped_packets": 7},
            {"emergency_dropped_packets": 11},
        ]
        self.assertEqual(
            queue_counter_delta(rows, "emergency_dropped_packets"), 7
        )


if __name__ == "__main__":
    unittest.main()
