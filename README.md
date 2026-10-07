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

**Plan merged; P0 (foundations and the solver gate) is next.** No optimiser exists here yet. Start with [`PLAN.md`](PLAN.md).

| | |
|---|---|
| [`research/BRIEF.md`](research/BRIEF.md) | the question and the ground rules given to the researchers |
| [`research/round1/`](research/round1/) | four independent reports: architecture/roadmap, mechanics/maths, compute/performance, designer workflow + constraint catalog |
| [`research/reviews/`](research/reviews/) | each researcher's review of the other three (12 reviews) |
| [`research/final/`](research/final/) | each report revised against its three reviews, with a disposition table |
| [`research/checks/`](research/checks/) | the small numeric checks and benchmarks behind the reports |
| [`PLAN.md`](PLAN.md) | the merged plan: decisions, machines, roadmap P0–P5, risks, open questions |

The four researchers were AI agents (Claude) working in parallel, then cross-reviewing.
Their numbers come with stated evidence levels; treat anything tagged *guess* or
*slicer-only* accordingly. Nothing here is physically qualified yet.

## Ground rules for work in this repo

See [`AGENTS.md`](AGENTS.md): no personal information, honest uncertainty, reproducible numbers.

## Licence

Code: MIT ([`LICENSE`](LICENSE)). Documentation, research, catalog and data: CC BY 4.0 ([`LICENSE-docs.md`](LICENSE-docs.md)).
