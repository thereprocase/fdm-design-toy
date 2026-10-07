# Gandalf on Sauron (round 2 cross-review)

Reviewed: `D:\Code\Models\fdm-gen\research\sauron.md` (810 lines), plus `scratch\sauron\` listing. Spot-checked
against `spool-wall-rack` (`gpu_hex.py`, `plastic_shape.py`, `designs/closed-wall-e6/material-reference-data.json`)
and against Legolas's measurements. Angle: architecture, integration, roadmap feasibility.

## 1. Verdict

This is the strongest of the three reports on substance, and it changes the plan. It shows that compliance is
nearly blind to build orientation for PETG/ASA (15% directional modulus spread), so orientation has to act through
inter-layer strength, overhang and massing. That finding invalidates part of my own P1 test (finding 2). The main
problem is feasibility: **D4 (TO grid at 0.2 mm) is not affordable** on the measured hardware, and the v1 formulation
stacks too many advanced pieces into one first release. Both are fixable by staging.

## 2. Findings

1. **[critical] §4.1 / D4: the 0.2 mm TO grid contradicts Legolas's measurements.** Legolas measured an 11.25 M-cell
   (0.4 mm) bracket box as the practical ceiling on the 11.5 GB laptop GPU, with 0.2 mm (90 M box cells, 270 M DOF)
   "does not fit" and 5-10 h per orientation on CPU (legolas.md §3, §4). D4 also implies the robust formulation's three
   solves per iteration (§4.5, §4.7) times K load cases, which nobody has costed. As written, D4 makes an orientation
   sweep impossible.
   *Requested change:* restate D4 as multi-resolution. Use 1.6/0.8 mm for screening, without coating. Run the
   directional coating only at ≤ 0.4 mm on a masked domain for the leaders. 0.2 mm is for re-analysis only. Then state
   explicitly what the coating can represent at 0.4 mm: 0.84 mm wall shells are about 2 cells, so they are crude. If
   that is not good enough, propose a sub-cell alternative, such as an analytic shell-fraction field from XY and Z
   distance transforms, instead of resolved erosion.

2. **[critical] §0.1 / §2.5 conflicts with Gandalf §6 P1-B; Sauron is right, and the merged plan must follow him.**
   My P1-B test assumed E3/E1 ≤ 0.7 and expected compliance to rank orientations. Sauron's TDS table (§2.2) puts
   E_Z/E_XY at 0.85-0.92, giving about 15% directional variation. Under those numbers, a compliance-only MVP would
   produce a weak or null orientation result. Legolas's sweep design (S0/S1 rank orientations by compliance) has the
   same problem.
   *Requested change:* none to Sauron's text. Add one sentence to §4.7 saying that orientation **ranking in v1** uses
   the inter-layer index F_L and the overhang/support metric, not compliance, so the other reports can cite it.

3. **[warning] §4.4 + §4.6 + §3.3 + §4.5 + §4.7: v1 is too large for a first build.** Problem v1 combines minimax
   compliance, an aggregated stress constraint with qp-relaxation, a robust three-field formulation, directional
   coating erosions, an AM filter on the printed-material field, and MMA. Every block needs the finite-difference and
   Taylor tests of I14. That is a research programme. The roadmap has to land something that works end to end first.
   *Requested change:* split into **v1a** and **v1b**.
   - **v1a** (my P1): SIMP compliance + density filter + AM filter + volume. F_L is evaluated **post hoc** for ranking
     only, with no gradient.
   - **v1b** (P2/P3): coating, robust formulation, aggregated F_L constraint.

   Name which invariants gate v1a. I1-I13 and I18-I19 appear needed; I14-I17 can wait for v1b.

4. **[warning] D2 vs Gandalf §3.3: Sauron's simpler material model is better, and it simplifies the solver.**
   Sauron uses a homogenised TI card about printer Z at the design stage, and per-element orthotropic properties only
   at re-analysis. I proposed bead-class orthotropy with wall-tangent bins at the design stage. With TI and a
   print-frame grid, **every design cell has the same rotated C**. The design solver can therefore keep `gpu_hex`'s
   single shared `Ke` and add only a per-cell SIMP scale. This is a much smaller change than the `ke` stack I proposed,
   which is then needed only in the truth solver (§5.4).
   *Requested change:* say this architectural consequence explicitly in §5.4. I will adopt D2 in round 3.

5. **[warning] §1 frames (D, P, M, G) vs Gandalf §3 (part/installed/print/bed) vs Frodo §2.1 (design/print/plate).**
   Three vocabularies describe one concept, and frame confusion is the repos' best-documented bug class (P1S `0x2`
   offset, `PRINT_Z`/`pose()`). Sauron's `R_TO_FROM` naming and the explicit d = -e_z singular case are the best of the
   three.
   *Requested change:* add the **installed** frame I (spool-rack's `model_to_installed`, used by
   INTERFACE-CONTRACT coordinates) and Frodo's **plate** frame (Orca bed, before the extruder offset). Distinguish
   *plate* (after placement) from G (after the nozzle offset). One table should then be used by all reports.

6. **[warning] D10 tiers (T0/T1/T2) vs Frodo §2.3 (U/S/V/L/H) vs Gandalf §3.3 (ASSUMED/.../VALIDATED).**
   *Requested change:* keep Sauron's tiers as the **card-level** status and Frodo's U/S/V/L/H as the **per-value**
   provenance tag. Mine should be dropped. Say so in D10 so the merged schema has one vocabulary.

7. **[warning] §2.2 / D2 "sparse infill = 0 credit per house rule" is presented as system-wide.** This is a
   spool-rack G2 policy (`G2-BRIEF.md`), not a property of the tool. a collaborator's parts and most user parts will use sparse
   infill. Frodo correctly treats it as a `rule_overrides` entry in `problem.yaml` (frodo.md §4.3).
   *Requested change:* reword D2/D5 as "default for problems that declare 0% base infill". Keep §4.8 as the declared
   path when infill is enabled, rather than as an afterthought.

8. **[warning] §4.6: the 45° stencil default vs Frodo's 50° design target.** Frodo (OVH-001) sets α ≥ 50° from
   horizontal as the design value, because the wedge test at exactly 45° *did* receive support
   (`overhang-threshold-test/toolpath-verification.json`: `wedge-45deg` support_segments 2421; I verified this). A
   one-cell stencil on cubic voxels gives exactly 45° (§4.6), so it cannot enforce 50°.
   *Requested change:* say how 50° is met. Options are a non-cubic voxel (dx/dz = tan 40° ≈ 0.84), a 2-cell
   anisotropic stencil, or a 45° filter plus an M-level 50° post-check. Then agree the choice with Frodo. My
   preference is a 45° filter in v1a plus the M/T checks, because Orca is the final judge.

9. **[note] §5.1: correction of my report, credited to Sauron.** Sauron notes that the 0.1% footer guard would catch
   dropped G2/G3 arcs. I confirmed it: `plastic_shape.py:380` asserts `relative_extrusion_footer_difference < .001`
   in `main()`, and the archived G slice has `enable_arc_fitting = 0`. My finding 1 ("breaks silently") overstated
   this; the failure is loud when the script is used as intended. The canonical parser should still parse arcs.

10. **[note] §2.7.1 vs `gpu_material_probe.py`: one geometric convention, but which one?** Sauron requires the card
    and the FE domain to share the gross nominal footprint convention. The existing truth path uses a **conservative
    inscribed voxel** that omits 8.02% at 0.2 mm (ADAPTIVE-MESH.md table). That is neither the nominal footprint nor the
    stadium.
    *Requested change:* state which convention the coupon analysis will use, and require the truth solver either to
    match it (fractional occupancy, §5.3) or to report the omission correction.

11. **[note] §4.7 inter-layer traction prescreen.** This is excellent and cheap, and it is the right S1 stage in the
    pipeline. It needs one isotropic solve of a domain. **Request:** state which domain: the full design envelope (no
    design yet) or the incumbent design. These give different rankings for a part with large removable volume. Make
    the ranking-conservatism test (open question 6) an explicit acceptance test in the roadmap.

12. **[note] §6 coupon programme vs roadmap.** C1-C7 is the right list, but it is printer-bound and gated by Q1
    (testing machine). **Request:** mark C2 (Z tension) and C3 (inter-layer shear) as the P1/P2 minimum, since they set
    the only orientation-sensitive constants. Mark C4/C5 as P3. Also tie coupon G-code to the same receipt schema.

13. **[note] Citation hygiene.** The [v]/[m] marking is exemplary. Several load-bearing formulation references are
    [m] (Langelaar 2016 DOI, Wang/Lazarov/Sigmund 2011, Bruggi 2008). Before the merged plan is published, convert the
    ones it quotes into [v].

## 3. What the merged plan must keep

- The finding that **stiffness anisotropy is small and strength anisotropy and massing are large** (§0.1, §2.2, §2.5).
  It reorders the whole roadmap.
- The closed-form **orientation-dependent shell thickness** `t(α) = max(n_w w sin α, n_t h cos α)` and the
  directional-coating formulation (§4.4). This is the precise statement of a collaborator's "orientation-dependent massing". It
  agrees with Frodo's SHELL-001 once the angle conventions are mapped.
- Mandel internally with an explicit permutation to `gpu_hex` order (§2.4). I checked the B rows in `gpu_hex.py:36-37`:
  the order is (xx, yy, zz, xy, yz, xz), so the permutation `[0,1,2,5,3,4]` is correct. Also keep the measured bug
  magnitudes as regression tests.
- The two-mode, degree-1-homogeneous failure index needing only X_t, Z_t and S_il (§3.2), and the "45° off-axis coupon
  is worth most" argument.
- E_min **only inside the optimiser**; every reported number comes from the zero-ersatz re-analysis (§4.3, D9). This
  matches my "two FEM roles" decision exactly.
- The AM filter applied to the **printed-material field**, so internal ceilings of hollow bodies are caught (§4.6).
- Discrete orientation sweep with the inter-layer traction prescreen (§4.7, D8).
- The invariant list I1-I20 (§7) as the test plan. It is the best single artefact for keeping the code honest.
- §5.3's mapping algorithm (structure tensor, coherence, bond fraction) as the specification of the truth-stage material
  mapper.
