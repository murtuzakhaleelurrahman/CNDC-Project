"""Integration test for the ten-repetition Phase 2 analysis output."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
TEST_TMP_ROOT = PROJECT_ROOT / "tmp" / "tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

from experiments.congestion_design import SCENARIOS  # noqa: E402

try:  # The lightweight Windows test runtime does not bundle matplotlib.
    from experiments import analyze_results  # noqa: E402
except ModuleNotFoundError as error:  # pragma: no cover - environment dependent
    if error.name != "matplotlib":
        raise
    analyze_results = None


class Phase2AnalysisTests(unittest.TestCase):
    @unittest.skipUnless(analyze_results is not None, "matplotlib is not installed")
    def test_three_arm_analysis_writes_confidence_intervals(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as directory:
            output_root = Path(directory)
            congestion_path = output_root / "congestion.csv"
            failure_path = output_root / "failure.csv"
            congestion_rows = []
            for repetition in range(1, 11):
                for scenario_index, scenario in enumerate(SCENARIOS):
                    congestion_rows.append(
                        {
                            "group_id": "phase2-test",
                            "repetition": repetition,
                            "scenario": scenario,
                            "emergency_throughput_mbps": 20 + scenario_index * 10 + repetition * 0.1,
                            "emergency_udp_loss_percent": 30 - scenario_index * 8 + repetition * 0.05,
                            "emergency_udp_jitter_ms": 2 - scenario_index * 0.3 + repetition * 0.01,
                            "mean_rtt_ms": 25 - scenario_index * 2 + repetition * 0.02,
                            "mean_nhs": 60 + scenario_index * 4 + repetition * 0.1,
                            "bulk_throughput_mbps": 30 - scenario_index * 5 + repetition * 0.1,
                            "academic_throughput_mbps": 40 - scenario_index * 2 + repetition * 0.1,
                            "recovery_mean_nhs": 80 + scenario_index + repetition * 0.1,
                            "recovery_nhs_change": 15 + scenario_index + repetition * 0.1,
                            "emergency_queue_drops_congestion": 50 - scenario_index * 10 + repetition,
                            "peak_emergency_backlog_bytes": 5000 - scenario_index * 500 + repetition * 10,
                            "controller_response_seconds": (
                                3 + repetition * 0.05 if scenario == "ANRE_ON" else None
                            ),
                            "recovery_to_normal_seconds": (
                                7 + repetition * 0.05 if scenario == "ANRE_ON" else None
                            ),
                        }
                    )
            pd.DataFrame(congestion_rows).to_csv(congestion_path, index=False)
            pd.DataFrame(
                [
                    {
                        "group_id": "failure-test",
                        "repetition": repetition,
                        "packets_lost_during_convergence": repetition,
                        "service_interruption_ms": 100 + repetition,
                        "route_convergence_ms": 80 + repetition,
                        "primary_restoration_ms": 120 + repetition,
                        "route_after_failure": "via 10.10.255.6 dev r1-eth1",
                        "route_after_restoration": "via 10.10.255.2 dev r1-eth0",
                    }
                    for repetition in range(1, 11)
                ]
            ).to_csv(failure_path, index=False)

            arguments = [
                "analyze_results.py",
                "--congestion-csv",
                str(congestion_path),
                "--failure-csv",
                str(failure_path),
            ]
            with patch.object(analyze_results, "RESULTS_ROOT", output_root), patch.object(
                sys, "argv", arguments
            ):
                self.assertEqual(analyze_results.main(), 0)

            summary = pd.read_csv(output_root / "core_experiment_summary.csv")
            congestion_summary = summary[
                summary["experiment"] == "THREE_ARM_CONGESTION"
            ]
            self.assertEqual(
                set(congestion_summary["scenario"]), set(SCENARIOS)
            )
            self.assertTrue(congestion_summary["ci95_low"].notna().all())
            self.assertTrue(congestion_summary["ci95_high"].notna().all())
            self.assertTrue((congestion_summary["n"] == 10).all())
            analysis = (output_root / "core_experiment_analysis.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Tuned static", analysis)
            self.assertIn("95% CI", analysis)


if __name__ == "__main__":
    unittest.main()
