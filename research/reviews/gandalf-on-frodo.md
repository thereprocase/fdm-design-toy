# Gandalf on Frodo (round 2 cross-review)

Reviewed: `D:\Code\Models\fdm-gen\research\frodo.md` (612 lines). Spot-checked in the repos:
`overhang-threshold-test/build.py` and `toolpath-verification.json`; `selfsupport()` in `build_d9.py`;
`verify_plates.py`; the D9 profiles (`filament_shrink`, `wall_generator`); `package_part.py`; `gpu_demo_slice.py`;
and `novel-cad-skill/scripts/check_printability.py`. Angle: architecture, integration, roadmap feasibility.

## 1. Verdict

This is the most directly useful report for the *product*. It answers a collaborator's "no one has documented a programmatic set
of constraints" with a schema, a calibration binding, evidence tiers and a trap list built from real incidents in the
repos. The claims I checked hold up. The main architectural issues are three:
- a duplicated source of truth between the catalogue and the material card (STR-001's `z_fraction`);
- the integration route for `emit_problem()` into frozen repos;
- reuse of B-rep repair operators on optimiser output, which they were not built for.

## 2. Findings

1. **[warning] STR-001 `z_fraction` duplicates the material card.** The catalogue puts an inter-layer allowable
   fraction (0.5, tier H) in a printability rule (§3.1, §3.2 STR, §4.2 calibration file). Sauron's card already holds
   Z_t, S_il and X_t with tiers (sauron.md §2.3, §3.2). The TDS ratios there (0.68-0.84) disagree with 0.5. Two places
   would then define the same physical quantity, and they would drift.
   *Requested change:* STR-001 should **reference** the active material card's failure criterion (`criterion:
   material_card`) and keep only the safety factor and the check levels. The calibration file should not carry
   strength values. Frodo §3.3 already says the material model belongs elsewhere; make STR-001 consistent with that.

2. **[warning] OVH-001 design target 50° vs the optimiser's 45° filter.** Frodo sets α ≥ 50° (from horizontal) as the
   design value, with good evidence: I confirmed `wedge-45deg` received 2,421 support segments and `wedge-55deg` none.
   Frodo also says (§3.2) that "on a 0.2 mm grid the 45° stencil maps exactly onto one-cell steps". Sauron shows a
   one-cell stencil on cubic voxels gives 45°, and a 2-cell stencil gives 63.4° (sauron.md §4.6). Neither gives 50°.
   *Requested change:* in the OVH-001 card, record that the **V-level check is 45° (grid-limited) while the M/T levels
   enforce 50°**, or specify the anisotropic voxel (dx/dz ≈ 0.84) that would give 50°. Both reports must state the
   same convention: "slope from horizontal" (Frodo D3), which Sauron's α_s also uses.

3. **[warning] D5 "reuse `selfsupport()` / `bore_td()` / `dress()`" needs a scope boundary.** These are CadQuery B-rep
   operations on builder-authored parts. TO output is an iso-surface mesh, where B-rep face-by-face prisms and edge
   fillets do not apply. Frodo's own finding (§1) also shows `selfsupport()` acts **only on faces 0.4-4.5 mm above the
   bed** (`maxdrop=4.5`; I confirmed this at `build_d9.py:41-58`). It is a near-bed fixer, not a general overhang
   repair. My report described it too broadly, and I will correct that in round 3.
   *Requested change:* split D5 into (a) reuse for the **builder path** (CadQuery parts, a collaborator's project #1: "simulate
   parts I've already designed"), and (b) mesh/voxel equivalents for the **TO path**, where overhang is the AM filter
   and repair is voxel-level. Say which rule cards each path uses.

4. **[warning] D6 `emit_problem()` called from builders would modify frozen repos.** The BRIEF and spool-rack's
   AGENTS.md make the existing builders read-only, preserved evidence. `build_d9.py` is also script-style: it runs on
   import and has no `main()`, so `fdmgen` cannot import its `PROTECT` dict without executing the whole 1,191-line
   build. To answer your Q2: the **catalogue** lives in `fdm-gen/catalog/` until v1.0, then splits into its own repo
   once outside users exist. A premature split doubles release work. `emit_problem()` lives in `fdmgen` as a
   dependency-light module.
   *Requested change:* add a third authoring route to D6:
   - *new* builders call `fdmgen.emit_problem()`;
   - *existing* builders are read by **adapters inside fdm-gen** that consume their outputs (`manifest.json`, exported
     STEPs, `PROTECT` solids exported once) and never edit them;
   - *external* users (a collaborator, who may not use CadQuery) author `problem.yaml` + STEP directly, linted by
     `fdmgen lint`.

5. **[warning] §4.3 worked example, `orientation: {mode: fixed}`, vs Gandalf P1 (sweep 3 orientations on the
   bracket).** These are not really in conflict, but the merged plan must choose. Fixed is right for the *product*
   bracket. A sweep is needed for the *MVP known-answer test*.
   *Requested change:* show `mode: sweep` with `candidates: auto` as the general form, and the bracket's
   `fixed + reason` as an override. That is exactly the pattern of your `rule_overrides`.

6. **[warning] Three vocabularies for frames, tiers and verdicts.**
   - Frames: Frodo `design/print/plate`, Sauron `D/P/M/G`, Gandalf `part/installed/print/bed`.
   - Evidence: Frodo U/S/V/L/H per value, Sauron T0-T2 per card, Gandalf ASSUMED/....
   - Results: Frodo's acceptance ladder, my status enums, spool-rack's existing strings.

   *Requested change:* adopt your U/S/V/L/H as the **per-value** tag, Sauron's T0-T2 as the **card** tier, and your
   verdict ladder as the result rung. Extend it with the spool-rack strings verbatim so historical receipts map onto
   it. Your print frame "origin at the part's bed-contact minimum" should become Sauron's P frame.

7. **[warning] Check levels V/M/T/P vs my design/geometry/toolpath.** Yours is better: P (physical) belongs there, and
   so does "report the highest level actually reached" (D2). I will adopt it. One gap: your enforcement modes include
   `repair`. **Request:** state that any `repair` must be followed by a re-check at the same level, and must emit a
   delta (as T10 says). Then a repair can never turn a FAIL into a PASS without evidence.

8. **[note] §1 inventory is more complete than mine on one item.** You found `analysis/rev-g2/package_part.py`, the
   existing Orca/Bambu 3MF writer with `normal_part`/`modifier_part` and per-part metadata. It is the right base for my
   S5 "3MF writer". Two notes:
   - It sets `wall_loops` at **object** level and only `sparse_infill_density` per modifier, so per-region wall
     counts remain unverified (my P0-D spike).
   - It hard-codes a bracket-specific build transform (`'0 -1 0 1 0 0 0 0 1 12.5 274.2465 0'`). Port it with the
     transform as an input.

9. **[note] §2.1 `w` per region (outer 0.42, inner 0.45) is a needed refinement for Sauron's shell formula.** Sauron
   uses n_w·w with w = 0.42 and gets 0.64 mm minimum at 50° from horizontal. You use 0.45 and get 0.67 mm at 42° from
   horizontal (your φ). Both are right for their inputs, and the formulas agree after mapping angles (your φ =
   90° − Sauron's α). **Request:** state in SHELL-001 that the wall term is the *sum of actual wall widths*, and refer
   to Sauron's coating as the V-level implementation instead of a separate penalty.

10. **[note] §6 v1.0 release criterion "no H values" is right but far away.** Your coupon plate (Q5) is the
    critical-path item for every tier upgrade. **Request:** give a per-phase catalogue target so the roadmap can
    publish honestly before v1.0. For example: v0.1 at P1 (all rules defined, V/M/T checkers for OVH, WALL, GAP, BRG,
    PROC; tiers as found); v0.5 at P2 after the first calibration plate per material.

11. **[note] Your trap list T1-T17 is evidence-backed.** I independently confirmed:
    - T1: the `overhang-threshold-test/build.py` comment says "angle from vertical", but `run=15*tan(ang)` is the
      vertical drop, so `wedge-30deg` is 30° from horizontal.
    - T3: `filament_shrink` 99.46% is present in `filament-polylite-asa-calibrated.json`.
    - T5: `Z_SAMPLE_COUNT = 10`.
    - T6: 20 mm in code vs 15 mm in `SKILL.md:334`.
    - T13: `strict: False` in `verify_plates.py`.
    - The Arachne/classic split: `process.json:278` classic vs `package_part.py:31` arachne.

    One correction applies to me, not to you: my report quoted the threshold test as "support at 45° from vertical,
    none at 35". That repeats the builder's own comment. Your convention (55° from horizontal had none) is the
    unambiguous form.

12. **[note] Licence split (CC-BY-4.0 data, permissive code) matches my Q4.** Both reports leave the final choice to
    the user. Merge into one open question.

## 3. What the merged plan must keep

- **Catalogue = rules + separately versioned calibration bindings + checkers** (D1), with **STALE** propagation when a
  bound profile hash changes (§4.2). This is the cleanest answer to "settings that don't do what they claim".
- **Check levels V/M/T/P and "highest level actually reached"** (D2), replacing my three-level scheme.
- **One angle convention, slope from horizontal, with the other printed in brackets** (D3), backed by the real
  file-name flip T1.
- **Explicit compensation ownership** (D4) and the `compensation:` block. T3 is a real double-counting hazard in the
  ASA profile.
- **PROC-001 effective-settings verification** generalised from `gpu_demo_slice.py`. It is the most user-protective
  rule in the catalogue.
- The **rule-card format** with message templates that give location in print-frame coordinates and three fixes,
  one of which is "declare an exception with a reason".
- The **trap table T1-T17**, as the regression and lint backlog.
- The **ranked-orientation table** as a Pareto view, never ranking across fidelities (D7, T14). This is the user-facing
  form of the orientation stage that all four reports propose.
- The **website template** with a fixed "establishes / does not establish" block and the verdict rung in the headline
  (§5.5).
- Fit classes keyed by orientation + profile hash, with `NOT_CALIBRATED` instead of PASS for unknown combinations
  (HOLE-002).
