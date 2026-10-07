"""Canonical G-code reader: extrusion segments, credited vs sacrificial material, frame chain (PLAN D3)."""
from .frames import (
                     build_transform_from_3mf,
                     extruder_offset,
                     gcode_to_model,
                     placed_component_bbox,
                     undo_xy_shrink,
                     xy_scale_vs_model,
)
from .reader import FooterMismatch, Toolpath, credit, read_gcode

__all__ = ["FooterMismatch", "Toolpath", "build_transform_from_3mf", "credit", "extruder_offset", "gcode_to_model",
           "placed_component_bbox", "read_gcode", "undo_xy_shrink", "xy_scale_vs_model"]
