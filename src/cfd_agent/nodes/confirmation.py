"""Durable human confirmation and actual saved-CAD handoff."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from cfd_agent.adapters.fluent import close_client
from cfd_agent.adapters.spaceclaim import SpaceClaimRunner
from cfd_agent.config import config_from_state
from cfd_agent.services.artifacts import write_json
from cfd_agent.services.boundaries import build_fluent_job, confirm_roles, rebind_mesh_targets
from cfd_agent.services.contracts import ConfirmationPayload
from cfd_agent.services.execution import _failed, _persist, _run_dir
from cfd_agent.state import PipelineState


def human_confirmation(state: PipelineState) -> dict[str, Any]:
    response = interrupt(
        {
            "message": "SpaceClaim processing is complete. Review or edit the working CAD, then answer yes/no in the CLI. Yes saves unsaved changes and reuses existing group roles; unknown roles stop the handoff. Python API callers must save and supply any new group roles before approval.",
            "working_geometry": state["working_geometry"],
            "boundary_roles": state["boundary_roles"],
            "spaceclaim_process_id": state["labeling"].get("process_id"),
        }
    )
    payload = ConfirmationPayload.model_validate(response)
    return _persist(
        state,
        "human_confirmation",
        {
            "human_response": payload.model_dump(mode="json"),
            "status": "running",
            "error": "",
        },
    )


def reload_confirmed_cad(state: PipelineState) -> dict[str, Any]:
    try:
        response = ConfirmationPayload.model_validate(state["human_response"])
        runner = SpaceClaimRunner(
            output_dir=_run_dir(state) / "artifacts" / "confirmed-catalog",
            ui_mode="hidden",
            config=config_from_state(state),
        )
        try:
            catalog, path = runner.catalog(Path(state["working_geometry"]), render_candidates=False)
        finally:
            runner.close()
        roles = confirm_roles(
            catalog=catalog,
            proposed=response.boundary_roles,
            previous=state["boundary_roles"],
        )
        confirmed = _run_dir(state) / "artifacts" / "confirmed.scdoc"
        shutil.copy2(state["working_geometry"], confirmed)
        # CAD readers run outside Python; use the same ASCII staging convention
        # as SpaceClaim instead of handing a Unicode archive path to Fluent.
        runtime_confirmed = Path(state["runtime_dir"]) / "confirmed.scdoc"
        shutil.copy2(confirmed, runtime_confirmed)
        requirements = rebind_mesh_targets(
            requirements=state["mesh_requirements"],
            previous_groups=state["labeling"]["groups"],
            confirmed=catalog,
            roles=roles,
        )
        job = build_fluent_job(
            geometry=str(runtime_confirmed),
            roles=roles,
            requirements=requirements,
        )
        return _persist(
            state,
            "reload_confirmed_cad",
            {
                "confirmed_geometry": str(confirmed),
                "confirmed_catalog": catalog.model_dump(mode="json"),
                "boundary_roles": roles,
                "fluent_job": job,
                "mesh_requirements": requirements,
                "artifacts": {
                    **state["artifacts"],
                    "confirmed_geometry": str(confirmed),
                    "confirmed_catalog": str(path),
                },
                "error": "",
            },
        )
    except Exception as error:
        return _failed(state, "reload_confirmed_cad", error)


def confirmation_route(state: PipelineState) -> str:
    return "cancelled" if state["human_response"]["action"] == "cancel" else "reload_confirmed_cad"


def cancelled(state: PipelineState) -> dict[str, Any]:
    close_client(state["run_id"])
    result = {
        "status": "cancelled",
        "run_id": state["run_id"],
        "working_geometry": state["working_geometry"],
        "reason": "User cancelled",
    }
    write_json(_run_dir(state) / "result.json", result)
    return _persist(state, "cancelled", {"status": "cancelled", "result": result, "error": ""})
