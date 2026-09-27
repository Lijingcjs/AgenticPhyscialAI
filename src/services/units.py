"""Length conversions shared by task construction and Fluent execution."""

from __future__ import annotations

from ansys.units import Quantity


def convert_length(value: float, source_unit: str, target_unit: str) -> float:
    try:
        return float(Quantity(float(value), source_unit).to(target_unit).value)
    except Exception as error:
        raise ValueError(
            f"Length conversion failed: {value} {source_unit} -> {target_unit}: {error}"
        ) from error


def control_in_metres(control: dict | None) -> float | None:
    if control is None:
        return None
    return convert_length(control["value"], control["unit"], "m")
