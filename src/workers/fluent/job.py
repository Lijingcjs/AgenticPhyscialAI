"""Internal Fluent job assembled from Prompt and confirmed SpaceClaim groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.services.contracts import resolve_boundary_types


@dataclass(frozen=True)
class MeshJob:
    job_name: str
    geometry_path: Path
    length_unit: str | None
    boundaries: dict[str, list[str]]
    surface_max_size: float | None
    local_refinements: tuple[dict[str, Any], ...]
    boundary_layers: dict[str, Any]
    volume_fill: str
    quality: dict[str, float]
    raw: dict[str, Any]
    control_unit: str | None = None
    surface_min_size: float | None = None
    volume_max_size: float | None = None
    boundary_types: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MeshJob":
        geometry = Path(data["geometry_path"]).expanduser().resolve()
        if not geometry.is_file() or geometry.suffix.lower() != ".scdoc":
            raise ValueError("The confirmed SpaceClaim geometry is missing")
        unit = data.get("length_unit")
        boundaries = {
            role: list(data.get("boundaries", {}).get(role, []))
            for role in ("inlet", "outlet", "wall", "symmetry")
        }
        surface_max_size = data.get("surface_max_size")
        refinements = []
        for item in data.get("local_refinements", []):
            if not item.get("zone"):
                raise ValueError("Each local refinement needs a confirmed zone")
            refinements.append({"zone": str(item["zone"]), **{
                key: float(item[key]) if item.get(key) is not None else None
                for key in ("size", "min_size", "max_size")
            }})
        layers = dict(data.get("boundary_layers") or {})
        layers.setdefault("zones", [])
        layers.setdefault("layers", None)
        layers.setdefault("growth_rate", None)
        layers.setdefault("first_layer_height", None)
        return cls(
            job_name=str(data.get("job_name") or "cfd-agent-run"),
            geometry_path=geometry,
            length_unit=unit,
            boundaries=boundaries,
            boundary_types=resolve_boundary_types(
                {name: role for role, names in boundaries.items() for name in names},
                data.get("boundary_types") or {},
            ),
            surface_max_size=None if surface_max_size is None else float(surface_max_size),
            surface_min_size=data.get("surface_min_size"),
            volume_max_size=data.get("volume_max_size"),
            local_refinements=tuple(refinements),
            boundary_layers=layers,
            volume_fill="poly-hexcore",
            quality=dict(data.get("quality") or {}),
            raw=data,
            control_unit=data.get("control_unit") or unit,
        )
