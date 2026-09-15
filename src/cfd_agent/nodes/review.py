"""Graph routing around the failure diagnosis and repair service."""

from __future__ import annotations

import copy

from langgraph.types import Command, interrupt

from cfd_agent.services.contracts import ParameterConfirmationPayload, RepairDecision
from cfd_agent.services.reviewer import diagnose_failure, execute_repair
from cfd_agent.state import PipelineState


def review_failure(state: PipelineState) -> dict:
    return diagnose_failure(state)


def apply_repair(state: PipelineState) -> Command:
    outcome = execute_repair(state)
    return Command(update=outcome.update, goto=outcome.goto)


def parameter_confirmation(state: PipelineState) -> Command:
    """Approve one numeric repair while the original Fluent session remains alive."""
    response = interrupt({"kind": "parameter_confirmation", **state["parameter_confirmation"]})
    payload = ParameterConfirmationPayload.model_validate(response)
    if payload.action == "cancel":
        return Command(update={"parameter_confirmation": {}}, goto="cancelled")
    decision_data = copy.deepcopy(state["repair_decision"])
    if payload.parameter_value is not None:
        decision_data["parameters"]["value"] = payload.parameter_value
    decision = RepairDecision.model_validate(decision_data)
    history = copy.deepcopy(state["repair_history"])
    history[-1]["user_confirmation"] = {
        **state["parameter_confirmation"],
        "approved_value": decision.parameters["value"],
        "choice": "suggestion" if payload.parameter_value is None else "manual",
    }
    update = {"repair_history": history, "repair_decision": decision.model_dump(mode="json")}
    outcome = execute_repair({**state, **update}, user_approved=True)
    return Command(
        update={**update, **outcome.update, "parameter_confirmation": {}},
        goto=outcome.goto,
    )
