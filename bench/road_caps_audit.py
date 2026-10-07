"""Synthetic road segmentation audit of optional deposition caps, not print evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import inspect
import math
from pathlib import Path
import numpy as np
from fdmgen.gcode import read_gcode
from fdmgen.gcode.occupancy import deposit


def road_code(segments):
    # Same 10 mm centreline, bead dimensions and nominal extrusion per unit length.
    area = math.pi*1.75**2/4
    e = .42*.2*10/segments/area
    lines = ['; filament_diameter: 1.75', 'M83', 'G90', '; printing object part',
             ';TYPE:Outer wall', ';Z:0.2', ';HEIGHT:0.2', ';WIDTH:0.42',
             'G1 X0 Y0 Z0.2']
    lines += [f'G1 X{10*k/segments:.12f} Y0 E{e:.15f}' for k in range(1, segments+1)]
    return '\n'.join(lines+['; stop printing object part', ''])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--step-frac', type=float, default=.2)
    args = ap.parse_args()
    if not np.isfinite(args.step_frac) or not 0 < args.step_frac <= 1:
        ap.error('step-frac must be in (0, 1]')
    origin = np.array([-1., -1., -.1])+1e-4*np.pi
    h = .1; shape = (125, 25, 5); step_frac = args.step_frac
    fields = {}; rows = []
    for segments in (1, 10, 100):
        code = road_code(segments); tp = read_gcode(code, footer_rel_tol=None)
        for caps in (False, True):
            v, outside = deposit(tp, (0, 0, 0), np.eye(3), np.zeros(3), origin, h, shape,
                                 step_frac=step_frac, caps=caps)
            credited = float(tp.volume.sum())
            if not np.isclose(v.sum()+outside, credited, rtol=1e-12, atol=1e-12):
                raise ValueError('deposition failed volume accounting')
            fields[segments, caps] = v
            rows.append(dict(segments=segments, caps=caps, gcode_sha256=hashlib.sha256(code.encode()).hexdigest(),
                credited_mm3=credited, deposited_mm3=float(v.sum()), outside_mm3=outside,
                density_sha256=hashlib.sha256((v/h**3).astype('<f8').tobytes()).hexdigest(),
                solid_cells_at_half_density=int((v/h**3 >= .5).sum()),
                # Half L1 is the volume that must be reassigned to match the comparator.
                moved_vs_one_segment_mm3=float(np.abs(v-fields[1, caps]).sum()/2),
                moved_vs_uncapped_mm3=float(np.abs(v-fields[segments, False]).sum()/2)))
    result = dict(schema='fdmgen/road-caps-audit@0.1',
        geometry=dict(length_mm=10, width_mm=.42, height_mm=.2),
        grid=dict(origin_mm=origin.tolist(), h_mm=h, shape=shape, step_frac=step_frac),
        producer='deposit: default rectangular roads vs optional caps at the pinned implementation',
        producer_source_sha256=hashlib.sha256(Path(inspect.getfile(deposit)).read_bytes()).hexdigest(),
        establishes='synthetic volume accounting and sensitivity to collinear G-code segmentation',
        does_not_establish=['physical bead corner geometry', 'preferred cap model', 'actual bracket sensitivity',
                           'shell qualification', 'mechanical effect'], rows=rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
