# fdm-design-toy

Toward open, programmatic **generative design for FDM-printed parts**, where:

- **print orientation** drives both where material goes (perimeters, skins, infill: the
  structure's *massing*) and the **anisotropic material model** (layers are weaker across
  than along), and
- **printability is written down as a documented, machine-checkable constraint set**:
  overhangs, bridges, minimum features in extrusion widths, wall/skin rules, inter-layer
  strength, bed contact, warping, and more, each with units, defaults, evidence level and
  where it can be checked (density field, mesh, real slicer toolpaths, physical coupon).

Nobody seems to have published that constraint set as code. This repo is where the
research, the plan, and then the implementation live, and where the work is tracked (issues).

## Status

**P0 is in progress.** The plan is in [`PLAN.md`](PLAN.md); work items are GitHub issues. No optimiser
exists yet. What runs today:

| Piece | What it does | Evidence so far |
|---|---|---|
| [`catalog/`](catalog/) | 35 printability rules as data (units and an evidence tag on every number), a calibration binding, a T0 PolyLite ASA material card | lints clean; known-answer tests per checker |
| `fdmgen.catalog.checks` | checkers for overhang (grid, mesh and slicer toolpaths), wall width, gap width, bridges, slicer settings | cross-checked on a real bracket: every mesh-level overhang island is where Orca puts support |
| `fdmgen.gcode` | Orca G-code reader: credited vs spent material, arcs, frame chain back to the model | reproduces the pinned credited volume of the archived slice exactly; matches all 24 archived references |
| [`problems/`](problems/) | `problem.yaml` generated from pinned sources, with a lint that checks load resultants and cross-file consistency | load split matches the pinned reference to 1e-12 |
| `fdmgen.orient` | ranked orientation table: stable poses, printability columns, inter-layer index F_L from a stress field | the existing hand-chosen bracket pose ranks first; uniaxial-bar known answers pass |
| `fdmgen.coupons` | overhang and bridge ladder plate, plus slicer-evidence receipts per rung | Orca supports the 35–45° rungs and leaves 50–60° alone (slicer evidence only) |
| `fdmgen.fem` | GPU multigrid elasticity solver and cell stress recovery; CPU algebraic-multigrid pilots in [`bench/`](bench/) | solver gate (#4) not met yet |
| [`ui/`](ui/) | local browser workspace for comparing orientation evidence and drafting shell and helper regions | draft sketches record intent only; modifier geometry and strength checks come from the Python tools; see [`ui/README.md`](ui/README.md) |

Nothing here is physically qualified. Slicer results say what Orca generates; printed coupons
(issue #12) and the test rig (issue #18) come next for the physical tier.

| Research | |
|---|---|
| [`research/BRIEF.md`](research/BRIEF.md) | the question and the ground rules given to the researchers |
| [`research/round1/`](research/round1/) | four independent reports: architecture/roadmap, mechanics/maths, compute/performance, designer workflow + constraint catalog |
| [`research/reviews/`](research/reviews/) | each researcher's review of the other three (12 reviews) |
| [`research/final/`](research/final/) | each report revised against its three reviews, with a disposition table |
| [`research/checks/`](research/checks/) | the small numeric checks and benchmarks behind the reports |

The four researchers were AI agents (Claude) working in parallel, then cross-reviewing.
Their numbers come with stated evidence levels; treat anything tagged *guess* or
*slicer-only* accordingly.

## Quickstart

```bash
pip install -e '.[geom,dev]'            # numpy, pyyaml; geometry extras for meshes and raster checks
pytest -q
fdmgen catalog lint                      # the rule catalog and calibration binding
fdmgen card show polymaker-polylite-asa-t0
fdmgen lint problems/spool-rack-g2-ef/problem.yaml
fdmgen orient problems/spool-rack-g2-ef/problem.yaml --voxel     # needs the source part checkout
fdmgen coupons --out out/coupons         # overhang + bridge ladder plate (STL + rung metadata)
fdmgen coupons-evidence out/coupons/ladder-plate.json plate_1.gcode
```

Commands that read the example part need a checkout of its source repository next to this one
(or `SPOOL_RACK_ROOT`); without it they say so and stop. Output goes to `out/`, which git ignores.

## Ground rules for work in this repo

See [`AGENTS.md`](AGENTS.md): no personal information, honest uncertainty, reproducible numbers.

## Licence

Code: MIT ([`LICENSE`](LICENSE)). Documentation, research, catalog and data: CC BY 4.0 ([`LICENSE-docs.md`](LICENSE-docs.md)).
