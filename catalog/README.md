# Printability rule catalog (v0)

Machine-checkable printability rules for FDM parts, as data. Licensed CC BY 4.0 (see `LICENSE-docs.md`).
Source: the master table and rule cards in [`research/final/frodo.md`](../research/final/frodo.md) §3,
with the plan's decisions applied ([`PLAN.md`](../PLAN.md) D5, D13).

| Path | What |
|---|---|
| `rules/<ID>.yaml` | one rule per file (`fdmgen/rule@0.1`), stable IDs |
| `calibration/*.yaml` | calibration bindings (`fdmgen/calibration@0.1`): rule values tied to slicer-profile hashes |

## Conventions
- **Angle:** α is the slope from horizontal. A flat underside is 0°, a vertical wall 90°. Reports say
  "50° (40° from vertical)".
- **Numbers:** every parameter has a `unit` and an evidence `tag`: U own print, S slicer behaviour,
  V vendor or slicer documentation, L literature, H heuristic placeholder, `derived`, `precedent`
  (a design value never print-tested), `policy` (an owner decision), `logic`. Unitless or untagged
  numbers fail the lint. True ratios use unit `'1'`.
- **Status:** a value is PROVISIONAL until a coupon or print calibrates it. A heuristic (H) value can
  never be CALIBRATED.
- **Bindings:** a calibration binding pins machine, process and filament profile hashes. It is BOUND
  when all match the profiles in use, STALE when any differs, UNBOUND while a hash is unknown. Only a
  BOUND binding's values can carry CALIBRATED.
- **Levels:** V density field, M mesh (or its per-layer sections), T real Orca toolpaths, P physical
  coupon. A result reports the level it reached, and T overrides M overrides V.
- **Verdicts:** PASS, FAIL, NOT_CHECKED (the check could not run as specified), NOT_CALIBRATED. A PASS on
  a provisional value is shown as `PASS (PROVISIONAL)`. NOT_CHECKED is never counted as PASS.
- Material strengths are not catalog data: they live in the material card.

## Rule count
The plan and issue #9 say 33 rules; the master table in `research/final/frodo.md` §3.1 lists 35. All 35
are here. Why the counts differ is not recorded; nothing was dropped to match the smaller number.

## Checkers implemented (v0)

| Rule | Level | Method | Known-answer tests |
|---|---|---|---|
| OVH-001 | V | 5-point cross support stencil, one layer down; reports the grid's worst-azimuth angle | stencil angle table from `research/final/sauron.md` §4.7; overhanging step |
| OVH-001 | M | per-triangle slope of downward faces, bed faces excluded, islands by shared vertex | 45° wedge fails, 55° passes, 50° passes |
| WALL-001 | M | per-layer opening with a 2w disc; corner residue within 0.5 r ignored | 0.6 mm fin fails, 1.2 mm fin passes, square block passes |
| GAP-001 | M | the same on the void phase | 0.5 mm slot fails, 1.2 mm slot passes, L-corner passes |
| BRG-001 | M | 2 × max distance from air-borne pixels to supported pixels of the same layer | 12 mm bridge fails at 10 mm, 8 mm passes, floating slab fails |
| PROC-001 | T | declared settings vs the G-code CONFIG_BLOCK or 3MF `project_settings.config` | synthetic config with one mismatch and one missing key |

The wedge fixtures are generated in the tests from their defining angles rather than copied from the
owner's sliced test wedges; the slice evidence for the 45°/55° threshold is cited in
`research/final/sauron.md` §4.7 and is tier S (what Orca does), not P1S print quality.

## What v0 does not do
- No T-level overhang, bridge or width checks yet (they need the G-code parser, issue #2).
- No repair passes, no V-level width filter: those belong to the optimiser.
- The calibration binding's profile hashes are not pinned yet, so every bound value reports UNBOUND.
