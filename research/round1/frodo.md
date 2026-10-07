# Frodo: designer workflow and the FDM printability constraint catalog

Round 1 research report for `fdm-gen`. Angle: the person who has to use this every day. Two questions. Can
the printability rules be written down so that a machine can check them and a human can trust the result? And what
does the loop look like from a CadQuery builder through to a printed part and a published write-up?

Scope: Bambu Lab P1S, 0.4 mm nozzle, PETG and ASA, OrcaSlicer 2.4.2. Everything was read-only. No remote machines
were used and nothing was printed or sliced for this report. Evidence tiers are defined in section 2.3. Every number
in this report has one.

---

## 0. Summary and numbered decisions

a collaborator is **mostly right**. The guidance that exists comes in four forms, and none of them is a versioned,
machine-checkable rule set that is tied to a calibrated printer:
- Generic standards. [ISO/ASTM 52910](https://www.iso.org/standard/67289.html) explicitly gives no process- or
  material-specific data.
- Vendor rule-of-thumb tables, e.g. [Hubs](https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/).
- One-off empirical studies, e.g. [Adam & Zimmer 2014](https://ris.uni-paderborn.de/record/22384).
- Slicer settings, which encode the *slicer's* behaviour, not the printer's capability.

The user's repos already encode about 15 rules in code, more than any public source I found. They are scattered
across builders, profile JSON, audit scripts and prose (section 1).

| # | Decision proposed |
|---|---|
| D1 | The catalog is **data plus checkers plus calibration receipts**, in three separate files: `rules.yaml` (definitions, stable IDs), `calibration/<printer>-<nozzle>-<filament>-<date>.yaml` (values with evidence), and a checker library. A rule value never lives in a builder constant without a pointer back to the catalog. |
| D2 | Every rule declares **which levels it can be checked at**: V (voxel/density field, inside optimisation), M (mesh/B-rep, post-geometry), T (actual Orca toolpaths) and P (physical coupon). A result reports the *highest level actually reached*, never just "PASS". |
| D3 | **One angle convention**: overhang slope is measured from the horizontal bed plane, matching Orca's `support_threshold_angle`. Reports also print the other convention in brackets. Reason: the user's own overhang test files are named in the opposite sense to what they measure (section 5.3, trap T1). |
| D4 | **Compensation ownership is explicit per interface**: who owns shrink, hole and elephant-foot correction, the geometry or the slicer profile. Today the ASA profile applies `filament_shrink = 99.46%` while the docs say "no global ASA shrink correction" (trap T3). |
| D5 | Reuse, don't rewrite. Use `selfsupport()`/`bore_td()`/`dress()` and `PROTECT`/`PRINT_Z` from D9-P5, `audit_print_mesh_support.py` and `verify_mixed_plate.py` from coupon-pipeline, `plastic_shape.py`/`audit_ef_bonds.py`/`package_part.py`/the effective-settings and modifier-role checks in `gpu_demo_slice.py` from spool-rack, the Arachne bead algebra from Fillaprint `docs/SPEC.md`, and `print-log.py` for physical feedback. |
| D6 | The problem definition is a YAML file (`problem.yaml`) that the CadQuery builder **emits**, the same way it already emits `manifest.json`. Designers keep authoring in CadQuery and do not hand-write YAML for geometry. |
| D7 | Results use a fixed **verdict ladder**, extending the status strings the spool-rack already uses (`PASS_ACTUAL_SLICE_PROCESS_AND_BED_CHECKS; PHYSICAL_PRINT_UNQUALIFIED`). Pareto plots never rank points of different fidelity against each other. |
| D8 | Publish catalog v1.0 only when every rule has (a) a definition, (b) checkers at two or more levels with golden-geometry tests, (c) defaults with tiers, and (d) at least one physical calibration receipt on the P1S for both PETG and ASA. Until then it is labelled v0.x "provisional". |

---

## 1. What the user's repos already encode (inventory)

These are the raw material for the catalog. File references are absolute under `D:\Code\Models\`.

| Rule (catalog ID) | Where it lives today | What it does | Gap |
|---|---|---|---|
| Overhang ≥ 45° from horizontal (OVH) | `5680-dock\desk-dock\D9-P5\build_d9.py:41` `selfsupport()` | Fuses straight-down fill under every face whose normal is within 45° of print-down (`dot > 0.7071`), only for faces 0.4–4.5 mm above the bed (`maxdrop=4.5`), and respects a keep-out solid | Local near-bed fix only. Added volume is **not reported** in the manifest, unlike `dress()` |
| Teardrop horizontal bores (OVH/HOLE) | `build_d9.py:85` `bore_td()` | 40° from vertical (50° from horizontal) tangent crest, "clear of the slicer's 45° threshold" | Margin of 5° chosen by hand. Not tied to a calibrated value |
| Gusset slope (OVH) | `build_d9.py:97` `GUSSET_SLOPE=1.5` (34° from vertical) | Support-reducing gussets under bosses | Cites `overhang-threshold-test/` |
| Slicer overhang threshold (OVH) | `5680-dock\desk-dock\D9-P5\overhang-threshold-test\` | Four wedges sliced in Orca. Slopes of 30/39/45° from horizontal got support; 55° did not | **Slice-only** evidence (tier S), not a print. File names are in the inverted convention (T1) |
| Protected zones (PROT) | `build_d9.py` `PROTECT[name]=[solids]` (e.g. lines 348, 413, 519) | Keep-out solids per part: bores, key slots, airways, laptop band | Used by `dress()` and `selfsupport()` keep-out, not by support placement checks |
| Print orientation (ORI) | `build_d9.py:108` `PRINT_Z`, `pose()`; `DESIGN.md:258-269` | Named print-up vectors per part. Orientation tradeoffs argued in prose (bed contact 65→718 mm², vertical pose rejected at 89 mm² and for "load across weaker layers") | Hand-picked; "No slicer search for orientations" (`DESIGN.md:34`) |
| Edge dressing (WARP/EF) | `5680-dock\desk-dock\D9-P5\dress.py` | Fillets edges parallel to print Z (inside 3 mm, outside 1.5 mm); never touches bed edges; skips PROTECT; reports every operation | Already acts as a warp mitigation (rounded footprint corners) but is not described as one |
| Build volume and exclusions (BED) | `profiles\machine.json` (`printable_area` 256², height 250, `bed_exclude_area` 18×28); `prepare_and_slice.py` asserts 10–246 mm placement and 12 mm spacing | Placement guard | Fine. Also note `extruder_offset 0x2` (T2) |
| Support / bridge counting (OVH/BRG/SUP) | `5680-dock\tools\coupon-pipeline\architect\verify_mixed_plate.py` | Per-object counts of Support, Bridge and Internal Bridge roads from actual G-code; "strict" objects must have zero | `verify_plates.py` sets **every object non-strict** (T13) |
| Geometric support proof (OVH/BED) | `coupon-pipeline\architect\audit_print_mesh_support.py` | Mesh-only: bed contact area, non-bed downward area, max underside angle. Writes a `scope` line saying what it is not | Good model for honest receipts |
| Hole sizes from toolpaths (HOLE) | `coupon-pipeline\architect\check_native_holes.py`, `verify\` | Sections sliced meshes for small rings | Prototype only |
| Effective settings verification (PROC) | `spool-wall-rack\analysis\rev-g2\gpu_demo_slice.py:120-145` | Confirms Orca actually used P1S / material / walls / skins / 0% infill and that modifier roles survived | Excellent. Generalise it to every rule that depends on a setting |
| Modifier 3MF packaging (MOD) | `spool-wall-rack\analysis\rev-g2\package_part.py` | Model-only 3MF: one `normal_part` plus N `modifier_part` at 100% | Reuse as the massing output path |
| Toolpath → layer polygons, bond connectivity (WALL/MOD/STR) | `spool-wall-rack\analysis\rev-g2\plastic_shape.py`, `audit_ef_bonds.py`, `audit_ef_connections.py` | Raw roads with widths, heights and roles; bridge roads get **zero structural credit**; layer-to-layer bond graph | This is the T-level substrate for most toolpath checks |
| Two-wall minimum, 0% base infill, helpers 100% (WALL/MOD) | `spool-wall-rack\G2-BRIEF.md` | Process rules as prose | Should become rule overrides in `problem.yaml` |
| Minimum stroke and minimum clear gap = 2w (WALL/GAP) | `double-bead\README.md:24-36`, `docs\SPEC.md` R1–R11, §6 | Width rules in line-width units, the Arachne bead-count algebra and the morphological pinch fill (`PINCH_R=0.98w`) | Written for text; generalises directly to any 2D section |
| Fit allowances (FIT) | `5680-dock\TOLERANCES.md`, `build_d9.py:118-123`, `docs\prints\print-log.json` | Dovetail 0.30 mm per side; pin 4.0/4.1; ASA pins: 7.9 round in 8.4 bore fits, 8.2 round will not enter, 8.2 AC octagon in 8.8 rattles | Real physical data (tier U), but keyed to nothing (orientation, profile) |
| Printed load direction (STR) | `spool-wall-rack\README.md:189`, `5680-dock\ENGINEERING_REPORT.md:93`, `D9-P5\DESIGN.md:21`, `D8\FAN_FIT.md:33` | "Main bending load stays in the layer plane"; "leaves flex in the layer plane"; pins lie on a chord flat; threads print axis-vertical | Rule of practice. Never quantified |
| Generic printability checker (OVH/WALL/BRG/FEAT/BED) | `novel-cad-skill\scripts\check_printability.py` | Mesh checks: flat bottom, overhang, wall thickness, bridge span, min feature | Uncited defaults (bridge 20 mm in code vs 15 mm PETG in `SKILL.md:334`); **10 Z samples per part** (T5) |
| Physical feedback log (CAL) | `5680-dock\tools\print-log.py`, `docs\prints\print-log.json` | Every print tied to source-STL hash, profiles and commit, with lessons | This is how calibration receipts should be collected |

**Net:** about 15 rules exist as working code, and about 10 more exist only as prose. The missing pieces are a single
convention, a schema, a calibration binding and a verdict ladder. The physics knowledge is not what's missing.

---

## 2. Conventions every rule depends on

### 2.1 Frames and units
- Units are mm, deg, s, mm/s, N and MPa. Every parameter has a `unit:` field. A unitless number is a lint error.
- Three frames, always named: `design` (the builder's assembly frame), `print` (+Z = build direction, origin at the
  part's bed-contact minimum) and `plate` (Orca bed coordinates). `PRINT_Z` already defines `design→print`. The
  `plate` frame must undo the P1S `extruder_offset 0x2`. `EVOLUTION.md` documents a 2 mm material shift caused by
  missing this (T2).
- `w` is the **actual configured line width** for the region (outer wall 0.42, inner 0.45, first layer 0.5 in the
  D9 profile). `h` is the layer height (0.2). Rules expressed in `w` and `h` come out in mm via the active profile, as
  Fillaprint does.

### 2.2 Angle convention (D3)
- `slope_from_horizontal` (α): angle between the surface and the bed plane. A horizontal ceiling has α = 0 and a
  vertical wall has α = 90. This equals the angle between the outward normal and −Z, which is what Orca's
  `support_threshold_angle` means: "support for overhangs whose slope angle is below the threshold"
  ([Orca support wiki](https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support)).
- Reports print `α=50° (40° from vertical)`, because the user's code mixes both conventions (`bore_td` "40° from
  vertical", gussets "34° from vertical", Orca threshold 45 from horizontal).

### 2.3 Evidence tiers (on every default value)
| Tier | Meaning | Example |
|---|---|---|
| **U** | User's own physical print outcome, logged | 7.9 mm pin in 8.4 mm ASA bore fits (P-0012) |
| **S** | What the user's slicer profile does (slice evidence, not print evidence) | Orca supports 45° slopes and leaves 55° alone |
| **V** | Vendor or slicer documentation | Prusa elephant-foot compensation ≈ 0.2 mm |
| **L** | Literature or general DfAM guidance | Bridges < 10 mm generally fine (Hubs) |
| **H** | Heuristic placeholder; needs a coupon before anyone relies on it | Pillar height/width ≤ 8 |

The lint fails on any value without a tier. A rule whose binding value is only tier H shows as **PROVISIONAL** in
every report, in the same place as its verdict.

### 2.4 Check levels and enforcement modes
- **V** voxel or density field (inside the optimiser). **M** mesh or B-rep of a candidate. **T** actual Orca
  toolpaths (`plastic_shape.py` roads with role, width and height). **P** physical coupon or part.
- Enforcement: `hard_filter` (built into the design parameterisation, e.g. AM filter), `penalty` (in the objective),
  `repair` (automatic geometry change with a delta report), `post_check` (accept or reject only), `advisory`.

---

## 3. The constraint catalog

### 3.1 Master table

Defaults assume the P1S, 0.4 mm nozzle, h = 0.2, w_outer = 0.42, Textured PEI, the profiles in
`D9-P5\profiles\` (Generic PETG starter, PolyLite ASA calibrated). "Opt" is whether the rule can be enforced inside
optimisation.

| ID | Rule | Protects against | Levels | Opt | PETG default | ASA default | Tier |
|---|---|---|---|---|---|---|---|
| BED-001 | Build volume, exclusion zone, margins | Unprintable or colliding placement | M,T | hard (bounds) | 256×256×250, exclude 0–18 × 0–28, margin ≥ 10 mm, spacing ≥ 12 mm | same | S |
| OVH-001 | Self-supporting slope | Drooping or curled undersides, support scars | V,M,T | hard_filter | α ≥ 50° designed; slicer threshold 45° | α ≥ 50° designed | S (threshold), H (print quality) |
| OVH-002 | Overhang step per layer | Same, generalised to layer height | V,M | hard_filter | offset per layer `h/tan α ≤ k·w`, k = 0.5 → α_min = 43.6° at h = 0.2 | k = 0.4 (less fan) → 50.0° | H, derived |
| BRG-001 | Bridge span | Sag, failed anchors | M,T | post_check (+ relaxed filter) | external ≤ 10 mm, internal (hidden) ≤ 20 mm | external ≤ 10, internal ≤ 18 | L / precedent |
| BRG-002 | Bridge anchoring and credit | Bridges ending in air; overstated strength | T | post_check | both ends on material; first bridge layer gets zero structural credit | same | U-policy (G2) |
| WALL-001 | Minimum solid wall / feature (XY) | Dropped or partial features | V,M,T | hard (length scale) | ≥ 2w = 0.84 mm | same | U (G2, Fillaprint) |
| WALL-002 | Bead-count band edge | Stiffness jumps from print variation | M,T | penalty | no thickness within ±0.1w of an Arachne band edge (1.70, 2.85, 3.70, 4.85 w at mb = 0.85) | same | U (Fillaprint algebra) |
| WALL-003 | Perimeter count | Thin load-bearing shell | T | post_check (process) | ≥ 2 walls everywhere; structural ≥ 4 | same | U-policy |
| GAP-001 | Minimum clear gap (XY negative feature) | Gaps fused or smeared | V,M,T | hard (void length scale) | ≥ 2w = 0.84 mm | same | U (Fillaprint R3/R9) |
| GAP-002 | Print-in-place / sliding clearance | Fused moving parts | M,P | post_check | ≥ 0.3 mm per side XY (dovetail precedent); Z ≥ 1 layer + 0.1 | same | U (Rev F), H (Z) |
| ZQ-001 | Z quantisation | Fit-critical heights rounded by slicer | M | hard (snap variables) | fit-critical Z features on multiples of h | same | L |
| HOLE-001 | Horizontal-axis hole roof | Sagging bore crowns, support inside bores | M,T | repair (`bore_td`) | teardrop crest α ≥ 50° (40° from vertical), tangent | same | U (D9 prints) |
| HOLE-002 | Hole / peg fit classes | Rattling or non-entering fits | M,T,P | frozen interface | lookup table keyed by orientation, material, profile hash (3.3) | same | U for ASA Ø8; H otherwise |
| EF-001 | Elephant foot / first-layer squish | Oversized bed-edge, binding fits | M,T | repair or process | slicer comp 0.15 mm **or** 0.3–0.5 mm 45° chamfer on fit-critical bed edges, never both | same | S, V |
| BED-002 | Bed contact and stability | Detachment, knock-over, toppling | M | orientation-level | contact ≥ 100 mm² and ≥ 5% of the projected footprint; CoM projection inside contact hull with ≥ 3 mm margin; height / min base width ≤ 4 without brim | same | H (D9 precedent 89 mm² rejected) |
| WARP-001 | Warp risk (long flat runs, sharp footprint corners) | Lifted corners, bowed long parts | V,M | penalty | footprint L ≤ 200 mm without extra measures | L > 120 mm ⇒ brim ≥ 5 mm and convex footprint corners r ≥ 3 mm; avoid bed-lying plates t < 2 mm with L > 100 mm | L (Wang 2007), H values |
| COOL-001 | Minimum layer time / small sections | Heat sag, blobs, poor tips | T (V proxy) | post_check | flag layers below `slow_down_layer_time` = 12 s that hit `slow_down_min_speed` 20 mm/s | threshold 3 s | S |
| VOID-001 | Enclosed voids are allowed but self-supporting | Collapsed roofs, wrong mass | V,M | hard_filter (via OVH) | cavity roofs obey OVH/BRG | same | L, U (Rev F, G2 hollow sections) |
| VOID-002 | No trapped support | Support permanently inside a cavity | V,T | post_check | 0 support roads inside any enclosed cavity | same | logic |
| SUP-001 | No support on protected/functional faces | Debris on fits (D9 T-tongue "0.6 mm proud" was support debris) | T | post_check | 0 support-interface contact within 0.6 mm of `PROTECT` faces | same | U (P-0004) |
| SUP-002 | Support removal access | Unremovable support | V,T | post_check | every support island connected to exterior through an opening ≥ 6 mm and depth ≤ 3 × opening | same | H |
| SUP-003 | Support interface gap | Fused or ugly supported faces | T (settings) | process | top z gap 0.15–0.2 (profile 0.15 / plates 0.2); PETG prefers ≥ 0.2 | 0.15–0.2 | S, V |
| SEAM-001 | Seam placement | Zits on fits; aligned weak line | T | post_check | no outer-wall loop starts within 1 mm of PROTECT faces | same | H |
| SKIN-001 | Top skin over sparse/void | Pillowing, holes in tops | T | process | top ≥ max(5 layers, 1.0 mm); 0% base infill needs internal bridge anchors ≤ BRG-001 | same | S |
| PILL-001 | Thin free-standing pillars/fins | Wobble, nozzle knock, layer-time sag | V,M | penalty | min width ≥ 3w; height / min width ≤ 8 | same | H |
| MOD-001 | Modifier (dense helper) geometry | Sliver solids, unbonded helpers, lost roles | M,T | hard (massing) | helper boundaries ≥ 2w from walls/other helpers or overlapping by ≥ 2w; helper bonded to credited material; roles survive slicing | same | U (G2 audits), H (2w) |
| MOD-002 | Small sparse areas become solid | Mass/stiffness differ from intent | T | advisory | `minimum_sparse_infill_area` 15 mm² | same | S |
| SHELL-001 | Orientation-dependent skin thickness | Thin skin on mid slopes | M,T | penalty | normal skin `t_n(φ) ≈ max(n_w·w·cos φ, n_t·h·sin φ)` ≥ t_min | same | derived, H |
| STR-001 | Load paths in layer plane | Interlayer tension/shear failure | V (FE) | penalty/constraint | σ_zz,+ and τ_z ≤ z_fraction × in-plane allowable / SF; z_fraction = 0.5 placeholder | same placeholder | L (Ahn 2002), H value |
| STR-002 | Flexures and snap leaves flex in the layer plane | Snapped leaves | M | post_check | bending axis of a flexure ∥ Z | same | U (D8/D9 practice) |
| STR-003 | Threads axis-vertical; pins lie with axis in layers | Weak threads, split pins | M | orientation-level | thread axis ∥ Z; pin axis ⟂ Z on a chord flat | same | U (D9) |
| SURF-001 | Stair-stepping on functional faces | Rough fits, leaks | M | post_check | cusp `c = h·cos α_n` ≤ allowable where the face is tagged functional | same | L |
| TXT-001 | Embossed text / marks | Unreadable or filled marks | M,T | post_check | Fillaprint: stroke and gap ≥ 2w; capital height 14w | same | U (Fillaprint) |
| PROC-001 | Effective settings match the declared process | "The setting didn't do what it claimed" | T | post_check | every rule-relevant key compared to the effective config | same | U (spool-rack check) |
| CAL-001 | Rule values bound to a calibration | Generic values passed off as calibrated | – | lint | every binding value has tier + receipt | same | policy |

### 3.2 Rule cards (the ones where the details matter)

Each card has the same parts: protects / parameters / check per level / enforcement / defaults / sources / pitfalls.

**OVH-001 / OVH-002: overhang**
- *Protects:* surfaces printed over nothing, which curl, droop or get supports.
- *Parameters:* `alpha_min_deg`, or the derived form `k_step` (the fraction of line width a new perimeter may hang
  past the one below). `alpha_min = atan(h / (k_step·w))`. At w = 0.42 and k = 0.5: h = 0.12 → 29.7°, 0.20 → 43.6°,
  0.28 → 53.1°. This is the honest way to make the rule "depend on layer height". Cooling and material enter through
  k. Orca's overhang speed classes are also defined "relative to line width"
  ([Orca overhangs](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_overhangs)), so k maps
  onto the slicer's own model. The ASA calibrated profile runs fans at 10–80% (PETG 40–90%), so a smaller k for ASA
  is plausible. That needs a printed coupon.
- *Checks:* **V**: Langelaar's AM filter (layer-by-layer max-type filter, fixed 45° on a grid;
  [paper](https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf)) or Gaynor & Guest's projection
  ([paper](https://link.springer.com/article/10.1007/s00158-016-1551-x)). On a 0.2 mm voxel grid with h = 0.2, the
  45° stencil maps exactly onto one-cell steps. Other angles need anisotropic stencils (Sauron's call). **M**:
  area-weighted downward faces with α < α_min, excluding bed faces and `support_allowed` regions
  (`audit_print_mesh_support.py` logic). Report islands with location in the print frame. **T**: per-object
  `Support`/`Support interface` road counts and overhang-wall roads (`verify_mixed_plate.py`).
- *Defaults:* design target α ≥ 50°. The slicer threshold is 45° and the wedge test at exactly 45° *did* get support,
  so designing at 45° is a coin-flip. The 5° margin is what `bore_td` already uses.
- *Pitfall:* the wedge test proves what Orca **will generate**, not what the P1S **prints well** (tier S, not U). A
  printed overhang ladder in both materials is the first calibration coupon.
- *Exceptions:* small overhangs below `k·w`; horizontal ceilings that qualify as bridges (BRG); the bed.

**BRG-001 / BRG-002: bridges**
- *Parameters:* `max_span_external_mm`, `max_span_internal_mm`, `anchor_min_mm` (each end on material ≥ 2w),
  `structural_credit_first_layer = 0`.
- *Checks:* **M**: per-layer, find downward horizontal regions that have support at both ends in the layer below and
  measure the shortest anchored span (morphological width of the unsupported region along the best direction).
  **T**: `Bridge` and `Internal Bridge` road lengths per object; verify both endpoints land on prior-layer material
  (`plastic_shape` layer polygons). **V**: overhang-length relaxation lets the optimiser keep short horizontal spans
  ([Sci China Tech Sci 2021](https://link.springer.com/article/10.1007/s11431-021-1996-y)). Treat it as optional; the
  T check is authoritative.
- *Defaults:* 10 mm external, from the general guidance
  ([Hubs](https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/)). Internal (hidden)
  ≤ 18–20 mm: the Rev F ASA design used an intentional 18 mm closed-spine bridge, but its own guide calls that "a
  geometry audit, not … a print test", so it is a **precedent, not evidence**. The novel-cad-skill table says 15 mm
  PETG while its code defaults to 20 mm for everything. That is exactly the untiered-default problem (T6).
- *Orca note:* Orca has no "max bridge length without support" for normal supports
  ([issue #12966](https://github.com/OrcaSlicer/OrcaSlicer/issues/12966)), so slicer settings cannot enforce this
  rule. Geometry must.

**WALL-001 / WALL-002 / GAP-001: widths in line-width units (the Fillaprint generalisation)**
- *Parameters:* `min_solid_w = 2`, `min_gap_w = 2`, `wall_generator` (classic | arachne), `min_bead_width` (mb),
  `band_margin_w = 0.1`.
- *Why in w:* Fillaprint already shows the rule is about **beads**, not millimetres. At T = 2w a stroke is "the outer
  wall loop passing itself". Under Arachne, `beads(T) = n + [(T−n) ≥ (n odd ? 2mb−1 : mb)]`, so 2 beads for
  T ∈ [1.70, 2.85)w, 3 beads for [2.85, 3.70)w, 4 beads for [3.70, 4.85)w (`double-bead\docs\SPEC.md` §2). See also
  [Orca wall generator](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_wall_generator) and
  [Prusa Arachne](https://help.prusa3d.com/article/arachne-perimeter-generator_352769).
- *Concrete catch:* D9 key leaves are 1.2 mm = 2.86w at w = 0.42, right on the Arachne 2/3-bead edge. D9 slices with
  `wall_generator = classic`, while spool-rack `package_part.py` sets `arachne`. **The same rule gives different bead
  outcomes per generator**, so the rule must key on the generator, and only the T check settles it.
- *Checks:* **V**: robust (eroded/dilated) length-scale formulation on both phases (Gaynor & Guest include minimum
  length scale). **M**: per-layer section raster, distance transform, local thickness = 2 × inscribed radius
  ([Telea & Jalba 2011](https://link.springer.com/chapter/10.1007/978-3-642-21569-8_34)). The gap check is
  Fillaprint's `fill_pinches`, a closing with radius 0.98w, applied to the void phase. Sample **every layer**, not 10
  levels (T5). **T**: count beads across the section from actual roads and flag gap-fill-only regions.

**HOLE-001 / HOLE-002: holes, pegs and fits**
- *Orientation matters first:* a vertical-axis hole is a polygon in every layer. It prints undersize from facets and
  corner blobbing ([nophead polyholes](https://hydraraptor.blogspot.com/2011/02/polyholes.html)). A horizontal-axis
  hole has a roof that needs a teardrop (`bore_td`) and a stair-stepped circumference.
- *Where compensation lives (D4):* the D9 profile has `xy_hole_compensation = 0` and `elefant_foot_compensation =
  0.15`. The **ASA calibrated filament profile has `filament_shrink = 99.46%`**, which scales XY up by about 0.54%
  ([Orca material info](https://www.orcaslicer.com/wiki/material_settings/filament/material_basic_information)). The
  ASA pin fits below were therefore learned *with* that scaling on, and they do not transfer to a generic ASA profile.
- *Fit-class table seed (all from the user's prints):*

| Fit | Geometry | Orientation | Material / profile | Result | Tier |
|---|---|---|---|---|---|
| Removable pin, sliding | Ø7.9 round pin (one chord flat) in Ø8.4 teardrop bore = 0.5 mm diametral | Bore axis in layer plane; pin lying on its flat | PolyLite ASA calibrated | Fits (P-0012) | U |
| Too tight | Ø8.2 round in Ø8.4 = 0.2 diametral | same | same | Will not enter (P-0008) | U |
| Too loose | 8.2 AC octagon in Ø8.8 = 0.6 at corners | same | PETG (P-0004) | Rattles | U |
| Sliding dovetail | 0.30 mm per side horizontal | Rev F | ASA (design value) | Coupon advised | precedent |
| Pin/socket | Ø4.0 / Ø4.1 = 0.1 diametral | Rev F | ASA (design value) | "variation can dominate" | precedent |
| Key barb | 1.8 mm total interference through a 5.4 mm slot | Flat XY print | PETG → ASA | Adopted after P-0004 | U |

- *Checks:* **M**: classify cylindrical B-rep faces by axis relative to print Z and by diameter, then look up the fit
  class; unknown combinations are `NOT_CALIBRATED`, not PASS. **T**: measure the inner-perimeter road centreline
  diameter + w at mid-height (extend `check_native_holes.py`).
- *Enforcement:* interfaces are **frozen keep-ins** in the optimiser and are never optimised.

**EF-001: elephant foot**
- Slicer compensation 0.15 mm (profile, S; Prusa suggests about 0.2 mm on 0.4 nozzles
  ([Prusa](https://help.prusa3d.com/article/elephant-foot-compensation_114487))). `dress()` deliberately never
  touches bed edges. Rule: for bed-edge segments within a PROTECT/fit zone, either the slicer owns it (record the
  compensation) or the geometry owns it (chamfer). A lint warning fires if both are present on one edge.
  `5680-dock\TOLERANCES.md` already tells users to "inspect elephant foot … before changing geometry".

**BED-002 / WARP-001: bed contact, stability, warping**
- *Model:* the warp in [Wang, Xi & Jin 2007](https://link.springer.com/article/10.1007/s00170-006-0556-9) grows with
  shrinkage rate and stacked-section length, and falls with layer count and chamber temperature. The P1S chamber is
  passive (no heater), so ASA on long footprints is the risk case
  ([Bambu ASA](https://bambulab.com/en-us/filament/asa)).
- *Checkable metrics per first-layer island:* longest in-plane extent L; minimum convex-corner radius of the footprint;
  contact area; thin bed-lying plates (area ≫, t < 2 mm). The user always runs a 5 mm outer brim (8 mm for Rev F
  ASA), and `dress()` already rounds footprint corners (outside 1.5 mm, inside 3 mm). That should be credited as the
  mitigation it is.
- *Stability:* the D9 splice-ring decision (65 → 718 mm² bed contact; vertical pose rejected at 89 mm²) is the model
  for a ranked-orientation table. All threshold numbers are H until a warp bar ladder and a tall-thin coupon are
  printed.

**COOL-001: layer time**
- `slow_down_layer_time` is 12 s for the PETG starter and 3 s for the ASA calibrated profile, with
  `slow_down_min_speed` 20 mm/s ([Orca cooling](https://www.orcaslicer.com/wiki/material_settings/cooling/material_cooling)).
- **T**: compute per-layer time from G-code feedrates; flag layers where the slowdown floor was hit (the slicer could
  not reach the minimum time).
- **V** proxy: per-layer perimeter length / area.
- Mitigation is often plate-level (print small parts with others), which `prepare_and_slice.py` already does
  implicitly. The check should say so instead of asking for a geometry change.

**VOID-001 / VOID-002 / SUP-001 / SUP-002: cavities and supports**
- FDM differs from powder and resin here: **closed voids are fine and useful** (Rev F hollow sections, G2 0% base
  infill). There is nothing to drain. The rules are that roofs self-support and that no support is generated inside a
  sealed cavity.
- **V**: flood fill the void phase from the exterior; any unreached component is an enclosed cavity.
- **T**: map support roads into cavities: any hit is FAIL with location.
- SUP-001 is the PROTECT idea applied to supports. P-0004's "T tongue looked 0.6 mm proud but it was stuck support
  debris" is the canonical failure.
- SUP-002 (removal access) is the hardest to make objective. Start with a tool-opening heuristic and label it H.
  "Hidden accessible support is acceptable" (D9 `DESIGN.md`) becomes a per-region `support_allowed: {access: hidden}`
  flag.

**MOD-001 / SHELL-001: massing rules (where orientation drives material)**
- Perimeters are always laid in the XY plane of the *print* frame. On a face whose normal is φ above horizontal
  (wall φ = 0, top φ = 90), the wall shell is about `n_w·w·cos φ` thick and the top/bottom skin about `n_t·h·sin φ`.
  The thinnest combined skin sits near `tan φ = n_w·w / (n_t·h)`: 42° for 2 walls × 0.45 and 5 × 0.2 layers,
  ≈ 0.67 mm. That is orientation-dependent massing in one line, and it is why the generative system has to know print
  Z before it allocates shells. Orca's `ensure_vertical_shell_thickness` may add solid infill, so the T check is
  authoritative.
- Helpers (100% modifiers in a 0% body) must not leave slivers thinner than 2w, must bond (`audit_ef_bonds.py`), and
  must survive slicing as `modifier_part` (`gpu_demo_slice.py` role check).

**STR-001 / 002 / 003: orientation-dependent strength**
- The rule of practice is already universal in the repos: "main bending load stays in the layer plane".
- Quantify it as: in the print frame, evaluate interlayer normal tension σ_zz⁺ and interlayer shear (τ_xz, τ_yz) per
  cell against `z_fraction × allowable / SF`. FDM interlayer properties are well documented as weaker and process
  dependent ([Ahn et al. 2002](https://iss.mech.utah.edu/wp-content/uploads/sites/103/2012/10/Ahn-Anisotropic_material-2002.pdf)).
  Strength-based anisotropic topology optimisation with Tsai-Wu exists
  ([Mirzendehdel, Rankouhi & Suresh 2018](https://par.nsf.gov/servlets/purl/10057716)). A cheap orientation screen
  exists too ([Umetani & Schmidt 2013](https://www.research.autodesk.com/publications/cross-sectional-structural-analysis-for-3d-printing-optimization/)).
- The **value** of z_fraction for P1S PETG/ASA is unknown here and must come from coupons. 0.5 is a placeholder (H)
  and must appear as PROVISIONAL in every report. The material model itself is Sauron's area. The catalog only defines
  the check and where its inputs come from.

**PROC-001: effective settings**
- This is the most user-protective rule in the set. Every rule that depends on a slicer key (`wall_loops`,
  `support_threshold_angle`, `slow_down_layer_time`, `filament_shrink`, `elefant_foot_compensation`,
  `wall_generator`, …) declares the key. After slicing, the checker compares declared and effective values, exactly
  as `gpu_demo_slice.py` does for 7 keys today. A mismatch blocks the result, with a message naming the key, the
  expected value, the actual value and which profile layer set it.

### 3.3 What is deliberately *not* in the catalog
Drying, nozzle and bed temperatures, enclosure closed for ASA, and material service temperature or creep (G2: 85°F
sustained, 100°F brief). These are **process/material** requirements bound by profile hash and the material model,
not geometric rules. The catalog references them through `requires_profile:` so they cannot be silently dropped.

---

## 4. Schemas

### 4.1 Rule definition (`catalog/rules.yaml`), one entry shown

```yaml
catalog: fdm-printability
catalog_version: 0.1.0            # semver of rule semantics (section 6)
conventions:
  units: {length: mm, angle: deg, time: s, force: N, stress: MPa}
  angle: slope_from_horizontal     # 0 = ceiling, 90 = vertical wall
  frames: [design, print, plate]
rules:
  - id: OVH-001
    name: Self-supporting slope
    protects: Undersides printed over nothing (droop, curl, support scars)
    applies_to:
      phase: solid
      exclude_regions: [bed_contact, support_allowed]
    parameters:
      alpha_min_deg: {unit: deg, binding: calibration}     # value comes from the calibration file
      k_step:        {unit: w,   binding: calibration, optional: true}
      min_island_area_mm2: {unit: mm2, default: 0.3, tier: S, note: "selfsupport() skips faces < 0.3 mm2"}
    derived:
      alpha_min_from_k: "degrees(atan(layer_height / (k_step * line_width_outer)))"
    slicer_keys: [support_threshold_angle, enable_support, support_type]   # PROC-001 verifies these
    checks:
      V: {method: am_filter, ref: "Langelaar 2017", stencil: layer_aligned, enforce: hard_filter}
      M: {method: downward_face_area, report: islands_with_bbox_print_frame}
      T: {method: orca_role_count, roles: [Support, Support interface], limit_per_object_from: problem.support_policy}
    severity: error
    message_template: >
      {rule} {verdict} on {part}: {area_mm2:.0f} mm2 of downward faces flatter than {alpha_min_deg:.0f} deg
      (largest island {island_area:.0f} mm2 at print-frame X {x0:.0f}..{x1:.0f}, Y {y0:.0f}..{y1:.0f}, Z {z0:.1f}..{z1:.1f}).
      Orca will add support here. Fix: steepen to >= {alpha_min_deg:.0f} deg, add a gusset, use bore_td for bores,
      or mark the region support_allowed in problem.yaml with a reason.
    sources:
      - {tier: S, ref: "D9-P5/overhang-threshold-test/toolpath-verification.json"}
      - {tier: V, ref: "https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support"}
      - {tier: L, ref: "https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf"}
    calibration_coupon: overhang-ladder-v1     # STEP + expected roles shipped with the catalog
```

### 4.2 Calibration binding (`catalog/calibration/p1s-0.4-polylite-asa-cal-2026-10.yaml`)

```yaml
calibration_id: p1s-0.4-polylite-asa-cal-2026-10
binds:
  printer: {model: Bambu Lab P1S, nozzle_mm: 0.4, plate: Textured PEI}
  orca_version: 2.4.2
  machine_profile_sha256: <sha of profiles/machine.json>
  process_profile_sha256: <sha of profiles/process.json>
  filament_profile_sha256: <sha of profiles/filament-polylite-asa-calibrated.json>
  compensation: {filament_shrink_xy: 0.9946, xy_hole_compensation: 0, elefant_foot_compensation: 0.15}
values:
  OVH-001.alpha_min_deg:  {value: 50, tier: S, receipt: "overhang-threshold-test (slice only)", status: PROVISIONAL}
  BRG-001.max_span_internal_mm: {value: 18, tier: precedent, receipt: "Rev F guide (geometry audit only)", status: PROVISIONAL}
  HOLE-002.fit.pin_horizontal_d8: {clearance_diametral_mm: 0.5, tier: U, receipt: "print-log P-0012"}
  COOL-001.slow_down_layer_time_s: {value: 3, tier: S, receipt: "filament profile"}
  STR-001.z_fraction: {value: 0.5, tier: H, status: PROVISIONAL, receipt: null}
```

If any bound hash changes, every value in the file shows **STALE** until it is re-confirmed. That is how "settings
that don't do what they claim" are caught before printing, not after.

### 4.3 Part problem definition, worked example: G2 spool-rack bracket (E+F family)

All values are from `spool-wall-rack\designs\rev-g2\INTERFACE-CONTRACT.md`, `shape-seeds\moulding-clearance.json`,
`G2-BRIEF.md` and `print-controls\ef-core-asa-4w-1p6\selected-layout.json`.

```yaml
problem: spool-rack-g2-ef
problem_version: 3
emitted_by: {builder: designs/rev-g2/print-controls/ef-core-asa-4w-1p6/build_core.py, builder_sha256: <sha>}
catalog: {version: 0.1.0, calibration: p1s-0.4-polylite-asa-cal-2026-10}
frames:
  design: "installed: X out from wall (wall plane X=0), Y vertical rel. rear rod, Z along rods"
  print:  {up_in_design: [0, 0, 1], note: "broad side down; principal bending in layer plane"}
design_domain:
  envelope_step: body-envelope.step                    # PROPOSED new artefact: outer bound the optimiser may fill
  thickness_z_mm: 24                                   # reference width; may vary per family
interfaces:                                            # frozen keep-ins; never optimised
  - {id: rear-rod,  type: rod_seat, axis: Z, center_xy_mm: [90, 0],  nominal_d_mm: 25.4, seat_d_mm: 26,
     fit: {class: measured_pending, owner: geometry}, faces: functional, support: forbidden}
  - {id: front-rod, type: rod_seat, axis: Z, center_xy_mm: [190, 12], nominal_d_mm: 25.4, seat_d_mm: 26,
     fit: {class: measured_pending, owner: geometry}, faces: functional, support: forbidden}
  - {id: mount-upper, type: screw_clearance, axis: X, center_yz_mm: [164, 12], d_mm: 5.2,
     access: {driver_and_washer: required}}
  - {id: mount-lower, type: screw_clearance, axis: X, center_yz_mm: [40, 12],  d_mm: 5.2,
     access: {driver_and_washer: required}}
  - {id: wall-datum, type: locating_corner, point_xy_mm: [0, -32], horizontal_underside_x_mm: [0, 25.4]}
keep_outs:
  - {id: crown-moulding, rule: "no material with Y < -32 for X in [0, 25.4]", source: moulding-clearance.json,
     structural_support: none}
  - {id: spool-slide, rule: "flange slide envelope for 180-220 mm spools, >= 3.5 mm clearance over rail radius 12.4-12.7",
     sweep: axial_Z}
loads:
  - {id: full, force_N: 117.72, at: [rear-rod, front-rod], split: per_contact_model, note: "12 kg per bracket"}
  - {id: one-spool-delta, mass_kg: 1.25, metric: movement_change_mm, limit: 1.0, needs_fresh_solve: true}
supports:   # boundary conditions, not print supports
  - {id: wall, type: unilateral_contact, face: X=0}
  - {id: screws, type: fastener, at: [mount-upper, mount-lower]}
service: {sustained_F: 85, brief_loaded_F: 100}
objectives:
  minimise: spent_extrusion_cm3            # actual Orca volume, bridges counted, zero credit
  constraints:
    - {metric: bracket_movement_mm, max: 4.0, note: "5 mm total minus 1 mm provisional rails/mounts"}
    - {metric: fracture_factor, min: 4.0, basis: material_process}
process:                                   # becomes Orca settings + PROC-001 expectations
  printer: P1S-0.4
  material: ASA            # PETG variant = second problem file, same geometry
  walls: {min: 2, design_variable: [2, 8]}
  base_infill_percent: 0
  helpers: {role: modifier_part, infill_percent: 100, count: free, clipped_to_body: true}
  skins_mm: {top: 1.6, bottom: 1.6}
rule_overrides:            # every override needs a reason; reports list them prominently
  - {rule: BRG-002, value: {structural_credit_first_layer: 0}, reason: "G2 brief: sacrificial bridges get no credit"}
  - {rule: WALL-003, value: {min_walls: 2}, reason: "G2 hard requirement"}
support_policy: {default: forbidden, allowed_regions: []}
orientation: {mode: fixed, candidates: [print.up_in_design], reason: "bending in layer plane; interfaces along Z"}
acceptance_ladder: [GEOMETRY, TOOLPATH, SCREEN_REDUCED, FE_3D, COUPON, PART_PRINTED, QUALIFIED]
```

How this comes out of a builder (D6): the builder already holds `PROTECT`, `PRINT_Z` and the manifest. Add one call,
`fdmgen.emit_problem(path, parts=..., protect=PROTECT, print_z=PRINT_Z, interfaces=..., loads=...)`. It writes the
YAML plus STEP files for every keep-in and keep-out solid, each hashed. The YAML is generated and reviewable, but not
hand-maintained.

---

## 5. The designer workflow end to end

### 5.1 Stages and artefacts

| Stage | Command (proposed) | Runs on | Returns | Reuses |
|---|---|---|---|---|
| 1. Define | builder + `emit_problem()` | PC | `problem.yaml`, keep-in/out STEPs, hashes | `build_d9.py` PROTECT/PRINT_Z, manifest pattern |
| 2. Lint | `fdmgen lint problem.yaml` | PC, seconds | Errors: missing units, frames, untiered values, keep-in ∩ keep-out, interface inside keep-out, override without reason, STALE calibration. Lists every PROVISIONAL rule that will bind | new |
| 3. Orient | `fdmgen orient problem.yaml` | PC, minutes | Ranked orientation table (section 5.2) with per-rule penalties; nothing chosen silently | `audit_print_mesh_support.py` |
| 4. Run | `fdmgen run problem.yaml --budget 20m --host pc` (later `--host compute-box`) | PC / compute-box | Run folder with a live `progress.json` (generation, best-so-far, ETA, failures so far); resumable | `evo_search.py`, `evo_screen.py` budget model |
| 5. Verify finalists | `fdmgen verify run/ --top 3` | PC (Orca) | Per-candidate actual slice, PROC-001, toolpath rule report, 3D FE receipt | `package_part.py`, `gpu_demo_slice.py`, `verify_mixed_plate.py`, `audit_ef_bonds.py` |
| 6. Review | `fdmgen review run/cand-XXXX` | PC | `review.html` + PNG panels (section 5.4) | `render_print_control.py`, `verify_mixed_plate.preview` |
| 7. Print coupons | existing `p1s-print` + `print-log.py add/update` | printer | Print-log entry tied to slice hash | existing |
| 8. Calibrate | `fdmgen calibrate --from print-log P-00NN` | PC | New calibration file version; dependent results flagged STALE | new |
| 9. Publish | `fdmgen writeup run/cand-XXXX` | PC | Markdown page draft for the site (section 5.5) | Gridline pages |

### 5.2 What "ranked orientations" should look like

| Rank | Print up (design frame) | Support area mm² (M) / roads (T) | Bed contact mm² | Max interlayer tension / allowable | Warp L mm (ASA) | Height mm / est. time | Hard fails | Provisional rules in play |
|---|---|---|---|---|---|---|---|---|
| 1 | +Z | 0 / 0 | 2,950 | 0.21 | 214 → brim | 24 / 3h10 | none | STR-001, WARP-001 |
| 2 | … | … | … | … | … | … | … | … |

These numbers are illustrative. Rules for this table:
- Ranking is Pareto, not a weighted sum. Dominated rows are greyed, not hidden.
- Each penalty cell links to the rule card and the region.
- The D9 splice-ring paragraph (`DESIGN.md:262-269`) is exactly this table written as prose. The tool should
  produce the table and keep a free-text "designer decision" field next to it.

### 5.3 Where confusion and false confidence creep in (and the guard for each)

| # | Trap | Real example in the repos | Guard |
|---|---|---|---|
| T1 | Angle convention flip | `overhang-threshold-test/build.py` names wedges `wedge-30deg`…`55deg` with `run=15*tan(ang)` as the **vertical** drop, so `wedge-30deg` is 30° from horizontal (60° from vertical). The builder comment reads the result correctly, but the file names say the opposite | D3: one convention, both printed, unit test on a known wedge |
| T2 | Frame offsets | P1S `extruder_offset 0x2` shifted the parsed material −2 mm until fixed (`EVOLUTION.md`) | Frame transforms recorded in every receipt; round-trip test design→plate→design |
| T3 | Compensation double counting or silent compensation | ASA profile `filament_shrink 99.46%` vs "No global ASA shrink correction is applied" (TOLERANCES/README); EF compensation plus a CAD chamfer | `compensation:` block in the calibration file; lint warns when geometry and profile both own an edge or interface |
| T4 | Slicer behaviour treated as printer capability | Overhang test is slice-only | Tier S vs U shown next to the verdict |
| T5 | Sampled checks miss features | `check_printability.py` uses `Z_SAMPLE_COUNT = 10` | Checks run per layer or state their sampling; a check that could not run is `NOT_CHECKED`, never PASS |
| T6 | Untiered defaults that disagree | Bridge 15 mm (SKILL.md, PETG) vs 20 mm (script default) | CAL-001 lint |
| T7 | Effective settings drift / unrecovered slices | G PETG project "two walls; exact submitted slice not recovered" (`RECOVERED-PRINTS.md`) | PROC-001 plus slice hash in `print-log` |
| T8 | Lost modifier roles | STEP stores no roles; Orca import can drop modifier settings | Post-slice role check (exists in spool-rack) is mandatory |
| T9 | Optimiser exploits the proxy | "Cheap stress trends were unreliable" (`EVOLUTION.md`); B failed both solves | Finalists always get actual slice + 3D; proxy and verified values side by side; failed candidates stay in the ledger |
| T10 | Silent automatic geometry changes | `selfsupport()` adds material without a report (`dress()` does report) | Every `repair` emits a delta (volume, bbox, rule that caused it) and air/keep-out re-check, as D9 does for airways |
| T11 | Bead-count band edges | D9 key leaf 1.2 mm = 2.86w | WALL-002 |
| T12 | Z quantisation | `TONGUE_H = 12.7` = 63.5 layers at 0.2 | ZQ-001 reports the as-sliced height |
| T13 | Global "non-strict" passes | `verify_plates.py` sets `strict: False` for every object | Support policy per region from `problem.yaml`; the plate verdict lists which objects were allowed support and where |
| T14 | Mixed-fidelity Pareto plots | Screening and 3D results on one chart | Marker shape = fidelity; no ranking across fidelities |
| T15 | Generic profile presented as calibration | G2: "Generic printer/filament profiles are not calibration" | Calibration binding; "uncalibrated" banner |
| T16 | Fit transfers across orientation/material | Round vs octagon pins, PETG vs ASA results differ | Fit classes keyed by orientation + profile hash |
| T17 | Site write-up implies "optimised = stronger/qualified" | (risk) | Write-up template with a fixed "establishes / does not establish" block and the verdict ladder rung |

### 5.4 Reviewing a result (what the designer looks at, in order)
1. **Verdict strip.** Highest rung reached, the count of PROVISIONAL rules, overrides with reasons, STALE
   calibrations. Any red here stops the review.
2. **Print-frame view** with the bed, build arrow, overhang heat map (α), support roads (T) and bridge roads
   coloured by span.
3. **Bead map.** Per-layer bead counts from the actual slice, band-edge regions flagged, helper (modifier) outlines.
4. **Interlayer map.** σ_zz⁺ / allowable, labelled PROVISIONAL while z_fraction is H.
5. **Fits table.** Each interface, its fit class, compensation owner and calibration status.
6. **Diff against the previous candidate or revision.** Volume moved, rules newly passing or failing, and "what
   changed and why" (mutation record, as the evolution ledger already stores).
7. **Iterate** by editing the builder or `problem.yaml`, never the generated YAML or result folder. The run records
   its inputs' hashes, so the diff is trustworthy.

Error messages follow the OVH-001 template: what happened, where (print-frame coordinates and part name), why it
matters, and two or three concrete fixes, one of which is always "declare an exception with a reason".

### 5.5 Website write-up template (Gridline, honest-limits house style)
1. **Headline result** in one sentence, with the rung reached, e.g. "Toolpath-verified, 3D-screened; not printed".
2. **The problem**: interfaces, keep-outs and loads diagram, and the orientation with the reason.
3. **What the optimiser could change** and what it could not (frozen interfaces, process rules).
4. **Pareto chart**, fidelity encoded; finalists labelled; failures counted.
5. **Chosen candidate**: section images, actual toolpath sections, spent extrusion (Orca grams and cm³), helper
   modifiers.
6. **Printability report**: the rule table with verdict, level reached and tier, PROVISIONAL rules highlighted.
7. **What this establishes / does not establish**: a fixed block, as in the existing spool-rack pages.
8. **Downloads**: body STEP, helper STEPs, model-only 3MF with roles, sliced 3MF (engineering evidence, not
   ready-to-print), `problem.yaml`, calibration file, SHA256SUMS.
9. **Reproduce**: three commands.

---

## 6. What "good enough to publish as the documented constraint set" means

**Scope statement (v1.0):** single-nozzle FDM, 0.4 mm, enclosed CoreXY class (P1S as the reference machine), PETG and
ASA, OrcaSlicer 2.4.x, planar layers. Out of scope: multi-material, non-planar, resin and powder, and long-term
creep/fatigue allowables.

**Release criteria:**
1. Every rule has an ID, definition, parameters with units, check levels, enforcement mode, a message template and
   sources.
2. Each rule has checkers at two or more levels with **golden-geometry tests**: a small STEP per rule with known
   verdicts, including near-threshold cases on both sides. The calibration coupons are those same STEP files.
3. For both PETG and ASA on the P1S, every rule's binding value is tier U or explicitly marked "slicer-defined" (tier
   S, where the slicer *is* the behaviour, e.g. build volume). There are no H values in a 1.0 release.
4. A conformance suite: `fdmgen selftest` slices the coupon plate and checks that every T-level checker reproduces the
   expected verdicts on the current Orca. This catches Orca behaviour changes between versions.
5. A slicer-key mapping table (Orca ↔ Prusa ↔ Bambu Studio, Cura where possible), so other users can bind the
   rules to their own profiles.

**Versioning:**
- `catalog_version` uses semver for *rule semantics*. Major: a rule's meaning or check changes. Minor: a new rule.
  Patch: wording or sources.
- Calibration files are versioned **separately**, by date and bound profile hashes. Changing a value never bumps the
  catalog version.
- Results pin both versions. A result made under a superseded calibration is shown as STALE but is never rewritten.
  This matches the repos' "historical records remain unchanged" rule.

**Reuse by others:**
- Publish the JSON Schema for `rules.yaml`, `calibration.yaml` and `problem.yaml`.
- Publish the coupon plate and a one-afternoon "calibrate your printer" guide.
- Others contribute calibration files for their machines. The catalog stays the same.
- License: data and text under CC-BY-4.0, checker code under a permissive license (to match the user's repos;
  confirm with the user).
- Every rule cites where it came from, including "the user's own print P-0012". That provenance chain is the
  difference from the vendor tables.

---

## 7. Open questions for cross-review

1. **Sauron:** can OVH-002's `k_step` form be implemented as a layer-aligned anisotropic stencil on the 0.2 mm grid,
   or should angles other than 45° be handled by changing h? Which interlayer failure criterion should STR-001 use
   (max-stress on σ_zz/τ_z or Tsai-Wu)?
2. **Gandalf:** should the catalog be its own repo (reusable by others) with `fdm-gen` depending on it? Should
   `emit_problem()` live in the builders or in a shared library both the 5680 and spool-rack repos import?
3. **Legolas:** cost of per-layer M checks (every 0.2 mm) on ~200 mm parts, and of T-level parsing for every
   finalist. Is the existing `plastic_shape` cache fast enough for 3 finalists per generation?
4. **All:** which 3–5 rules must be *inside* the optimiser on day one? My proposal: OVH-001 (filter), WALL-001/GAP-001
   (length scale), frozen interfaces and keep-outs, and STR-001 as a penalty. Everything else is a post-check.
5. **User:** the first physical calibration plate. Proposed contents: overhang ladder 35–60° in 5° steps, bridge
   ladder 6–24 mm, gap ladder 1–3w, horizontal and vertical hole/peg ladder at Ø4 and Ø8, a warp bar 150 mm, and
   pillar ladders. One plate per material.

---

## 8. Sources

User repos (read-only): files cited inline above.

External:
- [OrcaSlicer support settings (threshold angle definition)](https://www.orcaslicer.com/wiki/print_settings/support/support_settings_support)
- [OrcaSlicer overhang settings](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_overhangs)
- [OrcaSlicer wall generator (min_bead_width, min_feature_size)](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_wall_generator)
- [OrcaSlicer material basic information (filament_shrink)](https://www.orcaslicer.com/wiki/material_settings/filament/material_basic_information)
- [OrcaSlicer filament shrinkage vs XY compensation discussion](https://github.com/SoftFever/OrcaSlicer/discussions/541)
- [OrcaSlicer material cooling (slow_down_layer_time)](https://www.orcaslicer.com/wiki/material_settings/cooling/material_cooling)
- [OrcaSlicer issue #12966: no max bridge length for normal supports](https://github.com/OrcaSlicer/OrcaSlicer/issues/12966)
- [Prusa: elephant foot compensation](https://help.prusa3d.com/article/elephant-foot-compensation_114487)
- [Prusa: Arachne perimeter generator](https://help.prusa3d.com/article/arachne-perimeter-generator_352769)
- [Hubs: DFM tips for thin walls](https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/)
- [nophead: Polyholes](https://hydraraptor.blogspot.com/2011/02/polyholes.html)
- [Bambu Lab: ASA guide](https://bambulab.com/en-us/filament/asa)
- [ISO/ASTM 52910:2018](https://www.iso.org/standard/67289.html)
- [Adam & Zimmer 2014, Design for AM: element transitions and aggregated structures](https://ris.uni-paderborn.de/record/22384)
- [Langelaar 2017, An AM filter for topology optimization of print-ready designs](https://link.springer.com/content/pdf/10.1007/s00158-016-1522-2.pdf)
- [Gaynor & Guest 2016, Topology optimization considering overhang constraints](https://link.springer.com/article/10.1007/s00158-016-1551-x)
- [Overhang constraint with overhang length relaxation (2021)](https://link.springer.com/article/10.1007/s11431-021-1996-y)
- [Mirzendehdel, Rankouhi & Suresh 2018, Strength-based TO for anisotropic parts](https://par.nsf.gov/servlets/purl/10057716)
- [Umetani & Schmidt 2013, Cross-sectional structural analysis for 3D printing optimization](https://www.research.autodesk.com/publications/cross-sectional-structural-analysis-for-3d-printing-optimization/)
- [Telea & Jalba 2011, Voxel-based assessment of printability of 3D shapes](https://link.springer.com/chapter/10.1007/978-3-642-21569-8_34)
- [Wang, Xi & Jin 2007, A model research for prototype warp deformation in the FDM process](https://link.springer.com/article/10.1007/s00170-006-0556-9)
- [Ahn et al. 2002, Anisotropic material properties of FDM ABS](https://iss.mech.utah.edu/wp-content/uploads/sites/103/2012/10/Ahn-Anisotropic_material-2002.pdf)
- [Will it print: a manufacturability toolbox for 3D printing](https://pmc.ncbi.nlm.nih.gov/articles/PMC8555737/)
- [3MF structure in Bambu Studio / Orca (model_settings.config), secondary source](https://printago.io/blog/3mf-file-format)
