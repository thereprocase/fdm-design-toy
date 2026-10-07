# Arc-fitting parity fixture (P0-B, issue #2)

Two Orca 2.4.2 slices of the same part: a cylinder 16 mm in diameter and 2 mm tall, with 180 facets. It is
centred on the bed at (128, 128), with 2 walls and the seed shell-only project's process and filament
settings. The two projects differ only in the process key `enable_arc_fitting`, which is 0 for `no-arc.gcode`
and 1 for `arc.gcode`. Both were sliced through the CLI with arrange and orient off and an isolated data
directory.

| file | sha256 | arc moves (G2/G3) |
|---|---|---|
| `no-arc.gcode` | de596a5bb076414c7adec84fdd28bc84be682d4cb1bb53dd757aba4408d64b1b | 8 (outside the object) |
| `arc.gcode` | a19db2cca02d7446052272fd8d301dad84b7f3411ef7a9aacb4af154fa30037d | 348 |

Project hashes: no-arc `4c70cc3c…`, arc `79107798…`. They were written with `fdmgen.slicer.threemf.write_project`.
