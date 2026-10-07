"""Rule catalog: load `catalog/rules/*.yaml`, lint it, resolve calibrated values (PLAN D13).

Conventions (research/final/frodo.md section 2):
- one angle convention: alpha = slope from horizontal (0 = flat underside, 90 = vertical wall);
- every number carries a unit and an evidence tag; an untagged or unitless number is a lint error;
- material strengths never live here (they belong to the material card);
- calibrated values come from a calibration binding tied to slicer-profile hashes, and go STALE
  as soon as any bound hash differs from the profile actually in use.
"""
from __future__ import annotations

import importlib
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .result import LEVELS

RULE_SCHEMA = "fdmgen/rule@0.1"
BINDING_SCHEMA = "fdmgen/calibration@0.1"
ID_RE = re.compile(r"^[A-Z]{2,5}-\d{3}$")
# U own print, S slicer behaviour, V vendor/slicer docs, L literature, H heuristic placeholder,
# derived (computed from other tagged values), precedent (a design value never print-tested),
# policy (an owner/house decision), logic (follows from the definition).
EVIDENCE_TAGS = {"U", "S", "V", "L", "H", "derived", "precedent", "policy", "logic"}
UNITS = {"mm", "mm2", "mm3", "deg", "s", "mm/s", "N", "MPa", "1", "count", "%", "C"}
STATUSES = {"PROVISIONAL", "CALIBRATED"}
ENFORCEMENT = {"hard_filter", "constraint", "repair", "post_check", "advisory", "process", "lint"}
REQUIRED = ("schema", "id", "name", "protects", "levels", "enforcement", "defaults", "evidence", "sources")


def catalog_root() -> Path:
    """`catalog/` at the repository root (the catalog is data, licensed CC BY 4.0)."""
    return Path(__file__).resolve().parents[3] / "catalog"


@dataclass
class Rule:
    id: str
    name: str
    data: dict
    path: Path | None = None

    @property
    def levels(self) -> list[str]:
        return list(self.data["levels"])

    @property
    def parameters(self) -> dict:
        return self.data.get("parameters") or {}

    def param(self, name: str, binding: Binding | None = None) -> Value:
        """Resolve a parameter: calibration binding first (if bound and not stale), else the default."""
        if name not in self.parameters:
            raise KeyError(f"{self.id} has no parameter {name!r}; known: {sorted(self.parameters)}")
        p = self.parameters[name]
        if binding is not None:
            v = binding.value(f"{self.id}.{name}")
            if v is not None:
                return v
        return Value(p["value"], p["unit"], p["tag"], p.get("status", "PROVISIONAL"), source="rule default")


@dataclass
class Value:
    value: object
    unit: str
    tag: str
    status: str
    source: str = ""

    @property
    def provisional(self) -> bool:
        return self.status != "CALIBRATED"


@dataclass
class Binding:
    """A calibration binding: values valid only for the exact slicer profiles whose hashes it pins."""
    id: str
    data: dict
    current_hashes: dict = field(default_factory=dict)

    @property
    def bound_hashes(self) -> dict:
        return self.data["binds"].get("profile_sha256", {})

    def status(self) -> str:
        """BOUND (all pinned hashes match), STALE (any differs), or UNBOUND (hashes not pinned / unknown)."""
        pinned = self.bound_hashes
        if not pinned or any(v is None for v in pinned.values()):
            return "UNBOUND"
        if any(self.current_hashes.get(k) not in (None, v) for k, v in pinned.items()):
            return "STALE"
        if any(self.current_hashes.get(k) is None for k in pinned):
            return "UNBOUND"
        return "BOUND"

    def value(self, key: str) -> Value | None:
        v = self.data.get("values", {}).get(key)
        if v is None:
            return None
        st = self.status()
        status = v.get("status", "PROVISIONAL") if st == "BOUND" else st
        return Value(v["value"], v["unit"], v["tag"], status, source=f"calibration {self.id} ({st})")


def load_rules(root: str | Path | None = None) -> dict[str, Rule]:
    root = Path(root) if root else catalog_root() / "rules"
    rules = {}
    for p in sorted(root.glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        rules[d["id"]] = Rule(d["id"], d["name"], d, p)
    return rules


def load_binding(path: str | Path, current_hashes: dict | None = None) -> Binding:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Binding(d["id"], d, dict(current_hashes or {}))


def _lint_number(where: str, spec: dict, errors: list[str]) -> None:
    if not isinstance(spec, dict) or "value" not in spec:
        errors.append(f"{where}: must be a mapping with value, unit and tag")
        return
    if spec.get("unit") not in UNITS:
        errors.append(f"{where}: unit {spec.get('unit')!r} is missing or unknown (allowed: {sorted(UNITS)}); "
                      "a unitless number is a lint error, use unit '1' for a true ratio")
    if spec.get("tag") not in EVIDENCE_TAGS:
        errors.append(f"{where}: evidence tag {spec.get('tag')!r} is missing or unknown (allowed: {sorted(EVIDENCE_TAGS)})")
    if spec.get("status", "PROVISIONAL") not in STATUSES:
        errors.append(f"{where}: status {spec.get('status')!r} not in {sorted(STATUSES)}")
    if spec.get("tag") == "H" and spec.get("status") == "CALIBRATED":
        errors.append(f"{where}: a heuristic (H) value cannot be CALIBRATED; print the coupon first")


def lint_rule(d: dict, filename: str | None = None) -> list[str]:
    """Plain-language problems with one rule definition (empty list = clean)."""
    rid = d.get("id", "?")
    errors = [f"{rid}: missing required key {k!r}" for k in REQUIRED if k not in d]
    if errors:
        return errors
    if d["schema"] != RULE_SCHEMA:
        errors.append(f"{rid}: schema is {d['schema']!r}, expected {RULE_SCHEMA!r}")
    if not ID_RE.match(rid):
        errors.append(f"{rid}: id must look like ABC-001")
    if filename and Path(filename).stem != rid:
        errors.append(f"{rid}: file is named {Path(filename).name}; rule files are named after their id")
    bad = [lv for lv in d["levels"] if lv not in LEVELS and lv != "-"]
    if bad:
        errors.append(f"{rid}: unknown check levels {bad}; use V, M, T, P")
    for mode in d["enforcement"]:
        if mode not in ENFORCEMENT:
            errors.append(f"{rid}: enforcement {mode!r} not in {sorted(ENFORCEMENT)}")
    if d.get("convention", {}).get("angle", "slope_from_horizontal") != "slope_from_horizontal":
        errors.append(f"{rid}: the catalog uses one angle convention, slope from horizontal")
    for name, spec in (d.get("parameters") or {}).items():
        _lint_number(f"{rid}.parameters.{name}", spec, errors)
    for lv, path in (d.get("checkers") or {}).items():
        if lv not in d["levels"]:
            errors.append(f"{rid}: checker for level {lv} but the rule does not list that level")
        mod, _, fn = path.rpartition(".")
        try:
            getattr(importlib.import_module(mod), fn)
        except (ImportError, AttributeError) as e:
            errors.append(f"{rid}: checker {path} for level {lv} cannot be imported ({e})")
    tmpl = d.get("message_template")
    if tmpl:
        names = {f for _, f, _, _ in string.Formatter().parse(tmpl) if f}
        unknown = {n.split(".")[0].split("[")[0] for n in names} - set(d.get("parameters") or {}) - \
            set(d.get("message_fields") or []) - {"rule", "verdict", "level"}
        if unknown:
            errors.append(f"{rid}: message_template uses {sorted(unknown)}, which are neither parameters nor "
                          "declared message_fields")
    for s in d["sources"]:
        if s.get("tag") not in EVIDENCE_TAGS or not s.get("ref"):
            errors.append(f"{rid}: every source needs an evidence tag and a ref, got {s}")
    if re.search(r"(?i)\b(X_t|Z_t|S_il|tensile strength)\b\s*[:=]\s*\d", yaml.safe_dump(d.get("parameters") or {})):
        errors.append(f"{rid}: material strengths belong to the material card, not the catalog")
    return errors


def lint_binding(d: dict, rules: dict[str, Rule]) -> list[str]:
    cid = d.get("id", "?")
    errors = []
    if d.get("schema") != BINDING_SCHEMA:
        errors.append(f"{cid}: schema is {d.get('schema')!r}, expected {BINDING_SCHEMA!r}")
    if "profile_sha256" not in (d.get("binds") or {}):
        errors.append(f"{cid}: binds.profile_sha256 is required (use null for a hash not yet pinned)")
    for key, spec in (d.get("values") or {}).items():
        rid, _, pname = key.partition(".")
        if rid not in rules:
            errors.append(f"{cid}: value {key} names unknown rule {rid}")
        elif pname not in rules[rid].parameters:
            errors.append(f"{cid}: value {key}: rule {rid} has no parameter {pname!r}")
        else:
            _lint_number(f"{cid}.values.{key}", spec, errors)
            if spec.get("unit") != rules[rid].parameters[pname]["unit"]:
                errors.append(f"{cid}: value {key} is in {spec.get('unit')!r} but the rule declares "
                              f"{rules[rid].parameters[pname]['unit']!r}")
    return errors


def lint_catalog(root: str | Path | None = None) -> list[str]:
    root = Path(root) if root else catalog_root()
    rules = load_rules(root / "rules")
    errors = [e for r in rules.values() for e in lint_rule(r.data, r.path)]
    for p in sorted((root / "calibration").glob("*.yaml")):
        errors += lint_binding(yaml.safe_load(p.read_text(encoding="utf-8")), rules)
    return errors
