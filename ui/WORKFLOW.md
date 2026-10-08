# Plan a print orientation and its reinforcement

Open [the orientation workspace](index.html) in Chromium. This local workspace
reads your files and saves planning drafts. Geometry export, slicing and analysis
run separately on a compute worker; the browser does not run those jobs.

## Try the included example

For a first walkthrough, use the existing [example orientation table](../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json)
and its [six-helper planning draft](fixtures/seed-draft.json) from your checkout.
The JSON links open the files for inspection; they are not a download/import action.
Keep their bytes unchanged: the draft pins this exact table, not the later shell- or
bridge-enriched tables.

1. In **Orientation table**, select
   `tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json`.
2. In the planning section, use **Reopen a saved planning draft** to select
   `ui/fixtures/seed-draft.json`.
   Its pose, rationale, shell and six helper boxes are restored together.
3. Inspect the proposal's scope and helper purposes before editing. This is a
   stress-seeded candidate, not a proven optimum or qualified print.

The files let you review pose evidence and edit helper fields without loading a
mesh. For the 3D preview, supply the matching `body-mounted.stl` from the part
source checkout; the JSON files do not include the STL. The workspace checks
its fingerprint. This example does not download or generate geometry for you.

### Try the sliced-pose example

To inspect measured shell and bridge checks instead, open **Or open a complete
orientation evidence bundle** and select all six JSON files in
`ui/fixtures/orient-evidence-roads/` together. Keep the files unchanged. This is a
separate example from the seed draft above: it opens an enriched table with a
different fingerprint, so that older draft cannot be reopened against it.

1. Choose **Review facet-01** in the verified bundle summary.
2. Under **Recorded checks needing review**, use **Locate recorded strand** for
   the external bridge. It opens the preview's location controls and selects the
   recorded 52.2 mm strand maximum, with keyboard focus on that choice.
3. Load the matching body STL to draw the road. Selecting a road before the mesh
   is loaded retains the selection. The dashed line is the full road and the
   solid segment is the unsupported run; both are drawn through the body.
4. Compare **facet-00**. Changing pose clears the previous road; select that
   pose's internal strand to inspect its recorded 122.1 mm maximum.
5. To start a new draft from this enriched table, choose a pose and use
   **Plan this pose**. Keep its exact table with the exported draft. To reopen
   the older six-helper draft instead, return to its original table above.

Both poses retain bridge FAIL results. These are provisional toolpath checks;
locating a road does not establish a helper remedy or physical printability.
The workspace does not change helper geometry when you select a road.

## Choose a pose

1. Load the orientation table produced by `fdmgen orient`. Read what its evidence
   establishes and what remains unverified.
2. Load the matching STL in **Part mesh and viewing help**. The workspace checks
   its fingerprint before showing it. The mesh stays attached to the selected
   design-to-print transform.
3. Select pose buttons to inspect their checks. **Show feasible poses only**
   filters the producer's fit/stability result; it does not mean every check
   passes. Missing measurements remain **Not checked**.
4. To compare alternatives, select one and press **Use selected pose as reference**.
   Select another to see their measurements side by side. Expand each cell's
   **Context** to compare methods and settings. The reference is only a viewing
   aid; the selected pose is the one saved in your draft.
5. Record **Why choose this pose?**, then press **Plan this pose**.

Tab and Shift+Tab move between pose buttons; Enter or Space selects one.
Filters can hide the selected pose without changing it; **Show selected pose**
reveals it again. Bridge strand and ceiling maxima can come from different roads.
A numerical ordering or a passed slicer check is not print qualification.

## Plan the shell and helpers

Set **Perimeter walls** and **Top / bottom skin**. Choose **Shell only** explicitly
if you want no helper regions in this draft. Helpers request 100% infill; sparse
infill receives no structural credit. Otherwise, give each helper a name,
location, load-carrying purpose and interface constraints. Select the applicable
interface and keep-out references, and enter the required clearance when known.
**Select all interfaces** records every declared interface for that helper; you can
uncheck individual entries. KEEP-CLEAR runs only for selected interfaces. A blank
clearance is exported as unspecified, which the exporter evaluates with **0 mm
extra clearance**: the helper must stay outside the modelled interface, with no
extra gap. Enter a value to require a gap. Unselected interfaces are not checked.
The live summary states the selected count and this default;
it does not establish clearance, printed fit or assembly access.
Part keep-outs can be drawn with the optional table-pinned geometry import (see below). Expand each constraint to read its
rule, declared frame and model; inspect the exporter’s KEEP-OUT results after
export. A visible helper box does not establish clearance.
**Add helper** selects the new region and focuses its name, ready for typing.

Directly below the helper name, enable **Place a box-shaped planning region**
to specify its centre and size. These coordinates are in the **design frame**; they stay attached to the
part when you choose a different print pose.

- **View this helper** brings its framed preview into view without entering
  placement mode or changing coordinates. It requires a matched mesh and valid
  box. Use **Return to helper controls** to resume editing, especially on a phone.
- **Place centre on part** picks a surface point. Adjust the centre and size to
  extend the helper into the body as intended. Picking a surface does not prove
  bonding or clearance.
- **Cancel placement** or Escape exits picking without moving the helper.
- **Move centre by** and the axis buttons move along design X/Y/Z.
- **Undo last centre move** reverses the latest nudge or successful surface pick,
  restoring the previous coordinate text, including blanks. **Redo centre move**
  restores an undone placement. A fresh move clears redo; typing a coordinate
  clears both histories for that helper. Up to 20 nudges and successful picks
  can be undone and redone during this editing session. When the focused Undo or
  Redo button runs out of moves, focus switches to the reverse action. A move
  refused because a centre coordinate is incomplete focuses that field.
- The dimension controls show **unclipped box volume** to compare sizes. This
  is not credited material or a print estimate: body clipping, overlaps and the
  existing shell are not deducted. Sliced evidence is needed for material changes.
- **Undo dimension edit** and **Redo dimension edit** recover box sizes, including
  arrow-key changes and incomplete fields. Typing in one field is one edit; up to
  20 edits are kept per helper. Centre moves use their own history.
- **Duplicate region** copies its fields into an independently editable helper.
  **Undo remove** restores a removed helper while that removal history remains
  in this session.

Use **Helper to edit** beside the preview to select and highlight a region.
**Show only selected helper** folds the other editors without removing their data;
**Expand all helpers** opens them again. **Return to helper controls** reopens the
selected editor and focuses its centre, or its name if no box is enabled.
An **Edit** button beside a planning warning takes you to the affected helper;
undersized-edge warnings focus the dimension that needs attention. Invalid-box
warnings focus the actual blank or invalid coordinate or dimension, opening a
collapsed editor when necessary.

Helper spacing warnings distinguish a box-to-box gap from a small overlap. For
overlap they name the design axis with the least overlap (zero means touching).
These are measurements of the unclipped planning boxes against the nominal
0.84 mm screen, not checks of body bonding or the sliced toolpaths. Use either
helper’s **Edit** button to inspect its position before choosing a change.

## Inspect the geometry

To inspect a small region, select it with **Helper to edit** and press **Focus
helper**. Orbit and zoom now centre on that box. **Show whole part** restores the
overview without changing the viewing direction; the preset view buttons also
restore whole-part framing. Changing the selected helper or disabling its box
ends focused framing. Only the selected helper is labelled by default; **Show all
helper labels** reveals the other names when needed.

The design-axis indicator follows the pose and camera, matching the helper
coordinate controls. A circled dot points toward you; a circled cross points away.
**Print +X side** and **Print +Y side** look from those positive print axes, with
print Z upward on screen. **Top view** looks from print +Z. Camera changes do not
change your print pose or draft.

Orange dashed boxes and the highlighted helper are unclipped planning regions.
Their displayed volume is not credited material. The ground rectangle shows the
declared bed at print Z=0, with the print origin at a bed corner. Without bed
dimensions it is only a labelled reference plane. A dashed inset shows the declared
BED-001 margin when available. Exclusion zones are not drawn; use the recorded
bed-fit check. Size, gap and bounding-box warnings are planning
screens. Exporter checks, sliced evidence and physical testing remain separate.

If a replacement STL is rejected, the previously matched mesh and camera remain
available. The viewing-help panel opens with the error and identifies the retained
mesh. Loading a new orientation table clears that preview; load its matching STL.

## Save the exact inputs

Press **Export planning draft**. Missing required fields are focused for correction.
The suggested name identifies the part and pose. In the opened handoff panel,
press **Download exact source table** to keep the original table bytes beside it.
The draft pins those exact bytes, including formatting; resaving the table as
new JSON can change its fingerprint.

A saved draft can still contain helpers described only in words. The handoff lists
those missing boxes and offers **Edit box for …** actions that focus each helper's
placement toggle. The action does not enable geometry or fill in coordinates.
Define the boxes and export again before running the geometry exporter. These
links describe the last exported draft; removing a helper or choosing shell-only
mode disables its old action.

Download an updated draft after editing. The edit indicator tracks changes since
opening or downloading a draft; it is not autosave. Replacing a table/draft or
leaving the page with edits prompts you first. Reopen a saved draft only after
loading its original table. Downloading the table alone does not save draft edits.

If the draft belongs to another table, the error supplies its full required
fingerprint and the suggested `orientation-table-<fingerprint-prefix>.json`
filename. Locate the table saved alongside that draft. The complete bytes must
match: renaming or reformatting another table cannot repair the pairing. A rejected
import leaves current edits intact; save them before accepting a different table.

## Export, slice and collect evidence

The handoff panel fills the commands with suggested download names where possible.
Adjust them to the actual paths on your worker, especially if the browser renamed
a repeated download. Run long work in a named detached job on the compute worker.
Use the second workstation for slicing. **Select massing command** and **Select
evidence command** select the complete visible command and focus it for your
system Copy action (Ctrl+C or ⌘C). They do not copy automatically or run a job;
replace the remaining placeholder paths before execution.

1. Run the displayed `fdmgen massing` command with the saved draft, exact table and
   an Orca-written template `.3mf` (or the supported slice-evidence archive).
   The matching part source checkout must be adjacent to the repository or set
   through `SPOOL_RACK_ROOT` for the bracket adapter. The exporter writes a helper
   project, a shell-only baseline and a report. Exit 2 means a geometry check
   failed: inspect the report and revise the affected helper.
2. Slice **both** 3MFs using the same Orca build and printer, filament and process
   settings. Turn automatic arrangement and orientation off. Retain the original
   project files and the corresponding project and shell-only G-codes.
3. Run the displayed `fdmgen evidence` command with the report, both G-codes, exact
   table and selected pose. This worker also needs the matching part source
   checkout (or `SPOOL_RACK_ROOT` for the bracket adapter): shell and bridge checks
   load the body mesh. It runs helper material, shell and pose-bound bridge checks,
   writing `evidence-bundle.json` and five receipt files. Exit 2 records
   one or more FAIL results; exit 1 means an error without a completed manifest.

If evidence exits 1, read the terminal line naming the failed check and slice
(for example, `bridge-check on the project slice failed`) and the preceding error.
Check the matching body source checkout or `SPOOL_RACK_ROOT` on that worker;
confirm the G-codes came from the exact exported projects with automatic
arrangement and orientation off; and check the exact table bytes and project/baseline
pairing. Correct the inputs and rerun the full evidence command. Partial receipt
files alone are not a completed bundle. Exit 2 instead means a completed bundle
contains FAIL results to inspect.

A written file or zero exit code does not establish physical qualification.
Changing the draft requires a new export and new evidence for that export.

## Review and revise

Open [helper export review](massing-review.html). Load the saved draft and exporter
report first. Then select the manifest **and all five receipt JSON files together**
from the evidence output folder. Fingerprints must pair before results are shown.
Read failed and unchecked results, their scope, coverage and method context.
The review page’s **Next steps** section repeats the full bundle command. Its
optional helper-material command produces only the sliced-helper receipt; it
does not replace the shell and bridge checks in a full bundle.
If a paired comparison is withheld, read the first reason in the bundle summary
and the complete producer-reported list below it. Resolve the stated input or
context mismatch before trying to interpret a numerical change.

A strand-model bridge FAIL has no verified helper-edit remedy in this workspace.
Follow the adjacent investigation, coupon and owner-decision links for the bracket
infill/printing questions. A smaller ceiling-model span does not override that
FAIL; adding helpers does not establish a fix.

Use **Revise this draft**, or a helper's revision action, to return to planning.
Load the exact table pinned by this draft when prompted; its SHA-256 is listed in
**Current input fingerprints**. A draft made from an enriched table requires that
enriched table, not the root table used to generate orientation evidence.
Revise the intent, export a new draft and
repeat the export/slice/evidence loop. Old receipts remain evidence for their
original inputs; they do not verify the revised plan.

For schema details, evidence limits and test-worker instructions, see the
[technical UI guide](README.md).

### Review the mechanics example

Open [Helper review](massing-review.html). This example reads an existing CPU
analysis; it does not start a solve or qualify the draft for printing.

1. In **Saved planning draft**, select `ui/fixtures/seed-draft.json`.
2. In **Massing-export receipt**, select `ui/fixtures/seed-export-report.json`.
3. Expand **Optional: load individual receipts or a mechanics pilot**. In
   **Optional sliced-helper evidence**, select `ui/fixtures/seed-slice-evidence.json`.
4. In **Optional mechanics pilot receipt**, select
   `bench/receipts/occupancy-density-p1-h08.json`.
5. Choose **Mechanics** in the review navigation. Check the model and its scope
   before interpreting the reported **−1.798%** compliance change.

Here, lower compliance means less load-weighted deformation in the stated model.
It is not a strength margin. The model uses the 0.8 mm grid, all positive-density
cells, no fragment removal, and all original loads and 7,216 fixed degrees of
freedom (restrained displacement components). Its assumed stiffness is linear
in capped density; that law is uncalibrated. Predicted displacements are not
validated physical movement. The complete source receipt remains available below
the displayed results.

The seed slices were re-rasterised at a deposition sampling step of h/12
(about 0.067 mm), rather than the original h/3. This refines deposition within
the 0.8 mm solver cells; it does not make a 0.067 mm FE grid. Each input's
sampling block records the resampling and its original source; separate h/3
controls exist. Check these blocks before comparing receipts with different
sampling steps.

To inspect the nominal anisotropic material model on the **same grid and density
law**, select `bench/receipts/occupancy-ti-density-p1-h08.json` in the mechanics
input. It reports **−1.706%**. The physical model is transversely isotropic, using
the T0 card's `sustained_effective` basis: in-plane E 1,000 MPa, through-layer E
870 MPa, and through-layer G 278.4 MPa. Its isotropic auxiliary preconditioner
only helps solve those equations; it does not make the physical model isotropic.
This comparison changes the whole constitutive tensor, including Poisson ratios,
and is not a sweep of material uncertainty or evidence of physical strength.

For a contrasting audit, select
`bench/receipts/occupancy-connected-sensitivity-r1.json` in the same input. The
older thresholded model retained only 1,978 of 2,071 original restrained components.
The review now withholds its comparison even though the historical receipt says
ready/solved. Read the specific reason and original/retained counts rather than
treating a successful solver status as sufficient evidence. This is a different
grid, domain and load policy; the two results are not a controlled grid-refinement
comparison. Changing the draft requires new matching evidence.

### Locate a failing bridge on the body

After loading a matched review and its evidence bundle, choose **Saved geometry**
in the review navigation. Load the exact body STL recorded by the draft. The
preview shows the saved pose and helper boxes, without changing the draft.

1. Open **Locate a worst bridge road**.
2. Choose **Helper project** or **Shell-only baseline** to match the slice you
   want to inspect. The matching shell check must already be loaded, either from
   the bundle or through the individual receipt controls.
3. Select that slice's pose-bound bridge receipt. The page checks its G-code,
   pose and geometry context against the loaded shell check, then validates the
   recorded location coordinates.
4. Choose an external/internal strand or ceiling maximum. Use **Top** or
   **Isometric**, then orbit or zoom to inspect its position. **Hide road** removes
   the overlay without discarding the receipt.

The dashed line is the full road; the solid segment is its longest bounded
unsupported run. A dot marks the ceiling model's farthest unsupported point.
They are drawn through the body to make the location visible. Strand and ceiling
maxima can come from different roads. “External” and “internal” are slicer role
labels, not proof of open air or a hollow core; location alone does not establish
that a helper can fix the failure. Read the selected road's context and the
**Location source receipt** alongside the picture.

To try the exact checked example, load `ui/fixtures/seed-draft.json` and
`ui/fixtures/seed-export-report.json`, then all six JSON files in
`ui/fixtures/seed-evidence-bundle/`. Select **Shell-only baseline** and open
`ui/fixtures/bridge-locations/facet-00-shell-only.bridge-check.json`. Its
**internal strand · 122.1 mm** button locates the long road near the mount face.
Use the matching body STL from the part source checkout. The newer location
receipt does not replace the older bundle's measurements or hashes.

Older bridge receipts can lack location geometry. For your own slice, generate a
fresh receipt on the compute worker with the current checker:

```bash
fdmgen bridge-check shell-only.gcode --table TABLE.json --pose POSE_ID --out out/bridge-location.json
```

Use the exact G-code, table and pose paired with the loaded shell check; use the
project G-code instead when inspecting **Helper project**. The worker needs the
matching part source checkout (or `SPOOL_RACK_ROOT` for the bracket). Exit 2 means
the completed receipt contains a FAIL to inspect. Exit 1 means no new receipt was
written: read the terminal error for the cause. Common causes include a missing
part checkout or a slice that does not verify as the requested pose (the wrong
G-code, or automatic arrangement/orientation during slicing). The current checker
clears the requested output before work, so an earlier receipt at that path is
removed even if the new check fails. Use a fresh output filename to preserve
existing evidence. Keep old receipt files intact;
a new optional location receipt does not repair or reissue an existing bundle.
A missing-location message leaves the old measurements readable without an
invented overlay.

### Preview keep-outs while placing helpers

On the geometry worker, run `fdmgen keepout-render TABLE.json --problem problem.yaml --out keepouts.json`
with the exact orientation table and matching part checkout. In the preview,
open **Optional: preview part keep-outs**, select this JSON, and enable the
constraints you want to see. Load the matching STL and select a pose first.
Magenta dashed lines show constraints through the body; orange/blue boxes remain
helper intent. These toggles do not add references to helpers or change the draft.

The moulding box is bounded for display, and spool sweeps show sampled discs,
not the envelope between samples. Expand the provenance for original unbounded
axes, clipping, frame and sampling. Use exporter KEEP-OUT results for clearance;
a drawing is not a check. Changing tables clears this optional geometry.

### Locate interface models while placing helpers

On the evidence worker, generate a sidecar for the exact table open in the browser:

```sh
fdmgen interface-render TABLE.json --problem PROBLEM.yaml --out interface-render.json
```

The worker needs the matching part source checkout (or `SPOOL_RACK_ROOT` for the
bracket adapter). The problem must explicitly declare the supported frame
relationship. Exit 1 leaves no output file; read the terminal error. Generating
this file does not run a clearance check.

Open **Optional: locate interface models** beside the part preview and load the
sidecar. Choose which interfaces to draw, then load the matching STL and select a
pose. Blue dash-dot cylinders show the base models used by KEEP-CLEAR: the largest
seat radius for a rod seat, or the clearance-bore radius for a screw. They do not
include any helper’s requested extra clearance. Mount washers and driver access
are not modelled. End rings are drawing clips of an axially unbounded model, not
physical bore ends.

In a helper’s settings, **Show selected interfaces on part** displays only that
helper’s selected references using the loaded base models. If a required file is
missing, it takes you to the interface or mesh loader. It does not include the
helper’s extra clearance. With no selected references, it hides the overlays.

Drawing an interface does not select it in a helper’s keep-clear references, move
a helper or record a PASS. Use the exporter’s KEEP-CLEAR results to check the
selected references and requested gaps. **Hide interface models** clears the
view without changing the draft. Wrong-table or malformed sidecars leave the
previously matched overlay intact; opening another table clears it.

### Open an orientation evidence batch

On the geometry worker, use the original root table that defines the sliced poses,
before shell/bridge enrichment. Feeding an enriched table back into
`orient-evidence` is refused because those pose columns already contain receipts:

```sh
fdmgen orient-evidence TABLE.json \
  --slice facet-00 shell-only facet-00.gcode \
  --slice facet-01 shell-only facet-01.gcode \
  --out out/orientation-evidence
```

Use your actual pose IDs and G-code paths. Each pose accepts one slice, labelled
`shell-only` or `project`; do not mix the two within one pose. The worker needs the
matching part checkout (or `SPOOL_RACK_ROOT` for the bracket). Preserve the exported
pose when slicing, with automatic arrangement and orientation off. Exit 2 means a
completed batch contains a FAIL; exit 1 means an error and no completed manifest.
Partial receipts alone are not a completed batch.

In the orientation workspace, open **Or open a complete orientation evidence
bundle** and select all output JSON files together: the manifest, enriched table,
and two receipts per pose. The workspace checks hashes and bindings before loading
the enriched table. Invalid input or cancelled replacement preserves current edits.
Use each **Review POSE** button to inspect that pose's results. The batch does not
rank or qualify poses; unsliced poses remain unchecked for these measurements.

The enriched table has its own byte fingerprint. A draft pinned to the original
table still requires that original table; this route does not migrate old drafts.
Use **Download exact source table** in the export handoff section for drafts and
massing exports made from the enriched workspace. Keep the original root table
for rerunning `orient-evidence`; the enriched download does not replace that input. Recorded G-code/source hashes are provenance; the browser does not
open those inputs or rerun the checks.

## Pause with incomplete helper inputs

Use **Save unfinished work → Download work snapshot** if dimensions or required
notes are still incomplete. Beside that button, use **Download matching source
table** and keep both files together. This downloads the original table bytes;
it does not save current form edits. To resume,
open that table first, then **Reopen work snapshot**. The snapshot preserves raw
inputs for the selected pose and all helpers, including original proposal metadata.
Comparison rationale notes for other poses are saved too (older snapshots may
contain only the selected pose’s note; the reopen status says so). The pinned
comparison pose is restored alongside the selected planning pose. Older snapshots
without a comparison reference reopen unpinned. Pinning is a view choice; it does
not change the exported planning draft. The snapshot does not
save meshes, receipts or undo history, and is not
an input to `fdmgen massing`. Finish the form and **Export planning draft** before
following the CLI steps. No checks run when a snapshot is saved or reopened.
