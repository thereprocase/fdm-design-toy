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

`keep_clear` now stores validated `interface_ids`, empty `keep_out_ids`, optional
`clearance_mm`, and a human `note`. Unknown interface IDs are rejected. Older
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
