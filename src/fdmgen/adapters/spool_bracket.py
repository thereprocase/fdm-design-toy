"""Adapter for the spool-wall-rack G2 bracket (read-only; never writes into that repo).

Frames (PLAN D1 frame table):
  installed I: X out from the wall (wall plane X = 0), Y vertical, Z across the bracket / along the rods
               (INTERFACE-CONTRACT.md, spool-wall-rack@14338e9).
  print P:     the plate frame of the handoff meshes (bed at Z = 0). For this bracket, printed flat on its
               side, P = R I + t with R a proper rotation among the 24 axis-aligned ones. R and t are DERIVED
               from the two meshes (installed vs plate) and verified both ways to 1e-3 mm; for the E+F handoff
               this gives a 180-degree turn about Z, t = (250, 182, 0): a translation-only assumption is wrong
               and would put the loads in the wrong place and direction. Forces rotate with R.

Loads are generated from the ported source, never retyped (PLAN D15).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SOURCE_COMMIT = "14338e9"
HANDOFF = "designs/rev-g2/print-controls/ef-core-asa-4w-1p6"
HELPERS = ("dense-chords-and-seats", "central-rib-plane", "local-transition-backing", "direct-brace-core")
TOTAL_LOAD_N = 117.72          # 12 kg, as the reference interface precheck
ROD_AXES_I = {"rear_seat": (90.0, 0.0), "front_seat": (190.0, 12.0)}   # (X, Y), axes along Z
SEAT_RADIUS = (12.4, 13.6)     # effective rail radius interval 12.4-12.7 mm plus the seat skin
MOUNT_AXES_I = {"upper": (164.0, 12.0), "lower": (40.0, 12.0)}          # (Y, Z), axes along X
MOUNT_BORE_R = 2.6             # 5.2 mm screw clearance
WASHER_PLANE_X = 3.6


def interface_loads(total: float) -> dict:
    """Ported from spool-wall-rack@14338e9:analysis/rev-g2/solve_plastic.py (interface_loads).
    Seat forces in the installed frame [N] for a total vertical load `total` [N]."""
    span = np.hypot(100, 12)
    rise = np.sqrt((90 + 12.4) ** 2 - span ** 2 / 4)
    cx, cy = 140 - 12 * rise / span, 6 + 100 * rise / span
    a, b = cx - 90, 190 - cx
    den = a * (cy - 12) + b * cy
    horizontal = total * a * b / den
    rear = total * b * cy / den
    front = total * a * (cy - 12) / den
    return {"rear_seat": np.array([-horizontal, -rear, 0.0]),
            "front_seat": np.array([horizontal, -front, 0.0])}


@dataclass
class Bracket:
    root: Path                      # spool-wall-rack checkout
    R_I_to_P: np.ndarray            # p = R i + t
    t_I_to_P: np.ndarray

    @classmethod
    def load(cls, root: str | Path) -> "Bracket":
        import itertools

        import trimesh
        from scipy.spatial import cKDTree

        root = Path(root)
        d = root / HANDOFF
        mi = trimesh.load(d / "body-mounted.stl")
        mp = trimesh.load(d / "body-only.stl")
        tp = cKDTree(mp.vertices)
        best = None
        for perm in itertools.permutations(range(3)):
            for signs in itertools.product((1, -1), repeat=3):
                R = np.zeros((3, 3))
                for r, (c, sg) in enumerate(zip(perm, signs)):
                    R[r, c] = sg
                if np.linalg.det(R) < 0:
                    continue  # proper rotations only: a print cannot mirror the part
                a = mi.vertices @ R.T
                t = np.round(mp.bounds[0] - a.min(axis=0), 4)
                err = max(tp.query(a + t)[0].max(), cKDTree(a + t).query(mp.vertices)[0].max())
                if best is None or err < best[0]:
                    best = (err, R, t)
        err, R, t = best
        if err > 1e-3:
            raise ValueError(f"no rigid axis-aligned map between installed and plate meshes (best {err:.2e} mm)")
        return cls(root, R, t)

    def mesh(self, name: str = "body-only"):
        import trimesh
        return trimesh.load(self.root / HANDOFF / f"{name}.stl")

    def to_print(self, p_installed) -> np.ndarray:
        return np.asarray(p_installed, float) @ self.R_I_to_P.T + self.t_I_to_P

    def vec_to_print(self, v_installed) -> np.ndarray:
        return np.asarray(v_installed, float) @ self.R_I_to_P.T

    def loads_print(self) -> dict:
        """Seat forces rotated into the print frame (installed values from the ported source)."""
        return {k: self.vec_to_print(v) for k, v in interface_loads(TOTAL_LOAD_N).items()}


def problem_dict(br: Bracket) -> dict:
    """The problem definition (PLAN D13/D15 schema sketch), all values from pinned sources."""
    loads = br.loads_print()
    return {
        "part": "spool-wall-rack G2 bracket, E+F solid brace core handoff",
        "source": {"repo": "spool-wall-rack", "commit": SOURCE_COMMIT, "handoff": HANDOFF},
        "frames": {"installed_to_print": {"R": br.R_I_to_P.tolist(), "t_mm": br.t_I_to_P.tolist(),
                                          "verified_tol_mm": 1e-3}, "print_z": "bed normal"},
        "process": {"printer": "P1S", "nozzle_mm": 0.4, "walls": 4, "top_bottom_layers": 8, "layer_mm": 0.2,
                    "base_infill": 0.0, "helpers": "100 %", "infill_credit": False},
        "design": {"body": "body-only.stl (frozen in P2)", "design_field": "100 % helper density inside the body",
                   "existing_helpers": list(HELPERS)},
        "loads_print_N": {k: v.tolist() for k, v in loads.items()},
        "loads_installed_N": {k: v.tolist() for k, v in interface_loads(TOTAL_LOAD_N).items()},
        "load_total_N": TOTAL_LOAD_N,
        "interfaces": {"rod_axes_installed_XY": ROD_AXES_I, "mount_axes_installed_YZ": MOUNT_AXES_I,
                       "mount_bore_radius_mm": MOUNT_BORE_R, "washer_plane_x_mm": WASHER_PLANE_X},
        "restraint_model": "SOLVER-GATE SIMPLIFICATION: mounting bore surfaces clamped, wall face X=0 roller "
                           "(u_x = 0, bilateral); the truth model uses washer/bore restraints and unilateral wall contact",
    }


def write_problem(br: Bracket, path: str | Path) -> None:
    Path(path).write_text(json.dumps(problem_dict(br), indent=1))
