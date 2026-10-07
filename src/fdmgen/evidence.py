"""One evidence bundle for a massing round trip: every T-level receipt for a project slice and its shell-only
baseline, written next to a manifest that pins them all.

The bundle runs the existing commands (massing-evidence, shell-check, bridge-check), so each receipt has
exactly the format and checks of the command that wrote it. The manifest adds what no single receipt can:
the inputs by sha256, every receipt's sha256 and verdict, and the paired project-minus-baseline deltas.
Paths in the manifest are relative to the bundle directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "fdmgen/evidence-bundle@0.1"


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(argv: list[str]) -> int:
    from .cli import main
    return main(argv)


def build_bundle(report: Path, project_gcode: Path, baseline_gcode: Path, table: Path, pose: str, out_dir: Path, *,
                 shell_cell_mm: float = 0.1, shell_samples: int = 20000, bridge_cell_mm: float = 0.1) -> dict:
    """Run every T-level check on both slices into out_dir and return the manifest (also written there).

    Raises RuntimeError when a command errors (exit 1); a FAIL verdict (exit 2) is recorded, not raised.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "evidence-bundle.json"
    manifest_path.unlink(missing_ok=True)          # a failed run must not leave an earlier bundle looking current
    slices = {"project": Path(project_gcode), "shell-only": Path(baseline_gcode)}
    jobs = [("massing-evidence", "project", "massing-evidence.json",
             ["massing-evidence", str(report), str(slices["project"]), "--baseline", str(slices["shell-only"])])]
    for kind, g in slices.items():
        jobs.append(("shell-check", kind, f"{kind}.shell-check.json",
                     ["shell-check", str(g), "--table", str(table), "--pose", pose, "--cell", str(shell_cell_mm),
                      "--samples", str(shell_samples)]))
        jobs.append(("bridge-check", kind, f"{kind}.bridge-check.json",
                     ["bridge-check", str(g), "--table", str(table), "--pose", pose, "--cell", str(bridge_cell_mm)]))
    receipts = []
    for check, kind, name, argv in jobs:
        dest = out_dir / name
        code = _run(argv + ["--out", str(dest)])
        if code == 1 or not dest.is_file():
            raise RuntimeError(f"{check} on the {kind} slice failed (exit {code}); no bundle written")
        rec = json.loads(dest.read_text(encoding="utf-8"))
        receipts.append({"check": check, "slice_kind": kind, "path": name, "sha256": _sha(dest),
                         "schema": rec.get("schema"), "verdict": _verdict(check, rec)})
    by = {(r["check"], r["slice_kind"]): json.loads((out_dir / r["path"]).read_text(encoding="utf-8")) for r in receipts}
    manifest = {
        "schema": SCHEMA,
        "pose": pose,
        "inputs": {"report_sha256": _sha(report), "table_sha256": _sha(table),
                   "gcode_sha256": {k: _sha(g) for k, g in slices.items()}},
        "receipts": receipts,
        "paired": _paired(by),
        "establishes": "Which T-level checks this project slice and its shell-only baseline pass, each pinned by "
                       "hash, and how the helpers change the shell and bridge measurements.",
        "does_not_establish": "Anything at P level (printed parts), or for a different slice, pose or body.",
    }
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    tmp.replace(manifest_path)                     # written whole or not at all
    return manifest


def _verdict(check: str, rec: dict) -> str:
    if check == "massing-evidence":
        verdicts = [h["verdict"] for h in rec["helpers"]]
        return "FAIL" if "FAIL" in verdicts else ("PASS" if verdicts and all(v == "PASS" for v in verdicts) else
                                                  "NOT_CHECKED")
    return rec["result"]["verdict"]


SLICER_KEYS = ("generator", "version", "printer_model", "print_settings_id", "filament_settings_id", "layer_height",
               "wall_loops", "sparse_infill_density", "filament_shrink", "enable_support", "extruder_offset_mm")


def _pairing_problems(check: str, p: dict, b: dict) -> list[str]:
    """Why two receipts of one check may not be differenced; empty when they may."""
    from .orient.table import MIN_POSE_BANDS
    bad = [f"{k} differs" for k in ("pose", "table", "mesh", "method", "source_sha256") if p.get(k) != b.get(k)]
    bad += [f"slicer {k} differs" for k in SLICER_KEYS if p["gcode"].get(k) != b["gcode"].get(k)]
    for name, r in (("project", p), ("shell-only", b)):
        bands = (r.get("placement") or {}).get("bands") or []
        if len(bands) < MIN_POSE_BANDS:
            bad.append(f"{name} slice checked against the pose at {len(bands)} heights (< {MIN_POSE_BANDS})")
    if check == "shell-check":
        gp, gb = p["grid"], b["grid"]
        bad += [f"grid {k} differs" for k in ("frame", "origin_mm", "cell_mm", "shape") if gp.get(k) != gb.get(k)]
        for name, r in (("project", p), ("shell-only", b)):
            if r["grid"]["clipped_outside_grid_mm3"] != 0:
                bad.append(f"{name} raster clipped {r['grid']['clipped_outside_grid_mm3']} mm3")
            if r["result"]["metrics"]["unmeasured"] != 0:
                bad.append(f"{name} has {r['result']['metrics']['unmeasured']} unmeasured samples")
    return bad


def _paired(by: dict) -> dict:
    """Project minus baseline for the measurements both slices have, only when the two receipts are comparable
    (same pose, table, mesh, method, source and slicer context, both pose-checked, and for the shell the same grid
    with full coverage); otherwise every reason the delta is withheld."""
    out = {}
    for check, metric_keys in (("shell-check", ("thin_fraction",)),
                               ("bridge-check", ("max_span_external_mm", "max_span_internal_mm"))):
        p, b = by[(check, "project")], by[(check, "shell-only")]
        bad = _pairing_problems(check, p, b)
        if bad:
            out[check] = {"withheld": bad}
            continue
        mp, mb = p["result"]["metrics"], b["result"]["metrics"]
        out[check] = {k: {"project": mp[k], "shell-only": mb[k], "delta": round(mp[k] - mb[k], 6)} for k in metric_keys}
    return out
