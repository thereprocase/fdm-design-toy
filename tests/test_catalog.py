"""Rule catalog v0: the data lints clean, bindings go STALE, verdicts never hide NOT_CHECKED (#9)."""
import copy

import pytest

pytest.importorskip("yaml")

from fdmgen.catalog import (
    CheckResult,
    Verdict,
    governing,
    lint_catalog,
    lint_rule,
    load_binding,
    load_rules,
)
from fdmgen.catalog.rules import catalog_root

BINDING = catalog_root() / "calibration" / "p1s-0.4-polylite-asa-cal-2026-10.yaml"


def test_catalog_lints_clean_and_has_every_table_rule():
    assert lint_catalog() == []
    rules = load_rules()
    assert len(rules) == 35                     # master table rows (the plan's "33" is out of date)
    for rid in ("OVH-001", "WALL-001", "GAP-001", "BRG-001", "PROC-001", "STR-001", "CAL-001"):
        assert rid in rules
    assert set(rules["OVH-001"].data["checkers"]) == {"V", "M", "T"}          # T: toolpath.check_support


def test_lint_catches_unitless_untagged_and_misnamed():
    d = copy.deepcopy(load_rules()["OVH-001"].data)
    d["parameters"]["alpha_min_deg"].pop("unit")
    d["parameters"]["min_island_area_mm2"]["tag"] = "trust me"
    d["parameters"]["alpha_grid_deg"].update(tag="H", status="CALIBRATED")
    errs = lint_rule(d, "OVH-002.yaml")
    text = "\n".join(errs)
    assert "unitless" in text and "evidence tag" in text and "cannot be CALIBRATED" in text
    assert "rule files are named after their id" in text


def test_lint_rejects_other_angle_conventions_and_bad_checkers():
    d = copy.deepcopy(load_rules()["OVH-001"].data)
    d["convention"]["angle"] = "from_vertical"
    d["checkers"]["T"] = "fdmgen.catalog.checks.ovh.no_such_function"
    errs = "\n".join(lint_rule(d))
    assert "one angle convention" in errs
    assert "does not list that level" not in errs          # T is a listed level for OVH-001
    assert "cannot be imported" in errs


def test_binding_status_unbound_bound_stale():
    rules = load_rules()
    b = load_binding(BINDING)
    assert b.status() == "UNBOUND"              # hashes not pinned yet
    v = rules["OVH-001"].param("alpha_min_deg", b)
    assert (v.value, v.unit, v.status, v.provisional) == (50, "deg", "UNBOUND", True)

    pinned = {"machine": "a" * 64, "process": "b" * 64, "filament": "c" * 64}
    b.data["binds"]["profile_sha256"] = dict(pinned)
    b.current_hashes = dict(pinned)
    assert b.status() == "BOUND"
    assert rules["BRG-001"].param("max_span_external_mm", b).status == "PROVISIONAL"
    b.current_hashes["process"] = "d" * 64       # someone edited the process profile
    assert b.status() == "STALE"
    assert rules["BRG-001"].param("max_span_external_mm", b).status == "STALE"
    # a parameter the binding does not carry falls back to the rule default
    assert rules["OVH-001"].param("min_island_area_mm2", b).source == "rule default"


def test_governing_prefers_highest_level_that_ran():
    v = CheckResult("OVH-001", "V", Verdict.PASS, "v")
    m = CheckResult("OVH-001", "M", Verdict.FAIL, "m")
    t = CheckResult("OVH-001", "T", Verdict.NOT_CHECKED, "t")
    g = governing([v, t, m])
    assert g["OVH-001"] is m                     # T did not run, so M governs
    assert governing([t])["OVH-001"] is t        # nothing ran: NOT_CHECKED, never PASS
    assert m.label == "OVH-001 M FAIL (PROVISIONAL)"
    with pytest.raises(ValueError):
        CheckResult("OVH-001", "X", Verdict.PASS, "bad level")
