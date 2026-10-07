# Sauron on Gandalf (architecture and roadmap): cross-review, round 2

Reviewer angle: frames, units, tensor conventions, mechanics, the numbers, and data flow between stages.
Checked against the repos (read-only), the Bambu TDS, and my numpy scratch (`scratch\sauron\*.py`).

## 1. Verdict

The architecture is sound. Two FEM roles, slicer-generated toolpaths, print-frame re-voxelisation, rules as data
with check levels, and hash-pinned provenance are the right skeleton, and I would keep almost all of it.

The weaknesses sit at the mechanics/data boundary:
- The `problem.yaml` load translation contradicts the existing contact-derived seat loads.
- The material card has no Poisson convention and no transversely isotropic design class.
- The design grid (0.6 mm) cannot represent the massing the emulator is supposed to model.
- One overhang rule mixes two angle conventions.
- The P1-B acceptance test uses an anisotropy ratio outside the measured range.

## 2. Findings

1. **[critical] Section 3.1 `problem.yaml`: the seat loads are wrong.** The sketch puts `[0,-58.86,0]` on each seat,
   a purely vertical equal split of 117.72 N. Spool-rack's production split (`analysis/rev-g2/solve_plastic.py`
   `interface_loads`, a spool resting on two rods at different heights) gives a **rear seat of 75.12 N down, a front
   seat of 42.60 N down, and ±31.29 N horizontal**. I recomputed this from the function with total = 117.72 N. The
   equal split understates the rear seat by 22%. It also drops the horizontal pair, which carries a moment into the
   wall contact. For the "translate the contract" P0 deliverable this would silently change every answer.
   **Change:** loads come from a named contact model (`split: per_contact_model`, as Frodo writes it), or from
   `interface_loads` ported with a parity test. Write each resultant as a frame-tagged vector, and assert the total
   force and the moment about a datum.

2. **[warning] Section 3.3 material card: three problems.**
   - (a) No convention for `nu: [nu12, nu13, nu23]`. State `nu_ij = -eps_j/eps_i` under `sigma_i`. Without that,
     half the literature's values enter transposed. Reciprocity requires `nu_ij/E_i = nu_ji/E_j`.
   - (b) No positive-definiteness check at load. For transversely isotropic cards the condition is
     `1 - nu_p - 2 nu_pz^2 E_z/E_p > 0`; for orthotropic cards, check that the eigenvalues of the 6x6 C in Mandel form
     are positive.
   - (c) The only classes are `bead` and `sparse_infill`. The design stage needs a **homogenised transversely
     isotropic "printed solid" class about print Z** (my D2, also Legolas section 5). A bead-frame card needs a bead
     direction, and the design stage does not have one.

   **Change:** add `convention:` and `symmetry: {transversely_isotropic_z | orthotropic_bead}` fields, a load-time PD
   check, and a `bond_scaling` entry (inter-layer constants scaled by the mapped bond fraction; Sauron section 2.7).

3. **[warning] Section 3.3 and P1 scope: "orthotropic with one bead class" at design time, and S3 "wall tangents
   quantised into angle bins".**
   - Grid alignment makes only the **layer normal** axis-aligned. Wall bead tangents follow the contour, so they are
     not axis-aligned. Section 4 S3's claim that grid alignment makes the classes axis-aligned is true for the
     transversely isotropic model only.
   - With T0 data there is no measured E1/E2. Bambu gives XY and Z only.
   - **Proposal:** transversely isotropic in S3. Per-element bead angle only in S6, read from the G-code.
   - The bin count Gandalf asked for: 5 deg bins (36 over 180 deg) change C by at most **0.63%** (spectral norm,
     half-bin 2.5 deg) for an assumed E1/E2 = 1.33 card, and 0.18% for a TDS-like 1.10 card (computed this round).
     So **36 bins suffice for stiffness**. Strength indices should still use the exact per-element angle, which is
     cheap and pointwise.

4. **[warning] Section 3.4 `OVH-01`: two angle conventions in one rule.** The statement reads "flatter than theta
   from the build plane", but the parameter is `theta_deg_from_vertical: 45`. These agree only at 45 deg. The
   evidence line says "support at 45 deg from vertical, none at 35". I re-derived the wedge geometry in
   `overhang-threshold-test/build.py`: the underside slope from horizontal equals the `ang` in the file name. So
   wedge-55 is 35 deg from vertical, and Gandalf's reading is correct. However, the `build.py:10` comment calls `ang`
   "angle from vertical", which is the trap Frodo calls T1. Also, this test establishes Orca's
   `support_threshold_angle = 45` behaviour (tier S), **not** P1S print capability.
   **Change:** adopt Frodo's D3 convention (slope from horizontal), rename the parameter, and tag the evidence as
   slicer-behaviour only.

5. **[warning] Sections 4 S2/S3 and 7 R3: a 0.6 mm design grid cannot express the massing the emulator models.**
   - Two walls at w = 0.42 is about 0.84 mm (about 0.81 mm using Orca's flow spacing `w - h(1 - pi/4)`), i.e. 1.4
     cells at 0.6 mm.
   - The 2w minimum length scale is also 1.4 cells, below any filter radius that can enforce it.
   - So at 0.6 mm the "per-layer 2D erosion gives wall shells" step is sub-cell noise.
   - **Change:** at grids of 0.4 mm and coarser, treat all body material as printed solid (body = helper
     everywhere), which is faithful for a 0%-infill part with a solid body. Run the directional coating only on
     0.2 mm grids, or locally refined ones. State this resolution rule in S3. (Legolas section 4 reaches the same
     conclusion: "shells are a post-processed concept" at 0.8 mm.)

6. **[warning] Section 4 S2: "XY spacing is a fraction or multiple of w" silently sets the overhang angle.** The
   Langelaar 1-cell support stencil admits overhang `atan(dx/dz)` from vertical:
   - dx = w = 0.42 with dz = 0.2 gives **64.5 deg**. That is exactly where nominal inter-layer overlap reaches zero
     (Sauron section 2.7).
   - dx = 0.21 gives 46.4 deg.

   **Change:** use cubic cells (dx = dz = k*h), or derive the stencil from the declared alpha_min. Add the
   azimuthal stencil-anisotropy test (Sauron I13): a 3x3 stencil admits 54.7 deg along the diagonals.

7. **[warning] Section 6 P1-B: an anisotropy ratio outside the measured data.** The test requires flat-on-side to
   rank first for `E3/E1 <= 0.7`.
   - Bambu TDS give E_Z/E_XY = **0.85 (PETG HF), 0.92 (PETG Basic), 0.87 (ASA)** (Sauron section 2.2).
   - At those ratios directional stiffness varies by only about 15%. Compliance differences between orientations can
     be comparable to re-voxelisation noise.
   - **Change:** keep the 0.7 (or 0.5) run as a plumbing test, and add a run at 0.85. Require only a **monotone trend**
     in the ratio, not a rank flip at realistic values.
   - Add a control isolating **voxelisation noise**: isotropic material, no AM filter, all three orientations. The
     spread of that control is the noise floor any orientation claim must exceed.
   - Also state that, for these materials, orientation is decided mainly by **inter-layer strength and printability**,
     not compliance. That is why the inter-layer failure index must be in the P1 or P2 scope as a constraint or ranking
     metric (Sauron D7), not deferred entirely to P3.

8. **[warning] Sections 3.1/6: the stiffness basis is not stated.** Spool-rack's 4 mm movement gate uses the
   **E = 1,000 MPa "effective planning model"** (G2-BRIEF line 66; "not a demonstrated lifetime law"). That is a
   sustained-load, creep-informed value, not the short-term TDS E (1,810-2,780 MPa PETG). The two bases give
   displacements differing by up to 2.8x.
   - The P1-E honesty table and every movement metric must state which modulus basis applies.
   - The material card needs separate `short_term` and `sustained_effective` entries.
   - Anisotropy ratios measured short-term are an **assumption** when applied to the sustained modulus.

   (My own report misses this distinction; I will add it in round 3.)

9. **[warning] Section 3.2 `process.yaml`: `modifiers: allowed_densities [0.15, 0.4, 1.0], pattern: gyroid`.**
   - This conflicts with the house rule (0% base infill, sparse infill zero credit, 100% helpers).
   - `plastic_shape.py:127` asserts that no sparse infill is present.
   - Crediting partial infill needs a homogenised infill card (periodic RVE of the actual Orca pattern; Sauron
     section 4.8), and no data for one exists.

   **Change:** default `allowed_densities: [1.0]`. Partial densities stay behind an explicit opt-in with
   `status: ASSUMED` and zero-credit verification as a bound.

10. **[warning] Section 1.2: "actual-slice material reconstruction validated to 0.005 mm" overstates the evidence.**
    `analysis/rev-g2/validation/matrix-shape-validation.md:13` reports cache-versus-oracle occupancy agreement
    **outside a 0.005 mm boundary band**. That is a numerical consistency check of the parser and cache, not
    agreement with printed geometry. The bead neck, the stadium cross-section and squish are not represented
    (Sauron section 2.7).
    **Change:** reword it as "the occupancy cache agrees with the exact oracle outside a 0.005 mm band".

11. **[warning] Sections 4 S5/S6: missing data-flow step for slicer-side geometric compensation.**
    - The ASA-calibrated profile in `5680-dock/desk-dock/D9-P5/profiles/filament-polylite-asa-calibrated.json` sets
      `filament_shrink = 99.46%`. Orca then scales XY by about 1.0054 when slicing.
    - `plastic_shape.read_paths` inverts only the 3MF item transform and asserts that it is orthonormal. The shrink
      scaling is applied inside Orca and is invisible to that check.
    - Mapped G-code material would therefore sit up to about **0.5 mm** too large over a 100 mm half-length. That is
      far beyond the spool-rack audit's 0.03 mm tolerance, and it corrupts keep-in and contact-gap checks.
    - **Change:** the canonical parser reads the effective `filament_shrink` (and `xy_hole_compensation`,
      `elefant_foot_compensation`) from the effective settings and either undoes them or declares the truth geometry
      as-printed-hot.
    - Add a fixture: the same part sliced at 100% and 99.46% must map to the same design-frame occupancy after
      correction. The scaling centre must be determined by that fixture, not assumed.

12. **[note] Section 3: the frame list needs two more frames.** Gandalf names part, installed, print and bed. Add:
    - **gcode** = bed minus the P1S extruder offset `(0,2)`, the frame `plastic_shape` actually inverts.
    - **bead** = per-element material frame `[t, e_z x t, e_z]`.

    Also record that Orca's arrange step may **spin** the object about Z. The spin must be read back from the sliced
    3MF item transform (as `plastic_shape` does), never assumed from `R_part_to_print`.

    Proposed merged naming for round 3: `design(part) -> installed -> print -> bed -> gcode`, plus `bead` per element.
    Name every matrix `R_<to>_<from>`.

13. **[note] P0-C: "bitwise-identical" for the anisotropic Ke path with isotropic inputs.** This is achievable only
    when the identity rotation takes the same code path. Through a rotated C (Q C Q^T) the right gate is about 1e-12
    relative. Also add the canonical-to-`gpu_hex` Voigt permutation test: `gpu_hex` orders shear (xy, yz, xz), not
    (23, 13, 12). See Sauron section 1 / I9.

14. **[note] P1-A tolerance (requested).** Split it into two gates.
    - (i) **Solver parity:** evaluate the *reference code's final density field* with our solver; compliance within
      1e-6 relative. This isolates solver bugs.
    - (ii) **Optimiser parity:** same grid, penalisation and continuation, filter radius, beta schedule, move limit and
      volume fraction; final compliance within 2% and volume within 0.1%.

    Topology optimisation is nonconvex and a tighter optimiser gate would fail for legitimate reasons. Neither gate
    involves anisotropy; add a third: (iii) rotation-covariance. Rotate the loads, the domain and the transversely
    isotropic axis together by a grid-symmetry rotation; compliance must be unchanged to 1e-10.

15. **[note] P2-A band (requested).** Proposal: at 0.2 mm, per material class, the symmetric-difference volume
    between emulator and real Orca credited material is at most 5% of class volume. In addition, mean
    surface-normal shell thickness must be within ±1 cell of the Orca walls/skins at 0, 30, 50, 70 and 90 deg
    inclination. Set the final band after the first measurement and publish it with its basis.

16. **[note] Section 4 S1: hull poses versus sweep.** Hull poses are right for analysing an existing part (flat bed
    contact). In topology optimisation from an envelope, the optimiser can create its own bed footing, so the
    candidate set may be any direction that keeps the interfaces printable. I suggest S1 = (hull ∪ axis ∪ user) for
    fixed-geometry analysis, and the inter-layer traction prescreen over a Fibonacci sphere (Sauron section 4.7) to
    choose candidates for optimisation. Up and down differ for overhang, so use the full sphere, not a hemisphere.

17. **[note] Q5 (truth accuracy at 0.2 mm), mechanics answer.**
    - **Displacement:** converges up to the known omission bias. Report it with the omitted-volume bound, as
      spool-rack does.
    - **Inter-layer failure index:** meaningful at 0.2 mm only if the card was calibrated on coupons analysed with the
      same nominal-footprint idealisation.
    - **Raw peaks at bead scale:** do not converge and must stay labelled.
    - Sub-bead resolution is unnecessary for consistency with a footprint-calibrated card. It would be necessary only
      for bead-scale fracture claims, which are out of scope.

## 3. What Gandalf got right (the merged plan must keep these)

- Two FEM roles with separate entry points and invariants. The truth solver refuses `Emin > 0` (R6). This is exactly
  how to keep the house rule while still running topology optimisation.
- Re-voxelise in the print frame per orientation, with layers on grid planes. This agrees with my D4 and conflicts
  with Legolas D3; see my Legolas review for the reconciliation.
- Port with parity tests, never import; hash-pinned references; one canonical G-code parser with arc and offset
  fixtures (P0-A/B). The finding that `path_reader.py` already handles G2/G3 is valuable.
- Every metric carries `fidelity` and `scope`. Failures are preserved. Material cards carry `status`. A sensitivity
  sweep over anisotropy ratios is required.
- The single `Rotation` object that derives both the build vector and the pose fixes a real bug class
  (`PRINT_Z` vs `pose()`).
- The bracket is a known-answer test, honestly labelled weak for orientation, with a harder second part in P2.
- The P0-D modifier-capability spike. Whether Orca modifiers can override `wall_loops` and skins determines whether
  the massing outputs I proposed (body + helper + wall/skin counts) are expressible per region.
