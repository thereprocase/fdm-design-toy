"""Issue #10 FP32/FP64 operator throughput; explicit device, hashed inputs.

CUDA runs require a working driver. Run sustained jobs in a named detached tmux
session with a log and exit-code file. This measures matvecs, not solve quality,
hierarchy peak VRAM, thermal qualification, or the real-bracket solver gate.
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
import warp as wp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fdmgen.fem import element
from fdmgen.fem.warp_structured import operator_module


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--grid", default="64,32,32")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.seconds <= 0:
        ap.error("seconds must be positive")
    shape = tuple(int(v) for v in a.grid.split(","))
    if len(shape) != 3 or min(shape) < 1:
        ap.error("grid needs three positive sizes")
    wp.init()
    if a.device.startswith("cuda") and not wp.is_cuda_available():
        ap.error("CUDA unavailable; no GPU benchmark result was generated")
    dev = wp.get_device(a.device)
    nx, ny, nz = shape
    cells = int(np.prod(shape)); nodes = (nx + 1) * (ny + 1) * (nz + 1)
    fixed = np.zeros(nodes * 3, dtype=np.int32)
    fixed[:3 * (ny + 1) * (nz + 1)] = 1
    x = np.random.default_rng(10).standard_normal(nodes * 3); x[fixed != 0] = 0
    Ke = element.box_ke(element.isotropic_C(1, 0.3), 0.4, 0.4, 0.4)
    mod = operator_module(Ke)
    outputs = []; rows = []
    for dtype in (np.float32, np.float64):
        wt = wp.float32 if dtype == np.float32 else wp.float64
        Ew = wp.array(np.ones(cells, dtype=dtype), dtype=wt, device=dev)
        fw = wp.array(fixed, dtype=wp.int32, device=dev)
        xw = wp.array(x.astype(dtype), dtype=wt, device=dev); yw = wp.zeros_like(xw)
        kernel = getattr(mod, 'matvec_' + np.dtype(dtype).name)
        def launch():
            wp.launch(kernel, dim=nodes, inputs=[nx, ny, nz, wt(1), Ew, fw, xw, yw], device=dev)
        launch(); wp.synchronize_device(dev)  # exclude compilation
        windows = []
        deadline = time.perf_counter() + a.seconds
        while time.perf_counter() < deadline:
            t0 = time.perf_counter()
            count = 0
            while True:
                for _ in range(10):
                    launch()
                count += 10
                wp.synchronize_device(dev)
                if time.perf_counter() - t0 >= 0.25:
                    break
            dt = time.perf_counter() - t0
            windows.append(dict(seconds=dt, matvecs=count, million_cell_matvecs_s=cells * count / dt / 1e6))
        outputs.append(yw.numpy().astype(np.float64))
        rates = [w['million_cell_matvecs_s'] for w in windows]
        rows.append(dict(dtype=np.dtype(dtype).name, windows=windows,
                         median_million_cell_matvecs_s=float(np.median(rates)),
                         minimum_to_first_rate=float(min(rates) / rates[0])))
    receipt = dict(evidence="measured operator benchmark", device=dev.name, grid=shape,
                   h_mm=[0.4] * 3, seed=10, requested_seconds_per_precision=a.seconds,
                   input_sha256=hashlib.sha256(Ke.tobytes()+fixed.tobytes()+x.tobytes()).hexdigest(),
                   relative_fp32_fp64_difference=float(np.linalg.norm(outputs[0]-outputs[1])/np.linalg.norm(outputs[1])),
                   versions=dict(warp=wp.__version__, numpy=np.__version__, python=platform.python_version()), rows=rows,
                   establishes="operator output difference and synchronized throughput on this device",
                   does_not_establish="whole-solve FP32 accuracy, hierarchy VRAM, thermal gate or bracket acceptance")
    a.out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(f"wrote {a.out.name}", flush=True)


if __name__ == '__main__':
    main()
