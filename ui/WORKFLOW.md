# Plan a print orientation and its reinforcement

Open [the orientation workspace](index.html) in Chromium. This local workspace
reads your files and saves planning drafts. Geometry export, slicing and analysis
run separately on a compute worker; the browser does not run those jobs.

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
**Expand all helpers** opens them again.

## Inspect the geometry

The design-axis indicator follows the pose and camera, matching the helper
coordinate controls. A circled dot points toward you; a circled cross points away.
**Print +X side** and **Print +Y side** look from those positive print axes, with
print Z upward on screen. **Top view** looks from print +Z. Camera changes do not
change your print pose or draft.

Orange dashed boxes and the highlighted helper are unclipped planning regions.
Their displayed volume is not credited material. The ground rectangle marks
print Z=0; it is not a bed-fit test. Size, gap and bounding-box warnings are planning
screens. Exporter checks, sliced evidence and physical testing remain separate.

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
   table and selected pose. It runs helper material, shell and pose-bound bridge
   checks, writing `evidence-bundle.json` and five receipt files. Exit 2 records
   one or more FAIL results; exit 1 means an error without a completed manifest.

A written file or zero exit code does not establish physical qualification.
Changing the draft requires a new export and new evidence for that export.

## Review and revise

Open [helper export review](massing-review.html). Load the saved draft and exporter
report first. Then select the manifest **and all five receipt JSON files together**
from the evidence output folder. Fingerprints must pair before results are shown.
Read failed and unchecked results, their scope, coverage and method context.

Use **Revise this draft**, or a helper's revision action, to return to planning.
Load the original table when prompted. Revise the intent, export a new draft and
repeat the export/slice/evidence loop. Old receipts remain evidence for their
original inputs; they do not verify the revised plan.

For schema details, evidence limits and test-worker instructions, see the
[technical UI guide](README.md).
