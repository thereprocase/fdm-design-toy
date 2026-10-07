# Sauron on Frodo (workflow and printability catalog): cross-review, round 2

Reviewer angle: frames, units, tensor conventions, mechanics, the numbers, and data flow between stages.
Checked against the repos (read-only) and my numpy scratch (`scratch\sauron\*.py`).

## 1. Verdict

The catalog structure is the best artefact of round 1. It has:
- Rules as data, with check levels V/M/T/P.
- Evidence tiers.
- Calibration bindings that go STALE on hash change.
- One angle convention.
- A trap list drawn from real repo incidents.

The formulas I could check are right: SHELL-001 matches my independent derivation, and OVH-002 is algebraically
consistent with my overlap model. The weak points are on the mechanics side:
- STR-001's criterion and its placeholder value.
- A missing data-flow consequence of `filament_shrink`.
- Frame naming that stops short of the G-code and bead frames.
- A few numbers that should use Orca's flow spacing.

## 2. Findings

1. **[warning] Section 3.1 STR-001 and section 4.2 `z_fraction`: the criterion is under-specified and the
   placeholder ignores available data.**
   - "σ_zz,+ and τ_z ≤ z_fraction × in-plane allowable / SF" has three problems:
     - (a) It uses the *tensile* fraction for shear. Inter-layer shear strength S_il is a separate, unmeasured
       constant.
     - (b) It has no interaction between normal and shear. At 45 deg to the layers, predicted strength spreads by 28%
       across plausible S_il (Sauron section 3.2 table).
     - (c) "In-plane allowable" is undefined: TDS tensile, flexural, annealed or as-printed?
   - Tier V data exist. Bambu TDS tensile Z/XY = **0.68 (PETG HF), 0.69 (PETG Basic), 0.84 (ASA)**; Polymaker PETG
     0.95, PolyLite ASA 0.73 (spool-rack `material-reference-data.json`). Two Bambu sheets used annealed specimens.
   - **Change:**
     - Define STR-001 as the inter-layer mode `F_L = sqrt((<sigma_n>+/Z_t)^2 + (tau/S_il)^2) <= 1/SF` on the layer
       plane (Sauron section 3.2).
     - Bind `Z_t` (tier V, the TDS value of the actual grade, flagged annealed) and `S_il` (tier H, bracket
       0.5-1.0 x Z_t) separately.
     - Report results at the bracket corners.
     - Keep z_fraction = 0.5 only as an explicitly conservative tier-H fallback, not as the default.
   - This answers Frodo Q1(b): a quadratic two-term interface criterion, not a bare max-stress check on sigma_zz, and
     not Tsai-Wu (whose F12 we cannot measure).

2. **[warning] Sections 3.2 HOLE-002 and 4.2 (`filament_shrink: 0.9946`): the downstream mechanics consequence is
   missing.** Frodo correctly finds that the ASA-calibrated profile scales XY by about 1/0.9946 (trap T3) and treats
   it as a fit issue. It is also a **truth-mapping** issue:
   - `plastic_shape.read_paths` inverts only the 3MF item transform (asserted orthonormal). Orca's shrink scaling is
     invisible to that assertion.
   - G-code material mapped back to the design frame is therefore about 0.54% too large: about 0.5 mm over a 100 mm
     half-length.
   - That breaks keep-in checks, the zero-gap wall contact and the 0.03 mm audit tolerance in
     `audit_g_slicer_mapping.py`.

   **Change:**
   - Extend the `compensation:` block so the T-level mapper consumes it: undo the scaling, or declare the truth
     geometry as-printed-hot.
   - Add a golden test: the same part sliced at 100% and 99.46% must map to identical design-frame occupancy.
   - Add `filament_shrink` (and `xy_hole_compensation`, `elefant_foot_compensation`) to PROC-001's key list for every
     T-level geometric rule, not only for fit rules.

3. **[warning] Section 2.1 frames: two frames are missing.** Frodo has `design`, `print` and `plate`. The data flow
   needs two more:
   - **`gcode`** = plate minus the P1S `extruder_offset (0,2)`. That is the frame `plastic_shape` actually inverts:
     `model = (gcode + offset - xf[3]) @ xf[:3].T`. Frodo writes that "the plate frame must undo the offset", which
     conflates the two.
   - **`bead`** = per-element material frame `[t, e_z x t, e_z]` for the inter-layer and in-layer criteria.

   Also note that Orca's arrange may **spin** the part about Z. The plate transform must be read back from the sliced
   3MF, not assumed from `PRINT_Z`. Gandalf uses part/installed/print/bed; I use D/P/M/G.

   **Change:** adopt one merged list in round 3: `design -> installed -> print -> plate(bed) -> gcode`, plus `bead`,
   with matrices named `R_<to>_<from>`.

4. **[warning] SHELL-001 (section 3.1 and the MOD-001/SHELL-001 card): the formula is right, but the inputs and the
   threshold need fixing.**
   - Frodo's `t_n(phi) = max(n_w w cos phi, n_t h sin phi)` with phi = normal elevation equals my
     `t(alpha) = max(n_w w sin alpha, n_t h cos alpha)` with alpha = 90 - phi. The minimum
     `n_w w n_t h / sqrt((n_w w)^2 + (n_t h)^2)` gives 0.67 mm at phi = 42 deg for 2 x 0.45 and 5 x 0.2. I confirm
     that arithmetic; mine is 0.64 mm at alpha = 50 deg for 2 x 0.42.
   - Problem (a): `n_w * w` overstates the wall shell.
     - Orca places walls at **flow spacing** `w - h(1 - pi/4)`: 0.377 mm for 0.42 and 0.407 mm for 0.45.
     - For outer 0.42 + inner 0.45, the shell is about 0.21 + (0.377 + 0.407)/2 + 0.2035 ≈ **0.81 mm**. Frodo's
       2 x 0.45 = 0.90 mm is 11% high. (My report has the same approximation; I will correct it in round 3.)
   - Problem (b): `t_min` is not stated. If t_min = 2w (WALL-001), the house's minimum configuration (2 walls,
     5 x 0.2 skins) **fails SHELL-001 at the M level on every 30-60 deg surface**.
   - **Change:** state t_min and its basis. Make SHELL-001 M-level advisory and T-level binding, measured on actual
     roads after `ensure_vertical_shell_thickness`, which Orca adds to fix exactly this.

5. **[warning] OVH-001/OVH-002 and Frodo Q1(a): grid realisation of `k_step`.**
   - The algebra checks out: `alpha_min = atan(h/(k w))` gives 43.6/29.7/53.1 deg (k = 0.5) and 50.0 deg (k = 0.4).
   - **Mechanical meaning:** k_step is my `1 - f`, where f is the nominal inter-layer overlap of a leaning wall
     (Sauron section 2.7). So k = 0.5 accepts only **50% bonded width** on overhang walls. That is a printability rule
     *and* an inter-layer strength knock-down. OVH-002 should feed the bond fraction into STR-001.
   - On grids:
     - The Langelaar 1-cell stencil on cubic 0.2 mm cells gives a 45 deg slope (k = 0.476 at w = 0.42), exactly
       only **along grid axes**. A 3x3 stencil admits 54.7 deg along diagonals; a 5-point cross admits about 35 deg.
       Either way, "maps exactly onto one-cell steps" holds only axis-aligned.
     - Other angles need fractional-weight (interpolated) support stencils or front propagation. **Do not change h**:
       h is bound to the material card and the calibration.
   - **Change:** add an azimuthal acceptance test (rotate an inverted cone; record the accepted angle versus
     azimuth), and require the M and T checks to stay authoritative over the V filter.

6. **[note] T1 trap description (section 5.3): the comment is wrong, not the file names.** I re-derived the gusset in
   `overhang-threshold-test/build.py`:
   - The underside runs from (30, 25) to (15, 25 - 15 tan(ang)), so its slope from horizontal **equals `ang`**.
     File name `wedge-30deg` means 30 deg from horizontal.
   - The source comment on line 10 says "angle from vertical", and that is the error. The file names are just
     unlabelled.

   Frodo's table row ("30/39/45 deg from horizontal got support; 55 deg did not") is correct. Only the T1 narrative
   should be reworded. Also note what the wedge test measures: Orca's `support_threshold_angle = 45` decision
   (process.json line 21), tier S, as Frodo says in T4.

7. **[note] Section 4.3 G2 problem: the load has no direction or frame.** `force_N: 117.72` with
   `split: per_contact_model` is the right idea, and better than Gandalf's equal 58.86/58.86 split. For reference, the
   existing model gives rear 75.12 N, front 42.60 N, ±31.29 N horizontal (`solve_plastic.interface_loads`). But the
   load still needs:
   - a direction vector in a named frame (gravity is -Y in `installed`);
   - a hash-pinned reference to the contact model that produces the split.

   Units are fine. `one-spool-delta` with 1.25 kg is consistent with G2-BRIEF: 12.26 N, or 0.104 x 117.72 N.

8. **[note] Section 5.2 ranked-orientation table, column "Max interlayer tension / allowable".** Change it to the
   inter-layer failure index F_L, which includes shear, with the material-card tier next to it. The value is
   orientation-sensitive and should be computed by the analytic traction prescreen (Sauron section 4.7). Frodo
   already cites the right prior art for this: Umetani & Schmidt 2013.

9. **[note] PROC-001: extend the key list to the material card's process binding.** Every key that changes the
   mechanical card must be compared with the effective config, or results go STALE:
   - line widths, layer height, speeds, temperatures, fan, chamber;
   - `wall_generator`;
   - `ensure_vertical_shell_thickness`;
   - solid infill direction and pattern;
   - arc fitting (the spool-rack parser ignores G2/G3).

   This is Sauron D10 expressed as Frodo's mechanism, and I prefer his mechanism.

10. **[note] Q4, "which rules inside the optimiser on day one".** I agree with OVH-001 (AM filter), WALL-001/GAP-001
    (robust length scale) and frozen interfaces and keep-outs. Two changes:
    - STR-001 should be an **aggregated constraint** (p-norm with qp-relaxation), not a penalty. A penalty weight has
      no units and silently trades strength for volume.
    - VOID-001 belongs inside too. The AM filter must act on the **printed-material field (shells + helpers)**, not
      the body envelope. With 0% infill, every hollow region has internal ceilings that the envelope check never
      sees (Sauron D6).

11. **[note] SURF-001 `c = h cos(alpha_n)`.** This is consistent with alpha = slope from horizontal (vertical wall
    c = 0; near-flat c → h). Write it with the D3 symbol alpha, not `alpha_n`, to avoid a fourth angle name.
    Horizontal faces lying exactly on a layer boundary have c = 0, not h. The formula needs that exception.

## 3. What Frodo got right (keep in the merged plan)

- **D3, one angle convention (slope from horizontal).** Adopt it in all reports, mine included. I will restate my
  overlap formula as `f = 1 - h/(w tan alpha)`. The finding that the repos mix conventions is real and caused a
  mislabelled evidence file.
- Check levels V/M/T/P, with "highest level reached" reported instead of PASS. The T level is authoritative over the
  V filter. This is the right epistemic stance for an optimiser that can exploit proxies (T9).
- Evidence tiers with tier S (slicer behaviour) separated from tier U (printed). The wedge test is S, not U.
- Calibration files bound to profile hashes that go STALE. This is the same idea as my process-locked material cards
  and should be one mechanism for both rules and material.
- The PROC-001 effective-settings check, generalised from `gpu_demo_slice.py`.
- Rules in units of w and h (the Fillaprint algebra). The Arachne band-edge rule WALL-002 checks out: 1.2 mm =
  2.86w sits on the 2/3-bead edge, and the classic versus Arachne generator split is a real trap.
- VOID-001 (closed voids allowed, roofs self-supporting) and BRG-002 (bridges get zero credit) as data.
- The first calibration plate proposal. Merge it with my mechanical coupons (C1-C5) so one print campaign covers
  geometry *and* the material card. The overhang ladder doubles as the C5 bond-fraction coupon if printed as
  tension specimens.
