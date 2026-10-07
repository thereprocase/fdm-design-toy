# Sauron (final): mechanics and mathematics of orientation-driven generative design for FDM

Round 3: this report integrates the three cross-reviews (`reviews/gandalf-on-sauron.md`, `reviews/legolas-on-sauron.md`,
`reviews/frodo-on-sauron.md`) and my own round-2 self-corrections. It is self-contained. `sauron.md` is kept unchanged
as the round-1 record. Written 2026-10-07.

**Scope:** the material model in the print frame, tensor rotation, failure criteria, the topology-optimisation (TO)
formulation (split into v1a and v1b) including massing and overhang, toolpath-aware re-analysis, coupon calibration,
and the invariants the implementation must test.

**Executable checks** (pure numpy, each under 1 s) in `D:\Code\Models\fdm-gen\scratch\sauron\`:

| Script | What it checks |
|---|---|
| `tensor_checks.py` | Rotation conventions, bug magnitudes, directional modulus, dC/dθ |
| `laminate_checks.py` | Exact layered homogenisation (its shell/overlap section is superseded by `stencil_checks.py`) |
| `stencil_checks.py` (new in round 3) | Overhang-stencil acceptance angle versus azimuth, the Orca flow-spacing shell model, leaning-wall overlap in the slope-from-horizontal convention |

**Citation key.**
- **[v]** = verified by web search or by reading the source in this session.
- **[m]** = from memory; verify the bibliographic details before quoting.
- In round 3 I converted the load-bearing formulation references (Langelaar 2016, Wang–Lazarov–Sigmund 2011,
  Bruggi 2008, Qian 2017, Pellens 2019) to [v].

**Conventions used throughout** (agreed with Frodo D3):
- **α = slope of a surface from horizontal**: 0 = ceiling, 90 = vertical wall. When the vertical convention is
  needed it is written in brackets, e.g. "α = 50° (40° from vertical)".
- Units are N, mm, MPa and mJ.
- Rule widths are in units of the line width **w** and the layer height **h**.

---

## 0. Executive summary

1. **For PETG and ASA, stiffness anisotropy is small, but strength anisotropy and massing effects are large.**
   - Vendor data: E_Z/E_XY = 0.85–0.92, while tensile strength Z/XY = 0.68–0.95 depending on grade and vendor
     (§2.2). For PolyLite ASA, the grade the user actually prints, the strength ratio is 0.73.
   - Directional stiffness for a transversely isotropic (TI) card at these ratios varies by only about 15% (§2.5), so
     a compliance-only optimiser hardly sees orientation.
   - **Orientation ranking in v1 therefore uses the inter-layer failure index F_L and the overhang/support/bed
     metrics, not compliance** (§4.9).
2. **Orientation-dependent massing has a closed form:** `t(α) = max(W·sin α, T·cos α)`.
   - W is the wall-shell thickness from Orca's flow spacing; T is the skin thickness.
   - With 2 walls (outer 0.42, inner 0.45) and 5 × 0.2 mm skins: W = 0.806 mm, T = 1.0 mm, and the shell bottoms
     out at **t_min = 0.63 mm at α = 51°** (§4.5).
   - The leaning-wall layer overlap is `f = 1 − h/(w·tan α)`: 0.60 at α = 50°, 0.52 at 45°, and zero at 25.5°.
     This is the same quantity as Frodo's overhang step k_step (k = 1 − f), so one parameter `overlap_min` governs
     both printability and an inter-layer strength knock-down (§2.7).
3. **The TO is staged by resolution and feature set.** This accepts Gandalf's and Legolas's critical findings; a
   0.2 mm TO grid is not affordable.

   | Stage | What it does |
   |---|---|
   | S0 prescreen | Analysis only, full sphere of directions, vector score |
   | v1a | SIMP compliance + AM filter, on a print-frame grid with dz = 0.6 mm and dx = 0.50 mm; body treated as fully solid; F_L evaluated after the fact |
   | v1b | Leaders only, dz ≤ 0.4 mm: inclination-dependent shell coating, aggregated F_L constraint, robust formulation in the last continuation stage |
   | Truth | 0.2 mm, zero ersatz stiffness, material mapped from the real G-code |

4. **Overhang margin (Frodo's critical finding):** Orca supported the exactly-45° wedge (2,421 support segments).
   - Fix: a 5-point cross support stencil with voxel aspect **dx = dz·tan 40°** enforces α ≥ 50° at every azimuth
     (50.0° on the grid axes, 59.3° on diagonals).
   - Layers stay on grid planes because dz is still a multiple of h.
   - The usual 3 × 3 stencil is unsafe: it admits 35.3° (cubic voxels) or 40.1° (tan 40° aspect) on diagonals (§4.7).
5. **Rotating the stiffness tensor:** use Mandel notation (Q orthogonal, C' = Q C Q^T), and convert to the solver's
   Voigt order only at the boundary.
   - The common bugs measured 55–484 MPa of error on a ~2,000 MPa card.
   - `gpu_hex.py` orders shear as (xy, yz, xz), so a permutation is mandatory (§2.4).
   - **At the design stage, with a TI card on a print-frame grid, no rotation of C is needed at all.** Every design
     cell is a scalar multiple of one Ke, so `gpu_hex`'s shared-Ke kernel survives (§5.4).
6. **Failure (v1):** a two-mode index that scales linearly with load.
   - Inter-layer mode: `F_L = √((⟨σ_n⟩₊/Z_t)² + (τ/S_il)²)` on the layer plane.
   - In-layer mode: `F_P = σ_vM/X_t`.
   - Needs three strengths. In v1a it is evaluated after the fact; in v1b it becomes an aggregated constraint (§3).
7. **Two modulus bases must never be mixed silently.** The short-term datasheet E (1,810–2,780 MPa) feeds strength
   and ratios. Spool-rack's sustained "effective planning" E = 1,000 MPa feeds the movement gates. The anisotropy
   ratios for the sustained basis are an assumption (§2.3).
8. **Calibration is a "virtual coupon" fit.** Coupons are simulated through the same truth pipeline (same mapper,
   same voxel convention) and the card is fitted to their measured response. The card and the FE geometry therefore
   share one convention by construction (§6).
9. **The datasheet cards are not internally consistent.** Bending modulus versus tensile modulus, flexural Z versus
   tensile Z, annealed specimens, and vendor process conditions all disagree. Absolute strength claims need our own
   coupons, and **whether a testing machine is available is the first question for the user** (§6, §10).

### Decisions (final proposal)

| # | Decision |
|---|---|
| D1 | One merged frame table (§1): design D → installed I → print P → plate B → gcode G, plus the per-element bead frame M. Matrices are named `R_TO_FROM`. Tensors are Mandel internally and Voigt (permuted) only at solver I/O. Slicer compensations (filament_shrink etc.) are explicit transforms in the chain. |
| D2 | Design-stage material: homogenised **TI about print Z**, one "printed solid" card shared by walls, skins and 100% helpers. Truth stage: per-element orthotropic, with bead angle and bond fraction from the G-code. Sparse-infill credit is a **per-problem switch**: off for 0%-infill problems such as spool-rack G2, and on with an infill card (§4.10) for problems like D9-P5 (40% gyroid). |
| D3 | Failure: the two-mode, degree-1 index (§3.2). The card holds Z_t and S_il, and the catalog rule STR-001 references the card (single source of truth). Tsai-Wu/Hoffman only after off-axis coupons. |
| D4 | **Resolution ladder** (§4.1): S0 fixed part-frame grid at 1.6/0.8 mm (analysis only); v1a print-frame dz = 0.6, dx = 0.50 mm; v1b dz = 0.4 or 0.2 on a masked leader domain; truth at 0.2 mm. Every TO grid is re-voxelised per orientation with dz a multiple of h. |
| D5 | Massing: v1a treats the whole body as 100% printed solid (faithful, since body = helper). v1b adds the **inclination-dependent erosion coating** (§4.5), whose shell thickness follows t(α) at sub-cell precision, plus a helper field s. Resolved erosion is used only at 0.2 mm, as a check. |
| D6 | Overhang: Langelaar AM filter on the **printed-material field**, with a 5-point cross stencil and aspect dx = dz·tan(90° − α_min). Default α_min = 50° (40° from vertical), the agreed margin over Orca's 45° threshold. M- and T-level checks are authoritative. |
| D7 | v1a: minimax compliance over K load cases + volume + AM filter. **F_L post hoc.** v1b adds the aggregated F_L/F_P constraints with qp-relaxation, and the robust formulation in the final continuation stage only. |
| D8 | Orientation: S0 prescreen over a ~200-point full-sphere Fibonacci set, giving a **vector score** (F_L aggregate, support-area estimate, bed contact and stability, interface printability, discrete spin bed-fit). Pareto filter to ≤ 24 v1a runs; repeat runs set a noise floor. |
| D9 | No reported number comes from the TO model. Every result passes through threshold → CAD → Orca slice → toolpath map → zero-ersatz truth solve, and the design-versus-truth gap is gated (I19). |
| D10 | Cards carry a card-level tier (**T0** datasheet + assumptions, **T1** own coupons, **T2** demonstrator-validated) and Frodo's per-value provenance tags (U/S/V/L/H). Cards are process-locked by profile hash via Frodo's PROC-001 mechanism. |
| D11 | E_min/E_0 = 1e-6 by default. Raise it (≤ 1e-3) only if benchmark B2 shows more than 40 MG-PCG iterations, and record E_min in every receipt. I19 guards against any reliance on ersatz stiffness. |
| D12 | The invariants of §7 gate results. I1–I15 and I18–I23 gate v1a (I14 only for the blocks v1a contains); I16–I17 gate v1b. |

---

## 1. Frames, notation, units

### 1.1 Merged frame table (Gandalf F5; my round-2 reviews of Gandalf and Frodo)

| Frame | Definition | Authored or derived | Spool-rack / tool counterpart |
|---|---|---|---|
| **D** design/part | CAD frame of the supplied geometry; keep-ins, keep-outs | Authored | 3MF "model" coordinates; Frodo `design`; Gandalf `part` |
| **I** installed | Service frame for loads and contract coordinates (e.g. X out of the wall, Y up) | Authored (`x_I = R_ID x_D + t_ID`) | `plastic_shape` `model_to_installed`; INTERFACE-CONTRACT coordinates |
| **P** print | Per orientation candidate. +Z = build direction; origin at the part's minimum on the bed plane; **before** slicer placement | Derived from (d, ψ) | Gandalf `print`; Frodo `print` |
| **B** plate/bed | Orca bed coordinates **after** arrange/placement, **including any spin Orca applied** | Read back from the sliced 3MF item transform, never assumed | Frodo `plate`; Gandalf `bed` |
| **G** gcode | Coordinates in the G-code: B minus the P1S nozzle offset (0, 2) mm, and **scaled by any `filament_shrink` compensation** | Read from the effective settings | `plastic_shape`: `model = (gcode + offset − xf[3]) @ xf[:3].T` |
| **M** bead | Per element: e1 = bead tangent t, e2 = e_z × t, e3 = e_z | Derived from toolpaths | — |

**Placement.** The placement is `x_P = R_PD x_D + t_PD`, and the build direction in D is `d = R_PD^T e_z`.

To build R_PD from (d, ψ): rotate d onto +Z with the Rodrigues formula, then spin by ψ about Z. **Singular case:**
d = −e_z has no unique Rodrigues axis. Handle it explicitly with a 180° turn about X, and test it (I2).

**Slicer compensation in the chain** (new; found in round 2). The PolyLite ASA calibrated profile the user prints with
sets `filament_shrink = 99.46%` (print-log P-0006…P-0015, `D9-P5/profiles/filament-polylite-asa-calibrated.json`).

- Orca scales XY by about 1/0.9946 ≈ 1.0054. That scaling is not in the 3MF item transform, so `plastic_shape`'s
  orthonormality assertion cannot see it.
- Unless it is undone, mapped material is about 0.5 mm oversize over a 100 mm half-length, far beyond the 0.03 mm
  tolerance of the slicer-mapping audit.
- The G → B step must read `filament_shrink`, `xy_hole_compensation` and `elefant_foot_compensation` from the
  effective config and invert them. Otherwise it must declare the truth geometry "as-printed-hot".
- The scaling centre must be established with a fixture (I21), not assumed.

### 1.2 Notation

- **Canonical order:** (11, 22, 33, 23, 13, 12).
- **Voigt:** `σ_V = [σ11, σ22, σ33, σ23, σ13, σ12]`, `ε_V = [ε11, ε22, ε33, γ23, γ13, γ12]` with γ = 2ε.
- **Mandel:** `σ_M = W σ_V`, `ε_M = W⁻¹ ε_V`, `C_M = W C_V W`, with `W = diag(1, 1, 1, √2, √2, √2)`. Strain energy is
  equal in both forms; checked to 4e-12.
- **`gpu_hex` order** (`gpu_hex.py`, B-matrix rows; independently confirmed by Gandalf): (xx, yy, zz, xy, yz, xz) with
  engineering shear. The permutation from canonical order is `[0, 1, 2, 5, 3, 4]`, applied as `C_gpu = P C_V P^T`.
- **Poisson convention:** `ν_ij = −ε_j/ε_i` under σ_i, with reciprocity `ν_ij/E_i = ν_ji/E_j`. Every card states this.

---

## 2. Material model

### 2.1 Hierarchy

| Scale | Object | Symmetry | Notes |
|---|---|---|---|
| Bead | Extruded road, stadium cross-section | Orthotropic in M (9 constants) | Inter-layer anisotropy exceeds in-layer anisotropy ([PLA orthotropy, Compos. Struct. 2024](https://www.sciencedirect.com/science/article/pii/S026382312400243X) [v]) |
| Region | Walls (bead along the contour) | Orthotropic, e1 = contour tangent | 2–4 loops; bead-on-bead inter-layer bond |
| Region | Solid raster (skins, internal solid, 100% helpers), ±45° alternating | The two-layer stack is tetragonal (invariant under Rz(90°), not under Rz(45°)) | §2.6 |
| Region | Sparse infill | Cellular solid; depends on pattern | Per-problem switch (D2, §4.10) |
| Region | Thick and sacrificial bridges | — | Zero structural and bond credit (house rule; `plastic_shape` `structural` flag) |
| Part (design stage) | Homogenised printed solid | **TI about print Z** (5 constants) | In-plane anisotropy is averaged by ±45° skins and contour walls, and there is no in-plane data |

References:
- Ahn et al. 2002, *RPJ* 8(4):248 [m]; Rodriguez et al. 2003, *RPJ* 9(4):219 [m].
- [Casavola et al. 2016, *Mater. Des.* 90:453](https://www.sciencedirect.com/science/article/abs/pii/S0264127515307516) [v].
- [Zou et al. 2016, *Compos. B* 99:506](https://www.semanticscholar.org/paper/Isotropic-and-anisotropic-elasticity-and-yielding-Zou-Xia/744752e7b5f209c8b31391568114c9a60abf7fb3) [v].
- [Kiendl & Gao 2020, *Compos. B* 180:107562](https://www.researchgate.net/publication/336817681_Controlling_toughness_and_strength_of_FDM_3D-printed_PLA_components_through_the_raster_layup) [v].
- Weld physics: Seppala et al. 2017 *Soft Matter* 13:6761 [m]; Coogan & Kazmer 2017 *RPJ* 23(2):414 [m]. These
  explain why the cards are process-locked.

### 2.2 Data (what is known)

**What the user actually prints** (Frodo F3; checked in `5680-dock/docs/prints/print-log.json`):
- **Polymaker PolyLite ASA** with the "Repro – ASA – Polymaker PolyLite – Calibrated" profile: 260 °C, flow 0.93,
  `filament_shrink` 99.46%, used for P-0006…P-0015.
- **PETG** of unrecorded brand with the "Repro Generic PETG – 0.4 nozzle – Starter" profile: flow 0.95, shrink 100%,
  used for P-0001…P-0005.

| Grade (source) | E_XY | E_Z | E_Z/E_XY | σt XY | σt Z | Z/XY | Flex. mod. XY / Z | Flex. str. XY / Z | Specimen notes |
|---|---|---|---|---|---|---|---|---|---|
| **PolyLite ASA** (spool-rack `designs/closed-wall-e6/material-reference-data.json`, vendor TDS V5.4) | 2379 | — | — | 43.8 | 32 | **0.73** | **3206** / — | — | Vendor conditions; E_Z not published |
| Polymaker PETG (same file) | 2311 | — | — | 47.96 | 45.71 | 0.95 | 2277 / — | — | Vendor conditions |
| Bambu ASA ([TDS V3.0](https://solidprint3d.ie/wp-content/uploads/2024/03/Bambu-Lab-ASA-Filament-Technical-Data-Sheet.pdf) [v]) | 2450 ± 270 | 2120 ± 260 | 0.87 | 37 ± 3 | 31 ± 4 | 0.84 | 1920 / 1650 | 65 / 40 | 260 °C, 200 mm/s; **annealed 80 °C 12 h** |
| Bambu PETG HF ([TDS V1.0](https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf) [v]) | 1810 ± 190 | 1540 ± 130 | 0.85 | 34 ± 4 | 23 ± 4 | 0.68 | 2050 / 1810 | 64 / 48 | 255 °C, 200 mm/s; **annealed 75 °C 8 h** |
| Bambu PETG Basic ([TDS V3.0](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf) [v]) | 2780 ± 65 | 2550 ± 100 | 0.92 | 51 ± 1 | 35 ± 6 | 0.69 | **1950** / 1740 | 75 / 56 | X1C, 150 mm/s; annealing not stated |

All entries are tier V (vendor). Elongation at break roughly halves in Z: Bambu PETG HF 8.6% → 5.1%, Bambu ASA
9.2% → 4.6%. Z failure is interface-dominated and brittle, which favours a linear-elastic Z criterion.

**What these numbers establish:**
- E_Z/E_XY ≈ 0.85–0.92 (Bambu only).
- Strength Z/XY between 0.68 and 0.95 across grades, depending on the grade. For the user's ASA the value is 0.73.

**What they do not establish:**
- Any shear modulus, any Poisson ratio, S_il, Z compressive strength, or the in-layer bead-transverse strength.
- Behaviour under the user's profile (flow 0.93, the user's speeds, a P1S chamber that is not actively heated, while
  Bambu specifies 45–60 °C for ASA).
- As-printed properties for the annealed Bambu specimens.

**Inconsistencies within the datasheets:**
- Bending modulus is below tensile modulus for Bambu PETG Basic and ASA, but far above it for PolyLite ASA
  (3206 vs 2379).
- Z flexural strength is 1.3–2.1 × Z tensile strength (Bambu sheets).

Possible causes are layup or wall fraction, fixture compliance, the stress-gradient/size effect, or ambiguous
specimen orientation. None is confirmed. **Never calibrate Z_t from flexure.**

**Vendor printability figures** (Bambu "max overhang ~70°", "max bridging ~30/40 mm") are tier V for Bambu grades and
profiles. They are **not** optimiser defaults (Frodo F2). Overhang and bridge limits come from Frodo's catalog,
calibrated by coupons.

### 2.3 Material cards: T0 values and the two modulus bases

TI card, 5 independent constants: E_p, E_z, ν_p, ν_pz, G_z, with G_p = E_p/(2(1 + ν_p)).

**Positive definiteness** must be checked at load: `1 − ν_p − 2 ν_pz² E_z/E_p > 0`, together with E, G > 0 and
|ν_p| < 1.

**Two modulus bases** (round-2 self-correction):

| Basis | Value | Used for | Anisotropy ratio |
|---|---|---|---|
| `short_term` | Datasheet E (ASA 2379–2450; PETG 1810–2780 by grade) | Strength evaluation, coupon calibration, stiffness *ratios* | Datasheet (T0) or coupons (T1) |
| `sustained_effective` | **1,000 MPa** spool-rack planning value (G2-BRIEF: "not a demonstrated lifetime law") | Movement gates (4 mm bracket, 1 mm delta) at sustained 85 °F | **Assumed equal** to the short-term ratio (no anisotropic creep data). Flag as an assumption in every report |

For force-controlled linear elasticity with uniformly scaled C, stresses do not depend on the basis. Displacements
scale as 1/E. The exception is contact with a nonzero gap, where the active set depends on displacement magnitude
and so on the basis.

**T0 cards (relative studies only; report results at the bracket corners).**

*PolyLite ASA, built first* because it is the user's production grade:

| Constant | Value | Basis / tier |
|---|---|---|
| E_p (short-term) | 2379 MPa | Vendor TDS, V |
| E_z | 0.87 E_p (bracket 0.85–0.92) | Bambu ASA ratio, V (another grade) |
| ν_p, ν_pz | 0.38, 0.36 (bracket 0.33–0.40) | H |
| G_z | 0.32 E_z (bracket 0.20–0.36) | H |
| X_t | 43.8 MPa | V |
| Z_t | 32 MPa (vendor ratio 0.73); **lower corner 0.5·X_t = 21.9 MPa** for as-printed and unknown conditions | V / H |
| S_il | Bracket 0.5–1.0 × Z_t | H |

*PETG:* the grade is unknown. Use the bracket over the Bambu HF / Bambu Basic / Polymaker values above until the user
confirms the grade (§10).

### 2.4 Rotating the stiffness tensor

For `A' = R A R^T`, the Mandel vector transforms as `a' = Q(R) a`, with `Q_IJ = B_I : (R B_J R^T)` where B_I is the
orthonormal Mandel basis. Explicitly, with normal indices i, j and shear pairs (k, l):

```
Q[i, j] = R_ij²
Q[i, (kl)] = √2 R_ik R_il
Q[(kl), j] = √2 R_kj R_lj
Q[(ij), (kl)] = R_ik R_jl + R_il R_jk
```

- **Q is orthogonal**, so `C'_M = Q C_M Q^T` and Mandel eigenvalues are invariant. Checked: |QQ^T − I| ≈ 1e-15; the
  result matches the 4th-order einsum rotation to 1e-12.
- **Voigt form:** `T_σ = W⁻¹QW`, `T_ε = WQW⁻¹ = T_σ^{-T}`, `C'_V = T_σ C_V T_σ^T`. This matches the Mandel route to
  1e-12.
- **Which R:** `C^P = Q(R_PM) C^M Q(R_PM)^T` for a bead card. For a mesh in the design frame,
  `C^D = Q(R_PD^T R_PM) C^M Q(·)^T`.

**Measured bug magnitudes** (card E1/E2/E3 = 1810/1650/1540 MPa, `tensor_checks.py`):

| Bug | Max error |
|---|---|
| Mandel Q applied to a Voigt C | 239–484 MPa |
| Inverse rotation (R vs R^T) | 55–133 MPa |
| Canonical C passed to `gpu_hex` without permutation | G12/G23/G13 swapped |
| Mandel-stored shear fed to a criterion without dividing by √2 | 41% overestimate of τ |

**Derivative:** `dC/dθ = dQ C Q^T + Q C dQ^T` with dR = KR. Checked against finite differences: relative error 2e-9.

**Where rotation is actually needed** (simplification from Gandalf F4):
- **Not** at the design stage. With a TI card about print Z on a print-frame grid, C^P is the unrotated card for every
  orientation; the orientation lives entirely in the re-voxelised geometry and loads.
- It is needed in three places only:
  - (a) S0 analysis mode on a fixed part-frame grid;
  - (b) truth-stage bead frames;
  - (c) reporting stresses in D or I.

### 2.5 How build direction and raster enter

- **Build direction d (2 DOF)** is the TI symmetry axis and the normal of every inter-layer plane. For the elastic C,
  d and −d are equivalent. For printability they are **not** (§4.9).
- **Directional modulus**, T0 PETG-HF-like card, using `1/E(n) = (n⊗n) : S : (n⊗n)`:

  | Angle from layer plane | 0° | 15° | 30° | 45° | 60° | 75° | 90° |
  |---|---|---|---|---|---|---|---|
  | E(n), MPa | 1810 | 1764 | 1667 | 1582 | 1542 | 1537 | 1540 |

  That is a 15% spread. The PolyLite ASA T0 card (ratio 0.87) gives about 13%.
- **Spin ψ and raster** enter only through bead-level orthotropy, which is not modelled at the design stage. Spin is
  still a **printability feasibility variable** (bed fit, exclusion zone, warp diagonal, seam). It is checked
  discretely at candidate generation (Frodo F5), not inside the solve.

### 2.6 Layered homogenisation and multigrid coarse levels

For bonded layers normal to z, the in-plane strains (e11, e22, e12) and the out-of-plane stresses (s33, s23, s13) are
continuous across layers. Average the partial inverse

```
M = [[C_aa − C_ab C_bb⁻¹ C_ba,  C_ab C_bb⁻¹],
     [−C_bb⁻¹ C_ba,             C_bb⁻¹    ]]
```

and then undo the partial inversion (Sun & Li 1988,
[*J. Compos. Mater.* 22(7):629](https://journals.sagepub.com/doi/abs/10.1177/002199838802200703) [v];
`laminate_checks.py`, round-trip 1e-13).

For a ±45° stack the exact result and the Voigt average differ by less than 0.1% at PETG/ASA anisotropy. Use the
exact form anyway: it is free.

**Where the exact form is required:**
- (a) Adaptive coarsening (`ADAPTIVE-MESH.md` merges 2 layers per coarse cell).
- (b) **Geometric-multigrid coarse levels** in the truth stage (Legolas F8). At 0.2 mm the ±45° alternation is resolved
  explicitly and oscillates in z, so rediscretised coarse operators must use this homogenisation, or Galerkin coarse
  operators must be used. Test the iteration counts on a ±45° stack (Legolas B2).

### 2.7 Inter-layer weakness: geometry built in

1. **Stadium bead.** Slic3r/Orca use the flow area `h(w − h(1 − π/4))`: 0.0754 mm² at w = 0.42, h = 0.2, against
   w·h = 0.084. Flow spacing is `s = w − h(1 − π/4)`: 0.377 mm at w = 0.42 and 0.407 mm at w = 0.45.
   - The flat contact width between stacked beads is nominally w − h = 0.22 mm, i.e. 52% of nominal width.
   - Squish and reheating enlarge the real weld.
   - The truth domain does not model the neck. Section 6 handles this by calibrating through the same pipeline
     ("virtual coupon"), so the neck is absorbed consistently into the inter-layer constants.
2. **Leaning-wall overlap** (slope α from horizontal): the outer wall steps out by h/tan α per layer, giving
   `f(α) = max(0, 1 − h/(w·tan α))` (`stencil_checks.py`, w = 0.42):

   | h | α = 60° | 50° | 45° | 40° | 35° | 30° | Zero at |
   |---|---|---|---|---|---|---|---|
   | 0.12 | 0.84 | 0.76 | 0.71 | 0.66 | 0.59 | 0.51 | 15.9° |
   | 0.20 | 0.73 | 0.60 | 0.52 | 0.43 | 0.32 | 0.18 | 25.5° |
   | 0.28 | 0.62 | 0.44 | 0.33 | 0.21 | 0.05 | 0 | 33.7° |

   - **Shared parameter with Frodo (F6):** his overhang step `k_step = h/(w tan α)` equals 1 − f. The catalog
     parameter becomes `overlap_min = f_min`, used for printability (OVH-002) and for the strength hypothesis.
   - α_min = 50° at h = 0.2 means f_min = 0.60 (k = 0.40, which is exactly Frodo's ASA value).
   - **Hypothesis (coupon C5):** inter-layer strength on overhang walls scales as `g(f) = f`.
3. **Smeared, not cohesive.** The inter-layer weakness is put into E_z, G_z, Z_t and S_il, scaled per element by the
   mapped bond fraction b (§5.3).

---

## 3. Failure criteria and stress measures

### 3.1 Options

| Criterion | Constants | Fit for our data budget |
|---|---|---|
| Max stress (M frame) | 9 or more | No interaction; too many constants |
| Tsai-Hill / Hill48 | X, Y, Z, S's | Counts interface compression as damage (wrong for welds) |
| Tsai-Wu (Tsai & Wu 1971 [m]) | Needs F12 from biaxial tests | Not measurable with our coupons. Used for FDM TO by [Mirzendehdel et al. 2018](https://par.nsf.gov/servlets/purl/10057716) [v] and [Kundu & Zhang 2023](https://doi.org/10.1016/j.addma.2023.103730) [v] |
| Hoffman [m] | Uniaxial strengths only; F12 implied | Interaction is implied, not measured. [Zou & Xia 2023, *JCDE* 10(2):892](https://academic.oup.com/jcde/article/10/2/892/7110403) [v] |
| **Hashin-type interface mode** (Hashin 1980 [m]) | Z_t, S_il | Physically separate mode; interface compression not counted. **Chosen** |

### 3.2 v1 criterion

With n = layer normal (print Z expressed in the stress frame; in D, n = d), traction `t = σn`,
`σ_n = n·σ·n`, `τ = |t − σ_n n|`:

```
F_L = √( (⟨σ_n⟩₊ / Z_t,eff)² + (τ / S_il,eff)² )      inter-layer (interface)
F_P = σ_vM / X_t                                       in-layer
F   = max(F_L, F_P);   reserve factor = 1/F
```

- **Degree-1 homogeneous:** F scales linearly with load.
- **Smoothing for gradients:** `⟨x⟩₊ → (x + √(x² + δ²))/2`, with δ ≈ 1e-3·Z_t.
- **Effective strengths:** `Z_t,eff = g(b)·Z_t` and `S_il,eff = g(b)·S_il`, with b = 1 at the design stage and
  mapped b at the truth stage.
- **STR-001 binding (with Frodo):** the catalog rule references the card's Z_t and S_il (one source of truth;
  Gandalf-on-Frodo F1). Frodo's `z_fraction = 0.5` becomes the T0 **lower corner** for Z_t, not a separate value.
  Results are reported at both the vendor-ratio corner and the 0.5 corner.
- **Why the 45° off-axis coupon matters most:** under uniaxial stress at angle φ from the layer plane (X_t = 34,
  Z_t = 23), predicted strength at 45° is 23.6 MPa if S_il = 15 and 30.3 MPa if S_il = 25. That 28% spread makes one
  45° coupon worth more than any other single test.
- **Upgrade path:** Tsai-Wu/Hoffman in the M frame, truth stage only, after C4. Use the strength ratio λ from
  `aλ² + bλ − 1 = 0`, with 1/λ as the degree-1 index.

### 3.3 Aggregation, relaxation, and when they apply

- **v1a:** F_L and F_P are computed **after the fact** on each v1a result and on the truth solve, for ranking and
  reporting. They have no gradient (Gandalf F3).
- **v1b:** they become constraints.
  - qp-relaxation (stress interpolated with q < p): [Bruggi 2008, *SMO* 36:125](https://doi.org/10.1007/s00158-007-0203-6) [v].
    The variant in [Le et al. 2010, *SMO* 41:605](https://link.springer.com/article/10.1007/s00158-009-0440-y) [v]
    uses q = 1/2 with p = 3.
  - p-norm `F_PN = (Σ_e v_e F_e^P)^(1/P)` with adaptive normalisation (Le et al. 2010).
  - Alternatives: [Verbart et al. 2017](https://link.springer.com/article/10.1007/s00158-016-1524-0) [v]; augmented
    Lagrangian ([Senhora et al. 2020](https://link.springer.com/article/10.1007/s00158-020-02573-9) [v]).
  - F_L and F_P are **separate aggregates**, so the orientation-sensitive one can run alone.
- **Adjoint cost:** each aggregated constraint needs one adjoint solve **per load case** per iteration (§4.8).
- **Honesty rule (spool-rack practice):** the p-norm is an optimisation device. Every verification reports raw per-Gauss
  maxima, percentiles and locations. Peaks at re-entrant corners are labelled as non-converged.

---

## 4. Topology optimisation formulation

### 4.1 Resolution ladder (accepted: Gandalf F1, Legolas F1)

Costs are Legolas's estimates for a 150 × 80 × 60 mm box, measured at 159–184 M cell-matvecs/s on the RTX 3500 Ada
laptop. They are not measurements of the full loop.

| Stage | Grid (frame) | Cells (box) | What runs | Massing | Overhang | Cost / orientation (estimate) |
|---|---|---|---|---|---|---|
| S0 prescreen | 1.6 or 0.8 mm cubic, **fixed part frame** | 0.18 M / 1.4 M | One isotropic (or TI) solve of the domain; analytic traction map over ~200 directions; mesh-level support and bed estimates | — | Mesh estimate only | Seconds to minutes in total |
| v1a TO | **Print frame per orientation**, dz = 0.6 mm (3 layers), dx = dy = 0.503 mm (= 0.6·tan 40°) | ≈ 4.7 M (≈ 1.4 × the 0.6 mm cubic count; ~30% occupied) | SIMP compliance, minimax over K, density filter + Heaviside, AM filter, volume | **Body = 100% printed solid** | Cross stencil, α ≥ 50° | ~15–30 min (Legolas's 10–20 min at 0.6 mm cubic × 1.4) |
| v1b TO (leaders only) | Print frame, dz = 0.4 (or 0.2) mm, dx = dz·tan 40°, masked domain | Masked leader region | v1a + coating + helper field + aggregated F_L/F_P + robust in final stage | Inclination-dependent coating (§4.5) | As v1a | Hours; leaders only |
| Truth | 0.2 mm cubic, adaptive, zero ersatz | 4–8 M leaves | G-code-mapped per-element C | Real (from G-code) | Real (Orca) | 2–6 min once MG-PCG exists (Legolas) |

Notes:
- Re-voxelisation per orientation costs about 7–51 s of host build at 0.8–0.4 mm (Legolas, measured). That is small
  next to a TO run, and the structured geometric-MG hierarchy needs no setup.
- Rotated boxes can need 1.5–2 × more cells (Legolas-on-Gandalf F1), so budget on the masked domain.
- `gpu_hex.element(spacing)` already takes a 3-vector spacing, so non-cubic cells are supported.

### 4.2 v1a problem

```
min_{ρ, t}  t
s.t.  c_k(ρ) ≤ t,                     k = 1..K   (bound formulation, minimax compliance)
      V(ξ) ≤ V*                       ξ = printed field after the AM filter
      0 ≤ ρ ≤ 1
post hoc: F_L, F_P aggregates; min-feature, overhang (M) and Orca (T) checks
```

The optimiser is MMA (Svanberg 1987, *IJNME* 24:359 [m]).

### 4.3 Filter chain

```
ρ̃ = H_M ρ    anisotropic conic filter;  |Δx|_M² = (Δx² + Δy²)/r_xy² + Δz²/r_z²
ρ̄ = [tanh(βη) + tanh(β(ρ̃ − η))] / [tanh(βη) + tanh(β(1 − η))]
ξ = AM_filter(printed(ρ̄, s))     (in v1a, printed = ρ̄)
```

Sources: Wang, Lazarov & Sigmund 2011, [*SMO* 43:767](https://doi.org/10.1007/s00158-010-0602-y) [v]; Bruns &
Tortorelli 2001 and Bourdin 2001 [m]; PDE filter, Lazarov & Sigmund 2011 [m].

- **Padding:** void, except mirror padding at symmetry planes and "supported" at the bed plane
  ([Clausen & Andreassen 2017](https://link.springer.com/article/10.1007/s00158-017-1709-1) [v]).
- **β continuation:** for example 1 → 32 in stages of 40–50 iterations.
- **Volume** is measured on the physical field ξ.

### 4.4 Interpolation and E_min

`C_e = [E_min/E_0 + ξ_e^p (1 − E_min/E_0)] · C_TI`, with p = 3 (continuation from 1). A scalar times one card means
**one shared Ke for every design cell** (§5.4). RAMP is an alternative (Stolpe & Svanberg 2001 [m]).

**E_min (D11):**
- Default 1e-6.
- Raise to at most 1e-3 only if B2 measures more than 40 MG-PCG iterations, and record E_min in every receipt
  (Gandalf-on-Legolas F6).
- B2 also measures the compliance gap to a zero-ersatz re-solve at each E_min (Frodo-on-Legolas F6).
- E_min is a solver device, never a physical claim. Under 0% infill, voids carry no stiffness.

### 4.5 Massing: closed form, and the coating that reproduces it

**Orca's construction:**
- Walls: in-layer inward offset by the wall-shell thickness W.
- Skins: regions not covered by the n_t layers above (top) or n_b layers below (bottom).
- Interior: void at 0% infill, unless it is a helper.

**Wall-shell thickness with flow spacing** (round-2 self-correction; Frodo F7), for n_w ≥ 2 and an approximate
Slic3r-lineage model [m]. The T-level check remains authoritative:

```
W_eff = w_o/2 + s_o/2 + (n_w − 1)·s_i,     s = w − h(1 − π/4)
```

| n_w (outer 0.42, inner 0.45, h 0.2) | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| W_eff (mm) | 0.399 | **0.806** | 1.213 | 1.620 |
| Nominal-footprint edge (mm) | 0.420 | 0.827 | 1.234 | 1.641 |
| Naive n·0.42 (mm) | 0.42 | 0.84 | 1.26 | 1.68 |

**Skin thickness:** `T = h·max(n_t, ⌈top_shell_thickness/h⌉)`. G's effective settings (5 layers, 1.0 mm) give
T = 1.0 mm.

**Surface-normal shell thickness:**

```
t(α) = max(W sin α, T cos α),     t_min = W T / √(W² + T²)  at  tan α* = T/W
```

| Walls | Skins | t_min | α* (from horizontal) |
|---|---|---|---|
| 2 | 5 × 0.2 | **0.63 mm** | 51.1° |
| 2 | 3 × 0.2 | 0.48 mm | 36.7° |
| 4 | 5 × 0.2 | 0.85 mm | 31.7° |

(`stencil_checks.py`. Round 1 gave 0.64 mm at 50° using the naive W.)

Frodo's SHELL-001 is the same formula written with the normal elevation φ = 90° − α. Rotating a part changes which
surfaces are thin-skinned; this is the orientation-dependent massing in closed form. Orca's
`ensure_vertical_shell_thickness` adds solid infill on such surfaces, so SHELL-001 binds at the T level.

**v1a (dz = 0.6 mm):** a 0.81 mm shell is about 1.5 cells, too thin to resolve. The faithful choice is to treat the
**body as 100% printed solid** and hand it to Orca as body + a full-body helper modifier (or as wall counts that fill
it). Hollow massing is not decided in v1a. That is an honest scope limit.

**v1b (dz ≤ 0.4, leaders): the inclination-dependent erosion coating.** This reproduces t(α) at sub-cell precision
without resolving W by erosion (Legolas F1, Gandalf F1). It extends the gradient-norm coating of Clausen, Aage &
Sigmund 2015 ([*CMAME* 290:524](https://doi.org/10.1016/j.cma.2015.02.011) [v]) and the erosion-based shell
identification of Luo, Li & Liu 2019 (*CMAME* 355:94 [v]).

```
n_e    = −∇ρ̃ / |∇ρ̃|                       outward normal from the filtered field
α_e    = arccos |n_e,z|                      surface inclination from horizontal
t_e    = max(W sin α_e, T_up/down cos α_e)   T_up for n_z > 0 (top skins), T_down for n_z < 0
I      = H( F_R ρ̄ ; η_e(t_e/R) )           erosion of depth t_e: large-radius filter R ≥ t_max (≥ 3 cells)
                                             with a per-cell threshold from the planar-interface relation
shell  = ρ̄ (1 − I),   core = ρ̄ I
C_e    = [E_min + shell^p + core^p s̄^p (1 − E_min)] · C_TI       (0% infill: the core is void unless helper s̄)
```

- The threshold-to-depth map η(t/R) for the chosen filter kernel is derived for a planar interface (cf. Fernández et
  al. 2021, [analytical length-scale relations](https://link.springer.com/article/10.1007/s00158-021-02998-w) [v]) and
  tabulated.
- Validated by I16 against resolved erosion at 0.2 mm and against Orca's real walls and skins at α = 0, 30, 50, 70 and
  90°.
- Shell and helper both use the TI card, so the cell stiffness is still a scalar times one Ke.
- Memory: about 5–8 extra float64 fields for sensitivities, roughly 0.2 GB at 3 M cells (Legolas F5). Acceptable on a
  masked leader domain.
- The outputs (body STL, helper STL, wall/skin counts) map onto the user's Orca controls. **Caveat** (Gandalf-on-Frodo
  F8): `package_part.py` sets `wall_loops` per object, with only infill density per modifier. Per-region wall counts
  wait on Gandalf's P0-D modifier spike.
- **Buckling:** thin hollow shells need the buckling check (spool-rack `rev-g/buckling.py`). Stiffness/stress TO
  does not see it (Clausen et al. 2016, *Engineering* 2(2):250 [m]).

Related work:
- [Wu, Clausen & Sigmund 2017](https://backend.orbit.dtu.dk/ws/files/134847727/MARAC_1_s2.0_S0045782517305984_main.pdf) [v].
- [Jewett & Carstensen 2023](https://www.sciencedirect.com/science/article/abs/pii/S0045794923001888) [v].
- [Kim-Tackowiak & Carstensen 2025](https://www.sciencedirect.com/science/article/pii/S0264127525011207) [v].

### 4.6 Minimum length scale

The minimum solid and gap in XY is 2w = 0.84 mm (Fillaprint rule; Frodo WALL-001/GAP-001). In Z, plates must be at
least n_t·h thick.

- **v1a (0.5–0.6 mm cells):** the filter radius r_xy ≈ 1.0–1.2 mm (about 2 cells) gives approximate control only.
  WALL-001/GAP-001 are post-checks at the M level (distance transform on every layer) and at the T level (bead counts
  and gap fill).
- **v1b:** robust formulation (eroded / nominal / dilated with η = 0.5 ± Δη; Wang et al. 2011 [v]), with (r, Δη) taken
  from the Fernández et al. 2021 relations [v]. It runs **only in the final continuation stage** (Legolas F2). The
  realised minimum feature is then measured (I17).

### 4.7 Overhang: AM filter, stencil and margin (Frodo F1, Gandalf F8)

**Evidence for a margin.** In `D9-P5/overhang-threshold-test/toolpath-verification.json`, with
`support_threshold_angle = 45`, Orca generated support on the wedges whose underside slopes were 30°, 39° and **45°**
(2,421 support segments) from horizontal. It generated none at 55°.

I re-derived the geometry: the underside slope from horizontal equals the file-name angle, and the `build.py:10`
comment "angle from vertical" is wrong. Note what this shows: it is Orca's support *decision* (tier S), not P1S print
quality.

**Filter.** Langelaar's AM filter ([2016, *Addit. Manuf.* 12:60](https://doi.org/10.1016/j.addma.2016.06.010) [v];
[2017, *SMO* 55:871](https://doi.org/10.1007/s00158-016-1522-2) [v]):

```
for k = 1..N (bed = layer 0, fully supporting):
    Ξ_e = smax_{s ∈ S_e(layer k−1)} ξ_s
    ξ_e = smin(ρ_e, Ξ_e)
adjoint sweep k = N..1
```

It is applied to the **printed-material field** (shell + helper in v1b). In 0%-infill bodies, internal ceilings must
self-support or bridge within the calibrated BRG-001 limit (Frodo's VOID-001).

**Stencil acceptance versus azimuth.** For a stencil S, the lateral advance per layer in azimuth φ is the support
function `h_S(φ) = max_{s∈S} s·(cos φ, sin φ)·dx`. Then `α_min(φ) = atan(dz/h_S(φ))`. From `stencil_checks.py`:

| Stencil, aspect | α_min at φ = 0° | 15° | 30° | 45° | Worst |
|---|---|---|---|---|---|
| 5-point cross, cubic | 45.0° | 46.0° | 49.1° | 54.7° | 45.0° (Orca supports it) |
| 3 × 3, cubic | 45.0° | 39.2° | 36.2° | **35.3°** | 35.3° (unsafe) |
| **5-point cross, dx = dz·tan 40°** | **50.0°** | 51.0° | 54.0° | 59.3° | **50.0°** |
| 3 × 3, dx = dz·tan 40° | 50.0° | 44.2° | 41.1° | 40.1° | 40.1° (unsafe) |

**Decision (D6):** use the 5-point cross with `dx = dz·tan(90° − α_min)` and α_min = 50° (40° from vertical).

- The aspect ratio leaves dz as a multiple of h, so layer alignment survives. Frodo's concern that a changed aspect
  breaks layers applies only if dz were changed.
- The cost is conservatism on diagonals (up to 59°) and about 1.4 × more cells than cubic.
- The 50° margin matches `bore_td`'s 40°-from-vertical crest.
- Which stencil Langelaar's 3D paper uses (5 or 9 cells) should be checked against the paper; v1 specifies the cross
  regardless.

**Checks:**
- M-level: slope ≥ 50° on the extracted mesh, sampled per triangle, not one sample per face as `selfsupport()`
  does. Islands are reported.
- T-level: zero Support and Support-interface roads (Orca is the final judge).
- **I13b:** Orca adds zero support roads to the AM-filter output of the I13 test cone at every azimuth.
- **Repair fallback:** an M-level 50° repair pass after extraction, which reports its volume delta (Frodo T10).

**Alternatives** (for arbitrary angles or continuous orientation):
- [Gaynor & Guest 2016](https://link.springer.com/article/10.1007/s00158-016-1551-x) [v].
- [Pellens et al. 2019, *SMO* 59:2005](https://link.springer.com/article/10.1007/s00158-018-2168-z) [v] (length scale
  + overhang).
- [Kumar & Fernández 2022](https://arxiv.org/abs/2204.07333) [v].
- Front propagation: van de Ven et al. 2018 [m];
  [3D, CMAME 2020](https://www.researchgate.net/publication/342391766_Overhang_control_based_on_front_propagation_in_3D_topology_optimization_for_additive_manufacturing) [v].
- Qian 2017, *IJNME* 111:247 [v], where d enters smoothly.

**Vendor "~70° overhang" and "30/40 mm bridging" values are not defaults** (§2.2).

### 4.8 Solves per iteration (Legolas F2, Gandalf-on-Legolas F5)

| Formulation | Solves per iteration (K load cases) | Bracket, K = 2 |
|---|---|---|
| v1a compliance (self-adjoint) | K | 2 |
| v1b + 2 aggregated constraints (one adjoint per constraint per load case) | K + 2K = 3K | 6 |
| v1b with robust (3 realisations) in the final stage | 9K | 18 |

There is also one sequential AM-filter sweep forward and one adjoint, each N layers long: about 100–250 launches at
0.6–0.4 mm. That is milliseconds per iteration, but it is N dependent launches, not one kernel (Legolas F4).

v1b stress-constrained runs often need 300–500 iterations. This is why v1b runs on leaders only.

### 4.9 Orientation

**S0 prescreen (D8).**
- Directions: a full-sphere Fibonacci set of ~200 (about 14° spacing). Up and down differ for overhang, bed contact
  and ceilings, so a hemisphere is wrong for anything printability-related (Legolas F10 agrees).
- The score is a **vector**, Pareto-filtered (Frodo F4):
  1. **F_L aggregate** from the analytic inter-layer traction map: for each d, per element, `σ_n = d·σd` and
     `τ = |σd − σ_n d|`. This needs one isotropic stress field and no solve per direction. It is justified because
     E_z/E_p ≈ 0.85–0.92 barely changes the field. Prior art: Umetani & Schmidt 2013 (cited by Frodo).
  2. Support-area estimate: mesh downward area with α < 50°.
  3. Bed contact area and stability (Frodo BED-002).
  4. Interface printability. Bores and rod seats whose axis lies in the layer plane need a d-specific teardrop
     (`bore_td`). Keep-ins are exempt from the AM filter but not from M/T checks.
  5. Discrete **spin** feasibility (0°/90°/… against the 256 × 256 bed, the 18 × 28 mm exclusion, and the ASA warp
     diagonal). The spool bracket envelope is about 207.5 × 233.5 mm (Frodo F5).
- **Domain for the stress field** (Gandalf F11):
  - The **design envelope** for problem-level pruning: keep K generous.
  - The **frozen v1a result** for each candidate. This is analysis mode: cheap, and it re-ranks the leaders.
- **Ranking in v1** uses F_L plus the printability metrics, not compliance (Gandalf F2).

**TO budget:** at most 24 v1a orientations after Pareto filtering. Repeat runs (3–5 perturbed starts) on the top 3 set
the noise floor; orientation differences smaller than that floor are reported as ties (Legolas F9).

**Acceptance test (P1):** on the benchmark problems, the orientation that is finally best must lie in the prescreen's
top K (Legolas F6, Gandalf F11).

**Not in v1:** continuous or gradient orientation design ([Langelaar 2018](https://doi.org/10.1007/s00158-017-1877-z)
[v]; [Olsen & Kim 2020](https://link.springer.com/article/10.1007/s00158-020-02590-8) [v]). The stiffness signal is
weak and the printability terms are not smooth in d.

### 4.10 Sparse infill as a per-problem switch (Gandalf F7, Frodo F8)

0% base infill with zero credit is a spool-rack G2 policy, not a property of the tool. D9-P5 plates run 5 walls with
40% gyroid (`prepare_and_slice.py:79`).

When `infill.credit: true`:
- C_core(ρ_inf, pattern) comes from **periodic RVE homogenisation of the actual Orca pattern** on the GPU hex solver.
- Gibson-Ashby form `E*/E_s = C ρ^n`: rectilinear/grid patterns are stretching-dominated along their lines, while
  gyroid is near-isotropic with n ≈ 2 ([MDPI 2022](https://www.mdpi.com/2076-3417/12/4/2180) [v]).
- The infill card has its own tier. A **zero-credit truth solve is always reported alongside** as a bound.
- Every report states which setting was used.

---

## 5. Toolpath-aware re-analysis

### 5.1 Existing code (read-only review)

| File | Does | Does not |
|---|---|---|
| `analysis/rev-g2/plastic_shape.py` `read_paths` | Parses G0/G1, M82/M83, G90/G91, G92 and role/width/height/Z comments. Restores the extruder offset; inverts the 3MF item transform (asserts it is orthonormal and Z-preserving); separates priming lines; marks thick bridges non-structural; hashes inputs. `main()` asserts the object E-volume is within 0.1% of the footer (line 380), so dropped G2/G3 arcs fail loudly. The archived G slice has `enable_arc_fitting = 0` (Gandalf F9). | No arc parsing (the D9 `path_reader.py` has it; merge them). No orientation output. **No handling of `filament_shrink`.** Part-specific default transform. |
| `designs/closed-wall-e13/inspect_toolpaths.py` | Older reader | Hard-codes layer = round(z/0.2) − 1 and installed offsets |
| `analysis/rev-g2/audit_g_slicer_mapping.py` | Diagnostic: per-layer FEM sections versus emitted non-sparse footprints (FEM 2542.4 vs emitted 2547.9 mm³) | No orientation or anisotropy |
| `analysis/rev-g2/gpu_material_probe.py` | Conservative voxeliser (keeps a cell only if fully covered) | No fractional occupancy |
| `analysis/rev-g2/gpu_hex.py` | Matrix-free Q1 hex, shared isotropic Ke, face-connected node splitting, 8 Gauss stresses | Per-element C |
| `analysis/rev-g2/solve_plastic.py` | skfem P1 tets with `linear_elasticity(λ, μ)` | Anisotropy |

**Omission figures** for the conservative voxeliser (Frodo F9; this also corrects my round-2 Legolas review, which
said 16.4/33.1 could not be found):
- **Whole G: 8.02% / 16.38% / 33.09%** at 0.2 / 0.4 / 0.8 mm (`ADAPTIVE-MESH.md`, table and line 90).
- **Crop only:** 17.12% / 8.37% / 4.31% at 0.4 / 0.2 / 0.1 mm (`GPU-VALIDATION.md`). `ADAPTIVE-MESH.md` warns that
  crop losses must not be substituted for whole-part figures.

### 5.2 Missing

1. Per-segment direction carried into the cell map.
2. Role → material class as configuration.
3. Fractional occupancy and bond fraction b.
4. Per-element C in the truth solver, plus anisotropic stress recovery and failure evaluation.
5. The card schema with tiers and provenance.
6. **Inversion of slicer compensation** (`filament_shrink`; §1.1).
7. Synthetic G-code fixtures (I20, I21).

### 5.3 Mapping algorithm (truth stage; vectorised, Legolas F7)

For layer k (cell z-extent = layer k), rasterise each segment's footprint (the segment buffered by w/2, consistent with
`union_footprints`) by supersampling, for example 4 × 4 per cell. This uses numpy/Warp kernels and an atomic-add
structure-tensor accumulation, with an estimated 1–3 min for a 74 cm³ part.

Per cell e:

```
φ_e       occupancy fraction
A_e       = Σ_s a_es t_s⊗t_s           structure tensor (independent of the sign of t)
r_e[c]    role fraction per material class
b_e       = area(fp_k ∩ fp_{k+1} ∩ cell)/cell area     (2D mask AND per layer pair)
θ_e       = principal eigenvector of A_e;   κ_e = (λ1 − λ2)/(λ1 + λ2)
```

- If κ is low (corners, crossings, gap fill), use the area-weighted Voigt average of the rotated cards. This is an
  upper bound; flag it and report the volume fraction affected.
- **Fractional occupancy** enters as a partial-volume scalar on the cell stiffness, the same kernel as the SIMP scale.
  Report it alongside the conservative-voxel result until convergence studies settle which is used.
- **Conservation:** Σ φ_e V_e versus footprint area × h versus footer E-volume, within stated tolerances. Check the
  orientation histogram against Orca's settings.

### 5.4 Solver interface

- **Design stage (Gandalf F4):** TI card + print-frame grid means one Ke (for the spacing vector) and a per-cell scalar.
  This is the minimal change to `gpu_hex` (adding the per-cell scalar). Gandalf's Ke stack is needed only in the truth
  stage.
- **Truth stage (Legolas F3):** a **Ke library** indexed by (class, θ-bin, b-bin) is the solver interface, with a
  1-byte index per cell. Per-cell C (21 numbers) is used only in stress recovery and failure evaluation.
  - Per-cell B^T C B costs about 4.5 × the FLOPs of a shared-Ke matvec on a kernel that appears FP64-bound.
  - **Bin widths:** 5° θ-bins (36 over 180°) change C by at most 0.63% (spectral norm) for E1/E2 = 1.33, and 0.18% for
    a TDS-like 1.10 (computed in round 2). With b in 8 levels and 2 classes that is 576 entries × 4.6 kB ≈ 2.7 MB,
    resident in L2.
  - Strength is evaluated with the exact per-element θ and b.
- **Multigrid** with heterogeneous C needs Galerkin or laminate-homogenised coarse operators (§2.6). Jacobi smoothing
  alone degrades.
- **Precision:** FP32 is acceptable for smoothers and preconditioners. The anisotropic patch test (I11) and all
  finite-difference sensitivity checks (I14) run in FP64.

---

## 6. Validation and calibration

### 6.1 Principles

- **Process lock.** Coupons use the production profile (line widths, layer height, speeds, temperatures, fan, chamber
  state, flow 0.93/0.95, shrink) and the same filament lot and drying. Record the profile hash via PROC-001.
- **Virtual-coupon calibration** (resolves Gandalf F10). Each coupon's own G-code goes through the same truth pipeline:
  mapper, voxel or fractional-occupancy convention, solver. The card constants are then fitted:
  - E from measured force–displacement (via DIC);
  - strengths from the failure load, using the same index and Gauss-point convention as part predictions.
  - The neck, the stadium bead and voxel omission are thereby absorbed consistently. Caliper and gross-area values are
    recorded for comparison only.
- **Coupon thermal history must match parts** (Frodo F11). Print tall Z coupons (C2) with companion parts on the
  plate, or as a block that is then machined. Record per-layer time from the G-code and compare with Orca's minimum
  layer time (3 s ASA, 12 s PETG in the user's profiles).
- Name orientations per ISO/ASTM 52921 [m]. Condition at 23 °C for at least 48 h, as-printed. Test n ≥ 5 per
  condition (ISO 527).
- Coupon G-code and results use the same receipt schema as part runs (Gandalf F12).
- **Merge with Frodo's calibration plate:** the overhang ladder, printed as tension specimens, doubles as C5.

### 6.2 Coupon plan and priority

| # | Test | Pins down | Phase |
|---|---|---|---|
| **C2** | Z tension (upright, or a machined block, with companion parts) | E_z, Z_t | **P1/P2 minimum** |
| **C3** | Inter-layer shear: V-notch (ASTM D5379/D7078) or double-notch (D3846) on a layer plane ([JMR&T 2023](https://www.sciencedirect.com/science/article/pii/S2238785422020361) [v]; [Polymers 14:4028](https://doi.org/10.3390/polym14194028) [v]) | S_il, G_z | **P1/P2 minimum** |
| C1 | XY tension, flat production layup (+ DIC) | E_p, X_t, ν_p | P1/P2 (cheap) |
| C4 | 45° off-axis tension | Interaction in F_L (largest single information gain) | P3 |
| C5 | Overhang-wall tension at α = 60/50/40° | g(f), overlap_min | P3 (shares coupons with Frodo's ladder) |
| C6 | Flexure, flat and on edge | **Validation only** | P3 |
| C7 | Demonstrator in 2–3 orientations, with **pre-registered** predictions | T2 | P3 |

**If there is no universal testing machine** (question 1 for the user; Frodo F12), dead-weight loading is feasible:
- Z tension on a 4 × 2 mm gauge at 23 MPa needs about 184 N (19 kg).
- 3-point flexure (b 10, h 4, L 64 mm) at 40 MPa needs about 67 N.
- Moduli need DIC; displacement read from a dial includes fixture compliance.

### 6.3 Stating confidence

| Card tier | Basis | May claim |
|---|---|---|
| T0 | Datasheet (V) + assumptions (H) | Rankings and intervals from the bracket corners; no absolute strength |
| T1 | Own C1–C3 (+ C4, C5) via virtual-coupon fits | Stiffness within about ±10–15% if CVs are small; strengths with stated scatter; "mean − k·s" lower bounds (normal 90/95: k ≈ 3.4 at n = 5, 2.36 at n = 10 [m]), which are **not** CMH-17 basis values |
| T2 | T1 + demonstrator inside its pre-registered band | Model form supported for that part family and load type |

Each value also carries Frodo's provenance tag (U/S/V/L/H). Size effect: brittle inter-layer failure is
non-conservative from coupon to part. This is noted, not modelled.

---

## 7. Correctness invariants (tests)

**Frames, units, data flow**

1. **I1** — Every transform is named `R_TO_FROM`, has det = +1 and orthonormality to 1e-12. Round trips D→I and D→P→D
   are identity.
2. **I2** — `R_PD d = e_z` for random d, including ±e_z.
3. **I3** — The G→B→D mapping reproduces `plastic_shape`'s assertions: offset restored, Z-preserving item transform,
   footer volume within 0.1%.
4. **I4** — Units: unitless numbers rejected at I/O. Mass check against Orca's grams.
5. **I5** — Resultant force and moment are preserved through D→I→P re-voxelisation.

**Tensors and elements**

6. **I6** — Symmetry and positive-definiteness of Mandel C; engineering-constant inequalities; reciprocity.
7. **I7** — Mandel eigenvalue invariance under rotation; QCQ^T equals the einsum rotation, which equals the Bond-Voigt
   route.
8. **I8** — TI card invariant under Rz; the ±45° laminate invariant under Rz(90°) but not under Rz(45°).
9. **I9** — `gpu_hex` permutation: C[3,3] = G12, C[4,4] = G23, C[5,5] = G13; pure-shear tests.
10. **I10** — Ke symmetric PSD with exactly 6 zero modes, including non-cubic spacing. GPU operator equals an
    independent skfem anisotropic assembly.
11. **I11** — Anisotropic patch test: affine u gives σ = Cε at every Gauss point, in FP64.

**Failure**

12. **I12** — F(λσ) = λF(σ). Uniaxial stress along the bead gives F_P = σ/X_t. Part-x tension gives F_L = σ/Z_t when
    printed x-up and F_L = 0 when printed flat. Mandel shear is divided by √2 before evaluation.

**TO blocks**

13. **I13** — AM-filter output is self-supported cell by cell. Accepted slope versus azimuth matches the
    `stencil_checks.py` table. Internal ceilings of hollow bodies are caught.
14. **I13b** — Orca generates zero support roads on the AM-filter output of the test cone at every azimuth (T-level,
    Frodo F1).
15. **I14** — Central finite differences and Taylor tests (O(h²)) in FP64 for every gradient block present: filter,
    projection, AM filter at the **production layer count** (Legolas F4); in v1b also coating, robust and p-norm.
16. **I15** — Filter normalisation and padding at edges, symmetry planes and bed.
17. **I16** (v1b) — The coating reproduces t(α) ± ½ cell at α = 0, 30, 50, 70, 90° against resolved 0.2 mm erosion,
    and against Orca roads after `ensure_vertical_shell_thickness`.
18. **I17** (v1b) — Measured minimum solid and gap ≥ 2w in XY and ≥ n_t·h in Z, or flagged.

**Discretisation and verification**

19. **I18** — Mesh dependence at a fixed physical filter radius on a reduced domain. Raw corner peaks are labelled.
20. **I19** — Design versus zero-ersatz truth: **|c_truth/c_design − 1| ≤ 15%**, and the orientation ranking by F_L is
    preserved. The threshold is provisional, set before the first result is shown, and recalibrated on the bracket.
    A breach blocks the candidate.
21. **I20** — Mapper fixtures: a straight raster gives the exact θ; concentric walls give tangential θ; the ±45°
    alternation is recovered; a staircase gives a known b.
22. **I21** — Compensation fixture: the same part sliced at `filament_shrink` 100% and 99.46% maps to identical
    D-frame occupancy after inversion. This fixes the scaling centre.
23. **I22** — Rotation covariance: rotate the domain, loads and TI axis together by a grid-symmetry rotation; compliance
    must be unchanged to 1e-10. This catches R versus R^T bugs that oracle comparisons sharing the same R miss.
24. **I23** — Prescreen conservatism: on benchmarks, the final best orientation is in the prescreen top K.

---

## 8. Literature (grouped; [v] verified in this session)

| Topic | References |
|---|---|
| FDM anisotropy | Ahn 2002 [m]; Rodriguez 2003 [m]; [Casavola 2016](https://www.sciencedirect.com/science/article/abs/pii/S0264127515307516) [v]; [Zou 2016](https://www.semanticscholar.org/paper/Isotropic-and-anisotropic-elasticity-and-yielding-Zou-Xia/744752e7b5f209c8b31391568114c9a60abf7fb3) [v]; [Kiendl & Gao 2020](https://www.researchgate.net/publication/336817681_Controlling_toughness_and_strength_of_FDM_3D-printed_PLA_components_through_the_raster_layup) [v]; [PLA orthotropy 2024](https://www.sciencedirect.com/science/article/pii/S026382312400243X) [v] |
| Weld physics | Seppala 2017 [m]; Coogan & Kazmer 2017 [m] |
| Vendor data | Bambu TDS: [PETG HF](https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf), [PETG Basic](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf), [ASA](https://solidprint3d.ie/wp-content/uploads/2024/03/Bambu-Lab-ASA-Filament-Technical-Data-Sheet.pdf) [v]; Polymaker/PolyLite via spool-rack `material-reference-data.json` (source URLs and hashes therein) |
| Laminates | [Sun & Li 1988](https://journals.sagepub.com/doi/abs/10.1177/002199838802200703) [v] |
| Anisotropic strength TO | [Mirzendehdel 2018](https://par.nsf.gov/servlets/purl/10057716) [v]; [Kundu & Zhang 2023](https://doi.org/10.1016/j.addma.2023.103730) [v]; [Zou & Xia 2023](https://academic.oup.com/jcde/article/10/2/892/7110403) [v]; [Dapogny 2019](https://www.researchgate.net/publication/328607322_Shape_and_topology_optimization_considering_anisotropic_features_induced_by_additive_manufacturing_processes) [v]; [FDM process-structure TO 2024](https://link.springer.com/article/10.1007/s00170-024-14929-2) [v] |
| Bead-aware TO | [Jewett & Carstensen 2023](https://www.sciencedirect.com/science/article/abs/pii/S0045794923001888) [v]; [Kim-Tackowiak & Carstensen 2025](https://www.sciencedirect.com/science/article/pii/S0264127525011207) [v] |
| Stress TO | [Le 2010](https://link.springer.com/article/10.1007/s00158-009-0440-y) [v]; [Bruggi 2008](https://doi.org/10.1007/s00158-007-0203-6) [v]; [Verbart 2017](https://link.springer.com/article/10.1007/s00158-016-1524-0) [v]; [Senhora 2020](https://link.springer.com/article/10.1007/s00158-020-02573-9) [v]; Duysinx & Bendsøe 1998 [m]; Holmberg 2013 [m] |
| Regularisation | [Wang, Lazarov & Sigmund 2011](https://doi.org/10.1007/s00158-010-0602-y) [v]; [Clausen & Andreassen 2017](https://link.springer.com/article/10.1007/s00158-017-1709-1) [v]; [Fernández 2021](https://link.springer.com/article/10.1007/s00158-021-02998-w) [v]; Bruns & Tortorelli 2001 [m]; Bourdin 2001 [m]; Guest 2004 [m]; Lazarov & Sigmund 2011 [m] |
| Overhang | [Langelaar 2016](https://doi.org/10.1016/j.addma.2016.06.010) [v]; [Langelaar 2017](https://doi.org/10.1007/s00158-016-1522-2) [v]; [Gaynor & Guest 2016](https://link.springer.com/article/10.1007/s00158-016-1551-x) [v]; [Pellens 2019](https://link.springer.com/article/10.1007/s00158-018-2168-z) [v]; [Kumar & Fernández 2022](https://arxiv.org/abs/2204.07333) [v]; Qian 2017 IJNME 111:247 [v]; van de Ven 2018 [m] / [2020](https://www.researchgate.net/publication/342391766_Overhang_control_based_on_front_propagation_in_3D_topology_optimization_for_additive_manufacturing) [v] |
| Orientation | [Langelaar 2018](https://doi.org/10.1007/s00158-017-1877-z) [v]; [Olsen & Kim 2020](https://link.springer.com/article/10.1007/s00158-020-02590-8) [v]; Ulu et al. 2015 J. Mech. Des. 137:111410 [v, bibliographic]; Umetani & Schmidt 2013 (via Frodo) |
| Coating / shell-infill | [Clausen 2015](https://doi.org/10.1016/j.cma.2015.02.011) [v]; [Wu, Clausen & Sigmund 2017](https://backend.orbit.dtu.dk/ws/files/134847727/MARAC_1_s2.0_S0045782517305984_main.pdf) [v]; Luo, Li & Liu 2019 CMAME 355:94 [v]; Clausen 2016 Engineering [m]; Wu 2018 TVCG [m] |
| Infill | [Gyroid 2022](https://www.mdpi.com/2076-3417/12/4/2180) [v]; Groen & Sigmund 2018 [m] |
| Interpolation / optimiser | Bendsøe & Sigmund 1999 [m]; Stolpe & Svanberg 2001 [m]; Svanberg 1987 [m] |
| Multi-axis (context) | [Fang 2020](https://doi.org/10.1145/3414685.3417834) [v] |

---

## 9. Open disputes for the merge

| # | Dispute | Positions | My recommendation and evidence |
|---|---|---|---|
| 1 | **Fixed vs re-voxelised grid** | Legolas R1: fixed part grid + rotated Ke. Gandalf, Frodo, Sauron: re-voxelise. Legolas conceded most of this in his Gandalf review. | **Re-voxelise every TO** (layers on grid planes for the AM filter, layer erosion and bond resolution). Keep the fixed grid **only for S0 analysis mode**, where it removes re-voxelisation noise from comparisons. Evidence: host build 7–51 s versus 15+ min TO (Legolas, measured); geometric MG needs no setup. |
| 2 | **Design-grid ladder** | Sauron R1: 0.2 mm. Gandalf: 0.6. Legolas: 1.6/0.8/0.4 (R1), 0.6 for P1 (R2). | **v1a: dz 0.6, dx 0.503 mm, body solid. v1b leaders: dz ≤ 0.4. Truth: 0.2.** Evidence: 0.2 mm is 90 M box cells and does not fit 11.5 GB (Legolas). A 0.8 mm grid loses 33% of material in conservative voxelisation (`ADAPTIVE-MESH.md`). The shell (0.81 mm) is about 1.5 cells at 0.6 mm, hence body = solid in v1a. **Unsettled:** whether v1b needs 0.2 mm locally, or whether the inclination coating at 0.4 mm passes I16. Decide by I16 measurement. |
| 3 | **Hemisphere vs full sphere** | Legolas R1: hemisphere (n ~ −n). Sauron, Frodo, and Legolas R2: full sphere. | **Full sphere** for anything with printability; a hemisphere only for pure-stiffness analysis. C(d) = C(−d), but overhang, bed and ceilings flip. |
| 4 | **E_min** | Legolas: ≥ 1e-3. Sauron: 1e-6. | **1e-6 default; raise to ≤ 1e-3 only if B2 shows more than 40 iterations; record in receipts; B2 also measures the zero-ersatz compliance gap; I19 gate.** Evidence: Legolas measured 16 → 106 SA iterations at 1e-3 contrast on one contrived pattern; there is no measurement yet for structured GMG. |
| 5 | **Infill palette vs 0%-infill rule** | Gandalf: 15/40/100% modifiers. Sauron R1 and spool-rack: 0% + 100% helpers. Frodo: per problem. | **Per-problem switch (D2, §4.10).** The spool-rack G2 problem uses 0%. D9-like problems may credit infill only with an RVE-homogenised card and a zero-credit bound reported. Evidence: D9-P5 really runs 40% gyroid; spool-rack `plastic_shape` asserts no sparse infill. |
| 6 | **Overhang margin vs exactly 45°** | Gandalf: 45° filter + M/T checks. Frodo: α ≥ 50° designed. | **50° enforced in the filter with the cross stencil and dx = dz·tan 40°** (worst-case azimuth exactly 50°), plus M/T checks. Evidence: Orca supported the 45° wedge (2,421 segments; 0 at 55°); the stencil table in §4.7. Cost: about 1.4 × cells. **Unsettled:** whether 50° prints well on the P1S (tier S only), pending Frodo's overhang ladder. |
| 7 | **z_fraction 0.5 vs vendor Z/XY** | Frodo: 0.5 placeholder. Sauron: vendor ratio. | **Card holds Z_t; report at both corners (vendor-ratio and 0.5·X_t); design to the 0.5 corner until C2.** Evidence: vendor ratios are 0.68–0.95 from annealed or unknown-condition specimens; the user's parts are as-printed with a different profile. |
| 8 | **PolyLite ASA vs Bambu cards** | Sauron R1 built T0 on Bambu PETG HF. Frodo: the user prints PolyLite ASA and generic PETG. | **T0 from PolyLite ASA first** (2379 MPa, 43.8/32 MPa, ratio 0.73), with E_z borrowed from the Bambu ASA ratio (0.87, flagged). PETG card **unassigned** until the grade is known. Evidence: print log P-0006–P-0015. Note that PolyLite flexural modulus 3206 vs tensile 2379 is unexplained. |
| 9 | **Strength in design: post hoc vs constraint** | Gandalf and Legolas: defer. Sauron R1: v1 constraint. | **v1a post hoc, v1b constraint on leaders** (D7). Evidence: solve counts 2 versus 6–18 per iteration (§4.8). |
| 10 | **Modulus basis for movement gates** | Not addressed in round 1 by anyone except as "E = 1 GPa". | **Two bases on every card** (§2.3). Ask the user whether the anisotropy ratio may be assumed equal for the sustained basis, or whether creep coupons (Z vs XY) are in scope. |

---

## 10. Open questions for the user

1. **Is a universal testing machine available** (or should dead-weight + DIC be used)? This decides whether T1 is
   reachable.
2. Which **PETG grade** is printed (the print log says "Generic PETG Starter" profile with an unrecorded brand)?
   Confirm PolyLite ASA as the primary ASA.
3. Is creep (sustained 85 °F) in scope, and can the short-term anisotropy ratio be assumed for the 1,000 MPa
   sustained basis?
4. Is sparse-infill credit wanted for non-spool-rack parts (a collaborator's parts, D9-style)?
5. Who sets the I19 gap threshold and the C7 pre-registered bands? (Proposed: 15%, recalibrated on the bracket.)

## 11. Artifacts

- `D:\Code\Models\fdm-gen\scratch\sauron\tensor_checks.py`: Mandel Q, Bond-Voigt, bug magnitudes, TI invariance,
  directional modulus, dC/dθ finite differences, gpu_hex permutation, quadratic inter-layer example.
- `D:\Code\Models\fdm-gen\scratch\sauron\laminate_checks.py`: exact layered homogenisation. Its shell and overlap
  section uses the round-1 naive W and the from-vertical overlap form; **superseded by `stencil_checks.py`**.
- `D:\Code\Models\fdm-gen\scratch\sauron\stencil_checks.py` (round 3): stencil acceptance versus azimuth, the
  flow-spacing shell table and t_min, and overlap f(α).
- `D:\Code\Models\fdm-gen\research\sauron.md`: the round-1 record, unchanged.

---

## 12. Review disposition

| Review # | Finding (short) | Disposition | Reason | Landed in |
|---|---|---|---|---|
| Gandalf 1 | 0.2 mm TO grid unaffordable | **Accepted** | Legolas's measurements; 90 M cells does not fit | §4.1 ladder, D4, Dispute 2 |
| Gandalf 2 | Rank orientation by F_L/printability, not compliance | **Accepted** | Follows from the 15% stiffness spread | §0.1, §4.9, D8 |
| Gandalf 3 | v1 too large; split v1a/v1b; name gating invariants | **Accepted** (partly on invariants) | Agree on the split. I14 (FD tests) still gates every gradient block present in v1a, including the AM filter, because untested gradients produce silent nonsense | §4.2, §4.8, D7, D12 |
| Gandalf 4 | TI at design stage means a single shared Ke | **Accepted** | Correct; stronger still, no rotation of C is needed at the design stage | §2.4, §5.4 |
| Gandalf 5 | Add installed and plate frames; one table | **Accepted** | Also added the shrink step to the chain | §1.1, D1 |
| Gandalf 6 | Tiers: card-level T0–T2 plus Frodo per-value tags | **Accepted** | One vocabulary | D10, §6.3 |
| Gandalf 7 | 0% infill is a spool-rack policy, not system-wide | **Accepted** | D9-P5 uses 40% gyroid | D2, §4.10, Dispute 5 |
| Gandalf 8 | Reconcile the 45° stencil with the 50° target | **Accepted** | Cross stencil + dx = dz·tan 40° gives worst case 50° (computed) | §4.7, D6, Dispute 6 |
| Gandalf 9 | Arc-drop is caught by the footer guard (credit) | **Accepted** | Confirmed `plastic_shape.py:380`, arc fitting off in G | §5.1 |
| Gandalf 10 | Which geometric convention for card vs FE? | **Accepted** | Virtual-coupon calibration through the same pipeline | §6.1, §5.3 |
| Gandalf 11 | Which domain feeds the prescreen? | **Accepted** | Envelope for pruning, frozen v1a design for re-ranking, plus a conservatism test | §4.9, I23 |
| Gandalf 12 | C2/C3 as P1/P2 minimum; receipts | **Accepted** | They set the only orientation-sensitive constants | §6.2 |
| Gandalf 13 | Convert load-bearing [m] citations to [v] | **Accepted** | Langelaar 2016, Wang 2011, Bruggi 2008, Qian 2017, Pellens 2019 verified | §8 |
| Legolas 1 | 0.2 mm design grid; use 0.6–0.8 with sub-cell shell | **Accepted** | Same as Gandalf 1; sub-cell = inclination-dependent erosion | §4.1, §4.5 |
| Legolas 2 | Solves per iteration; v1a/v1b; robust only late | **Accepted, corrected** | Adjoints are per constraint **per load case**, so 9K (18 at K = 2), not 3(K + 2) = 12 | §4.8 |
| Legolas 3 | Per-cell C expensive; Ke library interface; bin b | **Accepted** | 5° θ-bins (≤ 0.63% error) rather than 2°; b in 8 levels | §5.4 |
| Legolas 4 | AM filter sequential; FD test at production layer count | **Accepted** | Float64-sensitive smooth max over many layers | §4.8, I14 |
| Legolas 5 | Coating memory and cost | **Accepted** | Leader-only masked domain | §4.5 |
| Legolas 6 | Prescreen needs an acceptance criterion | **Accepted** | Top-K containment on benchmarks | §4.9, I23 |
| Legolas 7 | Mapper must be vectorised | **Accepted** | numpy/Warp kernels; 1–3 min estimate | §5.3 |
| Legolas 8 | Heterogeneous C and MG coarse levels | **Accepted** | Laminate homogenisation or Galerkin coarse operators | §2.6, §5.4 |
| Legolas 9 | Weak signal: add a repeat-run noise floor | **Accepted** | Ties reported below the floor | §4.9 |
| Legolas 10 | Full-sphere prescreen; state the TO budget | **Accepted** | ≤ 24 v1a runs | §4.9, D8 |
| Legolas 11 | I14/I18 costs are fine | **Accepted** (no change) | — | §7 |
| Legolas 12 | Coupons outside his angle | **Noted** | — | — |
| Frodo 1 | 45° default fails Orca; margin; I13b | **Accepted** | Stencil/aspect solution keeps layer alignment; I13b added | §4.7, I13b, D6 |
| Frodo 2 | Vendor bridge/overhang numbers are not limits | **Accepted** | Tier V only; catalog plus ladder coupons decide | §2.2, §4.7 |
| Frodo 3 | T0 cards for grades the user does not print | **Accepted** | Verified the print log; T0 = PolyLite ASA, PETG unassigned | §2.2, §2.3, Dispute 8 |
| Frodo 4 | Sweep ignores bed and interface printability; vector score | **Accepted** | Pareto vector prescreen | §4.9, D8 |
| Frodo 5 | Spin is a feasibility gate, not polish | **Accepted** | Discrete spin check at candidate generation | §2.5, §4.9 |
| Frodo 6 | f and k_step are one parameter (overlap_min) | **Accepted** | k = 1 − f; α_min 50° ↔ f_min 0.60 ↔ k 0.40 | §2.7 |
| Frodo 7 | Use actual per-loop widths | **Accepted, extended** | Used Orca flow spacing: W = 0.806 mm for 2 walls | §4.5 |
| Frodo 8 | 0% infill not user-wide | **Accepted** | As Gandalf 7 | D2, §4.10 |
| Frodo 9 | Omission numbers were crop numbers | **Accepted** | Whole-G 8.02/16.38/33.09% quoted; my round-2 Legolas review was wrong to say they were missing | §5.1 |
| Frodo 10 | E_min dispute; numeric I19 | **Accepted** | Conditional rule (Gandalf's) plus I19 = 15% provisional | §4.4, I19, D11, Dispute 4 |
| Frodo 11 | C2 thermal history (layer time) | **Accepted** | Companion parts or machined block; layer times recorded | §6.1 |
| Frodo 12 | Testing machine is the first user question | **Accepted** | — | §10 Q1 |
| Self (R2) | Modulus basis: short-term vs 1,000 MPa sustained | **Applied** | Movement gates use the sustained basis; ratio for it is assumed | §2.3, Dispute 10 |
| Self (R2) | Orca flow spacing in the shell formula | **Applied** | t_min 0.63 mm at 51.1° (was 0.64 at 50°) | §4.5 |
| Self (R2) | Slopes from horizontal (Frodo D3) | **Applied** | Overlap rewritten as f(α); all angles from horizontal | Conventions, §2.7, §4.7 |
| Self (R2) | `filament_shrink` breaks the truth mapping | **Applied** | Added to the frame chain, missing list and I21 | §1.1, §5.2, I21 |
