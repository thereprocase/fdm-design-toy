"""`fdmgen` command line: lint problems, lint the catalog, show material cards, generate problems."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _cmd_lint(a) -> int:
    from .problem import lint_problem_file
    findings = lint_problem_file(a.problem)
    errors = [f for f in findings if f.severity == "error"]
    if a.json:
        print(json.dumps({"problem": str(a.problem), "ok": not errors,
                          "findings": [f.to_dict() for f in findings]}, indent=1))
    else:
        for f in findings:
            print(f)
        print(f"{a.problem}: {len(errors)} error(s), {len(findings) - len(errors)} warning(s)"
              + ("" if errors else " - OK to solve"))
    return 1 if errors else 0


def _cmd_catalog_lint(a) -> int:
    from .catalog import lint_catalog, load_rules
    errors = lint_catalog()
    for e in errors:
        print(f"ERROR   {e}")
    print(f"catalog: {len(load_rules())} rules, {len(errors)} error(s)")
    return 1 if errors else 0


def _cmd_card_show(a) -> int:
    from .materials import load_card
    try:
        card = load_card(a.card)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR   {e}")
        return 1
    print(card.summary())
    return 0


def _cmd_problem_spool(a) -> int:
    from .problem import spool_bracket as gen
    root = a.root or os.environ.get(gen.ROOT_ENV) or str(Path(__file__).resolve().parents[3] / gen.SOURCE_REPO)
    if not Path(root).is_dir():
        print(f"ERROR   the {gen.SOURCE_REPO} checkout was not found at {root}; pass --root or set {gen.ROOT_ENV}")
        return 1
    gen.write(root, a.out)
    print(f"wrote {a.out}; now run: fdmgen lint {a.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fdmgen", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint", help="check a problem.yaml in plain language before solving")
    p.add_argument("problem", type=Path)
    p.add_argument("--json", action="store_true", help="machine-readable findings")
    p.set_defaults(fn=_cmd_lint)
    c = sub.add_parser("catalog", help="rule catalog tools").add_subparsers(dest="sub", required=True)
    c.add_parser("lint", help="lint catalog/rules and catalog/calibration").set_defaults(fn=_cmd_catalog_lint)
    m = sub.add_parser("card", help="material cards").add_subparsers(dest="sub", required=True)
    s = m.add_parser("show", help="summarise a card (both modulus bases, all strength corners)")
    s.add_argument("card", help="card id (catalog/materials/<id>.yaml) or a path")
    s.set_defaults(fn=_cmd_card_show)
    g = sub.add_parser("problem", help="generate problems from pinned sources").add_subparsers(dest="sub", required=True)
    sp = g.add_parser("spool-bracket", help="the spool-rack G2 E+F bracket")
    sp.add_argument("--root", help="spool-wall-rack checkout at the pinned commit")
    sp.add_argument("--out", type=Path, default=Path("problems/spool-rack-g2-ef/problem.yaml"))
    sp.set_defaults(fn=_cmd_problem_spool)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
