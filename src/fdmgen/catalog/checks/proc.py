"""PROC-001: the slicer's effective settings match the declared process and material-card binding.

Effective settings are read back from what the slicer actually produced: the `; key = value` config
block Orca writes at the end of the G-code, or `Metadata/project_settings.config` in a 3MF.
A mismatch is blocking and names the key, the declared and effective values.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from ..result import CheckResult, Verdict

_LINE = re.compile(r"^;\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")


def settings_from_gcode(text: str) -> dict[str, str]:
    """Key/value pairs from the CONFIG_BLOCK (or, failing that, every `; key = value` comment)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if "CONFIG_BLOCK_START" in ln), None)
    end = next((i for i, ln in enumerate(lines) if "CONFIG_BLOCK_END" in ln), None)
    body = lines[start + 1:end] if start is not None and end is not None else lines
    out = {}
    for ln in body:
        m = _LINE.match(ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def settings_from_3mf(path: str | Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("Metadata/project_settings.config"))


def _items(v) -> list[str]:
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    return [x.strip() for x in str(v).replace(";", ",").split(",")]


def _num(s: str):
    s = s.strip()
    pct = s.endswith("%")
    try:
        return float(s.rstrip("%")), pct
    except ValueError:
        return None, pct


def values_match(declared, effective, rel_tol: float = 1e-6) -> bool:
    """Compare a declared value with an effective one; numbers within rel_tol, lists element-wise.

    A single declared value matches a per-extruder list whose entries are all equal to it.
    Booleans accept 1/0/true/false. Percent signs must agree (99.46% is not 99.46 mm).
    """
    d, e = _items(declared if not isinstance(declared, bool) else int(declared)), _items(effective)
    if len(d) == 1 and len(e) > 1:
        d = d * len(e)
    if len(d) != len(e):
        return False
    for a, b in zip(d, e):
        a = {"true": "1", "false": "0"}.get(a.lower(), a)
        b = {"true": "1", "false": "0"}.get(b.lower(), b)
        (na, pa), (nb, pb) = _num(a), _num(b)
        if na is not None and nb is not None:
            if pa != pb or abs(na - nb) > rel_tol * max(1.0, abs(na), abs(nb)):
                return False
        elif a != b:
            return False
    return True


def check_settings(declared: dict, effective: dict, *, source: str = "effective config") -> CheckResult:
    """T level, blocking: every declared key must be present in the effective config with the same value."""
    mismatched, missing = [], []
    for k, v in declared.items():
        if k not in effective:
            missing.append(k)
        elif not values_match(v, effective[k]):
            mismatched.append({"key": k, "declared": v, "effective": effective[k]})
    metrics = {"checked": len(declared), "mismatched": mismatched, "missing": missing, "source": source}
    does_not = "Whether the declared process is a good one; only that the slicer used it."
    if mismatched or missing:
        parts = [f"{m['key']} declared {m['declared']!r} but the slice used {m['effective']!r}" for m in mismatched]
        parts += [f"{k} is absent from the {source}" for k in missing]
        msg = (f"PROC-001 FAIL (blocking): {len(mismatched) + len(missing)} of {len(declared)} settings do not "
               "match: " + "; ".join(parts) + ". Results from this slice must not be used.")
        return CheckResult("PROC-001", "T", Verdict.FAIL, msg, False, metrics,
                           ["fix the profile or the 3MF per-object settings so the slicer uses the declared value",
                            "if the declared value is wrong, change it in the process file and re-run every check"],
                           "", does_not)
    msg = f"PROC-001 PASS: all {len(declared)} declared settings match the {source}."
    return CheckResult("PROC-001", "T", Verdict.PASS, msg, False, metrics, [],
                       "The slice was produced with exactly the declared settings for every checked key.", does_not)
