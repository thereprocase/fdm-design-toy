"""problem.yaml + `fdmgen lint` (#7): resultant assertion, plain-language errors, pinned sources."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

yaml = pytest.importorskip("yaml")

from fdmgen.cli import main
from fdmgen.problem import lint_problem, lint_problem_file
from fdmgen.problem import spool_bracket as gen

REPO = Path(__file__).resolve().parents[1]
PROBLEM = REPO / "problems" / "spool-rack-g2-ef" / "problem.yaml"
FIX = json.loads((REPO / "tests" / "fixtures" / "g2_interface_loads.json").read_text())
SOURCE = REPO.parent / gen.SOURCE_REPO


def _p():
    return yaml.safe_load(PROBLEM.read_text())


def _errors(p):
    return [f for f in lint_problem(p) if f.severity == "error"]


def test_committed_problem_lints_without_errors():
    assert [f for f in lint_problem_file(PROBLEM) if f.severity == "error"] == []


def test_full_case_resultant_and_split_match_pinned_reference():
    full = next(lc for lc in _p()["load_cases"] if lc["id"] == "full")
    forces = {f["at"]: np.array(f["N"]) for f in full["forces"]}
    assert np.allclose(sum(forces.values()), [0.0, -117.72, 0.0], rtol=0, atol=1e-12)
    assert np.allclose(forces["rear_seat"], FIX["rear_seat_target_N"], rtol=1e-12, atol=1e-12)
    assert np.allclose(forces["front_seat"], FIX["front_seat_target_N"], rtol=1e-12, atol=1e-12)
    delta = next(lc for lc in _p()["load_cases"] if lc["id"] == "one-spool-delta")
    assert delta["total_N"] == pytest.approx(1.25 * 9.81, rel=1e-12)


def test_hand_edited_force_is_caught_twice_in_plain_language():
    p = _p()
    p["load_cases"][0]["forces"][0]["N"][1] += 0.02
    msgs = [f.message for f in _errors(p)]
    assert any("add up to" in m and "117.72 N along gravity" in m and "regenerate" in m for m in msgs)
    assert any("edited by hand or the adapter changed" in m for m in msgs)


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["load_cases"][0]["forces"][0].update(at="rear_rod"), "not a declared interface"),
    (lambda p: p["rule_overrides"][0].update(reason=""), "has no reason"),
    (lambda p: p["rule_overrides"][0].update(rule="WALL-999"), "unknown rule"),
    (lambda p: p["rule_overrides"][0]["value"].update(min_wals=2), "has no parameter 'min_wals'"),
    (lambda p: p["infill"].update(credited=True), "never credited"),
    (lambda p: p["process"]["settings"].update(layer_height=0.28), "only valid at 0.2"),
    (lambda p: p["refs"].update(material="polylite-petg-t0"), "material card"),
    (lambda p: p["requirements"][0].pop("modulus_basis"), "must name its modulus_basis"),
    (lambda p: p["requirements"][1].update(load_case="two-spools"), "does not exist"),
    (lambda p: p["interfaces"][0].pop("support"), "support rule"),
    (lambda p: p["load_cases"][0].update(gravity_dir=[0, -2, 0]), "not a unit vector"),
    (lambda p: p.pop("supports"), "required key is missing"),
])
def test_lint_errors(mutate, needle):
    p = _p()
    mutate(p)
    msgs = " | ".join(f"{f.where}: {f.message}" for f in _errors(p))
    assert needle in msgs


def test_source_hashes(tmp_path, monkeypatch):
    p = _p()
    monkeypatch.setenv("SPOOL_RACK_ROOT", str(tmp_path))            # an empty "checkout"
    msgs = [f.message for f in _errors(p)]
    assert any("is missing" in m for m in msgs)
    for f in p["generated_by"]["source"]["files"]:
        dst = tmp_path / f["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("changed")
    assert any("no longer matches its pinned sha256" in f.message for f in _errors(p))
    q = copy.deepcopy(p)
    q["generated_by"]["source"]["repo"] = "no-such-repo"
    monkeypatch.delenv("SPOOL_RACK_ROOT")
    warn = [f for f in lint_problem(q) if f.severity == "warning"]
    assert any("NOT checked" in f.message for f in warn)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="spool-wall-rack checkout not next to this repository")
def test_committed_problem_is_exactly_what_the_generator_writes():
    assert gen.build(SOURCE) == _p()


def test_cli_lint_json_and_exit_codes(tmp_path, capsys):
    assert main(["lint", str(PROBLEM), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    bad = _p()
    bad["infill"]["credited"] = True
    path = tmp_path / "problem.yaml"
    path.write_text(yaml.safe_dump(bad))
    assert main(["lint", str(path)]) == 1
    assert "never credited" in capsys.readouterr().out
    path.write_text("schema: [unclosed")
    assert main(["lint", str(path)]) == 1
    assert main(["catalog", "lint"]) == 0
    assert main(["card", "show", "polymaker-polylite-asa-t0"]) == 0
    assert main(["card", "show", "no-such-card"]) == 1
