"""Unit tests for the Phase 4 closed-loop adaptive-routing design."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from controller.adaptive_controller import CampusShieldAdaptiveController  # noqa: E402
from controller.routing_manager import AdaptiveRoutingController, RoutingAction  # noqa: E402
from experiments.adaptive_routing_design import (  # noqa: E402
    hold_down_respected,
    route_shift_valid,
)


class Phase4AdaptiveRoutingTests(unittest.TestCase):
    def test_one_loop_drives_anre_and_routing(self):
        controller = CampusShieldAdaptiveController(
            routing=AdaptiveRoutingController(hold_down_seconds=5)
        )
        first = controller.observe(40, 40, now=0)
        second = controller.observe(40, 40, now=1)
        third = controller.observe(40, 40, now=2)
        self.assertEqual(first.anre.current_state.value, "NORMAL")
        self.assertEqual(second.anre.current_state.value, "CRITICAL")
        self.assertIs(third.routing.action, RoutingAction.PENALIZE)

        for timestamp in range(3, 7):
            held = controller.observe(90, 90, now=timestamp)
            self.assertIs(held.routing.action, RoutingAction.NONE)
        controller.observe(90, 90, now=7)
        controller.observe(90, 90, now=8)
        restored = controller.observe(90, 90, now=9)
        self.assertIs(restored.routing.action, RoutingAction.RESTORE)

    def test_route_sequence_and_hold_down_checks(self):
        self.assertTrue(
            route_shift_valid(
                "via 10.10.255.2 dev r1-eth0",
                "via 10.10.255.6 dev r1-eth1",
                "via 10.10.255.2 dev r1-eth0",
            )
        )
        self.assertFalse(route_shift_valid("primary", "backup", "primary"))
        self.assertTrue(hold_down_respected(10, 55, 45))
        self.assertFalse(hold_down_respected(10, 54.9, 45))


if __name__ == "__main__":
    unittest.main()
