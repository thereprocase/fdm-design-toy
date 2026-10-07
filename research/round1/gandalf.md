# Gandalf: system architecture and phased roadmap for `fdm-gen`

Round 1 research report. Angle: architecture, reuse, data model, pipeline, repo layout, roadmap, risks.
Other angles (math/mechanics, compute, workflow and constraint catalogue) belong to Sauron, Legolas
and Frodo; where this report depends on them it says so and states the interface it needs.

Repos read (read-only): `spool-wall-rack` @ `14338e9`, `5680-dock` @ `05a770b`, `novel-cad-skill`,
`double-bead`, `thereprocase.github.io`. No code was run except listing files and checking the local GPU.

---

## 0. Executive summary

1. **Do not build a new system from scratch.** About 70% of the hard parts exist already, spread
   across three repos. They include a G-code-to-credited-material reader, a matrix-free GPU hex FEM with
   contact and adaptive coarsening, an Orca CLI pipeline with per-object toolpath audits, a
   two-tier screen-then-verify search loop with receipts, keep-out solids, build-direction vectors
   and a 45-degree self-support operator. Nobody has packaged them as a general tool.
2. **The missing parts are specific:** (a) a *design-time* optimiser, meaning density topology
   optimisation that knows how a slicer will turn a shape into walls, skins and infill; (b) an
   **anisotropic** material model (every existing result uses isotropic E = 1 GPa); (c) printability
   rules written as **data**, not scattered through code; (d) orientation as a first-class, swept variable.
3. **Core architectural decision: use two FEM roles with different rules.** The *design solver*
   runs on a coarse grid with ersatz stiffness, runs hundreds of times and uses a slicer emulator.
   The *truth solver* uses real G-code material at 0.2 mm with no ersatz stiffness, keeps every stress
   sample and runs a few times. The spool-rack house rule "no density floor or ersatz stiffness" stays
   in force for the truth solver only. If the two roles are mixed, the project will produce
   unbelievable numbers or never converge.
4. **Use the slicer to generate toolpaths. Do not write our own.** The optimiser's output is a body
   mesh, modifier meshes and per-region Orca settings. Spool-rack already prints parts this way
   (100% helpers). Re-analysis reads the real G-code back.
5. **Build a separate voxel grid in the print frame for each candidate orientation.** Layers then
   fall on grid planes. Walls and skins become axis-aligned erosions, the overhang filter acts along a
   grid axis, and the anisotropy axes align with the grid. Loads and boundary conditions are kept in
   the part frame and mapped through one rotation object.
6. **MVP part: the spool-rack bracket.** It is the best part for validating the pipeline: it has
   printed and sliced ground truth, a written interface contract and existing FEM baselines. It is
   **weak as a demonstration of orientation**, because its layers already lie parallel to the bending
   plane, so laying it flat is the obvious answer. Use that as a known-answer test, then move to a
   part where orientation choice is genuinely hard in Phase 2 (section 6.3).
7. **New repo `D:\Code\Models\fdm-gen\` as a uv-managed package `fdmgen`.** Port code from spool-rack
   with provenance headers and parity tests. Never import from spool-rack via `sys.path`, and never
   write into it.

---

## 1. What exists, and what to reuse, wrap or retire

### 1.1 Inventory with dispositions

| Asset (path under `D:\Code\Models\`) | What it does | Disposition | Notes / required changes |
|---|---|---|---|
| `spool-wall-rack/analysis/rev-g2/plastic_shape.py` (415 lines) | Parses Orca G-code into per-path width, height, role and E; credited vs sacrificial bridge material; layer polygons; `contains`, `equivalent_thickness`, `integrated_volume` | **Port. This becomes the truth-material core.** | Hard-coded G transform default (`model_to_installed`), fixed 0.2 mm nominal layer, and a process policy assert inside the parser (`no Sparse infill`). It **handles only G0/G1**, so arc-fitted G-code (G2/G3) would be misread. Keep the per-segment direction, which is needed for bead-direction anisotropy. |
| `5680-dock/desk-dock/D9-P5/path_reader.py`; `5680-dock/tools/coupon-pipeline/architect/verify_mixed_plate.py` (`roads`) | Two more G-code parsers. `path_reader` does handle G2/G3 arcs. `verify_mixed_plate` attributes paths to objects and counts support and bridge roads per object. | **Merge with the above into one `fdmgen.slicer.gcode` module** | Three parsers already exist with different coverage. Spool-rack's P1S `0x2` nozzle-offset bug (-2 mm X) shows how easily a parser can be subtly wrong. One canonical parser, with fixtures for arcs, offsets, relative/absolute E and object labels. |
| `spool-wall-rack/analysis/rev-g2/gpu_hex.py` (230 lines) | Matrix-free Q1 hex elasticity on Warp, Jacobi-CG, face-connectivity node splitting, stress recovery, unilateral wall contact | **Port and extend** | Uses one element stiffness `ke` for *all* cells (uniform isotropic material). Needs a `ke` stack indexed by material class or orientation bin, plus a per-cell scale (SIMP). Rejects CPU devices; keep that for the truth role, but add a CPU backend for compute-box. |
| `gpu_contact.py`, `gpu_demo_adaptive.py`, `gpu_demo_adaptive_operator.py`, `gpu_multigrid.py`, `gpu_coarse_geometry.py` | Contact with time budgets, 2:1 adaptive coarsening with hanging-node constraints (MFEM-style), V-cycle and coarse correction | **Port into the truth solver** | `ADAPTIVE-MESH.md`: two full-G solves **failed to converge** with Jacobi-CG. A multigrid preconditioner is a prerequisite, not an option (Legolas to size this). |
| `validate_gpu_hex.py`, `validate_gpu_contact.py`, `validate_gpu_demo_adaptive.py`, `validate_plastic_shape.py`, `validate_mechanics.py` + `validation/*.json`, `gpu-validation/*.json` | Independent fixtures (patch tests, rigid motion, affine stress, 50,000-sample occupancy) | **Port as the regression suite** | These become the parity tests that show the port did not change behaviour. |
| `evo_search.py`, `evo_screen.py`, `evo_refine.py`, `evo_verify.py`, `evo_transfer.py` | Bounded GA (quantised 5-10% mutations), cheap 2D screen, actual-slice finalists, leader refinement, ledgers and receipts | **Reuse the *pattern*; port only the GA kernel** | `evo_screen.Screen` hard-codes G's wall nodes (`y in [40,164]`), hotspot coordinate and cache paths. The three-stage *policy* (cheap screen, then 3 actual-slice finalists, then refine the leader, with feedback changing the next cycle's fitness) is the right shape for the whole system (section 4). |
| `reduced_plastic.py`, `evo_screen.py` 2D plane-stress model | Exact-integrated reduced model for the flat bracket | **Keep bracket-specific; do not generalise** | Valid only because the bracket is a layered, plate-like part. The general system needs 3D. |
| `mesh_plastic.py`, `audit_volume_mesh.py`, TetGen/fTetWild route | Conforming tet meshing of sliced material | **Retire** | `MESHING-NOTES.md` and the README record failure (topology/quality rejection, long jobs stopped). Voxel/hex is the chosen path. |
| `designs/rev-g2/INTERFACE-CONTRACT.md`, `shape-seeds/moulding-clearance.json`, `G2-BRIEF.md` | Fixed interfaces, keep-out envelope, loads (117.72 N), movement budgets, temperatures, fracture factor 4 | **Translate into the first `problem.yaml`, pinned by sha256** | This is exactly the "design problem spec" the system needs, already written in prose. |
| `designs/rev-g2/print-controls/*`, `g-recheck/*` (SHA256SUMS, slice-evidence.zip, 3mf-verification) | Eight virtual controls plus five wall/skin cases with real slices and hashes | **Use as ground-truth fixtures and baselines** | MVP results must be ranked against E13/G/E+F on the *same* truth pipeline and material card. |
| `5680-dock/desk-dock/D9-P5/build_d9.py` `selfsupport()` | CadQuery B-rep: prisms every face flatter than 45 degrees down to the bed, minus keep-out | **Keep as reference behaviour; reimplement in voxel and mesh form** | Inside the optimiser, self-support is a filter (Langelaar AM filter). After extraction it is a repair-and-verify step. B-rep prisms do not scale to iso-surface meshes. |
| `build_d9.py` `PROTECT{part: [solids]}` | Per-part keep-out solids, respected by fill and edge dressing | **Generalise into the problem spec's `regions` (keep_in / keep_out / interface)** | This maps directly onto non-design regions. |
| `build_d9.py` `PRINT_Z{name: vector}` + `pose()` | Build direction per part | **Generalise into `process.orientation`** | **Two sources of truth:** `PRINT_Z` vectors and the hand-written rotations in `pose()` encode the same orientation separately, so a mismatch would pass silently. In fdm-gen, one `Rotation` produces both. |
| `build_d9.py` `bore_td()`, `GUSSET_SLOPE`, `dress.py` rules; `overhang-threshold-test/` | Teardrop crest at 40 degrees for horizontal bores; gusset slope; fillet only perimeter-parallel edges, chamfer top edges, never touch bed edges; measured overhang threshold | **Move into the rule catalogue as data, with the test as evidence** | These are calibrated printability rules locked inside builder code. |
| `5680-dock/desk-dock/D9-P5/prepare_and_slice.py`, `verify_plates.py`, `tools/coupon-pipeline/architect/*` | 3MF writer, Orca CLI invocation with isolated `--datadir`, plate placement and bed checks, per-object support/bridge audit | **Wrap into `fdmgen.slicer`** | Hard-coded `C:\Program Files\OrcaSlicer\orca-slicer.exe`. The coupon pipeline is a *snapshot* whose live copy is in a Codex worktree with absolute paths. Port the logic and pin the Orca version and profile hashes. |
| `novel-cad-skill/scripts/check_printability.py` | Mesh checks: flat bottom, overhang %, wall thickness, bridge span, minimum feature, with thresholds from a spec | **Port as the first geometric rule checkers** | Assumes +Z is build-up. Must take the build direction from the process spec. |
| `novel-cad-skill/ARCHITECTURE.md` (build123d + Manifold) | Geometry engine choice and gate pattern | **Adopt engine choice: build123d/OCP for STEP import and interface solids, manifold3d for booleans on meshes** | fdm-gen is mesh/voxel-first; B-rep is only for importing and keeping exact interfaces. |
| `double-bead/docs/SPEC.md` | Rules written in extrusion widths `w` ("stroke = gap = 2w") | **Adopt the unit convention**: catalogue rules are expressed in `w` (line width) and `h` (layer height) wherever physically sensible | This makes the catalogue portable across nozzles and layer heights. |
| `spool-wall-rack/analysis/rev-g/run_native.py` | Disposable worker that survives native CAD/VTK teardown crashes | **Reuse as the stage runner for native-CAD stages** | This is a real Windows OCC problem; keep the workaround. |
| Receipt/ledger JSON conventions (`receipt.json`, `ledger.json`, `SHA256SUMS.json`, status enums like `CONTACT_SCREEN_AT_STATED_TOLERANCE_ERODED_MATERIAL_ONLY`, `scope` strings) | Reproducibility and honest scope | **Formalise as a schema** (section 3.6) | The conventions are good but ad hoc per script; fdm-gen gives them one schema and one writer. |

### 1.2 What the existing work *establishes* and what it does not

- Established: actual-slice material reconstruction validated to 0.005 mm. GPU elasticity and contact
  pass independent fixtures. The adaptive operator equals the projected fine operator. A three-stage
  search loop ran 100 proposals in 11 min 18 s with finalists in about 5-7 min each.
- Not established: anisotropic material, design-time optimisation (the GA only tuned parameter bands),
  convergence on a full part at 0.2 mm without multigrid, and any physical calibration of the
  1 GPa planning modulus. `print-controls/README.md` says it plainly: *"these results do not demonstrate
  a reliable 5-minute architecture loop."* The system must be designed around that limit, not
  assume it away.

### 1.3 Hardware reality check (from this research)

- **This PC's GPU is an RTX 3500 Ada Laptop, 11.5 GiB** (`nvidia-smi`). All spool-rack GPU results
  were run on an **RTX 3080 Ti, 12 GiB, under WSL2** (`GPU-VALIDATION.md`). That is presumably
  second workstation, but the brief does not say. **Open question Q1: confirm which machine has the 3080 Ti.**
  The two cards have similar memory, so whole-part limits carry over. Timings do not.

---

## 2. Prior art at the system level, and the gap

| System | Orientation | Overhang in optimiser | Anisotropic material | Shell/infill (slicer) awareness | Reads real toolpaths back | Open/programmable |
|---|---|---|---|---|---|---|
| Autodesk Fusion Generative Design | X+, Y+, Z+ only; each direction gives a separate outcome set ([docs](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-MFG-METHODS.htm); [blog](https://www.autodesk.com/products/fusion-360/blog/unlocking-better-additive-manufacturing-outcomes-generative-design/)) | Yes (max overhang angle, min thickness) | Not documented | No | No | No (cloud, closed) |
| nTop | Any build vector ([nTop overhang constraint](https://support.ntop.com/hc/en-us/articles/360060738793-How-to-use-the-overhang-constraint-in-Topology-Optimization); [release note](https://www.ntop.com/resources/product-updates/topology-optimization-additive-manufacturing-constraints-in-ntop-platform/)) | Yes | Not in topopt per the docs found | Via lattices/implicits, not FDM perimeters | No | Partly scriptable, closed |
| Altair Inspire | Draw/print direction chosen from bounding-box face ([Overhang](https://help.altair.com/inspire/en_us/topics/inspire/structure/draw_overhang_c.htm)) | Yes | Not in topopt | No | No | No |
| Teton SmartSlice (Cura plugin, about 2020) | Uses the user's orientation | n/a | FEA with print-parameter-dependent properties | **Yes: optimises walls, infill and top/bottom per region** ([Fabbaloo](https://www.fabbaloo.com/2020/02/teton-simulations-smart-slice-tool-works); [docs](https://help.tetonsim.com/cura/tutorial-optimize)) | Partial | No (cloud, commercial) |
| Hexagon Digimat-AM / RP (FFF) | Uses given part | n/a | **Yes: maps G-code toolpath to FE mesh for local anisotropy** ([Digimat AM guide](https://documentation-be.hexagon.com/bundle/Digimat_2023.3_AM_User_Guide/raw/resource/enus/Digimat_2023.3_AM_User_Guide.pdf)) | Yes (toolpath) | **Yes** | No (commercial) |
| TopOpt_in_PETSc (DTU, LGPL) | Structured 3D grid | Via an extension repo | No | Local-volume constraint for infill in the Python-wrapped fork ([wrapped fork, LGPL-2.1](https://github.com/thsmit/TopOpt_in_PETSc_wrapped_in_Python); [base](https://github.com/topopt/TopOpt_in_PETSc)) | No | Yes, C++/MPI |
| FEniTop, DL4TO, Scikit-Topt, TopOpt.jl | Generic | No | No | No | No | Yes ([Scikit-Topt JOSS](https://joss.theoj.org/papers/10.21105/joss.09092.pdf); [DL4TO](https://dl.acm.org/doi/10.1007/978-3-031-38271-0_54)) |
| Academic: shell-infill topopt ([Wu, Clausen, Sigmund 2017, CMAME 326](https://research.tudelft.nl/en/publications/minimum-compliance-topology-optimization-of-shellinfill-composite/)) | Single | No | No | **Yes: optimised shell plus non-uniform infill** | No | Paper |
| Academic: AM filter ([Langelaar 2016](https://www.researchgate.net/publication/305622859_An_additive_manufacturing_filter_for_topology_optimization_of_print-ready_designs)) | Single, grid-aligned | **Yes (45 degrees, layer-wise)** | No | No | No | 2D Matlab reference |
| Academic: orientation + topology ([simultaneous optimisation](https://www.researchgate.net/publication/341288654_Simultaneous_optimization_of_build_orientation_and_topology_for_additive_manufacturing); [anisotropic multicomponent, arXiv 1911.10393](https://arxiv.org/pdf/1911.10393); [multi-axis overhang + anisotropy, arXiv 2502.20343](https://arxiv.org/pdf/2502.20343)) | **Optimised** | Yes | **Yes** | No | No | Papers |
| Academic: FDM strength anisotropy in topopt ([Addit. Manuf. 2023](https://www.sciencedirect.com/science/article/abs/pii/S2214860423003433); [JCDE strength + anisotropy](https://academic.oup.com/jcde/article/10/2/892/7110403); [hybrid deposition path, PMC7463923](https://pmc.ncbi.nlm.nih.gov/articles/PMC7463923/)) | Single | Some | **Yes** | Partly (path) | No | Papers |
| Academic: stress-aligned toolpaths ([Reinforced FDM, TOG 2020](https://github.com/GuoxinFang/ReinforcedFDM); [Neural Slicer, TOG 2024](https://arxiv.org/pdf/2404.15061)) | Multi-axis | Yes | Yes (aligns filament) | Replaces slicer | n/a | Research code |

**The gap this fills** (as far as this search found; not exhaustive):
no open, scriptable pipeline combines (1) sweeping arbitrary build orientations, (2) a design
optimiser that emulates **a real planar slicer's walls/skins/infill per layer**, (3) an orthotropic
bead-level material whose axes come from the orientation and the toolpath, (4) **re-analysis on the
actual slicer output**, and (5) a **published, machine-checkable printability rule set** with
calibration evidence. Commercial tools each cover one or two of these. The academic papers cover
the theory one piece at a time, usually in 2D or on idealised layers. Digimat is the closest to the
"truth" stage and SmartSlice is the closest to the "massing" stage; neither is open or generative.

**Deliberate non-goals:** multi-axis or non-planar printing, our own slicer, continuous-fibre paths.
Reinforced FDM and Neural Slicer show where the field is heading. The P1S is a planar 3-axis machine,
and the value here is doing planar FDM honestly.

---

## 3. Core data model (schema sketch)

Design rules for the data model:
- **Every vector and point is tagged with a frame.** The spool-rack nozzle-offset bug and the D9
  `PRINT_Z`/`pose()` duplication are frame bugs. Frames: `part` (CAD), `installed` (optional
  service frame), `print` (one per orientation candidate, derived and never authored), `bed`
  (after slicer placement).
- **Units are explicit**: mm, N, MPa, s, degrees C. Printability rules may use `w` and `h` units, which
  are resolved against the process spec.
- **Everything is content-hashed.** A run is identified by the hash of (problem, process, material,
  rules, optimiser settings, code version).
- Storage format: YAML authored by humans, validated by JSON Schema (pydantic models generate it),
  plus canonical JSON for hashing.

### 3.1 Design problem spec (`problem.yaml`)

```yaml
schema: fdmgen/problem@0.1
id: spool-bracket-g2
units: {length: mm, force: N, stress: MPa}
provenance:
  - {source: spool-wall-rack/designs/rev-g2/INTERFACE-CONTRACT.md, sha256: <pin>}
  - {source: spool-wall-rack/designs/rev-g2/shape-seeds/moulding-clearance.json, sha256: <pin>}
frames:
  part: {note: "CAD frame of supplied geometry"}
  installed: {from: part, rotation: identity, translation: [0,0,0],
              note: "X out of wall, Y up, Z along rods"}
geometry:
  design_domain: {file: geom/envelope.step, frame: part}   # max allowed material extent
  regions:                       # non-design regions, generalising D9 PROTECT
    - {id: rear_seat,  kind: keep_in,  file: geom/rear_seat.step,  role: interface}
    - {id: front_seat, kind: keep_in,  file: geom/front_seat.step, role: interface}
    - {id: screw_upper, kind: keep_out, file: geom/screw_upper_clear.step, role: clearance}
    - {id: moulding,   kind: keep_out, file: geom/moulding_zone.step, role: clearance}
    - {id: spool_sweep, kind: keep_out, file: geom/spool_sweep.step, role: motion_envelope}
  interfaces_exact: true          # keep_in solids are booleaned back exactly after extraction
load_cases:
  - id: full_12kg
    frame: installed
    loads:
      - {type: bearing, region: rear_seat,  resultant_N: [0,-58.86,0], distribution: cosine}
      - {type: bearing, region: front_seat, resultant_N: [0,-58.86,0], distribution: cosine}
    supports:
      - {type: fixed,   region: screw_upper_land}
      - {type: contact_unilateral, region: wall_face, normal: [-1,0,0], gap_mm: 0, friction: 0}
    service: {temperature_C: 29.4}            # 85 F sustained
  - id: one_spool_delta
    derive: {from: full_12kg, scale_loads: 0.104}   # must be re-solved, not scaled (G2-BRIEF)
requirements:                   # targets checked by the truth stage, not by the optimiser
  - {id: movement, metric: max_resultant_displacement, region: all, load_case: full_12kg, max_mm: 4.0}
  - {id: delta,    metric: displacement_change, load_cases: [full_12kg, one_spool_delta], max_mm: 1.0}
  - {id: fracture, metric: strength_factor, criterion: per_material_card, min: 4.0}
objective: {minimise: spent_extrusion_volume, report: [print_time_s, support_volume_mm3]}
```

### 3.2 Process spec (`process.yaml`), one per orientation candidate after expansion

```yaml
schema: fdmgen/process@0.1
printer: catalog/printers/bambu-p1s-0.4.yaml     # bed 256x256, exclusions, nozzle offset (0,2)
slicer: {name: OrcaSlicer, version: "2.4.2", exe_sha256: <pin>,
         profiles: {machine: <sha256>, filament: <sha256>, process: <sha256>}}
orientation:
  mode: sweep                     # fixed | sweep
  candidates: auto                # auto = stable hull poses + 6 axis poses + user list
  user: [{name: flat_side, build_dir_part: [0,0,1], spin_deg: 0}]
  # the print frame is derived: R maps part -> print with build_dir -> +Z_print
layer_height_mm: 0.2
line_width_mm: 0.42               # "w" for rule resolution
walls: {min: 2, max: 8}           # design variable range when optimising massing
skins: {top_mm: [1.0, 1.6], bottom_mm: [1.0, 1.6]}
infill:
  base: {density: 0.0}
  modifiers: {allowed_densities: [0.15, 0.4, 1.0], pattern: gyroid}  # discrete palette
support: {allowed: false}         # or: {allowed: true, max_volume_mm3: ..., removable_only: true}
bridges: {structural_credit: false}   # spool-rack rule, here as data
```

### 3.3 Material card (`catalog/materials/petg-generic-p1s.yaml`)

```yaml
schema: fdmgen/material@0.1
id: petg-generic-p1s-0.2h-0.42w
polymer: PETG
process_binding: {layer_height_mm: 0.2, line_width_mm: 0.42, nozzle_C: 250, bed_C: 70, cooling: profile:<sha>}
status: ASSUMED                    # ASSUMED | LITERATURE | COUPON_MEASURED | VALIDATED
classes:                           # per bead-class effective orthotropic properties
  bead:                            # local axes: 1 = along bead, 2 = across in-layer, 3 = build
    E_MPa: [E1, E2, E3]
    G_MPa: [G12, G13, G23]
    nu: [nu12, nu13, nu23]
    strength_MPa:
      t: [Xt, Yt, Zt_interlayer]  # interlayer tension is the critical one
      c: [Xc, Yc, Zc]
      s: [S12, S13_interlayer, S23_interlayer]
    criterion: max_stress          # or tsai_wu; Sauron decides
  sparse_infill:                   # homogenised, density-dependent (gyroid)
    model: power_law
    params: {E_scale: k, exponent: n}
    valid_density: [0.1, 0.6]
temperature: {curve: [[23, 1.0], [29.4, a], [37.8, b]]}  # modulus multiplier; 85 F / 100 F
creep: {status: UNMODELLED}
evidence: []                       # coupon IDs, papers, with what each establishes
uncertainty: {E_rel_sd: null, strength_rel_sd: null}
```

The material card must state its own `status`. The roadmap requires P1 to run a **sensitivity sweep
over the anisotropy ratios**, so conclusions do not depend on an assumed number.

### 3.4 Constraint/rule set (`catalog/rules/*.yaml`)

The architecture specifies the rule *schema* and the *three levels at which rules are checked*.
Frodo owns the catalogue contents.

```yaml
schema: fdmgen/rule@0.1
id: OVH-01
statement: "No downward-facing surface flatter than theta from the build plane without support."
params: {theta_deg_from_vertical: 45}
units_basis: angle
applies: {printers: [bambu-p1s-0.4], materials: [PETG, ASA]}
levels:
  design:   {mechanism: am_filter, ref: "Langelaar 2016"}      # inside the optimiser
  geometry: {checker: fdmgen.rules.overhang_mesh}               # on extracted mesh, build dir from process
  toolpath: {checker: fdmgen.rules.support_roads, expect: {support_segments: 0}}  # on real G-code
severity: hard                       # hard | soft(weight) | report
evidence:
  - {kind: calibration_print, ref: 5680-dock/desk-dock/D9-P5/overhang-threshold-test/, establishes: "this Orca profile adds support at 45 deg from vertical, none at 35"}
status: CALIBRATED_ONE_PROFILE
```

Examples already present in the repos, waiting to become entries: `WALL-MIN-2` (spool-rack),
`BRIDGE-NOCREDIT` (spool-rack), `FEAT-MIN-2w` / `GAP-MIN-2w` (double-bead), `BORE-TEARDROP-40`
(`bore_td`), `GUSSET-34` (`GUSSET_SLOPE`), `EDGE-DRESS` (`dress.py`), `BED-FIT` / `EXCLUSION-ZONE`
(coupon pipeline), `SUPPORT-ZERO-STRICT` (`verify_mixed_plate`).

**The three-level split is the key point of this section.** A rule that can only be checked on G-code
(for example, bridge credit or a perimeter-count shortfall in thin regions) cannot be guaranteed
by the optimiser. It can only be *steered* by the emulator and *verified* after slicing. The
catalogue records which levels each rule has.

### 3.5 Candidate and result records

```yaml
schema: fdmgen/candidate@0.1
id: <sha256-12 of inputs>
inputs: {problem: <sha>, process: <sha>, material: <sha>, rules: <sha>, optimiser: <sha>, code: <git sha + dirty flag>, env_lock: <sha>}
orientation: {name: flat_side, R_part_to_print: [[...]], build_dir_part: [0,0,1]}
design: {density_field: runs/<id>/rho.npz, grid_mm: 0.6}
artifacts: [{path: body.stl, sha256: ...}, {path: modifiers/*.stl}, {path: plate.3mf}, {path: plate_1.gcode}]
metrics:                      # each metric carries its fidelity and scope
  - {name: compliance, value: ..., fidelity: design_emulated, scope: "coarse grid, emulated shells, SIMP"}
  - {name: max_displacement_mm, value: ..., fidelity: truth_slice, scope: "actual G-code, 0.2 mm, eroded"}
  - {name: spent_volume_mm3, value: ..., fidelity: slicer}
rule_results: [{rule: OVH-01, level: toolpath, pass: true, detail: {...}}]
status: SCREENED | SLICED | TRUTH_SOLVED | TRUTH_FAILED_CONVERGENCE | REJECTED_RULE:<id>
```

### 3.6 Receipts (one per stage execution)

Same idea as spool-rack's `receipt.json`, standardised:
`{stage, candidate_id, inputs:{name:sha}, outputs:{name:sha}, params, tool_versions, machine,
started, seconds, returncode, status, scope}`. Rules:
- Failed runs keep their receipts and fields (spool-rack policy: preserve raw failures).
- A cache hit is defined as an identical input-hash set plus an identical stage-code hash. The runner
  skips work only on a hit and records `cache_hit: true`.
- Absolute local paths and machine usernames do not go into published receipts (spool-rack AGENTS.md
  rule); `machine` is a logical name (`pc`, `second workstation`, `compute-box`).

---

## 4. Pipeline stages and module boundaries

```
 S0 import ──► S1 orient ──► S2 voxelise ──► S3 optimise ──► S4 extract ──► S5 slice ──► S6 truth ──► S7 rank ──► S8 report
 (CAD+yaml)   (candidates)   (print frame)   (design FEM)    (mesh+exact     (Orca CLI     (G-code→      (Pareto)   (site,
                                                              interfaces,     + toolpath    material→                receipts)
                                                              rule checks)    audit)        truth FEM)
                                    ▲                                                         │
                                    └───────── emulator calibration feedback ◄────────────────┘
```

| Stage | Module | Input → output | Machine | Notes |
|---|---|---|---|---|
| S0 Import | `fdmgen.spec`, `fdmgen.geom.importer` | STEP + `problem.yaml` → hashed region solids, tessellations | PC (Windows OCP; `run_native` worker) | Region solids are kept as B-rep for exact boolean-back in S4. |
| S1 Orient | `fdmgen.process.orient` | domain + regions → N `Rotation`s | PC | Candidates: stable convex-hull poses, 6 axis poses, user list. Pre-filter: bed fit, minimum bed contact, and hard interface rules (for example, a bore axis that must be vertical). No continuous orientation optimisation in v1. |
| S2 Voxelise | `fdmgen.geom.voxel` | rotated domain → grid aligned to the print frame, region tags | any | Grid z-spacing is an integer multiple of `h` (0.2 or 0.6 mm). XY spacing is a fraction or multiple of `w`. Re-voxelised per orientation (cheap). |
| S3 Optimise | `fdmgen.opt` (`DensityTopOpt`, `ParametricEvo`) + `fdmgen.process.emulator` + `fdmgen.material` + `fdmgen.fem` (design role) | grid + load cases → density field and material-class field | **second workstation GPU** (Warp) or **compute-box CPU** (one orientation per process, many in parallel) | Two optimiser plug-ins behind one interface. The spool-rack GA becomes `ParametricEvo` for parameterised families. Emulator: per-layer 2D erosion gives wall shells, z-erosion gives skins, the remainder becomes an infill class. Grid alignment makes anisotropic classes axis-aligned. Wall tangents are quantised into angle bins (Sauron to set the bin count). |
| S4 Extract | `fdmgen.geom.extract`, `fdmgen.rules` (geometry level) | density → watertight body mesh + modifier meshes + region settings | PC or compute-box | Iso-surface, smoothing, `manifold3d` union with exact keep_in solids, minus keep_out solids, then repair (voxel self-support pass, the successor to `selfsupport()`), then geometric rule checks. Output is mesh-first; STEP is only produced for interface solids. |
| S5 Slice | `fdmgen.slicer` (3MF writer, Orca driver, `gcode` parser, toolpath rules) | 3MF (body + modifiers + per-object settings) → G-code + sliced 3MF + audit | **PC** (Windows Orca 2.4.2, known working) | Isolated `--datadir` per job (D9 pattern). Pinned exe and profile hashes. Toolpath-level rules run here. Linux Orca on compute-box only after a parity test. |
| S6 Truth | `fdmgen.verify` (ported `plastic_shape`) + `fdmgen.fem` (truth role, adaptive + multigrid + contact) | G-code → credited material with **per-bead direction** → per-cell orthotropic `C` → displacements and stresses | **second workstation GPU** | No ersatz stiffness, every stress sample kept, bridges get no credit, eroded-material omission reported (spool-rack rules unchanged). Finalists only. |
| S7 Rank | `fdmgen.rank` | candidate records → Pareto set per problem | any | No single scalar score is published. Design-vs-truth disagreement is logged as calibration data. |
| S8 Report | `fdmgen.report` | records → figures, `site.json`, Markdown | PC | The site consumes a static JSON export (it is a static Next/Vinext export, so no runtime is needed). |

**Search policy (inherited from EVOLUTION.md, generalised):** many cheap design solves (S3) per
orientation. The top k per orientation go through S4-S5, and the best 1-3 overall go through S6. If S6
reverses the S3 ranking, that is recorded and the emulator is recalibrated. The cheap score is never
promoted to a claim.

**Cross-machine execution:** ssh + rsync of the content-addressed run directory. Each stage is a
pure function of its hashed inputs, so remote results are accepted only if the input hashes match.
Start with a small in-house runner (DAG of stages, receipts, cache). Reconsider Snakemake only if
the DAG outgrows a page. Heavy runs go outside Claude background shells (MEMORY: PanoStitch lesson).
They saturate machines in parallel (farm work style) and yield on RAM pressure. Nothing runs on
compute-box until its owner is told and the CFD work has finished.

**Environment split** (as in spool-rack): `[cad]` Windows-native OCP/build123d, `[gpu]` Warp under
WSL on second workstation, `[cpu]` scipy/pyamg (compute-box), `[slice]` Orca exe. One `uv` project with extras.
Each receipt records its environment lock hash.

---

## 5. Repo layout and integration

```
D:\Code\Models\fdm-gen\
  pyproject.toml            uv; extras [cad] [gpu] [cpu] [dev]
  README.md  AGENTS.md  CLAUDE.md
  research\                 this phase (BRIEF + four reports + plan)
  schemas\                  generated JSON Schemas (problem, process, material, rule, candidate, receipt)
  catalog\
    printers\bambu-p1s-0.4.yaml
    materials\petg-*.yaml asa-*.yaml        status-tagged cards
    rules\*.yaml                             printability catalogue (Frodo's contents)
    orca-profiles\<sha>\                    frozen machine/filament/process JSON
  problems\
    spool-bracket-g2\problem.yaml + geom\   pins spool-rack sources by sha256
    bench-cantilever-3d\                    known-answer benchmark
    bench-orientation-L\                    orientation known-answer benchmark
  src\fdmgen\
    spec\  geom\  process\  material\  fem\{warp_hex,cpu_hex,contact,adaptive,multigrid}\
    opt\{density,evo,filters}\  rules\  slicer\{orca,threemf,gcode}\  verify\  rank\  report\  pipeline\
  tests\
    parity\                 must reproduce spool-rack published numbers (section 6, P0)
    fixtures\               gcode with arcs and offsets, tiny hex patches, rule fixtures
  runs\                     gitignored content store (on D:, never OneDrive)
  scratch\<agent>\          research-phase scratch only
```

**Integration rules:**
1. **Port, do not import.** Each ported file carries a header naming its source, for example
   `ported from spool-wall-rack@14338e9:analysis/rev-g2/gpu_hex.py`, plus a parity test. Spool-rack's
   files are preserved historical records under its own AGENTS.md. Coupling to them through `sys.path`
   would let either repo silently break the other.
2. **Reference by hash.** fdm-gen problem specs and fixtures name spool-rack and 5680-dock artifacts
   by relative path plus sha256. A mismatch is a hard error, not a warning.
3. **Hand-off, not write-through.** If an fdm-gen result is useful to the spool rack, fdm-gen emits a
   "candidate package" (aligned body + helper STEP/STL, model-only 3MF, slice evidence, receipts). A
   session in spool-rack checkpoints it under that repo's rules (PRINT-CANDIDATES, DESIGN-JOURNAL,
   generic commit identity). fdm-gen never commits to another repo.
4. **Site:** add one project entry in `thereprocase.github.io/lib/projects.ts` plus a landing page fed
   by `fdm-gen`'s `site.json`, under the existing Gridline flow. The site repo is edited only when
   publishing, and only by a session working in that repo.
5. **License:** pick one before the first public commit (open question Q4). Dependencies: Warp
   Apache-2.0, manifold3d Apache-2.0, pyamg MIT, TopOpt_in_PETSc LGPL (used only as an *external
   reference oracle*, not linked). The DTU GPU codes have no licence (spool-rack finding) and must not
   be copied.

---

## 6. Phased roadmap

Durations assume one human plus agents, part-time. They are guesses, labelled as such.

### P0: foundations and parity (about 1-2 weeks)

Build: repo, schemas, receipts/runner, a canonical G-code parser (merging three), ports of
`plastic_shape`, `gpu_hex`, contact and adaptive code, an Orca driver, and the bracket `problem.yaml`.

Acceptance tests:
- **P0-A parser parity:** from the archived `g-recheck/2w-5layers/slice-evidence.zip`, credited
  E = 70,979.8 mm³ and sacrificial E = 6,940.5 mm³, matching to <= 1e-6 relative. The restored
  extruder offset is `(0,2)` for P1S slices.
- **P0-B arcs:** the same test part sliced with Orca arc fitting on and off gives credited volume
  within 0.1% and occupancy agreement within the spool-rack 0.005 mm band. (The current spool-rack
  parser would fail this, and that is the point.)
- **P0-C FEM parity:** the ported operator passes every spool-rack GPU fixture
  (`validate_gpu_hex`, contact, adaptive) with the same tolerances on second workstation. The new anisotropic `ke`
  path with isotropic inputs is bitwise-identical to the old path on the fixtures.
- **P0-D slicer modifier spike:** confirm which Orca settings a *modifier* volume can override
  (infill density and pattern certainly; wall loops and skins **unverified**). The answer determines
  how much massing S4 can express. Record the result as a rule/capability file.
- **P0-E determinism:** two runs of S0-S2 on the bracket produce identical hashes.
- Publish: nothing (internal).

### P1: MVP, an orientation-aware topopt of the spool bracket (about 3-5 weeks)

Scope: compliance minimisation with a volume or mass constraint and two load cases.
`DensityTopOpt` uses SIMP and a density filter, plus the AM overhang filter along the print z axis.
Material is orthotropic with **one bead class** (no shell emulation yet), using an ASSUMED card swept
over the anisotropy ratio. Use 3 orientations: flat-on-side (current), standing on the wall plate, and
standing on the tip. Then run S4-S7 end to end, with the truth solve on the leader of each orientation.

**Why the bracket:** it has printed ground truth (the E13 ASA archive), eight sliced controls with
hashes, a precise interface contract, solved isotropic baselines (G 4.3355 mm and others), and a
known user need. **Its weakness:** the layers are already parallel to the bending plane, so "print it
on its side" is the expected answer. P1 turns that weakness into a test.

Acceptance tests:
- **P1-A optimiser known answer:** a 3D cantilever benchmark matches a reference isotropic code
  (TopOpt_in_PETSc or a published top3d result) in final compliance within a stated tolerance on the
  same grid and parameters (Sauron to set the tolerance).
- **P1-B orientation known answer:** with E3/E1 = 1 (isotropic control), the three orientations'
  optimised compliances agree to within the overhang-filter effect alone. With E3/E1 <= 0.7 (assumed),
  flat-on-side ranks first and the gap grows as the ratio falls. If this does not happen, the
  anisotropy plumbing is wrong.
- **P1-C exact interfaces:** after S4, every keep_in region differs from the source B-rep by <= 1e-3
  mm³ symmetric difference, and keep_out regions contain zero material.
- **P1-D printable:** the extracted leader slices in Orca with 0 support roads, passes all hard rules
  at geometry and toolpath level, and fits the P1S bed and exclusions.
- **P1-E honesty table:** the leader, E13, G (8 walls), and E+F are run on the **same** truth pipeline
  with the **same** material card, and the table reports spent volume, max displacement, raw peak and
  eroded fraction. The design-vs-truth discrepancy is *measured and published*. A small discrepancy
  is not an acceptance criterion; measuring it is.
- Publish: an fdm-gen landing page ("MVP: method, bracket results, what is assumed"), with the
  limitations box first, as the spool-rack README style does.

### P2: process-aware massing and a part where orientation is hard (about 4-6 weeks)

Scope: the slicer emulator (wall shells as per-layer erosion, skins as z-erosion, an infill class
palette); output of body + modifier 3MFs; multiple bead classes with wall-tangent bins; a second
part chosen so that orientation trades off load-path anisotropy against overhang and support.

Part candidates (decide in round 2, open question Q2): a D9-P5 part with a non-trivial `PRINT_Z`
(such as the plug-holder arm or clamp shoulder), the Dell 5560 wall-mount arm (cantilever plus
bores), or a part from a collaborator. Criterion: *at least two orientations must be competitive under
isotropic assumptions*, so anisotropy is what decides between them.

Acceptance tests:
- **P2-A emulator validity:** emulator material vs the real Orca credited material on 5+ shapes and
  3 wall/skin schedules. Occupancy disagreement is reported per class. Target band to be set by
  Sauron/Legolas, with the spool-rack 50,000-sample method reused.
- **P2-B modifier round trip:** the massing the optimiser intended equals the massing in the slicer
  output, within the emulator band, for every modifier region.
- **P2-C orientation decision:** on the P2 part, the isotropic and anisotropic runs choose
  **different** orientations or different massings, and the truth stage confirms the anisotropic
  choice under the swept card. If it does not, publish that result.
- Publish: the constraint catalogue v0 page (rules, levels, evidence status) and emulator
  validation figures.

### P3: strength, calibration and one physical test (about 4-8 weeks, printer-bound)

Scope: coupon campaign (bead-direction, in-layer transverse and interlayer tension/shear for PETG
and ASA at the P1S process); material cards move from ASSUMED to COUPON_MEASURED; strength criterion
in the truth stage, then as an aggregated constraint in design (Sauron); one optimised part and one
control printed and load-tested.

Acceptance tests:
- **P3-A cards:** each card has coupon evidence with scatter, and the truth stage reports results
  under mean and lower-bound properties.
- **P3-B physical:** measured stiffness of the optimised part and the control falls inside the
  prediction band, and the observed failure location matches a predicted critical region. If not,
  publish the miss.
- Publish: the physical results page, using spool-rack's qualification language (simulation pass is
  not a rating).

### P4: generalisation and handoff to users like a collaborator (ongoing)

CLI (`fdmgen run problem.yaml`), documented authoring of problems from STEP, rule catalogue v1,
two more parts, and an optional `ParametricEvo` path for CAD-family designs. Acceptance: a person who
did not write the code runs a new part from STEP to sliced 3MF and a report using only the docs.
Publish: tool release and catalogue.

---

## 7. Top risks and early de-risking

| # | Risk | Likelihood / impact | De-risk early by |
|---|---|---|---|
| R1 | **No real anisotropic data.** Every ranking rides on assumed E3/E1 and interlayer strength. | High / high | P1 sweeps ratios (P1-B); start the coupon print plan during P1 (the printer is idle); cards carry `status`. |
| R2 | **Design model and printed truth disagree** (coarse grid vs 2-wall 0.84 mm perimeters; voxel erosion lost 4-17% of material in spool-rack crops). | High / high | Measure it in P1-E before investing in the emulator. Run the feedback calibration loop. Keep fidelity tags on every metric. |
| R3 | **Solver convergence and scale** (Jacobi-CG failed on whole-G; SIMP contrast worsens conditioning). | High / high | Multigrid before the optimiser. Design grid at 0.6 mm or coarser. Truth solves only for finalists, with time budgets and preserved failures. Legolas to benchmark. |
| R4 | **The slicer cannot express the intended massing** (modifier limits; Orca updates change paths). | Medium / high | P0-D spike. Pin the Orca exe and profile hashes. Treat a version bump as a re-baseline event. |
| R5 | **Frame and transform bugs** (precedents: P1S offset, `PRINT_Z` vs `pose`). | Medium / high | Single `Rotation` and frame-tagged vectors. Round-trip tests part to print to bed to G-code. |
| R6 | **House rules violated by design** (ersatz stiffness, percentile peaks) when optimisation code leaks into verification. | Medium / high | Separate `fem.design` and `fem.truth` entry points with different invariants checked in code. Truth refuses `Emin > 0`. |
| R7 | **Scope creep** into stress-constrained anisotropic topopt, orientation as a continuous variable, multi-axis. | High / medium | Compliance first; a discrete orientation set; stress constraints only in P3; non-goals written down (section 2). |
| R8 | **Coupling to frozen evidence repos.** | Medium / medium | Port plus parity tests, hash pins, hand-off packages (section 5). |
| R9 | **Machine availability** (compute-box shared and busy; Windows commit limit; laptop GPU). | Medium / medium | Design P0-P2 to fit PC + second workstation. compute-box is an accelerator for orientation sweeps after a heads-up. Runs are resumable and content-addressed. |
| R10 | **Overclaiming on the site.** | Medium / high (reputation) | Each metric carries a `fidelity` and `scope` (3.5). Report pages show limitations first. Failures are published. |

---

## 8. Architecture findings on the existing code (house format)

### Gandalf — Opus

**Findings:**
1. **[severity: warning]** `spool-wall-rack/analysis/rev-g2/plastic_shape.py:81` — Extrusion is parsed only for `G0/G1/G92`. G2/G3 arcs are ignored, so position tracking breaks silently if Orca arc fitting is ever enabled. The D9 `path_reader.py:15-55` handles arcs. Fix: one canonical parser in fdm-gen with an arc fixture (P0-B).
2. **[severity: warning]** `spool-wall-rack/analysis/rev-g2/plastic_shape.py:35,127` — The parser has a G-specific default transform and a process-policy assert (`no Sparse infill`) built in. Fix: transforms and policies become explicit inputs; the parser only parses.
3. **[severity: warning]** `5680-dock/desk-dock/D9-P5/build_d9.py:102-108` — Orientation is encoded twice (`pose()` rotations and `PRINT_Z` vectors). Fix in fdm-gen: one rotation object derives both.
4. **[severity: warning]** `spool-wall-rack/analysis/rev-g2/gpu_hex.py:140,150` — One shared `ke` for every cell. Fine for verification of uniform material, but it blocks SIMP and anisotropy. Fix: a class- and bin-indexed `ke` stack plus a per-cell scale, keeping the matrix-free kernel.
5. **[severity: note]** `spool-wall-rack/analysis/rev-g2/evo_screen.py:54-58` — Boundary nodes, hotspot and cache paths are hard-coded to G. Reuse the three-stage policy; do not reuse the class.
6. **[severity: note]** `5680-dock/desk-dock/D9-P5/prepare_and_slice.py:92` and `tools/coupon-pipeline/README.md` — The Orca path is hard-coded, and the live pipeline lives in an external Codex worktree with absolute paths. Fix: an Orca driver with a configured exe and pinned hashes.
7. **[severity: note]** Three G-code parsers (`plastic_shape.read_paths`, `D9-P5/path_reader.paths`, `coupon-pipeline/.../verify_mixed_plate.roads`). This debt grows with every new project. Consolidating now is cheaper than later.

**Summary:** The foundations are sound and unusually well evidenced. The work they need is consolidation and generalisation, not reinvention. The main threat is mixing design-time approximations into the verification path.
**Verdict:** ISSUES FOUND (0 critical, 4 warning, 3 note)

---

## 9. Numbered decisions (proposed, for round-2 challenge)

1. New repo `fdm-gen`, Python package `fdmgen`, uv-managed; port with parity, never import.
2. Two FEM roles (design / truth) with separate entry points and invariants.
3. The slicer generates toolpaths; output is body + modifiers + per-region settings; truth reads G-code.
4. Re-voxelise in the print frame for each orientation; layers on grid planes.
5. A discrete orientation candidate set in v1; each candidate is optimised independently and in parallel.
6. Printability rules are data with three check levels (design / geometry / toolpath) and evidence status.
7. Material cards are orthotropic per bead class with a `status`; P1 runs on ASSUMED cards with a sensitivity sweep.
8. Exact interfaces are booleaned back from source B-rep after extraction; meshes come first.
9. Receipts for every stage; content-addressed run store on D:; failures preserved.
10. MVP part: spool bracket (pipeline validation + known-answer orientation test); P2 adds a part where orientation is genuinely hard.

## 10. Open questions

- **Q1** Which machine has the RTX 3080 Ti used for spool-rack GPU work: second workstation? (This PC is an RTX 3500 Ada Laptop, 11.5 GiB.)
- **Q2** P2 part: a D9 arm or clamp, the Dell 5560 arm, or a part from a collaborator? Does a collaborator have a candidate and data he can share?
- **Q3** Do Orca 2.4.2 modifier volumes support per-region `wall_loops` and top/bottom shell overrides via CLI 3MF metadata? (P0-D.)
- **Q4** License for fdm-gen (MIT or Apache-2.0 suggested; avoid LGPL-linking constraints).
- **Q5** Can the truth stage reach acceptable accuracy at 0.2 mm on whole parts, or does it need sub-bead resolution in critical regions (spool-rack: 4.31% omission even at 0.1 mm XY in a crop)? Legolas/Sauron.
- **Q6** Is orientation-dependent creep at 85 F in scope for P3, or explicitly excluded?

## Sources

- Autodesk, [Manufacturing methods in Generative Design](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-MFG-METHODS.htm); [Achieving better AM outcomes in generative design](https://www.autodesk.com/products/fusion-360/blog/unlocking-better-additive-manufacturing-outcomes-generative-design/)
- nTop, [Overhang constraint](https://support.ntop.com/hc/en-us/articles/360060738793-How-to-use-the-overhang-constraint-in-Topology-Optimization); [AM constraints update](https://www.ntop.com/resources/product-updates/topology-optimization-additive-manufacturing-constraints-in-ntop-platform/)
- Altair, [Inspire Overhang](https://help.altair.com/inspire/en_us/topics/inspire/structure/draw_overhang_c.htm)
- Teton Simulation SmartSlice: [Fabbaloo review](https://www.fabbaloo.com/2020/02/teton-simulations-smart-slice-tool-works); [Optimize workflow docs](https://help.tetonsim.com/cura/tutorial-optimize); [3DPI launch](https://3dprintingindustry.com/news/teton-simulation-launches-smart-slice-software-plug-in-for-ultimaker-essentials-176114/)
- Hexagon, [Digimat 2023.3 AM User's Guide](https://documentation-be.hexagon.com/bundle/Digimat_2023.3_AM_User_Guide/raw/resource/enus/Digimat_2023.3_AM_User_Guide.pdf)
- DTU, [TopOpt_in_PETSc](https://github.com/topopt/TopOpt_in_PETSc); Smit et al., [Python wrapper, LGPL-2.1](https://github.com/thsmit/TopOpt_in_PETSc_wrapped_in_Python)
- [Scikit-Topt (JOSS)](https://joss.theoj.org/papers/10.21105/joss.09092.pdf); [DL4TO](https://dl.acm.org/doi/10.1007/978-3-031-38271-0_54)
- Wu, Clausen, Sigmund (2017), [Minimum compliance topology optimization of shell-infill composites for AM](https://research.tudelft.nl/en/publications/minimum-compliance-topology-optimization-of-shellinfill-composite/), CMAME 326
- Langelaar (2016), [An additive manufacturing filter for topology optimization of print-ready designs](https://www.researchgate.net/publication/305622859_An_additive_manufacturing_filter_for_topology_optimization_of_print-ready_designs)
- [Simultaneous optimization of build orientation and topology for AM](https://www.researchgate.net/publication/341288654_Simultaneous_optimization_of_build_orientation_and_topology_for_additive_manufacturing)
- [Anisotropic multicomponent topology optimization with build orientation design (arXiv 1911.10393)](https://arxiv.org/pdf/1911.10393)
- [Topology optimization for multi-axis AM considering overhang and anisotropy (arXiv 2502.20343)](https://arxiv.org/pdf/2502.20343)
- [AM of stiff and strong structures leveraging printing-induced strength anisotropy (Addit. Manuf. 2023)](https://www.sciencedirect.com/science/article/abs/pii/S2214860423003433); [TO for AM with strength constraints considering anisotropy (JCDE)](https://academic.oup.com/jcde/article/10/2/892/7110403); [TO for FDM parts considering hybrid deposition path (PMC7463923)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7463923/)
- Fang et al., [Reinforced FDM (TOG 2020)](https://github.com/GuoxinFang/ReinforcedFDM); Liu et al., [Neural Slicer for Multi-Axis 3D Printing (TOG 2024)](https://arxiv.org/pdf/2404.15061)
- MFEM [nonconforming mesh notes](https://mfem.org/howto/ncmesh/) (cited by spool-rack ADAPTIVE-MESH.md)
