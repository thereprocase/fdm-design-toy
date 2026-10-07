"""Inter-layer failure prescreen F_L over build directions (PLAN D9, research/final/sauron.md 3.2).

F_L = sqrt((<sigma_n>+ / Z_t)^2 + (tau / S_il)^2) on the layer plane, whose normal is the build
direction d. sigma_n = d . sigma . d, tau = |sigma . d - sigma_n d|, <x>+ = max(x, 0). Linear in load,
even in d (F_L(d) = F_L(-d)). One stress field serves every direction (the analytic traction map).
Stress input: the NPZ written by bench/export_bracket_stress.py (schema v1): centres_mm (N, 3),
stress_mpa (N, 6) Voigt xx yy zz yz xz xy, cell_volume_mm3 (N,), plus cell_indices and solid_mask.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

VOIGT = ((0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1))


@dataclass
class StressField:
    centres: np.ndarray        # (N, 3) mm, frame given by `frame`
    stress: np.ndarray         # (N, 6) MPa, Voigt xx yy zz yz xz xy
    volume: np.ndarray         # (N,) mm3
    frame: str = "installed"
    meta: dict | None = None

    @classmethod
    def load(cls, path) -> StressField:
        z = np.load(Path(path), allow_pickle=False)
        missing = {"centres_mm", "stress_mpa", "cell_volume_mm3"} - set(z.files)
        if missing:
            raise ValueError(f"{path}: stress export is missing {sorted(missing)} (expected schema v1)")
        s = np.asarray(z["stress_mpa"], float)
        if s.ndim != 2 or s.shape[1] != 6:
            raise ValueError(f"{path}: stress_mpa must be (N, 6) Voigt xx yy zz yz xz xy, got {s.shape}")
        meta = {k: z[k].tolist() for k in z.files if k not in ("centres_mm", "stress_mpa", "cell_volume_mm3",
                                                                 "cell_indices", "solid_mask") and z[k].size < 64}
        return cls(np.asarray(z["centres_mm"], float), s, np.asarray(z["cell_volume_mm3"], float), meta=meta)


def tensor(voigt) -> np.ndarray:
    v = np.asarray(voigt, float)
    T = np.empty(v.shape[:-1] + (3, 3))
    for k, (i, j) in enumerate(VOIGT):
        T[..., i, j] = T[..., j, i] = v[..., k]
    return T


def interlayer_index(stress_voigt, d, Z_t: float, S_il: float):
    """Per-cell F_L, sigma_n and tau for layer-plane normal d (any frame, consistent with the stress)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    t = tensor(stress_voigt) @ d
    sn = t @ d
    tau = np.linalg.norm(t - sn[..., None] * d, axis=-1)
    return np.sqrt((np.maximum(sn, 0.0) / Z_t) ** 2 + (tau / S_il) ** 2), sn, tau


def weighted_quantile(x, w, q):
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, q * cw[-1])])


def prescreen(field: StressField, directions, Z_t: float, S_il: float, X_t: float | None = None) -> list[dict]:
    """For each direction: max and volume-weighted 99th-percentile F_L, and where the max sits."""
    out = []
    vm = None
    if X_t is not None:
        s = field.stress
        vm = np.sqrt(0.5 * ((s[:, 0] - s[:, 1]) ** 2 + (s[:, 1] - s[:, 2]) ** 2 + (s[:, 2] - s[:, 0]) ** 2)
                     + 3 * (s[:, 3] ** 2 + s[:, 4] ** 2 + s[:, 5] ** 2))
    for d in directions:
        f, _, _ = interlayer_index(field.stress, d, Z_t, S_il)
        k = int(np.argmax(f))
        row = {"F_L_max": float(f[k]), "F_L_p99": weighted_quantile(f, field.volume, 0.99),
               "F_L_max_at_mm": field.centres[k].round(2).tolist()}
        if vm is not None:
            row["F_P_max"] = float(vm.max() / X_t)     # in-layer index: orientation independent
        out.append(row)
    return out
