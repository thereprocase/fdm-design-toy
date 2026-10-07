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


def _cmd_orient(a) -> int:
    import hashlib
    import subprocess

    import trimesh
    import yaml

    from .materials import load_card
    from .orient import StressField, build_table
    from .problem.lint import _source_root

    prob = yaml.safe_load(Path(a.problem).read_text(encoding="utf-8"))
    body = prob["geometry"]["body"]
    if body.get("frame") not in ("installed", "design", prob.get("frames", {}).get("design")):
        print(f"ERROR   the body mesh is in frame {body.get('frame')!r}; orientation analysis needs the design frame")
        return 1
    root = _source_root(prob)
    if root is None:
        print("ERROR   the source checkout for this problem was not found; set its root_env or place it next to the repo")
        return 1
    mesh_path = root / body["path"]
    mesh = trimesh.load(mesh_path, force="mesh")
    card = load_card(prob["refs"]["material"])
    sf = next((r["min"] for r in prob["requirements"] if r.get("metric") == "fracture_factor"), 1.0)
    stress = StressField.load(a.stress) if a.stress else None
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False,
                                cwd=Path(__file__).parent).stdout.strip() or None
    except OSError:
        commit = None
    prov = {"problem": prob["id"],
            "mesh": {"path": body["path"], "sha256": hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
                     "frame": "design", "source": prob.get("generated_by", {}).get("source", {}).get("repo")},
            "generated": {"commit": commit, "catalog": prob["refs"].get("catalog"), "card": card.id,
                          "card_corner": "design", "fracture_factor": sf,
                          "stress": None if stress is None else {"path": Path(a.stress).name, **(stress.meta or {})}}}
    table = build_table(mesh.vertices, mesh.faces, card=card, stress=stress, sf=sf, sphere=a.sphere,
                        voxel=a.voxel, provenance=prov, interfaces=prob.get("interfaces"))
    out = a.out or Path("out") / prob["id"] / "orientation-table.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=1), encoding="utf-8")
    feas = [c for c in table["candidates"] if c["feasible"]]
    print(f"wrote {out}: {len(table['candidates'])} poses, {len(feas)} feasible")
    for c in table["candidates"][:5]:
        col = c["columns"]
        fl = col["F_L_max"]["value"]
        print(f"  rank {c['rank']!s:4} {c['id']:12} d={c['build_dir_design']} overhang {col['ovh_fail_mm2']['value']:.0f} mm2, "
              f"height {col['height_mm']['value']:.0f} mm, F_L max {'not checked' if fl is None else f'{fl:.3f}'}"
              + ("" if c["feasible"] else "  (infeasible: " + "; ".join(c["reasons"]) + ")"))
    return 0


def _cmd_coupons(a) -> int:
    from .coupons import plate, write_stl
    (v, f), meta = plate()
    a.out.mkdir(parents=True, exist_ok=True)
    write_stl(a.out / "ladder-plate.stl", v, f, "fdmgen overhang + bridge ladders")
    (a.out / "ladder-plate.json").write_text(json.dumps({"schema": "fdmgen/coupon-plate@0.1", "frame": "print",
                                                         "units": "mm", "rungs": meta}, indent=1), encoding="utf-8")
    print(f"wrote {a.out / 'ladder-plate.stl'} ({len(f)} triangles, {len(meta)} rungs) and ladder-plate.json")
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
    o = sub.add_parser("orient", help="rank candidate print orientations of a problem's body")
    o.add_argument("problem", type=Path)
    o.add_argument("--stress", type=Path, help="stress export NPZ (schema v1) for the F_L column")
    o.add_argument("--sphere", type=int, default=0, help="also sample N directions on the sphere")
    o.add_argument("--voxel", action="store_true", help="add V-level OVH-001 and BRG-001 on the D5 grid")
    o.add_argument("--out", type=Path)
    o.set_defaults(fn=_cmd_orient)
    cp = sub.add_parser("coupons", help="write the overhang + bridge ladder plate (STL + rung metadata)")
    cp.add_argument("--out", type=Path, default=Path("out/coupons"))
    cp.set_defaults(fn=_cmd_coupons)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
