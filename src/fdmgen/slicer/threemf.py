"""Write an Orca project 3MF from parts already placed on the plate (PLAN D3: body + modifiers + settings).

The project settings (printer, process, filament) come unchanged from an Orca-written template 3MF, so
a slice of the output runs under exactly the template's profile context. Parts are given in plate
coordinates (mm, bed corner origin, z up), e.g. a pose from the orientation table applied to the body
and to every helper. Per-part settings are written as part metadata, the way Orca stores modifier
overrides; which of them Orca honours is recorded in catalog/slicer/*-modifier-capabilities.yaml.
"""
from __future__ import annotations

import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

import numpy as np

M = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
P = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
NS = {"m": M, "p": P}
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"
IDENTITY4 = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"


@dataclass
class Part:
    name: str
    vertices: np.ndarray                  # (n, 3) plate frame, mm
    faces: np.ndarray                     # (m, 3) outward wound
    subtype: str = "normal_part"          # normal_part | modifier_part
    settings: dict = field(default_factory=dict)


def _mesh_object(parent, oid, part: Part):
    o = ET.SubElement(parent, f"{{{M}}}object", {"id": str(oid), f"{{{P}}}UUID": str(uuid.uuid5(uuid.NAMESPACE_URL, f"fdmgen/{oid}/{part.name}")),
                                               "type": "model"})
    mesh = ET.SubElement(o, f"{{{M}}}mesh")
    vs = ET.SubElement(mesh, f"{{{M}}}vertices")
    for x, y, z in np.asarray(part.vertices, float):
        ET.SubElement(vs, f"{{{M}}}vertex", x=f"{x:.6f}", y=f"{y:.6f}", z=f"{z:.6f}")
    ts = ET.SubElement(mesh, f"{{{M}}}triangles")
    for a, b, c in np.asarray(part.faces, int):
        ET.SubElement(ts, f"{{{M}}}triangle", v1=str(a), v2=str(b), v3=str(c))


def write_project(template: bytes, parts: list[Part], *, object_name: str, object_settings: dict | None = None) -> bytes:
    """Orca 3MF with one object made of `parts` (the first must be the normal_part body)."""
    if not parts or parts[0].subtype != "normal_part":
        raise ValueError("the first part must be the body (subtype normal_part)")
    bad = [p.name for p in parts if p.subtype not in ("normal_part", "modifier_part")]
    if bad:
        raise ValueError(f"unknown part subtype for {bad}; use normal_part or modifier_part")
    for prefix, uri in (("", M), ("p", P), ("BambuStudio", "http://schemas.bambulab.com/package/2021")):
        ET.register_namespace(prefix, uri)
    zin = zipfile.ZipFile(io.BytesIO(template))
    root = ET.fromstring(zin.read("3D/3dmodel.model"))
    old_path = root.find(".//m:component", NS).get(f"{{{P}}}path")
    asm_id = len(parts) + 1
    # main model: one assembly object whose components are the parts, identity transforms (parts are on the plate)
    res = root.find("m:resources", NS)
    for o in list(res):
        res.remove(o)
    asm = ET.SubElement(res, f"{{{M}}}object", {"id": str(asm_id), f"{{{P}}}UUID": str(uuid.uuid5(uuid.NAMESPACE_URL, f"fdmgen/asm/{object_name}")),
                                               "type": "model"})
    comps = ET.SubElement(asm, f"{{{M}}}components")
    for i, _ in enumerate(parts, 1):
        ET.SubElement(comps, f"{{{M}}}component", {f"{{{P}}}path": old_path, "objectid": str(i),
                                                   f"{{{P}}}UUID": str(uuid.uuid5(uuid.NAMESPACE_URL, f"fdmgen/c{i}")),
                                                   "transform": IDENTITY})
    item = root.find("m:build/m:item", NS)
    item.set("objectid", str(asm_id))
    item.set("transform", IDENTITY)
    for md in root.findall("m:metadata", NS):
        if md.get("name") == "Title":
            md.text = object_name
    # object file with the part meshes
    oroot = ET.Element(f"{{{M}}}model", {"unit": "millimeter", "xml:lang": "en-US", "requiredextensions": "p"})
    ores = ET.SubElement(oroot, f"{{{M}}}resources")
    for i, p in enumerate(parts, 1):
        _mesh_object(ores, i, p)
    # model settings: object-level settings from the template object, then the requested ones; one entry per part
    croot = ET.fromstring(zin.read("Metadata/model_settings.config"))
    tobj = croot.find("object")
    obj = ET.Element("object", id=str(asm_id))
    settings = {md.get("key"): md.get("value") for md in tobj.findall("metadata")}
    settings["name"] = object_name
    settings.update({k: str(v) for k, v in (object_settings or {}).items()})
    for k, v in settings.items():
        ET.SubElement(obj, "metadata", key=k, value=v)
    for i, p in enumerate(parts, 1):
        pe = ET.SubElement(obj, "part", id=str(i), subtype=p.subtype)
        for k, v in (("name", p.name), ("matrix", IDENTITY4), ("source_file", f"{p.name}.stl"), ("source_object_id", "-1"),
                     ("source_volume_id", "-1"), ("source_offset_x", "0"), ("source_offset_y", "0"), ("source_offset_z", "0")):
            ET.SubElement(pe, "metadata", key=k, value=v)
        for k, v in p.settings.items():
            ET.SubElement(pe, "metadata", key=k, value=str(v))
    croot.remove(tobj)
    croot.insert(0, obj)
    for mi in croot.iter("model_instance"):
        for md in mi.findall("metadata"):
            if md.get("key") == "object_id":
                md.set("value", str(asm_id))
    for plate in croot.iter("plate"):
        for md in list(plate.findall("metadata")):
            if md.get("key") in ("gcode_file", "thumbnail_file", "thumbnail_no_light_file", "top_file", "pick_file"):
                plate.remove(md)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in zin.namelist():
            if name in ("Metadata/plate_1.gcode", "Metadata/plate_1.gcode.md5", "Metadata/_rels/model_settings.config.rels") \
                    or name.endswith(".png"):
                continue
            if name == "3D/3dmodel.model":
                data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
            elif name == old_path.lstrip("/"):
                data = ET.tostring(oroot, xml_declaration=True, encoding="UTF-8")
            elif name == "Metadata/model_settings.config":
                data = ET.tostring(croot, xml_declaration=True, encoding="UTF-8")
            else:
                data = zin.read(name)
            z.writestr(name, data)
    return out.getvalue()
