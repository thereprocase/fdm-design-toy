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

    import numpy as np
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
    if a.gcode:
        from .orient.table import add_toolpath_columns
        pairs = dict(g.split("=", 1) for g in a.gcode)
        add_toolpath_columns(table, mesh.vertices, pairs)
    if a.export_poses:
        from .coupons import write_stl
        a.export_poses.mkdir(parents=True, exist_ok=True)
        for c in table["candidates"]:
            if c["feasible"]:
                V = mesh.vertices @ np.array(c["R_design_to_print"]).T + np.array(c["t_mm"])
                write_stl(a.export_poses / f"{c['id']}.stl", V, mesh.faces, f"{prob['id']} {c['id']} print frame")
        print(f"exported feasible poses to {a.export_poses} (print frame, bed-centred; slice with arrange/orient off)")
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


def _cmd_coupons_evidence(a) -> int:
    import hashlib

    from .coupons.evidence import slice_evidence
    plate = json.loads(a.plate.read_text(encoding="utf-8"))
    ev = slice_evidence(plate, a.gcode, a.plate.name, hashlib.sha256(a.plate.read_bytes()).hexdigest())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(ev, indent=1), encoding="utf-8")
    s = ev["gcode"]["settings"]
    print(f"wrote {a.out} ({ev['gcode']['generator']} {ev['gcode']['version']}, support {s['enable_support']} "
          f"threshold {s['support_threshold_angle']}, bridge_no_support {s['bridge_no_support']})")
    for r in ev["rungs"]:
        key = f"{r['alpha_deg']:.0f} deg" if "alpha_deg" in r else f"{r['span_mm']:.0f} mm"
        extra = f", longest bridge road {r['longest_bridge_road_mm']:.1f} mm" if "longest_bridge_road_mm" in r else ""
        print(f"  {r['id']:7} {key:7} support roads {r['support_segments']:5d}{extra}")
    return 0


def _cmd_modifier_spike(a) -> int:
    import shlex

    import yaml

    from .slicer.modifier_spike import capability_file, run_probes
    probes, extras = run_probes(a.template, a.work, shlex.split(a.orca))
    cap = capability_file(probes, extras)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    (a.work / "probes.json").write_text(json.dumps({"probes": probes, "extras": extras}, indent=1), encoding="utf-8")
    a.out.write_text("# Orca modifier capability file (issue #6, P0-D). GENERATED by fdmgen.slicer.modifier_spike; "
                     "CC BY 4.0.\n" + yaml.safe_dump(cap, sort_keys=False, width=110), encoding="utf-8")
    for r in cap["settings"]:
        print(f"  {r['key']:26} {r['status']:9} {r['non_local_side_effect'] or ''}")
    print(f"wrote {a.out}")
    return 0


def _cmd_massing(a) -> int:
    import os
    import zipfile

    import trimesh

    from .massing import export_plan, load_capabilities
    from .planning import load_draft
    table_bytes = a.table.read_bytes()
    table = json.loads(table_bytes)
    mesh = table["mesh"]
    repo = mesh.get("source")
    roots = [Path(os.environ["SPOOL_RACK_ROOT"])] if os.environ.get("SPOOL_RACK_ROOT") else []
    roots.append(Path(__file__).resolve().parents[3] / (repo or ""))
    mesh_path = next((r / mesh["path"] for r in roots if (r / mesh["path"]).is_file()), None)
    if mesh_path is None:
        print(f"ERROR   the body mesh {mesh['path']} was not found in the {repo} checkout")
        return 1
    try:
        plan = load_draft(a.draft.read_bytes(), table_bytes, mesh_path.read_bytes())
    except ValueError as e:
        print(f"ERROR   the draft cannot be used: {e}")
        return 1
    template = (zipfile.ZipFile(a.template).read("audit.3mf") if a.template.suffix == ".zip" else a.template.read_bytes())
    body = trimesh.load(mesh_path, force="mesh")
    try:
        data, report = export_plan(plan, body.vertices, body.faces, template, load_capabilities(a.capabilities),
                                   interfaces=table.get("interfaces"))
    except ValueError as e:
        print(f"ERROR   {e}")
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    stem = f"{plan.problem}-{plan.candidate_id}-massing"
    (a.out / f"{stem}.3mf").write_bytes(data)
    import dataclasses
    shell_data, _ = export_plan(dataclasses.replace(plan, shell_only=True), body.vertices, body.faces, template,
                                load_capabilities(a.capabilities))
    (a.out / f"{stem}-shell-only.3mf").write_bytes(shell_data)    # baseline for massing-evidence
    (a.out / f"{stem}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {a.out / (stem + '.3mf')}, {stem}-shell-only.3mf (baseline) and {stem}.json "
          f"({len(report['helpers'])} helpers)")
    for c in report["checks"]:
        print(f"  {c['verdict']:11} {c['message']}")
    if report.get("warning"):
        print(f"  WARNING     {report['warning']}")
    return 0 if all(c["verdict"] != "FAIL" for c in report["checks"]) else 2


def _cmd_massing_evidence(a) -> int:
    from .massing import slice_evidence
    report = json.loads(a.report.read_text(encoding="utf-8"))
    ev = slice_evidence(report, a.gcode.read_text(encoding="utf-8"),
                        a.baseline.read_text(encoding="utf-8") if a.baseline else None)
    out = a.out or a.report.with_name(a.report.stem + "-slice-evidence.json")
    out.write_text(json.dumps(ev, indent=1), encoding="utf-8")
    print(f"wrote {out}; {ev['slicer']['generator']} {ev['slicer']['version']}, placement shift "
          f"{ev['placement_shift_xy_mm']} mm, credited {ev['credited_mm3']} mm3")
    if ev["baseline_context_mismatch"]:
        print(f"  WARNING the baseline was sliced differently: {', '.join(ev['baseline_context_mismatch'])}")
    for h in ev["helpers"]:
        print(f"  {h['verdict']:5} {h['message']}")
    return 2 if any(h["verdict"] == "FAIL" for h in ev["helpers"]) else 0


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
    o.add_argument("--export-poses", type=Path, help="write each feasible pose as a print-frame STL into DIR")
    o.add_argument("--gcode", action="append", metavar="ID=PATH",
                   help="slice of pose ID (from --export-poses); adds T-level columns; repeatable")
    o.set_defaults(fn=_cmd_orient)
    cp = sub.add_parser("coupons", help="write the overhang + bridge ladder plate (STL + rung metadata)")
    cp.add_argument("--out", type=Path, default=Path("out/coupons"))
    cp.set_defaults(fn=_cmd_coupons)
    ce = sub.add_parser("coupons-evidence", help="pair a coupon plate with its sliced G-code (tier S receipt)")
    ce.add_argument("plate", type=Path, help="ladder-plate.json from 'fdmgen coupons'")
    ce.add_argument("gcode", type=Path)
    ce.add_argument("--out", type=Path, default=Path("out/coupons/slice-evidence.json"))
    ce.set_defaults(fn=_cmd_coupons_evidence)
    ms = sub.add_parser("modifier-spike", help="probe which per-modifier settings the slicer honours (P0-D)")
    ms.add_argument("template", type=Path, help="an Orca-written 3MF whose project settings define the context")
    ms.add_argument("--work", type=Path, default=Path("out/modifier-spike"))
    ms.add_argument("--orca", default="orca-slicer", help="slicer command prefix, e.g. 'flatpak run "
                    "--command=orca-slicer com.orcaslicer.OrcaSlicer --datadir DIR'")
    ms.add_argument("--out", type=Path, default=Path("out/modifier-capabilities.yaml"))
    ms.set_defaults(fn=_cmd_modifier_spike)
    mg = sub.add_parser("massing", help="turn a planning draft into an Orca project (body + helper modifiers)")
    mg.add_argument("draft", type=Path, help="fdmgen.massing-plan JSON exported by the planning workspace")
    mg.add_argument("--table", type=Path, required=True, help="the orientation table the draft was made from")
    mg.add_argument("--template", type=Path, required=True,
                    help="Orca-written 3MF (or slice-evidence zip with audit.3mf) that defines the profile context")
    mg.add_argument("--capabilities", type=Path,
                    default=Path(__file__).resolve().parents[2] / "catalog" / "slicer" /
                    "orca-2.4.2-p1s-asa-modifier-capabilities.yaml")
    mg.add_argument("--out", type=Path, default=Path("out/massing"))
    mg.set_defaults(fn=_cmd_massing)
    me = sub.add_parser("massing-evidence", help="read a slice of an exported massing project back (T level)")
    me.add_argument("report", type=Path, help="the .json report written by 'fdmgen massing'")
    me.add_argument("gcode", type=Path)
    me.add_argument("--baseline", type=Path, help="slice of the -shell-only.3mf written by 'fdmgen massing'")
    me.add_argument("--out", type=Path)
    me.set_defaults(fn=_cmd_massing_evidence)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
