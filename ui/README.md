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

Current limits: no helper geometry editor yet. Planning exports are drafts. The
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

Planning drafts now use `fdmgen.massing-plan.v0.2`. Each requested helper has a
name, location, load purpose and interface/clearance constraints. Shell-only is
an explicit option. Geometry is not created by these intent records. Changing
shell or helper settings does not recompute the source analysis.

Reopen a draft after loading its original orientation table. The exact table
SHA256 must match; stale/other-table drafts are rejected without replacing the
current plan. Reopened evidence comes from the loaded table, not from copied
metrics in the draft. v0.1 free-text helper notes are retained as one region;
location and clearance fields must be completed before exporting v0.2.

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
