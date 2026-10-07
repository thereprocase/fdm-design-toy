# Frodo on Sauron (mechanics and mathematics)

## 1. Verdict

This is the most useful report for a collaborator's actual question. It shows, with numbers, that orientation matters through
inter-layer *strength*, *printability* and *massing*, not through elastic stiffness. It also gives closed forms for
the massing shell and the leaning-wall overlap, and a falsifiable test list. The weak spots are on my side of the
fence: overhang defaults without a margin, vendor bridge and overhang figures quoted as if they were limits,
material cards for grades the user doesn't print, and an orientation sweep that ignores bed and interface
printability.

## 2. Findings

1. **[critical] §4.6 / D6: a 45° default with no margin fails the user's own slicer test.** The AM filter with a
   1-cell reach on 0.2 mm cubes yields surfaces at exactly 45°. The user's
   `D9-P5/overhang-threshold-test/toolpath-verification.json` shows Orca at `support_threshold_angle = 45`
   **supporting the exactly-45° wedge** (2,421 support segments) and leaving 55° alone. So "Orca's slice is the final
   judge" will judge the TO output as needing support along every grid-aligned 45° face.
   - Your diagonal analysis makes it worse for the 3×3 stencil: 54.7° from vertical is 35.3° from horizontal, deep
     in support territory.
   - The 5-point cross is conservative on diagonals but still exactly 45° on axes.

   **Requested change:** state the margin explicitly. Options:
   - an anisotropic voxel aspect (dz/dx > 1), which breaks layer alignment, so probably not;
   - a 2-cells-in-XY-per-3-layers stencil (≈ 56° from horizontal);
   - a lowered Orca threshold with a printed 40–45° coupon;
   - a post-extraction margin repair.

   Then add an invariant test, "I13b: Orca adds zero support roads to the AM-filter output of the I13 cone at every
   azimuth".
2. **[warning] §4.6 bridging and overhang figures are vendor marketing, not limits.** "Bambu TDS gives ~30 mm for
   PETG and ~40 mm for ASA [v]". I confirmed the sheets say this, next to "Max Overhang Angle ~ 70°". They are for
   Bambu grades, Bambu profiles and (for ASA) a 45–60°C chamber that the P1S does not actively hold. They are not the
   user's evidence:
   - The Rev F ASA design used an 18 mm internal bridge, which its own guide calls "a geometry audit, not … a print
     test".
   - General guidance is about 10 mm for exposed bridges.

   My catalog (BRG-001) has 10 mm external / 18–20 mm internal, marked provisional. **Contradiction to resolve:**
   neither number is calibrated. **Change:** label the TDS figures tier V and do not use them as optimiser defaults;
   both of us point to a bridge-ladder coupon (6–40 mm) on the user's profile.
3. **[warning] §2.2–2.3: T0 cards are for grades the user is not printing.** The print log
   (`5680-dock/docs/prints/print-log.json`) shows the production parts are **Polymaker PolyLite ASA with the
   "Repro … Calibrated" profile** (260°C, `filament_flow_ratio 0.93`, `filament_shrink 99.46%`) and "PETG grey"
   with a generic/Polymaker PETG starter profile. Your table includes Polymaker data from the spool-rack repo, but the
   T0 card is built from Bambu PETG HF.
   - PolyLite ASA's own sheet gives Z/XY strength 0.73, vs 0.84 for Bambu ASA, so the grade changes the very ratio
     the orientation decision rests on.

   That answers your open question 2 in part: **build T0 from PolyLite ASA first**, and record the PETG grade as
   unknown until the user confirms it.
4. **[warning] §4.7: the orientation sweep ignores bed contact and interface printability.** A Fibonacci sweep of ~200
   directions includes many with no flat bed face, a point contact or a sliver bed island, and many where frozen
   keep-in interfaces become unprintable. A Ø8.4 bore or Ø26 rod seat whose axis lands in the layer plane needs a
   teardrop crest aligned with *that* build direction (`bore_td()`), and keep-ins are exempt from the AM filter. The
   traction-map prescreen can rank a direction first that the catalog rejects outright.
   - The user already makes this tradeoff in prose: D9 `DESIGN.md:262-269` rejects a vertical splice-ring pose for
     89 mm² bed contact *and* load across layers.

   **Change:** the prescreen score is a vector, not a scalar: inter-layer index, support area estimate, bed contact
   or stability, and interface printability (with teardrop variants generated per d). Pareto-filter it.
5. **[note] D8: "spin psi only at re-analysis" understates spin.** Spin matters for bed fit and the P1S exclusion
   zone (18×28 mm front-left; `machine.json`). The spool bracket envelope I measured is 207.5 × 233.5 × 24 mm
   (`print-controls/ef-core-asa-4w-1p6/body-only.stl`), which is close to the 256 mm bed. Spin also matters for
   warping risk (long footprint diagonal in ASA) and seam placement. These are feasibility gates, not a later polish.
   **Change:** run the bed and exclusion check as part of candidate generation.
6. **[note] §2.7 f(β) and my OVH-002 are the same quantity. Let's share one parameter.** Your leaning-wall overlap
   is `f = 1 − h·tanβ/w`. My overhang step rule is `h·tanβ ≤ k·w`, so `k = 1 − f`. I propose the catalog parameter
   be **`overlap_min = f_min`**, used both for printability (OVH-002) and as your bond-fraction hypothesis
   g(f) (C5 coupon). One coupon then calibrates both. I accept your Q7: **adopt α_s from horizontal**, and the min
   length pair 2w (XY) / n_t·h (Z).
7. **[note] §4.4 shell thickness agrees with mine.** Your `t(α) = max(n_w·w·sin α, n_t·h·cos α)` and my
   SHELL-001 (written with the normal angle) are the same formula; your t_min = 0.64 mm at 50° checks out. Use the
   *actual* per-loop widths: the D9 profile has outer 0.42, inner 0.45, so `n_w·w` = 0.42 + 0.45·(n_w − 1), not
   n_w × 0.42. The difference is small but it is exactly the kind of thing that makes the emulator disagree with
   Orca by a cell.
8. **[warning] D2 / §4.8: "sparse infill = 0 credit per house rule" is a spool-rack rule, not a user-wide one.**
   D9-P5's main plates run 5 walls + 40% gyroid PETG (`prepare_and_slice.py`). Your Q4 should be answered "yes,
   sometimes". Gandalf's process spec already offers 15/40% modifiers (contradiction noted in my Gandalf review).
   **Change:** treat infill credit as an explicit per-problem switch with its own card status, and say in every
   report which one was used.
9. **[note] §5.1 omission numbers are crop numbers.** "Omits 17.1/8.4/4.3% at 0.4/0.2/0.1 mm" are from the
   GPU-VALIDATION **crop**. `ADAPTIVE-MESH.md` explicitly says crop losses "must not be substituted for these
   whole-part measurements" (whole-G: 8.02/16.38/33.09% at 0.2/0.4/0.8 mm, as Legolas quotes). **Change:** label it
   as crop, or quote the whole-part figures.
10. **[warning] §4.3 E_min = 1e-6 vs Legolas D5 (E_min ≥ 1e-3).** These differ by three orders of magnitude, and
    Legolas measured a 16 → 106 iteration jump at 1e-3 contrast. From the user's side the risk is a design that
    leans on grey or void stiffness. Your I19 (TO vs zero-ersatz gap blocks the candidate) is the right guard.
    **Change:** agree a value with Legolas, and make the I19 threshold a number before the first result is shown.
11. **[note] §6 C2 Z-tension coupon.** "Tall thin prints wobble" is my PILL-001 and COOL-001 (small sections hit
    the minimum layer time: 3 s ASA, 12 s PETG in the user's profiles). **Change:** print C2 on a plate with
    companion parts, or as a block that is machined, and record layer times from the G-code. Otherwise the weld
    history of the coupon will not match that of a part, which undermines the process-lock principle you state.
12. **[note] §6 open question 1 (testing machine) should be the first question to the user.** The whole T1 tier,
    and therefore whether anything beyond rankings can ever be published, depends on it.

## 3. What the merged plan must keep

- **The headline finding:** stiffness anisotropy is small for PETG/ASA (about 15% directional), while strength
  anisotropy and massing are large. This should shape the MVP objective and the P1-B known-answer test.
- **The closed-form massing shell `t(α)`** and the directional-coating formulation (D5): the "orientation drives
  massing" core a collaborator asked for, mapped one-to-one onto the user's existing Orca controls.
- **Mandel storage with an explicit `gpu_hex` permutation**, and the measured bug magnitudes. Those numbers make the
  invariant tests feel mandatory rather than academic.
- **The degree-1 two-mode failure index** with only three strengths, and "one 45° off-axis coupon is worth more than
  any other single test".
- **D9: nothing reported from the TO model;** zero-ersatz re-analysis on the slice, with the gap reported.
- **The tiered confidence table (T0/T1/T2)** and its "what may be claimed" column. It should be merged with my
  evidence tiers, so the catalog and material cards use one vocabulary.
- **The invariant list (§7)** as the gate before any result is shown to anyone, plus the `[v]/[m]` citation honesty.
