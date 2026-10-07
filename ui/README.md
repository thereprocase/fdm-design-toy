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
