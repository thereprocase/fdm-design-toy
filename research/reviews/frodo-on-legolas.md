# Frodo on Legolas (compute and performance)

## 1. Verdict

The measurements are solid and honestly labelled. Jacobi-CG doesn't scale, a matrix-free geometric MG-PCG is the one
must-build item, and the go/no-go benchmarks are exactly what a schedule needs. But the speed headline rests on two
choices that drop most of the printability rules and most of the orientation signal: a fixed grid with a rotated
tensor, and design resolution ≥ 0.8 mm. The "1–2 h, overnight-free" estimate is for a generic box, not the MVP part,
and leaves out contact, two load cases, slicing and printability. The `taskkill /IM` incident needs a process fix.

## 2. Findings

1. **[critical] D3 "fixed grid + rotated tensor, never re-mesh" conflicts with Gandalf (decision 4) and Sauron
   (D4), and with the printability catalog.** Every geometric print rule is defined in the print frame:
   - overhang filter along build Z;
   - layer-wise wall and skin erosion (massing);
   - bridges and per-layer gaps;
   - Z quantisation to the layer height;
   - the bed plane as support.

   On a part-fixed grid, an arbitrary build direction cuts cells obliquely, so none of these can be enforced inside
   the solve. Sauron also shows that the elastic tensor only varies about 15% with direction for PETG/ASA
   (E_Z/E_XY = 0.85–0.92, verified against the Bambu sheets). So a sweep that only rotates `C(n)` measures the
   *weakest* orientation signal and ignores the strong ones: inter-layer strength, support/overhang, and massing.

   **Requested change:** keep fixed-grid rotation for **analysis mode** (§5 option 1: scoring an existing design
   across orientations, which is a good deliverable for a collaborator's "project #1"). State plainly that design TO
   re-voxelises per orientation candidate. Then re-cost the sweep, including per-orientation voxelisation and MG
   hierarchy rebuild, which you note are cheap.
2. **[critical] Housekeeping (§10): `taskkill /F /IM python.exe` killed every Python process on the PC.** The
   disclosure is honest, and that matters. But the user runs their own long Python batches on this PC outside Claude shells (e.g.
   PanoStitch), and other agents may have been running Python at the same time. Killing by image name can silently destroy hours of someone else's work with no receipt. The
   coordinator has since banned it. **Change:** benchmarks must record their own PIDs (or run under a job object
   with a time budget) and kill only those. Add a timeout to `bench_direct.py`-style runs so a runaway never needs
   manual killing. Ask the user whether any of their jobs died around that time.
3. **[warning] D4 "TO homogenised ≥ 0.8 mm" means the optimiser cannot honour the minimum-feature or massing
   rules.**
   - At 0.8 mm cells, one cell is about the minimum feature (2w = 0.84 mm, Fillaprint/G2) and the minimum gap.
     The robust length-scale formulation needs about 3–4 cells per feature.
   - The 1.6 mm skins and 2–4-wall shells (0.84–1.7 mm) are sub-cell.
   - The overhang stencil spans 4 layers.
   - Your own quoted number (§6: 33.1% of material omitted at 0.8 mm on whole-G; verified in `ADAPTIVE-MESH.md`)
     says the same.

   That is fine **if the plan says so**. Otherwise a reader will assume "the optimiser respected printability".
   **Change:** add a column to the §4 table saying which catalog rules each tier enforces (my guess: OVH-001 coarse
   at 1.6/0.8, WALL/GAP/SHELL only at ≤ 0.2–0.4, everything else post-check). Reconcile with Sauron's 0.2 mm design
   grid: is there a hybrid, e.g. massing emulated analytically at coarse resolution (Sauron's `t(α)`) and resolved
   only in the final tier?
4. **[warning] §4–5: the budget is for a 150 × 80 × 60 mm cantilever box, not the MVP part.** The spool bracket
   (Gandalf's and my worked example) has a body envelope of **207.5 × 233.5 × 24 mm**, measured from
   `spool-wall-rack/designs/rev-g2/print-controls/ef-core-asa-4w-1p6/body-only.stl`:
   - box 1.16e6 mm³ vs your 0.72e6, about 1.6× more cells;
   - body is about 15% of the box (you assumed 25–40%);
   - only 24 mm thick, i.e. 30 cells at 0.8 mm and 120 layers at 0.2 mm.

   **Change:** re-run `bench_gpu.py` with the bracket envelope and a masked domain. A plate-like part probably makes
   the masked/sparse layout more valuable than your estimate shows.
5. **[warning] §5 "S0–S2 ≈ 1 h … overnight-free" leaves out costs a user will hit:**
   - The G2 bracket has **two load cases** (full 117.72 N and a one-spool change, which G2-BRIEF says must be
     re-solved, not scaled).
   - It has **unilateral wall contact** (active-set iterations; the repo's contact solves took minutes).
   - S4 extraction, Orca slicing, toolpath checks and the per-orientation interface printability check.
   - Laptop thermals (your runs were under 80 s).

   A designer told "about an hour" who waits four will stop trusting every other estimate. **Change:** quote ranges
   per stage, label the excluded items, and make the runner write a live `progress.json` with an ETA that updates
   from measured iteration times (frodo.md §5.1). A late estimate then becomes visible early, not at the end.
6. **[warning] D5 E_min ≥ 1e-3 vs Sauron's 1e-6.** Your measured contrast effect (16 → 106 SA iterations) is a real
   argument, but at 1e-3 grey and void regions carry stiffness the printed part won't have. Together with D4's
   ≥ 0.8 mm homogenisation, the design-vs-truth gap could be large. Sauron's I19 (gap blocks the candidate) and
   Gandalf's R6 (truth refuses E_min > 0) are the guards. **Change:** make B2 measure iteration counts *and* the
   compliance gap to a zero-ersatz re-solve at each E_min, so the choice is evidence-based rather than a
   solver-comfort default.
7. **[note] §5 "spin about n is a later refinement".** For printability it is not later: bed fit with the P1S
   18×28 mm exclusion, footprint diagonal for ASA warping, and seam placement all depend on spin. For a
   207 × 233 mm part, bed fit alone may decide it. **Change:** include spin as a discrete feasibility check (0/90°
   at least) in candidate generation, even if the solve ignores it.
8. **[note] §2 "FDM has no truly-weightless fill anyway" is not true for the MVP.** The spool-rack process is 0% base
   infill: enclosed voids with zero material and, by house rule, zero credit. That argues for keeping E_min a
   solver-only device, never a physical claim.
9. **[note] §6 total verification "2–6 min per candidate".** Good, and the 0.1% extrusion-footer gate is the right
   correctness check. Add the PROC-001 effective-settings and modifier-role checks (`gpu_demo_slice.py`) to the
   per-candidate cost. They are seconds, but they are what stops a result built on settings Orca quietly ignored.
10. **[note] Q "strength as design constraint or post-check".** My answer from the catalog side: inter-layer
    strength (STR-001) should be a *penalty or constraint in the design solve* at whatever tier can carry it, because
    it is the main orientation signal (Sauron). Absolute strength claims stay post-check and PROVISIONAL until
    coupons exist.

## 3. What the merged plan must keep

- **D1: matrix-free geometric MG-PCG in Warp, PyAMG/scikit-fem as oracles**, plus the measured evidence that
  Jacobi-CG fails (iteration count ~1/h, reproducing the repo's 4.1 M-cell failure).
- **The B1–B8 benchmark plan with go/no-go thresholds and fallbacks.** That is the most schedule-protective thing in
  any of the reports.
- **Analysis mode** (one design × many orientations at a few seconds each). It is the fastest route to something
  a collaborator can use on parts he has already designed, and it needs no optimiser.
- **The two-tier honesty statement (D4):** "Do not promise TO at bead resolution"; bead-aware 0.2 mm verification
  only. Keep the wording; add the rule-enforcement table that makes it concrete.
- **`[measured]` vs `[estimate]` tagging** and the "assumptions and limits of my measurements" section, including
  the self-reported `taskkill` incident. That is the house style.
- **compute-box as a batch/RAM machine, only after the CFD sweep finishes and its owner is told.** The PC GPU stays
  the inner-loop machine.
