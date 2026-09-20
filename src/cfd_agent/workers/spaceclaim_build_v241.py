# Python Script, API Version = V241
"""SpaceClaim-side volume extraction and boundary grouping operations.

Loads the complete packaged helper file in SpaceClaim's scripting namespace.
Uses model-selected native references, not case-specific object IDs.
"""

import json
import math
import os
import traceback

execfile(os.environ["CFD_AGENT_SC_COMMON"], globals())

from SpaceClaim.Api.V241 import Group, IDocObject
from SpaceClaim.Api.V241.Scripting.Commands import Delete, DocumentOpen, DocumentSave, RenameObject, VolumeExtract
from System.Collections.Generic import List


with open(os.environ["CFD_AGENT_SC_BUILD_REQUEST"], "r") as request_stream:
    build_request = json.load(request_stream)

build_result = {
    "ok": False,
    "operation": build_request.get("operation"),
    "steps": [],
    "images": [],
}


def record(step, data):
    build_result["steps"].append({"step": step, "result": data})


def save_picture(name):
    Selection.Empty().SetActive()
    ViewHelper.SetProjection(ViewHelper.ViewProjection.Isometric, True, False)
    ViewHelper.ZoomToEntity(Selection.Create(list(DocumentHelper.GetRootPart().GetAllBodies())))
    refresh_for_export(build_request["ui_mode"])
    path = os.path.join(build_request["folder"], name + ".png")
    export_picture(path)
    build_result["images"].append({"view": name, "path": path})


def terminal_from_selection(port, boundary):
    target = LIVE_OBJECTS[port["candidate_id"]]
    edges = [LIVE_OBJECTS[edge_id] for edge_id in boundary["edge_ids"]]
    if boundary["kind"] in ("circular_edge", "circular_inner_loop"):
        if len(edges) != 1:
            raise ValueError("Circular opening must contain exactly one edge: " + port["name"])
        edge = edges[0]
        if boundary["kind"] == "circular_edge" and (
                target.Faces.Count != 1 or not isinstance(target.Shape.Geometry, Circle)):
            raise ValueError("Selected opening edge is not one circular open edge: " + port["name"])
        if not isinstance(edge.Shape.Geometry, Circle):
            raise ValueError("Selected opening loop is not circular: " + port["name"])
        circle = edge.Shape.Geometry
        center = vector3(circle.Frame.Origin)
        normal = vector3(circle.Frame.DirZ)
        area = math.pi * float(circle.Radius) * float(circle.Radius)
        radius = float(circle.Radius)
    else:
        if not isinstance(target.Shape.Geometry, Plane):
            raise ValueError("Selected opening face is not planar: " + port["name"])
        center = vector3(MeasureHelper.GetCentroid(Selection.Create(target)))
        normal = vector3(target.Shape.Geometry.Frame.DirZ)
        area = float(target.Area)
        radius = None
    terminal = {
        "name": port["name"],
        "role": port["role"],
        "source_candidate_id": port["candidate_id"],
        "center_m": center,
        "normal": normal,
        "area_m2": area,
    }
    if radius is not None:
        terminal["radius_m"] = radius
    return edges, terminal


try:
    operation = build_request["operation"]
    DocumentOpen.Execute(build_request["input"])

    if operation == "extract_volume":
        catalog = build_catalog()
        plan = build_request["selection_plan"]
        requested = [item["candidate_id"] for item in plan["openings"]]
        requested.append(plan["seed_inner_wall_id"])
        boundaries = build_request["terminal_boundaries"]
        for boundary in boundaries.values():
            requested.extend(boundary["edge_ids"])
        validate_catalog_identity(build_request["catalog"], catalog, requested)

        cap_edges = []
        terminals = []
        for port in plan["openings"]:
            edges, terminal = terminal_from_selection(
                port, boundaries[port["candidate_id"]])
            cap_edges.extend(edges)
            terminals.append(terminal)
        seed_face = LIVE_OBJECTS[plan["seed_inner_wall_id"]]
        if plan["seed_inner_wall_id"].startswith("F") is False:
            raise ValueError("The fluid-volume seed must be a face")
        seed_center = MeasureHelper.GetCentroid(Selection.Create(seed_face))
        seed_point = seed_face.Shape.Geometry.ProjectPoint(seed_center).Point
        terminal_faces = [
            LIVE_OBJECTS[port["candidate_id"]] for port in plan["openings"]]
        existing_body = seed_face.Parent
        use_existing_body = (
            all(boundary["kind"] == "terminal_face" for boundary in boundaries.values())
            and all(face.Parent == existing_body for face in terminal_faces)
            and existing_body.Shape.Volume > 0)
        if use_existing_body:
            fluid = existing_body
            source_mode = "existing_fluid_body"
        else:
            options = VolumeExtractOptions()
            options.SeedPoint = seed_face.Shape.Geometry.ProjectPoint(seed_center)
            options.CreateShareTopology = False
            extraction = VolumeExtract.Create(
                Selection.Create(cap_edges), Selection.Empty(), options)
            volumes = list(extraction.CreatedVolumes)
            if not extraction.Success or len(volumes) != 1 or volumes[0].Shape.Volume <= 0:
                raise ValueError("VolumeExtract did not create exactly one positive fluid volume")
            fluid = volumes[0]
            source_mode = "extracted_internal_volume"
        for group in list(Window.ActiveWindow.Groups):
            group.Delete()
        others = [body for body in DocumentHelper.GetRootPart().GetAllBodies() if body != fluid]
        if others:
            Delete.Execute(Selection.Create(others))
        RenameObject.Execute(Selection.Create(fluid), "fluid")
        DocumentSave.Execute(build_request["output"])
        extracted_catalog = build_catalog()
        free_edges = [
            edge["id"] for edge in extracted_catalog["public"]["edges"]
            if len(edge["face_ids"]) != 2
        ]
        if free_edges:
            raise ValueError("Extracted fluid body contains free edges: " + str(free_edges))
        build_result["transfer"] = {
            "terminals": terminals,
            "seed_point_m": vector3(seed_point),
            "volume_m3": float(fluid.Shape.Volume),
            "face_count": int(fluid.Faces.Count),
            "free_edges": free_edges,
            "source_mode": source_mode,
        }
        record("extract_volume", build_result["transfer"])
        save_picture("extracted-fluid")

    elif operation == "label_faces":
        transfer = build_request["extraction"]["transfer"]
        fluid_bodies = [body for body in DocumentHelper.GetRootPart().GetAllBodies() if body.Shape.Volume > 0]
        if len(fluid_bodies) != 1:
            raise ValueError("Expected exactly one positive fluid body before grouping")
        fluid = fluid_bodies[0]
        for group in list(Window.ActiveWindow.Groups):
            group.Delete()

        assigned = []
        groups = []
        for terminal in transfer["terminals"]:
            matches = []
            target_area = terminal.get("area_m2")
            if target_area is None:
                target_area = math.pi * terminal["radius_m"] * terminal["radius_m"]
            for face in fluid.Faces:
                if not isinstance(face.Shape.Geometry, Plane):
                    continue
                point = vector3(MeasureHelper.GetCentroid(Selection.Create(face)))
                delta = [point[i] - terminal["center_m"][i] for i in range(3)]
                direction = vector3(face.Shape.Geometry.Frame.DirZ)
                alignment = abs(sum(direction[i] * terminal["normal"][i] for i in range(3)))
                if (
                    sum(value * value for value in delta) ** 0.5 < 1e-5
                    and abs(alignment - 1.0) < 1e-6
                    and abs(face.Area - target_area) < max(1e-10, target_area * 1e-5)
                ):
                    matches.append(face)
            if len(matches) != 1 or matches[0] in assigned:
                raise ValueError("Cannot uniquely map extracted cap for " + terminal["name"])
            assigned.append(matches[0])
            groups.append((terminal["name"], terminal["role"], matches))

        remaining = [face for face in fluid.Faces if face not in assigned]
        if remaining:
            groups.append(("wall", "wall", remaining))
        if len(set(name for name, role, faces in groups)) != len(groups):
            raise ValueError("Boundary group names are not unique")
        for name, role, faces in groups:
            Group.Create(DocumentHelper.GetRootPart(), name, List[IDocObject](faces))
        DocumentSave.Execute(build_request["output"])
        final_catalog = build_catalog()
        group_records = [
            {
                "name": name,
                "role": role,
                "count": len(faces),
                "member_monikers": [moniker_of(face) for face in faces],
            }
            for name, role, faces in groups
        ]
        coverage = sum(item["count"] for item in group_records)
        if coverage != fluid.Faces.Count:
            raise ValueError("Boundary groups do not cover every fluid face")
        build_result["groups"] = group_records
        build_result["catalog"] = final_catalog
        build_result["coverage"] = coverage
        build_result["total_faces"] = int(fluid.Faces.Count)
        record("label_faces", {"groups": group_records, "coverage": coverage})
        save_picture("labeled-fluid")
        if build_request.get("keep_open"):
            execfile(os.environ["CFD_AGENT_SC_SAVE"], globals())
            build_result["save_bridge"] = install_save_bridge(
                Window.ActiveWindow.Document, build_request["output"], build_request["folder"]
            )
    else:
        raise ValueError("Unsupported build operation: " + str(operation))

    build_result["ok"] = True
except Exception:
    build_result["error"] = traceback.format_exc()

temporary = build_request["response"] + ".tmp"
with open(temporary, "w") as response_stream:
    json.dump(build_result, response_stream, indent=2)
os.rename(temporary, build_request["response"])
