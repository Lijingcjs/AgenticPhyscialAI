import os
from pathlib import Path

import pytest

from cfd_agent.adapters.spaceclaim import SpaceClaimRunner

pytestmark = pytest.mark.skipif(
    os.environ.get("CFD_AGENT_RUN_ANSYS_INTEGRATION") != "1",
    reason="requires licensed Ansys 2024 R1",
)


def test_spaceclaim_returns_real_native_catalog(tmp_path: Path):
    supplied = os.environ.get("CFD_AGENT_TEST_GEOMETRY")
    if not supplied:
        pytest.skip("Set CFD_AGENT_TEST_GEOMETRY to a privately supplied SCDOC")
    geometry = Path(supplied)
    runner = SpaceClaimRunner(output_dir=tmp_path, ui_mode="hidden", timeout_s=900)
    try:
        catalog, _ = runner.catalog(geometry, render_candidates=False)
    finally:
        runner.close()
    assert catalog.faces
    assert catalog.native_catalog["internal"]["refs"]
