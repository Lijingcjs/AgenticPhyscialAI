"""Opening topology candidates exposed to the CAD grounding model."""

from cfd_agent.nodes.cad import (
    _is_existing_fluid_body,
    _prompt_explicitly_declares_fluid_body,
)
from cfd_agent.services.geometry_models import GeometryCatalog
from cfd_agent.services.grounding import _opening_candidate_context


def test_opening_context_exposes_planar_faces_and_closed_arbitrary_loops():
    catalog = GeometryCatalog(
        catalog_id="catalog",
        geometry_id="geometry",
        faces=[
            {"id": "F_RECT", "kind": "face", "surface_type": "Plane"},
            {"id": "F_WALL", "kind": "face", "surface_type": "Cylinder"},
        ],
        loops=[
            {
                "id": "L_RECT",
                "kind": "loop",
                "face_id": "F_RECT",
                "closed": True,
                "is_outer": True,
                "edge_ids": ["E1", "E2", "E3", "E4"],
            },
            {
                "id": "L_OPEN",
                "kind": "loop",
                "face_id": "F_RECT",
                "closed": False,
            },
        ],
    )

    context = _opening_candidate_context(catalog)

    assert context["planar_faces"] == ["F_RECT"]
    assert context["closed_loops"] == ["L_RECT"]
    assert "arbitrary opening" in context["selection_guidance"]


def test_closed_positive_volume_body_can_skip_volume_extract():
    catalog = GeometryCatalog(
        catalog_id="catalog",
        geometry_id="geometry",
        bodies=[
            {
                "id": "B1",
                "kind": "body",
                "solid_or_sheet": "solid",
                "volume_m3": 1.0,
            }
        ],
        edges=[
            {"id": "E1", "kind": "edge", "body_id": "B1", "face_ids": ["F1", "F2"]},
            {"id": "E2", "kind": "edge", "body_id": "B1", "face_ids": ["F1", "F2"]},
        ],
    )

    assert _is_existing_fluid_body(catalog)


def test_sheet_or_open_body_still_requires_volume_extract():
    catalog = GeometryCatalog(
        catalog_id="catalog",
        geometry_id="geometry",
        bodies=[
            {
                "id": "B1",
                "kind": "body",
                "solid_or_sheet": "sheet",
                "volume_m3": 0.0,
            }
        ],
        edges=[
            {"id": "E1", "kind": "edge", "body_id": "B1", "face_ids": ["F1"]},
        ],
    )

    assert not _is_existing_fluid_body(catalog)


def test_volume_extraction_is_the_default_when_prompt_is_silent():
    assert not _prompt_explicitly_declares_fluid_body("Select the left inlet and right outlet.")


def test_existing_fluid_body_requires_an_explicit_prompt_statement():
    assert _prompt_explicitly_declares_fluid_body(
        "The input is already the fluid domain; keep its existing volume."
    )
