"""Read confirmed SpaceClaim named groups and build Fluent boundary input."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from src.services.contracts import resolve_boundary_types
from src.services.errors import PipelineError
from src.services.geometry_catalog import GeometryCatalog
from src.services.units import control_in_metres

ALLOWED_ROLES = {"inlet", "outlet", "wall", "symmetry"}


def named_groups(catalog: GeometryCatalog) -> dict[str, list[str]]:
    native = getattr(catalog, "native_catalog", None)
    if not isinstance(native, dict):
        raise ValueError("Confirmed catalog has no native group data")
    raw_groups = native.get("internal", {}).get("raw_groups", [])
    result: dict[str, list[str]] = {}
    for row in raw_groups:
        name = str(row.get("raw_name", "")).strip()
        members = [str(item) for item in row.get("member_ids", [])]
        if not name:
            continue
        if name in result:
            raise ValueError("Duplicate SpaceClaim group name: " + name)
        result[name] = members
    return result


def confirm_roles(
    *, catalog: GeometryCatalog, proposed: dict[str, str], previous: dict[str, str]
) -> dict[str, str]:
    groups = named_groups(catalog)
    extra = sorted(set(proposed) - set(groups))
    roles = {name: proposed.get(name, previous.get(name, "")) for name in groups}
    missing = sorted(name for name, role in roles.items() if not role)
    invalid = sorted(name for name, role in roles.items() if role and role not in ALLOWED_ROLES)
    if missing:
        raise ValueError("Boundary roles are missing for confirmed groups: " + ", ".join(missing))
    if extra:
        raise ValueError("Boundary roles refer to absent confirmed groups: " + ", ".join(extra))
    if invalid:
        raise ValueError("Unsupported boundary roles for: " + ", ".join(invalid))
    return roles


def validate_confirmed_cad(
    *, catalog: GeometryCatalog, roles: dict[str, str]
) -> dict[str, Any]:
    """Validate the actual saved CAD before Fluent receives it.

    SpaceClaim groups are editable during human confirmation.  Verify the
    topological and grouping invariants again from a fresh catalog rather than
    trusting the groups produced before the handoff pause.
    """

    bodies = list(catalog.bodies)
    positive = [
        body
        for body in bodies
        if body.solid_or_sheet == "solid" and (body.volume_m3 or 0.0) > 0.0
    ]
    if len(bodies) != 1 or len(positive) != 1:
        raise PipelineError(
            "CAD_CONFIRMED_SOLID_INVALID",
            "The confirmed CAD must contain exactly one positive-volume solid.",
            stage="reload_confirmed_cad",
            substep="solid validation",
            objects=[{"candidate_id": body.id} for body in bodies],
            suggested_action="Remove extra bodies or repair zero-volume bodies, then save the CAD again.",
            evidence={
                "body_count": len(bodies),
                "positive_solid_ids": [body.id for body in positive],
            },
        )
    body = positive[0]
    groups = named_groups(catalog)
    if set(groups) != set(roles):
        raise PipelineError(
            "CAD_CONFIRMED_GROUP_ROLE_MISMATCH",
            "The confirmed boundary groups do not match the confirmed role names.",
            stage="reload_confirmed_cad",
            substep="boundary-group validation",
            suggested_action="Assign roles again for every current boundary group.",
            evidence={"group_names": sorted(groups), "role_names": sorted(roles)},
        )
    face_ids = {face.id for face in catalog.faces if face.body_id == body.id}
    assigned: dict[str, str] = {}
    for name, members in groups.items():
        if not members:
            raise PipelineError(
                "CAD_CONFIRMED_GROUP_EMPTY",
                "A confirmed boundary group is empty.",
                stage="reload_confirmed_cad",
                substep="boundary-group validation",
                objects=[{"name": name, "role": roles.get(name, "")}],
                suggested_action="Add fluid-body faces to that group, or remove the empty group and confirm roles again.",
            )
        non_faces = [member for member in members if member not in face_ids]
        if non_faces:
            raise PipelineError(
                "CAD_CONFIRMED_GROUP_MEMBER_INVALID",
                "A confirmed boundary group contains an object outside the fluid body.",
                stage="reload_confirmed_cad",
                substep="boundary-group validation",
                objects=[{"name": name, "candidate_id": member} for member in non_faces],
                suggested_action="Boundary groups may contain only faces from the fluid body.",
            )
        overlap = [member for member in members if member in assigned]
        if overlap:
            raise PipelineError(
                "CAD_CONFIRMED_GROUP_OVERLAP",
                "Confirmed boundary groups contain overlapping faces.",
                stage="reload_confirmed_cad",
                substep="boundary-group validation",
                objects=[
                    {"name": assigned[member], "candidate_id": member}
                    for member in overlap
                ] + [{"name": name, "candidate_id": member} for member in overlap],
                suggested_action="Assign each fluid face to exactly one boundary group.",
            )
        assigned.update({member: name for member in members})
    missing_faces = sorted(face_ids - set(assigned))
    if missing_faces:
        raise PipelineError(
            "CAD_CONFIRMED_GROUP_COVERAGE_INCOMPLETE",
            "Confirmed boundary groups do not cover every fluid face.",
            stage="reload_confirmed_cad",
            substep="boundary-group validation",
            objects=[{"candidate_id": face_id} for face_id in missing_faces],
            suggested_action="Assign every ungrouped fluid face to an inlet, outlet, wall, or symmetry group.",
        )
    return {
        "positive_volume": True,
        "nonempty_groups": True,
        "nonoverlapping_groups": True,
        "all_faces_grouped": True,
        "roles_complete": True,
        "body_id": body.id,
        "face_count": len(face_ids),
        "group_count": len(groups),
    }


def build_fluent_job(
    *, geometry: str, roles: dict[str, str], requirements: dict[str, Any]
) -> dict[str, Any]:
    boundaries = {role: [] for role in ALLOWED_ROLES}
    for name, role in roles.items():
        boundaries[role].append(name)
    global_control = requirements.get("surface_max_size")
    layers = requirements.get("boundary_layers") or {}
    layer_zones = resolve_layer_zones(layers, roles)
    return {
        "job_name": "cfd-agent-run",
        "geometry_path": geometry,
        "length_unit": requirements.get("length_unit"),
        "control_unit": "m",
        "boundaries": boundaries,
        "boundary_types": resolve_boundary_types(roles, requirements.get("boundary_types") or {}),
        "surface_max_size": control_in_metres(global_control),
        "surface_min_size": control_in_metres(requirements.get("surface_min_size")),
        "volume_max_size": control_in_metres(requirements.get("volume_max_size")),
        "local_refinements": [
            {
                "target": item["target"],
                **{key: control_in_metres(item.get(key)) for key in ("size", "min_size", "max_size")},
                "zone": item.get("boundary_name"),
            }
            for item in requirements.get("local_refinements", [])
            if any(item.get(key) is not None for key in ("size", "min_size", "max_size"))
        ],
        "boundary_layers": {
            "zones": layer_zones,
            "scope_specified": (layers.get("boundary_names") is not None or layers.get("target") is not None) and layers.get("layers") != 0,
            "layers": layers.get("layers"),
            "growth_rate": layers.get("growth_rate"),
            "first_layer_height": control_in_metres(layers.get("first_layer_height")),
        },
        "parameter_sources": copy.deepcopy(requirements),
        "volume_fill": "poly-hexcore",
        "quality": dict(requirements.get("quality") or {}),
    }


def resolve_layer_zones(layers: dict, roles: dict[str, str]) -> list[str]:
    if not layers or layers.get("layers") == 0:
        return []
    names = layers.get("boundary_names")
    if names is None:
        target = layers.get("target")
        if target is None:
            return []
        names = (
            [name for name, role in roles.items() if role == "wall"]
            if target == "all walls"
            else [target]
        )
    return list(dict.fromkeys(names))


def rebind_mesh_targets(
    *,
    requirements: dict,
    previous_groups: list[dict],
    confirmed_catalog: GeometryCatalog,
    roles: dict[str, str],
    resolve_missing: Callable[[list[str]], dict[str, str]] | None = None,
) -> dict:
    """Follow native membership first, then resolve uncertain targets as one batch."""
    result = copy.deepcopy(requirements)
    groups = named_groups(confirmed_catalog)
    objects = confirmed_catalog.by_id()
    current = {
        name: {objects[item].moniker for item in members if item in objects}
        for name, members in groups.items()
    }
    previous = {row["name"]: set(row["member_monikers"]) for row in previous_groups}
    unresolved: set[str] = set()
    bindings: list[tuple[dict | list, str | int, str]] = []

    def resolve(name: str | None, target: str) -> str:
        requested = name or target
        members = previous.get(requested)
        if requested in roles and requested in groups and (
            members and None not in members and current[requested] == members
        ):
            return requested
        matches = [
            name
            for name, values in current.items()
            if members and None not in members and values == members
        ]
        if len(matches) != 1:
            unresolved.add(requested)
            return requested
        return matches[0]

    for item in result.get("local_refinements", []):
        bindings.append((item, "boundary_name", item.get("boundary_name") or item["target"]))
        item["boundary_name"] = resolve(item.get("boundary_name"), item["target"])
    layers = result.get("boundary_layers")
    if layers and layers.get("layers") != 0:
        names = layers.get("boundary_names")
        if names is None and layers.get("target") not in (None, "all walls"):
            names = [layers["target"]]
        if names is not None:
            layers["boundary_names"] = [resolve(name, name) for name in names]
            bindings.extend((layers["boundary_names"], index, name) for index, name in enumerate(names))
        resolve_layer_zones(layers, roles)
    type_bindings = [
        {"name": resolve(name, name), "type": value}
        for name, value in result.get("boundary_types", {}).items()
    ]
    bindings.extend((row, "name", name) for row, name in zip(type_bindings, result.get("boundary_types", {}), strict=True))
    if unresolved:
        if resolve_missing is None:
            raise ValueError("Cannot uniquely bind meshing target after CAD confirmation: " + ", ".join(sorted(unresolved)))
        mapping = resolve_missing(sorted(unresolved))
        if set(mapping) != unresolved or any(name not in groups or name not in roles for name in mapping.values()):
            raise PipelineError(
                "CAD_MESH_TARGET_MAPPING_INVALID",
                "The model must map every unresolved meshing target to an existing saved CAD group.",
                stage="reload_confirmed_cad", evidence={"targets": sorted(unresolved), "mapping": mapping},
            )
        for container, key, original in bindings:
            if original in unresolved:
                container[key] = mapping[original]
    if "boundary_types" in result:
        rebound = {}
        for row in type_bindings:
            if row["name"] in rebound and rebound[row["name"]] != row["type"]:
                raise ValueError("Conflicting boundary types map to the same saved CAD group")
            rebound[row["name"]] = row["type"]
        resolve_boundary_types(roles, rebound)
        result["boundary_types"] = rebound
    return result
