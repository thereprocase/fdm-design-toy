# Benchmark receipts (#5, #10, #4)

Run from the project root with the geometry/development dependencies installed.
GPU runs use pinned Warp 1.17.0. Compilation is excluded from matvec timings.

- `python bench/geometry.py --mesh body.stl --h 0.4 --out geometry.json`
  compares scanline and polygon-section occupancy hashes and timings, then times
  node coordinates on a 4 M-cell grid. Omit `--mesh` for a synthetic annulus.
- `python bench/matvec_benchmark.py --device cuda:0 --grid 128,128,128 --seconds 600 --out matvec.json`
  measures synchronized FP32/FP64 operator windows. A CUDA failure produces no GPU receipt.
  `--device cpu --grid 8,4,4 --seconds 1` is a smoke test only.

Long runs belong in named detached tmux sessions, with logs and exit-code files.
For example (choose unused session and output names):

```sh
tmux new-session -d -s solver-fdm-matvec \
  'python bench/matvec_benchmark.py --seconds 600 --out matvec.json > matvec.log 2>&1; result=$?; echo "$result" > matvec.exit'
```

Committed receipts establish local synthetic geometry parity/timing and a small
CPU operator smoke test. They do not establish the real bracket gate, GPU thermal
stability, peak hierarchy VRAM, physical accuracy, or print qualification.
The minimum/first throughput ratio is a diagnostic, not automatic thermal acceptance:
compare sustained 0.4 mm runs with a separately measured burst on the same device.
B4/B5 hierarchy VRAM and the sustained GPU thermal gate remain open in #10.
B10 FP64 reference covariance now passes all 24 proper grid rotations on a
masked non-cubic TI case; this does not establish production GPU rotation parity.

The solver regression in `tests/test_coarse_operator.py` uses CPU Warp and checks
that the dense coarsest inverse actually inverts the first Galerkin operator,
including a masked thin-shell domain. It does not measure bracket convergence.

Real-bracket receipt `receipts/geometry-bracket.json`: the hashed body at 0.4 mm
has exact scanline/section occupancy parity; three local scanline runs take
2.64–2.74 s (measured; this establishes #5 voxeliser timing for that fixture).
The local GPU smoke receipt identifies the actual Quadro T2000, not the larger
GPU described by the original handoff. It is a smoke measurement, not a thermal
gate or a full 0.4 mm hierarchy memory result.

`python bench/domain_audit.py --root <checkout> --out connectivity.json` audits
body connectivity and clamp/load membership. At 3.2 mm, a disconnected loaded
seven-cell island has no full clamp: that resolution is an invalid mechanical
repro. At 1.6 mm the body is node-connected but has five face-connected groups;
at 0.8 mm it is face-connected. Node connectivity does not prove absence of
hinge modes or full rigid-body restraint. See the hashed connectivity receipt.
The bracket runner stops optimisation after a failed true-residual check.

R1 masked-bracket comparison on the actual Quadro T2000 (one cold-start solve,
E_min=1e-6, 0.5 uniform density, h=1.6 mm): degree-40 Chebyshev at the coarsest
level takes 84 CG iterations / 2.90 s; dense solve with `--coarsest-dofs 4000`
takes 56 / 1.84 s. True residuals are 6.4e-7 and 2.4e-7; compliance agrees to
1.17e-10 relative. Setup timings are NOT a fair comparison: the first run
includes compilation (81.84 s), the second uses a warm cache (2.70 s).
This supports investigating the coarsest solve but does not meet the <=40 gate,
and neither R1 run establishes the 0.8 mm per-optimiser-iteration timing gate.
The receipts pin device, precision, inputs and solver settings. Full R2/R3,
E_min/TI sweeps, zero-ersatz gap and sustained/memory benchmarks remain open.

#5 mesh scaling: `--connectivity --node-grid 200,200,100` and
`--connectivity --node-grid 200,200,200` also build full 24-DOF element maps.
Committed local receipts measure node coordinates plus connectivity at 1.53 s
for 4 M cells and 3.20 s for 8 M cells, both below 30 s. They establish structured
mesh build performance for those grids, not imported-mesh repair or physical accuracy.

The 0.4 mm bracket grid cannot run the current full MG hierarchy on this actual
4 GiB GPU. An analytic lower bound from only fine work vectors plus the second
Galerkin level is 4.089 GiB, already above capacity, before masks, diagonals,
other levels and driver memory. See `bracket-04-memory-lower-bound.json`.
This is an allocation estimate, not measured peak VRAM; the requested #10 full
0.4 mm hierarchy and thermal benchmarks need a larger GPU or storage changes.

CPU aggregation pilot (#4): with optional `pyamg==5.3.0` installed, run
`python bench/amg_bracket.py --root <checkout> --out amg.json` in detached tmux.
Limit BLAS/OpenMP threads and wrap the command in an external timeout. The
pilot assembles active cells only, keeps homogeneous constrained rows as
identity, and validates against a sparse direct solve. It compares translation
candidates, six rigid-body candidates, and six candidates with energy-smoothed
interpolation. All use symmetric block Gauss–Seidel smoothing and FP64 CG.
A fixed random seed makes candidate setup reproducible within the same environment.
The diagnostic solve timings include an extra true-residual matvec per iteration.
This experiment tests interpolation on one uniform-density R1 design field;
it is not the mixed-precision GPU gate or an optimisation sweep. Candidate
construction follows the elasticity example in the
[PyAMG examples](https://github.com/pyamg/pyamg-examples/tree/main/linear_elasticity).
Use `--skip-direct` to run the iterative trials independently when sparse
factorisation is slow. Such receipts report true residuals but leave direct
reference error fields null; they must not be described as direct-validated.

Measured R1 CPU pilot (`receipts/bracket-r1-amg-cpu.json`, PyAMG 5.3.0,
isotropic, density 0.5, E_min=1e-6): translation-only candidates required
162 CG iterations, six rigid-body candidates 42, and six with energy-smoothed
interpolation 26. True residuals were respectively 8.39e-7, 9.49e-7 and 4.48e-7.
The active matrix has 164,364 DOFs and 9,724,592 nonzeros. Compliance agrees
across variants to about 8e-13 relative; this is internal agreement, not an
independent direct-reference validation. The iterative receipt used one BLAS
thread while other bounded jobs ran. Setup/solve seconds were 2.15/37.52,
3.65/10.51 and 11.06/8.61: fewer iterations did not give the fastest first solve
once setup is included. This supports testing elasticity-aware interpolation
in the production solver; it does not establish GPU runtime, mixed-precision
accuracy, a material/resolution sweep, or the full <=40-iteration solver gate.

`python bench/export_bracket_stress.py --root <checkout> --out stress.npz`
exports an orientation prescreen under the full G2 load. The default R1 model
is a fully solid envelope with isotropic E=1000 MPa and nu=0.3. It is not the
printed shell/helper material model. It retains the solver-gate mounting clamp
and bilateral wall roller approximation. The JSON sidecar records convergence,
mesh/output hashes, transforms, units and limitations.

NPZ `fdmgen.stress-field.v1` stores installed-frame `centres_mm` (N,3),
`stress_mpa` (N,6: xx yy zz yz xz xy), `cell_volume_mm3` (N,), and
`cell_indices` (N,3) in `argwhere(solid_mask)` order. `solid_mask` is the complete
3D print-grid occupancy; indices are in that grid, not installed coordinates.
`frame` and `voigt_order` are strings in the archive. Samples are at cell
centres; they do not establish within-cell peak stress or mesh convergence.

The same CPU pilot at 0.8 mm (`receipts/bracket-08-amg-cpu.json`) has 1,143,591
active DOFs / 72,869,440 nonzeros. Translation candidates require 230 CG
iterations, rigid6 65, and rigid6 with energy interpolation 32, with true
residuals 9.88e-7, 7.20e-7 and 5.03e-7. Setup/solve times on one CPU thread
are 17.03/358.76 s, 27.93/109.58 s and 69.21/53.90 s. Peak process RSS across
the sequential variants is 9.88 GB. All three completed within the external
900-second timeout. Compliance agrees to 3.2e-12 relative across variants;
there is no independent direct reference. This remains a uniform-density,
isotropic FP64 CPU test, not the TI/E_min/mixed-precision production gate.

### Slice occupancy mechanics audit

`compare_occupancy.py` compares thresholded baseline/project occupancy on the
pinned solver grid. It validates the grid receipt, body mesh, pose and boundary
selection before assembling anything. The reference loads are retained exactly;
missing loaded DOFs, face-disconnected pieces, or insufficient restraints block
a solve. Edge/point connections are counted separately. There is no ersatz
material and no implicit force redistribution.

```bash
python bench/compare_occupancy.py --root /path/to/part-checkout \
  --reference bench/receipts/bracket-stress-r1.json \
  --baseline shell-only.npz --project helpers.npz \
  --threshold 0.5 --audit-only --out audit.json
```

Without `--audit-only`, eligible domains use CPU AMG with isotropic E = 1000 MPa,
nu = 0.3, the original full-load boundary arrays and a true-residual check. A
fully solid solve must reproduce the pinned compliance before a comparison is
reported. This is a coarse thresholded-raster experiment, not printed-material
truth, anisotropic strength or physical qualification. Run on a compute worker
in a named detached job with logs and an exit-code file.

The R1 seeded-helper audit found that the 0.5 threshold loses 108 original
loaded DOFs in both slices (6.493 N summed absolute missing DOF forces; this is
not the magnitude of a resultant). Both retain about 113.844 N in the vertical
load direction instead of 117.720 N and acquire a 2.018 N horizontal resultant.
The slice domains have 7 / 6 face-connected components and 3 / 3 node-connected
components. Lowering the threshold to 0.25 retains all original load DOFs but
still leaves a 30-cell piece joined only through edges or nodes. The full-body
centre-sampled reference itself has five face components, all node-connected.
At 0.75, 648 loaded DOFs are missing. These receipts establish sensitivity to
coarse occupancy and load discretisation; they do not establish helper stiffness
improvement. A revised contact-load discretisation must explicitly preserve each
seat's resultant and moment before such a comparison can be interpreted.

### Explicit seat-load transfer and connected-domain sensitivity

`seat_load_transfer.py` constructs nonnegative nodal forces parallel to each
original seat force. Weights are closest to uniform while preserving that seat's
resultant and moment about the zero of the solver coordinate frame. Candidate
nodes are the intersection of surviving nodes in both slices and the full-body
context, restricted to the original bearing-side nodes. Each case receives the
same resulting load array. This is an explicit discretisation change, not a
contact-pressure solution.

```bash
python bench/seat_load_transfer.py --root /path/to/part-checkout \
  --reference bench/receipts/bracket-stress-r1.json \
  --baseline shell-only.npz --project helpers.npz --out transfer.json
# Separate sensitivity: explicitly remove face-disconnected fragments, then solve.
python bench/seat_load_transfer.py --root /path/to/part-checkout \
  --reference bench/receipts/bracket-stress-r1.json \
  --baseline shell-only.npz --project helpers.npz --out sensitivity.json \
  --largest-face-component --solve
```

The first command retains the raw domains and their connectivity failures.
The second records removed cells, cell volumes, original load and restraint
DOFs before retaining each largest face-connected component. It does not insert
stiffness into empty cells. The adjacent NPZ stores original/transferred loads
and constraints; receipts pin input and output hashes.

Measured R1 sensitivity at density threshold 0.5, E = 1000 MPa, nu = 0.3:

| Domain | Removed cells | Compliance N·mm | Maximum displacement mm |
|---|---:|---:|---:|
| Full-body context | 120 | 108.549 | 1.744 |
| Shell-only | 52 | 484.839 | 8.130 |
| Seeded helpers | 51 | 470.662 | 7.932 |

None of the removed fragments had original loaded or fixed DOFs exclusive to
its nodes. The transfers retain 620 rear-seat and 600 front-seat nodes, with
force errors below 2e-13 N and moment errors below 3e-11 N·mm. All three true
relative residuals are below 1e-8. The helper case has 2.924% lower compliance
under this common redistributed load and **explicitly modified domain policy**.
The full-body centre-sampled context is not a guaranteed stiffness bound because
its boundary occupancy differs from the deposited-road raster.

Receipts: `receipts/occupancy-seat-transfer-r1.json` (raw topology still blocked)
and `receipts/occupancy-connected-sensitivity-r1.json` (modified domains).
This does not establish the unmodified 0.5-domain result, mesh convergence,
unchanged local pressure, anisotropic behaviour, large-deflection validity or physical performance.
The solver uses linear small-displacement elasticity; the reported millimetres
are model outputs, not validated movement predictions.

### Threshold robustness of the connected-domain comparison

The helper effect is **not established as robust to the coarse modelling
policy**. Repeating the same explicit largest-component and per-seat
force/moment-transfer procedure on the same R1 density fields gives:

| Density threshold | Baseline compliance N·mm | Project compliance N·mm | Project change | Common seat nodes, rear / front |
|---|---:|---:|---:|---:|
| 0.25 | 287.482 | 283.496 | −1.387% | 626 / 648 |
| 0.50 | 484.839 | 470.662 | −2.924% | 620 / 600 |
| 0.75 | 15,695.155 | 15,901.856 | +1.317% | 286 / 214 |

Each pair uses identical load arrays, with each original seat resultant and
moment conserved. **The nodal arrays differ between thresholds**, so this is a
combined threshold/domain/load-discretisation sensitivity, not an isolated
threshold effect. The 0.75 cleanup removes 519 / 540 cells and removes nodes
that originally carried 63.065 N of summed absolute force components before
transfer. Its linear-model maximum movements are 224 / 227 mm; these cannot be
interpreted as physical small-displacement predictions. The sign reversal does
not establish that the helpers harm the printed part.

Receipts: `receipts/occupancy-connected-threshold025-r1.json` and
`receipts/occupancy-connected-threshold075-r1.json`, alongside the original 0.50
receipt. Reproduce with `--threshold 0.25` or `--threshold 0.75` on the command
above. The first 0.75 baseline solve narrowly missed the independent 1e-8 true
residual gate (1.0131e-8), despite CG reporting success. Tightening the internal
CG target to 1e-9, with the acceptance gate unchanged, gave residuals below
2.1e-9 for the accepted 0.75 pair. Do not promote the isolated −2.924% result to
a design benefit without resolving occupancy sampling and discretisation.

### Bead-sampling sensitivity at threshold 0.5

Refining the deposited-road sampling step on the same 1.6 mm grid retains
the sign of the paired compliance change in all four trials. These are
**modified-domain, isotropic FE sensitivities**, not physical stiffness evidence.
The occupancy producer was unchanged; the input pairs were generated with its
deposition sampling step bound to h/K. Each receipt preserves that provenance.

| Sampling step | Baseline compliance N·mm | Project compliance N·mm | Project change | Common seat nodes, rear / front | Removed cells, baseline / project |
|---|---:|---:|---:|---:|---:|
| h/3 | 484.839 | 470.662 | −2.924% | 620 / 600 | 52 / 51 |
| h/6 | 466.910 | 451.602 | −3.279% | 619 / 600 | 58 / 58 |
| h/12 | 479.847 | 465.891 | −2.909% | 616 / 600 | 45 / 45 |
| h/16 | 476.874 | 462.627 | −2.988% | 618 / 600 | 45 / 45 |

All cases use density >= 0.5, explicit largest-face-component retention,
E = 1000 MPa and nu = 0.3. Loads are identical within each baseline/project/context
triple, but surviving seat nodes and transferred load arrays change between
sampling levels. This is therefore combined sampling/domain/load-discretisation
sensitivity. Each seat conserves its original force and moment (errors below
2e-13 N and 3e-11 N·mm); no removed fragment exclusively carried an original
loaded or fixed DOF. All true relative residuals are below 9e-10.

The h/3 control reproduces the earlier −2.924% result. The four-trial range
−3.279% to −2.909% is an observed sensitivity range, not a confidence interval
or convergence bound. Absolute compliance is non-monotonic with refinement.
The sign reversal in the preceding threshold study remains unresolved; these
results do not establish robustness to threshold, spatial-grid refinement,
contact pressure, anisotropy or physical printing. Maximum linear-model movements
remain about 7.4–8.1 mm, without physical validation.

Receipts: `receipts/occupancy-connected-sampling03-r1.json`,
`receipts/occupancy-connected-sampling06-r1.json`,
`receipts/occupancy-connected-sampling12-r1.json`, and
`receipts/occupancy-connected-sampling16-r1.json`. Reproduce with the
`seat_load_transfer.py --largest-face-component --solve` command above and
the corresponding pinned sampling pair. Each receipt records both NPZ hashes,
the source NPZ hashes, sampling step, domain audit and transferred-load hash.

Input verification initially stopped before solving because the h/12 baseline
handoff digest contained only 63 characters. The accepted run explicitly pinned
the observed 64-character digest recorded in its receipt and verified embedded
provenance against the sidecar and the recorded mask count. No claim is made that
the malformed handoff digest matched. Solves used source commit `35511cc`; the
compute-box suite passed 202 tests, with 6 CUDA-only skips.

### Density-weighted sensitivity: a different constitutive assumption

`density_weighted.py` replaces binary occupancy with
`E/E0 = min(raw_density, 1)^power`, using power 1 or 3 and **no stiffness floor**.
Zero-density cells are absent. This removes the positive density cutoff but
introduces an uncalibrated homogenisation law: even a small deposit spreads
stiffness across the whole coarse cell and may bridge an unresolved bead gap.
A cubic penalty is a sensitivity choice, not a measured printed-material law.

```bash
python bench/density_weighted.py --root /path/to/part-checkout \
  --reference bench/receipts/bracket-stress-r1.json \
  --baseline seed-shell-only-r1-sf16.npz --project seed-project-r1-sf16.npz \
  --power 1 --largest-face-component --solve --out weighted-p1.json
# Repeat with --power 3 and a distinct output file.
```

The script preserves the original full-body nodal load array and restraints.
Raw and retained-domain audits are both recorded; missing loaded nodes or
connectivity failures block solving. The explicit largest-component option
records removed grid/deposited volume and any original load/restraint DOFs lost
with those cells. It never redistributes the loads.

Measured on the pinned h/16 sampling pair, 1.6 mm solver grid, E0 = 1000 MPa,
nu = 0.3, with identical original loads in both trials:

| Density exponent | Baseline compliance N·mm | Project compliance N·mm | Project change | Maximum displacement baseline / project, mm |
|---|---:|---:|---:|---:|
| 1 | 318.130 | 312.602 | −1.738% | 5.351 / 5.269 |
| 3 | 622.043 | 603.964 | −2.906% | 10.389 / 10.114 |

Both printed domains are already single face-connected components (32,931 /
33,071 positive-density cells), retain every original loaded DOF, and lose
**zero cells** under the largest-component option. The full-body context alone
loses its usual 120 fragments and gives 108.515 N·mm; it remains contextual,
not a guaranteed stiffness bound. Minimum retained E/E0 is 3.12e-4 for power 1
and 3.04e-11 for power 3. This is not an imposed stiffness floor.

Every true relative residual is below 9e-10. The sizeable change in absolute
response between laws shows why this is not a resolution of model uncertainty.
The result is not directly equivalent to the binary-mask pilots, whose domain
and redistributed nodal loads differ. Neither density law establishes bond
continuity, anisotropic strength, mesh convergence or physical displacement.
The reported millimetres are unvalidated linear-model outputs.

Receipts: `receipts/occupancy-density-p1-sf16-r1.json` and
`receipts/occupancy-density-p3-sf16-r1.json`, using the distinct
`fdmgen/density-weighted-mechanics-pilot@0.1` schema. Existing mechanics UI inputs
intentionally reject that schema rather than labelling it a thresholded result.
Both retain full input provenance and hashes. Known-answer tests verify density
capping, exact zero stiffness outside deposits and compliance scaling of a
clamped block with a fixed load (1×, 2×, 8× for full, half-linear, half-cubic).

### Optional road caps: segmentation sensitivity

The density pilots above use caps-off occupancy. In the historical producer
`419dd82`, optional `deposit(caps=True)` extended each segment **forward** by
half its width and redistributed the same extruded volume over the extended
road. It filled some raster corner gaps, but also changed density according to
how a path was split into G-code moves. The audit below motivated the revision
described next; it does not describe the current producer.

A synthetic straight 10 × 0.42 × 0.2 mm road (0.84 mm³) was represented as
1, 10 or 100 equal collinear moves, with identical total extrusion. On a fixed
0.1 mm grid, deposition step 0.02 mm and slightly offset origin:

| Moves | Caps-off volume moved versus one move, mm³ | Caps-on volume moved versus one move, mm³ | Caps-on volume moved versus same uncapped path, mm³ |
|---|---:|---:|---:|
| 1 | 0 | 0 | 0.01790 |
| 10 | <1e-15 | 0.11236 | 0.12421 |
| 100 | <1e-15 | 0.01754 | 0.00893 |

“Moved” means half the L1 difference between cell-volume arrays. All six runs
conserve the input volume within 1e-12 tolerance, with zero outside the grid.
Changing one move to ten reassigns 13.4% of the road volume with caps enabled;
the uncapped control is invariant to numerical precision in this experiment.
The response is not monotonic in segment count. This measures synthetic raster
sensitivity, not the size or direction of the effect on the bracket or its
mechanics. It neither validates caps-off geometry nor invalidates a physical
print; corner shape and overlap still need a defensible bead model.

Reproduce with `PYTHONPATH=src python bench/road_caps_audit.py --out audit.json`.
`receipts/road-caps-audit.json` records grid, input G-code hashes, density hashes
and volume accounting. The script generates all inputs without external part
files. No producer defaults or published occupancy fields were changed.

#### Independent check after the caps revision

Producer `22f64d8` adds extensions at path ends and turns, omits them at straight
continuations, deposits extension material at each road's line density, and
rescales the field once to preserve total extrusion. The same synthetic inputs
were rerun from source snapshot `1a863be`; the producer source hash is recorded
in both new receipts. The historical receipt above remains unchanged.

| Deposition step | Caps-on volume moved, 10 versus 1 move | Caps-on volume moved, 100 versus 1 move |
|---|---:|---:|
| 0.02 mm (original audit) | 0.001533 mm³ / 0.1825% | 0.001310 mm³ / 0.1560% |
| 0.008333 mm (h/12) | 0.001561 mm³ / 0.1858% | 0.001359 mm³ / 0.1617% |

At the original sampling step, the ten-way split effect fell from 13.4% to
0.1825%. Uncapped fields differ by less than 1e-14 mm³ in these reruns. All
input volume remains accounted, with no clipping. The remaining differences
are small but nonzero, and do not decrease monotonically in these two sampling
trials. This supports approximate segmentation consistency for this synthetic
case; it is not proof of exact invariance, bead geometry or bracket mechanics.
Existing caps-off mechanics receipts are unchanged.

Receipts: `receipts/road-caps-revised-step5.json` and
`receipts/road-caps-revised-step12.json`. The audit now records the imported
producer file's SHA-256 and accepts `--step-frac`; use the default 0.2 or
`--step-frac 0.08333333333333333` with distinct output files to reproduce.

### Arc fitting on the real bracket (P0-B)

The archived 2-wall, 5-layer audit project of the bracket was re-sliced twice with the same Orca 2.4.2
executable. The two projects differ only in `enable_arc_fitting`. Both G-code files pass the reader's footer
guard.

| | arc fitting off | arc fitting on |
|---|---:|---:|
| Arc chords inside the object (5° each) | 0 | 87,467 |
| Credited volume, mm³ | 70,979.670 | 70,979.038 |
| Orca footer filament, mm | 32,396.18 | 32,394.23 |

Credited volume differs by −0.0009 %, which meets the 0.1 % gate. Orca's own footer differs by −0.006 %, so
arc fitting also changes the slicer's plan slightly. The overhang-wall role changes by −1.8 % and gap infill
by +0.2 %, while walls and skins agree within 0.012 %.

On one 0.4 mm print-frame grid with caps off and step 1/3, 1.06 % of the material lands in different cells.
19,745 of about 1.13 M solid cells flip at a density of 0.5. That is local placement only: arcs and chords
of the same curve, plus the plan changes above.

What this establishes: the reader credits the same material whether Orca writes this part's curves as arcs
or as chords, within 0.001 %.

What it does not establish: equality of the deposited field cell by cell, or equality for every part. The
small-part fixture in `tests/fixtures/gcode/arc-parity/` shows Orca's plan moving gap infill by about 0.1 %.
It also establishes nothing about the printed part.

Reproduce: re-slice the audit project twice with `enable_arc_fitting` 0 and 1 and arrange and orient off,
then run the command below. `receipts/arc-parity-bracket.json` records both project and G-code hashes, the
grid and every number above.

```bash
PYTHONPATH=src python bench/arc_parity.py PLAIN.gcode ARCED.gcode --project-sha256 PLAIN_SHA ARCED_SHA --out receipt.json
```

### Corner-cap mechanics sensitivity on the R1 grid

The revised optional road-end/turn caps were tested on the same slices, h/16
bead sampling and 1.6 mm solver grid as the uncapped sampling study above.
Input hashes, embedded provenance against sidecars, zero clipping and credited
volume accounting were verified before solving. The producer reports caps=True;
this is an approximate bead raster, not measured printed material.

| Raster model | Baseline compliance N·mm | Project compliance N·mm | Project change | Common seat nodes, rear / front | Removed cells, baseline / project |
|---|---:|---:|---:|---:|---:|
| Uncapped | 476.874 | 462.627 | −2.988% | 618 / 600 | 45 / 45 |
| End/turn caps | 485.325 | 474.219 | −2.288% | 618 / 602 | 58 / 58 |

The apparent reduction is smaller by 0.699 percentage points. This is combined
raster/domain/load-discretisation sensitivity: the transferred front-seat load
array changes, and retained fixed DOFs rise from 1993 to 2015. It does not isolate
corner filling under an identical nodal load and restraint set. The physical
restraint selection rule, E = 1000 MPa, nu = 0.3, density threshold 0.5 and explicit
largest-face-component policy remain the same. Each baseline/project/context
triple uses one common transferred load array.

The unmodified capped masks remain **blocked**: both have five face-connected
components and lose original loaded DOFs (106 baseline / 108 project;
6.435 / 6.605 N L1 load). The modified-domain sensitivity removes 58 cells
(237.568 mm³) from each printed mask; none exclusively carries an original load
or fixed DOF. Each seat's resultant and moment are conserved to below 2e-13 N
and 3e-11 N·mm. All three solves pass the unchanged true-residual acceptance
criterion (largest observed residual 9.04e-10). The full-solid contextual
compliance is 108.551 N·mm; it is not a guaranteed stiffness bound for raster
boundary cells. Maximum linear-model movement is 8.060 / 7.910 mm for the
baseline/project, without physical validation.

Receipts: `receipts/occupancy-caps-sf16-raw-r1.json` preserves the blocked raw
audits; `receipts/occupancy-caps-sf16-connected-r1.json` records the explicitly
modified solve. Original uncapped receipts are unchanged. Reproduce using
`compare_occupancy.py --audit-only` and
`seat_load_transfer.py --threshold .5 --largest-face-component --solve` with the
capped NPZ hashes pinned in the new receipts. Solver source was `32c96bf`.
This result does not resolve the threshold sign reversal or establish helper
strength, grid convergence, realistic contact, anisotropy or physical performance.

### CPU TI and stiffness-contrast sensitivity

`amg_sensitivity.py` extends the CPU aggregation investigation with an explicit
synthetic TI family and nonuniform stiffness. It does not change the production
solver or fit a material card. Run on the compute worker with the existing
optional PyAMG dependency, one BLAS/OpenMP thread, a named detached job and an
external timeout:

```sh
python bench/amg_sensitivity.py --root /path/to/part-source \
  --ratios 1 .7 --axes z --patterns uniform bands --emin 1e-3 \
  --maxiter 150 --out out/amg-sensitivity.json
```

The law is `Ep=1`, `Ez=ratio`, `nu_p=nu_pz=0.3`, `Gpz=ratio/2.6` in the grid
frame. `--axes x y z` rotates the TI axis using proper cyclic permutations.
This family is a numerical challenge, not measured printed-material properties.
The uniform control uses density 0.5; the band case alternates density 0 and 1
in four-cell grid-X bands inside the body. Body stiffness is
`E_min + rho^3 (1-E_min)`; outside cells remain exactly inactive. Unlike the
uniform control, the band case exercises actual stiffness contrast. The bands
are artificial and are not printable helper proposals.

Every solve resets the random seed and records its true residual, convergence
status, iteration count, timing, law, field hashes, load/restraint hashes and
source hashes. Timing includes diagnostic residual matvecs. Exit 2 records at
least one unconverged case; a written receipt alone does not establish convergence.
Use a fresh output path for each run. Known-answer tests cover the isotropic
limit, weak-axis compliance, band contrast, and a small TI contrast solve against
a dense direct reference. These checks do not establish full bracket accuracy,
GPU or mixed-precision performance, realistic contact, the zero-ersatz gap, or
physical qualification.

Measured R1 contrast result (`receipts/bracket-r1-ti-bands-emin003.json`, harness
`516af9b`): energy-smoothed aggregation, six rigid-body candidates, one CPU thread,
`E_min=1e-3`, fixed grid-Z TI axis and per-case seed 0:

| Field | Ez/Ep | CG iterations | True relative residual | Setup / solve seconds | Converged at 1e-6 |
|---|---:|---:|---:|---:|---|
| Uniform rho 0.5 | 1.0 | 26 | 4.48e-7 | 8.92 / 5.64 | yes |
| Uniform rho 0.5 | 0.7 | 27 | 4.56e-7 | 8.90 / 5.90 | yes |
| Four-cell rho 0/1 bands | 1.0 | 150 (cap) | 3.07e-3 | 8.88 / 32.72 | **no** |
| Four-cell rho 0/1 bands | 0.7 | 150 (cap) | 1.68e-3 | 8.92 / 32.92 | **no** |

The benchmark exited 2 as intended: both band cases failed the residual target.
Their compliance values are unconverged iterates, not accuracy or stiffness
comparison evidence. The uniform field has one stiffness value (0.125875); the
bands have stiffness 0.001 and 1, a real 1,000:1 contrast. This demonstrates a
limitation of the tested default aggregation configuration on a deliberately
segmented field; the uniform-density result is insufficient evidence for an
optimisation solver. It does not prove failure for every heterogeneous field,
constitutive law, AMG configuration or GPU implementation. The observed timings
include diagnostic work on a shared CPU worker and are not GPU gate measurements.
Next investigation: aggregation strength and interpolation that preserve motion
of stiff regions separated by soft bands, tested against this unchanged receipt
before any claim of improvement. Full remote validation of the harness: 253 tests
passed, 6 CUDA-only skips; the small direct-reference test passed separately.

For a card-informed conditioning study, use
`--card-ratio-corners polymaker-polylite-asa-t0` instead of explicit `--ratios`.
The harness reads and hashes the linted card: both `E_z_over_E_p` interval ends
and both `G_z_over_E_z` interval ends, keeping the card's nominal Poisson inputs.
This is four ratio combinations, **not all uncertainty corners** (the Poisson
intervals are not swept). Ep remains normalized to 1, so this is neither a
short-term nor sustained dimensional movement prediction. The receipt retains
borrowed/assumed evidence tags. Explicit synthetic studies can instead use
`--shear-ratios`, `--nu-p` and `--nu-pz`; mixing those overrides with card mode
is refused. Previous receipts and the original synthetic defaults stay intact.

Card-ratio run (`receipts/bracket-r1-card-corners-emin003.json`, harness `1f46cab`)
uses the pinned T0 PolyLite ASA card's Ez/Ep endpoints (borrowed vendor ratio),
Gz/Ez endpoints (assumption), and nominal `nu_p=0.38`, `nu_pz=0.36`. Same R1
mask, loads, restraints, density/stiffness fields and active DOFs as the preceding
synthetic run were verified by their hashes. Grid-Z axis, energy interpolation,
E_min=1e-3 and per-case seed 0 remain fixed.

| Ez/Ep | Gz/Ez | Uniform CG / residual | Banded CG / residual |
|---:|---:|---:|---:|
| 0.85 | 0.20 | 33 / 5.82e-7 | 150 cap / 1.98e-2 |
| 0.85 | 0.36 | 28 / 5.68e-7 | 150 cap / 5.79e-3 |
| 0.92 | 0.20 | 33 / 5.24e-7 | 150 cap / 2.18e-2 |
| 0.92 | 0.36 | 28 / 4.26e-7 | 150 cap / 6.22e-3 |

All uniform cases converged; all four band cases missed the 1e-6 target and the
run exited 2. Lower shear ratio increased the uniform iteration count in these
cases; the longitudinal ratio endpoints had no iteration-count difference.
Neither observation is a general condition-number bound. Banded residuals at the
cap remain too large to interpret the saved compliance iterates as converged
predictions. This uses card ratio intervals for a normalized conditioning study,
not measured anisotropy or either dimensional modulus basis. It is not a complete
card uncertainty or orientation sweep. Full remote suite: 258 passed, 6 CUDA-only
skips; card matrices checked against the independently invoked card API after
normalization. Source and card hashes match the published files.

The additive `--strength-thresholds 0 .08 .25` option sweeps symmetric
nodal block-strength filtering with every other case input fixed. Zero retains
the original unfiltered default; each row records method, threshold and block
size. This changes the AMG hierarchy, not the stiffness matrix or boundary
conditions. Direct-reference controls exercise all three thresholds.

Strength sensitivity (`receipts/bracket-r1-strength-emin003.json`, harness
`5f44f92`) holds the R1 banded case at Ez/Ep=0.85, Gpz/Ez=0.20,
nu_p=0.38, nu_pz=0.36, E_min=1e-3, grid-Z axis and energy interpolation.
These explicit normalized parameters match the preceding card corner; this run
uses explicit parameters rather than rereading the card. All mask, load,
restraint, density, stiffness, active-DOF and constitutive inputs match that
corner. The zero-threshold residual history reproduced it exactly.

| Symmetric block-strength theta | CG iterations | Final true relative residual | Operator complexity |
|---:|---:|---:|---:|
| 0 | 150 cap | 0.0198 | 1.241 |
| 0.08 | 150 cap | 248.1 | 1.304 |
| 0.25 | 150 cap | 11.61 | 1.923 |

All three missed 1e-6 (benchmark exit 2). These positive thresholds made this
case worse; none is a recommended setting. No converged compliance comparison
can be made. This does not isolate the cause or establish that every strength
method fails: aggregation, interpolation and preconditioner suitability for CG
still need examination. The original default remains zero. Remote direct-solve
controls passed at all three thresholds; full suite 260 passed, 6 CUDA-only
skips. Source hashes were verified. This is CPU numerical evidence, not a GPU
gate result or a physical bracket prediction.

Use `--coarse-solver pinv` to compare a dense pseudoinverse on the coarsest
operator with the default sparse LU (`splu`). The receipt records this choice
per row. No fine-grid operator, loads or restraints are changed. This option is
an experimental numerical comparison, not an automatic repair or new default.
