# Gandalf on Legolas (round 2 cross-review)

Reviewed: `D:\Code\Models\fdm-gen\research\legolas.md` (178 lines) and `scratch\legolas\` (`bench_*.py`,
`out_h0.8.txt`). Repo numbers spot-checked in `spool-wall-rack/analysis/rev-g2/ADAPTIVE-MESH.md` and
`adaptive-validation/*.json`. Angle: architecture, integration, roadmap feasibility.

## 1. Verdict

These are the most useful numbers any of the four reports produced: measured matvec rates, measured Jacobi-CG scaling
and an honest projection layer. Its central call is correct: **geometric MG-PCG is the one must-build compute item.**
Two architectural decisions need revision: D3 ("never re-mesh per orientation") and the premise that compliance
discriminates orientations. Both conflict with Sauron's mechanics and with the layer-wise filters the design depends
on.

## 2. Findings

1. **[critical] §0.3 / §5 / D3 "fixed grid + rotated `Ke(n)`, never re-mesh per orientation" conflicts with Gandalf
   §0.5 and Sauron D4/D6.** A fixed part-frame grid works for an elastic TI model. However, the parts of the model that
   make orientation matter all need layers on grid planes:
   - the Langelaar AM filter, which is a layer-by-layer sweep along a grid axis (Sauron §4.6);
   - the directional coating, which uses per-layer XY erosion plus Z erosion (Sauron §4.4);
   - Z quantisation of skins (n_t·h).

   On a fixed grid with an arbitrary build direction you would need a non-grid-aligned overhang measure (front
   propagation or Qian's gradient form) and an oblique coating. That is a research problem, and it is not cheap.
   Re-voxelising on a structured grid is cheap: the geometric MG hierarchy is just grid coarsening, so the "hierarchy
   reuse" saving is small.
   *Requested change:* keep D3 for **analysis mode** (§5 option 1: scoring an existing design across orientations,
   which is exactly a collaborator's project #1). Use per-orientation print-frame voxelisation for **TO**. Cost both in §5. Add the
   re-voxelisation and hierarchy-build time to the B-list; I expect seconds at 0.8 mm.

2. **[critical] §5 orientation economics assume compliance varies usefully with `n`; Sauron shows it barely does.**
   §5 ("compliance varies smoothly with n, so 20-25 samples") and the S0/S1 schedule rank orientations by compliance.
   Sauron's TDS table gives E_Z/E_XY of 0.85-0.92 and about 15% directional modulus spread (sauron.md §2.2, §2.5).
   A compliance-ranked S0/S1 would mostly sort noise. My own P1-B made the same mistake and I am withdrawing it.
   *Requested change:* make S0 Sauron's **inter-layer traction prescreen** (one isotropic solve, analytic over about
   200 directions; sauron.md §4.7) plus an overhang/support-area estimate. Then re-cost S1-S3 as "TO for the top K from
   the prescreen". This probably cuts S1 from 24 orientations to 5-10, which helps the budget.

3. **[warning] §2 "Anisotropy and MG": "E_xy/E_z of 2-3 for FDM are mild" is off by a factor of about two for these
   materials.** Sauron's data gives about 1.1-1.2 for PETG/ASA stiffness. The conclusion (MG copes) survives, but a
   wrong number in a compute report will be quoted later.
   *Requested change:* cite the TDS ratios. Keep 2-3 only as a stress case for CF-filled or strength-weighted studies,
   and label it as such.

4. **[warning] §4 / D4 resolution vs Sauron D4 (0.2 mm) vs Gandalf ("0.6 mm or coarser").** Legolas's numbers settle
   the cost side. A 0.8 mm voxel cannot represent 0.84 mm shells (§4 caution), and Legolas's repo citation shows
   conservative voxels omit 33.09% of material at 0.8 mm and 16.38% at 0.4 mm. I verified this in
   `adaptive-validation/g-h0p8-geometry.json` and `g-h0p4-geometry.json`. So the massing model cannot run at the
   screening tier at all.
   *Requested change:* add one row to §4 stating the **minimum resolution at which the directional coating is
   meaningful**: I estimate 0.4 mm XY with dz = 0.2 or 0.4. Cost that tier on a masked domain (30% occupancy). That
   makes the honest roadmap statement "massing-aware TO is a leaders-only tier", which the merged plan needs.

5. **[warning] Robust formulation and load cases not costed.** Sauron's v1 uses eroded/nominal/dilated designs (3
   solves per iteration) and minimax over K load cases. The bracket alone has 2 cases (12 kg and the one-spool delta;
   G2-BRIEF). §4/§5 cost one solve per iteration.
   *Requested change:* add a multiplier column (robust × K) to the §4 and §5 tables, even if the robust formulation is
   deferred to v1b. That number decides whether v1b is feasible on the laptop.

6. **[warning] D5 E_min ≥ 1e-3 vs Sauron §4.3 E_min/E_0 = 1e-6.** This contradicts Sauron. At 1e-3, void cells carry
   0.1% stiffness. That is harmless for compliance but biases the TO-vs-reanalysis comparison (Sauron I19) and the
   stress constraint near void. B2 already measures iteration counts against E_min.
   *Requested change:* make D5 conditional: "1e-6 unless B2 shows > 40 iterations, in which case raise it, and record
   the E_min used in every receipt". Sauron should accept the same rule in round 3.

7. **[warning] §5 option 2 / D3 analytic `dC/dn` co-optimisation is scope creep for v1.** Sauron (D8) and I (§9.5)
   both propose a discrete sweep. Given finding 2, gradient orientation would be optimising a nearly flat compliance
   landscape, and it is incompatible with the layer-wise filters (finding 1).
   *Requested change:* move it to "later research" and remove it from the decisions list.

8. **[warning] Warp version drift.** Benchmarks ran on **Warp 1.18.0** in `scratch\legolas\.venv`. Spool-rack pins
   **1.17.0** (`requirements-gpu.txt`) and its fixtures were accepted on that version. Legolas's report says this (§1)
   but does not draw the consequence: P0 parity tests (my P0-C) must run on the pinned version first, and an upgrade
   is a separate re-baseline.
   *Requested change:* add this to the B-list as B0.

9. **[warning] §6 `mesh_from_cells` vectorisation (B7) is on the critical path but not in any roadmap phase.** The
   7.66 s for 232 k nodes Python loop extrapolates to minutes at 4-8 M cells. The truth stage depends on it for every
   finalist.
   *Requested change:* tag B7 as a P0/P1 deliverable in the merged roadmap, not a "measure later".

10. **[note] Hardware facts align with my report.** Both of us found that this PC is an RTX 3500 Ada Laptop (11.5 GB),
    not the repo's RTX 3080 Ti. Both of us ask whether second workstation has a CUDA GPU. Keep this as one merged open
    question. If second workstation has the 3080 Ti, my machine table (second workstation = GPU truth worker) holds. If not, Legolas's (PC = inner
    loop) is the only option and compute-box becomes more important.

11. **[note] Stage numbering collides.** Legolas uses S0-S4 for sweep tiers. I use S0-S8 for pipeline stages, and
    Frodo uses stages 1-9. **Request:** rename the sweep tiers to R1-R4 ("resolution tiers") in round 3, so the merged
    plan has one stage vocabulary.

12. **[note] §10 housekeeping: `taskkill /F /IM python.exe`.** Disclosure was honest. Under the new coordinator rule it
    must not recur: kill only the PIDs you started. I ran no Python during that window, so my work was unaffected.
    Other agents should check.

13. **[note] §3 FP64 suspicion is well reasoned.** About 1,150 flop per cell-matvec at 159 M/s ≈ 180 GFLOP/s, which is
    near a consumer-Ada FP64 ceiling. The B1 FP32-smoother/FP64-outer plan is the right test. **Request:** fetch the
    actual FP64 peak spec for the RTX 3500 Ada Laptop so B1's expectation is anchored rather than assumed.

## 3. What the merged plan must keep

- **MG-PCG on a structured, masked voxel grid as the single must-build compute item**, with PyAMG/scikit-fem as
  oracles (D1). The measured Jacobi-CG iteration doubling (790 → 1570) is the evidence.
- The two-tier honesty statement: **TO is homogenised; bead resolution is verification only** (D4, §4 caution).
- Measured operator throughput (151-184 M cell-matvec/s, flat across sizes) and the memory ceiling of about 15-20 M
  cells in the present layout, with the implicit-index kernel as the fix.
- The B1-B8 benchmark plan with explicit go/no-go criteria, and the project-level gate "GO if B2 passes and B3 ≤ 3 s/it
  at 0.8 mm". This should become P0's exit criterion in the merged roadmap.
- **Analysis mode** (§5 option 1): score any given design across about 90 orientations in minutes. This is the
  fastest route to something useful for a collaborator's project #1, and it could ship before any optimiser.
- Verification cost of about 2-6 min per finalist once MG exists, and "export per-cell maxima in sweeps; keep all
  Gauss samples for finals" (§6). That reconciles the spool-rack honesty rule with throughput.
- File-based, idempotent jobs with receipts (§5 scheduler). This matches my receipt and content-addressed store design.
