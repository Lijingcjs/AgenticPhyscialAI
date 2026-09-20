# CFD Agent

CFD Agent generates Fluent volume meshes from a SpaceClaim CAD file and a natural-language
prompt. It supports a single connected internal fluid domain with arbitrary planar
opening contours (including circular, rectangular, polygonal, and mixed-curve openings),
with human confirmation before meshing. Flow solving is not included.

The workflow uses LangGraph for orchestration, a language model for interpretation and
failure diagnosis, SpaceClaim for fluid-domain extraction, and PyFluent for meshing.
Meshing uses Fluent Watertight Geometry and poly-hexcore.

## Requirements

- Windows; Python 3.12 is recommended (package metadata allows 3.11–3.13).
- Ansys 2024 R1 (v241), including SpaceClaim, Fluent, and a valid Ansys license.
- An existing `.scdoc` file and a nonempty UTF-8 prompt file.
- Existing Codex OAuth credentials and access to a compatible image-capable model.

The usual credential location is `%USERPROFILE%\.codex\auth.json`. The workflow currently
uses Codex OAuth only; API-key authentication and other model providers are not integrated.
The default model is `gpt-5.6-luna`. `--model` selects another compatible model available
through the same service; it does not change the provider or authentication method.

## Quick start

### 1. Install

Open PowerShell in the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:AWP_ROOT241 = "C:\Program Files\ANSYS Inc\v241"
```

Replace the Ansys path if necessary, or use `--ansys-root` when starting a run.
Python dependencies are installed automatically; Ansys and model credentials are separate.

### 2. Prepare a prompt

Save a UTF-8 file such as `C:\CFD-inputs\prompt.txt`. Replace the placeholders for your CAD:

```text
Use [reference view] as the directional reference.
Select [opening locations or features] and [the seed face on the inner fluid wall].
Assign [opening name] as an inlet and [opening name] as an outlet.
Treat the remaining fluid boundary as a wall.
Optional: [global size, local refinement, boundary-layer settings, and length units].
```

Specify a reference view when using directions such as left or right.

By default, the workflow extracts the internal fluid volume from the selected opening
boundaries. It skips volume extraction only when the prompt explicitly states that the
input solid is already the fluid domain. A planar face or a closed loop can represent an
opening; a loop may contain multiple line, arc, spline, or mixed-curve edges.

### 3. Run

```powershell
.\.venv\Scripts\cfd-agent.exe run `
  --geometry "C:\CFD-inputs\model.scdoc" `
  --prompt-file "C:\CFD-inputs\prompt.txt" `
  --ui-mode gui `
  --keep-open
```

Use `run --help` to see all options. The default UI mode is `hidden`, which still requires
terminal confirmation. `--keep-open` requires `--ui-mode gui`.

## Confirmation and resume

At the CAD pause, inspect or edit the working copy shown in the terminal.

- `yes`: in GUI mode, save unsaved changes in the original editing session, then reread
  the saved groups and continue if the handoff succeeds. Hidden mode uses the saved file.
- `no`: cancel without requesting a save; the SpaceClaim editing window stays open.

Keep existing group names when using the CLI: new or renamed groups with unknown roles
stop the handoff. For these groups, Python callers must first save the CAD, then supply
their roles through `cfd_agent.resume_pipeline` using `boundary_roles` and `action="approve"`.

Failures can trigger limited repair attempts. Numeric repairs to parameters identified
by the model as user-specified require confirmation: enter `accept`, a replacement value
in the displayed unit, or `cancel`. Layer counts require integers.
Complete parameter confirmation in the original process; it needs the live Fluent session.

With `--keep-open`, press Enter at the final terminal prompt to close the retained Fluent
session. Close SpaceClaim separately. Cancellation closes the run's Fluent session.

If the terminal was closed at a CAD confirmation pause, keep the original SpaceClaim
editing session open and resume using the same code version:

Replace `YOUR-RUN-ID` with the name of the relevant folder under `runs`, then run:

```powershell
.\.venv\Scripts\cfd-agent.exe resume --run-dir ".\runs\YOUR-RUN-ID"
```

This command resumes pending CAD confirmation, not parameter confirmation or failed runs.

## Results and limitations

Outputs are created under `runs/<run-id>/` in the current working directory, or the
directory selected with `--output`.

| File | Contents |
|---|---|
| `artifacts/confirmed.scdoc` | Saved CAD copied at the confirmation handoff |
| `artifacts/mesh.msh.h5` | Mesh copied after successful validation |
| `result.json` | Outcome and available details; fields vary for success, failure, and cancellation |

Mesh checks cover quality metrics, negative volumes, execution-label presence, and file
save/readback. They do not establish physical validity or independently verify that
repaired inlet/outlet assignments preserve the confirmed roles. Review the final mesh.

For failures, inspect terminal messages and available run logs. Early startup errors may
occur before `result.json` exists.

Prompts, geometry attributes, and images are sent to the model service. Keep credentials,
private CAD, and generated run data out of public commits.
