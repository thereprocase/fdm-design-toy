"""Generate problems/spool-rack-g2-ef/problem.yaml from pinned sources (PLAN D15: never retyped).

Loads and interface positions come from the bracket adapter (ported interface_loads, P0-G parity);
the process comes from the handoff's selected-layout.json; requirements are quoted from the G2 brief.
Every source file is pinned by sha256 so `fdmgen lint` can tell when the source moved on.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from ..adapters import spool_bracket as sb

SOURCE_REPO = "spool-wall-rack"
ROOT_ENV = "SPOOL_RACK_ROOT"
G = sb.TOTAL_LOAD_N / 12.0           # 117.72 N is 12 kg, so the brief's g is 9.81 m/s^2
ONE_SPOOL_KG = 1.25                  # G2-BRIEF.md: "one 1.25 kg spool"
LAYOUT = f"{sb.HANDOFF}/selected-layout.json"
MOULDING = "designs/rev-g2/shape-seeds/moulding-clearance.json"
CONTRACT = "designs/rev-g2/INTERFACE-CONTRACT.md"
PINNED = ("G2-BRIEF.md", CONTRACT, LAYOUT, MOULDING,
          f"{sb.HANDOFF}/body-mounted.stl", f"{sb.HANDOFF}/body-only.stl")


def keep_outs(root: Path) -> list[dict]:
    """Keep-outs from the pinned sources: geometry only where the source gives it as data."""
    import re
    m = json.loads((root / MOULDING).read_text(encoding="utf-8"))
    x0, x1 = m["minimum_locating_underside_X_interval_mm"]
    spool = re.search(r"^\| Spool clearance \| (.+?) \|\s*$", (root / CONTRACT).read_text(encoding="utf-8"), re.MULTILINE)
    return [
        {"id": "crown_moulding", "type": "box", "frame": "installed",
         "min_mm": [float(x0), None, None], "max_mm": [float(x1), float(m["locating_underside_Y_mm"]), None],
         "rule": m["below_moulding_top_rule"], "structural_support": "none", "source": MOULDING},
        {"id": "spool_slide", "type": "not_derived", "frame": "installed",
         "rule": spool.group(1).strip() if spool else None, "source": CONTRACT,
         "note": "the flange sweep envelope is not derived from the contract text yet; checks report NOT_CHECKED"},
    ]


def _forces(total_N: float) -> list[dict]:
    return [{"at": k, "N": [float(x) for x in v]} for k, v in sb.interface_loads(total_N).items()]


def load_cases() -> list[dict]:
    """The load cases, in the design (installed) frame, straight from the ported adapter."""
    return [
        {"id": "full", "frame": "installed", "total_N": sb.TOTAL_LOAD_N, "gravity_dir": [0.0, -1.0, 0.0],
         "split_model": "radial seat pressure, zero axial moment (ported interface_loads)",
         "forces": _forces(sb.TOTAL_LOAD_N)},
        {"id": "one-spool-delta", "frame": "installed", "total_N": ONE_SPOOL_KG * G, "gravity_dir": [0.0, -1.0, 0.0],
         "split_model": "same split at the one-spool load",
         "note": "the brief requires a new load/contact solve for this case; proportional scaling is insufficient",
         "forces": _forces(ONE_SPOOL_KG * G)},
    ]


def build(root: str | Path) -> dict:
    root = Path(root)
    layout = json.loads((root / LAYOUT).read_text(encoding="utf-8"))
    layer_mm = 0.2
    skin_layers = round(layout["skin_mm"] / layer_mm)
    if not np.isclose(skin_layers * layer_mm, layout["skin_mm"]):
        raise ValueError(f"skin {layout['skin_mm']} mm is not a whole number of {layer_mm} mm layers")
    files = [{"path": f, "sha256": hashlib.sha256((root / f).read_bytes()).hexdigest()} for f in PINNED]
    seats = [{"id": k, "type": "rod_seat", "axis": "Z", "center_xy_mm": list(xy), "seat_radius_mm": list(sb.SEAT_RADIUS),
              "role": "interface", "support": "forbidden", "roof_variant": "teardrop_auto"}
             for k, xy in sb.ROD_AXES_I.items()]
    mounts = [{"id": f"mount_{k}", "type": "screw_clearance", "axis": "X", "center_yz_mm": list(yz),
               "d_mm": 2 * sb.MOUNT_BORE_R, "washer_plane_x_mm": sb.WASHER_PLANE_X, "role": "interface",
               "support": "forbidden"} for k, yz in sb.MOUNT_AXES_I.items()]
    return {
        "schema": "fdmgen/problem@0.1",
        "id": "spool-rack-g2-ef",
        "part": "spool-wall-rack G2 bracket, E+F solid brace core handoff",
        "generated_by": {"generator": "fdmgen.problem.spool_bracket.load_cases",
                         "command": "fdmgen problem spool-bracket",
                         "source": {"repo": SOURCE_REPO, "commit": sb.SOURCE_COMMIT, "root_env": ROOT_ENV,
                                    "files": files}},
        "refs": {"material": "polymaker-polylite-asa-t0", "calibration": "p1s-0.4-polylite-asa-cal-2026-10",
                 "catalog": "v0"},
        "frames": {"design": "installed",
                   "installed": "X out from the wall (wall plane X = 0), Y up, Z along the rods",
                   "print": "derived per orientation candidate; the handoff pose is a 180 deg turn about Z"},
        "geometry": {"body": {"path": f"{sb.HANDOFF}/body-mounted.stl", "frame": "installed", "role": "fixed body (P2)"},
                     "helpers": list(sb.HELPERS)},
        "interfaces": seats + mounts,
        "keep_outs": keep_outs(root),
        "load_cases": load_cases(),
        "supports": [
            {"id": "wall", "type": "unilateral_contact", "face": "X=0",
             "solver_gate_model": "bilateral roller u_x = 0"},
            *({"id": f"mount_{k}_restraint", "at": f"mount_{k}", "type": "washer_axial_and_bore_lateral",
               "solver_gate_model": "bore surface clamped"} for k in sb.MOUNT_AXES_I),
        ],
        "process": {"settings": {"layer_height": layer_mm, "wall_loops": int(layout["walls"]),
                                 "top_shell_layers": skin_layers, "bottom_shell_layers": skin_layers,
                                 "sparse_infill_density": f"{layout['infill_percent']}%"},
                    "helpers": "100 % modifier volumes", "source": LAYOUT},
        "requirements": [
            {"metric": "bracket_movement_mm", "load_case": "full", "max": 4.0, "modulus_basis": "sustained_effective",
             "source": "G2-BRIEF.md: 5 mm total, 1 mm provisionally reserved for rails/mounts"},
            {"metric": "movement_change_mm", "load_case": "one-spool-delta", "max": 1.0,
             "modulus_basis": "sustained_effective", "source": "G2-BRIEF.md"},
            {"metric": "fracture_factor", "min": 4.0, "basis": "material_card (design corner)",
             "source": "G2-BRIEF.md: nominal fracture factor of at least four"},
        ],
        "service": {"sustained_F": 85, "brief_loaded_F": 100, "source": "G2-BRIEF.md"},
        "infill": {"base_density": 0, "credited": False, "reason": "PLAN D12: sparse infill is never credited"},
        "support_policy": {"default": "forbidden", "regions": []},
        "rule_overrides": [{"rule": "WALL-003", "value": {"min_walls": 2}, "reason": "G2 hard requirement"}],
    }


def write(root: str | Path, path: str | Path) -> dict:
    d = build(root)
    header = ("# GENERATED by `fdmgen problem spool-bracket` from pinned sources; do not edit by hand.\n"
              "# Regenerate it, then run `fdmgen lint` on it. CC BY 4.0.\n")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + yaml.safe_dump(d, sort_keys=False, width=110), encoding="utf-8")
    return d
