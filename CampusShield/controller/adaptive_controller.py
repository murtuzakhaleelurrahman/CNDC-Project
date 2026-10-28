"""Compose ANRE QoS and adaptive-routing decisions in one control loop."""

from __future__ import annotations

from dataclasses import dataclass

from controller.anre import AnreStateMachine, StateDecision
from controller.routing_manager import AdaptiveRoutingController, RoutingDecision


@dataclass(frozen=True)
class CombinedDecision:
    """One observation's QoS-state and routing decisions."""

    anre: StateDecision
    routing: RoutingDecision


class CampusShieldAdaptiveController:
    """Evaluate network and primary-link health through one controller API."""

    def __init__(
        self,
        *,
        anre: AnreStateMachine | None = None,
        routing: AdaptiveRoutingController | None = None,
    ) -> None:
        self.anre = anre or AnreStateMachine()
        self.routing = routing or AdaptiveRoutingController()

    def observe(
        self,
        network_health: float,
        primary_link_health: float,
        *,
        now: float | None = None,
    ) -> CombinedDecision:
        return CombinedDecision(
            anre=self.anre.evaluate_score(network_health),
            routing=self.routing.observe(primary_link_health, now=now),
        )
