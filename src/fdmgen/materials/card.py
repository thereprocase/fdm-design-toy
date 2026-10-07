"""Material card schema `fdmgen/material@0.1`: load, lint, stiffness per basis, strength corners.

A card is transversely isotropic (TI) about print z. It carries:
- a tier: T0 datasheet + assumptions, T1 own coupons, T2 demonstrator-validated;
- per-value provenance (evidence tag U/S/V/L/H/derived/policy) and, for assumed values, an interval;
- two modulus bases for E_p: `short_term` (strength work, ratios) and `sustained_effective` (movement
  gates). The anisotropy ratios are shared by both bases, which is itself an assumption;
- strengths at two Z_t corners (vendor ratio, 0.5 X_t) and an S_il/Z_t interval. Design uses the
  conservative corner until coupons exist.
Positive definiteness is checked at the nominal values and at every corner of the stiffness intervals.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from ..fem.element import ti_C

SCHEMA = "fdmgen/material@0.1"
TIERS = ("T0", "T1", "T2")
TAGS = {"U", "S", "V", "L", "H", "derived", "policy", "precedent"}
BASES = ("short_term", "sustained_effective")
RATIOS = ("E_z_over_E_p", "nu_p", "nu_pz", "G_z_over_E_z")


def materials_root() -> Path:
    return Path(__file__).resolve().parents[3] / "catalog" / "materials"


def pd_reasons(E_p, E_z, nu_p, nu_pz, G_z) -> list[str]:
    """Why a TI constant set is not positive definite (empty list = it is).

    Conditions for the compliance used by ti_C: E_p, E_z, G_z > 0, |nu_p| < 1 and
    1 - nu_p - 2 nu_pz^2 E_z / E_p > 0 (research/final/sauron.md section 2.3).
    """
    out = []
    if E_p <= 0 or E_z <= 0:
        out.append(f"moduli must be positive (E_p = {E_p}, E_z = {E_z})")
    if G_z <= 0:
        out.append(f"shear modulus must be positive (G_z = {G_z})")
    if not -1 < nu_p < 1:
        out.append(f"in-plane Poisson ratio must lie in (-1, 1), got nu_p = {nu_p}")
    if E_p > 0 and E_z > 0:
        disc = 1 - nu_p - 2 * nu_pz ** 2 * E_z / E_p
        if disc <= 0:
            out.append(f"1 - nu_p - 2 nu_pz^2 E_z/E_p = {disc:.4g} <= 0: nu_pz = {nu_pz} is too large for "
                       f"nu_p = {nu_p} and E_z/E_p = {E_z / E_p:.3g}")
    return out


@dataclass
class Card:
    id: str
    data: dict
    path: Path | None = None

    @property
    def tier(self) -> str:
        return self.data["tier"]

    def _ratio(self, name: str, corner: dict | None) -> float:
        if corner and name in corner:
            return float(corner[name])
        return float(self.data["moduli"][name]["value"])

    def constants(self, basis: str, corner: dict | None = None) -> dict:
        """TI constants (MPa) on one modulus basis; `corner` overrides any ratio by name."""
        if basis not in BASES:
            raise ValueError(f"unknown modulus basis {basis!r}; use one of {BASES} and say which in every report")
        E_p = float(self.data["moduli"]["E_p"][basis]["value"])
        E_z = E_p * self._ratio("E_z_over_E_p", corner)
        return {"E_p": E_p, "E_z": E_z, "nu_p": self._ratio("nu_p", corner),
                "nu_pz": self._ratio("nu_pz", corner), "G_z": E_z * self._ratio("G_z_over_E_z", corner)}

    def C(self, basis: str, corner: dict | None = None) -> np.ndarray:
        """6x6 stiffness, Voigt (xx, yy, zz, yz, xz, xy), engineering shear, print frame."""
        k = self.constants(basis, corner)
        return ti_C(k["E_p"], k["E_z"], k["nu_p"], k["nu_pz"], k["G_z"])

    def stiffness_corners(self) -> list[dict]:
        """Every combination of interval ends of the assumed ratios (2^n corners)."""
        names = [n for n in RATIOS if "interval" in self.data["moduli"][n]]
        ends = [self.data["moduli"][n]["interval"] for n in names]
        return [dict(zip(names, combo)) for combo in itertools.product(*ends)]

    def strength_corners(self) -> dict:
        """Strength sets at both Z_t corners plus the conservative design corner (MPa)."""
        s = self.data["strengths"]
        X_t = float(s["X_t"]["value"])
        lo, hi = s["S_il_over_Z_t"]["interval"]
        corners = {}
        for name, spec in s["Z_t"].items():
            Z_t = float(spec["value"]) if "value" in spec else _eval_from(spec["value_from"], X_t)
            corners[name] = {"X_t": X_t, "Z_t": Z_t, "S_il": [lo * Z_t, hi * Z_t], "tag": spec["tag"]}
        worst = min(corners, key=lambda n: corners[n]["Z_t"])
        w = corners[worst]
        corners["design"] = {"X_t": X_t, "Z_t": w["Z_t"], "S_il": lo * w["Z_t"], "from": worst,
                             "note": "conservative corner: lowest Z_t, lowest S_il/Z_t"}
        return corners

    def summary(self) -> str:
        st = self.strength_corners()
        k = self.constants("short_term")
        lines = [f"{self.data['grade']['vendor']} {self.data['grade']['product']} card {self.id}, tier {self.tier}",
                 (f"  short-term E_p {k['E_p']:.0f} MPa, E_z {k['E_z']:.0f} MPa, G_z {k['G_z']:.0f} MPa; "
                  f"sustained E_p {self.constants('sustained_effective')['E_p']:.0f} MPa (same ratios, assumed)")]
        for name, c in st.items():
            if name == "design":
                lines.append(f"  DESIGN corner ({c['from']}): Z_t {c['Z_t']:.2f} MPa, S_il {c['S_il']:.2f} MPa")
            else:
                lines.append(f"  corner {name}: X_t {c['X_t']:.1f}, Z_t {c['Z_t']:.1f} MPa (Z/XY {c['Z_t'] / c['X_t']:.2f}), "
                             f"S_il {c['S_il'][0]:.1f}..{c['S_il'][1]:.1f} MPa [{c['tag']}]")
        if self.tier == "T0":
            lines.append("  T0: datasheet values and assumptions; supports relative studies only, not qualification.")
        return "\n".join(lines)


def _eval_from(expr: str, X_t: float) -> float:
    """The only derived form allowed: '<factor> * X_t'."""
    factor, _, var = (p.strip() for p in expr.partition("*"))
    if var != "X_t":
        raise ValueError(f"value_from must be '<factor> * X_t', got {expr!r}")
    return float(factor) * X_t


def _lint_value(where: str, spec, errors: list[str], need_value: bool = True) -> None:
    if not isinstance(spec, dict):
        errors.append(f"{where}: must be a mapping with value, unit and tag")
        return
    if need_value and "value" not in spec and "value_from" not in spec:
        errors.append(f"{where}: has no value")
    if not spec.get("unit"):
        errors.append(f"{where}: has no unit (use '1' for a ratio)")
    if spec.get("tag") not in TAGS:
        errors.append(f"{where}: evidence tag {spec.get('tag')!r} is missing or unknown (allowed: {sorted(TAGS)})")
    iv = spec.get("interval")
    if iv is not None:
        if len(iv) != 2 or iv[0] > iv[1]:
            errors.append(f"{where}: interval must be [low, high], got {iv}")
        elif "value" in spec and not iv[0] <= spec["value"] <= iv[1]:
            errors.append(f"{where}: value {spec['value']} lies outside its interval {iv}")
    if spec.get("tag") == "H" and iv is None and need_value and "value_from" not in spec:
        errors.append(f"{where}: a heuristic (H) value needs an interval so results can be reported at its corners")
    if spec.get("borrowed") and not spec.get("note"):
        errors.append(f"{where}: a value borrowed from another grade must say where it came from (note)")


def lint_card(d: dict) -> list[str]:
    """Plain-language problems with a card (empty list = clean)."""
    cid = d.get("id", "?")
    errors = [f"{cid}: missing required key {k!r}" for k in
              ("schema", "id", "grade", "tier", "symmetry", "poisson_convention", "moduli", "strengths",
               "process_binding", "provenance") if k not in d]
    if errors:
        return errors
    if d["schema"] != SCHEMA:
        errors.append(f"{cid}: schema is {d['schema']!r}, expected {SCHEMA!r}")
    if d["tier"] not in TIERS:
        errors.append(f"{cid}: tier {d['tier']!r} must be one of {TIERS}")
    if d["symmetry"] != "transversely_isotropic":
        errors.append(f"{cid}: only transversely_isotropic cards are supported in v0.1")
    m = d["moduli"]
    for b in BASES:
        if b not in m.get("E_p", {}):
            errors.append(f"{cid}: E_p needs both modulus bases ({', '.join(BASES)}); got {sorted(m.get('E_p', {}))}")
        else:
            _lint_value(f"{cid}.moduli.E_p.{b}", m["E_p"][b], errors)
    for r in RATIOS:
        if r not in m:
            errors.append(f"{cid}: moduli.{r} is missing")
        else:
            _lint_value(f"{cid}.moduli.{r}", m[r], errors)
    s = d["strengths"]
    if "X_t" not in s or "Z_t" not in s or "S_il_over_Z_t" not in s:
        errors.append(f"{cid}: strengths need X_t, Z_t corners and S_il_over_Z_t")
        return errors
    _lint_value(f"{cid}.strengths.X_t", s["X_t"], errors)
    _lint_value(f"{cid}.strengths.S_il_over_Z_t", s["S_il_over_Z_t"], errors, need_value=False)
    if "half_X_t" not in s["Z_t"] or len(s["Z_t"]) < 2:
        errors.append(f"{cid}: Z_t must be reported at both corners, the vendor ratio and 0.5 X_t (PLAN D10)")
    for name, spec in s["Z_t"].items():
        _lint_value(f"{cid}.strengths.Z_t.{name}", spec, errors)
    if d["tier"] in ("T1", "T2") and not any(spec.get("tag") == "U" for spec in s["Z_t"].values()):
        errors.append(f"{cid}: tier {d['tier']} needs an own-coupon (U) Z_t; with datasheet values only it is T0")
    if errors:
        return errors
    card = Card(cid, d)
    for b in BASES:
        k = card.constants(b)
        for why in pd_reasons(**k):
            errors.append(f"{cid}: not positive definite at nominal values ({b}): {why}")
        for corner in card.stiffness_corners():
            for why in pd_reasons(**card.constants(b, corner)):
                errors.append(f"{cid}: not positive definite at interval corner {corner} ({b}): {why}")
    return errors


def load_card(path_or_id: str | Path) -> Card:
    p = Path(path_or_id)
    if not p.suffix:
        p = materials_root() / f"{path_or_id}.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    errors = lint_card(d)
    if errors:
        raise ValueError(f"material card {p.name} failed its lint:\n  " + "\n  ".join(errors))
    return Card(d["id"], d, p)
