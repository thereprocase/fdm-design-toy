# Orientation and massing workspace

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

The orientation-table contract is being implemented in `fdmgen.orient`.
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
