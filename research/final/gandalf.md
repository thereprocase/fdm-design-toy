# Gandalf (final): system architecture and phased roadmap for `fdm-gen`

Round 3 integrated report. It replaces `gandalf.md` (kept unchanged as the round-1 record) and folds in the
reviews by Sauron, Legolas and Frodo (`reviews/*-on-gandalf.md`), plus my own round-2 self-corrections.
Section 11 records how every review finding was handled, and section 10 lists the disputes I could not settle.
Where the round-1 text was wrong, this version corrects it rather than staying consistent with it.

Angle: architecture, reuse, data model, pipeline, repo layout, roadmap, risks.
- Mechanics (Sauron), compute (Legolas) and the workflow and constraint catalogue (Frodo) are owned elsewhere. This
  report adopts their results where the reviews converged.
- Repos read (read-only): `spool-wall-rack` @ `14338e9`, `5680-dock` @ `05a770b`, `novel-cad-skill`, `double-bead`,
  `thereprocase.github.io`.
- I ran no code beyond file inspection, a few `grep`/JSON reads, and `nvidia-smi`.

---

## 0. Executive summary

1. **Build from what exists.** The repos already hold:
   - a G-code-to-credited-material reader;
   - a matrix-free GPU hex FEM with contact and adaptive coarsening;
   - an Orca 3MF writer with body and modifier parts;
   - Orca CLI drivers with per-object toolpath audits;
   - a screen-then-verify search loop with receipts;
   - keep-out solids, build-direction vectors and near-bed self-support / teardrop operators.

   Nobody has packaged these as a general tool. Section 1 gives a disposition for each, with file paths.
2. **The material model changes what drives orientation (Sauron's finding, adopted).** For PETG/ASA the vendor data
   gives E_Z/E_XY = 0.85-0.92, so directional stiffness varies by only about 15%. **Compliance alone is a weak signal
   for choosing an orientation.** Orientation is decided by:
   - inter-layer strength (Z/XY tensile ratio 0.68-0.84 in the vendor data);
   - printability (overhang, support);
   - massing (slicer walls and skins thin out on mid-angle surfaces:
     `t(α) = max(n_w·w·sin α, n_t·h·cos α)`, minimum about 0.64 mm near α = 50° for 2 walls × 0.42 mm and
     5 skins × 0.2 mm).

   The roadmap is re-ordered around this. My round-1 compliance-based known-answer test (P1-B) is withdrawn.
3. **Two FEM roles, unchanged.**
   - The *design solver* uses a coarse grid, one transversely isotropic (TI) stiffness per orientation, a SIMP floor
     E_min > 0, many solves, and **one shared element matrix (Ke) times a per-cell scale**.
   - The *truth solver* reads real G-code material at 0.2 mm, with no ersatz stiffness, a class- and angle-indexed Ke
     library, every stress sample kept, and few solves.

   The spool-rack rule "no density floor or ersatz stiffness" binds the truth solver only.
4. **The slicer generates toolpaths.** The optimiser's output is a body mesh, modifier meshes and per-region
   settings, written with the existing `package_part.py` pattern. The truth stage reads the real G-code back. That
   includes undoing slicer-side scaling (`filament_shrink`), which round 1 missed.
5. **Optimisation re-voxelises in the print frame for each candidate orientation.** Layers sit on grid planes, so
   the overhang filter, Z quantisation and the coating all work. Legolas's fixed-grid / rotated-tensor approach
   survives as **analysis mode** (scoring a frozen design across orientations). All three reviewers agree.
6. **Use a deliberately non-cubic design voxel, 0.5 × 0.5 × 0.6 mm (dz = 3 layers), with a 5-point support
   stencil.** The voxel shape then *sets* the overhang angle: at least about 50° from horizontal along the grid axes,
   steeper on the diagonals. That builds in the margin above Orca's 45° threshold, which the user's own wedge test
   shows is not safe at exactly 45°. Massing (walls and skins) is not resolvable at this grid; it arrives in P3 as a
   calibrated sub-cell shell model. Section 10 records this as a dispute.
7. **New roadmap order.**
   - P0: parity and foundations, including multigrid as an exit gate.
   - **P1: orientation analysis of existing parts.** This is useful to a collaborator's "simulate parts I've already designed"
     immediately.
   - P2: topology optimisation MVP on the spool bracket, solid body, ranked by the inter-layer index.
   - P3: massing and a second, orientation-hard part.
   - P4: coupons and a physical test.
   - P5: generalisation.
8. **New repo `D:\Code\Models\fdm-gen\`, uv package `fdmgen`.**
   - Port with provenance headers and parity tests; never `sys.path` into spool-rack.
   - Never write into other repos.
   - Existing builders are read through adapters, not edited.

---

## 1. What exists, and what to reuse, wrap or retire

### 1.1 Inventory with dispositions

| Asset (path under `D:\Code\Models\`) | What it does | Disposition | Required changes / cautions |
|---|---|---|---|
| `spool-wall-rack/analysis/rev-g2/plastic_shape.py` (415 lines) | Parses Orca G-code into per-path width, height, role, E and segment direction. Separates credited from sacrificial bridge material. Builds layer polygons. Provides `contains`, `equivalent_thickness`, `integrated_volume`. Restores the P1S `0x2` extruder offset. | **Port as the truth-material core** | **Parser:**<br>- Only `G0/G1/G92` are parsed; G2/G3 arcs are skipped.<br>- `main()` asserts footer agreement < 0.1% at `plastic_shape.py:380`, which catches dropped arcs. `read_paths()` used as a library has **no** such guard.<br>- The D9 profile has `enable_arc_fitting = "1"` (`D9-P5/profiles/process.json:150`), so arcs are real today.<br><br>**Hard-coded assumptions:**<br>- the G transform (`:35`);<br>- the 0.2 mm nominal layer;<br>- a process-policy assert (`no Sparse infill`, `:127`).<br><br>**Not undone:** `filament_shrink` scaling. |
| `5680-dock/desk-dock/D9-P5/path_reader.py`; `5680-dock/tools/coupon-pipeline/architect/verify_mixed_plate.py` (`roads`) | Two more G-code parsers. `path_reader` handles G2/G3. `roads` does per-object support/bridge counting. | **Merge all three into one `fdmgen.slicer.gcode`** | It asserts the footer check internally and has fixtures for arcs, offset, relative/absolute E, object labels and shrink. |
| `spool-wall-rack/analysis/rev-g2/package_part.py` | **Writes model-only Bambu/Orca 3MF:** one `normal_part` plus N `modifier_part`, object-level `wall_loops`/skins/`wall_generator`, per-modifier `sparse_infill_density` 100%, deterministic zip timestamps, receipt | **Port as the S5 3MF writer** | Hard-coded bracket build transform (`'0 -1 0 1 0 0 0 0 1 12.5 274.2465 0'`) becomes an input. Only infill density is set per modifier; per-region `wall_loops`/skins are **unverified** (P0-D). Missing from my round-1 inventory; Frodo found it. |
| `spool-wall-rack/analysis/rev-g2/gpu_demo_slice.py:115-145` | Effective-settings check: `wall_loops`, skins, infill, printer, filament, nozzle, and modifier roles from `Metadata/model_settings.config` | **Port as PROC-001's checker** | Generalise the key list from the catalogue. |
| `spool-wall-rack/analysis/rev-g2/gpu_hex.py` (230 lines) | Matrix-free Q1 hex on Warp, Jacobi-CG, face-connectivity node splitting, 8-point stress recovery, unilateral wall contact | **Port and extend twice** | **Design role:** keep the single shared `Ke`, now the TI card rotated once per orientation, plus a per-cell SIMP scale.<br><br>**Truth role:** a class-, angle- and bond-bin-indexed `Ke` library. 36 bins of 5° change C by ≤ 0.63% (Sauron). Per-cell C is used only in stress recovery and failure evaluation.<br><br>**Shear order:** `gpu_hex` orders shear as (xy, yz, xz). Canonical-to-`gpu_hex` permutation `[0,1,2,5,3,4]` gets a test. |
| `gpu_contact.py`, `gpu_demo_adaptive.py`, `gpu_demo_adaptive_operator.py`, `gpu_coarse_geometry.py` | Contact with time budgets; 2:1 adaptive coarsening with hanging-node constraints | **Port into the truth solver** | Adaptive merging of anisotropic cells must respect class and orientation, or use the exact laminate C (Sauron §2.6). |
| `gpu_multigrid.py` (207 lines) | PyAMG smoothed-aggregation hierarchy over the adaptive coarse projection, assembled CSR, GPU V-cycle | **Reference only. Structured geometric MG-PCG is *new code*, not a port** (Legolas) | Jacobi-CG doubles its iterations per halving of h (790 → 1570, measured). Two full-G solves failed: 1,000 iterations / 15.67 s and 12,000 / 187.74 s (`ADAPTIVE-MESH.md:102-103`). |
| `mesh_from_cells` (in `gpu_hex.py`) | Face-connected node splitting | **Port and rewrite (vectorise)** | 7.66 s per 232 k nodes in a Python loop. Minutes at 4-8 M cells. It is on the truth stage's critical path (Legolas B7). |
| `validate_gpu_hex.py`, `validate_gpu_contact.py`, `validate_gpu_demo_adaptive.py`, `validate_plastic_shape.py`, `validate_mechanics.py` + `validation/*.json`, `gpu-validation/*.json` | Independent fixtures | **Port as the parity suite** | Run first on the **pinned Warp 1.17.0** (`requirements-gpu.txt`). Legolas measured on 1.18.0; an upgrade is a separate re-baseline. |
| `solve_plastic.py` `interface_loads()` + `adaptive-validation/g-h0p2-interfaces.json` | Contact-derived seat loads and the restraint model for the bracket | **Port with a parity test. This is the source of the bracket load block.** | My round-1 equal vertical split (58.86 N per seat) was wrong (section 3.1). |
| `evo_search.py`, `evo_screen.py`, `evo_refine.py`, `evo_verify.py`, `evo_transfer.py` | Bounded GA, cheap 2D screen, actual-slice finalists, leader refinement, ledgers | **Reuse the three-stage policy; port only the GA kernel** | `evo_screen.Screen` hard-codes G's wall nodes, hotspot and paths (`:54-58`). |
| `reduced_plastic.py` | 2D plane-stress reduced model | **Keep bracket-specific** | Valid only for plate-like layered parts. |
| `mesh_plastic.py`, `audit_volume_mesh.py`, TetGen/fTetWild route | Conforming tet meshing | **Retire** | Rejected on topology and quality; the jobs were stopped (`MESHING-NOTES.md`). |
| `designs/rev-g2/INTERFACE-CONTRACT.md`, `shape-seeds/moulding-clearance.json`, `G2-BRIEF.md` | Interfaces, keep-outs, loads, movement budgets, temperatures, fracture factor 4 | **Pin by sha256 in the first `problem.yaml`** | The **E = 1,000 MPa "effective planning model"** (`G2-BRIEF.md:66`) is a sustained-load basis, not the short-term vendor modulus (section 3.3). |
| `print-controls/*`, `g-recheck/*` | Eight controls plus five wall/skin cases, real slices, hashes | **Ground-truth fixtures and baselines** | P2-E compares on the same truth pipeline, loads and modulus basis. |
| `5680-dock/desk-dock/D9-P5/build_d9.py` `selfsupport()` (`:41`) | CadQuery B-rep. Prisms faces flatter than 45° down to the bed, **only for faces 0.4-4.5 mm above the bed** (`maxdrop=4.5`). Respects keep-out. **Does not report added volume.** | **Builder-path reuse only** | A near-bed fixer, not a general overhang repair. My round-1 text overstated it. On the optimisation path, overhang is the AM filter; repair is voxel-level and must emit a delta (Frodo T10). |
| `build_d9.py` `bore_td()` (`:85`) | Teardrop crest, 40° from vertical (= 50° from horizontal), tangent | **Reuse as the orientation-dependent interface variant** (`teardrop: auto`) | Crest direction depends on the build direction, so it is applied per candidate orientation to keep-in bores (Frodo finding 8). |
| `build_d9.py` `PROTECT{part:[solids]}`, `PRINT_Z` + `pose()` (`:102-108`) | Keep-out solids; build vectors and separate hand-written rotations | **Generalise into `regions` and one `Rotation`** | **Same orientation stored twice** (`PRINT_Z` vectors and `pose()` rotations). In fdm-gen, one rotation derives both. `build_d9.py` runs at import with no `main()`, so `PROTECT` is read by an **adapter** from exported solids, never by importing the builder. |
| `dress.py`; `overhang-threshold-test/` | Edge-dressing rules; four sliced wedges | **Become catalogue entries with evidence** | `build.py:10` comments "angle from vertical", but `run = 15·tan(ang)` is the vertical drop over a 15 mm horizontal run. So the file name is the slope **from horizontal**. `wedge-45deg` received **2,421 support segments**; `wedge-55deg` received **0**. This is slicer behaviour (tier S), not print capability. |
| `prepare_and_slice.py`, `verify_plates.py`, `tools/coupon-pipeline/architect/*` | 3MF placement, Orca CLI with isolated `--datadir`, plate checks, per-object audit | **Wrap into `fdmgen.slicer`** | Hard-coded Orca path (`prepare_and_slice.py:92`). The coupon pipeline is a snapshot with Codex-worktree absolute paths. `verify_plates.py` sets every object `strict: False`, which hides where support went (Frodo T13). |
| `novel-cad-skill/scripts/check_printability.py` | Mesh checks with spec thresholds | **Port as the first M-level checkers** | Assumes +Z build. Samples 10 Z levels (`Z_SAMPLE_COUNT = 10`) and should sample every layer. Bridge default 20 mm disagrees with `SKILL.md:334` (15 mm PETG). |
| `novel-cad-skill/ARCHITECTURE.md` | build123d + Manifold choice | **Adopt** | Use build123d/OCP for STEP import and interface solids, and manifold3d for mesh booleans. |
| `double-bead/docs/SPEC.md` | Rules in extrusion widths, Arachne bead-count algebra | **Adopt the `w`/`h` unit convention** | Arachne vs classic changes bead outcomes: D9 uses `classic` (`process.json:278`), spool-rack uses `arachne` (`package_part.py:31`). Rules must key on `wall_generator`. |
| `spool-wall-rack/analysis/rev-g/run_native.py` | Crash-tolerant native CAD worker | **Reuse for native-CAD stages** | — |
| `5680-dock/tools/print-log.py`, `docs/prints/print-log.json` | Print outcomes tied to STL hash, profile and commit | **Link candidate IDs to print-log entries** | Closes the loop from a printed result to calibration (Frodo). |
| Receipt/ledger conventions (`receipt.json`, `ledger.json`, `SHA256SUMS.json`, status strings) | Reproducibility and scope | **Formalise as one schema** (3.6) | Map historical status strings onto the verdict ladder verbatim. |

### 1.2 What the existing work establishes and does not

**Established:**
- The occupancy cache agrees with an independent exact capsule oracle **outside a 0.005 mm boundary band**
  (`validation/matrix-shape-validation.md:13`). That is a numerical consistency check of the parser and cache. It
  does **not** show agreement with printed geometry: bead neck, stadium section and squish are not represented.
- GPU elasticity and contact pass independent fixtures.
- The adaptive operator equals the projected fine operator.
- The three-stage search ran 100 proposals in 11 min 18 s, with finalists in about 5-10 min each.

**Not established:**
- anisotropic material;
- design-time optimisation;
- convergence at whole-part 0.2 mm (Jacobi-CG fails);
- any physical calibration of the 1 GPa planning modulus.

`print-controls/README.md` says it directly: the results "do not demonstrate a reliable 5-minute architecture loop."

### 1.3 Hardware reality

| Machine | Facts | Role until Q1 is answered |
|---|---|---|
| This PC | **RTX 3500 Ada Laptop, 11.5 GiB** (`nvidia-smi`), i9-13900H, 64 GB. Measured 151-184 M cell-matvecs/s FP64 with the existing operator. An 11.25 M-cell box fits (Legolas). Warp 1.18.0 ran natively on Windows (Legolas). | **Default for both design and truth GPU work.** Orca 2.4.2 slicing. CAD. |
| second workstation | Ryzen 5800X3D, 64 GB, WSL. GPU **unknown**. Spool-rack's GPU runs were on an RTX 3080 Ti 12 GiB under WSL2, machine unrecorded. | CPU batches: prescreens, G-code parsing, occupancy. GPU truth worker only if Q1 confirms a 3080 Ti. |
| compute-box | 40 threads, 300 GB, no GPU, shared, busy with CFD | **Not on the P0-P2 critical path.** Later: RAM-heavy 0.2 mm verification and parallel CPU batches, once a matrix-free CPU MG exists and the owner has had a heads-up. Assembled PyAMG measured 85 s setup + 81 s solve at 1.41 M cells, so it is not an inner-loop solver (Legolas). |

---

## 2. Prior art at the system level, and the gap

| System | Orientation | Overhang in optimiser | Anisotropic material | Shell/infill (slicer) awareness | Reads real toolpaths back | Open/programmable |
|---|---|---|---|---|---|---|
| Autodesk Fusion Generative Design | X+, Y+, Z+ only; separate outcome set per direction ([docs](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-MFG-METHODS.htm); [blog](https://www.autodesk.com/products/fusion-360/blog/unlocking-better-additive-manufacturing-outcomes-generative-design/)) | Yes | Not documented | No | No | No |
| nTop | Any build vector ([overhang constraint](https://support.ntop.com/hc/en-us/articles/360060738793-How-to-use-the-overhang-constraint-in-Topology-Optimization); [release](https://www.ntop.com/resources/product-updates/topology-optimization-additive-manufacturing-constraints-in-ntop-platform/)) | Yes | Not in topology optimisation per the docs found | Lattices/implicits, not FDM perimeters | No | Partly |
| Altair Inspire | Print direction from bounding-box face ([Overhang](https://help.altair.com/inspire/en_us/topics/inspire/structure/draw_overhang_c.htm)) | Yes | No | No | No | No |
| Teton SmartSlice (Cura plugin, about 2020) | User's orientation | n/a | Print-parameter-dependent FEA | **Optimises walls, infill and top/bottom per region** ([Fabbaloo](https://www.fabbaloo.com/2020/02/teton-simulations-smart-slice-tool-works); [docs](https://help.tetonsim.com/cura/tutorial-optimize)) | Partial | No |
| Hexagon Digimat-AM/RP (FFF) | Given part | n/a | **Toolpath-mapped local anisotropy** ([guide](https://documentation-be.hexagon.com/bundle/Digimat_2023.3_AM_User_Guide/raw/resource/enus/Digimat_2023.3_AM_User_Guide.pdf)) | Yes | **Yes** | No |
| TopOpt_in_PETSc (DTU, LGPL) | Structured 3D grid | Via an extension | No | Local-volume infill constraint in the [Python-wrapped fork (LGPL-2.1)](https://github.com/thsmit/TopOpt_in_PETSc_wrapped_in_Python); [base](https://github.com/topopt/TopOpt_in_PETSc) | No | Yes |
| FEniTop, DL4TO, Scikit-Topt, TopOpt.jl | Generic | No | No | No | No | Yes ([Scikit-Topt](https://joss.theoj.org/papers/10.21105/joss.09092.pdf); [DL4TO](https://dl.acm.org/doi/10.1007/978-3-031-38271-0_54)) |
| Shell-infill topology optimisation ([Wu, Clausen, Sigmund 2017](https://research.tudelft.nl/en/publications/minimum-compliance-topology-optimization-of-shellinfill-composite/)) | Single | No | No | **Optimised shell + infill** | No | Paper |
| AM filter ([Langelaar 2016](https://www.researchgate.net/publication/305622859_An_additive_manufacturing_filter_for_topology_optimization_of_print-ready_designs); 2017 SMO 55:871) | Grid-aligned | **Yes** | No | No | No | Reference code |
| Orientation + topology ([simultaneous](https://www.researchgate.net/publication/341288654_Simultaneous_optimization_of_build_orientation_and_topology_for_additive_manufacturing); [arXiv 1911.10393](https://arxiv.org/pdf/1911.10393); [arXiv 2502.20343](https://arxiv.org/pdf/2502.20343)) | **Optimised** | Yes | **Yes** | No | No | Papers |
| FDM strength anisotropy in topology optimisation ([Addit. Manuf. 2023](https://www.sciencedirect.com/science/article/abs/pii/S2214860423003433); [JCDE](https://academic.oup.com/jcde/article/10/2/892/7110403); [PMC7463923](https://pmc.ncbi.nlm.nih.gov/articles/PMC7463923/); Mirzendehdel et al. 2018, cited by Sauron) | Single | Some | **Yes** | Partly | No | Papers |
| Stress-aligned toolpaths ([Reinforced FDM 2020](https://github.com/GuoxinFang/ReinforcedFDM); [Neural Slicer 2024](https://arxiv.org/pdf/2404.15061)) | Multi-axis | Yes | Yes | Replaces the slicer | n/a | Research code |

**The gap** (as far as this search found; it was not exhaustive): no open, scriptable pipeline combines all five of:
1. a sweep over arbitrary build orientations;
2. a design model of **a real planar slicer's walls, skins and infill per layer**;
3. bead-level anisotropic material whose axes come from the orientation and the toolpath;
4. **re-analysis on the actual slicer output**;
5. a **published, calibrated, machine-checkable printability catalogue**.

Digimat is closest to the truth stage, and SmartSlice is closest to the massing stage. Neither is open or
generative.

**Non-goals:** multi-axis or non-planar printing, our own slicer, continuous-fibre paths, and treating orientation as
a gradient variable in v1.

---

## 3. Core data model

**Rules for the whole model:**
- Every vector and point carries a frame tag.
- Units are explicit (mm, N, MPa, s, °C). Rules may use `w`/`h` units, resolved against the active profile.
- Everything is content-hashed.
- Humans author YAML, validated by JSON Schema generated from pydantic models. Hashing uses canonical JSON.
- **Inputs that already exist as data are generated from their source, never retyped.** This covers loads, restraint
  models and `process_binding` from profile hashes. Both load errors the reviewers found came from retyping.

### 3.0 Frames (merged vocabulary)

| Frame | Definition | Notes |
|---|---|---|
| `design` (= part, CAD) | Frame of the supplied geometry | Loads, BCs, regions authored here |
| `installed` | Service frame; for the bracket X out of wall, Y up, Z along rods | Spool-rack's `model_to_installed`. Interface-contract coordinates are here. |
| `print` | +Z = build direction; layers are z = const | **Derived** from one `Rotation` (build direction d + spin ψ). Singular case d = −e_z handled explicitly. |
| `plate` | Orca bed coordinates after placement | The spin from Orca's arrange step is **read back** from the sliced 3MF item transform, never assumed. |
| `gcode` | `plate` minus the extruder offset (P1S `(0,2)`) | What the parser inverts. |
| `bead` | Per element `[t, e_z × t, e_z]` | Truth stage only. |

Matrices are named `R_<to>_<from>`. Tensors are stored in Mandel form internally, and converted to `gpu_hex` Voigt
order only at the solver boundary (Sauron §2.4).

### 3.1 Design problem spec (`problem.yaml`)

```yaml
schema: fdmgen/problem@0.2
id: spool-bracket-g2
units: {length: mm, force: N, stress: MPa}
provenance:     # hash-pinned; a mismatch is a hard error
  - {source: spool-wall-rack/designs/rev-g2/INTERFACE-CONTRACT.md, sha256: <pin>}
  - {source: spool-wall-rack/designs/rev-g2/shape-seeds/moulding-clearance.json, sha256: <pin>}
  - {source: spool-wall-rack/analysis/rev-g2/adaptive-validation/g-h0p2-interfaces.json, sha256: <pin>}
authoring: {route: adapter, adapter: fdmgen.adapters.spool_rack_g2}   # adapter | emit_problem | hand_yaml
frames:
  installed: {from: design, R: identity, t: [0,0,0]}
geometry:
  design_domain: {file: geom/envelope.step, frame: installed}   # NEW artefact; must be built in P0
  regions:
    - {id: rear_seat,   kind: keep_in,  role: interface, file: geom/rear_seat.step,
       print_variants: {horizontal_axis_bore: teardrop_auto}}
    - {id: front_seat,  kind: keep_in,  role: interface, file: geom/front_seat.step,
       print_variants: {horizontal_axis_bore: teardrop_auto}}
    - {id: mount_upper, kind: keep_in,  role: interface, file: geom/mount_upper_land.step}
    - {id: mount_lower, kind: keep_in,  role: interface, file: geom/mount_lower_land.step}
    - {id: screw_clear, kind: keep_out, role: clearance, file: geom/screw_driver_washer_access.step}
    - {id: moulding,    kind: keep_out, role: clearance, file: geom/moulding_zone.step}
    - {id: spool_sweep, kind: keep_out, role: motion_envelope, file: geom/spool_sweep.step}
load_cases:
  - id: full_12kg
    frame: installed
    loads:      # generated from interface_loads(117.72) / g-h0p2-interfaces.json, not typed
      - {type: bearing, region: rear_seat,  resultant_N: [-31.293, -75.121, 0], distribution: radial_nonnegative}
      - {type: bearing, region: front_seat, resultant_N: [ 31.293, -42.599, 0], distribution: radial_nonnegative}
    supports:   # restraint model string copied from the pinned JSON
      model: "Rigid washer axial restraint and rigid bore lateral restraint. ... Wall normal contact preserves voxel surface gaps."
      items:
        - {type: washer_axial_and_bore_lateral, region: mount_upper}
        - {type: washer_axial_and_bore_lateral, region: mount_lower}
        - {type: contact_unilateral, region: wall_face, normal: [-1,0,0], gap: from_geometry, friction: 0}
    checks: {resultant_N: [0, -117.72, 0], moment_about_each_dowel_axis: 0}   # lint asserts these
  - id: one_spool_delta
    derive: {from: full_12kg, mass_change_kg: 1.25, fresh_solve: required}
service: {sustained_F: 85, brief_loaded_F: 100}
requirements:   # truth-stage checks, each tied to a modulus basis
  - {id: movement, metric: max_resultant_displacement, load_case: full_12kg, max_mm: 4.0, modulus_basis: sustained_effective}
  - {id: delta, metric: displacement_change, load_cases: [full_12kg, one_spool_delta], max_mm: 1.0, modulus_basis: sustained_effective}
  - {id: fracture, metric: strength_factor, criterion: material_card, min: 4.0}
objective: {minimise: spent_extrusion_volume, report: [print_time_s, support_volume_mm3]}
orientation:
  mode: sweep                     # general form
  candidates: auto                # see S1
  override: {mode: fixed, up_in_installed: [0,0,1], reason: "product orientation; bending in layer plane"}  # used for product runs, not the MVP known-answer test
support_policy:
  default: forbidden
  regions: []                     # e.g. {region: X, allowed: true, access: hidden, reason: "..."}
infill_credit: {sparse: false}    # explicit per problem; spool-rack G2 = false; D9-style parts may opt in
rule_overrides:
  - {rule: BRG-002, value: {structural_credit_first_layer: 0}, reason: "G2 brief: sacrificial bridges get no credit"}
  - {rule: WALL-003, value: {min_walls: 2}, reason: "G2 hard requirement"}
acceptance_ladder: [GEOMETRY, TOOLPATH, SCREEN, FE_3D, COUPON, PRINTED, QUALIFIED]
```

**Three authoring routes** (answering Frodo's D6 / Q2):
1. New CadQuery/build123d builders call `fdmgen.emit_problem()`, a dependency-light module.
2. Existing builders (`build_d9.py`, spool-rack) are read by **adapters inside fdm-gen**. Adapters consume their
   outputs (`manifest.json`, exported STEPs, `PROTECT` solids exported once, pinned JSON) and never edit them.
3. External users (a collaborator) hand-write `problem.yaml` with STEP files, checked by `fdmgen lint`.

### 3.2 Process spec (`process.yaml`), expanded per orientation candidate

```yaml
schema: fdmgen/process@0.2
printer: catalog/printers/bambu-p1s-0.4.yaml     # bed, exclusions, extruder offset (0,2)
slicer: {name: OrcaSlicer, version: "2.4.2", exe_sha256: <pin>}
profiles: {machine: <sha256>, filament: <sha256>, process: <sha256>}   # all settings below are READ from these
derived_from_profiles:                 # filled by fdmgen, never hand-typed
  layer_height_mm: 0.2
  line_width_mm: {outer_wall: 0.42, inner_wall: 0.45, first_layer: 0.5}   # "w" is per region
  wall_generator: classic | arachne
  enable_arc_fitting: 0 | 1
  compensation: {filament_shrink_xy: 0.9946, xy_hole_compensation: 0, elefant_foot_compensation: 0.15}
massing_controls:
  walls: {min: 2, max: 8}
  skins_mm: {top: [1.0, 1.6], bottom: [1.0, 1.6]}
  modifiers: {allowed_densities: [1.0]}          # default; partial densities need infill_credit.sparse = true
                                                 # plus an infill card (status ASSUMED; zero-credit verification as bound)
proc_001_checked_keys: [wall_loops, top_shell_layers, bottom_shell_layers, sparse_infill_density,
                        support_threshold_angle, enable_support, wall_generator, enable_arc_fitting,
                        filament_shrink, elefant_foot_compensation, xy_hole_compensation]
```

### 3.3 Material card (`catalog/materials/*.yaml`)

```yaml
schema: fdmgen/material@0.2
id: petg-<grade>-p1s-0.2h
grade: "Bambu PETG HF | PETG Basic | Polymaker PETG | PolyLite ASA ..."   # one card per grade actually printed
process_binding: {profile_sha256: <filament>, <process>}                  # generated, not typed
tier: T0 | T1 | T2                       # card-level (Sauron D10)
convention:
  nu: "nu_ij = -eps_j / eps_i under sigma_i; reciprocity nu_ij/E_i = nu_ji/E_j"
  storage: mandel
  angle: slope_from_horizontal
classes:
  printed_solid_TI_z:                    # DESIGN stage: homogenised, transversely isotropic about print Z
    symmetry: transversely_isotropic_z
    E_p: {value: ..., tier_value: V}     # per-value provenance U/S/V/L/H (Frodo)
    E_z: {...}; nu_p: {...}; nu_pz: {...}; G_z: {...}
  bead_orthotropic:                      # TRUTH stage: axes from G-code (t, e_z x t, e_z)
    symmetry: orthotropic_bead
    E: [E1, E2, E3]; G: [G12, G13, G23]; nu: [nu12, nu13, nu23]
  sparse_infill: {status: ABSENT}        # present only if a problem opts into infill credit
strength:                                # Sauron's two-mode, degree-1 criterion
  criterion: two_mode_interlayer_v1
  X_t: {...}; Z_t: {...}; S_il: {...}
  bond_scaling: {model: "g(b) = b", status: HYPOTHESIS}   # inter-layer constants scaled by mapped bond fraction
modulus_basis:
  short_term: {E_p: ..., E_z: ...}                         # vendor / coupon, about 23 C
  sustained_effective: {E_p: 1000, ratio_source: "short-term ratio applied: ASSUMPTION"}  # spool-rack planning law
temperature: {curve: [[23, 1.0], [29.4, a], [37.8, b]]}
validation_on_load: [positive_definite_mandel, ti_condition: "1 - nu_p - 2 nu_pz^2 E_z/E_p > 0", reciprocity]
evidence: []
```

**Every reported number names its modulus basis.** Short-term vendor E (1,810-2,780 MPa) and the 1,000 MPa sustained
planning model differ by up to 2.8× in displacement.

### 3.4 Printability rules

**Adopt Frodo's catalogue schema in full:**
- `rules.yaml` with stable IDs;
- separately versioned `calibration/<printer>-<nozzle>-<filament>-<date>.yaml` bindings that go **STALE** when a bound
  profile hash changes;
- per-value evidence tiers U/S/V/L/H;
- a `compensation` owner;
- message templates;
- `NOT_CHECKED` as an explicit outcome.

My round-1 rule sketch is withdrawn. What the architecture adds on top:

1. **Check levels V/M/T/P** (Frodo D2) replace my design/geometry/toolpath. A result reports the highest level
   actually reached.
2. **One angle convention:** `slope_from_horizontal` in parameter names, with both conventions printed in reports.
3. **Any `repair` is followed by a re-check at the same level and emits a delta.** A repair can never convert FAIL to
   PASS without evidence.
4. **Rules that describe material strength reference the material card; they do not hold values.** STR-001 keeps
   only its safety factor and check levels (section 10, dispute 7).
5. **Each rule declares which grid tier can enforce it at level V** (table 4.2). "The optimiser respected
   printability" then means exactly the rules listed there.

### 3.5 Candidate and result records

```yaml
schema: fdmgen/candidate@0.2
id: <sha256-12 of inputs>
inputs: {problem: <sha>, process: <sha>, material: <sha>, catalog: <semver>, calibration: <id>, optimiser: <sha>,
         code: <git sha + dirty>, env_lock: <sha>}
orientation: {name: ..., R_print_design: [[...]], build_dir_design: [...], spin_readback_deg: ...}
design: {density_field: runs/<id>/rho.npz, grid_mm: [0.5, 0.5, 0.6], E_min: 1e-6}
artifacts: [{path: body.stl, sha256: ...}, {path: modifiers/*.stl}, {path: plate.3mf}, {path: plate_1.gcode}]
metrics:
  - {name: compliance, value: ..., fidelity: design_TI, scope: "0.5x0.5x0.6 grid, SIMP, solid body", modulus_basis: short_term}
  - {name: F_L_max, value: ..., fidelity: design_TI_posthoc, card_tier: T0, interval: [lo, hi]}
  - {name: max_displacement_mm, value: ..., fidelity: truth_slice, scope: "actual G-code, 0.2 mm, omission X%", modulus_basis: sustained_effective}
  - {name: spent_volume_mm3, value: ..., fidelity: slicer}
rule_results: [{rule: OVH-001, level_reached: T, verdict: PASS, calibration_status: PROVISIONAL}]
rung: TOOLPATH | FE_3D | ...              # verdict ladder; historical spool-rack status strings map verbatim
print_log: [P-00NN]                       # linked when printed
```

### 3.6 Receipts (one per stage execution)

Each receipt records:
`{stage, candidate_id, inputs:{name:sha}, outputs:{name:sha}, params, tool_versions, machine, started, seconds,
iterations, returncode, status, scope, cache_hit}`.

- Failed runs keep their receipts and fields.
- A cache hit requires identical input hashes **and** an identical stage-code hash.
- No absolute paths or usernames appear in published receipts; machines are logical names (`pc`, `second workstation`,
  `compute-box`).
- Iteration counts and seconds go in every solver receipt, so the parity suite doubles as a performance regression
  suite (Legolas).

---

## 4. Pipeline stages, module boundaries and resolution tiers

```
 S0 import ─► S1 orient+prescreen ─► S2 voxelise(print frame) ─► S3 optimise ─► S4 extract ─► S5 slice ─► S6 truth ─► S7 rank ─► S8 report
                     ▲                                                                                   │
                     └──────────────────── calibration feedback (emulator, prescreen ranking) ◄──────────┘
 Analysis mode (no optimiser): S0 ─► S1 ─► (fixed grid, rotated TI C) score ─► [S5 ─► S6 for top K'] ─► S7 ─► S8
```

### 4.1 Stage table

| Stage | Module | Machine | Known cost (measured unless marked) | Notes |
|---|---|---|---|---|
| S0 Import | `fdmgen.spec`, `fdmgen.adapters`, `fdmgen.geom.importer` | PC (Windows OCP via `run_native`) | seconds | Loads generated from pinned sources; lint asserts resultants and moments. |
| S1 Orient + prescreen | `fdmgen.process.orient`, `fdmgen.mech.prescreen` | PC / second workstation CPU | One isotropic solve (5 s at 1.6 mm, 25 s at 0.8 mm with Jacobi-CG, measured by Legolas; less with MG), then about 9 flops × cells × directions | **Candidates:**<br>- *analysis mode:* convex-hull poses ∪ axis poses ∪ user list;<br>- *optimisation:* Sauron's **inter-layer traction prescreen** on a Fibonacci set.<br><br>F_L(d) = F_L(−d) (it is quadratic in d), so the prescreen runs on a hemisphere. Each survivor then splits into ±d for printability. **Interface printability rules (HOLE-001, OVH-001 on keep-in faces, SUP-001) run per candidate here**, before any optimisation is spent (Frodo 8). |
| S2 Voxelise | `fdmgen.geom.voxel` | PC | host build 1.2 s / 6.8 s / 51 s at 0.18 / 1.4 / 11 M cells (Legolas numpy, measured) | Masked domain. Rotated poses can need 1.5-2× bbox cells (Legolas estimate). Force and moment conservation checked after rotation. |
| S3 Optimise | `fdmgen.opt` (`DensityTopOpt`, `ParametricEvo`), `fdmgen.fem.design` | **PC GPU** | Per tier, table 4.2 | **v1a (P2):**<br>- compliance + volume + AM filter on the **printed-solid TI** card;<br>- K solves per iteration (K = load cases);<br>- non-robust;<br>- F_L evaluated post hoc only.<br><br>**v1b (P3):** sub-cell shell model, then the F_L constraint (+ adjoint solves), then robust. |
| S4 Extract | `fdmgen.geom.extract`, `fdmgen.rules` (M) | PC | seconds-minutes | Iso-surface, then manifold3d union with exact keep-ins (with their **orientation-specific print variants**, e.g. teardrop), minus keep-outs. Then voxel-level repair with a delta, then M-level rules (overhang at 50°, every layer sampled). |
| S5 Slice | `fdmgen.slicer` (ported `package_part`, Orca driver, canonical `gcode`) | PC (Orca 2.4.2, Windows) | slice 2.67 s (G part) | Isolated `--datadir`, `--arrange 0 --orient 0`, pinned exe and profile hashes. PROC-001 and T-level rules. Spin read back. |
| S6 Truth | `fdmgen.verify` (ported `plastic_shape` + Sauron §5.3 mapper), `fdmgen.fem.truth` | **PC GPU** (second workstation if Q1 confirms a GPU) | parse 16 s, occupancy about 14 s, mesh about 30 s once vectorised, solve 10-60 s with MG (estimate), full export 30-250 s; about 2-6 min per finalist (Legolas) | Undo `filament_shrink`/compensation. Per-element bead angle, role class and bond fraction. Ke library indexed by class × 5° bin × bond bin. **No E_min** (refuses E_min > 0). All Gauss samples for finals; per-cell maxima in sweeps. Omission fraction reported. |
| S7 Rank | `fdmgen.rank` | any | trivial | Pareto **within one fidelity** only. Design-vs-truth gap logged (Sauron I19). |
| S8 Report | `fdmgen.report` | PC | — | Frodo §5.4 review view and §5.5 site template; `site.json` for the static site. |

### 4.2 Resolution tiers (R-numbers, to avoid colliding with stage numbers)

| Tier | Grid (dx = dy × dz) | Role | Rules enforceable at V level | Cost per orientation, one load case |
|---|---|---|---|---|
| R1 | 1.6 mm cubic, or fixed part grid | Analysis mode and prescreen solve only | none (scoring only) | < 1 min (measured basis) |
| R2 | **0.5 × 0.5 × 0.6 mm** (dz = 3 layers) | P2 design tier: solid printed body | OVH (5-point stencil: about 50° from horizontal along axes, steeper on diagonals), frozen keep-ins/keep-outs, volume | about 5-7 M bbox cells, 2-3 M masked. At 159 M cells/s, about 15-45 ms per matvec, about 2-10 s per MG solve, **about 10-50 min per orientation at 150 iterations** (estimate on Legolas's measured rate and assumed 20-40 MG iterations) |
| R3 | about 0.33 × 0.33 × 0.4 mm | Leaders only; P3 massing with sub-cell shell fraction | + WALL-001/GAP-001 length scale (2w ≈ 2.5 cells), + SHELL via sub-cell model | about 4× R2 (estimate) |
| R4 | 0.2 mm, adaptive | **Truth/verification only** (G-code material) | n/a: verification, not design | per finalist, as S6 |

The R2/R3 shapes are chosen so `atan(dx/dz)` from vertical is about 40°. **The voxel shape sets the overhang angle**
(Sauron's warning), and here that is deliberate. The 5-point stencil's azimuthal anisotropy must be measured (Sauron
I13) before results are shown. The 0.5 mm design voxel cannot represent 0.84 mm wall shells. That is why P2 designs
**solid printed bodies** (100% helper everywhere, which slices faithfully), and massing waits for P3.

### 4.3 Search policy

The pattern is inherited from EVOLUTION.md and generalised: prescreen many directions, run TO on the top K, slice
the top K' per orientation, and run truth on 1-3 overall. If truth reverses the design ranking, that reversal is
recorded and the emulator or prescreen is recalibrated. Cheap scores are never promoted to claims.

### 4.4 Execution

- Use an in-house DAG runner with content-addressed run folders, file-based idempotent jobs, and ssh + rsync
  dispatch. Remote results are accepted only if the input hashes match.
- Heavy runs go outside Claude background shells. Machines are saturated in parallel and yield on RAM pressure.
- **No process is ever killed by image name**; only the PIDs a job started.
- Environment extras: `[cad]` (Windows OCP), `[gpu]` (Warp, pinned 1.17.0 for parity; native Windows if parity passes,
  else WSL), `[cpu]`, `[dev]`.

---

## 5. Repo layout and integration

```
D:\Code\Models\fdm-gen\
  pyproject.toml  README.md  AGENTS.md  CLAUDE.md
  research\                 BRIEF, round-1 reports, reviews, finals
  schemas\                  generated JSON Schemas (problem, process, material, rule, calibration, candidate, receipt)
  catalog\                  rules.yaml, calibration\*.yaml, printers\, materials\, orca-profiles\<sha>\, coupons\
  problems\                 spool-bracket-g2\, bench-cantilever-3d\, bench-orientation-L\, (P3 part)\
  src\fdmgen\
    spec\ adapters\ geom\ process\ material\ mech\(prescreen, failure) fem\{design,truth,warp_hex,mg,contact,adaptive}\
    opt\{density,evo,filters}\ rules\ slicer\{orca,threemf,gcode}\ verify\ rank\ report\ pipeline\ emit.py
  tests\parity\  tests\fixtures\  tests\invariants\ (Sauron I1-I20)
  runs\                     gitignored content store on D:, never OneDrive
  scratch\<agent>\
```

**Integration rules:**
1. **Port, do not import.** Each ported file carries `ported from spool-wall-rack@14338e9:<path>` plus a parity test.
2. **Reference by hash.** A mismatch is a hard error.
3. **Hand off; do not write through.** fdm-gen emits candidate packages (aligned body/helper STEP/STL, model-only 3MF,
   slice evidence, receipts). A session in the receiving repo checkpoints them under that repo's rules.
4. **Adapters, not edits**, for existing builders (3.1).
5. **The catalogue lives in `fdm-gen/catalog/` until v1.0.** It then splits into its own repo, once outside
   contributors exist. A premature split doubles release work.
6. **Site:** one project entry plus a landing page fed by `site.json`, published by a session working in the site
   repo.
7. **Licence:** open question Q4. Frodo proposes CC-BY-4.0 for data and text, with permissive code. Warp is
   Apache-2.0, manifold3d Apache-2.0, pyamg MIT. TopOpt_in_PETSc (LGPL) is used only as an external oracle. The
   unlicensed DTU GPU codes are not copied.

---

## 6. Phased roadmap

Durations are guesses for one human plus agents, part-time.

### P0: foundations, parity and the solver gate (about 3-5 weeks)

Build:
- repo, schemas, receipts and runner;
- the canonical G-code parser;
- ports of `plastic_shape`, `package_part`, `gpu_hex`, contact and adaptive code, `interface_loads`, and the
  PROC-001 checker;
- the bracket adapter and `problem.yaml`;
- **structured geometric MG-PCG (new code)**;
- vectorised `mesh_from_cells`;
- `fdmgen lint` with plain-language errors.

Acceptance:
- **P0-A parser parity.** From the archived `g-recheck/2w-5layers/slice-evidence.zip`, credited E matches
  **70,979.8020219935 mm³**, the value in `g-recheck/2w-5layers/validated-shape/shape-verification.json` key
  `structurally_credited_extrusion_volume_mm3`, to ≤ 1e-9 relative. Sacrificial E is 6,940.469 mm³. Restored offset
  is `(0,2)` for P1S slices. Do not substitute `adaptive-validation/orca-replay.json` (70,979.852). It is a different
  slice and the values are "not interchangeable" (`MESHING-NOTES.md:52`).
- **P0-B arcs.** One part sliced with the D9 profile (`enable_arc_fitting = 1`) and with arcs off gives credited
  volume within 0.1% and occupancy within the 0.005 mm band. The library call raises on a footer mismatch.
- **P0-C FEM parity** on pinned Warp 1.17.0:
  - all spool-rack GPU fixtures pass at their own tolerances;
  - the operator agrees with scikit-fem to the repo's about 3e-16 relative;
  - the rotated-TI path with isotropic input agrees to ≤ 1e-12 relative;
  - the canonical-to-`gpu_hex` permutation test passes (pure shear in each plane returns the right G).
- **P0-D modifier spike.** Record which settings an Orca 2.4.2 modifier volume can override through 3MF metadata
  (`wall_loops`? top/bottom shells?). The result becomes a capability file and decides P3's massing outputs.
- **P0-E determinism.** S0-S2 twice gives identical hashes.
- **P0-F shrink fixture.** The same part sliced at `filament_shrink` 100% and 99.46% maps to the same design-frame
  occupancy after correction. The scaling centre is determined by the fixture, not assumed.
- **P0-G load parity.** Ported `interface_loads(117.72)` reproduces the pinned JSON to 1e-12. Lint asserts the
  resultant `[0,-117.72,0]`.
- **P0-H solver gate (exit criterion; Legolas B2/B3).** MG-PCG reaches ≤ 40 iterations to 1e-6 on a structured grid
  across E_min ∈ {1e-6, 1e-4, 1e-3} and TI ratios 0.7-1. Each run records the compliance gap to a zero-ersatz
  re-solve. ≤ 3 s per TO iteration at 0.8 mm. **No-go** means screening at R1 only, and the roadmap is re-planned.
- **P0-I** vectorised mesh build < 30 s at 4-8 M cells.

Publish: nothing.

### P1: orientation analysis of existing parts (about 2-3 weeks; useful to a collaborator's "project #1")

Scope: analysis mode on frozen designs (bracket G and E13, plus one D9 part):
- the traction prescreen;
- per-orientation interface and printability rules;
- the TI stiffness score;
- slice and truth for the top K'.

Output is Frodo's ranked-orientation table (Pareto, fidelity-marked) with a designer-decision field. Every
T0-card result is an interval over the card's bracket corners.

Acceptance:
- **P1-A** Sauron invariants I1-I13 pass.
- **P1-B mechanics known answer.**
  - A bar in uniaxial tension along design-x gives F_L = σ/Z_t when printed with x vertical, and F_L = 0 when printed
    flat (Sauron I12).
  - For the bracket, the existing flat-on-side orientation has the lowest max F_L of the swept set, and standing
    poses put the bending stress across layers.
  - These hold at every T0 bracket corner.
- **P1-C prescreen conservatism.** The prescreen ranking of the top 5 agrees with per-orientation full solves
  (anisotropic TI). Disagreements are published.
- **P1-D printable.** For the chosen orientation of each part, the M-level overhang check at 50° passes. The T level
  shows 0 support roads in `support: forbidden` regions, and PROC-001 passes.
- Start of the **coupon plate** (Frodo Q5 plus Sauron C2 Z-tension and C3 inter-layer shear; the printer is idle).

Publish: an "orientation report for existing parts" page, with limitations first.

### P2: topology optimisation MVP on the spool bracket, solid body (about 4-6 weeks)

Scope: v1a at R2, then leaders at R3.
- TI printed-solid card, SIMP, density filter, 5-point AM filter, volume, K = 2 load cases.
- Top K orientations from P1's prescreen, plus the three named poses (flat-on-side, standing on the wall plate,
  standing on the tip) as known-answer anchors.
- Bodies print fully dense. F_L is evaluated post hoc for ranking.
- Then S4-S8 end to end, with truth on the leader of each orientation.

Acceptance:
- **P2-A solver and optimiser parity** (Sauron 14):
  - (i) evaluate the reference code's final density with our solver: compliance within 1e-6;
  - (ii) same settings as the reference code: final compliance within 2% and volume within 0.1%;
  - (iii) rotate loads, domain and TI axis together by a grid symmetry: compliance unchanged to 1e-10.
- **P2-B orientation, honestly scaled.**
  - *Noise floor:* isotropic, no AM filter, three orientations, 3-5 repeats each.
  - *Plumbing test:* E_z/E_p = 0.5 and 0.7 must show a **monotone** compliance trend.
  - *Realistic run* at 0.85: report whether the effect exceeds the noise floor; no rank requirement.
  - *Ranking claim* uses F_L and printability, not compliance.
- **P2-C exact interfaces.** Every keep-in differs from its source (orientation-variant applied) by ≤ 1e-3 mm³
  symmetric difference. Keep-outs contain zero material.
- **P2-D printable.** M-level overhang at 50° passes. 0 support roads in forbidden regions. PROC-001 passes. Any
  repair has a delta report.
- **P2-E honesty table.** Leader vs E13, G (8 walls) and E+F on the same truth pipeline, **same pinned loads**, same
  card, **stated modulus basis**. Columns: spent volume, max displacement, raw peak, eroded fraction, and the
  design-vs-truth gap. Measuring the gap is the criterion, not its size.

Publish: the MVP page and catalogue v0.1 (all rules defined; V/M/T checkers for OVH, WALL, GAP, BRG, PROC; tiers as
found).

### P3: massing, inter-layer constraint, second part (about 5-8 weeks)

Scope:
- a sub-cell shell-fraction model using Sauron's `t(α)` with per-region `w`, calibrated against R4 truth and
  validated by resolved coating on 0.2 mm crops;
- body + modifier + per-region settings, as far as P0-D allows;
- the aggregated F_L constraint with adjoint costs budgeted;
- a second part where at least two orientations are competitive under isotropic assumptions (Q2).

Acceptance:
- **P3-A emulator band** (Sauron 15, provisional): at 0.2 mm, per class, the symmetric-difference volume between
  emulator and Orca credited material is ≤ 5% of class volume. Mean surface-normal shell thickness is within ±1 cell
  at 0/30/50/70/90°. The final band is set after the first measurement and published with its basis.
- **P3-B modifier round trip.** The intended massing equals the slicer output within the band.
- **P3-C orientation decision.** On the second part, isotropic and anisotropic runs choose different orientations or
  massings, and truth confirms the anisotropic choice across the card interval. If not, publish that.

Publish: the massing page, emulator validation, and catalogue v0.5 after the first calibration plate per material.

### P4: coupons, strength calibration, one physical test (about 4-8 weeks, printer-bound)

Scope: Sauron C1-C7 (C4 off-axis and C5 overhang-wall bond added); cards move to T1; one optimised part and one
control printed and loaded, with **pre-registered** predictions.

Acceptance: the measured stiffness of both parts falls inside the predicted band, and the failure location matches a
predicted critical region. Otherwise, publish the miss.

Publish: physical results, using spool-rack qualification language.

### P5: generalisation (ongoing)

- `fdmgen run`;
- documented STEP + YAML authoring;
- catalogue v1.0 when every binding value is tier U or slicer-defined (Frodo §6);
- two more parts;
- the `ParametricEvo` path.

Acceptance: a person who did not write the code takes a new part to a sliced 3MF and report using only the docs.

---

## 7. Top risks and early de-risking

| # | Risk | Likelihood / impact | De-risk by |
|---|---|---|---|
| R1 | No measured anisotropic data; strength ratios drive orientation | High / high | T0 intervals everywhere. Coupon plate starts in P1 (C2, C3 first). |
| R2 | Design model vs printed truth disagree (voxel omission 8.02% / 16.38% / 33.09% at 0.2 / 0.4 / 0.8 mm, `adaptive-validation/*geometry.json`) | High / high | Measure the gap in P2-E before investing in P3's emulator. Fidelity tags on every metric. |
| R3 | Solver convergence and scale | High / high | P0-H gate before any optimiser work. Truth on finalists only, with time budgets and preserved failures. |
| R4 | Slicer cannot express the intended massing | Medium / high | P0-D spike. Pinned Orca and profile hashes. A version bump is a re-baseline. |
| R5 | Frame, scale and compensation bugs (P1S offset, `PRINT_Z` vs `pose`, `filament_shrink`, arrange spin) | Medium / high | 3.0 frame table, single `Rotation`, P0-B/F fixtures, round-trip tests. |
| R6 | Optimiser approximations leak into published numbers | Medium / high | Separate `fem.design` / `fem.truth`; truth refuses E_min > 0. |
| R7 | Scope creep (stress-constrained robust TO, gradient orientation, multi-axis) | High / medium | v1a/v1b split; non-goals listed in section 2. |
| R8 | Retyped inputs (loads, nozzle temperatures) silently wrong | Medium / high | Generate from pinned sources; lint asserts resultants and moments. |
| R9 | Machine availability | Medium / medium | Everything through P2 fits this PC; compute-box optional, with a heads-up. |
| R10 | Overclaiming on the site | Medium / high | Verdict ladder in headlines; "establishes / does not establish" block; fidelity-separated Pareto plots. |
| R11 | 45° designs fail the user's measured Orca threshold | High (if ignored) / medium | Non-cubic voxel stencil (about 50°), M-check at 50°, T-check zero support. |

---

## 8. Architecture findings on existing code (house format, corrected)

### Gandalf — Opus

**Findings:**
1. **[severity: warning]** `spool-wall-rack/analysis/rev-g2/plastic_shape.py:81` — Parses only `G0/G1/G92`. The
   footer assert at `:380` guards `main()` only; `read_paths()` used as a library would accept arc-fitted G-code
   (the D9 profile enables arcs) with wrong positions. Fix: canonical parser with arc support and an internal footer
   assert.
2. **[severity: warning]** `plastic_shape.py:35,127` — The G-specific default transform and a process-policy assert
   live in the parser, and `filament_shrink` is not undone. Fix: explicit inputs; compensation read from effective
   settings.
3. **[severity: warning]** `5680-dock/desk-dock/D9-P5/build_d9.py:102-108` — Orientation is encoded twice. Fix: one
   rotation object.
4. **[severity: warning]** `gpu_hex.py:140,150` — One shared `Ke`. This is fine for the design role (rotated TI +
   per-cell scale). The truth role needs a class- and angle-indexed library.
5. **[severity: warning]** `gpu_hex.py:45-78` `mesh_from_cells` — A per-vertex Python loop, minutes at
   whole-part scale. Fix: vectorise.
6. **[severity: note]** `evo_screen.py:54-58` — Hard-coded G boundary nodes and hotspot. Reuse the policy, not the
   class.
7. **[severity: note]** `prepare_and_slice.py:92`, `package_part.py` build transform — Hard-coded paths and
   transforms. Fix: configured inputs.
8. **[severity: note]** `D9-P5/overhang-threshold-test/build.py:10` — The comment says "angle from vertical", but the
   geometry is slope from horizontal. Fix it in the catalogue's evidence record, not in the frozen repo.
9. **[severity: note]** Three G-code parsers — Consolidate now.

**Summary:** The foundations are sound and unusually well evidenced. The work is consolidation and honest staging;
the main hazards are design approximations leaking into verification, and retyped inputs.
**Verdict:** ISSUES FOUND (0 critical, 5 warning, 4 note)

---

## 9. Numbered decisions (final)

1. New repo `fdm-gen`, uv package `fdmgen`. Port with parity, never import, adapters for existing builders.
2. Two FEM roles. The design role uses a shared rotated-TI `Ke` and E_min. The truth role uses a class/angle/bond
   `Ke` library and refuses E_min.
3. The slicer generates toolpaths. Output is body + modifiers + per-region settings via ported `package_part`. Truth
   reads G-code and undoes slicer compensation.
4. Optimisation re-voxelises in the print frame per orientation. A fixed grid with rotated tensor is for analysis mode
   only.
5. Orientation: prescreen on a hemisphere (F_L is even in d), split survivors into ±d for printability, run TO on the
   top K. No gradient orientation in v1.
6. Resolution tiers R1-R4. The design voxel is 0.5 × 0.5 × 0.6 mm, chosen so the support stencil builds in the
   overhang margin. 0.2 mm is verification only.
7. Material: TI printed solid at design; bead-orthotropic at truth. Cards carry tier, per-value provenance,
   convention, PD check and modulus basis.
8. Catalogue: Frodo's schema, V/M/T/P levels, `slope_from_horizontal`. Strength values live in the material card.
9. Loads, restraints and process bindings are generated from pinned sources, never retyped.
10. Roadmap P0 (solver gate) → P1 orientation analysis → P2 solid-body TO MVP → P3 massing + second part → P4
    coupons and physical test → P5 generalisation.

---

## 10. Open disputes for the merge

| # | Dispute | Positions | My recommended resolution | Evidence |
|---|---|---|---|---|
| 1 | Fixed grid vs re-voxelised | Legolas D3 fixed grid + `Ke(n)`; Gandalf/Sauron/Frodo re-voxelise | **Mostly settled:** Legolas conceded in his review of my report. Re-voxelise for TO; fixed grid for analysis mode. Remaining: budget the 1.5-2× rotated-bbox growth. | Layer-wise AM filter, Z erosion and Z quantisation need layers on grid planes (Sauron §4.6, Frodo 12). Host rebuild is 1.2-51 s (measured). |
| 2 | Design-grid ladder | Sauron D4 0.2 mm; Legolas ≥ 0.8 mm (then 0.6 mm in his review); Gandalf round 1 "0.6 or coarser" | **R2 = 0.5 × 0.5 × 0.6 mm, R3 ≈ 0.33 × 0.33 × 0.4 for leaders, R4 = 0.2 mm truth only.** Massing via a sub-cell shell model at R2/R3 (Legolas), validated against resolved coating at 0.2 mm on crops (Sauron). Coating at 0.2 mm on the whole part is not affordable. | 0.2 mm ≈ 90 M bbox cells, does not fit 11.5 GB, 5-10 h per orientation (Legolas estimate). 2-wall shell = 1.4 cells at 0.6 mm (Sauron 5). Cell counts for R2 are estimates; P0 must measure the real bracket envelope. |
| 3 | Hemisphere vs full sphere | Legolas hemisphere (n ~ −n); Sauron full sphere | **Both, by stage.** The F_L prescreen is exactly even in d, so use a hemisphere. Printability (overhang, support, bed contact) is not, so each survivor is evaluated as ±d. | F_L uses σ_n = d·σ·d and τ = \|σd − σ_n d\|, both invariant under d → −d. |
| 4 | E_min in the design solve | Sauron 1e-6; Legolas ≥ 1e-3 | **Default 1e-6**, raised only if P0-H shows > 40 MG iterations. Record E_min in every receipt. Choose using the measured compliance gap to a zero-ersatz re-solve (Frodo's suggestion). Truth never uses it. | Legolas measured PyAMG 16 → 106 iterations at contrast 1e-3 on one contrived pattern; there is no data for optimised designs yet. |
| 5 | Sparse-infill palette vs 0%-infill house rule | Gandalf round 1 palette 0.15/0.4/1.0; Sauron zero credit; Frodo per-problem switch | **Per-problem `infill_credit.sparse`, default false; modifier densities default `[1.0]`.** Partial densities need an infill card (ASSUMED) and are verified at zero credit as a bound. | The house rule is spool-rack-only (`G2-BRIEF.md`). D9 plates run 40% gyroid (`prepare_and_slice.py`). `plastic_shape.py:127` asserts no sparse infill. |
| 6 | Overhang margin vs exactly 45° | Sauron default 45° stencil; Frodo design ≥ 50° | **Enforce about 50° at V via voxel shape** (dx/dz = 0.5/0.6, 5-point stencil). Check 50° at M and zero support at T. A margin-repair pass is the fallback. Must pass Sauron's I13 azimuth test. | `wedge-45deg`: 2,421 support segments; `wedge-55deg`: 0 (Orca, verified). `bore_td` already uses this 5° margin. |
| 7 | Z/XY strength: 0.5 placeholder vs vendor ratio | Frodo STR-001 `z_fraction` 0.5 (H); Sauron TDS Z_t/X_t 0.68-0.84 | **Strength lives in the material card.** The T0 card runs both corners: vendor ratio (annealed specimens, optimistic) and 0.5 (conservative fallback, H). Report an interval until C2/C3 coupons exist. | Bambu TDS (Sauron §2.2); two of three sheets used annealed specimens; user parts are as-printed. |
| 8 | Where F_L enters | Sauron D7 constraint in v1; Legolas post hoc (cost) | **P1-P2: prescreen + post hoc ranking; P3: aggregated constraint**, once adjoint cost is measured. | Robust × (K + 2) is about 12 solves per iteration at K = 2, versus K (Legolas). F_L is the orientation signal (Sauron), so it cannot wait until P4. |
| 9 | compute-box role | Gandalf round 1 S3 CPU optimiser; Legolas 0.2 mm verification and RAM | **Off the critical path through P2.** Later: RAM-heavy truth and parallel CPU batches, after a matrix-free CPU MG exists. | No CPU inner-loop solver exists. Assembled AMG is setup-dominated (85 s at 1.41 M cells, measured). Owner heads-up required. |
| 10 | Warp under WSL vs native Windows | Repo used WSL2; Legolas ran 1.18.0 natively | **Native Windows on the PC if P0-C parity passes on pinned 1.17.0.** Otherwise WSL. | The repo's WSL choice was on a different machine; the reason is unrecorded. |

---

## 11. Review disposition

| Reviewer # | Finding (short) | Disposition | Reason | Landed in |
|---|---|---|---|---|
| Sauron 1 | Seat loads wrong (equal vertical split) | **Accepted** | Verified `interface_loads` and `g-h0p2-interfaces.json`: rear [−31.29, −75.12, 0], front [+31.29, −42.60, 0] | 3.1, P0-G, R8 |
| Sauron 2 | Card: ν convention, PD check, TI class | **Accepted** | All three are necessary | 3.3 |
| Sauron 3 | TI at design; tangent bins only at truth; 36 bins | **Accepted** | Simplifies the design solver to a shared Ke | 0.3, 1.1 gpu_hex, 4.1 S6 |
| Sauron 4 | OVH rule mixes angle conventions; tier S | **Accepted** | Round-1 rule sketch withdrawn | 3.4, 1.1 overhang test |
| Sauron 5 | 0.6 mm cannot express massing | **Partly** | Agree on body = printed solid at coarse tiers. Massing via a sub-cell model at R2/R3, not 0.2 mm-only coating | 4.2, P2, P3, dispute 2 |
| Sauron 6 | XY spacing silently sets overhang angle | **Accepted** | Now set deliberately (0.5/0.6) with an azimuth test | 4.2, dispute 6 |
| Sauron 7 | P1-B ratio outside data; noise control; F_L in scope | **Accepted** | P1-B rewritten (mechanics known answer); P2-B monotone trend + noise floor | P1-B, P2-B |
| Sauron 8 | Modulus basis not stated | **Accepted** | Card carries short-term and sustained; every metric names its basis | 3.1, 3.3, 3.5, P2-E |
| Sauron 9 | Infill palette conflicts with house rule | **Accepted** | Default `[1.0]`; opt-in | 3.2, dispute 5 |
| Sauron 10 | "Validated to 0.005 mm" overstated | **Accepted** | Reworded | 1.2 |
| Sauron 11 | `filament_shrink` not undone | **Accepted** | Real hazard in the ASA profile | 1.1, 3.2, S6, P0-F |
| Sauron 12 | gcode and bead frames; arrange spin read back | **Accepted** | Frame table | 3.0, S5 |
| Sauron 13 | "Bitwise" unrealistic; permutation test | **Accepted** | 1e-12 relative plus permutation test | P0-C |
| Sauron 14 | P1-A split into solver/optimiser/covariance gates | **Accepted** | | P2-A |
| Sauron 15 | P2-A emulator band proposal | **Accepted (provisional)** | Final band set after the first measurement | P3-A |
| Sauron 16 | Hull poses for analysis, prescreen sphere for TO; full sphere | **Partly** | Adopted the split. Hemisphere is exact for F_L, ±d split for printability | S1, dispute 3 |
| Sauron 17 | Q5 answered (truth accuracy at 0.2 mm) | **Accepted** | Q5 closed; omission bound reported | S6, 10 |
| Legolas 1 | Re-voxelise accepted; budget rotated bbox | **Accepted** | | S2, dispute 1 |
| Legolas 2 | Design grid unstated; fix 0.6 mm | **Partly** | Stated: 0.5 × 0.5 × 0.6 rather than 0.6 cubic, to build in the overhang margin | 4.2, dispute 2 |
| Legolas 3 | MG unpriced; new code not port; P0 gate | **Accepted** | | 1.1 gpu_multigrid, P0-H |
| Legolas 4 | Solves per iteration; P1 compliance-only non-robust | **Accepted** | v1a/v1b split; F_L post hoc until P3 | S3, P2, dispute 8 |
| Legolas 5 | Truth placement rests on Q1 | **Accepted** | PC GPU default | 1.3, S6 |
| Legolas 6 | compute-box has no CPU solver | **Accepted** | Off the critical path | 1.3, dispute 9 |
| Legolas 7 | Class-indexed Ke library, per-cell C only for stress | **Accepted** | | 1.1, S6 |
| Legolas 8 | Stage timings; `mesh_from_cells` rewrite | **Accepted** | | 4.1, 1.1, P0-I |
| Legolas 9 | Bitwise unrealistic | **Accepted** | Same as Sauron 13 | P0-C |
| Legolas 10 | Noise floor, repeat runs | **Accepted** | | P2-B |
| Legolas 11 | Finalist throughput about 2 min before FE | **Accepted (noted)** | | S5/S6 costs |
| Legolas 12 | Warp native Windows | **Partly** | Conditional on parity | 4.4, dispute 10 |
| Frodo 1 | Bracket loads wrong; generate from JSON + lint | **Accepted** | Same as Sauron 1 | 3.1, P0-G |
| Frodo 2 | Both fixings + restraint model | **Accepted** | Verified the model string | 3.1 |
| Frodo 3 | P1-D fails at exactly 45°; margin needed | **Accepted** | Verified the wedge results | 4.2, P1-D, P2-D, dispute 6, R11 |
| Frodo 4 | Angle conventions mixed | **Accepted** | | 3.0, 3.4 |
| Frodo 5 | Rule schema lacks tiers, STALE, compensation, NOT_CHECKED | **Accepted** | Adopt Frodo's schema | 3.4 |
| Frodo 6 | Support policy per region | **Accepted** | | 3.1 |
| Frodo 7 | Infill palette per-problem, default zero credit | **Accepted** | | 3.1, 3.2, dispute 5 |
| Frodo 8 | Interfaces need orientation-dependent print variants; S1 prefilter | **Accepted** | | 1.1 `bore_td`, 3.1, S1, S4, P2-C |
| Frodo 9 | Arc fitting is real; library path unguarded | **Accepted** | Verified `process.json:150` | 1.1, P0-B, 8.1 |
| Frodo 10 | Pin the exact P0-A file and key | **Accepted** | Two values differ by 7e-7 relative | P0-A |
| Frodo 11 | P1-B ratio unsupported | **Accepted** | Same as Sauron 7 | P1-B, P2-B |
| Frodo 12 | Fixed grid = analysis only | **Accepted** | | dispute 1, 4 |
| Frodo 13 | Table of rules enforced per grid tier | **Accepted** | | 4.2 |
| Frodo 14 | Full verdict ladder; print-log link | **Accepted** | | 3.1, 3.5 |
| Frodo 15 | `fdmgen lint` with plain-language errors early | **Accepted** | Moved into P0 | P0 |
| Frodo 16 | `nozzle_C` hand-typed; generate from profile | **Accepted** | | 3.3, R8 |
| Self (round 2) | Arc guard exists at `:380`; `selfsupport` 4.5 mm reach; `package_part.py` missed; P1-B/material superseded by Sauron | **Applied** | | 1.1, 8, P1-B, 3.3 |

---

## 12. Open questions (remaining)

- **Q1** Which machine has the RTX 3080 Ti, and does second workstation have a CUDA GPU?
- **Q2** P3 part: a D9 arm or clamp, the Dell 5560 arm, or a part from a collaborator?
- **Q3** Does an Orca 2.4.2 modifier override `wall_loops` and skins via 3MF (P0-D)?
- **Q4** Licence (Frodo: CC-BY-4.0 for data and text, permissive code).
- **Q6** Is creep at 85°F in scope for P4, beyond the sustained-effective modulus?
- **Q7** Is a universal testing machine available (Sauron)? This decides coupon feasibility in P1/P4.
- **Q8** Which filament grades exactly? One card per grade per profile.
- **Q9** The bracket design envelope (`envelope.step`) does not exist yet. Who defines its limits beyond the
  interface contract?

## Sources

Round-1 sources are retained (section 2 links). Additional sources relied on here: the Bambu TDS and literature as
cited in `sauron.md` §2.2 and §8; Legolas's measurements in `scratch\legolas\`; Frodo's Orca wiki citations
(`support_threshold_angle`, `filament_shrink`, wall generator) in `frodo.md` §8.
