# Plan: open generative design for FDM parts

Merged from four researched, cross-reviewed reports
([`research/final/`](research/final/): architecture, mechanics, compute, workflow and constraint catalog).
Every number below carries its evidence level from those reports. Nothing here is physically
qualified yet; the roadmap ends with physical tests for exactly that reason.

## 1. What we're building, in one paragraph

A tool that takes a part's **design space, frozen interfaces, loads and printer/material profile**
and returns, for each candidate **print orientation**, an optimised body plus slicer instructions
(body mesh, modifier meshes, per-region settings in an Orca 3MF), ranked by **layer-to-layer
strength and printability**, and checked against a **published, machine-checkable printability
rule catalog** at four levels: density field (V), mesh (M), real Orca toolpaths (T), physical
coupon (P). It is built largely from parts that already exist in the owner's spool-rack and
desk-dock work (G-code reader, GPU hex FEM, Orca 3MF writer, toolpath audits, screen-then-verify
search loop, keep-out solids), packaged into one reproducible pipeline.

## 2. Findings that shape everything

1. **Stiffness barely depends on orientation; strength and printability do.** Vendor data for
   PETG/ASA: E_Z/E_XY = 0.85–0.92, so directional stiffness varies ~15 %; tensile Z/XY = 0.68–0.95
   (PolyLite ASA, the production grade: 0.73). A compliance-only optimiser hardly sees orientation.
   **Orientation is ranked by the inter-layer failure index F_L, overhang/support, bed contact and
   massing**, with compliance only as a secondary column with a measured noise floor.
   *(vendor data, verified; consensus of all four reports)*
2. **Massing has a closed form.** Orca's normal shell thickness is `t(α) = max(W·sin α, T·cos α)`
   (α = slope from horizontal). With 2 walls (W = 0.806 mm from Orca's flow spacing) and 5×0.2 mm
   skins (T = 1.0 mm) it bottoms out at **0.63 mm at α ≈ 51°**. The leaning-wall layer overlap
   `f = 1 − h/(w·tan α)` is the same quantity as the overhang step, so one parameter governs both
   printability and an inter-layer strength knock-down. *(derived, numpy-checked)*
3. **Exactly 45° is not safe on this printer/slicer.** Orca put 2,421 support segments on the
   owner's 45° test wedge and none at 55°. Designs target **α ≥ 50°**. *(slicer evidence)*
4. **The one must-build compute item is a multigrid-preconditioned CG solver.** The existing Warp
   GPU hex operator is fast (157–184 M cell-matvecs/s measured on the laptop GPU, FP64-bound at
   ~87 % of FP64 peak) but its Jacobi-CG needs 9,620 iterations on the real bracket at 1.6 mm and
   fails to converge in 6,000 at 0.8 mm. *(measured)*
5. **Existing work is substantial but not packaged**: credited-material G-code reader, Warp FEM
   with contact and adaptive coarsening, Orca 3MF writer, per-object toolpath audits, receipts,
   keep-out solids, teardrop/self-support operators. Gaps: a design-time optimiser, an anisotropic
   material model (everything so far is isotropic E = 1 GPa), rules as data, orientation as a
   variable. *(code inventory)*

## 3. Decisions (settled across the four reports)

| # | Decision |
|---|---|
| D1 | **Code lives in this repo**, uv package `fdmgen`. Existing code is **ported with provenance headers and parity tests**, never imported from other repos; existing CAD builders are read through **adapters**, never edited. |
| D2 | **Two FEM roles.** *Design solver*: coarse print-frame grid, one transversely-isotropic (TI) "printed solid" card, SIMP with a floor E_min, shared element matrix × per-cell scale. *Truth solver*: real G-code material at 0.2 mm, bead-angle/bond-fraction element library, **no ersatz stiffness**, every stress sample kept. Published numbers come only from truth. |
| D3 | **The slicer generates toolpaths.** Output is body + modifiers + per-region settings (ported 3MF writer); truth reads the actual G-code back, **undoing slicer compensations** (`filament_shrink`, arc fitting) explicitly in the frame chain. |
| D4 | **Re-voxelise in the print frame for every orientation** (layers on grid planes, so the overhang filter, Z quantisation and coating work). The fixed-grid/rotated-tensor route survives as **analysis mode** (scoring a frozen design across orientations). |
| D5 | **Non-cubic design voxel 0.503 × 0.503 × 0.6 mm** (dx = dz·tan 40°) with a **5-point cross support stencil**: enforces α ≥ 50° at every azimuth (50.0° on axes, 59.3° on diagonals). The common 3×3 stencil admits 35–40° on diagonals and is banned. M- and T-level checks stay authoritative. |
| D6 | **Resolution tiers**: R1 1.6 mm screening; R2 0.503×0.503×0.6 v1a workhorse; R3 dz ≤ 0.4 (0.4×0.4×0.2 where the coating needs it) for leaders; R4 0.2 mm adaptive truth. 0.2 mm is never a design grid (≈90–148 M bbox cells, does not fit 11.5 GB). Final R2/R3 sizes are confirmed by P0 measurements. |
| D7 | **Staged optimisation.** v1a: minimax compliance over the load cases + volume + AM filter, **design field = 100 % helper density inside a fixed body whose shell comes from the slicer model for that orientation** (D12), F_L evaluated afterwards. v1b (leaders only): inclination-dependent shell coating, aggregated F_L/F_P constraints (qp-relaxed), robust formulation only in the final continuation stage. Solves per iteration: 2 (v1a, K = 2) vs 6 (v1b) vs 18 (robust). |
| D8 | **Orientation search**: F_L prescreen from one stress field per load case over directions (exactly even in d, so a hemisphere suffices for F_L), then **full-sphere printability** (overhang/support area, bed contact and stability, interface printability, discrete spin bed-fit) → Pareto filter to ≤ 24 v1a runs → leaders. No gradient-based orientation in v1. |
| D9 | **Failure criterion v1** (linear in load, three strengths): inter-layer `F_L = √((⟨σ_n⟩₊/Z_t)² + (τ/S_il)²)` on the layer plane; in-layer `F_P = σ_vM/X_t`. Tsai-Wu/Hoffman only after off-axis coupons. |
| D10 | **Material cards** carry a tier (T0 datasheet + assumptions, T1 own coupons, T2 demonstrator-validated), per-value provenance (own print / slicer-only / vendor / literature / guess), Poisson convention, positive-definiteness check, and **two modulus bases** (short-term datasheet E for strength; 1,000 MPa sustained planning E for movement gates), never mixed silently. **All filament is Polymaker (owner): T0 cards for PolyLite ASA first, then PolyLite PETG**, from Polymaker's datasheets. Strengths are reported at both corners (vendor ratio and 0.5·X_t); **design to the conservative corner** until coupons exist. |
| D11 | **E_min = 1e-6** by default; raise (≤ 1e-3) only if the multigrid benchmark needs it; recorded in every receipt; a design-vs-truth gap gate (15 %, owner-accepted) guards against reliance on ersatz stiffness. |
| D12 | **Massing primitive = body shell + 100 % helper volumes; sparse infill is never credited** (owner decision: "it basically doesn't" contribute). Printed material = the slicer's shell of the body (walls and skins, thickness `t(α)` by surface slope) ∪ **companion helper volumes** that the slicer fills at 100 % (modifier meshes), inside a body printed at 0 % infill. This is how the spool-rack E+F work already prints (4 walls, 1.6 mm skins, 0 % infill, continuous solid helper core). The optimiser's design field is the **helper field**; the body envelope becomes a design variable only in P3. Helpers deliver non-uniform wall strength and mass reduction. |
| D13 | **Rule catalog** (33 rules, stable IDs): rules (`catalog/rules/*.yaml`), calibration bindings tied to slicer-profile hashes (go STALE when a hash changes), checkers. Levels V/M/T/P; results report the highest level reached; **repairs must re-check and emit a geometry delta**. One angle convention: α from horizontal. Material strengths live in the material card, not the catalog. |
| D14 | **Interfaces are orientation-aware**: bores/seats declare orientation-dependent printable variants (teardrop crest along +Z for axes within 45° of the layer plane); an orientation with no printable variant for some interface is rejected with a message naming it. |
| D15 | **Inputs are generated from pinned sources, never retyped** (loads, nozzle temperatures, profile values). `fdmgen lint` asserts load resultants and gives plain-language errors. |
| D16 | **Honest reporting**: a verdict ladder (geometry → toolpath → simulation → coupon → printed → qualified), never a bare PASS; an "establishes / does not establish" block on every result page; fidelity-separated Pareto plots. |

## 4. Machines

| Machine (by role) | Use |
|---|---|
| **Laptop GPU workstation** (RTX 3500 Ada laptop, 11.5 GB; FP64 207 GFLOP/s measured) | inner optimisation loops R1–R3; truth solves fit (4–8 M leaves) |
| **Second workstation** (RTX 3080 Ti 12 GB, confirmed; the spool-rack GPU results came from this card) | second GPU worker: truth stage, parallel orientations. Its FP64 rate is ~2.5× the laptop's by spec (estimate, to measure) |
| **Compute box** (40 Broadwell threads, 300 GB, no GPU) | off the critical path through P2: slicing/parsing batches, RAM-heavy cases > 20 M cells, CPU multigrid only if a measured need appears. Long jobs in named tmux sessions, heads-up to its owner for multi-hour full-load runs |

**Measured (matvec benchmark, [`research/checks/bench/RESULTS.md`](research/checks/bench/RESULTS.md)):** RTX 3080 Ti ≈ 4,500 M cells/s FP32 and
≈ 416 M FP64; laptop GPU ≈ 1,400 / 238; compute box (40 threads, Numba) ≈ 61 / 63. The 3080 Ti in FP32 is ≈ 74× the compute
box, so **the second workstation's 3080 Ti is the solver workhorse, in mixed precision** (FP32 smoothers/V-cycles inside an
FP64 outer CG), and the compute box is not a solver machine.

**Why GPUs at all:** they are not required. The expensive step is 2–6 elasticity solves per optimiser iteration on a
few million cells, × hundreds of iterations × dozens of orientations. The validated solver from the spool-rack work is
GPU code (NVIDIA Warp) and measures ~160–180 M cell-operations/s on the laptop GPU, so it is the default. Consumer GPUs
run FP64 at 1/64–1/69 of FP32, which narrows their lead (hence FP32 smoothers). A matrix-free CPU multigrid on the
compute box might reach 0.3–0.5× per solve (unmeasured guess) while running many orientations in parallel; benchmark
B8 measures that instead of assuming it away.

## 5. Roadmap (durations are guesses for one person plus agents, part-time)

### P0 — foundations, parity, and the solver gate (~3–5 weeks)
Build: repo skeleton, schemas, receipts, runner; canonical G-code parser; ports (credited-material reader, 3MF writer,
GPU hex FEM + contact + adaptive, interface loads, settings checker); bracket adapter and `problem.yaml`;
**structured geometric MG-PCG (new)**; vectorised mesh build and voxeliser; `fdmgen lint`.

Acceptance:
- **A parser parity**: credited volume from the archived slice matches **70,979.8020219935 mm³** to ≤ 1e-9 relative.
- **B arcs**: arc-fitted vs non-arc slices agree within 0.1 % volume; the library call raises on footer mismatch.
- **C FEM parity** on pinned Warp 1.17.0 (fixtures, scikit-fem agreement ~3e-16, rotated-TI isotropic limit ≤ 1e-12,
  Mandel↔solver shear-order permutation test).
- **D modifier spike**: which settings an Orca 2.4.2 modifier can override via 3MF (decides P3's massing outputs).
- **E determinism**; **F shrink fixture** (`filament_shrink` 100 % vs 99.46 % map to the same design occupancy);
  **G load parity** (pinned interface loads to 1e-12; resultant [0, −117.72, 0] N).
- **H solver gate (exit criterion)**: MG-PCG ≤ 40 iterations to 1e-6 on the real bracket across E_min ∈ {1e-6, 1e-4, 1e-3}
  and TI ratios 0.7–1, recording the zero-ersatz compliance gap; ≤ 3 s per optimiser iteration at 0.8 mm.
  **No-go → screen at R1 only and re-plan.**
- **I** vectorised mesh build < 30 s at 4–8 M cells; voxeliser < 5 s at 0.4 mm.
- Plus benchmarks B0–B10 (Warp version parity, FP32 smoothers, VRAM, thermal throttling, covariance tests).

### P1 — orientation analysis of existing parts (~2–3 weeks) — *useful immediately for "simulate parts I've already designed"*
Analysis mode on frozen designs (spool bracket G and E13, one dock part): F_L prescreen, per-orientation interface and
printability rules, TI stiffness score, slice + truth for the top few. Output: the ranked-orientation table (Pareto,
fidelity-marked, with a designer-decision field), intervals over the material card's corners.
Acceptance: mechanics invariants pass; known answer (uniaxial bar: F_L = σ/Z_t standing, 0 flat; bracket: the
existing flat-on-side pose has the lowest max F_L); prescreen top-5 agrees with full solves (disagreements published);
chosen orientations pass the 50° M check and zero support in forbidden regions.
**Start the coupon plate** (Z-tension, inter-layer shear, overhang ladder 40–60°, bridge ladder 6–40 mm).
Publish: "orientation report for existing parts" page, limitations first. Catalog v0.1.

### P2 — helper-volume optimisation MVP on the spool bracket (~4–6 weeks)
v1a at R2 then leaders at R3: **optimise where 100 % helper volumes go inside the fixed G / E+F body** (4 walls, 1.6 mm skins,
0 % infill), per orientation, with the body's shell taken from the slicer model for that orientation; TI printed-solid card for
shell and helpers; SIMP, density filter, 5-point AM filter on the helper field (helper roofs must self-support inside the void),
helper rules MOD-001 (boundaries ≥ 2w apart or overlapping ≥ 2w, bonded to credited material), volume, both load cases;
top orientations from P1 plus three named anchor poses; F_L post hoc; full extract → slice → truth on leaders.
Acceptance: solver/optimiser parity (reference density within 1e-6, reference run within 2 %/0.1 %, grid-symmetry
covariance 1e-10); orientation **noise floor** measured (repeat runs) and a monotone-trend plumbing test; exact
interfaces (≤ 1e-3 mm³ symmetric difference); printable (50° M check, zero support in forbidden regions, settings
check); helpers exported as Orca modifier meshes at 100 % and verified on the actual slice; an **honesty table** vs the existing hand designs on the same truth pipeline, same pinned loads, same card,
stated modulus basis, including the measured design-vs-truth gap.
Estimated compute (bracket, two load cases, laptop GPU, *estimate*): R0–R2 ≈ 0.5–1.5 h; with R3 + R4 on one leader ≈ 3–8 h.
Publish: MVP page.

### P3 — body envelope + helpers, inter-layer constraint, second part (~5–8 weeks)
Co-optimise the body envelope with the helpers; sub-cell shell model from `t(α)` calibrated against 0.2 mm truth; body + modifiers + per-region settings (as far as
P0-D allows); aggregated F_L constraint; a second part where orientation is genuinely contested (candidates: a dock
arm/clamp, the wall-mount arm, or a collaborator's part).
Acceptance: emulator within 5 % of Orca credited material per class (provisional band); modifier round trip; on the
second part, isotropic and anisotropic runs choose differently and truth confirms the anisotropic choice across the
card interval, or that result is published. Catalog v0.5 after the first calibration plate per material.

### P4 — coupons, strength and creep calibration, one physical test (~4–8 weeks, printer-bound)
**Test rig: build one** (owner has no testing machine): a printed-frame tensile/creep rig with a calibrated load cell
(checked against known masses), a lead-screw or dead-weight lever drive, and displacement by dial indicator or camera-based
image correlation; designed and calibrated in P1 so it is ready for P4 (its own issue).
**Creep is in scope** (owner): sustained-load coupons at ~85 °F, Z vs XY, to replace the assumed sustained-modulus
anisotropy ratio.
Coupons C1–C7 (incl. a 45° off-axis coupon, the most informative single extra test); cards move to T1 via a
"virtual coupon" fit through the same truth pipeline; one optimised part and one control printed and loaded against
**pre-registered** predictions. Acceptance: measured stiffness inside the predicted band and failure location in a
predicted critical region, or the miss is published.

### P5 — generalisation (ongoing)
`fdmgen run`; documented STEP + YAML authoring for outside users; catalog v1.0 when no binding value is a guess; two
more parts. Acceptance: someone who didn't write the code takes a new part to a sliced 3MF and report from the docs.

## 6. Top risks

| Risk | De-risk |
|---|---|
| No measured anisotropic data, yet strength ratios drive orientation | T0 intervals everywhere; coupon plate starts in P1 |
| Design model vs printed truth disagree (voxel omission 8 / 16 / 33 % at 0.2 / 0.4 / 0.8 mm) | measure the gap in P2 before investing in P3's emulator; fidelity tag on every metric |
| Solver convergence and scale | P0-H gate before any optimiser work |
| Slicer can't express the intended massing | P0-D spike; pinned Orca + profile hashes; version bump = re-baseline |
| Frame/scale/compensation bugs | one frame table, explicit compensation transforms, round-trip fixtures |
| Scope creep (stress-constrained robust TO, gradient orientation, multi-axis) | v1a/v1b split; non-goals listed |
| Overclaiming | verdict ladder, establishes/does-not-establish blocks |

## 7. Owner answers (recorded) and remaining questions

| # | Question | Answer |
|---|---|---|
| 1 | Universal testing machine? | **No; build one** → P1 issue for a DIY tensile/creep rig |
| 2 | Filament grades? | **Polymaker everything** (PolyLite ASA, PolyLite PETG) |
| 3 | Licence? | **Yes**: CC-BY-4.0 for docs and data, MIT for code |
| 4 | Creep in scope? | **Yes** → sustained-load coupons in P4 |
| 5 | P3 second part? | **Open** (candidates: dock arm/clamp, wall-mount arm, a collaborator's part) |
| 6 | Sparse-infill credit? | **No.** Infill basically doesn't contribute; the design primitive is 100 % helper volumes (D12) |
| 7 | 15 % design-vs-truth gap? | **Accepted** |

## 8. Process record

Round 1: four independent reports. Round 2: each reviewed the other three (12 reviews). Round 3: each author
integrated the three reviews of their own report, with a disposition table (architecture: 45 findings, 40 accepted,
5 partly; mechanics: 37, 36 accepted; compute: 37, 30 accepted, 6 partly, 1 rejected; workflow: 32, 31 accepted,
1 partly). This plan merges the four finals and resolves their open disputes as recorded in §3.
