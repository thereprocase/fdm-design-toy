# Legolas on Sauron (compute / performance review, round 2)

## 1. Verdict
The mechanics are careful and checkable, and the finding that orientation matters through strength and massing rather than stiffness is the key insight of the project. As a compute plan it is not yet affordable: the 0.2 mm design grid and problem v1 (minimax, two stress aggregates, robust triple) together cost two to three orders of magnitude more than the other reports assume. The inter-layer traction prescreen (4.7) is the best compute idea in any report and should be promoted.

## 2. Findings

1. **[critical] D4 / section 4.1: design grid dxy = dz = 0.2 mm.** For the 150x80x60 mm bracket that is 90 M cells (270 M DOF) in the bbox, about 27 M at 30 % occupancy. On this PC (RTX 3500 Ada, 11.5 GB; measured 159-184 M cell-matvecs/s; an 11.25 M-cell box already takes a large share of VRAM in the present layout) it does not fit. With an ideal MG-PCG a solve is about 100-200 s, so 150-300 TO iterations is 4-16 h per orientation per solve-per-iteration (estimate). Gandalf proposes 0.6 mm. Requested change: make 0.2 mm the verification grid (the existing adaptive truth path) and give the design stage 0.6-0.8 mm with a sub-cell shell model. At that size voxel erosion by n_w*w = 0.84 mm is about one cell, so the section 4.4 smooth-erosion coating cannot be validated at the design grid; use a fractional shell from local inclination (your own t(alpha) formula) calibrated against 0.2 mm as I16 suggests.

2. **[critical] Section 4.7 problem v1: solves per iteration.** Minimax over K load cases is K state solves. Each aggregated stress constraint adds an adjoint solve (+2 for F_PN,L and F_PN,P). The robust formulation triples the design, giving 3 x (K + 2) = 12 solves per iteration at K = 2, against the 1 in my cost model. qp-relaxed stress TO also tends to need more iterations (300-500 with beta continuation of 6 stages x 40-50). At 0.8 mm (2-3 s per MG solve, estimate) that is 24-36 s per iteration, 2-5 h per orientation. Requested change: split v1 into v1a (compliance, volume, AM filter, non-robust, K solves per iteration) and v1b (add stress aggregates, only on the top K orientations). Gandalf's roadmap defers stress to P3; the merged plan should side with Gandalf. If robust is kept, run the three realisations only in the last continuation stage.

3. **[warning] Section 5.4 / D2: per-element C as 21 numbers is the expensive option.** The element apply becomes a sum over 8 Gauss points of B^T C B u, about 2,600 FMA per cell versus about 576 MAC for the shared-Ke kernel (about 4.5x FLOPs; the kernel looked FP64-compute-bound at about 180 GFLOP/s on this laptop GPU, spec unverified). The quantised class library you also mention (theta bins of 2 degrees, class, b bins) is the right interface: an index into an L2-resident array of 24x24 Ke (4.6 kB each, 500 classes about 2.3 MB). Requested change: state the library as the solver interface and use per-cell C only in stress recovery. Bin the bond fraction b (for example 8 levels) so g(b) does not explode the library.

4. **[warning] Section 4.6 AM filter is a sequential layer sweep.** The forward and adjoint passes are N dependent steps each (300-750 layers at 0.2 mm, 100-250 at 0.6 mm). Each layer is a parallel 2D stencil, so the cost is a few ms per iteration, small beside the solve, but it must be N sequential launches, not one kernel. Run the I14 gradient test at the production layer count, since the P-norm smooth max/min across 50-100 layers is a float64-sensitive spot.

5. **[warning] Section 4.4 coating memory and cost.** Z-erosion over up to 11 layers and a disc filter of radius about 4 cells at 0.2 mm (9x9 stencil) are cheap per iteration (scipy binary erosion r = 4 measured 3.3 ms per 750x400 layer on CPU; a GPU separable version is cheaper). The sensitivities need stored intermediate fields: about 5-8 extra float64 grid fields, around 200 MB at 3 M cells but about 0.7 GB per field at 90 M cells. That is another reason for finding 1.

6. **[warning] Section 4.7 prescreen: cost is trivial, validity needs a number.** 200 directions x 3-8 M elements x about 20 flops is seconds on a GPU and tens of seconds in numpy. The caveat is that the isotropic stress field belongs to the incumbent design, which itself depends on orientation through the overhang constraint. You say it only ranks and prunes. Requested change: add an acceptance criterion (the eventual best orientation must be in the prescreen's top K on the benchmark problems). Testing that costs K full optimisations, about an hour at 0.8 mm with a working MG, so schedule it in P1.

7. **[warning] Section 5.3 mapper must be vectorised.** Supersampling 4x4 per cell over roughly 0.5-1 M segments for a G-sized part is about 1e8 samples: hours in Python loops, minutes in numpy or Warp. Bond fraction b from footprint_k intersect footprint_k+1 is a 2D mask AND per layer pair (milliseconds). The structure-tensor accumulation is a Warp atomic_add kernel. Expect 1-3 min for a 74 cm3 part (estimate; the existing occupancy-only footprint cache is 16.1 s). Fractional occupancy then needs partial-volume stiffness in the solver (see finding 3).

8. **[warning] Sections 2.6 and 5.4: heterogeneous C and multigrid.** You note Jacobi degrades. The same applies to geometric MG with rediscretised coarse operators: layer-alternating coefficients (+/-45 resolved explicitly at 0.2 mm) oscillate in z on the finest grid. Coarse levels need the exact laminate homogenisation from 2.6 (or Galerkin coarse operators), otherwise iteration counts rise. Keep 2.6 for this reason, and test MG iteration counts on the +/-45 stack (my plan item B2).

9. **[note] Section 2.5: the weak orientation signal supports my economics.** With elastic variation of only about 15 %, the stress field barely depends on d, which makes the traction prescreen and re-evaluation of a frozen design cheap and high-value. It also puts TO compliance differences between orientations near TO noise. Add a repeat-run noise-floor requirement to D8.

10. **[note] D8 sampling.** A full-sphere Fibonacci set of about 200 is right for the prescreen (overhang and bed contact are not symmetric under d to -d). For full TO only about 20-25 directions (30 degree spacing) merit a run; state the TO-count budget explicitly.

11. **[note] I14 and I18 test costs** are seconds to minutes on reduced domains (for example 40x20x20 mm for I18). Fine.

12. **[note] Section 6 coupon plan** is outside my angle; the dead-weight and DIC options imply only light image processing.

## 3. Keep
- The design/truth split (D9): zero-ersatz re-analysis and E_min only inside the optimiser. It is what makes the cost accounting honest.
- Mandel storage and the explicit permutation to the `gpu_hex` Voigt order (I9 is a cheap, high-value test that protects every later benchmark).
- The closed-form t(alpha) and the insight that rotating the part changes which surfaces are thin-skinned.
- The inter-layer traction prescreen, and F_L / F_P as separate aggregates so the orientation-sensitive one can be switched off for speed.
- Invariants I1-I20: most are seconds-scale unit tests and should gate every benchmark number in this project.
