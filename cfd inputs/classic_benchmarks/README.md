# Classic CFD benchmark geometries

All three `.scdoc` files are watertight, single fluid volumes. CFD Agent can
therefore proceed directly to boundary naming and Fluent Meshing.

| Geometry | Prompt | Intended test |
| --- | --- | --- |
| `01_t_junction_mixer.scdoc` | `01_t_junction_mixer_prompt.txt` | Passive-scalar or species mixing |
| `02_u_bend_heat_transfer.scdoc` | `02_u_bend_heat_transfer_prompt.txt` | Internal forced-convection heat transfer |
| `03_methane_air_t_mixer_combustor.scdoc` | `03_methane_air_t_mixer_combustor_prompt.txt` | Non-premixed methane-air mixing / combustion setup |

The third case uses the same robust T-mixer topology as the first, but assigns
the main duct as the air inlet and the branch as the methane inlet. All
dimensions are in millimetres.
