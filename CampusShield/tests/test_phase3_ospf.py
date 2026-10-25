"""Unit tests for the Phase 3 matched OSPF experiment design."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ospf_design import (  # noqa: E402
    SCENARIOS,
    h7_supported,
    recovery_improvement_percent,
    scenario_order_for_repetition,
)


class Phase3OspfDesignTests(unittest.TestCase):
    def test_order_rotates_between_repetitions(self):
        self.assertEqual(scenario_order_for_repetition(1), SCENARIOS)
        self.assertEqual(scenario_order_for_repetition(2), tuple(reversed(SCENARIOS)))
        self.assertEqual(scenario_order_for_repetition(3), SCENARIOS)

    def test_h7_uses_measured_direction(self):
        self.assertTrue(h7_supported(40_000, 1_200))
        self.assertFalse(h7_supported(1_000, 1_200))

    def test_improvement_percentage(self):
        self.assertAlmostEqual(recovery_improvement_percent(40_000, 1_000), 97.5)
        with self.assertRaises(ValueError):
            recovery_improvement_percent(0, 1_000)

    def test_repetition_must_be_positive(self):
        with self.assertRaises(ValueError):
            scenario_order_for_repetition(0)


if __name__ == "__main__":
    unittest.main()
