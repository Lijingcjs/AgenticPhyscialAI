"""Fluent task nodes using a persistent worker."""

from __future__ import annotations

from typing import Any

from cfd_agent.adapters.fluent import get_client
from cfd_agent.config import config_from_state
from cfd_agent.services.execution import _failed, _persist
from cfd_agent.state import PipelineState
from cfd_agent.workers.repair_protocol import STEP_ORDER

FLUENT_STEPS = STEP_ORDER[:-1]


def launch_fluent(state: PipelineState) -> dict[str, Any]:
    try:
        client = get_client(state["run_id"], state["runtime_dir"], config_from_state(state))
        client.call(
            "initialize",
            {
                "ui_mode": state["ui_mode"],
                "job": state["fluent_job"],
                "runtime_config": state.get("runtime_config", {}),
            },
        )
        result = client.call("launch")
        steps = dict(state.get("fluent_steps", {}))
        steps["launch"] = result
        return _persist(state, "launch_fluent", {"fluent_steps": steps, "error": ""})
    except Exception as error:
        return _failed(state, "launch_fluent", error)


def fluent_step(step: str):
    def execute(state: PipelineState) -> dict[str, Any]:
        try:
            client = get_client(state["run_id"], state["runtime_dir"], config_from_state(state))
            result = client.call("execute_step", {"step": step})
            steps = dict(state.get("fluent_steps", {}))
            steps[step] = result
            return _persist(state, step, {"fluent_steps": steps, "error": ""})
        except Exception as error:
            return _failed(state, step, error)

    execute.__name__ = step
    return execute


def validate_mesh(state: PipelineState) -> dict[str, Any]:
    step = "final_validation"
    try:
        client = get_client(state["run_id"], state["runtime_dir"], config_from_state(state))
        result = client.call("execute_step", {"step": step})
        picture = client.call("picture")
        steps = dict(state.get("fluent_steps", {}))
        steps[step] = result
        steps["picture"] = picture
        return _persist(state, step, {"fluent_steps": steps, "error": ""})
    except Exception as error:
        return _failed(state, step, error)
