# Sauron: mechanics and mathematics of orientation-driven generative design for FDM

Round 1 research report (math/mechanics angle). Researchers: Gandalf = architecture, Sauron = mechanics,
Legolas = compute, Frodo = workflow + printability catalog. Written 2026-10-07.

**Scope.** Material model in the printer frame, tensor rotation, failure criteria, the topology-optimisation (TO)
formulation including massing and overhang, toolpath-aware re-analysis, coupon calibration, and the invariants an
implementation must test. Two small numerical checks back the formulas in this report:
`D:\Code\Models\fdm-gen\scratch\sauron\tensor_checks.py` and `laminate_checks.py` (pure numpy, under 1 s).

**Citation key.** **[v]** = checked by web search or by reading the source in this session. **[m]** = cited from
memory. The [m] bibliographic details are probably right but should be checked before anyone quotes them.

---

## 0. Executive summary

1. **Stiffness anisotropy is small for PETG/ASA. Strength anisotropy and massing are large.** Bambu's own TDS give
   E_Z/E_XY = 0.85 to 0.92 but tensile strength Z/XY = 0.68 to 0.84 (section 2.2). With a transversely isotropic (TI)
   card at these ratios, directional stiffness varies by only 15% from layer plane to build axis (computed, section 2.5).
   **A compliance-only optimiser will barely care about build orientation.** Orientation matters through (a) inter-layer
   *strength*, (b) printability (overhang, bridging), and (c) **massing**: slicer walls and skins have different
   thicknesses on surfaces of different inclination (section 4.4). These three must drive the design. The elastic
   anisotropy can stay simple.
2. **The massing rule can be computed.** With 2 walls x 0.42 mm and 5 skin layers x 0.2 mm, the surface-normal shell
   thickness is `t(a) = max(n_w*w*sin a, n_t*h*cos a)`. It falls to **0.64 mm at a = 50 deg** from horizontal
   (vs 0.84/1.0 mm on vertical/horizontal faces), which is why Orca has `ensure_vertical_shell_thickness`. A TO
   formulation can model this exactly with a *directional* coating (XY erosion for walls, Z erosion for skins),
   which extends Clausen et al. 2015 / Luo et al. 2019.
3. **The inter-layer overlap of a leaning wall** is nominally `f = 1 - h*tan(beta)/w`: 52% at 45 deg and zero at
   64.5 deg for w = 0.42, h = 0.2. The same mechanism produces both the overhang limit and the weak bond on steep
   overhang walls, so the overhang constraint is also a strength constraint.
4. **Rotation of the stiffness tensor:** do it in **Mandel** notation, where the 6x6 rotation Q is orthogonal and
   `C' = Q C Q^T`. Convert to the solver's Voigt order only at the boundary. I measured the two common bugs:
   applying the Mandel Q to a Voigt C gives errors up to **480 MPa** on a ~2000 MPa card, and applying the inverse
   rotation gives errors up to **130 MPa**. The existing `gpu_hex.py` uses Voigt order **(xx,yy,zz,xy,yz,xz)** with
   engineering shear strain. This is not the canonical (11,22,33,23,13,12) order, so a permutation is required.
5. **Failure (v1):** a two-mode criterion that is homogeneous of degree 1. The inter-layer quadratic mode is
   `(<sigma_n>+/Z_t)^2 + (tau/S_il)^2` on the layer plane. The in-layer mode is von Mises/X_t. It needs three
   strengths: X_t, Z_t, S_il. A full Tsai-Wu needs an interaction term that our coupon budget cannot defend.
   Aggregate it with a p-norm or augmented Lagrangian and use qp-relaxation.
6. **Existing slicer mapping** (`plastic_shape.read_paths`, `audit_g_slicer_mapping.py`, `gpu_material_probe.py`)
   does **occupancy** well, with hash-pinned G-code, transform assertions and an E-volume footer check. It holds no
   **orientation**, no role-to-material mapping and no fractional inter-layer bond. Both solvers are isotropic:
   `gpu_hex` shares one Ke and `solve_plastic` uses skfem `linear_elasticity(lam, mu)`. Section 5 lists what is missing.
7. **Orientation should be a discrete sweep over the sphere of build directions, not a gradient variable** in v1.
   A cheap prescreen is the **inter-layer traction map**: from one isotropic stress field, evaluate the inter-layer
   failure index for every candidate build direction analytically, with no FE solve per direction (section 4.7).
8. **The TDS cards are not internally consistent.** Bending modulus is below tensile modulus for PETG Basic and ASA.
   Z-flexural strength is 1.3 to 2.1 times Z-tensile. The TDS specimens were annealed, which user parts are not.
   We cannot claim absolute strength until we test our own coupons with the production profile (section 6).

### Numbered decisions proposed

| # | Decision |
|---|---|
| D1 | Four named frames: part/design **D**, printer/plate **P**, bead/material **M**, G-code **G**. Transforms named `R_PD` ("P from D"). Store tensors in Mandel internally. Use Voigt only at solver I/O, with an explicit permutation. |
| D2 | Material v1: homogenised **TI about printer Z**, one card per region class (printed solid = walls + skins + 100% helpers; sparse infill = 0 credit per house rule; thick bridges = 0 credit). v2 (re-analysis only): per-element orthotropic, with bead angle taken from G-code. |
| D3 | Failure v1: two-mode, degree-1-homogeneous index (section 3.2). Tsai-Wu/Hoffman only after off-axis coupons exist. |
| D4 | TO grid = **printer-frame voxels re-built per candidate orientation**, with dz = layer height (0.2 mm) and dxy = 0.2 mm. This matches the existing GPU hex grid and puts layers on grid planes. |
| D5 | Massing = **slicer-faithful directional coating**: walls by in-layer erosion of radius n_w*w, skins by n_t layers of Z erosion, plus a helper field s for 100% modifier volumes. Interior with 0% sparse infill = void (house rule). |
| D6 | Overhang = Langelaar AM filter applied to the **printed-material field** (shell plus helper), not the body envelope. Hollow bodies create internal ceilings. Default 45 deg. Grid anisotropy of the stencil is tested. Orca's slice is the final judge. |
| D7 | Problem v1: minimise worst-case compliance over load cases (bound formulation) subject to volume and an aggregated inter-layer failure-index constraint. Min length = 2 extrusion widths, set with the robust (eroded/dilated) formulation. |
| D8 | Orientation: Fibonacci sweep of build direction d on the sphere. Prescreen with the inter-layer traction map, then full TO on the top K. Spin about Z only at the re-analysis stage. |
| D9 | Verification is never done on the TO model. Threshold, then CAD, Orca slice, toolpath map, and a **zero-ersatz** anisotropic re-analysis (house rule: voids have no stiffness). Report the TO-vs-as-sliced discrepancy. |
| D10 | Material cards carry provenance and a **tier** (T0 TDS+assumptions, T1 own coupons, T2 demonstrator-validated). Cards are process-locked: line width, layer height, speeds, temperatures, profile hash. |
| D11 | The invariants in section 7 become automated tests before any optimiser result is shown to anyone. |

---

## 1. Frames, notation, units

**Units:** N, mm, MPa, mJ (N*mm). These are the same as spool-wall-rack, where every solver docstring says
"N/mm/MPa". Densities are in g/mm^3 internally; TDS values in g/cm^3 are converted at ingest.

**Frames.**

| Frame | Definition | Where it lives |
|---|---|---|
| **D** (design) | CAD frame of the part; loads, BCs, keep-in/keep-out | CadQuery/build123d models, INTERFACE-CONTRACT |
| **P** (printer) | Bed frame; +Z = build direction; layers are planes z = const | TO grid, overhang filter, inter-layer criterion |
| **G** (G-code) | P plus plate placement and **extruder offset** (P1S: Orca subtracts a 0x2 mm nozzle offset; `plastic_shape.py` restores it) | Raw G-code |
| **M** (bead) | e1 = bead tangent t (in the layer plane), e2 = Z x t, e3 = Z | Per-segment / per-element material frame |

**Placement.** `x_P = R_PD x_D + t_PD`. Build direction expressed in D: `d = R_PD^T e_z`. Construct R_PD from
(d, psi): rotate d onto +Z (Rodrigues), then spin psi about Z. **Singular case:** d = -e_z, where Rodrigues has no
unique axis. Handle it explicitly with a 180 deg turn about X and test it.

**Bead frame from a toolpath segment:** `R_PM = [t, e_z x t, e_z]` (columns = M axes expressed in P). This is a proper
rotation (det = +1) for any unit t in the XY plane. t and -t give the same C (sign of the bead direction is
irrelevant), which section 5.3 uses.

**Notation.** Canonical index order is (11, 22, 33, 23, 13, 12).

- **Voigt:** sigma_V = [s11, s22, s33, s23, s13, s12]. eps_V = [e11, e22, e33, g23, g13, g12] with engineering shear
  g = 2*e. Then sigma_V = C_V eps_V.
- **Mandel:** sigma_M = W sigma_V and eps_M = W^-1 eps_V, with `W = diag(1,1,1,sqrt2,sqrt2,sqrt2)`. Then
  `C_M = W C_V W`. Mandel vectors are coordinates in an orthonormal basis of symmetric tensors. Energy satisfies
  `eps_M.C_M.eps_M = eps_V.C_V.eps_V` (checked: difference 4e-12).
- **gpu_hex order** (spool-wall-rack `analysis/rev-g2/gpu_hex.py`, B-matrix rows): (xx, yy, zz, **xy, yz, xz**) with
  engineering shear and `C[3:,3:] = mu`. In canonical indices this is the permutation `[0,1,2,5,3,4]`. Use
  `C_gpu = P C_V P^T`. Checked: C_gpu[3,3] = G12, [4,4] = G23, [5,5] = G13. `stress_tensors()` in the same file uses
  the same (0,0),(1,1),(2,2),(0,1),(1,2),(0,2) order, so it is self-consistent today. **Any new C built in canonical
  order and passed in without the permutation silently swaps G12/G23/G13.**

---

## 2. Anisotropic material model

### 2.1 Hierarchy of models (what is physically anisotropic, at what scale)

| Scale | Object | Symmetry | Notes |
|---|---|---|---|
| Bead | One extruded road, stadium cross-section | Orthotropic in M: 1 = along bead, 2 = bead-to-bead in layer, 3 = inter-layer | 9 constants. Directions 2 and 3 differ: different neck geometry, cooling and contact time. The 2024 PLA study finds inter-layer anisotropy stronger than in-layer anisotropy ([Comp. Struct. 2024](https://www.sciencedirect.com/science/article/pii/S026382312400243X) [v]). |
| Region | Perimeter walls (beads follow the contour) | Orthotropic with e1 = contour tangent, varying in space | Usually 2 to 4 loops = 0.84 to 1.7 mm. Inter-layer bond is bead-on-bead. |
| Region | Solid raster (skins, internal solid, 100% helpers), alternating +/-45 per layer by Orca default | Two-layer stack is **tetragonal** (invariant under Rz(90 deg), not TI). Checked: changes by 23 MPa under Rz(45 deg) for an assumed card. | Exact layered homogenisation in section 2.6. |
| Region | Sparse infill | Pattern-dependent cellular solid | Zero credit in the current house policy (0% base infill). Section 4.8 covers when it is enabled. |
| Region | Thick bridges / sacrificial bridges | — | Zero structural and zero bond credit (house rule, `plastic_shape.py` `structural` flag). |
| Part | Homogenised printed solid | **TI about printer Z** (5 constants) | The v1 design-stage model. In-plane anisotropy is averaged out by +/-45 skins and contour-following walls. This is acceptable because in-plane anisotropy of unfilled PETG/ASA is small, but no PETG/ASA data in hand establishes it. |

Classic references for the bead/laminate view: Ahn et al. 2002, *RPJ* 8(4):248-257 (ABS, raster-angle strength
ratios, Tsai-Wu) [m]. Rodriguez, Thomas, Renaud 2003, *RPJ* 9(4):219-230 (ABS, orthotropic mesostructure) [m].
[Casavola et al. 2016, *Mater. Des.* 90:453-458](https://www.sciencedirect.com/science/article/abs/pii/S0264127515307516)
(classical laminate theory for FDM) [v].
[Zou et al. 2016, *Compos. B* 99:506-513](https://www.semanticscholar.org/paper/Isotropic-and-anisotropic-elasticity-and-yielding-Zou-Xia/744752e7b5f209c8b31391568114c9a60abf7fb3)
(ABS, TI elasticity and Hill yield) [v].
[Kiendl & Gao 2020, *Compos. B* 180:107562](https://www.researchgate.net/publication/336817681_Controlling_toughness_and_strength_of_FDM_3D-printed_PLA_components_through_the_raster_layup)
(PLA, raster layup controls strength and ductility) [v].
Inter-layer weld physics: Seppala et al. 2017 *Soft Matter* 13:6761 [m] and Coogan & Kazmer 2017 *RPJ* 23(2):414 [m].
Both show that bond strength depends on the thermal history at the interface: nozzle temperature, speed, layer
time, fan and chamber temperature.

### 2.2 Data for PETG and ASA (what is known)

Manufacturer TDS. These are ISO 527 / ISO 178 values for 100%-infill specimens. Read the footnotes.

| Grade (source) | E_XY | E_Z | E_Z/E_XY | sigma_t XY | sigma_t Z | Z/XY | Flex. mod. XY / Z | Flex. str. XY / Z | Specimen notes |
|---|---|---|---|---|---|---|---|---|---|
| Bambu PETG HF ([TDS V1.0](https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf) [v]) | 1810+/-190 | 1540+/-130 | 0.85 | 34+/-4 | 23+/-4 | **0.68** | 2050 / 1810 | 64 / 48 | 255 C, 200 mm/s; **annealed + dried 75 C 8 h** |
| Bambu PETG Basic ([TDS V3.0](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf) [v]) | 2780+/-65 | 2550+/-100 | 0.92 | 51+/-1 | 35+/-6 | **0.69** | **1950** / 1740 | 75 / 56 | X1C, 255 C, 150 mm/s; annealing not stated |
| Bambu ASA ([TDS V3.0](https://solidprint3d.ie/wp-content/uploads/2024/03/Bambu-Lab-ASA-Filament-Technical-Data-Sheet.pdf) [v]) | 2450+/-270 | 2120+/-260 | 0.87 | 37+/-3 | 31+/-4 | **0.84** | **1920** / 1650 | 65 / 40 | 260 C, 200 mm/s; **annealed + dried 80 C 12 h** |
| Polymaker PETG (spool-wall-rack `designs/closed-wall-e6/material-reference-data.json`) | 2311 | — | — | 47.96 | 45.71 | 0.95 | 2277 / — | — | Vendor TDS, conditions per source |
| PolyLite ASA (same file) | 2379 | — | — | 43.8 | 32 | 0.73 | 3206 / — | — | Vendor TDS |

Elongation at break also roughly halves in Z: PETG HF 8.6% vs 5.1%, ASA 9.2% vs 4.6%. Failure across layers is
more brittle and dominated by the interface, so a linear-elastic failure criterion is more defensible for the Z
mode than for the XY mode.

**What these numbers do and do not establish.**

- They establish order-of-magnitude ratios: E_Z/E_XY of about 0.85 to 0.92, and sigma_Z/sigma_XY of about 0.68 to
  0.95 between vendors and grades.
- They do **not** give G_xz, G_yz, any Poisson ratio, the inter-layer shear strength S_il, the in-layer
  bead-transverse strength, or compressive strengths.
- **Bending modulus < tensile modulus** for PETG Basic (1950 vs 2780) and ASA (1920 vs 2450), but the reverse for
  PETG HF. These are not a coherent elastic card. Likely causes are specimen layup, walls versus infill fraction,
  and test-fixture compliance. This is unconfirmed.
- **Z flexural strength is 1.3 to 2.1 times Z tensile strength** (PETG HF 48 vs 23). Possible causes are the stress
  gradient and size effect of brittle interface failure, or an ambiguous Z-flexure specimen orientation (the TDS
  drawing does not settle which face is up). **Do not calibrate Z_t from a flexure test without accounting for this.**
- Two of the three Bambu sheets used **annealed** specimens. The user's parts are as-printed, so the Z strengths may
  be optimistic for our parts.
- All values come from Bambu's speeds, temperatures and widths, not the user's production profile. The spool-rack
  profiles use 4 to 8 walls, ASA and PETG, at Orca 2.4.2 defaults or overrides.

**Unknown for our process (must be measured or bracketed):** G13 = G23 (inter-layer shear modulus); nu_p and nu_pz;
S_il; Z compressive strength; temperature dependence near service conditions (PETG Tg is 66 to 71 C, and spool-rack
studies already flag creep at 29 to 38 C); moisture state; rate dependence; fatigue; creep (a separate analysis
already exists in spool-rack e8/e9).

### 2.3 Material card v1 (TI about printer Z)

Five independent constants: E_p (in-plane), E_z, nu_p, nu_pz (= -eps_z/eps_p under sigma_p), G_z (= G_xz = G_yz).
Then G_p = E_p / (2(1+nu_p)).

Positive definiteness requires E_p, E_z, G_z > 0, |nu_p| < 1, and **`1 - nu_p - 2 nu_pz^2 E_z/E_p > 0`**. Check this
at card load and fail loudly.

Tier-0 (T0) placeholder for PETG, used only for **relative** studies:

| Constant | Value | Basis |
|---|---|---|
| E_p | 1810 (HF) to 2780 (Basic) MPa | Bambu TDS, **grade-dependent**: choose the grade actually printed |
| E_z | 0.85 to 0.92 E_p | Bambu TDS ratio |
| nu_p, nu_pz | 0.38, 0.36 | **Assumed** (typical amorphous polymer); bracket 0.33 to 0.40 |
| G_z | 0.32 E_z | **Assumed**: isotropic-like G/E. Inter-layer shear is likely lower; bracket 0.2 to 0.36 E_z |
| X_t (in-layer) | sigma_t XY from TDS | TDS (annealed: optimistic) |
| Z_t | sigma_t Z from TDS | TDS (annealed: optimistic) |
| S_il | **unknown**; bracket 0.5 to 1.0 Z_t | Assumption. Must be measured (section 6) |

Every result computed with a T0 card should be run at the bracket corners of the assumed values. Report the result
as an interval or a ranking, never as a point allowable.

### 2.4 Rotating the stiffness tensor (exact, with pitfalls)

**Definition.** If a symmetric tensor transforms as `A' = R A R^T`, its Mandel vector transforms as `a' = Q(R) a`, where

```
Q_IJ = B_I : (R B_J R^T)          (B_I = orthonormal Mandel basis tensors)
```

Explicitly, with normal indices i,j and shear pairs (k,l):

```
Q[i, j]       = R_ij^2
Q[i, (kl)]    = sqrt2 * R_ik R_il
Q[(kl), j]    = sqrt2 * R_kj R_lj
Q[(ij), (kl)] = R_ik R_jl + R_il R_jk
```

**Q is orthogonal**, so `C'_M = Q C_M Q^T`, `S'_M = Q S_M Q^T`, and eigenvalues of C_M are rotation-invariant.
Checked numerically: |QQ^T - I| ~ 1e-15, and the result agrees with the full 4th-order rotation
`C'_ijkl = R_ip R_jq R_kr R_ls C_pqrs` to 1e-12.

**Voigt equivalent (Bond matrices):** `T_sigma = W^-1 Q W`, `T_eps = W Q W^-1 = T_sigma^-T`, and
`C'_V = T_sigma C_V T_sigma^T`. T_sigma is **not** orthogonal. Checked: agrees with the Mandel route to 1e-12.

**Which R.** For a material card C^M defined in the bead frame, the stiffness in the printer frame is
`C^P = Q(R_PM) C^M Q(R_PM)^T`. The columns of R_PM are the M axes written in P. For a design-frame FE mesh,
`C^D = Q(R_PD^T R_PM) C^M Q(...)^T`.

**Measured pitfalls** (illustrative orthotropic card, E1/E2/E3 = 1810/1650/1540 MPa, `tensor_checks.py`):

| Bug | Max error in C |
|---|---|
| Mandel Q applied to a Voigt C (factor-of-2 shear mix-up) | **239 to 484 MPa** |
| Inverse rotation (R instead of R^T, i.e. `T^-1 C T^-T`) | **55 to 133 MPa** |
| Canonical C passed to `gpu_hex` without the (xx,yy,zz,xy,yz,xz) permutation | swaps G12, G23 and G13 |
| Mandel-stored stress fed to a strength criterion without dividing the shear by sqrt2 | 41% overestimate of tau in the failure index |

**Derivative for gradient-based orientation:** with `dR/dtheta = K R` (K skew),
`dQ = Q-form(dR, R) + Q-form(R, dR)` and `dC/dtheta = dQ C Q^T + Q C dQ^T`. Checked against central finite
differences: relative error 2e-9. This is available if continuous in-plane angle design is ever wanted.

### 2.5 How build direction and raster angle enter

- **Build direction d** (2 DOF on the sphere) is the symmetry axis of the TI card and the normal of every inter-layer
  plane. For TI, the C seen in the design frame depends **only** on d. Spin psi about Z has no effect, and that
  invariance is a useful test (checked: |Q C Q^T - C| = 9e-13 under Rz).
- **Directional modulus** for the T0 PETG HF-like TI card (E_p 1810, E_z 1540, assumed nu and G), with
  `1/E(n) = (n(x)n) : S : (n(x)n)`:

  | Angle from layer plane | 0 | 15 | 30 | 45 | 60 | 75 | 90 deg |
  |---|---|---|---|---|---|---|---|
  | E(n), MPa | 1810 | 1764 | 1667 | 1582 | 1542 | 1537 | 1540 |

  The total variation is 15%, and it is nearly flat beyond 45 deg. **Stiffness alone gives weak orientation signal**
  for these materials.
- **In-plane raster angle** enters only through bead-level orthotropy: solid-infill direction, the +/-45 alternation,
  and the wall-contour tangent. At the design stage it is averaged away (D2). At re-analysis it is read from the
  G-code per element (section 5).

### 2.6 Layered homogenisation (when one FE cell spans several layers)

For perfectly bonded layers normal to z, the in-plane strains (e11, e22, e12) and the out-of-plane stresses (s33,
s23, s13) are continuous across layers. The exact effective stiffness comes from averaging the **partial inverse**:

```
[sigma_a]   [Caa - Cab Cbb^-1 Cba    Cab Cbb^-1] [eps_a  ]
[eps_b  ] = [ -Cbb^-1 Cba            Cbb^-1    ] [sigma_b],     a = {11,22,12}, b = {33,23,13}
```

Average M over the layer volume fractions, then invert the partial inversion (Sun & Li 1988,
[*J. Compos. Mater.* 22(7):629](https://journals.sagepub.com/doi/abs/10.1177/002199838802200703) [v]).
Implemented in `laminate_checks.py`. A round-trip with identical layers returns the input to 1e-13.

For an illustrative +/-45 stack (bead card E1/E2/E3 = 2000/1500/1300 MPa):

| Method | E_x | E_45 | E_z | G_xz |
|---|---|---|---|---|
| Exact | 1733.7 | 1754.3 | 1303.9 | 499.2 |
| Voigt average of C | 1733.7 | 1755.5 | 1303.9 | 500.0 |
| Reuss average of S | 1720.3 | 1714.3 | 1300.0 | 499.2 |

**For mildly anisotropic PETG/ASA the averaging method is immaterial** (below 0.1% for Voigt vs exact). Use the exact
version anyway: it costs nothing and stays right for filled or CF materials.

**Where this matters in existing code:** `ADAPTIVE-MESH.md` merges 8 fully occupied 0.2 mm siblings into one
0.4 mm hex, so one coarse cell spans 2 layers. With anisotropy, siblings can merge only if they share material
class and orientation, or the coarse cell must receive the exact laminate C.

### 2.7 Inter-layer weakness: geometric facts to build in

1. **Bead neck.** The Slic3r/Orca flow model uses a stadium cross-section with area `h(w - h(1 - pi/4))`. For
   w = 0.42 and h = 0.2 this is 0.0754 mm^2, against w*h = 0.084. The flat contact width between stacked beads is
   nominally `w - h = 0.22 mm` = **52% of nominal width**. Squish and reheating enlarge the real weld. The nominal
   footprint union used by `audit_g_slicer_mapping.py` and `gpu_material_probe.py` assumes full contact. **That is
   fine provided the inter-layer constants are calibrated on coupons analysed with the same footprint idealisation.**
   Card and FE domain must share one geometric convention (gross nominal footprint).
2. **Leaning walls.** A wall stepping outward by h*tan(beta) per layer keeps an overlap fraction
   `f(beta) = max(0, 1 - h tan(beta)/w)`:

   | w, h | beta = 30 | 45 | 55 | 60 | zero at |
   |---|---|---|---|---|---|
   | 0.42, 0.20 | 0.73 | 0.52 | 0.32 | 0.18 | **64.5 deg** |
   | 0.42, 0.12 | 0.84 | 0.71 | 0.59 | 0.51 | 74.1 deg |
   | 0.42, 0.28 | 0.62 | 0.33 | 0.05 | 0 | 56.3 deg |

   Bambu quotes a "max overhang ~70 deg" for both materials. That figure is printability, not strength; the angle
   convention is unspecified. **Hypothesis (needs coupons):** inter-layer stiffness and strength on overhang walls
   scale with f. Use `Z_t,eff = g(f) Z_t` with g(f) = f as the first model.
3. **Smeared, not cohesive.** With dz equal to one layer per cell, explicit cohesive interfaces would add a face
   element at every layer, which is not worth it at part scale. Smear the weakness into E_z, G_z, Z_t and S_il, and
   scale per element by the mapped bond fraction b (section 5.3).

---

## 3. Failure criteria and stress measures for optimisation

### 3.1 Options

| Criterion | Constants needed | Pros | Cons for our data budget |
|---|---|---|---|
| Max stress in M frame | X_t, X_c, Y_t, Y_c, Z_t, Z_c, S12, S13, S23 | Mode-explicit, simple | No interaction; many constants |
| Tsai-Hill / Hill48 | X, Y, Z, S's (symmetric in tension/compression) | Smooth, one equation; Zou 2016, Yao 2019 used Hill for FDM | Treats compressive inter-layer stress as damaging, which is wrong for interfaces |
| Tsai-Wu (Tsai & Wu 1971, *J. Compos. Mater.* 5:58 [m]) | F_i, F_ij including **F12** (needs biaxial data) | Tension/compression asymmetry, general | F12 cannot be measured in uniaxial coupons. Used for FDM TO by [Mirzendehdel et al. 2018](https://par.nsf.gov/servlets/purl/10057716) [v] and [Kundu & Zhang 2023, *Addit. Manuf.* 75:103730](https://doi.org/10.1016/j.addma.2023.103730) [v] |
| Hoffman (Hoffman 1967 [m]) | Uniaxial strengths only (F12 implied) | Asymmetric, no biaxial test needed | Interaction implied, not measured. Used by [Zou & Xia 2023, *JCDE* 10(2):892](https://academic.oup.com/jcde/article/10/2/892/7110403) [v] |
| Hashin-type modes (Hashin 1980, *J. Appl. Mech.* 47:329 [m]) | Per mode: e.g. inter-layer (Z_t, S_il) | Physically separate modes. Interface compression is not counted as damage | Mode switch is non-smooth (needs smoothing for gradients) |

### 3.2 Recommended v1 criterion (defensible with about 3 measured strengths)

Let n = e_z^P be the layer normal, expressed in whatever frame the stress is in (in D: n = d). The traction on the
layer plane is t = sigma n, with sigma_n = n.sigma.n and tau = |t - sigma_n n|.

```
F_L = sqrt( (<sigma_n>+ / Z_t,eff)^2 + (tau / S_il,eff)^2 )     inter-layer mode (Hashin-like, interface)
F_P = sigma_vM / X_t                                              in-layer mode (bead-level effects averaged)
F   = max(F_L, F_P)          reserve factor RF = 1/F
```

- **Homogeneous of degree 1:** F(lambda*sigma) = lambda*F(sigma). The index scales linearly with load, which matters
  for aggregation and for reporting a load factor. The quadratic forms above have this property; a raw Tsai-Wu
  polynomial does not.
- `<x>+` is the Macaulay bracket. For gradients use `(x + sqrt(x^2 + delta^2))/2` with delta about 1e-3 Z_t.
  Compression across layers does not open the interface. Ignoring its friction benefit is conservative.
- Z_t,eff and S_il,eff = g(b) times the card values, where b is the bond fraction (sections 2.7 and 5.3). Use b = 1
  at the design stage.
- Illustrative uniaxial strength at angle phi from the layer plane (X_t = 34, Z_t = 23; Tsai-Hill-like with an
  in-plane term; `tensor_checks.py`):

  | S_il | 0 | 15 | 30 | 45 | 60 | 75 | 90 deg |
  |---|---|---|---|---|---|---|---|
  | 15 | 34.0 | 31.0 | 26.4 | 23.6 | 22.6 | 22.8 | 23.0 |
  | 25 | 34.0 | 34.1 | 33.2 | 30.3 | 26.6 | 23.9 | 23.0 |

  The 45 deg value differs by 28% across the S_il bracket. **One 45 deg off-axis coupon is therefore worth more
  than any other single additional test** (section 6).
- Upgrade path: Tsai-Wu or Hoffman in the M frame only after the off-axis coupon exists, and only for the re-analysis.
  For a non-homogeneous polynomial, use the **strength ratio** lambda from `a lambda^2 + b lambda - 1 = 0`
  (a = sigma.F2.sigma, b = F1.sigma), giving lambda = (-b + sqrt(b^2 + 4a))/(2a). Then 1/lambda is a degree-1 index.
  This is the device used by Mirzendehdel et al. 2018.

### 3.3 Aggregation and relaxation for TO

- **Relaxation (avoid singular optima):** evaluate F on the "solid-material" stress `sigma_e = rho_e^q C_0,e B u_e`
  with q < p, the qp-approach (Bruggi 2008, *SMO* 36:125 [m]). The [Le et al. 2010, *SMO* 41:605](https://link.springer.com/article/10.1007/s00158-009-0440-y)
  [v] variant uses q = 1/2 with p = 3. Alternative: epsilon-relaxation (Duysinx & Bendsoe 1998, *IJNME* 43:1453 [m]).
- **Aggregation:** p-norm `F_PN = (sum_e v_e F_e^P)^(1/P)`, with Le et al.'s adaptive normalisation
  `c_k = F_max^(k-1)/F_PN^(k-1)` (damped). Optional clustering (Holmberg et al. 2013, *SMO* 48:33 [m]). For a
  unified lower-bound aggregation-relaxation see [Verbart et al. 2017, *SMO* 55:663](https://link.springer.com/article/10.1007/s00158-016-1524-0) [v].
  For v2, consider augmented-Lagrangian local constraints, which avoid aggregation
  ([Senhora et al. 2020, *SMO*](https://link.springer.com/article/10.1007/s00158-020-02573-9) [v]).
- **Aggregate F_L and F_P as two separate constraints.** Then each mode's sensitivity stays readable, and the
  inter-layer constraint can be switched on alone (it is the orientation-sensitive one).
- **Honesty rule (continuing spool-rack practice):** the p-norm is an optimisation device. Every verification
  reports raw per-Gauss-point maxima, percentiles and locations. Raw peaks at re-entrant corners do not converge
  under refinement and must be labelled so.

---

## 4. Topology optimisation formulation

### 4.1 Grid and frame

- Per candidate build direction d, re-voxelise the design domain, keep-in (PROTECT solids in `build_d9.py`
  terminology), keep-out, loads and BCs into the **P frame**. Layers then lie on grid planes, the overhang filter
  runs along a grid axis, and the inter-layer criterion uses the grid z axis directly.
- **dz = layer height (0.2 mm), dxy = 0.2 mm.** This equals the existing `gpu_hex` / evo grid. Minimum feature 2w =
  0.84 mm is about 4 cells: marginal but workable. Coarse sweeps can use 0.4 mm cells with the exact laminate
  homogenisation of section 2.6.
- Check after each re-voxelisation: total applied force and moment about a fixed point, expressed in D, match the
  source to round-off. Spool-rack's force/moment gates already do this.

### 4.2 Design variables and filter chain

Two fields on the P grid: the **body** density rho and a **helper** field s (where to place a 100% modifier volume).

```
rho_tilde = H_M rho                              anisotropic density filter
            w_ei = max(0, 1 - |x_e - x_i|_M)  with |dx|_M^2 = (dx^2 + dy^2)/r_xy^2 + dz^2/r_z^2
rho_bar   = [tanh(beta eta) + tanh(beta(rho_tilde - eta))] / [tanh(beta eta) + tanh(beta(1 - eta))]
            (Wang, Lazarov & Sigmund 2011, SMO 43:767 [m]; Guest et al. 2004 IJNME 61:238 [m])
xi        = AM_filter(printed_material(rho_bar, s))            overhang, section 4.5
```

- Density filter: Bruns & Tortorelli 2001 [m], Bourdin 2001 [m]. A PDE filter (Lazarov & Sigmund 2011, *IJNME*
  86:765 [m]) suits GPU/multigrid; that is Legolas's call.
- **Boundary effects:** pad the domain by the filter radius with void, except at symmetry planes (mirror) and at the
  **bed plane** (the AM filter treats it as support).
  [Clausen & Andreassen 2017, *SMO* 56:1147](https://link.springer.com/article/10.1007/s00158-017-1709-1) [v].
- beta continuation, for example 1, 2, 4, 8, 16, 32 every 40 to 50 iterations. Apply the volume constraint to the
  physical field.
- Optimiser: MMA (Svanberg 1987, *IJNME* 24:359 [m]). The bound formulation for minimax compliance fits MMA's form.

### 4.3 Interpolation with anisotropic C and multiple phases

SIMP for a single printed phase (Bendsoe & Sigmund 1999, *Arch. Appl. Mech.* 69:635 [m]):

```
C_e(rho_bar) = [E_min/E_0 + rho_bar_e^p (1 - E_min/E_0)] * C_0,e        p = 3 (continuation from 1), E_min/E_0 = 1e-6
```

Scaling the **whole tensor** by a scalar keeps symmetry and positive definiteness. C_0,e already contains the
rotation for orientation d. Under RAMP (Stolpe & Svanberg 2001, *SMO* 22:116 [m]) the scalar becomes
rho/(1 + q(1 - rho)). Multi-phase interpolation follows in section 4.4.

**House rule conflict, resolved by staging:** spool-rack forbids ersatz void stiffness in *analysis*
("No density floor or ersatz stiffness is used", `gpu_hex.py`). TO needs E_min > 0 for well-posedness. So:
**E_min exists only inside the optimiser.** Every reported number comes from the thresholded, sliced, zero-ersatz
re-analysis (D9). A large TO-vs-reanalysis gap flags reliance on grey material.

### 4.4 Massing: slicer-faithful directional coating (the "orientation-dependent massing" core)

Orca's construction:

- **Walls:** in each layer, the inward offset of the layer polygon by n_w*w.
- **Top and bottom skins:** in each layer, the region not covered by the n_t layers above (top) or n_b layers below
  (bottom).
- **Interior:** what remains. At 0% sparse infill it is void, unless a 100% helper modifier covers it.

This is erosion with two different structuring elements: a disc in XY and a line segment in Z. Hence the
surface-normal shell thickness

```
t(alpha) = max( n_w w sin(alpha), n_t h cos(alpha) )      alpha = surface inclination from horizontal
t_min    = n_w w n_t h / sqrt((n_w w)^2 + (n_t h)^2)   at  tan(alpha*) = n_t h / (n_w w)
```

| Walls x w | Skins x h | t_min | at alpha* |
|---|---|---|---|
| 2 x 0.42 | 5 x 0.2 | **0.64 mm** | 50 deg |
| 2 x 0.42 | 3 x 0.2 | 0.49 mm | 35.5 deg |
| 4 x 0.42 | 5 x 0.2 | 0.86 mm | 30.8 deg |

So rotating a part changes **which surfaces are thin-skinned**. This is the orientation-dependent massing a collaborator
described, in closed form. Orca's `ensure_vertical_shell_thickness` (`ensure_all` in G's effective settings) adds
solid infill to compensate. The re-analysis sees the real result; the design model must approximate it.

**Differentiable formulation** (extends Clausen, Aage & Sigmund 2015,
[*CMAME* 290:524](https://doi.org/10.1016/j.cma.2015.02.011) [v]. That paper uses a gradient-norm coating of
uniform thickness. The erosion-based shell identification is from
Luo, Li & Liu 2019, *CMAME* 355:94 [v, bibliographic only]):

```
I_xy = H_eta_e( F_disc(r = n_w w) rho_bar )                   in-layer erosion  (2D filter per layer + high threshold)
I_z  = smin_{j = -n_b..n_t} rho_bar(k + j)                    Z erosion by n_b/n_t layers (smooth min over a column)
I    = I_xy * I_z                                              interior (smooth AND)
shell = rho_bar * (1 - I)
core  = rho_bar * I
C_e  = C_min + shell^p C_shell + core^p [ s_bar^p C_solid + (1 - s_bar^p) C_core ]
       C_core = 0 for 0% sparse infill (house rule); E_min regularisation only
```

- Thresholds for erosion depth: Luo et al. 2019 give relations for the threshold-versus-radius calibration (also
  [Fernandez et al. 2021](https://link.springer.com/article/10.1007/s00158-021-02998-w) [v] for robust-formulation
  length scales). **Verify numerically** that the smooth erosion of a flat slab yields n_w*w +/- one cell.
- C_shell = C_solid = the TI "printed solid" card in v1. Walls and skins have different bead layups, but neither the
  data nor the mild anisotropy justifies separate cards yet.
- **The outputs map one-to-one onto the user's existing Orca controls:** body STL (thresholded rho_bar), helper
  modifier STL (thresholded s_bar inside the body) and wall_loops / skin counts. That matches
  `designs/rev-g2/print-controls/*` (n-wall ASA/PETG, 100% helpers, 0% base infill).
- **Hollow bodies need buckling checks.** Thin 0.84 mm shells under compression buckle before they yield. Stiffness
  and stress TO does not see this, so keep spool-rack's `rev-g/buckling.py` route for verification. Background:
  Clausen, Aage & Sigmund 2016, *Engineering* 2(2):250 (infill for buckling) [m].
- Related shell-infill TO: [Wu, Clausen & Sigmund 2017, *CMAME* 326:358](https://backend.orbit.dtu.dk/ws/files/134847727/MARAC_1_s2.0_S0045782517305984_main.pdf) [v];
  Wu, Aage, Westermann & Sigmund 2018, *IEEE TVCG* 24(2):1127 (bone-like infill, local volume constraint) [m].

### 4.5 Minimum length scale tied to extrusion width

- Rule (double-bead repo, `README.md`/`SPEC.md`): **nominal strokes and minimum clear gaps are two extrusion
  widths**. For w = 0.42 the minimum solid and minimum void are both 0.84 mm in XY. In Z, the minimum plate
  thickness is n_t*h (for example 3 layers = 0.6 mm). This is a separate radius, hence the anisotropic filter metric
  in section 4.2.
- Enforce it with the **robust formulation** (eroded/nominal/dilated, eta = 0.5 +/- delta_eta). Optimise the worst
  case, report the nominal design. Use Fernandez et al. 2021's relations to pick (r, delta_eta) for a target
  length, then **measure** the realised minimum feature with a distance transform on the thresholded design.
- A min-length violation surviving into the sliced G-code shows up as Gap infill / single-wall segments in the
  toolpath roles. That check is cheap with the existing role parser.
- Related: [Jewett & Carstensen 2023, *Comput. Struct.* 289:107158](https://www.sciencedirect.com/science/article/abs/pii/S0045794923001888)
  [v]: fixed bead-radius features plus a weak secondary "bond" material between beads.
  [Kim-Tackowiak & Carstensen 2025, *Mater. Des.* 259:114700](https://www.sciencedirect.com/science/article/pii/S0264127525011207)
  [v]: toolpath consideration increases test-vs-model fidelity.

### 4.6 Overhang / self-support and how build direction enters

**Angle conventions differ between sources; pin one down.** Define alpha_s = surface inclination from horizontal.
A down-facing surface is self-supporting if alpha_s >= alpha_min (default 45 deg, which equals overhang beta <= 45
deg from vertical).

- `build_d9.py selfsupport()` tests `n.down > cos 45 deg` on the face normal at its centre. That is the same 45 deg,
  sampled at one point per face.
- Orca's support threshold angle is measured from horizontal.
- Bambu's "max overhang ~70 deg" leaves its convention unstated.

**Langelaar AM filter** ([2016, *Addit. Manuf.* 12:60](https://doi.org/10.1016/j.addma.2016.06.010) [m, DOI not
re-checked]; [2017, *SMO* 55:871](https://doi.org/10.1007/s00158-016-1522-2) [v]):

```
for layers k = 1..N (bed = layer 0, fully supporting):
  Xi_e = smax_{s in S_e (layer k-1)} xi_s          smooth max (P-norm-type)
  xi_e = smin(rho_e, Xi_e)                          smooth min
sensitivities: adjoint sweep k = N..1
```

- **Apply it to the printed-material field (shell plus helper), not to rho_bar.** With 0% infill, the inside of every
  hollow body has internal ceilings. These must be self-supporting (for example diamond or teardrop cavities) or
  bridged within the bridging limit: Bambu TDS gives ~30 mm for PETG and ~40 mm for ASA [v], and spool-rack assigns
  sacrificial bridges zero credit. The envelope alone can be self-supporting while its interior is not.
- **Stencil reach and voxel aspect set the angle:** tan(beta_max) = reach*dx/dz. With 1-cell reach on 0.2 mm cubes,
  beta = 45 deg. With 2-cell reach, beta = 63.4 deg, almost exactly where the nominal wall overlap reaches zero
  (64.5 deg, section 2.7). That is too aggressive, so keep 1 cell.
- **The stencil makes the grid anisotropic.** A 3x3 support stencil allows 45 deg along axes but 54.7 deg along
  diagonals. A 5-point cross allows 45 deg along axes and about 35 deg along diagonals. Test: rotate an inverted cone
  about Z and record the accepted angle versus azimuth (invariant I13). Mitigate with disc stencils at finer reach,
  or with front propagation, which gives arbitrary angles on unstructured meshes (van de Ven et al. 2018, *SMO*
  57:2075 [m]; [3D, CMAME 2020](https://www.researchgate.net/publication/342391766_Overhang_control_based_on_front_propagation_in_3D_topology_optimization_for_additive_manufacturing) [v]).
- Alternatives:
  - [Gaynor & Guest 2016, *SMO* 54:1157](https://link.springer.com/article/10.1007/s00158-016-1551-x) [v]:
    projection with a support wedge, combined with minimum length.
  - Pellens et al. 2019, *SMO* 59:2005 [v, bibliographic only]: combined length scale and overhang.
  - [Kumar & Fernandez 2022, arXiv:2204.07333](https://arxiv.org/abs/2204.07333) [v]: length scale + overhang + build orientation.
  - Qian 2017, *IJNME* 111:247 [m]: a density-gradient integral measure in which d enters **smoothly**. This is the
    route if orientation ever becomes a gradient variable.
- **Ground truth is not the filter.** It is (a) an exact geometric face-normal check on the thresholded CAD
  (`selfsupport()`-style, but over sampled points, not face centres), and (b) Orca's own overhang/support
  classification of the slice (Overhang wall / Bridge roles in the G-code).

### 4.7 Objectives, load cases and orientation

**Problem v1:**

```
min_{rho, s, t}  t
s.t.  c_k(rho, s) <= t                    k = 1..K load cases (bound formulation: minimax compliance)
      F_PN,L(rho, s) <= 1/SF_L            aggregated inter-layer failure index, all elements x all load cases
      F_PN,P(rho, s) <= 1/SF_P            aggregated in-layer index
      V(printed material) <= V*           volume of shell + helper (actual plastic), not body envelope
      robust: all of the above on the eroded design (for stiffness) / dilated design (for volume)
```

- Weighted-sum compliance is an acceptable fallback. Minimax is preferred when load cases are disparate, such as a
  spool load versus insertion.
- A stress-objective formulation (minimise F_PN at fixed volume) is a v2 option. Stress-only problems are more
  nonconvex and more sensitive to aggregation parameters.

**Orientation design.** Compare a **discrete sweep** with continuous/gradient orientation:

| Option | Pros | Cons |
|---|---|---|
| **Discrete sweep** (recommended v1) | Embarrassingly parallel, robust; each TO is standard; handles the non-differentiable AM filter and re-voxelisation | Cost = N_d x one TO. Mitigate with a prescreen and coarse grids |
| Continuous orientation as a design variable ([Langelaar 2018, *SMO* 57:1985](https://doi.org/10.1007/s00158-017-1877-z) [v], 2D; [Olsen & Kim 2020, *SMO* 62:1989](https://link.springer.com/article/10.1007/s00158-020-02590-8) [v], 3D; Wang & Qian 2020, *CMAME* 372:113385 [m]) | One optimisation | Multimodal in d; needs a smooth overhang measure; local optima. Published demos are mostly compliance-only |

Build-orientation selection without TO: Ulu, Korkmaz, Yay, Ozdoganlar & Kara 2015, *J. Mech. Des.* 137(11):111410
[v, bibliographic only; no link retrieved].

**Inter-layer traction prescreen (cheap, no FE per direction).**

1. Take one stress field sigma^D(x), from an isotropic solve of the full design domain or of the incumbent design.
2. For each candidate d on a Fibonacci sphere (N about 200, about 14 deg spacing; up and down differ for overhang,
   so use the full sphere), compute per element `sigma_n = d.sigma.d`, `tau = |sigma d - sigma_n d|`, `F_L(d)`, then
   aggregate.
3. That costs N x n_elements x 9 flops: seconds.

It is justified because E_z/E_p is about 0.85, so the elastic field barely depends on d. It ignores redesign, so it
can only **rank and prune** directions. Run full TO on the top K (for example 5 to 10), plus an overhang/support
estimate. Then slice and re-analyse the top K', sweeping spin psi only there (bed fit, seam, raster).

### 4.8 Infill and lattice homogenisation (only if non-zero sparse infill is ever allowed)

House policy is 0% base infill, sparse infill gets zero credit, and helpers are 100%. If that changes:

- Treat sparse infill as a homogenised phase C_core(rho_inf, pattern), obtained by **periodic RVE homogenisation**
  of the actual Orca pattern on the GPU hex solver. Spool-rack's GPU review already lists homo3d/chfem as references.
- Gibson-Ashby form `E*/E_s = C rho*^n`. 2D-extruded rectilinear/grid patterns are stretching-dominated along their
  lines (n about 1) and strongly anisotropic with weak shear. Gyroid is nearly isotropic and bending-dominated
  (n about 2) ([MDPI Appl. Sci. 12(4):2180, 2022](https://www.mdpi.com/2076-3417/12/4/2180) [v]).
- Graded infill: Wu et al. 2018 *TVCG* [m]; de-homogenisation: Groen & Sigmund 2018 *IJNME* 113:1148 [m].
- Infill phase and orientation as TO phases with Tsai-Wu: Kundu & Zhang 2023 [v].
- Bead-path alignment to stress needs multi-axis hardware, which a P1S is not
  ([Fang et al. 2020, *ACM TOG* 39(6):204](https://doi.org/10.1145/3414685.3417834) [v]). On a planar printer the
  only levers are the raster angle per region (Orca modifiers) and the wall-contour tangent.

---

## 5. Toolpath-aware re-analysis (G-code to per-element material)

### 5.1 What the existing code does (read-only review)

| File | Does | Does not |
|---|---|---|
| `analysis/rev-g2/plastic_shape.py` `read_paths` | Parses G0/G1, M82/M83, G90/G91 and G92. Reads `;TYPE`/`;FEATURE`, `;WIDTH`, `;HEIGHT`, `;Z`. Restores the **extruder offset** and inverts the **3MF item transform** (asserts orthonormal and Z-preserving). Applies model-to-installed transform. Gives per-segment width, height, top z, role and E-volume. Separates priming lines. Asserts **object E-volume within 0.1% of Orca's footer**, no sparse infill, and planar extrusion. Excludes thick bridges as `structural=False`. Hashes G-code and 3MF. | Ignores G2/G3 arcs. The 0.1% footer guard would catch dropped arcs, so keep `arc_fitting` off in profiles or parse arcs. No direction or orientation output. The model-to-installed default is part-specific. |
| `designs/closed-wall-e13/inspect_toolpaths.py` `parse` | Older reader. Same transform logic; buffers nominal footprints by w/2. | Hard-codes layer = round(z/0.2) - 1 and the part's installed offsets (250, 182). Not general; use `plastic_shape` instead. |
| `analysis/rev-g2/audit_g_slicer_mapping.py` | Diagnostic only: per-layer exact planar sections of the archived tetra FEM versus the union of emitted non-sparse footprints in an ROI. Reports extra and uncovered area at 0.03 mm tolerance. Hash-pinned. Result: FEM 2542.4 vs emitted 2547.9 mm^3, 18.1 mm^3 emitted outside, 1.4 mm^3 uncovered. | Says it cannot be used to reuse old stress. No orientation, no anisotropy. |
| `analysis/rev-g2/gpu_material_probe.py` / `GPU-VALIDATION.md` | Conservative voxeliser: keeps a voxel only if **every** raw slab crossing its Z interval fully covers its XY rectangle. Omits 17.1/8.4/4.3% of raw material at 0.4/0.2/0.1 mm XY. | No fractional occupancy, no orientation. |
| `analysis/rev-g2/gpu_hex.py` | Matrix-free Q1 hex, uniform grid, **one shared Ke** (isotropic E, nu). Face-connected node splitting (no edge/corner bonds), 8 Gauss stresses per cell, contact active set. | Per-element C. |
| `analysis/rev-g2/solve_plastic.py` | skfem P1 tets with `linear_elasticity(lam, mu)`. Docstring: "isotropic printed-material screen". | Anisotropy. |

### 5.2 What is missing

1. Per-segment **direction** (already implicit in the 2-point segments) carried into the voxel map.
2. **Role to material class**, configured rather than hard-coded:
   - {Outer wall, Inner wall, Overhang wall, Gap infill} map to the wall card.
   - {Internal solid infill, Top surface, Bottom surface, Bridge (thin)} map to the solid raster card.
   - Sparse infill maps to 0 or the infill card.
   - Thick bridge maps to 0.
3. **Per-element inter-layer bond fraction** b between layers k and k+1. This is fractional, not the current
   binary face-bond rule.
4. **Per-element C** in both solvers, plus anisotropic stress recovery and failure evaluation in the M or P frame.
5. A **card schema** with provenance and tier.
6. **Synthetic G-code fixtures** with known answers (section 7).

### 5.3 Mapping algorithm (per layer k; voxel z-extent = layer k)

For each segment s in layer k with unit direction t_s, width w_s and role r_s, rasterise its footprint (the segment
buffered by w_s/2, consistent with `union_footprints`) onto the cell XY grid by supersampling (for example 4x4 per
cell). Accumulate per cell:

```
occupancy        phi_e   = covered fraction
structure tensor A_e     = sum_s a_es t_s (x) t_s        (a_es = covered area of s in e; sign-free in t)
role fractions   r_e[c]  = covered area by material class c
bond fraction    b_e     = area(footprint_k  intersect  footprint_k+1  intersect  cell) / cell area
```

- Orientation theta_e is the principal eigenvector of A_e. **Coherence** `kappa_e = (l1 - l2)/(l1 + l2)`. If kappa
  is low (corners, crossings, gap infill), use the area-weighted Voigt average of the rotated cards. That is an
  upper bound; flag such cells and report their volume fraction.
- `C_e = Q(R_PM(theta_e)) C_class Q^T`, with inter-layer entries and strengths scaled by g(b_e). Section 2.7 states
  this as a hypothesis.
- A 0.2 mm cell contains at most about one bead width (w = 0.42), so in-layer orientation is well defined almost
  everywhere. The +/-45 skin alternation is **resolved explicitly** (one layer per cell), so no laminate
  homogenisation is needed at 0.2 mm.
- **Conservation checks:** sum of phi_e * V_e versus sum of footprint area x h versus E-volume (footer) must agree
  within stated tolerances. These are the existing checks, extended. Also check the orientation histogram against
  Orca settings (solid infill direction, alternation).

### 5.4 Solver implications (mechanics side; performance is Legolas's)

- On a uniform grid, B at the 8 Gauss points is **shared**. Only C_e varies, so the element apply is
  `K_e u_e = sum_q w_q B_q^T C_e B_q u_e`. Store C_e as 21 numbers, or as an index into a library of orientation
  classes: quantised theta (for example 2 deg), class, and b bins.
- Storing a 24x24 Ke per element is 4.6 kB per cell, about 39 GB for the 8.5 M-cell G mesh. Not viable.
- Jacobi preconditioning (the current default) degrades with heterogeneity. Note it for the solver owner.
- **Patch test with anisotropic C:** an affine displacement must give stress = C eps exactly in every cell, for
  random rotated C. This extends `validate_gpu_hex.py`'s affine test.

---

## 6. Validation and calibration (P1S, 0.4 mm, PETG and ASA)

**Principles.**

- Print coupons with the **production profile**: same line widths, layer height, speeds, temperatures, fan, chamber
  state, filament lot and drying. Record the Orca profile hash and the coupon G-code hash, as spool-rack already does.
- **Run the toolpath mapper on the coupon G-code** to confirm the gauge section contains the intended roles and bead
  angles.
- Name orientations per ISO/ASTM 52921 (XYZ, ZXY, ...) [m]. Use gross nominal cross-section, the same as the FE
  convention (section 2.7).
- Condition as the parts will be: as-printed, 23 C, at least 48 h. Annealing only if parts will be annealed.
- n >= 5 per condition (the ISO 527 minimum).

| # | Test (standard) | Orientation / layup | Measures | Pins down in card | Notes |
|---|---|---|---|---|---|
| C1 | Tension (ISO 527-2 1A or ASTM D638 I) | Flat, production skins (+/-45) + walls | E_p, X_t, (nu_p with DIC) | E_p, X_t, nu_p | Without transverse strain (DIC/gauge), nu stays assumed |
| C2 | Tension | Upright (Z) | E_z, Z_t, failure location | E_z, Z_t | Tall thin prints wobble: use a stubby gauge or print a block and machine it. The highest-value single test |
| C3 | Inter-layer shear: V-notched (ASTM D5379 / D7078) or double-notch shear (ASTM D3846) with the notch plane on a layer plane | Layers parallel to the shear plane | S_il, G_z (with DIC) | S_il, G_z | Precedent: [efficient inter-layer shear characterisation, JMR&T 2023](https://www.sciencedirect.com/science/article/pii/S2238785422020361) [v]; [Polymers 14(19):4028](https://doi.org/10.3390/polym14194028) [v]. Short-beam shear (D2344/ISO 14130) gives only "apparent" shear; ductile PETG may yield in flexure first |
| C4 | Off-axis tension | Gauge at 45 deg to layers (printed as a block at 45 deg, then machined) | Strength at 45 deg | **Validates the interaction** in F_L (section 3.2 shows a 28% spread at 45 deg) | Calibrate with C1 to C3, then predict C4 before testing |
| C5 | Overhang-wall tension | Wall leaning beta = 30/45/55 deg, load across layers | Z_t,eff(beta) | g(f) in section 2.7 | Tests the bond-fraction hypothesis |
| C6 | 3-point flexure (ISO 178) | Flat and on-edge | Flexural modulus and strength | **Validation only** | Predict with the card. Do not calibrate Z_t from it (TDS ratio 1.3 to 2.1 between flex and tensile) |
| C7 | Demonstrator | One generated part printed in 2 to 3 orientations | Stiffness, failure load and location | Tier T2 | **Pre-register predictions** (ranking, location, load band) before testing |

**If no universal testing machine is available (open question for the user):** dead-weight tests are feasible for
small sections.

- Z-tension on a 4 x 2 mm gauge at 23 MPa needs about 184 N (19 kg).
- 3-point flexure with b = 10, h = 4, L = 64 mm at 40 MPa needs about 67 N.
- Measure stiffness with a dial gauge or phone-camera DIC.
- Crosshead or dial displacement includes fixture compliance and underestimates E. Use DIC or extensometry for
  moduli.

**Stating confidence.**

| Tier | Basis | What may be claimed |
|---|---|---|
| T0 | TDS + assumptions (section 2.3) | Rankings and trends between candidates; intervals from the bracket corners. No absolute strength claims |
| T1 | Own C1 to C3 (+ C4, C5) | Stiffness within about +/-10 to 15% if C1/C2 CVs are small. Strength predictions with stated scatter. "Mean minus k*s" lower bounds: for n = 5, a normal 90/95 tolerance factor is about 3.4 (n = 10: about 2.36) [m]. These are not CMH-17 basis values |
| T2 | T1 + demonstrator agrees within pre-registered band | The model form is supported for that part family and load type only |

Size effect: brittle inter-layer failure has Weibull-type volume and area dependence. Coupon gauge sections are
smaller than part interfaces, which makes the coupons non-conservative. Note it; do not model it in v1.

---

## 7. Correctness invariants and tests (must exist before results are shown)

Frames and units

1. **I1** Every transform is named `R_TO_FROM`; det = +1; R R^T = I to 1e-12. Round trip D to P to D is the
   identity on mesh nodes.
2. **I2** Build-direction construction: `R_PD d = e_z` for random d, **including d = -e_z and d = +e_z**.
3. **I3** G-code to P to D mapping reproduces `plastic_shape`'s existing assertions: Z-preserving item transform,
   extruder offset restored, footer E-volume within 0.1%.
4. **I4** Units: the card schema stores units; I/O rejects unitless numbers. A mass check (density x printed volume
   versus Orca's filament-mass estimate) catches g/cm^3 versus g/mm^3 errors.
5. **I5** Load/BC rotation: resultant force and moment about a fixed point agree between D and the P voxelisation.

Tensors

6. **I6** C has major and minor symmetry; Mandel C_M is symmetric positive definite (min eigenvalue > 0). Engineering
   constants satisfy the TI/orthotropic positivity inequalities and reciprocity `nu_ij/E_i = nu_ji/E_j`.
7. **I7** Rotation: eigenvalues of C_M are invariant; Q C Q^T equals the einsum 4th-order rotation; the Bond-Voigt
   route agrees. Check on random R (`tensor_checks.py` has all three).
8. **I8** TI card invariant under Rz(any) and +/-45 laminate invariant under Rz(90 deg), but not under Rz(45 deg).
9. **I9** Solver-order permutation: C_gpu[3,3] = G12, [4,4] = G23, [5,5] = G13. A pure-shear test in each plane
   returns the correct G.
10. **I10** Element: Ke symmetric PSD with exactly 6 zero eigenvalues, for random anisotropic C. GPU operator equals
    an independently assembled scikit-fem anisotropic operator (custom BilinearForm) on random displacements. This
    extends `validate_gpu_hex.py`.
11. **I11** Anisotropic patch test: affine u gives constant stress = C eps at all Gauss points, to round-off.

Failure

12. **I12** F(lambda sigma) = lambda F(sigma). Uniaxial stress along a bead gives F_P = sigma/X_t. A part loaded in
    tension along D-x gives F_L = sigma/Z_t when printed with x vertical and F_L = 0 when printed flat. Mandel-stored
    shear is divided by sqrt2 before evaluation (pure-shear unit test).

TO building blocks

13. **I13** AM filter output is self-supported cell by cell. A 45 deg ramp passes; a horizontal cantilever is
    removed. **The accepted angle is measured versus azimuth** (grid anisotropy), and so are internal ceilings of
    hollow bodies.
14. **I14** Every sensitivity is checked by central finite differences on a small grid with all blocks active
    (filter, projection, coating erosions, AM filter, p-norm, relaxation), and with a **Taylor test** (error O(h^2)).
    Each block is also tested separately. Use a relative error < 1e-5 in float64.
15. **I15** Filter: weights normalised; interior volume preserved; padding behaviour at domain edges, symmetry
    planes and bed plane as specified.
16. **I16** Coating: smooth erosion of a flat slab and of a 45 deg slab gives surface-normal shell thickness
    t(alpha) +/- 1 cell (section 4.4). Comparison against Orca's actual walls and skins uses the mapper's role
    fractions.
17. **I17** Min length: measured minimum solid and void widths of the thresholded design (distance transform) are
    >= 2w in XY and >= n_t*h in Z, or the run is flagged.

Discretisation and verification

18. **I18** Mesh dependence: re-run with fixed physical filter radius at h and h/2 on a reduced domain. Report the
    change in topology (volume-fraction difference) and in compliance. Raw stress peaks at re-entrant corners are
    labelled non-convergent, never filtered away (spool-rack practice).
19. **I19** TO model versus zero-ersatz re-analysis: report the ratio of compliance and of the inter-layer index. A
    gap above an agreed threshold blocks the candidate.
20. **I20** Mapper fixtures: synthetic G-code with (a) a straight raster at a known angle gives theta exact; (b)
    concentric circular walls give a tangential theta; (c) +/-45 alternation gives alternating theta per layer;
    (d) a known overhang staircase gives a known b. Real coupon G-code gives the expected role fractions in the gauge.

---

## 8. Literature (grouped)

| Topic | Reference | Use here |
|---|---|---|
| FDM anisotropy | Ahn et al. 2002 RPJ 8(4) [m]; Rodriguez et al. 2003 RPJ 9(4) [m]; [Casavola 2016](https://www.sciencedirect.com/science/article/abs/pii/S0264127515307516) [v]; [Zou 2016](https://www.semanticscholar.org/paper/Isotropic-and-anisotropic-elasticity-and-yielding-Zou-Xia/744752e7b5f209c8b31391568114c9a60abf7fb3) [v]; [Kiendl & Gao 2020](https://www.researchgate.net/publication/336817681_Controlling_toughness_and_strength_of_FDM_3D-printed_PLA_components_through_the_raster_layup) [v]; [PLA orthotropy 2024](https://www.sciencedirect.com/science/article/pii/S026382312400243X) [v] | Model form and symmetry class |
| Weld physics | Seppala et al. 2017 Soft Matter 13:6761 [m]; Coogan & Kazmer 2017 RPJ 23(2) [m] | Why the cards are process-locked |
| Vendor data | Bambu TDS: [PETG HF](https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf), [PETG Basic](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf), [ASA](https://solidprint3d.ie/wp-content/uploads/2024/03/Bambu-Lab-ASA-Filament-Technical-Data-Sheet.pdf) [v] | T0 cards and ratios |
| Laminate homogenisation | [Sun & Li 1988](https://journals.sagepub.com/doi/abs/10.1177/002199838802200703) [v] | Section 2.6 |
| Anisotropic strength TO for AM | [Mirzendehdel et al. 2018](https://par.nsf.gov/servlets/purl/10057716) [v]; [Kundu & Zhang 2023](https://doi.org/10.1016/j.addma.2023.103730) [v]; [Zou & Xia 2023](https://academic.oup.com/jcde/article/10/2/892/7110403) [v]; [Dapogny et al. 2019, CMAME 344:626](https://www.researchgate.net/publication/328607322_Shape_and_topology_optimization_considering_anisotropic_features_induced_by_additive_manufacturing_processes) [v]; [FDM process-structure TO 2024](https://link.springer.com/article/10.1007/s00170-024-14929-2) [v] | Failure-index TO, phases, orientation |
| Bead-aware TO | [Jewett & Carstensen 2023](https://www.sciencedirect.com/science/article/abs/pii/S0045794923001888) [v]; [Kim-Tackowiak & Carstensen 2025](https://www.sciencedirect.com/science/article/pii/S0264127525011207) [v] | Weak bond, discrete bead size |
| Stress TO | [Le et al. 2010](https://link.springer.com/article/10.1007/s00158-009-0440-y) [v]; [Verbart et al. 2017](https://link.springer.com/article/10.1007/s00158-016-1524-0) [v]; [Senhora et al. 2020](https://link.springer.com/article/10.1007/s00158-020-02573-9) [v]; Bruggi 2008 [m]; Duysinx & Bendsoe 1998 [m]; Holmberg et al. 2013 [m] | Section 3.3 |
| Regularisation | Bruns & Tortorelli 2001 [m]; Bourdin 2001 [m]; Guest et al. 2004 [m]; Wang, Lazarov & Sigmund 2011 [m]; Lazarov & Sigmund 2011 [m]; [Clausen & Andreassen 2017](https://link.springer.com/article/10.1007/s00158-017-1709-1) [v]; [Fernandez et al. 2021](https://link.springer.com/article/10.1007/s00158-021-02998-w) [v] | Sections 4.2 and 4.5 |
| Overhang | [Langelaar 2017](https://doi.org/10.1007/s00158-016-1522-2) [v]; Langelaar 2016 Addit. Manuf. 12:60 [m]; [Gaynor & Guest 2016](https://link.springer.com/article/10.1007/s00158-016-1551-x) [v]; Pellens et al. 2019 SMO 59:2005 [v]; [Kumar & Fernandez 2022](https://arxiv.org/abs/2204.07333) [v]; van de Ven et al. 2018 [m] / [2020](https://www.researchgate.net/publication/342391766_Overhang_control_based_on_front_propagation_in_3D_topology_optimization_for_additive_manufacturing) [v]; Qian 2017 IJNME [m] | Section 4.6 |
| Orientation | [Langelaar 2018](https://doi.org/10.1007/s00158-017-1877-z) [v]; [Olsen & Kim 2020](https://link.springer.com/article/10.1007/s00158-020-02590-8) [v]; Wang & Qian 2020 [m]; Ulu et al. 2015 [v] | Section 4.7 |
| Coating / shell-infill | [Clausen et al. 2015](https://doi.org/10.1016/j.cma.2015.02.011) [v]; [Wu, Clausen & Sigmund 2017](https://backend.orbit.dtu.dk/ws/files/134847727/MARAC_1_s2.0_S0045782517305984_main.pdf) [v]; Luo, Li & Liu 2019 CMAME 355:94 [v]; Clausen et al. 2016 Engineering [m]; Wu et al. 2018 TVCG [m] | Section 4.4 |
| Infill homogenisation | [Gyroid infill 2022](https://www.mdpi.com/2076-3417/12/4/2180) [v]; Groen & Sigmund 2018 [m] | Section 4.8 |
| Multi-axis (out of scope on P1S) | [Fang et al. 2020 Reinforced FDM](https://doi.org/10.1145/3414685.3417834) [v] | Context |
| Interpolation / optimiser | Bendsoe & Sigmund 1999 [m]; Stolpe & Svanberg 2001 [m]; Svanberg 1987 [m]; Andreassen et al. 2011 SMO 43:1 [m]; Aage et al. 2017 Nature 550:84 [m] | Section 4.3 |

---

## 9. Open questions (for the user and for round 2)

1. **Test equipment:** is there access to a universal testing machine, or do we plan dead-weight and DIC tests?
   (This changes C1 to C5 feasibility and section 6 sample sizes.)
2. **Which filament grades exactly?** Bambu PETG HF and PETG Basic differ by 1.5x in E_XY. Polymaker data is also in
   the repo. One card per grade per profile.
3. **Service temperature and duration:** PETG near 30 to 40 C with sustained load is creep-governed. Is creep in
   scope for v1 (spool-rack e8/e9 says it matters)?
4. **Is non-zero sparse infill ever allowed?** If yes, add section 4.8 (RVE homogenisation). If no, the massing model
   is shell + helper only.
5. **Acceptable TO-vs-reanalysis gap** (I19) and **pre-registered demonstrator bands** (C7): who sets them?
6. **Orientation sweep budget:** N directions, K full TOs and K' slices. Legolas and Gandalf own the cost and
   orchestration; the mechanics only requires the prescreen to be conservative in ranking (test it on the
   demonstrator).
7. For Frodo: should the printability catalog adopt the angle convention alpha_s (from horizontal) and the 2w / n_t*h
   minimum-length pair stated here, so mechanics and catalog share definitions?

## 10. Artifacts

- `D:\Code\Models\fdm-gen\scratch\sauron\tensor_checks.py`: Mandel Q, Bond-Voigt, bug magnitudes, TI invariance,
  directional modulus, dC/dtheta finite-difference check, gpu_hex permutation, quadratic inter-layer example.
- `D:\Code\Models\fdm-gen\scratch\sauron\laminate_checks.py`: exact layered homogenisation versus Voigt/Reuss, the
  shell-thickness relation t(alpha), wall overlap f(beta), stadium-bead numbers.
