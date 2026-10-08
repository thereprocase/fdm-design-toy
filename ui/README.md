# Orientation and massing workspace

Start with the [user workflow guide](WORKFLOW.md) for pose selection, helper editing,
exact-file handoff and evidence review. This page contains technical contracts,
evidence scope and verification details.

Jump to the interaction reference:

- [Compare and select poses](#compare-and-select-poses)
- [Edit and navigate helpers](#edit-and-navigate-helpers)
- [Control the geometry preview](#control-the-geometry-preview)
- [Save inputs and recover rejected imports](#save-inputs-and-recover-rejected-imports)
- [Import an evidence bundle](#import-an-evidence-bundle),
  [navigate the review](#navigate-the-matched-review), and
  [interpret bridge evidence](#interpret-bridge-evidence)
- [Run UI checks on a test worker](#run-all-ui-checks-on-a-test-worker)

Open `ui/index.html` directly in Chromium or serve this directory over localhost.
The current prototype imports an orientation JSON, compares candidates, records
a choice rationale, and exports a massing planning draft. No build step or network
service is required. The interface consumes `fdmgen orient` output;
analysis remains in the Python tooling. No slicer or solver runs in the browser.

The intended complete workflow is:

1. Open an orientation table and inspect the source part and evidence tier.
2. Compare candidate poses by layer failure index, overhang area, bed contact,
   and fit. Missing strength results remain visibly unchecked.
3. Inspect a candidate's rejection reasons and keep a deliberate choice with
   a rationale; a numerical ranking never silently becomes the design decision.
4. Plan a fixed body shell plus 100% helper regions, preserving interfaces and
   keeping sparse infill out of credited structural material.
5. Export a planning document with the selected orientation, shell settings,
   helper intent, outstanding checks and the source table fingerprint.

The orientation-table contract is implemented in `fdmgen.orient`.
Candidate directions and transforms must carry a frame. The stress prescreen
uses installed-frame centres and stress tensors; a consumer must align that
frame with the orientation table before computing failure indices.

Planning is distinct from validated geometry. Helper intent does not create a
modifier mesh or establish bond, overhang, load-path or strength compliance.
The interface must show that distinction at the choice and export steps.

The viewer accepts ASCII or binary STL and checks its SHA256 against the table
before rendering. It applies the supplied design-to-print matrix and translation;
mesh cell indices and installed-frame stresses are never treated as print coordinates.
Drag or use arrow keys to orbit, or choose a top view. The ground rectangle is an
orientation cue, not a printer bed-fit check. Shading is not stress or support evidence.

Current limits: helper boxes are sketches, not validated modifier meshes. Planning exports are drafts. The
viewer has been exercised with the real bracket table and STL in Chromium, including
wrong-mesh rejection and desktop/mobile layout. Synthetic interaction checks cover
selection, unchecked metrics, feasible filtering, exported source hash and invalid
input. Run `node --test ui/viewer.test.cjs` for parser/transform known-answer checks.

Optional Chromium integration: install `playwright` into a temporary tools
directory, expose its `node_modules` through `NODE_PATH`, set `FDM_PREVIEW_MESH`
to the matching `body-mounted.stl`, and run `node ui/browser.test.cjs` from the
repository root. `CHROMIUM_PATH` defaults to `/usr/bin/chromium`. The test checks
the committed real table, matched/mismatched meshes, visible FAIL verdicts,
camera controls and mobile overflow. It does not verify physical correctness.

Planning drafts use `fdmgen.massing-plan.v0.3`. Each requested helper has a
name, location, load purpose and interface/clearance constraints. Shell-only is
an explicit option. Geometry is not created by these intent records. Changing
shell or helper settings does not recompute the source analysis.

Reopen a draft after loading its original orientation table. The exact table
SHA256 must match; stale/other-table drafts are rejected without replacing the
current plan. Reopened evidence comes from the loaded table, not from copied
metrics in the draft. v0.1 free-text helper notes are retained as one region;
location and clearance fields must be completed before exporting a current draft.

Run `node --test ui/plan.test.cjs` for round-trip and provenance checks. With
Playwright exposed through `NODE_PATH`, `node ui/planning.browser.test.cjs`
checks real-table selection, multiple helpers, exact draft round-trip, wrong
source rejection, shell-only export and mobile layout.

Spatial drafts use `fdmgen.massing-plan.v0.3`. A helper may carry a design-frame
box (`geometry.type=box`, `center_mm`, `size_mm`) with `geometry_status=sketch`.
Enable its spatial controls, load a matching mesh, and use **Place centre on part**
to pick a surface. Edit centre/size to position the region through the body.
Boxes remain in the design frame when print poses change; preview outlines are
transformed through the selected pose. Zoom controls help inspect small regions.

The nominal planning screen warns for edges below 0.84 mm, helper pairs with
insufficient overlap/separation, and boxes wholly outside the part bounding box.
The threshold assumes a 0.42 mm line width. A box overlapping the bounding box
is not proof of body intersection or bonding; exact clipping remains downstream.
Print-Z extents are displayed, but layer snapping is not applied. These boxes
are intent, not modifier meshes, credited volume or a new strength result.

`keep_clear` stores validated `interface_ids` and `keep_out_ids`, optional
`clearance_mm`, and a human `note`. Unknown reference IDs are rejected. Older
string notes are migrated. Decision metadata includes candidate ID, source hash,
rank at decision and designer role. v0.1/v0.2 drafts remain readable.
Run `node ui/spatial.browser.test.cjs` with the same Playwright/mesh environment
as the viewer test for real-part picking and spatial save/reopen checks.

On desktop, the part preview stays beside the controls while scrolling through
orientation evidence or helper edits. **Plan this pose** and **Review orientation
choices** connect the two steps. Mesh upload/help collapses after a matching mesh
loads. After surface placement, **Return to helper controls** restores focus to
the region centre. Mobile uses a single column with these explicit navigation
controls, avoiding a fixed preview that would cover the form.

## Coupon slicer evidence

Open `ui/coupons.html` (also linked from the workspace in a new tab), load a
`fdmgen/coupon-plate@0.1` plate JSON, then select one or more
`fdmgen/slice-evidence@0.1` receipts together. Each must match the exact plate
file SHA256 and contain every rung exactly once. The footprint map is selectable
by mouse or keyboard; support settings and measured road counts stay together.
All settings and recorded provenance are available beside the results.

The committed samples are in `tests/fixtures/coupons/`. Comparing the support45
and nosupport receipts demonstrates why zero support roads alone is not evidence
of an unsupported print. Orange means support roads were recorded; grey means
none were recorded. Neither colour is a physical pass. The UI verifies the plate
pairing, not the G-code contents; it records the receipt's G-code hash. Unassigned
support counts and the producer's evidence limits remain visible.

Checks: `node --test ui/coupon-evidence.test.cjs` and, with temporary Playwright
exposed through `NODE_PATH`, `node ui/coupons.browser.test.cjs`.

The orientation comparison also displays the optional T-level pose-slice columns:
support segments, support volume and credited material volume. A slice filter
helps compare only measured poses. Missing columns remain **Not checked**. The
selected-pose panel retains the producer's slicer/profile/placement fidelity
text and credited-volume exclusions. Changing the helper draft does not refresh
these measurements. `node ui/toolpath.browser.test.cjs` (with Playwright exposed)
checks real measured and unmeasured candidates, filter behavior and mobile layout.

## Run all UI checks on a test worker

Keep browser automation and full Python suites off the development laptop. Copy a
source snapshot and the matching part fixture to the compute box, then run inside
a named detached tmux job with a log and exit-code file. No GPU is needed for
these browser checks. Install Node and Playwright in a separate tools directory;
install its Chromium browser and system libraries on the worker.

```bash
export NODE_PATH=/path/to/browser-tools/node_modules
export PLAYWRIGHT_BROWSERS_PATH=/path/to/browser-tools/browsers
export FDM_PREVIEW_MESH=/path/to/body-mounted.stl
bash ui/run-tests.sh
```

The runner uses Playwright's installed Chromium unless `CHROMIUM_PATH` is set.
It requires the real mesh fixture and runs all Node checks plus the planning,
pose-toolpath, coupon, spatial-editing and mesh-import browser checks sequentially.
A missing fixture or browser is an error, not a silently skipped check. Run the
Python suite separately; the UI runner does not establish solver correctness.

## Modifier capability evidence

The massing form includes the measured per-modifier requests from the slicer
capability catalog, with profile/template context, side effects and recorded
G-code/build provenance. Each request remains separate: a density probe does not
establish all density/pattern combinations. Honoured is a slicer observation,
not a strength or print qualification. No automatic profile match is claimed.
Whole-body walls/skins remain editable; modifier-only results do not govern them.

The static bundle supports opening the workspace offline without a YAML parser.
After a catalog change, run `python ui/build-capabilities.py` (requires PyYAML).
The remote browser check rejects a stale source fingerprint and checks that
ignored settings, side effects and positive-control receipts remain visible.

## Review a helper export

Open `ui/massing-review.html` from the workspace, then load the saved draft and
its `fdmgen/massing-export@0.1` receipt. Exact draft, table, mesh and pose
fingerprints must agree, and every helper must appear once. Failed checks name
the helpers and preserve suggested fixes, evidence level and provisional status.
Profile mismatch warnings stay visible. A new draft clears the previous review;
a rejected receipt preserves the last matching results with an error message.

Reopen the draft in the workspace to revise it, then export and check again.
Results never attach to unsaved edits. The review page verifies pairing, not
3MF contents, actual sliced material, interface clearance, bonding or strength.
The sample receipt in `ui/fixtures/` was generated by the Python exporter from
the committed two-helper UI draft; the 0.5 mm box deliberately fails MOD-001.

## From saved draft to project

After **Export planning draft**, the workspace opens the command handoff. A
helper with only text intent still needs its spatial box defined before the
backend can use it. Shell-only drafts need no helpers. On the compute worker,
with the matching body source checkout available, run:

```bash
fdmgen massing massing-plan.json --table TABLE.json --template PROFILE.3mf --out out/massing
```

Replace the table and template paths with your files; the exact original table
bytes must match. The template is an Orca project or a slice-evidence ZIP with
`audit.3mf`. For the example part, the source checkout can be located with
`SPOOL_RACK_ROOT`. Use a named detached job for geometry work.

The command writes the project and its JSON receipt. Exit code 2 reports a failed
check even though files were written. Open the receipt alongside the saved draft
in helper review, revise any failures, and export again. Slice the resulting
project on the second workstation; geometry checks are not toolpath evidence.

## Compare helper material with the shell-only slice

The review page accepts an optional `fdmgen/massing-slice-evidence@0.1` receipt
after the export report. Its project hash, plan provenance and full helper set
must match. The view shows project and baseline solid infill, added volume and
box fraction per helper, together with the producer's screening thresholds.
Overlapping boxes can count the same roads; do not sum them as material credit.
Without a baseline, added material stays unattributed even if the producer's
absolute-fill screen says PASS. Toolpath evidence does not establish bonding
or strength.

Slice both the exported project and its `-shell-only.3mf` companion with the
same Orca settings, automatic arrangement/orientation off, then run:

```bash
fdmgen massing-evidence REPORT.json project.gcode --baseline shell-only.gcode
```

Load the resulting `-slice-evidence.json` in review. Changing the draft or
accepted export report clears earlier slice results. A mismatched slice receipt
preserves the last matching result and displays an error. The UI verifies
recorded project/plan pairing, not the G-code bytes or baseline settings.

When recorded, project and baseline slicer settings and G-code fingerprints are
shown together. Differences in the recorded settings are flagged even if the
producer omitted its mismatch list. Such differences are not attributed to
helpers alone. Recorded hashes are provenance, not verification of G-code files.

## Return directly to a reviewed helper

**Edit [helper name]** in export or slice review opens the workspace in the
current review tab. Load the exact original orientation table; the reviewed
draft is then restored and its helper's name field receives focus. A wrong
table retains the pending draft and explains the mismatch. The other workspace
tab, saved files and receipt remain unchanged.

The handoff uses session storage in that tab and is removed after restoration
or cancellation. Browsers that block this storage show manual reopen
instructions. Only draft intent is transferred; previous check results do not
become evidence for edited geometry. Save and check the revised draft again.

The preview's **Helper to edit** selector jumps to a named region. Focusing
any helper field highlights that box with a solid blue outline and an
“Editing” label; other boxes remain dashed orange. Switching helpers cancels
an unfinished surface-placement action so a later click cannot move the old
region. These are still unclipped planning boxes, not credited material.

## Keep-out references

Tables with a top-level `keep_outs` list expose those declarations in each
helper form. Select the regions to track and inspect their rule and frame.
These selections record review intent; global keep-outs remain applicable
regardless of selection. Selection alone does not establish clearance.
References survive export/reopen and are validated against the exact table by
both the browser and Python ingestion. Unknown identifiers are rejected.

The original example table and its historical receipts remain unchanged. Use
`tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json`
for a new draft with the crown-moulding and spool-slide declarations. Existing
drafts still require their original table; they are not silently migrated.

## Worked helper revision

Load the with-keep-outs table above, then reopen
[`fixtures/revised-draft.json`](fixtures/revised-draft.json). The single backing
helper has design-frame centre `[90, -20, 12]` mm and size `[16, 10, 24]` mm.
It requests 0.5 mm clearance beyond the rear-seat cylinder and tracks both
keep-outs. Its shell is four walls and 1.6 mm skins, with no sparse infill.

This draft was exported through the browser controls. Compared with the older
two-helper negative fixture, the tiny test box is absent and the backing moves
2 mm away from the seat. A first revision kept its 20 mm thickness: the geometry
sampler reported **NOT_CHECKED** for shell contact. Extending it through the
24 mm body thickness gave 128 of 512 sampled points in the shell band.
The modelled seat-axis distance is 15.0 mm against 14.1 mm required; the crown
box and sampled spool sweep also pass their geometry checks. These are
provisional geometry observations, not proof of a continuous printed bond.

Open helper review and load that exact draft followed by
[`fixtures/revised-export-report.json`](fixtures/revised-export-report.json).
The report preserves the check scope and exact draft/table/body fingerprints.
The historical negative fixtures remain available for comparison; they use
their original table and cannot be reopened against the new table.

Then load [`fixtures/revised-slice-evidence.json`](fixtures/revised-slice-evidence.json).
The exact project and shell-only companion were sliced with Orca 2.4.2, 0.2 mm
layers, four walls, eight skin layers, 0% body infill, support off and 100%
filament shrink. Recorded baseline settings match. Inside the helper box,
solid infill is 3,565.268 mm³ versus 398.073 mm³ in the baseline: a measured
addition of 3,167.195 mm³ (about 82.5% of the box). This T-level screen passes;
it does not verify bond continuity, strength or physical printability.
The receipt records both G-code hashes and the exact project hash.

## Review a machine proposal

A saved draft can carry an additive `proposal` block from the stress seeder.
Reopen it against its exact orientation table as usual. The **Original machine
proposal** panel shows the source scope, stress fingerprint, original helper
clusters, nearest modelled restraints, rejected clusters and restraint-margin
sensitivity. Complete producer metadata remains available, including load,
material and receipt provenance when supplied. The browser does not verify the
stress file or rerun the seed.

Edits and exports preserve this block as historical provenance, with
`proposal_use=historical_provenance_requires_recheck`. The original cluster
measurements do not become evidence for changed boxes, shell settings or poses.
A `no_viable_helpers` proposal explicitly warns that an empty helper list does
not establish shell-only sufficiency. Reopening an ordinary draft or loading a
new table clears the proposal panel. These proposals are starting points for
review, not optimised designs or physical qualifications.

## Review a mechanics sensitivity

Each mechanics result row applies its own domain/load/convergence checks before
showing compliance or movement as established. A receipt marked ready/solved can
still be withheld if its detailed audit contradicts that status. Pair-only sampling
mismatches withhold the delta while leaving individually valid model rows visible.
Raw measurements remain in the complete receipt.

Withheld comparisons identify the first failed condition beside the summary and
list every blocking domain, load, restraint, convergence or seat-conservation
condition in the audit section. These explain the recorded model checks; they
do not recommend changing physical restraints to obtain a solve.

Weighted deltas also require matching sampling method metadata. Per-input source
NPZ names/hashes may differ; the remaining sampling block must match regardless
of JSON key order. Missing caps metadata remains “not recorded”, never inferred
false. The review shows the resampled fraction and original recorded fraction,
plus the full source/generator/purpose blocks for inspection. In the recorded
p1/p3 pilots these are 1/16 versus 1/3: a sampling sensitivity, not a new recorded
grid. Non-equivalence to the thresholded load-transfer pilot stays beside the delta.

The review also accepts `fdmgen/density-weighted-mechanics-pilot@0.1` receipts.
They retain their separate original-load policy and uncalibrated stiffness law
`E/E0 = min(raw_density, 1)^power`, with no stiffness floor. The page shows the
material constants, exponent, load fingerprint, raw/retained domain audits and
fragment accounting; it does not reinterpret them as thresholded load-transfer
results. The original receipt remains intact in provenance. A compliance delta
requires successful retained-domain audits, no recorded lost load or restraints,
and converged solves. The browser pairs recorded inputs; it does not rerun FE,
verify NPZ bytes, calibrate the law or establish physical movement/strength.

After loading the exact draft, export receipt and paired slice evidence, the
review page accepts a `fdmgen/seat-load-transfer-pilot@0.1` mechanics receipt.
It requires the export's project and plan hashes, both loaded slice G-code
hashes, matching recorded slicer context, and a common grid receipt. The UI
verifies recorded pairing, not NPZ or G-code contents.

The view shows domain policy, threshold, fragment removal, load audit failures,
convergence residuals, compliance and maximum movement. It computes the relative
compliance change from the recorded solves only when every domain audit,
convergence check and seat force/moment conservation screen passes. Raw blocked
receipts show **No supported compliance comparison**. A failed receipt import
retains the previous matched view with an error; changing the draft, accepted
export or accepted slice clears downstream mechanics results.

The exact seed example is `fixtures/seed-draft.json`,
`fixtures/seed-export-report.json` and `fixtures/seed-slice-evidence.json`.
Compare `../bench/receipts/occupancy-seat-transfer-r1.json` with
`../bench/receipts/occupancy-connected-sensitivity-r1.json`. The latter has an
explicit fragment-removal policy; it is not a successful solve of the unchanged
raster. Material constants absent from a receipt are labelled as unrecorded;
consult the benchmark's reproduction instructions. Occupancy sampling, grid
refinement, contact realism and physical qualification remain unresolved.

For a sensitivity comparison, load the same seed draft/export/slice and switch
the mechanics input between the threshold-0.25, 0.50 and 0.75 receipts listed in
`bench/README.md`. The recorded compliance changes are −1.387%, −2.924% and
+1.317%. These use different common nodal load sets across thresholds, and the
0.75 model predicts movements outside a physical small-displacement
interpretation. The isolated 0.50 decrease is not a robust design benefit.

The mechanics view separates **solver cell size** from **bead sampling step**.
For example, `occupancy-connected-sampling16-r1.json` reports 0.1 mm deposition
sampling on a 1.6 mm FE grid; it is not a 0.1 mm mechanics solve. Older receipts
without sampling metadata say “not recorded”. The view links the threshold and
sampling studies beside the comparison so a single percentage is not presented
as a robust design benefit.

### Recover a removed helper

Use **Undo remove** beside **Add helper region** to restore the most recently
removed helper. Up to 20 removals can be undone in reverse order, preserving
helper IDs, order, notes, interface/keep-out selections and box inputs, including
incomplete edits. The restored helper becomes active in the preview. This
history lasts only in the current browser page and resets when a different
table or saved draft is successfully loaded; a rejected draft leaves it intact.
It does not undo other edits or rerun verification. Save a draft to keep work
across page reloads.

The draft status above **Export planning draft** tracks edits since the last
reopen or download in this session. It includes pose, rationale, shell settings
and helper inputs; camera controls do not mark a draft edited. Reverting the
form, including undoing a removal, clears the edit indication when it matches
the checkpoint again. A failed export leaves the indication intact. This is
a form comparison, not autosave or evidence that a downloaded file was retained
on disk. Browser refresh still discards unsaved work.

Rejected orientation-table imports leave the last accepted table and current
draft available, including unsaved edits and helper-removal history. The import
status explains the error; it does not switch the draft to the rejected file.
A successfully loaded replacement table still starts a new plan.

**Order poses by** compares one metric at a time: conservative layer-failure
index, measured support-segment count, bed contact area or print height.
Unchecked/missing values stay last, zero remains a measured value, and ties keep
the source analysis order. Choose **Analysis order** to restore the supplied
ordering. Sorting preserves your selected pose and draft; it is not a new
combined ranking or qualification verdict. Check the selected pose's evidence
level and slicer context before interpreting a difference.

Use **Duplicate region** to start a similar helper beside the original in the
form. The copy gets a new ID and a “copy” name, retains notes, interface/keep-out
selections and raw box inputs, and becomes the active helper. Edits to it do
not affect the original. Its box initially occupies the same place, so the
workspace identifies the coincident boxes; move or resize the copy as appropriate.
Duplication copies planning intent only and does not inherit verified results.

### Review a sampled shell check

After loading matching draft, export and project-slice receipts in the helper
review, open the optional `fdmgen/shell-check@0.1` or `@0.2` receipt. It must match the
project G-code hash and selected pose. The view shows the recorded T verdict,
measured/unmeasured sample counts, thin fraction, slope bands and method inputs.
The exact archived project sample is `fixtures/seed-project-shell-check.json`.

Legacy shell receipts do not pin the table, mesh or complete producer method.
The view explicitly leaves geometry pairing unestablished for them. If table
or mesh hashes are supplied, mismatches are rejected. The checker is not rerun
in the browser; a passing sample screen does not establish an unchanged shell
everywhere, bead bonds or strength. Upstream receipt changes clear the shell
result, and a rejected shell receipt leaves the last matched result visible.

Current `@0.2` shell receipts additionally require matching table/mesh hashes,
the saved pose transform and recorded slicer settings, plus method and producer
source provenance. The original receipt is kept intact in the expanded view.
Legacy samples are never relabelled as current receipts.

`fixtures/seed-project-shell-check-current.json` is a fresh `@0.2` CLI result
from source `a3f45ed`, not a metadata upgrade of the legacy file. It reruns the
same project G-code at 0.1 mm with 20,000 samples and records the same result
(0.22% thin, no unmeasured samples). Its table, mesh, pose and slicer context
match the seed draft/export/slice fixtures. The browser test exercises this
exact receipt as well as legacy disclosure and a changed-transform rejection.

Load **Optional shell-only baseline check** to compare sampled thin fractions.
Each check must match its own recorded G-code hash and pose; comparison requires
current receipts with matching table, mesh, pose, grid, method, source hashes
and slicer context, zero clipped volume and no unmeasured samples. A legacy or
method-mismatched result remains visible but does not produce a comparison.

The paired current seed fixtures report 0.22% thin each (0 percentage-point
difference). This is aggregate sampled evidence, not proof of pointwise equal
thickness or physical shell integrity. The project receipt was independently
rerun and reproduced byte-for-byte (SHA-256 `7a7dd851…`); the baseline fixture is
the producer's unchanged receipt (SHA-256 `b7b362a8…`).

The pose list also shows an optional `t_shell_thin_fraction` column as a
percentage, retaining its recorded SHELL-001 / T verdict. The selected-pose
panel shows the producer's fidelity statement, recorded sample coverage and
complete column provenance. Missing coverage is explicitly unestablished.
Missing, unchecked or invalid fractions stay **Not checked**; a measured zero
remains visible. These are sampled toolpath screens of the recorded slice,
not checks of edits in the planning form. Compare methods and settings before
comparing fractions; the UI does not rank poses by this value automatically.

Try the new enriched table
[`spool-rack-g2-ef.with-keep-outs.shell.orientation-table.json`](../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell.orientation-table.json).
The two feasible poses record 0.22% and 0.19% thin samples, respectively, both
provisional T PASS. This small difference is not a demonstrated pose advantage.
The enriched file has a new hash: drafts pinned to the original table still
require that original file. Receipt hashes retain their original source-table
binding; enrichment does not relabel the underlying measurements.

If filters hide your selected pose, **Show selected pose** clears only the
filters excluding it and returns keyboard focus to its row. Your ordering,
selection, rationale and helper draft stay intact.

Mechanics review separately displays each input's recorded road-end/turn cap
setting. An absent setting says **not recorded**, rather than assuming caps are
disabled. The capped R1 receipt is exercised directly in the browser test. Equal
bead-sampling steps do not imply equal raster domains or transferred load arrays.

Selected poses show optional external and internal BRG-001 T columns separately:
longest unsupported run, recorded limit, verdict, fidelity and full column
coverage/provenance. Missing or invalid measurements stay Not checked. The limits
are provisional; a screen PASS does not prove absence of sag or printed strength.

Bridge coverage is visible beside the result: evaluated roads of each type,
total bridge roads, raster cell size and the longest reported cantilever.
Cantilevers are reported but not judged by this checker. Zero evaluated roads
is explicitly distinguished from a successful bridge trial; absent coverage
is not treated as complete.

The real combined example is
[`spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json`](../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json).
Facet-00 records external 3.15 mm (PASS) and internal 122.1 mm (FAIL); facet-01
records 52.2 mm and 53.95 mm (both FAIL). Limits are provisional 10 mm external
and 18 mm internal. These are toolpath-raster screens, not physical sag results.
The original pinned tables and receipt hashes are preserved.

The pose list counts recorded FAIL columns separately from bed-fit feasibility.
The selected-pose summary names each failed column, rule, evidence level and
producer explanation. Multiple columns can report the same rule (for example,
external and internal bridges); this is a column count, not a count of independent
physical defects. No recorded failures does not mean all checks were performed
or that the part is qualified.

Shell review accepts `shell-check@0.3` and displays its recorded road-containment
checks, tolerance and checked-height count. Malformed or failed placement bands
are rejected. Fewer than three checked heights remain viewable with a scope
warning and cannot establish a paired pose comparison. Mixed 0.2/0.3 receipts
also cannot establish that comparison. Older receipts retain their original
metadata and explicitly lack recorded section checks; none are relabelled.
Containment supports consistency with a pose, not unique pose identity.

When draft export rejects a missing required helper description or invalid shell,
clearance or box value, the editor focuses the first relevant field and associates
it with the error message for assistive technology. Editing clears the field's
error marker; export still runs the authoritative draft validation. No values
are filled in or repaired automatically.

The pose table scrolls within a bounded, keyboard-focusable region with sticky
column headings. **Plan this pose** sits beside the selected-pose heading, with a
link to its recorded checks. Evidence remains visible below; the action only
opens the massing controls and does not approve the pose or its checks.

The fresh real project receipt
[`seed-project-shell-check-v03.json`](fixtures/seed-project-shell-check-v03.json)
(SHA-256 `cd70f213…`, producer `7cad385`) records five containment-check heights,
the verifier source hash and the deposition offset after measured placement
correction. The browser imports these exact bytes and reports 0.22% thin samples.
It does not pair this newer receipt with a legacy baseline's weaker pose evidence.
Earlier receipt files remain unchanged.

The matching fresh baseline is
[`seed-baseline-shell-check-v03.json`](fixtures/seed-baseline-shell-check-v03.json)
(SHA-256 `fa03534d…`, same producer). Both receipts use the same grid, method,
source hashes, pose and placement correction. Their sampled thin fractions are
both 0.22%, a difference of zero percentage points; this does not establish
pointwise shell equality or printed strength. The browser checks the real pair
and retains it if a project receipt is mistakenly loaded as the baseline.

Export review starts with failed and not-checked geometry checks so that passing
rows do not bury the slice evidence. **Show export checks** reveals all checks or
one verdict, with the visible and total counts stated. Opening another matched
export resets this view to items needing attention. An empty view is explicitly
not a qualified result; complete receipts and helper editing remain available.

## Import an evidence bundle

After loading the saved draft and its export report, select `evidence-bundle.json`
and all five receipt JSON files together in **Evidence bundle**. Generate them in
a named detached job on the compute worker:

```bash
fdmgen evidence REPORT.json project.gcode shell-only.gcode --table TABLE.json --pose POSE_ID --out out/evidence
```

Keep the original filenames in one directory. The browser verifies each receipt's
bytes against the manifest, the exact loaded export report, and the recorded
table, pose and G-code identities before displaying the set. It loads helper and
shell evidence into the existing review panels and shows both bridge receipts.

A rejected bundle leaves the previous review intact. Loading an individual
slice or shell receipt clears the bundle summary, so the page does not represent
a mixed selection as the original bundle. The manifest's paired values remain
available as raw producer evidence; the shell comparison uses the page's own
pairing checks. File fingerprints establish consistency between supplied files,
not independent verification of G-code contents or physical performance.

The bundle contract/browser fixture is synthetic and explicitly labelled as
such. It uses existing receipts to exercise hash and identity gates; it is not a
receipt of a real `fdmgen evidence` run.

The separate [real seed bundle](fixtures/seed-evidence-bundle/evidence-bundle.json)
is the unchanged output of producer `f3e53da` (manifest SHA-256 `9ac51823…`).
Its five receipt hashes are checked during browser acceptance. Helper checks and
both shell screens PASS, but both bridge checks FAIL: internal strand span 122.1 mm
against the provisional 18 mm limit. The seeded helpers did not reduce this
maximum strand span. Both shell screens report 0.22% thin samples; neither equal screen
values nor successful bundle import establishes printed performance.

Review keeps draft, export report and full bundle inputs visible. Expand **Optional: load individual receipts or a mechanics pilot** for the manual route and its status messages; those controls preserve the same pairing checks.

Bundle pairing errors identify whether the export report, orientation table or
pose differs. A report mismatch directs users to its matching bundle or to rerun
`fdmgen evidence` with the current report and matching inputs. Identical 3MF bytes
do not override a bundle manifest's report fingerprint.

The review summary exposes current SHA-256 input fingerprints in an expandable panel. Draft and export-report hashes are calculated from opened bytes; table, template and project hashes are recorded provenance, not browser verification of those files. Rejected replacement reports retain the previously matched identities.

An incomplete bundle selection lists every missing receipt filename and asks for the manifest and all five receipts together. Each picker selection replaces the selected files; a rejected set leaves previously verified results intact.

Bundle import errors identify the selected filename when JSON is malformed or the document is not an object, so the damaged or unrelated file can be replaced without discarding the previous verified review.

When a bundle producer withholds paired shell or bridge deltas, review shows its
first reason in the bundle summary and the full reason list verbatim as text.
Producer-withheld shell comparisons do not display a numeric delta in the bundle
view. These manifest notes are labelled producer-reported; receipt validation
remains separate, and manifest numeric deltas are not promoted as validated results.

## Navigate the matched review

Helper names, purposes, identifiers and revision actions stay visible. Expand
**Design box, print bounds and exported settings** on an individual helper to
inspect its complete geometry/settings record without expanding the other helpers.

When helper names collide, review headings and edit actions include the stable
helper identifier. Stored names are unchanged, and revision actions still target
the matching identifier.

**Revise this draft** returns any matched export to the orientation workspace,
including shell-only plans with no helper edit buttons. Load the exact original
table to restore the saved plan; the general action focuses wall/skin controls,
while a helper's Edit button focuses that helper. The handoff preserves the draft
and does not transfer old check results as evidence for subsequent edits.

Review section buttons jump directly to export checks, helpers, slice evidence,
bundle/bridge results, shell results, mechanics and next steps. Unloaded sections
are disabled and labelled; replacing an export disables its old evidence links.
Navigation places keyboard focus on the section heading.

## Interpret bridge evidence

Bridge displays distinguish the strand span (unsupported run along an individual
road, used for the recorded verdict) from an optional ceiling span (twice the
distance to the nearest support below). They can differ substantially when the
slicer runs roads along a narrow channel. Ceiling measurements do not replace
the strand verdict, and their maxima need not come from the same road. Receipts
and orientation columns without the additive ceiling field show **not recorded**;
the UI never fills it from a newer run or interprets missing values as zero.
Physical behaviour of these different support models remains a coupon question.

The [fresh ceiling-enriched table](fixtures/ceiling/orientation-table.json)
(SHA-256 `d1f365b2…`) was generated with `f8de335` from the original shell-enriched
table and new, pose-bound bridge receipts, retained beside it. Browser acceptance
checks its exact bytes: facet-00 external strand/ceiling maxima are 3.15/2.0 mm,
internal maxima 122.1/15.678 mm; facet-01 external is 52.2 mm under both models.
These are separate maxima, not necessarily measurements of the same road. All
recorded strand verdicts remain unchanged; the smaller ceiling measurement does
not establish physical performance. Existing pinned tables and drafts are untouched.

Both bridge views label the figures as independent maxima over evaluated roads
of each type; adjacent values need not describe the same road. Draft export also
focuses a missing choice rationale, marks it invalid, and clears that marker on
edit, including for shell-only plans.

Failed BRG-001 toolpath screens now state that this workspace supplies no verified
helper-edit remedy. They retain the strand-model FAIL and link to the bracket
bridge-model investigation (#9) and coupon work (#12). This is not a claim that
helpers can never improve a bridge; a changed design needs new slices and checks,
and physical behaviour remains a separate question.

Bridge failure guidance links directly to the [owner decision record](https://github.com/thereprocase/fdm-design-toy/issues/17#issuecomment-6049963530),
including bracket infill policy and coupon printing. That navigation does not
change the recorded strand verdict or establish a helper-edit remedy.

## Compare and select poses

Pose buttons retain keyboard focus after selection. Use Tab or Shift+Tab to move
between them, and Enter or Space to select; selection updates the detail panel
without moving focus away from the comparison table.

Use **Use selected pose as reference** to keep one pose beside subsequent choices
in **Side-by-side measurements**. This compares recorded strength, geometry,
support, shell and bridge values without calculating a winner. Expand each
cell's Context to inspect its method and settings; unchecked values stay unchecked.
The reference survives filtering, but clears when a new table is accepted. It is
view state only: the selected pose remains the one saved in the planning draft.

The pose table includes print height beside its shell and fit results, so sorting
by height leaves the compared measurement visible. Missing heights remain
**Not checked** and sort after measured values; sorting does not choose a pose.

Pose filters display the producer's declared feasibility scope as text, or state
that it was not supplied. Only explicit true flags pass the feasible-only filter;
missing flags read **Fit not recorded**. Other check verdicts remain independent.

Bed fit (BED-001) has its own pose-table column, separate from combined feasibility
(BED-001 plus BED-002 in the bracket tables). A pose can fit the bed while failing
contact/stability. Missing or unchecked bed-fit evidence stays **Not checked**;
the producer's geometric fidelity note is retained on the cell.

The pose identifier column stays visible while scrolling horizontally through
comparison metrics, including on narrow screens. Its selected-row highlight and
keyboard selection remain available beside the far-right fit results.

An empty pose filter offers **Show all poses**. It clears visibility filters while
keeping sort order, selected pose and draft fields. Keyboard focus returns to the
selected row, or the first row without selecting it when no pose was chosen.

Pose measurements below 0.001 in magnitude use scientific notation instead of
rounding a nonzero value to zero. Exact zero remains zero. This changes display
formatting only; source values, sort order and exported evidence remain intact.

The material-corner range is withheld when either corner is explicitly
**NOT_CHECKED**, even if the producer retained a numeric value. Individual values
and the summary therefore agree about missing evidence; raw data is preserved.

**Review selected pose** beside the comparison controls moves to the selected
pose's evidence and planning action. It preserves the current choice and draft,
and places keyboard focus on the detail heading. It is disabled until selection.

Reference pose comparisons include supplementary bridge ceiling maxima beside strand maxima. These are independent per-measure maxima, potentially on different roads; the strand verdict remains authoritative for the recorded screen. Missing ceiling measurements remain explicitly unrecorded.

## Edit and navigate helpers

Interface selectors have expandable declarations with recorded model, axis,
support restriction and frame, plus the complete source dimensions. Absent
frame metadata is labelled rather than inferred. Opening a declaration changes
no draft fields and does not establish clearance; inspect KEEP-CLEAR after export.

Box helpers have **Move X/Y/Z** controls with an explicit step in millimetres
(0.1, 0.4, 1 or 5). They move the centre in the design frame and preserve box size
and references. **Undo last centre move** restores the previous coordinates;
typing a centre clears that undo to avoid restoring
an obsolete position. Incomplete centres must be filled first. Moves update the
preview and draft only; export and geometry checks are still required.

Typing a centre, moving it with the axis controls or undoing a move cancels any
pending surface-pick action. A subsequent viewer click cannot replace that
position unless **Place centre on part** is selected again.

Each helper editor can be folded while its name remains visible. **Show only
selected helper** closes the other editors; **Expand all helpers** restores them.
Folding changes presentation only: every helper remains in the preview and draft,
and it does not mark the plan edited. Selecting a helper from the preview or
focusing an export error opens the relevant editor automatically.

Successful surface placement also supports **Undo last centre move**. The previous
coordinate text is restored exactly, including blank fields; an unsuccessful pick
does not overwrite this one-step history. Another successful pick or axis move
replaces the history with that move's starting centre. Undo does not rerun checks.

The helper-planning entry repeats the selected pose and its design-frame build
direction, recorded fit/stability status and failed-check count. It identifies the
pose that will be saved, independently of any pinned comparison reference. The
recorded checks still describe the source analysis, not subsequent helper edits.

Planning warnings include **Edit** buttons for their affected helper(s). These open
the editor, highlight its box and focus its centre controls; a thin-edge warning
focuses the undersized dimension instead. Navigation preserves all draft values
and does not rerun geometry or sliced-evidence checks.

Helper box centre coordinates and dimensions have separate labelled design-frame groups.
They remain separate on narrow screens, so a centre coordinate never shares a row
with a size field. The spatial browser check covers desktop/mobile ordering and
unchanged draft data across layout changes.

**Add helper** selects the new region and brings its name field into view with
keyboard focus, including on narrow screens. Existing helper fields are retained.

**Return to helper** reopens a folded editor and reveals its centre field. For a
helper without an enabled box, it focuses the name instead. Navigation preserves
the draft; keyboard/mobile browser checks cover both cases.

Helpers with identical display names receive a temporary “helper N” suffix in
the selector, editor legends, preview and warning actions. N is their current
list position, not their stable identifier. Saved names and identifiers remain
unchanged; the suffix disappears when names become distinct.

Add, duplicate and undo-remove actions focus and reveal the helper name, including on small screens. Duplicate and Remove choose their resulting selection on activation, so button focus does not shift the controls during a pointer click. Undo still preserves incomplete field values and the helper’s original position.

## Control the geometry preview

Surface placement can be stopped with **Cancel placement** beside the preview
or **Escape**, leaving helper coordinates and draft edits unchanged. A completed
pick closes the mode. Changing pose, replacing the mesh or draft, removing a
helper, turning off its box or choosing shell-only also closes pending placement.

The preview's Design axes indicator rotates with the pose and camera, matching
helper centre/nudge coordinates. A circled dot indicates an axis toward the viewer;
a circled cross points away. The bed remains the print Z=0 plane. In top view,
print Z points toward the viewer rather than upward on screen.

The design-axis indicator is a noninteractive overlay: clicking or dragging it
does not place helper centres or rotate the part. Cancelled pointer gestures do
not leave a pending surface click.

**Print +X side** and **Print +Y side** look toward the part from the respective
positive print axis, with print Z upward on screen. These presets help inspect
helper depth. Like Top view and Angled view, they reset zoom and change only the
camera; the selected print pose and helper coordinates remain unchanged.

While surface placement is armed, an orbit gesture stays a drag once it travels
at least four screen pixels from its press point, even if it returns there before
release. It leaves placement armed for a subsequent deliberate click.

Preview orbit and placement gestures use the primary pointer's primary button.
Right/middle clicks and secondary contacts do not change the camera or helper
centre. A gesture belongs to its initiating pointer and ends on release,
cancellation or loss of pointer capture.

The preview labels only the active helper by default to keep dense proposals
readable. **Show all helper labels** restores every name when needed. All valid
box outlines remain visible either way; this viewing preference does not change
the draft or exclude helpers from export.

**Focus helper** frames the active valid box without changing its geometry or print
pose. Orbit and zoom then operate around that box. **Show whole part** restores
part framing while keeping the viewing direction; preset views also restore it.
Changing the active helper or disabling its box ends focused framing.

The preview scale bar reports millimetres in the orthographic view plane and
updates with zoom and helper framing. It is a viewing aid, not a surface-distance
measurement. Its inset, like the axis compass, does not accept placement clicks.

The preview draws the declared rectangular bed at print Z=0 using the table
producer's corner-origin convention. Its dimensions are labelled; absent/invalid
dimensions retain a labelled reference-plane cue. This does not recalculate fit:
a valid positive margin is drawn as a dashed inset labelled BED-001 margin;
exclusion zones are not drawn, and BED-001 remains the recorded result.

## Save inputs and recover rejected imports

The workspace asks before a valid replacement table or saved draft discards edits
since the last open/download checkpoint. Cancel preserves the current form,
including incomplete numeric fields. Invalid incoming files leave it intact
without a discard prompt. Browsers that support departure warnings also warn
before leaving an edited plan. This is not autosave: export the draft to keep it.

Draft downloads use the part and pose identifiers, for example
`spool-rack-g2-ef-facet-00-massing-plan.json`. Filename segments use safe ASCII
letters, digits and hyphens, limited to 64 characters each, with `part`/`pose`
fallbacks. Names help identify files; exact content hashes still control receipt
pairing. Repeated downloads can have the same suggested name.

The export handoff offers **Download exact source table**. This saves the accepted
input bytes unchanged, including a UTF-8 BOM or formatting, so the saved draft's
source fingerprint remains valid. It does not save draft edits. A rejected table
upload leaves the previously accepted table available. After draft export, the
CLI example uses the suggested draft and table names; adjust paths or names if
your browser renames a repeated download, and supply your own profile template.
The table filename includes a short fingerprint for recognition; verification
continues to use the full SHA-256 hash.

The handoff continues through both exported 3MF files: slice the helper project
and shell-only baseline using the same Orca build and settings, with automatic
arrangement and orientation off. Run the displayed `fdmgen evidence` command
against those two G-codes, the exporter report and exact table. It writes a
manifest and five receipts; select all six together in helper export review after
loading the saved draft and report. Evidence exit 2 means recorded FAIL results;
exit 1 means an error without a completed manifest. Toolpath checks do not replace
physical qualification. Generated commands fill ordinary part/pose identifiers;
unusual identifiers remain explicit placeholders to replace with exact paths.

The handoff identifies commands as belonging to the last downloaded draft and
warns when current edits are absent from that download. Reopening a draft,
including a review handoff, clears previous export filenames and geometry-input
summaries. Export again to populate them, or replace the template paths with
your existing saved files.

Provided helper identifiers must match the exporter contract: 1–80 lowercase
ASCII letters, digits, underscores or hyphens, beginning with a letter or digit,
and unique within the draft. Invalid imported identifiers are reported before
replacing the current plan; they are not silently renamed. Display names remain
free text. Generated helper identifiers already meet this rule.

Current-format draft imports must explicitly record a boolean shell-only choice
and a helper list. A shell-only draft containing helpers is rejected rather than
silently discarding them. The current form remains available after rejection.
Deliberately choosing Shell only in the editor still exports an empty helper list;
legacy free-text-note migration retains its separate behavior.

Orientation imports validate each candidate's finite rotation/translation and
build direction before replacing the current session. Rotations must be proper
(no scaling, shear or reflection), and must lift the build direction to print +Z,
using the planning backend's 1e-8 tolerance. Invalid tables report the candidate
and preserve the existing draft. This checks the pose contract, not mesh fit or
physical printability.

A rejected STL replacement retains the previously fingerprint-matched mesh and
camera view, with an explicit rejection message. The rejected file is never
displayed. Accepting a new orientation table still clears the old mesh.

When a saved draft requires another source table, the import error names its
full required fingerprint and the suggested exact-table download filename.
Renaming another table cannot satisfy that fingerprint; current edits remain
available while the correct source is located.

### Optional keep-out geometry preview

The preview accepts `fdmgen/keepout-render@0.1` JSON generated by
`fdmgen keepout-render TABLE.json --problem problem.yaml --out keepouts.json`. It requires exact table
and mesh fingerprints, design-frame millimetres and the recorded installed-to-design
identity. Per-constraint toggles show magenta wireframes through the body without
changing helper references, saved drafts, camera framing or body-surface picking.
The current box is clipped for display; the flange sweep draws sampled discs with
finite Z extents. Full clipping, original bounds and sampling provenance remain
available. Neither drawing establishes clearance. Failed imports retain the prior
matched geometry; accepting another table clears it.

For the example root table, use
`tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.keepout-render.json`.

Enabled keep-out IDs remain labelled below the canvas when their import panel is
closed. **Hide keep-outs** clears the visible overlays, keeps the geometry loaded,
and returns keyboard focus to the preview. It does not change helper references
or the saved draft. Re-enable individual constraints in the optional preview panel.

Editing from an export-check row carries a **Previous review note** into the
workspace after the exact table restores the draft. It retains the original
rule, message, measurements and recorded report fingerprint, explicitly as a
past result that has not been rerun on edits. The note never enters the saved
draft; dismissing it or successfully opening another draft/table clears it.

The pose slice filter includes usable SHELL-001 or BRG-001 toolpath results,
even when no support-count column is supplied. Missing support counts remain
**Not checked**; finding shell or bridge evidence never implies zero supports.
Unchecked or malformed shell/bridge columns do not satisfy the filter.

The previous-check note appears immediately after the targeted helper name.
Review handoff scrolls the focused name field into view rather than centring the
whole helper editor, which can be taller than the screen. Dismissing the note
returns focus to that helper; opening another draft/table clears the note.

### Orientation evidence bundle import

The opening screen accepts a complete `fdmgen/orient-evidence@0.1` bundle in one
file selection: manifest, enriched table and both receipts per pose. Hashes,
pose/G-code/root-table/mesh bindings and the table's receipt-linked measurements
are checked before the shared table loader and unsaved-draft guard run. A failed
or cancelled import retains the current draft and previous bundle summary.
Manual table replacement clears the prior bundle summary. The exact enriched
bytes remain downloadable; drafts pinned to the original table are not migrated.

To rerun `orient-evidence`, use the original root table before shell/bridge
enrichment. An enriched download already contains those pose receipts and is
refused as input to another batch. Use that download for drafts and massing
exports created from the enriched workspace.

The real two-pose example is in `ui/fixtures/orient-evidence/`. Both bridge FAIL
receipts remain visible. File verification is not physical qualification or an
independent check of the recorded G-code/source hashes. See the [batch workflow](WORKFLOW.md#open-an-orientation-evidence-batch).

Pose comparison shows recorded slice kinds beside shell and bridge values. Mixing
a helper-project slice with a shell-only slice triggers an explicit uncontrolled-
comparison note; the recorded values remain visible. Missing kinds stay unrecorded.
Equal kinds alone do not establish matching geometry or slicer settings.

The helper-review bundle upload status separates fingerprint verification from
receipt outcomes (FAIL, NOT_CHECKED and PASS counts). These count receipts, not
individual measurements or physical qualifications. Revision uses the exact table
pinned by the draft, including an enriched table when that is where it was made.

Bundle bridge review starts with a compact project/shell-only table of recorded
verdicts and independent strand/ceiling maxima. Missing ceiling measurements stay
Not recorded; zero evaluated roads stay explicit. Producer-withheld comparisons
are labelled before the individual values. No helper-effect delta is inferred;
full methods, limits, failure context and receipts remain below.
