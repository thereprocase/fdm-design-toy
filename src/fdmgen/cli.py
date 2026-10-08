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
                        voxel=a.voxel, provenance=prov, interfaces=prob.get("interfaces"), keep_outs=prob.get("keep_outs"))
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
    from .coupons import channel_plate, plate, write_stl
    if a.channel:
        (v, f), meta = channel_plate()
        stem, what = "channel-plate", "fdmgen channel ladder (slice with the part's own process)"
    else:
        (v, f), meta = plate()
        stem, what = "ladder-plate", "fdmgen overhang + bridge ladders"
    a.out.mkdir(parents=True, exist_ok=True)
    write_stl(a.out / f"{stem}.stl", v, f, what)
    (a.out / f"{stem}.json").write_text(json.dumps({"schema": "fdmgen/coupon-plate@0.1", "frame": "print",
                                                    "units": "mm", "rungs": meta}, indent=1), encoding="utf-8")
    print(f"wrote {a.out / (stem + '.stl')} ({len(f)} triangles, {len(meta)} rungs) and {stem}.json")
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
        key = (f"{r['alpha_deg']:.0f} deg" if "alpha_deg" in r else
               f"{r['span_mm']:.0f} mm" if "span_mm" in r else f"void {r['void_mm']:.0f}")
        extra = f", longest bridge road {r['longest_bridge_road_mm']:.1f} mm" if "longest_bridge_road_mm" in r else ""
        if r["kind"] == "channel":
            extra = (f", {r['bridge_roads']} bridge roads ({r['length_fraction_along']} of their length along), strand "
                     f"{r['strand_span_max_mm']} mm, ceiling {r['ceiling_span_max_mm']} mm")
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
    body = trimesh.load(mesh_path, force="mesh", process=False)      # raw STL order: no version-dependent merging
    try:
        import yaml
        prob_file = Path(__file__).resolve().parents[2] / "problems" / str(table.get("problem")) / "problem.yaml"
        keep_outs = table.get("keep_outs")                       # the pinned table first, then the problem file
        if keep_outs is None and prob_file.is_file():
            keep_outs = yaml.safe_load(prob_file.read_text(encoding="utf-8")).get("keep_outs")
        data, report = export_plan(plan, body.vertices, body.faces, template, load_capabilities(a.capabilities),
                                   interfaces=table.get("interfaces"), keep_outs=keep_outs)
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


def _cmd_report(a) -> int:
    import trimesh
    import yaml

    from .problem import lint_problem_file
    from .problem.lint import _source_root
    from .report import render_markdown, run_report
    prob = yaml.safe_load(a.problem.read_text(encoding="utf-8"))
    table = json.loads(a.table.read_text(encoding="utf-8"))
    cand = next((c for c in table["candidates"] if c["id"] == a.pose), None) if a.pose else table["candidates"][0]
    if cand is None:
        print(f"ERROR   pose {a.pose!r} is not in the table (have {[c['id'] for c in table['candidates']]})")
        return 1
    root = _source_root(prob)
    if root is None:
        print("ERROR   the problem's source checkout was not found")
        return 1
    mesh = trimesh.load(root / prob["geometry"]["body"]["path"], force="mesh", process=False)
    rep = run_report(prob, mesh.vertices, mesh.faces, cand, raster_px=a.px, workers=a.workers,
                     lint_findings=[str(f) for f in lint_problem_file(a.problem)])
    md = render_markdown(rep, {"problem file": str(a.problem), "orientation table": str(a.table),
                               "table sha256": hashlib_sha(a.table)})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(md, encoding="utf-8")
    fails = [r for r in rep["results"] if r.verdict.value == "FAIL"]
    print(f"wrote {a.out}: {len(rep['results'])} checks, {len(fails)} FAIL, evidence rung {rep['ladder_rung']}")
    return 2 if fails else 0


def hashlib_sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cmd_massing_seed(a) -> int:
    import trimesh
    import yaml

    from .massing.seed import dumps, load_stress_for_seed, seed_draft
    from .materials import load_card
    tb = a.table.read_bytes()
    table = json.loads(tb)
    roots = [Path(__file__).resolve().parents[3] / str(table["mesh"].get("source") or "")]
    import os
    if os.environ.get("SPOOL_RACK_ROOT"):
        roots.insert(0, Path(os.environ["SPOOL_RACK_ROOT"]))
    mesh_path = next((r / table["mesh"]["path"] for r in roots if (r / table["mesh"]["path"]).is_file()), None)
    if mesh_path is None:
        print(f"ERROR   the body mesh {table['mesh']['path']} was not found")
        return 1
    prob_file = Path(__file__).resolve().parents[2] / "problems" / str(table.get("problem")) / "problem.yaml"
    prob = yaml.safe_load(prob_file.read_text(encoding="utf-8")) if prob_file.is_file() else {}
    restraints = [s["at"] for s in prob.get("supports", []) if s.get("at")]
    settings = (prob.get("process") or {}).get("settings", {})
    walls = int(settings.get("wall_loops", 4))
    skin = float(settings.get("top_shell_layers", 8)) * float(settings.get("layer_height", 0.2))
    sf, sbytes = load_stress_for_seed(a.stress)
    body = trimesh.load(mesh_path, force="mesh", process=False)
    draft = seed_draft(table, tb, body.vertices, sf, sbytes, load_card(a.card), pose_id=a.pose, walls=walls, skin_mm=skin,
                       restraint_ids=restraints, restraint_margin_mm=a.margin, clearance_mm=a.clearance)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(dumps(draft))
    p = draft["proposal"]
    print(f"wrote {a.out}: {p['status']}, {len(p['accepted'])} helpers, {len(p['rejected'])} clusters rejected "
          f"(restraints {restraints}, margin {a.margin} mm)")
    for r in p["sensitivity"]:
        print(f"  margin {r['restraint_margin_mm']:5.1f} mm -> clusters {r['accepted_clusters']}")
    return 0


def _cmd_gcode_occupancy(a) -> int:
    import hashlib

    import numpy as np

    from .gcode import extruder_offset, read_gcode
    from .gcode.occupancy import occupancy, plate_to_grid
    table = json.loads(a.table.read_text(encoding="utf-8"))
    cand = next((c for c in table["candidates"] if c["id"] == a.pose), None)
    if cand is None:
        print(f"ERROR   pose {a.pose!r} is not in the table")
        return 1
    rec = json.loads(a.grid_receipt.read_text(encoding="utf-8"))
    g, i2p = rec["grid"], rec["installed_to_print"]
    if rec.get("frame") != "installed" or table["mesh"]["frame"] != "design":
        print("ERROR   the grid receipt must map the installed (= design) frame to its print grid")
        return 1
    M, c = plate_to_grid(cand["R_design_to_print"], cand["t_mm"], i2p["R"], i2p["t_mm"])
    rep_json = json.loads(a.report.read_text(encoding="utf-8")) if a.report else None
    raw = a.gcode.read_bytes()
    text = raw.decode("utf-8")
    tp = read_gcode(text)
    out = occupancy(tp, extruder_offset(text), M, c, np.asarray(g["origin_print_mm"]), np.asarray(g["h_mm"]),
                    tuple(g["shape"]), threshold=a.threshold)
    acct = out.pop("accounting")
    prov = {"schema": "fdmgen/occupancy@0.1", "gcode_sha256": hashlib.sha256(raw).hexdigest(),
            "table_sha256": hashlib.sha256(a.table.read_bytes()).hexdigest(), "pose": a.pose,
            "grid_receipt": a.grid_receipt.name, "grid_receipt_sha256": hashlib.sha256(a.grid_receipt.read_bytes()).hexdigest(),
            "grid_frame": "solver print grid of the receipt (installed -> print by installed_to_print)",
            "grid": g, "installed_to_print": i2p, "pose_R_design_to_print": cand["R_design_to_print"],
            "pose_t_mm": cand["t_mm"], "indexing": "C order, axes x y z", "accounting": acct,
            "density_kind": {"density": "raw: deposited volume / cell volume, exceeds 1 where beads overlap",
                             "density_capped": "min(raw, 1)", "solid_mask": f"raw density >= {a.threshold}"},
            **({"project_3mf_sha256": rep_json["project_3mf_sha256"], "plan": rep_json.get("plan")} if rep_json else {}),
            "note": "approximate bead raster of the slicer's credited roads; not a measured print"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, **{k: v for k, v in out.items()}, provenance=np.array(json.dumps(prov)))
    a.out.with_suffix(".json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print(f"wrote {a.out}: credited {acct['credited_input_mm3']:.1f} mm3, inside grid {acct['deposited_inside_grid_mm3']:.1f}, "
          f"clipped {acct['clipped_outside_grid_mm3']:.3f}, saturation excess {acct['saturation_excess_mm3']:.1f}, "
          f"solid cells {acct['solid_cells']} (density >= {a.threshold})")
    return 0


def _shell_check_provenance(a, text, tp, table, cand, mesh_path, origin, shape, outside) -> dict:
    """Everything needed to say which slice, part, pose, grid and method a SHELL-001 receipt measured.
    Paths are recorded as the table gives them (relative), never as resolved on this machine."""
    import hashlib
    import inspect

    from .catalog.checks import shell, toolpath
    from .gcode import extruder_offset, reader
    from .gcode import occupancy as occ
    from .massing.export import _slicer_context

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def defaults(fn, *names):
        sig = inspect.signature(fn).parameters
        return {n: sig[n].default for n in names}

    chk = defaults(shell.check_shell, "seed", "min_beads", "bead_spacing_mm", "layer_mm", "thin_fraction_limit",
                   "outer_width_mm")
    return {
        "gcode": {**_slicer_context(text, tp), "extruder_offset_mm": list(extruder_offset(text))},
        **_pose_provenance(a, table, cand, mesh_path),
        "grid": {"frame": "print (plate) frame of the pose", "origin_mm": [float(x) for x in origin],
                 "cell_mm": a.cell, "shape": list(shape), "clipped_outside_grid_mm3": outside},
        "method": {"deposit": {"roads": "credited", "caps": True, "step_frac": 0.5},
                   "tie_break_mm": shell.TIE_BREAK_MM,
                   "surface_samples": a.samples, **chk,
                   "march": defaults(shell.march, "step_mm", "max_mm", "empty"),
                   "entry_mm": chk["outer_width_mm"] / 2 + 1.5 * a.cell},
        "source_sha256": {f"fdmgen/{Path(m.__file__).relative_to(Path(__file__).parent).as_posix()}": sha(m.__file__)
                          for m in (shell, occ, reader, toolpath)},
    }


def _cmd_orient_shell(a) -> int:
    return _orient_enrich(a, "shell")


def _cmd_orient_bridge(a) -> int:
    return _orient_enrich(a, "bridge")


def _orient_enrich(a, what: str) -> int:
    import hashlib

    from .orient.table import add_bridge_columns, add_shell_columns
    raw = a.table.read_bytes()
    receipts = []
    for path, kind in a.receipt:
        rb = Path(path).read_bytes()
        receipts.append((json.loads(rb), hashlib.sha256(rb).hexdigest(), kind))
    fn = add_shell_columns if what == "shell" else add_bridge_columns
    try:
        out = fn(json.loads(raw), hashlib.sha256(raw).hexdigest(), receipts)
    except ValueError as e:
        print(f"ERROR   {e}")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for c in out["candidates"]:
        col = c["columns"]
        if what == "shell" and "t_shell_thin_fraction" in col:
            x = col["t_shell_thin_fraction"]
            print(f"  {c['id']}: SHELL-001 T {x['verdict']} thin {100 * x['value']:.2f} % ({x['receipt']['slice_kind']})")
        if what == "bridge" and "t_bridge_span_external_mm" in col:
            e, i = col["t_bridge_span_external_mm"], col["t_bridge_span_internal_mm"]
            print(f"  {c['id']}: BRG-001 T external {e['value']} mm {e['verdict']}, internal {i['value']} mm {i['verdict']} "
                  f"({e['receipt']['slice_kind']})")
    print(f"wrote {a.out} (receipts pinned to table {out['enriched']['from_table_sha256'][:12]})")
    return 0


def _cmd_bridge_check(a) -> int:
    import hashlib
    import inspect

    import numpy as np

    from .catalog.checks import toolpath
    from .gcode import extruder_offset, read_gcode, reader
    from .gcode import occupancy as occ
    from .massing.export import _slicer_context
    a.out.unlink(missing_ok=True)          # a failed run must not leave an older receipt looking current
    if (a.table is None) != (a.pose is None):
        print("ERROR   give --table and --pose together (or neither)")
        return 1
    raw = a.gcode.read_bytes()
    text = raw.decode("utf-8")
    tp = read_gcode(text)
    off = extruder_offset(text)
    pose_block = {}
    if a.table is not None:
        posed = _posed_body(a.table, a.pose)
        if isinstance(posed, str):
            print(f"ERROR   {posed}")
            return 1
        table, cand, mesh_path, body, V = posed
        try:
            placed = toolpath.verify_pose(tp, V, body.faces, off)
        except ValueError as e:
            print(f"ERROR   this slice is not pose {a.pose}: {e}")
            return 1
        pose_block = {**_pose_provenance(a, table, cand, mesh_path), "placement": placed}
    r = toolpath.check_bridge_toolpath(tp, offset=off, cell_mm=a.cell)
    if pose_block:                       # the worst roads in the pose's print frame and in the design frame too
        shift = np.append(pose_block["placement"]["shift_xy_mm"], 0.0)
        R, t = np.asarray(cand["R_design_to_print"], float), np.asarray(cand["t_mm"], float)
        for per_role in r.metrics["worst"].values():
            for w in per_role.values():
                if w is None:
                    continue
                pr = {k: (None if v is None else [round(float(x), 4) for x in np.asarray(v) - shift])
                      for k, v in w["plate_mm"].items()}
                w["print_mm"] = pr
                w["design_mm"] = {k: (None if v is None else [round(float(x), 4) for x in R.T @ (np.asarray(v) - t)])
                                  for k, v in pr.items()}
        r.metrics["worst_frames"] = {"plate_mm": "G-code coordinates with the extruder offset restored",
                                     "print_mm": "plate minus the measured placement shift (the pose's print frame)",
                                     "design_mm": "R_design_to_print^T (print - t_mm)"}
    sig = {**inspect.signature(toolpath.bridge_spans).parameters, **inspect.signature(toolpath.check_bridge_toolpath).parameters}
    out = {"schema": "fdmgen/bridge-check@0.2", "result": r.to_dict(),
           "gcode": {**_slicer_context(text, tp), "extruder_offset_mm": list(off)}, **pose_block,
           "method": {"cell_mm": a.cell, "support_density": sig["support_density"].default,
                      "margin_mm": sig["margin_mm"].default, "caps": True,
                      "max_span_external_mm": sig["max_span_external_mm"].default,
                      "max_span_internal_mm": sig["max_span_internal_mm"].default},
           "source_sha256": {f"fdmgen/{Path(m.__file__).relative_to(Path(__file__).parent).as_posix()}":
                             hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (toolpath, occ, reader)}}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(r.message)
    return 2 if r.verdict.value == "FAIL" else 0


def _posed_body(table_path: Path, pose: str):
    """(table dict, candidate, mesh path, trimesh body, posed vertices) or an error message string."""
    import numpy as np
    import trimesh
    table = json.loads(table_path.read_text(encoding="utf-8"))
    cand = next((c for c in table["candidates"] if c["id"] == pose), None)
    if cand is None:
        return f"pose {pose!r} is not in the table"
    roots = ([Path(os.environ["SPOOL_RACK_ROOT"])] if os.environ.get("SPOOL_RACK_ROOT") else []) + \
        [Path(__file__).resolve().parents[3] / str(table["mesh"].get("source") or "")]
    mesh_path = next((r / table["mesh"]["path"] for r in roots if (r / table["mesh"]["path"]).is_file()), None)
    if mesh_path is None:
        return f"the body mesh {table['mesh']['path']} was not found"
    body = trimesh.load(mesh_path, force="mesh", process=True)
    V = body.vertices @ np.asarray(cand["R_design_to_print"]).T + np.asarray(cand["t_mm"])
    return table, cand, mesh_path, body, V


def _pose_provenance(a, table, cand, mesh_path) -> dict:
    """Table, mesh and pose block shared by the shell and bridge receipts (paths as the table gives them)."""
    import hashlib

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {"pose": {"id": a.pose, "R_design_to_print": cand["R_design_to_print"], "t_mm": cand["t_mm"]},
            "table": {"name": a.table.name, "sha256": sha(a.table)},
            "mesh": {"path": table["mesh"]["path"], "source": table["mesh"].get("source"),
                     "frame": table["mesh"].get("frame"), "sha256": sha(mesh_path)}}


def _cmd_evidence(a) -> int:
    from .evidence import build_bundle
    try:
        m = build_bundle(a.report, a.project, a.baseline, a.table, a.pose, a.out, shell_cell_mm=a.shell_cell,
                         shell_samples=a.samples)
    except RuntimeError as e:
        print(f"ERROR   {e}")
        return 1
    print(f"wrote {a.out / 'evidence-bundle.json'}")
    for r in m["receipts"]:
        print(f"  {r['check']:16s} {r['slice_kind']:10s} {r['verdict']:12s} {r['sha256'][:12]}")
    for check, d in m["paired"].items():
        print(f"  paired {check}: " + ("; ".join(f"{k} {v['delta']:+g}" for k, v in d.items()) if "withheld" not in d
                                       else "withheld: " + "; ".join(d["withheld"])))
    return 2 if any(r["verdict"] == "FAIL" for r in m["receipts"]) else 0


def _cmd_keepout_render(a) -> int:
    import hashlib

    import trimesh
    import yaml

    from .catalog.checks.keepout import render_items

    def sha(b):
        return hashlib.sha256(b).hexdigest()
    a.out.unlink(missing_ok=True)          # a failed run must not leave an older receipt looking current
    traw, praw = a.table.read_bytes(), a.problem.read_bytes()
    table, prob = json.loads(traw), yaml.safe_load(praw)
    if (prob.get("frames") or {}).get("design") != "installed":
        print("ERROR   the problem does not declare frames.design = installed, so no installed-to-design transform is known")
        return 1
    if (prob.get("keep_outs") or []) != (table.get("keep_outs") or []):
        print("ERROR   the table's keep_outs differ from the problem's; render from the problem the table was built from")
        return 1
    roots = ([Path(os.environ["SPOOL_RACK_ROOT"])] if os.environ.get("SPOOL_RACK_ROOT") else []) + \
        [Path(__file__).resolve().parents[3] / str(table["mesh"].get("source") or "")]
    mesh_path = next((r / table["mesh"]["path"] for r in roots if (r / table["mesh"]["path"]).is_file()), None)
    if mesh_path is None:
        print(f"ERROR   the body mesh {table['mesh']['path']} was not found")
        return 1
    mraw = mesh_path.read_bytes()
    if sha(mraw) != table["mesh"].get("sha256"):
        print("ERROR   the body mesh on disk is not the one the table pins")
        return 1
    body = trimesh.load(mesh_path, force="mesh", process=False)
    geo = render_items(table.get("keep_outs"), table.get("interfaces"), body.vertices.min(axis=0), body.vertices.max(axis=0),
                       margin_mm=a.margin)
    out = {"schema": "fdmgen/keepout-render@0.1", "units": "mm", "frame": "design",
           "scope": "render only: where the keep-outs are, for a viewer; the KEEP-OUT and KEEP-CLEAR checks decide clearance",
           "table": {"name": a.table.name, "sha256": sha(traw)},
           "mesh": {"path": table["mesh"]["path"], "source": table["mesh"].get("source"), "sha256": sha(mraw)},
           "problem": {"name": a.problem.name, "sha256": sha(praw), "frames": prob["frames"]},
           "installed_to_design": {"R": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], "t_mm": [0.0, 0.0, 0.0],
                                   "source": "problem frames.design = installed (identity)"},
           **geo}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {a.out}: " + ", ".join(f"{i['id']} ({'drawn' if i['rendered'] else 'not drawn'})" for i in out["items"]))
    return 0


def _cmd_orient_evidence(a) -> int:
    from .evidence import build_orient_bundle
    try:
        m = build_orient_bundle(a.table, [(p, k, Path(g)) for p, k, g in a.slice], a.out, shell_cell_mm=a.shell_cell,
                                shell_samples=a.samples)
    except RuntimeError as e:
        print(f"ERROR   {e}")
        return 1
    print(f"wrote {a.out / 'orient-evidence.json'} and {m['enriched_table']['path']}")
    for r in m["receipts"]:
        print(f"  {r['pose']:10s} {r['slice_kind']:10s} {r['check']:13s} {r['verdict']:12s} {r['sha256'][:12]}")
    return 2 if any(r["verdict"] == "FAIL" for r in m["receipts"]) else 0


def _cmd_shell_check(a) -> int:
    import numpy as np

    from .catalog.checks.shell import check_shell, grid_origin
    from .gcode import extruder_offset, read_gcode
    from .gcode.occupancy import deposit
    a.out.unlink(missing_ok=True)          # a failed run must not leave an older receipt looking current
    posed = _posed_body(a.table, a.pose)
    if isinstance(posed, str):
        print(f"ERROR   {posed}")
        return 1
    table, cand, mesh_path, body, V = posed
    raw = a.gcode.read_bytes()
    text = raw.decode("utf-8")
    tp = read_gcode(text)
    from .catalog.checks.toolpath import verify_pose
    try:
        placed = verify_pose(tp, V, body.faces, extruder_offset(text))
    except ValueError as e:
        print(f"ERROR   this slice is not pose {a.pose}: {e}")
        return 1
    origin = grid_origin(V.min(axis=0))
    shape = tuple(int(x) for x in np.ceil((V.max(axis=0) + 1.0 - origin) / a.cell))
    # the slice's object may sit shifted on the plate; take the measured shift out so roads land on the posed body
    off = np.asarray(extruder_offset(text), float) - np.append(placed["shift_xy_mm"], 0.0)
    placed["deposit_offset_mm"] = [float(x) for x in off]
    vgrid, outside = deposit(tp, off, np.eye(3), np.zeros(3), origin, a.cell, shape, step_frac=0.5,
                             caps=True)
    r = check_shell(vgrid / a.cell ** 3, origin, a.cell, V, body.faces, n_samples=a.samples)
    out = {"schema": "fdmgen/shell-check@0.3", "result": r.to_dict(),
           **_shell_check_provenance(a, text, tp, table, cand, mesh_path, origin, shape, outside), "placement": placed}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(r.message)
    for b in r.metrics["bands"]:
        print(f"  slope {b['slope_deg']} deg: {b['samples']} samples, thin {100 * b['thin_fraction']:.1f} %, "
              f"median {b['median_mm']} mm (needs {b['required_mm']}), p05 {b['p05_mm']}")
    return 2 if r.verdict.value == "FAIL" else 0


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
    cp.add_argument("--channel", action="store_true", help="the channel ladder instead (internal bridges along a bar)")
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
    rp = sub.add_parser("report", help="design report: every check for one problem in one pose (Markdown)")
    rp.add_argument("problem", type=Path)
    rp.add_argument("--table", type=Path, required=True)
    rp.add_argument("--pose", help="candidate id (default: the table's first-ranked)")
    rp.add_argument("--px", type=float, default=0.1, help="raster cell size for width/gap/bridge checks (mm)")
    rp.add_argument("--workers", type=int, default=1, help="processes for the per-layer checks (use a big machine)")
    rp.add_argument("--out", type=Path, default=Path("out/report.md"))
    rp.set_defaults(fn=_cmd_report)
    sd = sub.add_parser("massing-seed", help="machine proposal: helper boxes over high-F_L clusters (a v0.3 draft)")
    sd.add_argument("--table", type=Path, required=True)
    sd.add_argument("--stress", type=Path, required=True, help="stress export NPZ (schema v1) with its receipt")
    sd.add_argument("--pose", help="candidate id (default: first ranked)")
    sd.add_argument("--card", default="polymaker-polylite-asa-t0")
    sd.add_argument("--margin", type=float, default=4.8, help="reject clusters this close to a modelled restraint (mm)")
    sd.add_argument("--clearance", type=float, default=0.5, help="keep-clear clearance written for every interface (mm)")
    sd.add_argument("--out", type=Path, default=Path("out/massing/seed-draft.json"))
    sd.set_defaults(fn=_cmd_massing_seed)
    go = sub.add_parser("gcode-occupancy", help="credited roads of a slice -> density grid on a solver grid (NPZ)")
    go.add_argument("gcode", type=Path)
    go.add_argument("--table", type=Path, required=True, help="orientation table holding the sliced pose")
    go.add_argument("--pose", required=True)
    go.add_argument("--grid-receipt", type=Path, required=True, help="solver receipt with grid + installed_to_print")
    go.add_argument("--threshold", type=float, default=0.5)
    go.add_argument("--report", type=Path, help="fdmgen massing report of the sliced project (adds project sha + plan)")
    go.add_argument("--out", type=Path, required=True)
    go.set_defaults(fn=_cmd_gcode_occupancy)
    osh = sub.add_parser("orient-shell", help="new orientation table with a SHELL-001 T column from shell-check receipts")
    osh.add_argument("table", type=Path, help="the orientation table the receipts were measured against")
    osh.add_argument("--receipt", nargs=2, action="append", required=True, metavar=("RECEIPT", "KIND"),
                     help="a shell-check@0.2 receipt and its slice kind: shell-only or project")
    osh.add_argument("--out", type=Path, required=True)
    osh.set_defaults(fn=_cmd_orient_shell)
    bc = sub.add_parser("bridge-check", help="BRG-001 at T level: longest unsupported bridge run in a slice")
    bc.add_argument("gcode", type=Path)
    bc.add_argument("--cell", type=float, default=0.1, help="raster cell of the layer below (mm)")
    bc.add_argument("--table", type=Path, help="orientation table the slice was made from (with --pose)")
    bc.add_argument("--pose", help="candidate id in --table; the slice footprint is verified against it")
    bc.add_argument("--out", type=Path, default=Path("out/bridge-check.json"))
    bc.set_defaults(fn=_cmd_bridge_check)
    obr = sub.add_parser("orient-bridge", help="new orientation table with BRG-001 T span columns from bridge-check receipts")
    obr.add_argument("table", type=Path, help="the pinned orientation table, or one already enriched from it")
    obr.add_argument("--receipt", nargs=2, action="append", required=True, metavar=("RECEIPT", "KIND"),
                     help="a bridge-check@0.2 receipt made with --table/--pose, and its slice kind: shell-only or project")
    obr.add_argument("--out", type=Path, required=True)
    obr.set_defaults(fn=_cmd_orient_bridge)
    ev = sub.add_parser("evidence", help="every T-level receipt for a project slice and its shell-only baseline, one manifest")
    ev.add_argument("report", type=Path, help="the .json report written by 'fdmgen massing'")
    ev.add_argument("project", type=Path, help="slice of the massing project")
    ev.add_argument("baseline", type=Path, help="slice of the -shell-only project")
    ev.add_argument("--table", type=Path, required=True)
    ev.add_argument("--pose", required=True)
    ev.add_argument("--shell-cell", type=float, default=0.1)
    ev.add_argument("--samples", type=int, default=20000)
    ev.add_argument("--out", type=Path, required=True, help="bundle directory")
    ev.set_defaults(fn=_cmd_evidence)
    kr = sub.add_parser("keepout-render", help="render-only keep-out geometry for a viewer (sidecar to an orientation table)")
    kr.add_argument("table", type=Path)
    kr.add_argument("--problem", type=Path, required=True, help="the problem.yaml the table was built from")
    kr.add_argument("--margin", type=float, default=10.0, help="clip margin around the body for open bounds (mm)")
    kr.add_argument("--out", type=Path, required=True)
    kr.set_defaults(fn=_cmd_keepout_render)
    oe = sub.add_parser("orient-evidence", help="shell + bridge receipts per pose slice and one enriched orientation table")
    oe.add_argument("table", type=Path, help="the pinned orientation table the slices were made from")
    oe.add_argument("--slice", nargs=3, action="append", required=True, metavar=("POSE", "KIND", "GCODE"),
                    help="a pose id, its slice kind (shell-only or project) and the slice's G-code; repeat per pose")
    oe.add_argument("--shell-cell", type=float, default=0.1)
    oe.add_argument("--samples", type=int, default=20000)
    oe.add_argument("--out", type=Path, required=True, help="output directory")
    oe.set_defaults(fn=_cmd_orient_evidence)
    sc = sub.add_parser("shell-check", help="SHELL-001 at T level: printed shell thickness by slope from a slice")
    sc.add_argument("gcode", type=Path, help="slice of the posed body (plate coordinates = the table's pose)")
    sc.add_argument("--table", type=Path, required=True)
    sc.add_argument("--pose", required=True)
    sc.add_argument("--cell", type=float, default=0.2, help="raster cell size (mm); heavy below 0.2 for whole parts")
    sc.add_argument("--samples", type=int, default=20000)
    sc.add_argument("--out", type=Path, default=Path("out/shell-check.json"))
    sc.set_defaults(fn=_cmd_shell_check)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
