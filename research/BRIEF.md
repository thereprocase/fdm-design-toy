# Brief: generative design for FDM printing (research + plan)

## The ask
The user (repo owner "thereprocase") was talking to a collaborator, who said:

> project #1 is just finishing simulation for parts I've already designed. I want to get good at
> generative design for FDM 3d printed stuff. no one has really documented a programmatic set of
> constraints so it's a little odd to automate right now. print orientation dependent structure
> massing + anisotropic material

The user asked: can we build something like this? Then: "research and plan this".
Goal: a plan for an open, programmatic generative-design system for FDM parts in which
**print orientation drives both the massing (where material goes, as shells/perimeters/infill)
and an anisotropic material model**, with **printability written down as a documented,
machine-checkable constraint set**. Output of this phase is research + a plan, not the build.

## Hardware available
- **This PC** (Windows 11, i9, NVIDIA laptop GPU, commit limit ~84-91 GB; heavy work must not go on C:
  or OneDrive; work on D:). Has Python/uv, OrcaSlicer 2.4.2 CLI, Hugin etc.
- **compute-box**: Linux container, 40 threads of 2x Xeon E5-2698 v4 (Broadwell, AVX2, no AVX-512),
  300 GB RAM, **no GPU**, Ubuntu 24.04. OpenFOAM v1912 installed; CadQuery 2.8 venv at
  /mnt/user/cfd/cadenv. A friend's box: fine for multi-hour jobs with a heads-up. It is busy with CFD
  right now: **do not run anything on it during this research phase.**
- **second workstation**: Windows + WSL, Ryzen 5800X3D, 64 GB.
- Printer: Bambu Lab P1S, 0.4 mm nozzle; materials PETG and ASA.

## Existing work you MUST read before proposing anything (read-only; do not modify these repos)
All cloned under `D:\Code\Models\`:
- **`spool-wall-rack/`**: the most relevant prior art, by the same user + agents:
  - `analysis/rev-g2/`: an **evolutionary screening loop** (`evo_*.py`, `EVOLUTION.md`), **GPU hex FEM
    on NVIDIA Warp** (`gpu_hex*`, `GPU-FEM-REVIEW.md`, `GPU-VALIDATION.md`), scikit-fem, adaptive
    meshes (`ADAPTIVE-MESH.md`, 0.2 mm cells, ~8.5 M cells), contact, **actual-slicer mapping**
    (`audit_g_slicer_mapping.py`, `g-slicer-mapping/`), plasticity (`solve_plastic`, `plastic_shape`).
  - `designs/rev-g2/INTERFACE-CONTRACT.md`, `shape-seeds/`, `print-controls/` (Orca projects, walls,
    infill); `README.md`, `DESIGN.md`, E-series engineering guides, `analysis/e13/` stress fields.
- **`5680-dock/desk-dock/D9-P5/build_d9.py`**: CadQuery builder with `selfsupport()` (45-degree overhang
  fill under every flatter face), `PROTECT` keep-out solids per part, print orientations per part
  (`PRINT_Z`), Orca CLI slicing + plate verification (`prepare_and_slice.py`, `verify_plates.py`).
  `5680-dock/tools/coupon-pipeline/` = coupon/slicing pipeline.
- **`novel-cad-skill/`**: plan for a next-gen parametric CAD skill (build123d + Manifold).
- **`double-bead/`** (Fillaprint): typeface whose rules are "nominal strokes and minimum clear gaps are
  both two extrusion widths": an existing documented FDM rule.
- `thereprocase.github.io/`: the project site (Gridline style; reports state limitations honestly).

## House style for this work
- Honest about uncertainty; numbers come with what they do and don't establish.
- Prefer extending the existing spool-rack machinery over reinventing it; say explicitly what is reused.
- Cite sources (papers, docs) with links when you rely on them; web research is encouraged.

## Rules for agents
- Read-only on all repos above. Write only under `D:\Code\Models\fdm-gen\` (your report, plus scratch
  under `D:\Code\Models\fdm-gen\scratch\<your-name>\` if you prototype something small locally).
- No commits, pushes, posting, or remote machine use. Small local experiments only (minutes, not hours).
- Reports are Markdown, concrete, skimmable: headings, tables, numbered decisions, open questions.
