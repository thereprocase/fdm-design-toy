# Frodo on Gandalf (architecture and roadmap)

## 1. Verdict

This is the right skeleton. Port instead of import, two FEM roles, slicer-as-toolpath-generator, a print-frame grid,
receipts and a phased roadmap with acceptance tests all match how the user already works. But the first
`problem.yaml` gets the bracket loads wrong. The rule schema has nowhere to say how far a value can be trusted. And
the P1 "printable" gate will fail on the user's own measured Orca behaviour unless an overhang margin is designed in.
None of this needs a redesign; it needs corrections before P0 starts.

## 2. Findings

1. **[critical] §3.1 problem.yaml: the bracket loads are wrong.** It applies `resultant_N: [0,-58.86,0]` to each
   seat, an equal vertical split. The repo's reference split is not equal and not vertical. From
   `spool-wall-rack/analysis/rev-g2/adaptive-validation/g-h0p2-interfaces.json`:
   - rear seat `target_force_N = [-31.29, -75.12, 0]`
   - front seat `target_force_N = [+31.29, -42.60, 0]`
   - total 117.72 N, with "zero moment about each dowel axis".

   An optimiser fed 58.86/58.86 will move material to the wrong seat. P1-E ("same truth pipeline … same material
   card" against E13/G/E+F) would then compare different load cases without anyone noticing. That is false confidence
   in its purest form. **Requested change:** generate the load block from the hashed interfaces JSON (same pattern as
   the `provenance:` pins), not by hand, and add a lint that compares the resultant and split against the pinned
   source.
2. **[warning] §3.1 supports.** Only `screw_upper_land` is fixed. The repo model uses rigid washer axial restraint
   *and* rigid bore lateral restraint at both mounting holes, plus unilateral wall contact (`g-h0p2-interfaces.json`
   `model`). Missing the lower fixing changes the load path. **Change:** list both fixings and copy the restraint
   model string, so the idealisation is visible.
3. **[critical] P1-D "0 support roads" vs the user's measured Orca threshold.** §3.4 and P1 both use a 45° overhang.
   The user's `D9-P5/overhang-threshold-test` shows Orca with `support_threshold_angle = 45` **generated support on
   the exactly-45° wedge** (2,421 support segments) and none at 55°. A 1-cell AM filter on cubic 0.2 mm voxels
   produces surfaces at exactly 45°, so the P1 leader will very likely fail P1-D. The fix is a deliberate margin,
   which `bore_td()` already uses ("40° from vertical, clear of the slicer's 45° threshold"). Pick one of:
   - design to ≥ 50° from horizontal;
   - lower the slicer threshold and calibrate print quality in the 40–45° band;
   - run a margin repair pass after extraction.

   Record the choice in the catalog (my OVH-001) and in the P1-D test text.
4. **[warning] §3.4 rule example mixes angle conventions.** The statement says "flatter than theta from the build
   plane", the parameter is `theta_deg_from_vertical`, and the evidence says "support at 45 deg from vertical, none
   at 35". The user's test files are themselves named in the inverted convention: `wedge-30deg` is 30° from
   **horizontal** (frodo.md trap T1). At 45 the two conventions coincide, so the bug stays hidden until someone uses
   50 or 40. Sauron (§4.6) and I both propose `slope_from_horizontal`, matching Orca's `support_threshold_angle`.
   **Change:** adopt it in the schema; parameters carry the convention in the name; reports print both.
5. **[warning] §3.4 rule schema has no way to grade evidence or catch stale calibration.** `status:
   CALIBRATED_ONE_PROFILE` is a label on the whole rule. The overhang test is *slice* evidence (what Orca will
   generate), not *print* evidence (what the P1S prints well), yet the label reads "calibrated". The schema needs:
   - per-value evidence tier (own print / slicer / vendor / literature / heuristic);
   - a binding to profile hashes, so a value goes STALE when the profile changes;
   - a `compensation` owner. The PolyLite ASA profile applies `filament_shrink = 99.46%` while the 5680 docs say "no
     global ASA shrink correction", and the user's pin fits were learned with that scaling on;
   - a message template;
   - `NOT_CHECKED` as an explicit outcome distinct from pass.

   frodo.md §4.1–4.2 has a concrete form; please merge rather than invent a third.
6. **[warning] §3.2 `support: {allowed: false}` is global.** Real parts need per-region policy. D9 says "Hidden
   accessible support is acceptable" for some regions, and P-0004 shows support debris on a fit face looked like a
   0.6 mm geometry error. Meanwhile `verify_plates.py` marks every object non-strict, which hides where support went.
   **Change:** `support_policy: {default, regions: [{region_id, allowed, access, reason}]}` and a toolpath check that
   support never touches `role: interface` regions.
7. **[warning] §3.2 vs Sauron D2/§4.8: sparse infill palette.** `modifiers: {allowed_densities: [0.15, 0.4, 1.0],
   pattern: gyroid}` and the material card's `sparse_infill` power law disagree with Sauron's "sparse infill = 0
   credit". Under Sauron's card the optimiser would never pick 15/40%. Under yours it would, using an uncalibrated
   law. Note that 0% base infill is a spool-rack rule only: D9-P5 plates run 40% gyroid with 5 walls
   (`prepare_and_slice.py`). **Change:** make "sparse infill credited?" an explicit per-problem choice with its own
   card status, and default to Sauron's zero credit until coupons exist.
8. **[critical] §4 S4 / P1-C "keep_in solids booleaned back exactly" ignores orientation.** Frozen interfaces are
   printable in the orientation they were designed for, not necessarily in every swept orientation. A Ø26 rod seat or
   an 8.4 mm pin bore whose axis ends up in the layer plane needs a teardrop crest pointing up (`bore_td()`), and the
   crest direction depends on the build direction. The AM filter is not allowed to touch keep-ins, so nothing fixes
   them. **Change:** interfaces carry orientation-dependent print variants (e.g. `bore: {teardrop: auto}`), and
   S1's prefilter runs the interface printability rules (HOLE-001, OVH-001 on keep-in faces, SUP-001) per candidate
   orientation before any optimisation is spent on it.
9. **[warning] §1.1 / finding 1: arc fitting is not hypothetical.**
   `5680-dock/desk-dock/D9-P5/profiles/process.json` has `"enable_arc_fitting": "1"`. Any fdm-gen run that reuses
   the D9 profiles produces G2/G3 today. Correction on "breaks silently": `plastic_shape.main()` asserts footer
   extrusion agreement < 0.1% (line 380). Dropped arc extrusion should trip that, but `read_paths()` called as a
   library (as fdm-gen would) has no such guard. **Change:** the canonical parser asserts the footer check
   internally, and PROC-001 records `enable_arc_fitting` among checked keys.
10. **[note] P0-A tolerance.** The repo holds two credited-E values for the same slice: 70,979.802 mm³
    (`shape-verification.json`) and 70,979.852 mm³ (`orca-replay.json`). `MESHING-NOTES.md` warns "these values are
    not interchangeable". At ≤ 1e-6 relative the choice matters. **Change:** pin the exact JSON file and key in P0-A.
11. **[warning] P1-B known answer relies on a ratio the data doesn't support.** P1-B expects flat-on-side to win
    with E3/E1 ≤ 0.7. Bambu TDS give E_Z/E_XY = 0.85–0.92 (Sauron §2.2; I verified the ASA and PETG Basic sheets).
    Sauron shows directional stiffness varies only ~15% at those ratios. A compliance-only P1 will show a small
    orientation effect, dominated by overhang-filter side effects. **Change:** make P1-B use the inter-layer strength
    index (Sauron §3.2) or massing, which carry the real orientation signal. Keep 0.7 only as a labelled stress test.
12. **[warning] Orientation representation conflicts with Legolas D3.** You (and Sauron D4) re-voxelise per
    orientation, which is what the printability rules need: layers on grid planes for OVH/BRG/SKIN/ZQ. Legolas
    proposes a fixed grid plus rotated tensor and "never re-mesh". The merged plan must state that the fixed-grid route
    is **analysis/screening only** (orientation scoring of an existing design, Legolas's "project #1" mode). The
    design TO re-voxelises.
13. **[warning] Design-grid resolution is undecided across reports, and the rules depend on it.** You say "0.6 mm or
    coarser" (R3), Sauron says 0.2 mm (D4), Legolas says ≥ 0.8 mm (D4).
    - At ≥ 0.6 mm the optimiser cannot enforce the 2w = 0.84 mm minimum feature or gap, cannot see 1.6 mm skins, and
      its overhang stencil spans 3–4 layers.
    - **Change:** add a table to §4 listing which catalog rules are enforced *in* the design solve at each grid tier,
      and which are only checked after S4/S5. Then nobody reads "the optimiser respected printability" when it only
      respected two rules.
14. **[note] §3.5 status enum ends at `TRUTH_SOLVED`.** The user's own vocabulary goes further
    (`PHYSICAL_PRINT_UNQUALIFIED`) and the print log closes the loop. **Change:** extend to the full ladder
    (`GEOMETRY → TOOLPATH → SCREEN → FE_3D → COUPON → PRINTED → QUALIFIED`) and link candidate IDs to `print-log.py`
    entries, so a printed result can update calibration.
15. **[note] P4 acceptance ("a person who did not write the code runs a new part … using only the docs") is the
    right bar.** It needs an earlier proxy: P1 should already include `fdmgen lint` with plain-language errors
    (what happened, where in print-frame coordinates, how to fix). Error UX is cheap early and expensive late.
16. **[note] Material card example** uses `nozzle_C: 250`. The user's PETG starter profile runs 255°C and ASA
    PolyLite 260°C (`D9-P5/profiles/`). Generate `process_binding` from the profile hash, not by hand, for the same
    reason as finding 1.

## 3. What the merged plan must keep

- **Port with provenance headers and parity tests; never `sys.path` into spool-rack** (§5, decision 1).
- **Two FEM roles with different invariants**, truth refusing `E_min > 0` (decision 2, R6). This is the strongest
  guard against optimiser numbers leaking into published claims.
- **The slicer makes toolpaths; output = body + modifiers + per-region settings; truth reads real G-code**
  (decision 3). That is how the user already prints the spool rack.
- **One `Rotation` object deriving both pose and build vector** (finding 3, `PRINT_Z` vs `pose()`).
- **P0-D modifier capability spike** (Q3). If Orca modifiers can't override `wall_loops`/skins via 3MF, massing
  output shrinks to infill density, and everyone needs to know that before P2.
- **Fidelity and scope tags on every metric** (§3.5) and "publish the miss" in P2-C/P3-B.
- **Hardware honesty**: runs stay outside Claude background shells, nothing touches compute-box until its owner is
  told, and Q1 (which machine has the 3080 Ti) gets asked.
- The **prior-art gap table** (§2) is the clearest statement of why this project is worth doing. Keep it as the
  opening of the public write-up.
