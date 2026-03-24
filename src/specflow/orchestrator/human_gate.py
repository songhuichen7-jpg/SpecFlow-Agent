from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from specflow.models import ExecutionMode
from specflow.orchestrator.models import HumanGateDecision, HumanGateRequest


class HumanGate(Protocol):
    """Protocol for interactive or scripted human gate providers."""

    def decide(self, request: HumanGateRequest) -> HumanGateDecision | None:
        """Return a decision or `None` when the gate should remain pending."""


@dataclass(frozen=True)
class AutoApproveHumanGate:
    """Always approve requests with a deterministic reason."""

    reason: str = "Auto-approved by human gate policy."

    def decide(self, request: HumanGateRequest) -> HumanGateDecision:
        return HumanGateDecision(
            approved=True,
            reason=f"{self.reason} gate={request.gate_name}",
        )


@dataclass(frozen=True)
class PendingHumanGate:
    """Keep every request pending until an explicit resume decision arrives."""

    def decide(self, request: HumanGateRequest) -> HumanGateDecision | None:
        return None


class QueueHumanGate:
    """Consume a predefined queue of decisions for deterministic tests."""

    def __init__(self, decisions: list[HumanGateDecision | bool]) -> None:
        self._decisions = deque(decisions)

    def decide(self, request: HumanGateRequest) -> HumanGateDecision | None:
        if not self._decisions:
            return None
        value = self._decisions.popleft()
        if isinstance(value, HumanGateDecision):
            return value
        if value:
            return HumanGateDecision(
                approved=True,
                reason=f"Approved queued gate {request.gate_name}.",
            )
        return HumanGateDecision(
            approved=False,
            reason=f"Rejected queued gate {request.gate_name}.",
        )


class InteractiveHumanGate:
    """Simple terminal-oriented gate for future CLI integration."""

    def __init__(self, input_fn: Callable[[str], str] = input) -> None:
        self._input = input_fn

    def decide(self, request: HumanGateRequest) -> HumanGateDecision | None:
        prompt = f"{request.message} [y/N]: "
        answer = self._input(prompt).strip().lower()
        if answer in {"y", "yes"}:
            return HumanGateDecision(approved=True, reason="Approved interactively.")
        if answer in {"n", "no", ""}:
            return HumanGateDecision(approved=False, reason="Rejected interactively.")
        return None


def resolve_gate_decision(
    *,
    mode: ExecutionMode,
    request: HumanGateRequest,
    gate: HumanGate,
    explicit_decision: HumanGateDecision | bool | None = None,
) -> HumanGateDecision | None:
    """Resolve a gate decision from debug mode, explicit input, or gate policy."""

    if mode is ExecutionMode.DEBUG:
        return HumanGateDecision(
            approved=True,
            reason=f"Debug mode bypassed gate {request.gate_name}.",
        )
    if explicit_decision is None:
        return gate.decide(request)
    if isinstance(explicit_decision, HumanGateDecision):
        return explicit_decision
    if explicit_decision:
        return HumanGateDecision(
            approved=True,
            reason=f"Approved via explicit decision for {request.gate_name}.",
        )
    return HumanGateDecision(
        approved=False,
        reason=f"Rejected via explicit decision for {request.gate_name}.",
    )
