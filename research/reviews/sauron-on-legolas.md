# Sauron on Legolas (compute and performance): cross-review, round 2

Reviewer angle: frames, units, tensor conventions, mechanics, the numbers, and data flow between stages.
Checked against the repos (read-only), Legolas's scratch scripts, and my numpy scratch (`scratch\sauron\*.py`).

## 1. Verdict

This is a strong, honestly labelled compute report. The diagnosis (Jacobi-CG is the bottleneck; build matrix-free
geometric multigrid-preconditioned CG) and the two-tier honesty statement are right. The cell, DOF and flop
arithmetic checks out.

The mechanics underneath the sweep economics has three errors that change the plan:
- The n ~ -n hemisphere reduction ignores up/down asymmetry.
- The fixed part-frame grid is incompatible with layer-wise print constraints.
- The per-iteration cost model omits the adjoint solves for strength constraints.

## 2. Findings

1. **[critical] Section 5, "Parametrisation" and "Sampling": the hemisphere reduction is wrong for this problem.**
   - C(n) = C(-n) holds for the transversely isotropic elastic tensor, and for the inter-layer failure index (which
     is quadratic in n).
   - Printing up versus down is **not** symmetric. Overhang/self-support, bed contact, internal ceilings, bridges and
     support all flip. A part printed "upside down" is a different print problem with the same stiffness.
   - Sampling a hemisphere halves the candidate set and can discard the only printable direction of a pair.
   - **Change:** sample the full sphere for anything involving printability.
   - The hemisphere is valid only for pure stiffness analysis mode (S0), and it should be labelled as such.
   - Recost S1 with the doubled count, or with the hemisphere for screening followed by an up/down printability split
     of the survivors.

2. **[critical] Headline 3 / D3, "never re-mesh per orientation; rotate the material tensor": incompatible with
   print-aware topology optimisation.** This contradicts Gandalf decision 4 and Sauron D4/D5/D6 (all re-voxelise in
   the print frame). On a fixed part-frame grid:
   - (a) Layers are not grid planes. The Langelaar layer-wise AM filter, which every report proposes for the overhang
     rule, does not apply. It would need an arbitrary-direction formulation such as front propagation (van de Ven) or
     Qian's gradient measure.
   - (b) The slicer-faithful massing (walls = in-layer erosion, skins = n_t layers of Z erosion; Sauron section 4.4)
     needs layer-aligned erosion.
   - (c) Inter-layer bond fractions and `dz = h` layer resolution are lost.

   **Legolas's own numbers show that re-voxelising is cheap:**
   - Host build is 1.2 s at 1.6 mm, 6.8 s at 0.8 mm and 51 s at 0.4 mm. Against a 0.5-75 min topology optimisation
     per orientation that is about 1-4% overhead.
   - A geometric multigrid hierarchy on a structured grid needs no setup beyond coarsening.

   **Proposed reconciliation:**
   - Use a fixed part-frame grid for **analysis mode** (S0: scoring a given design over orientations). There it is
     actually *better*, because it removes re-voxelisation noise from comparisons. Note that at E_Z/E_XY of about
     0.85 the compliance differences between orientations are only a few percent and comparable to that noise.
   - Use print-frame re-voxelisation for **every topology optimisation that applies printability or massing**.

3. **[warning] Section 5 option 2, "dC/dn = -u^T (dKe/dn) u": notation and constraint problems.**
   - Here C means compliance. The report uses C for the stiffness tensor everywhere else. Write
     `dc/dn = -sum_e u_e^T (dK_e/dn) u_e` (self-adjoint compliance only).
   - n is constrained to the unit sphere. The gradient must be projected onto the tangent plane, or n parametrised by
     two angles, with the pole singularity handled.
   - The derivative covers stiffness only. The AM filter, re-voxelisation, bed contact and the inter-layer strength
     constraint are non-smooth or non-differentiable in n on a grid.
   - Combined with the weak stiffness signal (about 15% directional modulus range, Sauron section 2.5), gradient
     co-optimisation of n would mostly chase noise.
   - I verified the tensor derivative itself numerically for in-plane spin (Sauron section 2.4: rel. err 2e-9 versus
     finite differences), so the math is available.

   **Change:** follow Gandalf R7. Use discrete orientations in v1 and treat the continuous refinement as an
   experiment, not a decision.

4. **[warning] Section 5 / S0: "analysis-mode score of the unoptimised envelope" by compliance will not discriminate.**
   Compliance of the solid envelope varies with n by at most roughly the directional-modulus range, about 15%, and
   usually much less. The orientation-sensitive quantity is the **inter-layer failure index**:
   - Inter-layer traction on the layer plane: `sigma_n = n.sigma.n` and `tau = |sigma n - sigma_n n|`.
   - It can be evaluated analytically for about 200 directions from **one** stress field, with no solve per
     direction (Sauron section 4.7; prior art in Umetani & Schmidt 2013, cited by Frodo).

   **Change:** make S0 output both compliance and the aggregated inter-layer index per direction, and rank on the
   latter plus printability.

5. **[warning] Sections 3a/4/5: the cost model omits adjoint solves and the AM-filter sweep.**
   - Compliance is self-adjoint. An aggregated p-norm stress or inter-layer constraint is not: it needs **one adjoint
     solve per aggregated constraint per load case per iteration**.
   - Sauron D7 has two such constraints (inter-layer and in-layer). That roughly triples solves per iteration relative
     to compliance-only.
   - The Langelaar filter is sequential in layers: about 75-190 layer kernel launches per pass at 0.8-0.4 mm for a
     60 mm build height (more at 0.2 mm), forward and adjoint.

   **Change:** add these lines to the per-iteration budget and to B3, and recost S1-S3 for "compliance + 2 aggregated
   constraints + AM filter".

6. **[warning] Section 2, "Anisotropy and MG": the realistic ratio and the hard case are both missing.**
   - Measured E_XY/E_Z for PETG/ASA is **1.09-1.18** (Bambu TDS, Sauron section 2.2), not 2-3. Keeping {1, 2, 3} in B2
     as a stress test is fine, but label the realistic value.
   - More importantly, "ours is uniform per run, so easier" is true for the design stage only. The **truth stage**
     has spatially varying C: per-element wall-tangent angle (S6), per-element bond-fraction scaling, and
     class/role changes.
   - Add a B2 variant with random per-element in-plane angles and a ±50% inter-layer-stiffness field. This is the
     case the cited SMO 2025 multigrid paper addresses.

7. **[warning] D5 / Section 2: "E_min >= 1e-3 ... FDM has no truly-weightless fill anyway."**
   - The rationale is wrong under the house rules. Base infill is 0%, sparse infill gets zero credit, and voids are
     void. There *is* weightless "fill".
   - E_min = 1e-3 is defensible only as a design-stage solver device, and Legolas correctly re-solves with true voids
     in D5.
   - At 1e-3 the void phase contributes about 1e-3 x (1 - volume fraction) of solid stiffness. That can visibly bias
     compliance for low volume fractions and slender members.
   - **Change:** drop the physical justification. Keep 1e-3 only if B2 needs it. Make the design-to-truth compliance
     ratio (Sauron I19) a gate that catches any reliance on ersatz stiffness.

8. **[warning] Section 4, the 0.8/1.6 mm tiers and massing: the faithful coarse-grid semantics are left unstated.**
   Legolas rightly says shells are not resolved at 0.8 mm. The mechanics consequence needs saying explicitly:
   - With 0% sparse infill, a thick body region prints as a **hollow 2-wall shell** unless it is covered by a 100%
     helper.
   - A coarse model that treats density 1 as solid is faithful only if **every body cell becomes helper (100%)** in the
     handoff to Orca.

   **Change:** state that coarse tiers (>= 0.4 mm) optimise "printed-solid" placement and output body = helper. Hollow
   massing (shell-only regions) is decided only at 0.2 mm or in local refinement. This also resolves Gandalf's 0.6 mm
   grid issue.

9. **[warning] Section 6 table: omission percentages at 0.4/0.8 mm.** "Conservative full-cell rule omitted 8.0% at
   0.2 mm, 16.4% at 0.4 mm, 33.1% at 0.8 mm (repo, G geometry)".
   - The 8.0% is confirmed: `g-results/*` `geometry_omission_fraction = 0.0802`.
   - I could not find 16.4% or 33.1% in `analysis/rev-g2` (Markdown or g-results JSON). `GPU-VALIDATION.md` gives
     17.12% at 0.4 mm and 8.37% at 0.2 mm for a crop, not whole G.

   **Change:** cite the file for 16.4/33.1, or mark them as estimates.

10. **[note] Section 3: FP32/mixed precision.** Agreed, with an FP64 outer residual (the Liu 2018 pattern). In
    addition:
    - The anisotropic patch test (Sauron I11) and **every finite-difference sensitivity check (Sauron I14)** must run
      in FP64. Central finite differences at h of about 1e-6 are meaningless in FP32.
    - FP32 is acceptable as a smoother or preconditioner, not as the operator inside the CG whose residual is gated.

11. **[note] Section 5 (Ke(n) as one 24x24 per orientation): correct for the design stage.** Two implementation
    traps carry over from my report:
    - (a) Rotate C in Mandel form (`C' = Q C Q^T`, Q orthogonal) and convert to Voigt only at the kernel. Applying the
      Mandel Q to a Voigt C gave errors up to **484 MPa** on a 1,540-1,810 MPa card in my check.
    - (b) `gpu_hex` orders Voigt shear (xy, yz, xz). A canonical (23, 13, 12) card needs the `[0,1,2,5,3,4]`
      permutation.

    For the truth stage, a library of Ke indexed by (class, 5 deg angle bin, bond bin) costs 4.6 kB per entry. A
    5 deg bin changes C by at most 0.63% (computed this round), so a 1-byte index per cell beats per-cell C.

12. **[note] B6, the orientation-correctness gate: add a covariance test.** Rotate the domain, loads and
    transversely isotropic axis together by a rotation that maps the grid onto itself (90 deg about a grid axis).
    Compliance must be identical to about 1e-10. This catches rotation-direction (R vs R^T) bugs, which
    agree-with-scikit-fem tests miss when both sides share the same R.

13. **[note] Section 10, housekeeping: `taskkill /F /IM python.exe`.** This killed every python.exe on the PC; it was
    disclosed honestly. Under the new coordinator rule only PIDs we started may be killed. My scratch runs were
    sub-second and finished before then, so I know of no damage to Sauron work. Record it in the merged plan's
    run-hygiene section.

14. **[note] Section 9, "stress-constrained TO needs the 0.4 mm tier or p-norm with a calibrated factor".** My answer
    (Sauron section 3.3): strength enters design as **aggregated** constraints (p-norm with qp-relaxation). That is
    meaningful at coarse resolution as a relative measure. Raw peaks and percentiles are reported only at the 0.2 mm
    truth stage. The third angle (raster spin) is **not** needed in topology optimisation under the transversely
    isotropic design model. Sweep it only at re-analysis, for bed fit, seam and raster, so it does not triple the
    sweep.

## 3. What Legolas got right (keep in the merged plan)

- Matrix-free geometric multigrid-preconditioned CG on a structured masked grid (D1). It is the only route past
  Jacobi-CG's measured h^-1 iteration growth (790 to 1,570 iterations for 1.6 to 0.8 mm), consistent with
  kappa ~ h^-2.
- Arithmetic checks, which I verified:
  - Cell counts: 750x400x300 = 90 M at 0.2 mm, 11.25 M at 0.4 mm, 1.41 M at 0.8 mm.
  - DOF: 3 x 376 x 201 x 151 = 34.2 M at 0.4 mm.
  - 1,152 flops per 24x24 matvec x 159 M/s = 183 GFLOP/s, which plausibly saturates laptop FP64.
- The two-tier honesty statement (D4): topology optimisation is homogenised; bead resolution is verification only.
  The finding that a 0.8 mm grid "cannot represent beads at all" is right and must stay prominent.
- True-void re-solve for finals (D5). A transversely isotropic material about the build axis at the design stage,
  matching my D2.
- The benchmark plan with go/no-go gates (B1-B8), especially B2 with a void-contrast sweep and B6 as a scikit-fem
  correctness oracle before scale.
- Analysis mode on a fixed grid for scoring existing parts. It serves a collaborator's "project #1" directly and is the
  noise-free way to compare orientations of a fixed design.
- Exporting all Gauss samples for finalists only, and per-cell maxima in sweeps, preserves the house rule where it
  matters.
