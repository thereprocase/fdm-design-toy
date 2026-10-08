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
Part keep-outs are not drawn in the preview. Expand each constraint to read its
rule, declared frame and model; inspect the exporter’s KEEP-OUT results after
export. A visible helper box does not establish clearance.
**Add helper** selects the new region and focuses its name, ready for typing.

Enable **Place a box-shaped planning region** to specify a helper's centre and
size. These coordinates are in the **design frame**; they stay attached to the
part when you choose a different print pose.

- **Place centre on part** picks a surface point. Adjust the centre and size to
  extend the helper into the body as intended. Picking a surface does not prove
  bonding or clearance.
- **Cancel placement** or Escape exits picking without moving the helper.
- **Move centre by** and the axis buttons move along design X/Y/Z.
- **Undo last centre move** reverses the latest nudge or successful surface pick,
  restoring the previous coordinate text, including blanks. Typing a coordinate
  clears this one-step history.
- **Duplicate region** copies its fields into an independently editable helper.
  **Undo remove** restores a removed helper while that removal history remains
  in this session.

Use **Helper to edit** beside the preview to select and highlight a region.
**Show only selected helper** folds the other editors without removing their data;
**Expand all helpers** opens them again. **Return to helper controls** reopens the
selected editor and focuses its centre, or its name if no box is enabled.
An **Edit** button beside a planning warning takes you to the affected helper;
undersized-edge warnings focus the dimension that needs attention.

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
Use the second workstation for slicing.

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
Load the original table when prompted. Revise the intent, export a new draft and
repeat the export/slice/evidence loop. Old receipts remain evidence for their
original inputs; they do not verify the revised plan.

For schema details, evidence limits and test-worker instructions, see the
[technical UI guide](README.md).
