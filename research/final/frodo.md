# Frodo (final): designer workflow and the FDM printability constraint catalog

Round 3 integrated report for `fdm-gen`. It replaces `frodo.md` as the working version. `frodo.md` stays untouched as
the round-1 record. Reviews folded in: `reviews/gandalf-on-frodo.md`, `reviews/sauron-on-frodo.md` and
`reviews/legolas-on-frodo.md`. Section 10 has the disposition of every finding.

Angle: the person who uses this every day. It answers two questions:
- Can printability rules be written down so a machine can check them and a human can trust the verdict?
- What does the loop look like from a CAD part to a printed part and a published write-up?

Scope: Bambu Lab P1S, 0.4 mm nozzle, PETG and ASA, OrcaSlicer 2.4.2, planar layers. Work was read-only on all repos.
Nothing was printed, sliced or run remotely for this report. Every number carries an evidence tag (section 2.4).

---

## 0. Summary and decisions

The collaborator is mostly right. Guidance exists, but none of it is a versioned, machine-checkable rule set bound to a
calibrated printer:
- Generic standards. [ISO/ASTM 52910](https://www.iso.org/standard/67289.html) explicitly gives no process- or
  material-specific data.
- Vendor rule-of-thumb tables, e.g. [Hubs](https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/)
  and the Bambu TDS "max overhang ~70°, max bridge ~30/40 mm".
- One-off empirical studies, e.g. [Adam & Zimmer 2014](https://ris.uni-paderborn.de/record/22384).
- Slicer settings, which describe the slicer's behaviour, not the printer's capability.

The user's repos already encode about 15 rules as working code and about 10 more as prose (section 1).

| # | Decision |
|---|---|
| D1 | The catalog has three parts: **rules** (`catalog/rules/*.yaml`, stable IDs), **calibration bindings** (`catalog/calibration/*.yaml`, values plus evidence, bound to profile hashes, going STALE when a hash changes) and **checkers**. Material strengths and stiffnesses are **not** in the catalog. Rules that need them (STR-001) reference the active material card (Sauron's schema). |
| D2 | Every rule declares its check levels: **V** (voxel/density, inside the optimiser), **M** (mesh/B-rep), **T** (actual Orca toolpaths), **P** (physical). Results report the **highest level actually reached**. **M and T are authoritative over V.** A `repair` must be followed by a re-check at the same level and must emit a geometry delta. |
| D3 | **One angle convention**: α = surface slope from the horizontal bed plane (0 = ceiling, 90 = vertical wall), matching Orca's `support_threshold_angle` and Sauron's α_s. Reports also print the from-vertical value in brackets. Every angle in every rule uses the symbol α. |
| D4 | **Compensation ownership is explicit**, and the T-level mapper consumes it. `filament_shrink`, `xy_hole_compensation` and `elefant_foot_compensation` are owned by either geometry or slicer per interface. G-code mapped back to the design frame must undo Orca's shrink scaling (section 2.1, trap T18). |
| D5 | Reuse is split by path. **Builder path** (CadQuery parts, a collaborator's "simulate parts I've already designed"): reuse `selfsupport()` (a near-bed fixer only), `bore_td()`, `dress()`, `PROTECT`/`PRINT_Z`, the audits. **TO path** (iso-surface output): overhang is the AM filter at V plus mesh/voxel checks at M, and repair is voxel-level. B-rep operators are not applied to optimiser meshes. |
| D6 | **Three authoring routes** for `problem.yaml`: (a) new builders call `fdmgen.emit_problem()`; (b) existing frozen builders are read by **adapters inside fdm-gen** that consume their outputs (`manifest.json`, exported STEPs, `PROTECT` solids exported once) and never edit them; (c) external users such as a collaborator write `problem.yaml` + STEP by hand, checked by `fdmgen lint`. |
| D7 | One shared vocabulary: **U/S/V/L/H** per value (provenance), Sauron's **T0/T1/T2** per material card, and the **verdict ladder** per result (section 2.5), extended so that existing spool-rack status strings map onto it verbatim. |
| D8 | **Day-one in-optimiser rules**: OVH-001 (AM filter at the grid-limited 45°), VOID-001 (the same filter applied to the printed-material field), WALL-001/GAP-001 (density filter + projection at a 2w radius, not the full robust triple), plus frozen interfaces and keep-outs. STR-001 starts as a **post-check and orientation prescreen**. It enters the optimiser only in the strength stage, as an **aggregated constraint** (p-norm, qp-relaxed), never as a unitless penalty. |
| D9 | Catalog releases are **phased**: v0.1 at roadmap P1, v0.5 at P2 after the first calibration plate per material, v1.0 when no binding value is tier H (section 6). |

---

## 1. What the user's repos already encode

All paths are under `D:\Code\Models\`. Corrections from round 2 are folded in.

| Rule (ID) | Where it lives | What it does | Gap / caveat |
|---|---|---|---|
| Near-bed self-support (OVH) | `5680-dock\desk-dock\D9-P5\build_d9.py:41-83` `selfsupport()` | Fuses straight-down prisms under faces whose normal is within 45° of print-down (`dot > 0.7071`, sampled at the **face centre**). Only for faces **0.4–4.5 mm above the bed** (`maxdrop=4.5`); respects a keep-out | A near-bed fixer, not a general overhang repair. Added volume is **not reported** (unlike `dress()`). Curved faces are judged at one point |
| Teardrop horizontal bores (OVH/HOLE) | `build_d9.py:85` `bore_td()` | Tangent crest at 40° from vertical (α = 50°), "clear of the slicer's 45° threshold" | The 5° margin is hand-chosen |
| Gusset slope (OVH) | `build_d9.py:97` `GUSSET_SLOPE=1.5` (34° from vertical, α = 56°) | Support-reducing gussets | Cites the threshold test |
| Slicer overhang threshold (OVH) | `D9-P5\overhang-threshold-test\` | Four wedges sliced with `support_threshold_angle = 45`. Underside slopes α = 30/39/45° got support (2,421 segments at 45°); α = 55° got none | **Slice-only (tier S).** The file names are correct (from horizontal). The docstring "angle from vertical" in `build.py` is the error (trap T1) |
| Protected zones (PROT) | `build_d9.py` `PROTECT[name]` (lines 348, 413, 519, …) | Keep-out solids: bores, key slots, airways, laptop band | Used by `dress()` and `selfsupport()`, not by support-placement checks |
| Print orientation (ORI) | `build_d9.py:102-108` `pose()` + `PRINT_Z`; `D9-P5\DESIGN.md:258-269` | Named build vectors; orientation tradeoffs argued in prose (bed contact 65 → 718 mm²; vertical pose rejected at 89 mm² and for "load across weaker layers") | Hand-picked; `pose()` and `PRINT_Z` encode the same thing twice |
| Edge dressing (WARP/EF) | `D9-P5\dress.py` | Fillets print-Z-parallel edges (inside 3 mm, outside 1.5 mm); never bed edges; skips PROTECT; reports every operation | Acts as a warp mitigation (rounded footprint corners) without being named as one |
| Build volume, exclusion, placement (BED) | `D9-P5\profiles\machine.json` (256², h 250, exclude 18×28, `extruder_offset 0x2`); `prepare_and_slice.py` (10–246 mm, 12 mm spacing) | Placement guard | Offset handled in `plastic_shape` |
| Arc fitting state (PROC) | `D9-P5\profiles\process.json`: `enable_arc_fitting = "1"`; `closed-wall-e13\slice_audit.py` forces `"0"` | The D9 profile emits G2/G3 | `plastic_shape.read_paths` ignores G2/G3. Only its `main()` footer check (< 0.1%) would catch the dropped extrusion |
| Support/bridge road counts (OVH/BRG/SUP) | `5680-dock\tools\coupon-pipeline\architect\verify_mixed_plate.py` (parses G2/G3) | Per-object Support / Bridge / Internal Bridge roads; "strict" objects must have zero | `verify_plates.py` marks **every** object non-strict (T13) |
| Geometric support proof (OVH/BED) | `coupon-pipeline\architect\audit_print_mesh_support.py` | Bed contact area, non-bed downward area, max underside angle, with a `scope` disclaimer | Good model for honest receipts |
| Toolpath hole sizes (HOLE) | `coupon-pipeline\architect\check_native_holes.py` | Sections sliced meshes for small rings | Prototype |
| Effective settings + modifier roles (PROC/MOD) | `spool-wall-rack\analysis\rev-g2\gpu_demo_slice.py:120-145` | Checks 7 effective keys and that `modifier_part` roles survived | Generalise to every rule key (PROC-001) |
| Modifier 3MF writer (MOD) | `spool-wall-rack\analysis\rev-g2\package_part.py` | One `normal_part` + N `modifier_part` | Sets `wall_loops` **per object** and only `sparse_infill_density` per modifier, so per-region walls are unverified (Gandalf P0-D). Hard-codes a bracket build transform; port with the transform as an input |
| Toolpath → layer polygons, bond graph (WALL/MOD/STR) | `plastic_shape.py`, `audit_ef_bonds.py`, `audit_ef_connections.py` | Roads with width/height/role; bridges get zero credit; layer-to-layer bond connectivity | T-level substrate. Must also undo `filament_shrink` (D4) |
| ≥ 2 walls, 0% base infill, 100% helpers (WALL/MOD) | `spool-wall-rack\G2-BRIEF.md` | Process rules in prose | **Per-problem** (spool-rack G2), not tool-wide: D9 plates use 5 walls + 40% gyroid |
| Stroke = gap = 2w; Arachne bead bands (WALL/GAP) | `double-bead\README.md:24-36`, `docs\SPEC.md` §2, §4, §6 | Width rules in line widths; `beads(T)`; pinch fill `PINCH_R = 0.98w` | Generalises to any layer section |
| Fit allowances (FIT) | `5680-dock\TOLERANCES.md`; `build_d9.py:118-123`; `docs\prints\print-log.json` | Dovetail 0.30/side; ASA: Ø7.9 pin in Ø8.4 teardrop bore fits, Ø8.2 won't enter; PETG: 8.2 AC octagon in Ø8.8 rattles | Physical (tier U) but keyed to no orientation or profile |
| Load in the layer plane (STR) | `spool-wall-rack\README.md:189`; `5680-dock\ENGINEERING_REPORT.md:93`; `D9-P5\DESIGN.md:21`; `D8\FAN_FIT.md:33` | "Main bending load stays in the layer plane"; flexures flex in-layer; pins lie on a chord flat; threads axis-vertical | Never quantified |
| Generic mesh checker (OVH/WALL/BRG/FEAT/BED) | `novel-cad-skill\scripts\check_printability.py` | Flat bottom, overhang, wall, bridge span, min feature | Uncited defaults (bridge 20 mm in code vs 15 mm PETG in `SKILL.md:334`); `Z_SAMPLE_COUNT = 10` (T5); assumes +Z build |
| Print feedback log (CAL) | `5680-dock\tools\print-log.py`, `docs\prints\print-log.json` | Each print tied to STL hash, profiles and commit, with lessons | The collection route for calibration receipts |

---

## 2. Conventions every rule depends on

### 2.1 Frames (one table for all reports)

Transforms are named `R_<to>_<from>` (Sauron D1), with det = +1 and orthonormality asserted.

| Frame | Symbol | Definition | Notes |
|---|---|---|---|
| design | D | CAD frame of the part; loads, BCs, keep-ins, keep-outs | Builder frame |
| installed | I | Optional service frame (spool-rack `model_to_installed`: X out of wall, Y up, Z along rods) | INTERFACE-CONTRACT coordinates live here |
| print | P | +Z = build direction; layers are planes z = k·h; origin at the bed-contact minimum | Derived from one `Rotation` per orientation candidate. Never authored twice (`pose()` vs `PRINT_Z`) |
| plate | B | Orca bed coordinates after placement **including any arrange spin and the `filament_shrink` XY scale** | **Read back from the sliced 3MF**, never assumed from `PRINT_Z` |
| gcode | G | Plate minus the P1S `extruder_offset (0, 2)` | What `plastic_shape` actually inverts: `model = (gcode + offset − xf[3]) @ xf[:3].T`. It must then also undo the shrink scale (D4). The centre of scaling is to be confirmed by a golden test |
| bead | M | Per segment: `[t, e_z × t, e_z]` | Used by STR-001 and Sauron's per-element orthotropic card |

### 2.2 Angle convention (D3)
- α = slope from horizontal (the angle between the outward normal and −Z_P). Orca's threshold uses the same sense:
  "support for overhangs whose slope angle is below the threshold"
  ([Orca support wiki](https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support)).
- Reports print `α = 50° (40° from vertical)`.
- Sauron's leaning-wall overlap in this convention: `f(α) = 1 − h / (w·tan α)`.

### 2.3 Units and widths
- mm, deg, s, mm/s, N, MPa. Every parameter has `unit:`. A unitless number is a lint error. Rules may use `w` and `h`,
  resolved from **one** source: the effective Orca config of the bound profile.
- **Line widths** come per role from the profile (D9: outer 0.42, inner 0.45, first layer 0.5).
- **Wall placement** uses Orca's **flow spacing** `s = w − h(1 − π/4)`: 0.377 mm for 0.42 and 0.407 mm for 0.45 at
  h = 0.2.
- The two-wall shell is therefore about `w_o/2 + (s_o + s_i)/2 + s_i/2 ≈ 0.21 + 0.392 + 0.204 ≈ 0.81 mm`, not
  2 × 0.45 = 0.90 (Sauron review #4). This is approximate; the T-level road measurement is authoritative.

### 2.4 Evidence tags (per value)

| Tag | Meaning | Example |
|---|---|---|
| **U** | User's own logged print outcome | Ø7.9 pin in Ø8.4 ASA bore fits (P-0012) |
| **S** | What the user's slicer profile does (slice, not print) | Orca supports α = 45°, not α = 55° |
| **V** | Vendor or slicer documentation | Bambu ASA TDS "max bridging ~40 mm" |
| **L** | Literature or general DfAM guidance | Bridges ≤ 10 mm (Hubs) |
| **H** | Heuristic placeholder; needs a coupon | Pillar height/width ≤ 8 |

Material **cards** carry Sauron's card tier (T0 TDS + assumptions, T1 own coupons, T2 demonstrator-validated). A rule
whose binding value is H, or which uses a T0 card, shows **PROVISIONAL** next to its verdict. The lint fails on any
untagged value.

### 2.5 Verdict ladder (per result)

| Rung | Meaning | Existing spool-rack strings that map here |
|---|---|---|
| GEOMETRY | M-level checks run | `zero_outward_growth_mesh_check`, `source-cad-verification` |
| TOOLPATH | Actual Orca slice, PROC-001 passed, T checks run | `PASS_ACTUAL_SLICE_PROCESS_AND_BED_CHECKS`, `PASS_NEW_P1S_<mat>_SLICE` |
| SCREEN | Reduced/cheap mechanics | `CONTACT_SCREEN_AT_STATED_TOLERANCE_ERODED_MATERIAL_ONLY` |
| FE_3D | Zero-ersatz 3D truth solve converged | (failures such as `FAIL_LINEAR_CONVERGENCE` are recorded; the rung is not reached) |
| COUPON | Relevant coupons printed and measured | print-log entries |
| PRINTED | Part printed and fit-checked | print-log `printed` + lessons |
| QUALIFIED | Physical load/qualification per the problem's plan | `PHYSICAL_PRINT_UNQUALIFIED` means not yet |

A check that could not run is **NOT_CHECKED**, never PASS. Unknown fit combinations are **NOT_CALIBRATED**.

### 2.6 Check levels, enforcement and what a grid can enforce
- Enforcement modes:
  - `hard_filter`: built into the design parameterisation;
  - `constraint`: aggregated, with units;
  - `repair`: automatic change, then a mandatory re-check and a delta report;
  - `post_check`;
  - `advisory`.
- **V can only enforce what the grid stencil can represent.** A one-cell Langelaar stencil on voxels with
  dx = dz gives α = 45°, exactly so only along grid axes. A 3×3 support stencil admits ~35° along diagonals; a
  5-point cross is stricter on diagonals. Larger α needs non-cubic cells with **dz = h kept** and
  dx = dz/tan α (α = 50° → dx ≈ 0.84·dz, ~1.42× more cells), or interpolated stencils.
- Changing h is not allowed: h is bound to the material card and calibration (Sauron #5).
- So **OVH-001 is enforced at 45° at V and at 50° at M/T** (section 3.2).

---

## 3. The constraint catalog

### 3.1 Master table

Defaults: P1S, 0.4 mm nozzle, h = 0.2, D9 profile widths, Textured PEI, profiles in `D9-P5\profiles\` (Generic PETG
starter; PolyLite ASA calibrated). "Day-1 opt" is the D8 set.

| ID | Rule | Protects against | Levels | Enforcement (day 1) | PETG default | ASA default | Tag |
|---|---|---|---|---|---|---|---|
| BED-001 | Build volume, exclusion, margins, spin feasibility | Off-bed or colliding placement | M,T | post_check per orientation **and spin** | 256×256×250; exclude 0–18 × 0–28; margin ≥ 10; spacing ≥ 12 | same | S |
| OVH-001 | Self-supporting slope | Droop, curl, support scars | V,M,T | V hard_filter at 45° (grid); M/T post_check at 50°; repair + re-check | α ≥ 50° (M/T); 45° (V) | same | S (threshold), H (quality) |
| OVH-002 | Minimum leaning-wall overlap | Same, generalised to h; feeds bond fraction to STR-001 | M | post_check | `f = 1 − h/(w tan α) ≥ f_min`; f_min = 0.6 ⇔ α = 50° at h 0.2, w 0.42 | same until coupon | H, derived |
| BRG-001 | Bridge span | Sag, failed anchors | M,T | post_check | external ≤ 10, internal (hidden) ≤ 18 mm | same | L / precedent; vendor 30/40 recorded as V (dispute §7.2) |
| BRG-002 | Bridge anchoring and credit | Bridges into air; overstated strength | T | post_check | both ends on prior-layer material; zero structural/bond credit | same | U-policy (G2) |
| WALL-001 | Minimum solid width (XY) | Dropped or partial features | V,M,T | V filter+projection at 2w radius; M/T binding | ≥ 2w = 0.84 mm | same | U (G2, Fillaprint) |
| WALL-002 | Bead-count band edge | Stiffness jumps from print variation | M,T | post_check | no thickness within ±0.1w of an Arachne band edge (1.70, 2.85, 3.70, 4.85 w at mb = 0.85) when `wall_generator = arachne` | same | U (Fillaprint algebra) |
| WALL-003 | Perimeter count | Thin load-bearing shell | T | post_check (process) | ≥ 2 walls; structural ≥ 4 | same | U-policy |
| GAP-001 | Minimum clear gap (XY) | Fused gaps | V,M,T | as WALL-001 on the void phase | ≥ 2w = 0.84 mm | same | U (Fillaprint R3/R9) |
| GAP-002 | Print-in-place / sliding clearance | Fused moving parts | M,P | post_check | ≥ 0.30 mm per side XY; Z ≥ h + 0.1 | same | precedent (Rev F), H |
| ZQ-001 | Z quantisation | Rounded fit heights | M | snap variables; post_check | fit-critical Z on multiples of h | same | L |
| HOLE-001 | Horizontal-axis bore roof (incl. frozen interfaces) | Sagging crowns, support in bores | M,T | repair (teardrop variant per orientation) | tangent crest α ≥ 50° | same | U (D9 prints) |
| HOLE-002 | Fit classes | Rattle / no entry | M,T,P | frozen interface; lookup | table keyed by axis-vs-Z, material, profile hash (3.2) | same | U for ASA Ø8; else NOT_CALIBRATED |
| EF-001 | Elephant foot | Oversize bed edges | M,T | repair or process | slicer 0.15 mm **or** 0.3–0.5 mm 45° chamfer on fit-critical bed edges, never both | same | S, V |
| BED-002 | Bed contact and stability | Detachment, toppling | M | orientation-level post_check | contact ≥ 100 mm² and ≥ 5% of footprint; CoM inside contact hull with 3 mm margin; height / min base width ≤ 4 without brim | same | H (D9 precedent) |
| WARP-001 | Warp risk | Lifted corners, bowed parts | M | orientation-level (first layers), not per iteration | footprint L ≤ 200 mm without measures | L > 120 mm ⇒ brim ≥ 5 mm, footprint corners r ≥ 3 mm; no bed-lying plate t < 2 mm with L > 100 mm | L (Wang 2007), H values |
| COOL-001 | Minimum layer time | Heat sag, blobs | V (proxy), T | V penalty optional; T post_check | flag layers below 12 s that hit the 20 mm/s floor | below 3 s | S |
| VOID-001 | Enclosed voids allowed; roofs self-support | Collapsed internal ceilings | V,M | **AM filter on the printed-material field** (shells + helpers) | roofs obey OVH/BRG | same | L, U |
| VOID-002 | No trapped support | Unremovable support | V (cavity detection), T | post_check | 0 support roads in any enclosed cavity | same | logic |
| SUP-001 | No support on interface faces | Debris on fits (P-0004) | T | post_check | 0 support/interface roads within 0.6 mm of `role: interface` regions | same | U |
| SUP-002 | Support removal access | Unremovable support | M (estimated), T | post_check | each support island reaches exterior through an opening ≥ 6 mm, depth ≤ 3 × opening | same | H |
| SUP-003 | Support interface gap | Fused supported faces | T (settings) | process | top z gap 0.15–0.2; PETG prefers ≥ 0.2 | 0.15–0.2 | S, V |
| SEAM-001 | Seam placement | Zits on fits | T | post_check | no outer-wall loop start within 1 mm of interface faces | same | H |
| SKIN-001 | Top skin over sparse/void | Pillowing | T | process | ≥ max(5 layers, 1.0 mm); 0% infill needs internal-bridge anchors within BRG-001 | same | S |
| SHELL-001 | Orientation-dependent shell thickness | Thin skin on mid slopes | V (coating), M advisory, T binding | V: Sauron's directional coating in the strength stage; T post_check | T: ≥ 2 solid beads normal to every surface after `ensure_vertical_shell_thickness`; M reports `t(α)` band | same | derived; threshold H |
| PILL-001 | Thin pillars / fins | Wobble, knock, layer-time sag | V,M | penalty optional; post_check | min width ≥ 3w; height / width ≤ 8 | same | H |
| MOD-001 | Helper (modifier) geometry | Slivers, unbonded helpers, lost roles | M,T | hard (massing); post_check | boundaries ≥ 2w apart or overlapping ≥ 2w; bonded to credited material; roles survive | same | U (G2 audits), H |
| MOD-002 | Small sparse areas become solid | Intent ≠ result | T | advisory | `minimum_sparse_infill_area` 15 mm² | same | S |
| STR-001 | Inter-layer failure index | Layer separation | V (aggregated, strength stage), T-mapped re-analysis | **post-check + orientation prescreen** day 1 | `F_L = sqrt((<σ_n>⁺/Z_t,eff)² + (τ/S_il,eff)²) ≤ 1/SF` with Z_t, S_il **from the active material card** | same | card tier (T0 today) |
| STR-002 | Flexures flex in the layer plane | Snapped leaves | M | post_check | flexure bending axis ∥ Z_P | same | U (practice) |
| STR-003 | Threads axis-vertical; pins axis in-layer | Weak threads, split pins | M | orientation-level | thread axis ∥ Z_P; pin axis ⟂ Z_P on a chord flat | same | U (D9) |
| SURF-001 | Stair-stepping on functional faces | Rough fits, leaks | M | post_check | cusp `c = h·cos α` ≤ allowable on faces tagged functional; `c = 0` for horizontal faces on a layer boundary | same | L |
| TXT-001 | Text and marks | Illegible marks | M,T | post_check | stroke, gap ≥ 2w; capital height ≥ 14w | same | U (Fillaprint) |
| PROC-001 | Effective settings match declared process **and material-card binding** | Settings that don't do what they claim | T | post_check (blocking) | see key list in 3.2 | same | U (spool-rack check) |
| CAL-001 | Values bound to calibration | Generic values passed off as calibrated | – | lint | every binding value tagged + receipt | same | policy |

### 3.2 Rule cards (where the details matter)

**OVH-001 / OVH-002: overhang and leaning-wall overlap**
- *Evidence:* with `support_threshold_angle = 45`, Orca supported the exactly-45° wedge (2,421 segments) and left 55°
  alone (tier S). That is what Orca **will generate**, not what the P1S **prints well**.
- *Margin (resolved with Gandalf and Legolas):*
  - V-level AM filter at 45° (one-cell stencil on dz = h = dx), which is what the grid can enforce.
  - M and T checks bind at **α ≥ 50°**, the same 5° margin `bore_td()` uses.
  - Surfaces between 45° and 50° that survive extraction go to a **voxel-level repair** (add material below to reach
    50°), then a mandatory re-check and a delta report (volume added, bbox, cause).
  - If repair deltas are routinely large (threshold to be set from the first runs), upgrade V to non-cubic cells
    (dx ≈ 0.84·dz, dz = h kept).
- *OVH-002:* expressed as Sauron's overlap fraction `f = 1 − h/(w·tan α)` (my round-1 `k_step` = 1 − f).
  - f_min = 0.6 corresponds to α = 50° at h = 0.2 and w = 0.42.
  - The same f is the bond-fraction hypothesis `Z_t,eff = g(f)·Z_t` in STR-001 (Sauron §2.7), so one printed
    overhang ladder (as tension specimens, Sauron's C5) calibrates both printability and strength.
  - At h = 0.12 the 50° limit could relax and at 0.28 it tightens. h is chosen per profile, not by the optimiser.
- *Checks:*
  - **V:** AM filter on the printed-material field, bed treated as support
    ([Langelaar 2017](https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf);
    [Gaynor & Guest 2016](https://link.springer.com/article/10.1007/s00158-016-1551-x)).
  - **M:** area-weighted downward faces with α < 50°, excluding bed and `support_allowed` regions, sampled per
    triangle, not per face centre. Islands are reported with print-frame bboxes.
  - **T:** Support / Support interface roads per object and overhang-wall roads.
- *Required test (from Sauron):* the azimuthal acceptance test. Rotate an inverted cone about Z, record the accepted
  α at V level versus azimuth, and confirm Orca adds zero support roads to the repaired output at every azimuth.

**BRG-001 / BRG-002: bridges**
- *Parameters:* `max_span_external_mm`, `max_span_internal_mm`, `anchor_min` = 2w,
  `structural_credit_first_layer = 0`.
- *Values (dispute §7.2):*
  - 10 mm external is general guidance (L).
  - 18 mm internal is the Rev F ASA closed-spine bridge, a **design precedent** whose own guide calls it "a geometry
    audit, not … a print test".
  - The Bambu TDS "~30 mm PETG / ~40 mm ASA" are recorded as tier V and not used as defaults.
  - All are PROVISIONAL until the bridge ladder prints.
- *Checks:*
  - **M:** per layer, the shortest anchored span across each unsupported region.
  - **T:** Bridge / Internal Bridge road lengths, with endpoints landing on prior-layer material.
  - **V** is optional ([overhang-length relaxation](https://link.springer.com/article/10.1007/s11431-021-1996-y)).
- Orca cannot enforce this for normal supports ([issue #12966](https://github.com/OrcaSlicer/OrcaSlicer/issues/12966)).

**WALL-001 / WALL-002 / GAP-001: widths in line widths (Fillaprint, generalised)**
- Arachne bead count: `beads(T) = n + [(T − n) ≥ (n odd ? 2mb − 1 : mb)]`. Bands: 2 beads [1.70, 2.85)w,
  3 beads [2.85, 3.70)w, 4 beads [3.70, 4.85)w (`double-bead\docs\SPEC.md` §2;
  [Orca wall generator](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_wall_generator)).
- *Concrete catch:* D9 key leaves are 1.2 mm = 2.86w, on the 2/3-bead edge. D9 slices **classic**; spool-rack
  `package_part.py` sets **arachne**. The rule keys on `wall_generator`, and only T settles it.
- *Day-1 V:* density filter + projection at a 2w radius (Legolas #2: the robust triple costs three solves). The
  measured minimum feature on the thresholded design is binding at M (distance transform) and T (bead counts,
  gap-fill-only regions). The full robust formulation comes later if M failures are frequent.
- Sample **every layer** (T5). Legolas measured it as cheap (section 3.3).

**HOLE-001 / HOLE-002: holes, pegs, fits, and frozen interfaces across orientations**
- A vertical-axis hole is a polygon per layer and prints undersize
  ([nophead](https://hydraraptor.blogspot.com/2011/02/polyholes.html)). A horizontal-axis hole needs a roof crest.
- **Frozen interfaces are only printable in the orientation they were designed for.** The AM filter is not allowed
  to touch keep-ins. Interfaces therefore carry **orientation-dependent variants**: `bore: {teardrop: auto}`, which
  generates a `bore_td()`-style crest along the candidate's +Z_P. HOLE-001, OVH-001 and SUP-001 run on keep-in
  faces in the orientation prefilter (section 5.1, stage 3) before any optimisation is spent (dispute §7.5).
- *Compensation (D4):* D9 profile `xy_hole_compensation = 0`, `elefant_foot_compensation = 0.15`; the ASA profile has
  `filament_shrink = 99.46%` (XY scaled ~+0.54%). The ASA fits below were learned **with** that scaling and do not
  transfer to an unscaled profile.

| Fit | Geometry | Orientation | Material / profile | Result | Tag |
|---|---|---|---|---|---|
| Removable pin | Ø7.9 round pin (chord flat) in Ø8.4 teardrop bore = 0.5 mm diametral | Bore axis in layer plane; pin on its flat | PolyLite ASA calibrated | Fits (P-0012) | U |
| Too tight | Ø8.2 round in Ø8.4 = 0.2 | same | same | Won't enter (P-0008) | U |
| Too loose | 8.2 AC octagon in Ø8.8 = 0.6 at corners | same | PETG (P-0004) | Rattles | U |
| Sliding dovetail | 0.30 mm per side | Rev F | ASA (design value) | coupon advised | precedent |
| Pin/socket | Ø4.0 / Ø4.1 | Rev F | ASA (design value) | "variation can dominate" | precedent |
| Key barb | 1.8 mm total interference in a 5.4 mm slot | flat XY | PETG → ASA | adopted after P-0004 | U |

**EF-001:** slicer 0.15 mm (S; Prusa suggests ~0.2 mm on 0.4 mm nozzles,
[Prusa](https://help.prusa3d.com/article/elephant-foot-compensation_114487)). On fit-critical bed edges, exactly one
owner: slicer or chamfer. Lint warns on both.

**BED-002 / WARP-001 / BED-001 spin**
- Warp grows with shrinkage and stacked length, and falls with layer count and chamber temperature
  ([Wang, Xi & Jin 2007](https://link.springer.com/article/10.1007/s00170-006-0556-9)).
- The P1S chamber is passive; Bambu's ASA sheet asks for a 45–60°C chamber
  ([Bambu ASA](https://bambulab.com/en-us/filament/asa)).
- These are computed **once per orientation and spin candidate** from the first layers (Legolas #6), not per
  iteration.
- Spin is a feasibility gate. The spool-bracket body envelope is **207.5 × 233.5 × 24 mm**
  (`print-controls\ef-core-asa-4w-1p6\body-only.stl`), against a usable 236 mm between the 10 mm margins, plus the
  18×28 mm exclusion.

**COOL-001:** `slow_down_layer_time` 12 s (PETG starter) and 3 s (ASA calibrated); `slow_down_min_speed` 20 mm/s
([Orca cooling](https://www.orcaslicer.com/wiki/material_settings/cooling/material_cooling)).
- **T:** per-layer time from feedrates; flag layers that hit the floor.
- **V proxy:** per-layer perimeter/area, a trivial reduction (Legolas #6).
- Mitigation is often plate-level. It also matters for coupons: Sauron's Z-tension coupon must not be printed alone,
  or its weld history differs from the part's.

**VOID-001 / VOID-002 / SUP-001 / SUP-002**
- Closed voids are allowed in FDM. With 0% infill, every hollow body has **internal ceilings that the envelope never
  sees**, so the AM filter runs on the printed-material field (Sauron D6).
- **V:** cavity detection by flood-filling the void phase from outside (scipy label, about 1 s at 11 M voxels,
  estimated).
- **T:** support roads mapped into cavities.
- SUP-002 needs support geometry, so it is **M (estimated support) and T only**.
- "Hidden accessible support is acceptable" (D9) becomes a per-region `support_allowed: {access: hidden, reason}`.

**SHELL-001: orientation-dependent massing**
- `t(α) = max(t_w·sin α, n_t·h·cos α)`, where t_w is the **flow-spaced wall shell** (≈ 0.81 mm for outer 0.42 +
  inner 0.45, section 2.3), not n_w × w. This agrees with Sauron's derivation.
- With 2 walls and 5 × 0.2 skins: `t_min = t_w·n_t·h / sqrt(t_w² + (n_t·h)²) ≈ 0.63 mm` at `tan α* = n_t·h / t_w`,
  α* ≈ 51°.
- If the threshold were 2w at M level, the house minimum process would fail on every 30–60° surface (Sauron #4).
  So M is **advisory** (reports the thin band), and T is binding: ≥ 2 solid beads measured normal to the surface on
  actual roads, **after** Orca's `ensure_vertical_shell_thickness`, which exists to fix exactly this.
- The V-level implementation is Sauron's directional coating (XY erosion for walls, Z erosion for skins), not a
  separate penalty.

**STR-001: inter-layer failure (material card owns the numbers)**
- `F_L = sqrt((<σ_n>⁺/Z_t,eff)² + (τ/S_il,eff)²)` on the layer plane (n = e_z^P). `<·>⁺` is the Macaulay bracket.
  Pass if `F_L ≤ 1/SF`, with SF from `problem.yaml` (G2: fracture factor 4).
- Z_t and S_il come from the **active material card**, never from the catalog. Results are reported at the card's
  bracket corners. `Z_t,eff = g(f)·Z_t` uses OVH-002's f where mapped (hypothesis, coupon C5).
- **Which card:** production ASA is **PolyLite ASA** (print log P-0006 to P-0015). Its TDS in the repo gives
  σ_t XY 43.8 / Z 32 MPa (ratio 0.73, `spool-wall-rack\designs\closed-wall-e6\material-reference-data.json`).
  Bambu ASA (37/31, ratio 0.84; I verified the sheet) is a sensitivity bracket. The PETG grade is unknown: the log
  says "PETG grey"; candidates are the starter profile and Polymaker PETG (47.96/45.71). Ask the user.
- *Day 1:* post-check on the re-analysis, and the orientation prescreen (Sauron's analytic traction map: one stress
  field, a loop over directions, seconds). In the strength stage it becomes an aggregated constraint (p-norm with
  qp-relaxation), each extra adjoint solve costed (Legolas #1). The round-1 `z_fraction = 0.5` is withdrawn: a T0
  card always exists, so no fallback number is needed.
- External basis: [Ahn et al. 2002](https://iss.mech.utah.edu/wp-content/uploads/sites/103/2012/10/Ahn-Anisotropic_material-2002.pdf);
  [Mirzendehdel et al. 2018](https://par.nsf.gov/servlets/purl/10057716);
  [Umetani & Schmidt 2013](https://www.research.autodesk.com/publications/cross-sectional-structural-analysis-for-3d-printing-optimization/).

**PROC-001: effective settings (blocking)**
- After every slice, compare declared vs effective values for:
  - every key a rule depends on;
  - every key in the material card's `process_binding`.
- Minimum key list:
  - `printer_model`, `nozzle_diameter`, `layer_height`, all line widths, `wall_loops`, `wall_generator`,
    `min_bead_width`;
  - top/bottom shell layers and thickness, `ensure_vertical_shell_thickness`, `sparse_infill_density`/pattern,
    solid infill direction/pattern, `support_threshold_angle`/`enable_support`/`support_type`;
  - `filament_type`, nozzle/bed temperatures, fan min/max, `slow_down_layer_time`, `filament_shrink`,
    `filament_shrinkage_compensation_z`, `xy_hole_compensation`, `elefant_foot_compensation`;
  - `enable_arc_fitting`, `extruder_offset`;
  - modifier roles and per-modifier settings.
- A mismatch blocks the result and names the key, the expected and actual values, and which profile layer set it.

### 3.3 Where each check runs and what it costs (Legolas measurements)

| Check family | Level | Runs on | Cost per candidate | Basis |
|---|---|---|---|---|
| AM filter (OVH-001/VOID-001), density filter + projection (WALL/GAP), COOL proxy | V | inside each TO iteration | small next to the solve (separable/local grid ops) | Legolas §2–3 [estimate] |
| Per-layer 2D distance transform (WALL/GAP/SHELL M) | M | every extracted candidate | 13 ms/layer at 750×400 px (0.2 mm), ~3.9 s for 300 layers | Legolas `bench_checks.py` [measured] |
| 3D EDT | M | every candidate | 1.3 s at 11.25 M voxels; ~11 s at 90 M | [measured] / [extrapolated] |
| Erosion by a 4-cell disc (coating, pinch) | M | every candidate | 3.3 ms/layer | [measured] |
| Cavity flood fill (VOID) | V/M | every candidate | < 1 s at 11 M voxels | [estimate] |
| Mesh sectioning with shapely | M | every candidate | tens of seconds | [assumed, not measured] |
| Orca slice + PROC-001 + role check | T | finalists | ~3 s | repo, 2.67 s |
| `plastic_shape` cache + occupancy (all T checks) | T | finalists | ~16 s + ~14 s ≈ 35 s per finalist | repo |
| Orientation table: geometric columns | M | per orientation × spin | seconds | above |
| Orientation table: F_L column | FE | one stress field, then analytic loop | 5 s at 1.6 mm, 25 s at 0.8 mm (Jacobi-CG, measured); less with MG | Legolas review #7 |
| 3D truth FE | FE_3D | 1–3 finalists | 5–10 min today; 2–6 min projected with MG-PCG | Legolas §6 |

The conclusion: there is **no performance excuse for sampled checks**. Rule checks cost about 2 min per generation
of three finalists. FE dominates.

---

## 4. Schemas

Following Gandalf's split, the problem, process, material and rules are separate files, each content-hashed. The
catalog side is shown here.

### 4.1 Rule definition (`catalog/rules/OVH-001.yaml`)

```yaml
schema: fdmgen/rule@0.2
id: OVH-001
name: Self-supporting slope
protects: Undersides printed over nothing (droop, curl, support scars)
convention: {angle: slope_from_horizontal}
applies_to: {phase: printed_material, exclude_regions: [bed_contact, support_allowed]}
parameters:
  alpha_min_deg:      {unit: deg, binding: calibration}            # M/T value (50)
  alpha_filter_deg:   {unit: deg, derived: "grid stencil", note: "45 for 1-cell reach, dx = dz = h"}
  min_island_area_mm2: {unit: mm2, value: 0.3, tag: S, note: "selfsupport() skips faces < 0.3 mm2"}
slicer_keys: [support_threshold_angle, enable_support, support_type]   # PROC-001 verifies these
levels:
  V: {method: am_filter, field: printed_material, enforce: hard_filter, angle: alpha_filter_deg}
  M: {method: downward_triangle_area, angle: alpha_min_deg, report: islands_bbox_print_frame}
  T: {method: orca_role_count, roles: [Support, Support interface], limit_from: problem.support_policy}
repair: {method: voxel_underfill_to_alpha_min, recheck: [M, T], emit: geometry_delta}
authority: [T, M, V]          # T overrides M overrides V
severity: error
message_template: >
  {rule} {verdict} on {part} (orientation {orient}): {area_mm2:.0f} mm2 of downward faces flatter than
  {alpha_min_deg:.0f} deg ({90-alpha_min_deg:.0f} deg from vertical); largest island {island_area:.0f} mm2 at
  print-frame X {x0:.0f}..{x1:.0f}, Y {y0:.0f}..{y1:.0f}, Z {z0:.1f}..{z1:.1f}. Orca will add support here.
  Fix: steepen to >= {alpha_min_deg:.0f} deg, add a gusset, use a teardrop for bores, or mark the region
  support_allowed in problem.yaml with a reason.
sources:
  - {tag: S, ref: "5680-dock/desk-dock/D9-P5/overhang-threshold-test/toolpath-verification.json"}
  - {tag: V, ref: "https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support"}
  - {tag: L, ref: "https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf"}
calibration_coupon: overhang-ladder-v1    # α 35..60 by 5, printed also as C5 tension specimens
```

STR-001 differs only in its parameters block:
`criterion: material_card.interlayer_mode`, `sf: {from: problem.requirements.fracture_factor}`, and no strength
values.

### 4.2 Calibration binding (`catalog/calibration/p1s-0.4-polylite-asa-cal-2026-10.yaml`)

```yaml
calibration_id: p1s-0.4-polylite-asa-cal-2026-10
binds:
  printer: {model: Bambu Lab P1S, nozzle_mm: 0.4, plate: Textured PEI}
  orca_version: 2.4.2
  machine_profile_sha256: <sha>  process_profile_sha256: <sha>  filament_profile_sha256: <sha>
compensation:                      # consumed by HOLE/EF rules AND by the T-level G-code -> design mapper
  filament_shrink_xy: {value: 0.9946, owner: slicer}
  filament_shrinkage_compensation_z: {value: 1.0, owner: slicer}
  xy_hole_compensation: {value: 0, owner: geometry}
  elefant_foot_compensation: {value: 0.15, owner: slicer}
values:
  OVH-001.alpha_min_deg:        {value: 50, tag: S, receipt: "overhang-threshold-test (slice only)", status: PROVISIONAL}
  OVH-002.f_min:                {value: 0.6, tag: H, status: PROVISIONAL}
  BRG-001.max_span_external_mm: {value: 10, tag: L, status: PROVISIONAL}
  BRG-001.max_span_internal_mm: {value: 18, tag: precedent, receipt: "Rev F guide (geometry audit only)", status: PROVISIONAL}
  HOLE-002.fit.pin_horizontal_d8: {clearance_diametral_mm: 0.5, tag: U, receipt: "print-log P-0012"}
  COOL-001.slow_down_layer_time_s: {value: 3, tag: S, receipt: "filament profile"}
# no material strengths here: STR-001 reads the material card bound to the same profile hashes
```

If any bound hash changes, every value shows **STALE** until re-confirmed. The material card uses the same binding
mechanism (Sauron D10), so rule values and material constants go stale together.

### 4.3 Problem definition, worked example: G2 spool-rack bracket (E+F family)

Values come from `spool-wall-rack\designs\rev-g2\INTERFACE-CONTRACT.md`, `shape-seeds\moulding-clearance.json`,
`G2-BRIEF.md`, `print-controls\ef-core-asa-4w-1p6\selected-layout.json` and
`analysis\rev-g2\adaptive-validation\g-h0p2-interfaces.json`. Process and material live in their own files (Gandalf
§3.2–3.3), referenced by hash.

```yaml
schema: fdmgen/problem@0.2
id: spool-rack-g2-ef
authored_by: {route: adapter, adapter: fdmgen.adapters.spool_rack_g2,      # D6(b): reads, never edits, spool-rack
              sources: [{path: spool-wall-rack/designs/rev-g2/INTERFACE-CONTRACT.md, sha256: <pin>},
                        {path: spool-wall-rack/designs/rev-g2/shape-seeds/moulding-clearance.json, sha256: <pin>},
                        {path: spool-wall-rack/analysis/rev-g2/adaptive-validation/g-h0p2-interfaces.json, sha256: <pin>}]}
refs: {process: process/p1s-asa-4w-1p6.yaml#<sha>, material: catalog/materials/polylite-asa-p1s-cal.yaml#<sha>,
       catalog: {version: 0.1.0, calibration: p1s-0.4-polylite-asa-cal-2026-10}}
frames:
  design: {note: "= installed for this part: X out of wall (wall plane X=0), Y up, Z along rods"}
design_domain: {file: geom/body-envelope.step, frame: design}     # new artefact produced by the adapter
interfaces:                       # frozen keep-ins; printability variants generated per orientation
  - {id: rear-rod,  type: rod_seat, axis: Z, center_xy_mm: [90, 0],  nominal_d_mm: 25.4, seat_d_mm: 26,
     fit: {class: measured_pending, owner: geometry}, role: interface, support: forbidden, roof_variant: teardrop_auto}
  - {id: front-rod, type: rod_seat, axis: Z, center_xy_mm: [190, 12], nominal_d_mm: 25.4, seat_d_mm: 26,
     fit: {class: measured_pending, owner: geometry}, role: interface, support: forbidden, roof_variant: teardrop_auto}
  - {id: mount-upper, type: screw_clearance, axis: X, center_yz_mm: [164, 12], d_mm: 5.2, access: driver_and_washer}
  - {id: mount-lower, type: screw_clearance, axis: X, center_yz_mm: [40, 12],  d_mm: 5.2, access: driver_and_washer}
  - {id: wall-datum, type: locating_corner, point_xy_mm: [0, -32], horizontal_underside_x_mm: [0, 25.4]}
keep_outs:
  - {id: crown-moulding, rule: "no material with Y < -32 for X in [0, 25.4]", structural_support: none}
  - {id: spool-slide, rule: "flange slide envelope, 180-220 mm spools, >= 3.5 mm over rail radius 12.4-12.7", sweep: axial_Z}
load_cases:
  - id: full
    frame: design
    gravity_dir: [0, -1, 0]
    total_N: 117.72                                  # 12 kg per bracket
    split: {model: radial_nonneg_seat_pressure_zero_axial_moment, source: g-h0p2-interfaces.json#<sha>,
            reference_N: {rear-rod: [-31.29, -75.12, 0], front-rod: [31.29, -42.60, 0]}}   # lint checks the sum
  - id: one-spool-delta
    mass_kg: 1.25                                    # 12.26 N = 0.104 x full
    metric: movement_change_mm
    limit: 1.0
    re_solve: required                               # G2-BRIEF: not proportional scaling
supports:                                            # boundary conditions, not print supports
  - {id: wall, type: unilateral_contact, face: "X=0"}
  - {id: mount-upper, type: washer_axial_rigid_plus_bore_lateral_rigid}
  - {id: mount-lower, type: washer_axial_rigid_plus_bore_lateral_rigid}
service: {sustained_F: 85, brief_loaded_F: 100}
requirements:
  - {metric: bracket_movement_mm, load_case: full, max: 4.0, note: "5 mm total minus 1 mm provisional rails/mounts"}
  - {metric: fracture_factor, min: 4.0, basis: material_card}    # STR-001 SF
objective: {minimise: spent_extrusion_cm3, note: "actual Orca volume; bridges counted, zero credit"}
rule_overrides:
  - {rule: BRG-002, value: {structural_credit_first_layer: 0}, reason: "G2: sacrificial bridges get no credit"}
  - {rule: WALL-003, value: {min_walls: 2}, reason: "G2 hard requirement"}
infill: {base_density: 0, credited: false, reason: "G2 per-problem declaration (not a tool default)"}
support_policy: {default: forbidden, regions: []}
orientation:
  mode: sweep                     # general form
  candidates: auto                # stable hull poses + 6 axes + user list, each with spin {0, 90} for BED-001
  override: {mode: fixed, up_in_design: [0, 0, 1],
             reason: "product bracket: bending in layer plane, interfaces along Z", applies_to: product_runs}
  # MVP known-answer runs drop the override and sweep 3 candidates (Gandalf P1)
acceptance_ladder: [GEOMETRY, TOOLPATH, SCREEN, FE_3D, COUPON, PRINTED, QUALIFIED]
```

The lint checks:
- the resultant matches `total_N` and the pinned reference split to round-off;
- every interface has a role and a support rule;
- every override has a reason;
- keep-ins don't intersect keep-outs.

---

## 5. The designer workflow end to end

### 5.1 Stages

| Stage | Command (proposed) | Runs on | Returns | Reuses |
|---|---|---|---|---|
| 1. Define | route (a) `emit_problem()`, (b) adapter, (c) hand-written YAML + STEP | PC | `problem.yaml`, keep-in/out STEPs, hashes | manifest pattern; D9/spool-rack outputs (read-only) |
| 2. Lint | `fdmgen lint` | PC, seconds | Plain-language errors: units, frames, untagged values, load sum/split vs pin, keep-in ∩ keep-out, overrides without reason, STALE calibration, the PROVISIONAL rule list | new |
| 3. Orient | `fdmgen orient` | PC, minutes | Ranked orientation × spin table (5.2). Prefilter: BED-001/002, WARP-001, interface printability (HOLE-001/OVH-001/SUP-001 on keep-ins with variants), STR-003 | `audit_print_mesh_support.py`; Sauron's traction prescreen |
| 4. Run | `fdmgen run --budget 20m` | PC GPU (compute-box later, with heads-up) | **Before starting:** printed cost estimate (cells × iterations × solves) and what fits in the budget (e.g. "20 min ≈ 20–40 orientations at 1.6 mm or 3–5 at 0.8 mm"). **During:** live `progress.json` with generation, best-so-far, measured s/iteration and a re-estimated ETA | `evo_*` budget pattern |
| 5. Verify finalists | `fdmgen verify --top 3` | PC (Orca) | Slice, PROC-001, all T checks, zero-ersatz FE, receipts | `package_part.py` (ported), `gpu_demo_slice.py`, `verify_mixed_plate.py`, `audit_ef_bonds.py` |
| 6. Review | `fdmgen review <cand>` | PC | `review.html` + PNG panels (5.4) | `render_print_control.py` |
| 7. Print coupons / part | `p1s-print` + `print-log.py` | printer | log entry tied to slice hash and candidate ID | existing |
| 8. Calibrate | `fdmgen calibrate --from print-log P-00NN` | PC | new calibration and card versions; dependent results marked STALE | new |
| 9. Publish | `fdmgen writeup <cand>` | PC | site page draft (5.5) | Gridline |

### 5.2 Ranked orientation table (what the designer sees)

| Rank | Up (design) / spin | Support area mm² (M) / roads (T) | Bed contact mm² | F_L (prescreen, card tier) | Warp L mm (ASA) | Interface variants needed | Height / est. time | Hard fails | PROVISIONAL rules |
|---|---|---|---|---|---|---|---|---|---|
| 1 | +Z / 0° | 0 / – | … | 0.21 (T0) | … → brim | none | 24 mm / … | none | STR-001, WARP-001 |

Rows are illustrative. The rules for this table:
- Pareto ranking; dominated rows are greyed, never hidden.
- Each cell links to its rule card and region.
- The F_L column states the FE resolution it came from.
- A free-text "designer decision" field sits beside the table (the D9 splice-ring paragraph is exactly this, written
  as prose).

### 5.3 Traps: where confusion and false confidence creep in

| # | Trap | Real example | Guard |
|---|---|---|---|
| T1 | Angle convention | `overhang-threshold-test/build.py` docstring says "angle from vertical", but `run = 15·tan(ang)` is the vertical drop, so `wedge-30deg` is α = 30° from horizontal. The names are right; the comment is wrong. Readers of the comment get the opposite meaning | D3, both values printed, unit test on a known wedge |
| T2 | Frame offsets | P1S `extruder_offset 0x2` shifted material −2 mm until fixed (`EVOLUTION.md`) | Frame table 2.1; plate transform read back from the sliced 3MF; round-trip test |
| T3 | Compensation double count | ASA `filament_shrink 99.46%` vs "no global ASA shrink correction" in the docs; EF compensation + chamfer | `compensation:` block with owner; lint |
| T4 | Slicer behaviour taken as printer capability | Wedge test is slice-only | S vs U tags shown next to verdicts |
| T5 | Sampled checks | `Z_SAMPLE_COUNT = 10` | Per-layer checks (cheap, 3.3); `NOT_CHECKED` ≠ PASS |
| T6 | Untagged, conflicting defaults | Bridge 15 mm (SKILL.md) vs 20 mm (code) | CAL-001 |
| T7 | Settings drift / lost slices | G PETG project slice not recovered | PROC-001 + slice hash in print log |
| T8 | Lost modifier roles | STEP has no roles | Post-slice role check |
| T9 | Optimiser exploits the proxy | "Cheap stress trends were unreliable" | Finalists always sliced + FE; proxy and verified side by side; failures kept |
| T10 | Silent geometry changes | `selfsupport()` adds unreported material | Every repair: delta + re-check (D2) |
| T11 | Bead-band edges | D9 key leaf 1.2 mm = 2.86w | WALL-002 |
| T12 | Z quantisation | `TONGUE_H = 12.7` = 63.5 layers | ZQ-001 reports the as-sliced height |
| T13 | Global non-strict passes | `verify_plates.py` sets all non-strict | Per-region support policy |
| T14 | Mixed-fidelity Pareto | Screen and FE points on one chart | Marker = fidelity; no cross-fidelity ranking |
| T15 | Generic profile as calibration | G2 says it isn't | Calibration binding; "uncalibrated" banner |
| T16 | Fit transfers across orientation/material | Pins differ by shape/material | Fit classes keyed by orientation + profile hash |
| T17 | Write-up overclaims | (risk) | Template 5.5 |
| T18 | Shrink scaling invisible to the truth mapper | `plastic_shape` asserts an orthonormal item transform; Orca's 1/0.9946 XY scale sits outside it, so mapped material is ~0.5 mm large over 100 mm (≫ the 0.03 mm audit tolerance) | Mapper consumes `compensation`; golden test: same part at 100% and 99.46% maps to identical design-frame occupancy |
| T19 | Frozen interfaces assumed printable in any orientation | Bores and rod seats exact-booleaned back after extraction | Interface variants + prefilter (HOLE-001) |
| T20 | Hand-typed loads | Round 1 Gandalf: equal 58.86 N vertical split vs the repo's 75.12/42.60 N with ±31.29 N horizontal | Loads generated from the pinned contact model; lint on sum and split |
| T21 | Arc fitting silently on | D9 `process.json` `enable_arc_fitting = "1"`; library `read_paths()` ignores G2/G3 | Canonical parser handles arcs and asserts the footer internally; key in PROC-001 |
| T22 | V filter believed to enforce the M/T angle | 45° stencil vs 50° target | `authority: [T, M, V]`; repair delta reported |

### 5.4 Reviewing a result (in order)
1. **Verdict strip.** Highest rung reached, PROVISIONAL count, overrides with reasons, STALE bindings, repair deltas.
   Any red stops the review.
2. **Print-frame view.** Bed, build arrow, α heat map, support roads, bridge roads coloured by span, repaired regions.
3. **Bead map.** Per-layer bead counts from the slice, band-edge flags, helper outlines, SHELL-001 thin band vs the
   T measurement.
4. **Inter-layer map.** F_L with card tier and bracket corners.
5. **Fits table.** Each interface, its variant in this orientation, fit class, compensation owner, calibration
   status.
6. **Diff against the previous candidate.** Volume moved, rules newly passing or failing, mutation record.
7. **Iterate** by editing the builder, adapter input or `problem.yaml`, never the generated files.

Every message follows the template: what happened, where (part, orientation, print-frame coordinates), why it
matters, and two or three fixes, one always "declare an exception with a reason".

### 5.5 Website write-up template (Gridline, limits first)
1. **Headline** with the rung reached ("Toolpath-verified, 3D-screened on a T0 card; not printed").
2. **Problem**: interfaces, keep-outs, loads (with direction and source), orientation and reason.
3. **What the optimiser could change** and what it could not (frozen interfaces, declared process).
4. **Pareto chart** with fidelity encoded, finalists labelled, failure count.
5. **Chosen candidate**: sections, actual toolpath sections, spent extrusion, helpers, repair deltas.
6. **Printability table**: verdict, level reached, tag, PROVISIONAL rules highlighted.
7. **What this establishes / does not establish** (fixed block).
8. **Downloads**: body/helper STEP, model-only 3MF with roles, sliced 3MF (engineering evidence), `problem.yaml`,
   calibration file, material card, SHA256SUMS.
9. **Reproduce** in three commands.

---

## 6. Publishing the constraint set

**Scope (v1.0):** single-nozzle 0.4 mm FDM, enclosed CoreXY class (P1S reference), PETG and ASA, OrcaSlicer 2.4.x,
planar layers. Out of scope: multi-material, non-planar, resin/powder, creep and fatigue allowables.

**Phased releases (aligned with Gandalf's roadmap):**

| Version | When | Content | Honesty label |
|---|---|---|---|
| v0.1 | Roadmap P1 | All rules defined; V/M/T checkers for OVH, VOID, WALL, GAP, BRG, PROC, BED; tags as found (mostly S/L/H) | "Provisional: slicer-verified, not print-calibrated" |
| v0.5 | P2, after the first calibration plate per material | OVH, BRG, GAP, HOLE, WARP, PILL values tag U; golden-geometry tests for every rule | "Calibrated on one P1S for PETG <grade> and PolyLite ASA" |
| v1.0 | No binding value is tag H; conformance suite passes | Slicer-key mapping (Orca ↔ Prusa ↔ Bambu Studio ↔ Cura where possible); JSON Schemas; one-afternoon calibration guide | Release |

**Release criteria:**
- every rule has a definition, parameters with units, levels, enforcement, a message template and sources;
- golden-geometry tests near the threshold on both sides;
- `fdmgen selftest` slices the coupon plate and reproduces the expected verdicts on the installed Orca, recording
  parse seconds so Orca-version regressions show (Legolas #9).

**Versioning:**
- Rule *semantics* use semver (major = meaning changes; minor = new rule; patch = text).
- Calibration files and material cards are versioned separately by date and profile hashes.
- Results pin both. Superseded results show STALE and are never rewritten.

**Reuse:** others contribute calibration files and cards for their machines. Licence: data and text CC-BY-4.0, code
permissive. This is one merged open question with Gandalf Q4; the user decides.

**The calibration plate (merged with Sauron's coupons):**
- overhang ladder α 35–60° in 5° steps, also printed as C5 tension specimens;
- bridge ladder 6–40 mm (covers the vendor claims);
- gap ladder 1–3w;
- horizontal and vertical hole/peg ladders at Ø4 and Ø8;
- a 150 mm warp bar;
- pillar ladder;
- Sauron's C1/C2 tension (C2 printed with companion parts for layer time).

One plate per material.

---

## 7. Open disputes for the merge (with recommended resolution)

1. **Overhang margin (45° filter vs 50° target).**
   - Evidence: Orca supported the exactly-45° wedge (S). A one-cell stencil on cubic voxels yields exactly 45°
     (Sauron §4.6).
   - Recommendation: **V = 45° filter; M/T bind at 50°; voxel repair + re-check + delta.** Upgrade to non-cubic V
     cells (dx ≈ 0.84·dz, dz = h) only if repair deltas are large. Gandalf and Legolas prefer this route.
   - Correction to my round-2 review of Sauron: non-cubic cells **do** keep layers on grid planes (dz stays h); only
     dx shrinks, costing about 1.4× cells.
   - Lowering Orca's threshold to 40° is the alternative only after a printed 40–45° coupon passes.
2. **Bridge limits: 10/18 mm vs vendor 30/40 mm.**
   - The Bambu TDS figures (verified on the ASA and PETG Basic sheets) are for Bambu grades and profiles, and for
     ASA with a 45–60°C chamber the P1S does not hold actively. The 18 mm precedent was never print-tested.
   - Recommendation: **default 10 external / 18 internal, PROVISIONAL; vendor figures stored as tag V and not used
     as defaults; bridge ladder 6–40 mm decides.**
   - Since BRG-002 gives bridges zero structural credit, a conservative default costs little structurally.
3. **Infill palette vs the 0% house rule.**
   - 0% base infill + 100% helpers is a **spool-rack G2 per-problem declaration**. D9 plates run 5 walls + 40%
     gyroid.
   - Recommendation: `infill: {base_density, credited}` is required in every `problem.yaml`. Sparse infill is
     credited only with a card of tier ≥ T1 for that pattern and density. Otherwise it is credited 0 (conservative)
     and the report says so.
   - Gandalf's 15/40% modifier palette is allowed only under that rule.
4. **PolyLite ASA vs Bambu cards.**
   - The print log shows production ASA is **PolyLite ASA, calibrated profile**. Its TDS gives Z/XY strength 0.73,
     vs 0.84 for Bambu ASA. The grade changes the very ratio that drives orientation choice.
   - Recommendation: **T0 ASA card from PolyLite** (repo `material-reference-data.json`), Bambu ASA as a
     sensitivity corner. Ask the user which PETG is "PETG grey".
5. **Frozen-interface printability across orientations.**
   - Evidence: keep-ins are exact-booleaned back and exempt from the AM filter. `bore_td()` crests depend on the
     build direction.
   - Recommendation: **interfaces declare orientation-dependent variants** (teardrop crest along +Z_P for any bore
     or seat whose axis lies within 45° of the layer plane). The orientation prefilter runs HOLE-001/OVH-001/SUP-001
     on keep-ins before optimisation. An interface with no printable variant in an orientation rejects that
     orientation, with a message naming the interface.
6. **Fixed grid + rotated tensor (Legolas) vs re-voxelise per orientation (Gandalf, Sauron).**
   - Every geometric rule needs layers on grid planes.
   - Recommendation: **re-voxelise for design TO.** Keep the fixed-grid rotated-tensor route as **analysis mode**
     (orientation scoring of an existing design). That is a good first deliverable for a collaborator's project #1, labelled
     as stiffness/strength-only with no printability rules applied.
7. **Design-grid resolution vs enforceable rules.**
   - At ≥ 0.6–0.8 mm the optimiser cannot enforce 2w features or gaps, 1.6 mm skins or per-layer overhang.
   - Recommendation: publish a **rule × resolution-tier table** in the merged plan:
     - OVH/VOID enforced at every tier (coarse);
     - WALL/GAP/SHELL only at ≤ 0.2–0.4 mm;
     - everything else post-check.
   - Never write "the optimiser respected printability" without naming the rules.
8. **STR-001 placement.**
   - Legolas: post-check first (the adjoint cost). Sauron: aggregated constraint, not penalty.
   - Recommendation: both, in sequence. Day 1 post-check + analytic prescreen; strength stage aggregated constraint.

---

## 8. Open questions

1. **User:** is there access to a universal testing machine? This decides whether the T1 card tier, and any
   absolute strength claim, is reachable (Sauron Q1).
2. **User:** which PETG is "PETG grey"? Confirm PolyLite ASA as the production ASA.
3. **User:** licence (CC-BY-4.0 data + permissive code proposed; shared with Gandalf Q4).
4. **User:** did any of your Python jobs die on 2026-10-07 around Legolas's `taskkill /IM` incident?
5. **Gandalf (P0-D):** can Orca 2.4.2 modifier volumes override `wall_loops` and shells via 3MF metadata? This
   bounds what SHELL-001 and MOD-001 can steer.
6. **Sauron:** the centre of Orca's `filament_shrink` scaling (object centre or origin?) for the T18 golden test.
7. **Legolas:** the repair-delta threshold that would justify non-cubic V cells (dispute 1); measure it on the first
   MVP runs.

---

## 9. Sources

User repos (read-only), cited inline. External:
- [OrcaSlicer support settings](https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support);
  [overhangs](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_overhangs);
  [wall generator](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_wall_generator);
  [material basic info (filament_shrink)](https://www.orcaslicer.com/wiki/material_settings/filament/material_basic_information);
  [cooling](https://www.orcaslicer.com/wiki/material_settings/cooling/material_cooling);
  [issue #12966](https://github.com/OrcaSlicer/OrcaSlicer/issues/12966);
  [shrink vs XY compensation discussion](https://github.com/SoftFever/OrcaSlicer/discussions/541)
- [Prusa elephant foot](https://help.prusa3d.com/article/elephant-foot-compensation_114487);
  [Prusa Arachne](https://help.prusa3d.com/article/arachne-perimeter-generator_352769)
- [Hubs thin walls](https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/);
  [nophead polyholes](https://hydraraptor.blogspot.com/2011/02/polyholes.html);
  [Bambu ASA guide](https://bambulab.com/en-us/filament/asa)
- Bambu TDS (verified: overhang ~70°, bridging ~30 mm PETG Basic / ~40 mm ASA; ASA specimens annealed):
  [ASA](https://solidprint3d.ie/wp-content/uploads/2024/03/Bambu-Lab-ASA-Filament-Technical-Data-Sheet.pdf),
  [PETG Basic](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf)
- [ISO/ASTM 52910:2018](https://www.iso.org/standard/67289.html);
  [Adam & Zimmer 2014](https://ris.uni-paderborn.de/record/22384)
- [Langelaar 2017](https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf);
  [Gaynor & Guest 2016](https://link.springer.com/article/10.1007/s00158-016-1551-x);
  [overhang length relaxation 2021](https://link.springer.com/article/10.1007/s11431-021-1996-y)
- [Mirzendehdel, Rankouhi & Suresh 2018](https://par.nsf.gov/servlets/purl/10057716);
  [Umetani & Schmidt 2013](https://www.research.autodesk.com/publications/cross-sectional-structural-analysis-for-3d-printing-optimization/);
  [Ahn et al. 2002](https://iss.mech.utah.edu/wp-content/uploads/sites/103/2012/10/Ahn-Anisotropic_material-2002.pdf)
- [Telea & Jalba 2011](https://link.springer.com/chapter/10.1007/978-3-642-21569-8_34);
  [Wang, Xi & Jin 2007](https://link.springer.com/article/10.1007/s00170-006-0556-9);
  [Will it print](https://pmc.ncbi.nlm.nih.gov/articles/PMC8555737/);
  [Bambu/Orca 3MF structure (secondary)](https://printago.io/blog/3mf-file-format)
- Fellow reports: `gandalf.md`, `sauron.md` (§2.3, §2.7, §3.2, §4.4, §4.6, §4.7), `legolas.md` and
  `scratch\legolas\bench_checks.py`.

---

## 10. Review disposition

| Reviewer # | Finding (short) | Disposition | Reason | Landed in |
|---|---|---|---|---|
| Gandalf 1 | STR-001 `z_fraction` duplicates the material card | **Accepted** | One source of truth; the T0 card always exists | D1, 3.1 STR-001, 3.2 STR-001, 4.2 |
| Gandalf 2 | 45° filter vs 50° target must be stated | **Accepted** | Grid-limited V; M/T authoritative | 2.6, 3.2 OVH, 4.1, §7.1, T22 |
| Gandalf 3 | Scope reuse of B-rep operators; `selfsupport` is near-bed only | **Accepted** | Iso-surface output can't take B-rep prisms or fillets | D5, §1 |
| Gandalf 4 | Adapters instead of editing frozen builders; three authoring routes | **Accepted** | BRIEF read-only rule; `build_d9.py` runs on import | D6, 4.3 `authored_by`, 5.1 |
| Gandalf 5 | Orientation `sweep` general, `fixed` as override | **Accepted** | Product vs MVP known-answer runs | 4.3 `orientation` |
| Gandalf 6 | One vocabulary for frames, tiers, verdicts | **Accepted** | U/S/V/L/H per value, T0–T2 per card, ladder + spool-rack strings | D7, 2.1, 2.4, 2.5 |
| Gandalf 7 | Repair must re-check and emit a delta | **Accepted** | Prevents FAIL → PASS without evidence | D2, 2.6, 4.1 `repair`, T10 |
| Gandalf 8 | `package_part.py`: per-object walls only; hard-coded transform | **Accepted** | Verified in source | §1 inventory |
| Gandalf 9 | Wall term = sum of actual widths; Sauron's coating as the V implementation | **Accepted** (refined by Sauron 4: flow spacing) | Single w source | 2.3, 3.2 SHELL-001 |
| Gandalf 10 | Per-phase catalog targets | **Accepted** | Lets the roadmap publish honestly before v1.0 | D9, §6 table |
| Gandalf 11 | Trap list verified; T1 convention form | **Accepted** (T1 wording further corrected per Sauron 6) | – | 5.3 T1 |
| Gandalf 12 | Merge licence question | **Accepted** | – | §6, §8 Q3 |
| Sauron 1 | STR-001 criterion: two-term interface mode, Z_t and S_il bound separately | **Partly** | Criterion adopted; the z_fraction fallback is dropped rather than kept as H, because a T0 card always exists (also per Gandalf 1) | 3.1, 3.2 STR-001 |
| Sauron 2 | `filament_shrink` breaks truth mapping | **Accepted** | Real ~0.5 mm/100 mm error vs 0.03 mm tolerance | D4, 2.1 gcode row, 4.2, T18, §8 Q6 |
| Sauron 3 | Add gcode and bead frames; plate read back from the sliced 3MF | **Accepted** | Plate ≠ gcode; arrange can spin | 2.1 |
| Sauron 4 | Flow spacing (~0.81 mm); state t_min; SHELL M advisory, T binding | **Accepted** | Otherwise the house minimum fails on all 30–60° faces | 2.3, 3.1, 3.2 SHELL-001 |
| Sauron 5 | k_step = 1 − f; don't change h; azimuthal test; M/T authoritative | **Accepted** | Shared parameter with STR bond fraction | 2.2, 2.6, 3.2 OVH, 4.1 `authority` |
| Sauron 6 | T1: the comment is wrong, not the file names | **Accepted** | Re-derived; my round-1 wording was inverted | §1, 5.3 T1 |
| Sauron 7 | Load needs direction, frame and a pinned contact model | **Accepted** | Also catches round-1 Gandalf's split error | 4.3 `load_cases`, T20 |
| Sauron 8 | Orientation column → F_L with card tier | **Accepted** | Includes shear | 5.2 |
| Sauron 9 | PROC-001 covers the material card's process binding keys | **Accepted** | Rules and cards go STALE together | 3.2 PROC-001, 4.2 |
| Sauron 10 | STR-001 as aggregated constraint; VOID-001 inside via the printed-material field | **Accepted** (timing per Legolas 1) | Unitless penalty hides tradeoffs; internal ceilings are invisible to envelope checks | D8, 3.1, 3.2 VOID, §7.8 |
| Sauron 11 | SURF-001 notation; layer-boundary exception | **Accepted** | Fewer angle names | 3.1 SURF-001 |
| Legolas 1 | STR-001 not in the optimiser day 1 (adjoint cost) | **Accepted** | Prescreen is analytic | D8, 3.2 STR-001, §7.8 |
| Legolas 2 | Filter + projection instead of the robust triple on day 1 | **Accepted** | 3× solves; M check is cheap and binding | D8, 3.2 WALL |
| Legolas 3 | Measured costs of M/T checks | **Accepted** | Answers Q3 | 3.3 |
| Legolas 4 | V enforces only what the stencil allows; margin at M/T with repair | **Accepted** | Same as Gandalf 2 | 2.6, 3.2 OVH, §7.1 |
| Legolas 5 | SUP-002 is M(estimated)/T, not V | **Accepted** | Support geometry exists only from Orca or estimation | 3.1, 3.2 |
| Legolas 6 | COOL proxy fine at V; WARP is orientation-level | **Accepted** | Computed once per orientation and spin | 3.1, 3.2 |
| Legolas 7 | `orient` F_L column needs an FE solve; state its resolution, PROVISIONAL | **Accepted** | – | 3.3, 5.2 |
| Legolas 8 | `--budget` should print a cost estimate first | **Accepted** (plus live ETA) | Users can't judge cells × iterations | 5.1 stage 4 |
| Legolas 9 | Selftest records parse seconds | **Accepted** | Catches Orca-version slowdowns | §6 |
