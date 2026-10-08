"""Known-answer parity of the browser box screen and exporter MOD-001 spacing.

No body or G-code is supplied: these cases establish spacing only, not bonding.
The seed generator's stricter non-overlap proposal policy is deliberately separate.
"""
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

pytest.importorskip("yaml")
from fdmgen.catalog import Verdict, load_rules
from fdmgen.massing import check_helpers
from fdmgen.planning import Helper

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/massing/helper-spacing.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_exporter_spacing_known_answers(case):
    helpers = [Helper(hid, hid, "test", "test", np.array(centre, float),
                      np.array([2, 2, 2], float), (), None, "")
               for hid, centre in [("a", [0, 0, 0]), ("b", case["centre_b"])]]
    results = check_helpers(helpers, gap_min_mm=case["minimum_mm"])
    assert any(r.verdict is Verdict.FAIL for r in results) is case["fail"]


def test_browser_spacing_matches_known_answers():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for browser/exporter spacing parity")
    script = """
const Plan=require('./ui/plan.js');
const cases=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const box=center=>({type:'box',frame:'design',center_mm:center,size_mm:[2,2,2]});
process.stdout.write(JSON.stringify(cases.map(c=>Plan.boxSeparation(
 box([0,0,0]),box(c.centre_b),c.minimum_mm===0.84?undefined:c.minimum_mm).needs_review)));
"""
    result = subprocess.run([node, "-e", script], cwd=ROOT, input=json.dumps(CASES),
                            text=True, capture_output=True, check=True, timeout=20)
    assert json.loads(result.stdout) == [case["fail"] for case in CASES]
    # The browser's default is nominal; a catalog change needs an explicit UI review.
    assert load_rules()["MOD-001"].parameters["boundary_gap_min_mm"]["value"] == 0.84
