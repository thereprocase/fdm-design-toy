"""Issue #5 geometry timing receipt; synthetic runs do not establish bracket acceptance.

python bench/geometry.py --mesh body.stl --h 0.4 --out geometry.json
python bench/geometry.py --out synthetic.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fdmgen.geom.voxel import voxelise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mesh", type=Path)
    ap.add_argument("--h", type=float, default=0.4)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--node-grid", default="200,200,100")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.repeat < 1:
        ap.error("repeat must be positive")
    if a.mesh:
        mesh = trimesh.load_mesh(a.mesh, process=True)
        digest = hashlib.sha256(a.mesh.read_bytes()).hexdigest()
    else:
        mesh = trimesh.creation.annulus(r_min=12, r_max=40, height=40, sections=128)
        digest = hashlib.sha256(mesh.vertices.tobytes() + mesh.faces.tobytes()).hexdigest()
    rows = []
    for backend in ("scanline", "section"):
        for repeat in range(a.repeat):
            t0 = time.perf_counter()
            occ, grid = voxelise(mesh, h=(a.h,) * 3, backend=backend)
            elapsed = time.perf_counter() - t0
            rows.append(dict(backend=backend, repeat=repeat, seconds=elapsed,
                             shape=grid.shape, solid_cells=int(occ.sum()),
                             occupancy_sha256=hashlib.sha256(occ.tobytes()).hexdigest()))
    from fdmgen.geom.voxel import Grid
    shape = tuple(int(v) for v in a.node_grid.split(","))
    if len(shape) != 3 or min(shape) < 1:
        ap.error("node-grid requires three positive counts")
    grid = Grid(np.zeros(3), (a.h,) * 3, shape)
    t0 = time.perf_counter(); nodes = grid.node_coords(); node_s = time.perf_counter() - t0
    receipt = dict(evidence="measured local geometry benchmark",
                   establishes="occupancy parity and timing for the hashed input and software versions",
                   does_not_establish="physical accuracy, GPU performance, or bracket acceptance from synthetic input",
                   input_kind="provided mesh" if a.mesh else "synthetic annulus",
                   mesh_sha256=digest, h_mm=a.h, rows=rows,
                   parity=len({r['occupancy_sha256'] for r in rows}) == 1,
                   node_build=dict(grid=shape, cells=int(np.prod(shape)), nodes=len(nodes),
                                   output_bytes=nodes.nbytes, seconds=node_s),
                   versions=dict(python=platform.python_version(), numpy=np.__version__, trimesh=trimesh.__version__))
    a.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
