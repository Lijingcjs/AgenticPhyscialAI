"""Offline protocol events, not claims of a real model call."""

import json

import pytest

from cfd_agent.adapters.llm import (
    CodexOAuthCredentials,
    CodexOAuthResponsesTransport,
    ProviderRequestError,
)


def test_provider_error_code_is_retained_without_response_body():
    class Response:
        status_code = 200
        closed = False

        def iter_lines(self, **kwargs):
            yield "data: " + json.dumps(
                {
                    "type": "response.failed",
                    "response": {
                        "error": {"code": "server_is_overloaded", "message": "PRIVATE DATA"}
                    },
                }
            )

        def close(self):
            self.closed = True

    response = Response()

    class Session:
        def post(self, *args, **kwargs):
            return response

    transport = CodexOAuthResponsesTransport(CodexOAuthCredentials("test-only"), session=Session())
    with pytest.raises(ProviderRequestError, match="server_is_overloaded") as error:
        transport.complete({})
    assert "PRIVATE" not in str(error.value)
    assert response.closed


def test_transient_ssl_failure_is_retried_before_marking_vision_blocked():
    class Response:
        status_code = 200

        def iter_lines(self, **kwargs):
            yield "data: " + json.dumps(
                {"type": "response.output_text.done", "text": '{"ok":true}'}
            )
            yield "data: [DONE]"

        def close(self):
            pass

    class Session:
        def __init__(self):
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise __import__("requests").exceptions.SSLError("transient")
            return Response()

    session = Session()
    transport = CodexOAuthResponsesTransport(
        CodexOAuthCredentials("test-only"),
        session=session,
        max_transport_retries=2,
        retry_backoff_seconds=0,
    )

    assert transport.complete({}) == '{"ok":true}'
    assert session.calls == 3


def test_exhausted_ssl_retries_record_attempt_count():
    class Session:
        def __init__(self):
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            raise __import__("requests").exceptions.SSLError("persistent")

    session = Session()
    transport = CodexOAuthResponsesTransport(
        CodexOAuthCredentials("test-only"),
        session=session,
        max_transport_retries=2,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ProviderRequestError, match="after 3 attempts") as error:
        transport.complete({})
    assert error.value.transport_attempts == 3
    assert error.value.transport_error_type == "SSLError"
    assert session.calls == 3


def test_custom_model_is_sent_by_existing_transport(monkeypatch):
    from cfd_agent.adapters import llm
    from cfd_agent.services.contracts import ConfirmationPayload

    payloads = []

    class Transport:
        def complete(self, payload):
            payloads.append(payload)
            return '{"action":"cancel","boundary_roles":{}}'

    monkeypatch.setattr(llm, "load_codex_oauth", lambda path: CodexOAuthCredentials("offline"))
    monkeypatch.setattr(llm, "CodexOAuthResponsesTransport", lambda *args, **kwargs: Transport())
    client = llm.GroundingLLMClient.from_codex_oauth(model="chosen-model")
    client.invoke(system_prompt="test", user_prompt="test", response_model=ConfirmationPayload)
    assert payloads[0]["model"] == "chosen-model"


def test_selection_requirements_and_reviewer_share_configured_model(tmp_path, monkeypatch):
    from cfd_agent.adapters.llm import GroundingLLMClient
    from cfd_agent.config import RuntimeConfig
    from cfd_agent.services import grounding, reviewer
    from cfd_agent.services.contracts import CadSelectionPlan, MeshRequirements, RepairDecision
    from cfd_agent.services.geometry_models import GeometryCatalog

    selected = CadSelectionPlan(
        status="selected",
        reference_view="Front",
        explanation="offline",
        seed_inner_wall_id="F2",
        openings=[
            {
                "candidate_id": "F1",
                "role": "inlet",
                "name": "feed",
                "description": "opening",
                "reason": "offline",
            }
        ],
    )

    class Client:
        def invoke(self, **kwargs):
            schema = kwargs["response_model"]
            if schema is CadSelectionPlan:
                return selected
            if schema is MeshRequirements:
                return MeshRequirements()
            return RepairDecision(
                action="stop", target_step="query_geometry", diagnosis="offline", evidence="offline"
            )

    models = []

    def factory(**kwargs):
        models.append(kwargs["model"])
        return Client()

    monkeypatch.setattr(GroundingLLMClient, "from_codex_oauth", factory)
    catalog = GeometryCatalog(
        catalog_id="c",
        geometry_id="g",
        faces=[{"id": "F1", "kind": "face"}, {"id": "F2", "kind": "face"}],
    )
    settings = RuntimeConfig(model="chosen-model")
    plan = grounding.plan_cad_selection(
        catalog=catalog, user_prompt="mesh", audit_dir=tmp_path, config=settings
    )
    grounding.extract_mesh_requirements(
        catalog=catalog,
        user_prompt="mesh",
        selection_plan=plan,
        audit_dir=tmp_path,
        config=settings,
    )
    reviewer.diagnose_failure(
        {
            "run_dir": str(tmp_path),
            "runtime_config": settings.model_dump(),
            "max_repair_rounds": 1,
            "failed_step": "query_geometry",
            "error": "offline",
        }
    )
    assert models == ["chosen-model"] * 3


def test_visual_edge_candidates_only_include_supported_circular_open_edges():
    from cfd_agent.services.geometry_models import GeometryCatalog
    from cfd_agent.services.grounding import _native_open_edges

    native_edges = [
        {"id": "E-circle-open", "curve_type": "Circle", "face_ids": ["F1"]},
        {"id": "E-circle-seam", "curve_type": "Circle", "face_ids": ["F1", "F2"]},
        {"id": "E-line-open", "curve_type": "Line", "face_ids": ["F1"]},
        {"id": "E-line-seam", "curve_type": "Line", "face_ids": ["F1", "F2"]},
    ]
    catalog = GeometryCatalog(
        catalog_id="catalog",
        geometry_id="geometry",
        native_catalog={"public": {"edges": native_edges}},
    )

    assert _native_open_edges(catalog) == [native_edges[0]]
