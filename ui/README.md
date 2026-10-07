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

Current limits: no geometry viewer or helper geometry editor yet. The table
consumer has been exercised with synthetic schema-shaped data in Chromium
(desktop and 390 px mobile): import, selection, unchecked metrics, feasible
filter, exported source hash, invalid input, and no browser console errors.
Integration with a generated real orientation table is still required.
