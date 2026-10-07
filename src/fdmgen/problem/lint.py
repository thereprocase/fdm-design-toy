"""`fdmgen lint`: plain-language checks on a problem.yaml before any solve is spent on it.

The lint is written for whoever (or whatever) authored the problem, often an LLM: every finding names
the place in the file, says what is wrong in words, and says what to do about it.
Errors block; warnings are things that could not be verified (they are never silently passed).
"""
from __future__ import annotations

import hashlib
import importlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import yaml

SCHEMA = "fdmgen/problem@0.1"
REQUIRED = ("schema", "id", "frames", "refs", "interfaces", "load_cases", "supports", "requirements",
            "infill", "support_policy")
FRAMES = {"design", "installed", "print"}
BASES = {"short_term", "sustained_effective"}


@dataclass
class Finding:
    severity: str          # "error" blocks; "warning" means could not verify
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.where}: {self.message}"

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt(v) -> str:
    return "[" + ", ".join(f"{x:.6g}" for x in np.asarray(v, float)) + "]"


def _source_root(problem: dict) -> Path | None:
    """The source checkout: $<root_env> if set, else a sibling directory named after the source repo."""
    src = (problem.get("generated_by") or {}).get("source") or {}
    repo = src.get("repo")
    if not repo:
        return None
    env = os.environ.get(src.get("root_env") or "")
    cands = ([Path(env)] if env else []) + [Path(__file__).resolve().parents[4] / repo]
    return next((c for c in cands if c.is_dir()), None)


def _check_loads(p: dict, out: list[Finding]) -> None:
    ifaces = {i.get("id") for i in p["interfaces"]}
    for n, lc in enumerate(p["load_cases"]):
        where = f"load_cases[{n}] ({lc.get('id', '?')})"
        if lc.get("frame") not in FRAMES:
            out.append(Finding("error", where, f"frame {lc.get('frame')!r} is not one of {sorted(FRAMES)}; "
                                                "say which frame the forces are written in"))
        forces = lc.get("forces") or []
        if not forces:
            out.append(Finding("error", where, "has no forces; list each force with the interface it acts on"))
            continue
        for f in forces:
            if f.get("at") not in ifaces:
                out.append(Finding("error", where, f"a force acts at {f.get('at')!r}, which is not a declared "
                                                    f"interface (declared: {sorted(ifaces)})"))
            if len(f.get("N", [])) != 3:
                out.append(Finding("error", where, f"force at {f.get('at')!r} must be a 3-vector in N"))
                return
        total, g = lc.get("total_N"), lc.get("gravity_dir")
        if total is None or g is None:
            out.append(Finding("error", where, "needs total_N and gravity_dir so the resultant can be checked"))
            continue
        g = np.asarray(g, float)
        if abs(np.linalg.norm(g) - 1) > 1e-12:
            out.append(Finding("error", where, f"gravity_dir {_fmt(g)} is not a unit vector"))
            continue
        resultant = np.sum([f["N"] for f in forces], axis=0)
        expected = total * g
        tol = lc.get("resultant_tol_N", 1e-9 * max(1.0, abs(total)))
        diff = np.abs(resultant - expected).max()
        if diff > tol:
            out.append(Finding("error", where,
                f"the forces add up to {_fmt(resultant)} N, but the case declares {total:g} N along gravity "
                f"{_fmt(g)}, i.e. {_fmt(expected)} N (largest difference {diff:.3g} N, allowed {tol:.3g} N). "
                "Either a force was typed wrongly or the split does not carry the whole load; regenerate the "
                "forces from their source instead of editing them by hand."))
        if "resultant_tol_N" in lc and not lc.get("resultant_tol_reason"):
            out.append(Finding("error", where, "resultant_tol_N is loosened without resultant_tol_reason"))


def _check_regeneration(p: dict, out: list[Finding]) -> None:
    gen = p.get("generated_by") or {}
    mod = gen.get("generator")
    if not mod:
        out.append(Finding("warning", "generated_by", "the problem was not generated from pinned sources, so its "
                                                       "loads cannot be re-derived (PLAN D15)"))
        return
    modname, _, fn = mod.rpartition(".")
    try:
        loads = getattr(importlib.import_module(modname), fn)
    except (ImportError, AttributeError) as e:
        out.append(Finding("error", "generated_by.generator", f"cannot import {mod} ({e})"))
        return
    fresh = {lc["id"]: lc for lc in loads()}
    for n, lc in enumerate(p["load_cases"]):
        ref = fresh.get(lc.get("id"))
        if ref is None:
            out.append(Finding("error", f"load_cases[{n}]", f"load case {lc.get('id')!r} is not produced by {mod}"))
            continue
        for a, b in zip(lc.get("forces", []), ref["forces"]):
            if a.get("at") != b["at"] or not np.allclose(a.get("N"), b["N"], rtol=1e-12, atol=1e-12):
                out.append(Finding("error", f"load_cases[{n}] ({lc['id']})",
                    f"force at {a.get('at')!r} is {_fmt(a.get('N'))} N but {mod} gives {b['at']!r} "
                    f"{_fmt(b['N'])} N. The file was edited by hand or the adapter changed: regenerate it "
                    "(fdmgen problem spool-bracket) rather than editing loads."))


def _check_sources(p: dict, out: list[Finding]) -> None:
    src = (p.get("generated_by") or {}).get("source") or {}
    files = src.get("files") or []
    if not files:
        return
    root = _source_root(p)
    if root is None:
        out.append(Finding("warning", "generated_by.source",
            f"the {src.get('repo')} checkout was not found (set {src.get('root_env') or 'its root_env'} or place it "
            "next to this repository), so the pinned source hashes were NOT checked"))
        return
    for f in files:
        path = root / f["path"]
        if not path.is_file():
            out.append(Finding("error", "generated_by.source", f"pinned source {f['path']} is missing in {root.name}"))
        elif hashlib.sha256(path.read_bytes()).hexdigest() != f["sha256"]:
            out.append(Finding("error", "generated_by.source",
                f"{f['path']} no longer matches its pinned sha256: the source changed since this problem was "
                "generated. Regenerate the problem and review what changed."))


def _check_keep_outs(p: dict, out: list[Finding]) -> None:
    kos = p.get("keep_outs") or []
    ids = [k.get("id") for k in kos]
    if len(set(ids)) != len(ids):
        out.append(Finding("error", "keep_outs", "keep-out ids must be unique"))
    for n, k in enumerate(kos):
        if k.get("type") == "box":
            lo, hi = k.get("min_mm"), k.get("max_mm")
            if not (isinstance(lo, list) and isinstance(hi, list) and len(lo) == 3 and len(hi) == 3):
                out.append(Finding("error", f"keep_outs[{n}] ({k.get('id')})", "a box needs min_mm and max_mm with 3 values (null = unbounded)"))
                return
            if any(a is not None and b is not None and a >= b for a, b in zip(lo, hi)):
                out.append(Finding("error", f"keep_outs[{n}] ({k.get('id')})", "min_mm must be below max_mm on every bounded axis"))
    root = _source_root(p)
    body = (p.get("geometry") or {}).get("body") or {}
    if not kos or root is None or not body.get("path"):
        return
    path = root / body["path"]
    if not path.is_file():
        return                                     # _check_sources already reports the missing file
    import trimesh

    from ..catalog.checks.keepout import check_body
    try:
        mesh = trimesh.load(path, force="mesh", process=False)
        if len(getattr(mesh, "faces", ())) == 0:
            raise ValueError("no triangles")
    except Exception as e:  # noqa: BLE001 - any corrupt source file is reported as a finding, never a crash
        out.append(Finding("warning", "keep_outs", f"the body mesh {body['path']} could not be read ({e}); keep-outs were NOT checked"))
        return
    for r in check_body(mesh.vertices, mesh.faces, kos, frame=body.get("frame", "installed")):
        if r.verdict.value == "FAIL":
            out.append(Finding("error", f"keep_outs ({r.metrics['keep_out_id']})", r.message))
        elif r.verdict.value == "NOT_CHECKED":
            out.append(Finding("warning", f"keep_outs ({r.metrics['keep_out_id']})", r.message))


def _check_refs(p: dict, out: list[Finding]) -> None:
    from ..catalog import load_rules
    from ..catalog.rules import catalog_root
    from ..materials import load_card

    refs = p["refs"]
    card = None
    try:
        card = load_card(refs["material"])
    except (FileNotFoundError, ValueError, KeyError) as e:
        out.append(Finding("error", "refs.material", f"material card {refs.get('material')!r} is unusable: {e}"))
    cal = refs.get("calibration")
    if cal and not (catalog_root() / "calibration" / f"{cal}.yaml").is_file():
        out.append(Finding("error", "refs.calibration", f"no calibration binding named {cal!r} in catalog/calibration"))
    if card is not None and cal and card.data["process_binding"].get("calibration") != cal:
        out.append(Finding("error", "refs", f"the material card is bound to calibration "
                                            f"{card.data['process_binding'].get('calibration')!r}, not {cal!r}"))
    proc = p.get("process", {}).get("settings", {})
    if card is not None:
        from ..catalog.checks.proc import values_match
        for k, v in card.data["process_binding"].get("settings", {}).items():
            if k in proc and not values_match(v, proc[k]):
                out.append(Finding("error", f"process.settings.{k}",
                    f"the problem sets {k} = {proc[k]!r} but the material card {card.id} is only valid at "
                    f"{v!r}; its strengths do not transfer to another process"))
    rules = load_rules()
    for n, o in enumerate(p.get("rule_overrides") or []):
        where = f"rule_overrides[{n}]"
        if o.get("rule") not in rules:
            out.append(Finding("error", where, f"unknown rule {o.get('rule')!r}"))
            continue
        if not str(o.get("reason", "")).strip():
            out.append(Finding("error", where, f"override of {o['rule']} has no reason; every override must say why"))
        for k in (o.get("value") or {}):
            if k not in rules[o["rule"]].parameters:
                out.append(Finding("error", where, f"{o['rule']} has no parameter {k!r} "
                                                   f"(known: {sorted(rules[o['rule']].parameters)})"))


def lint_problem(p: dict) -> list[Finding]:
    out = [Finding("error", k, "required key is missing") for k in REQUIRED if k not in p]
    if out:
        return out
    if p["schema"] != SCHEMA:
        out.append(Finding("error", "schema", f"is {p['schema']!r}, expected {SCHEMA!r}"))
    for n, i in enumerate(p["interfaces"]):
        for k in ("id", "type", "role", "support"):
            if k not in i:
                out.append(Finding("error", f"interfaces[{n}] ({i.get('id', '?')})",
                                   f"has no {k!r}; every interface needs an id, type, role and support rule"))
    _check_loads(p, out)
    lc_ids = {lc.get("id") for lc in p["load_cases"]}
    for n, r in enumerate(p["requirements"]):
        if "load_case" in r and r["load_case"] not in lc_ids:
            out.append(Finding("error", f"requirements[{n}]", f"refers to load case {r['load_case']!r}, which does not exist"))
        if r.get("modulus_basis") and r["modulus_basis"] not in BASES:
            out.append(Finding("error", f"requirements[{n}]", f"modulus_basis must be one of {sorted(BASES)}"))
        if r.get("metric", "").endswith("_mm") and not r.get("modulus_basis"):
            out.append(Finding("error", f"requirements[{n}]", "a movement limit must name its modulus_basis "
                                                              "(displacements scale as 1/E)"))
    if p["infill"].get("credited", False):
        out.append(Finding("error", "infill.credited", "sparse infill is never credited (PLAN D12)"))
    if p["support_policy"].get("default") not in ("forbidden", "allowed"):
        out.append(Finding("error", "support_policy.default", "must be 'forbidden' or 'allowed'"))
    _check_refs(p, out)
    _check_regeneration(p, out)
    _check_sources(p, out)
    _check_keep_outs(p, out)
    return out


def lint_problem_file(path: str | Path) -> list[Finding]:
    path = Path(path)
    try:
        p = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [Finding("error", str(path), f"is not valid YAML: {e}")]
    if not isinstance(p, dict):
        return [Finding("error", str(path), "must be a YAML mapping")]
    return lint_problem(p)
