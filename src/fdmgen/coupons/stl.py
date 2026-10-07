"""Binary STL writer (numpy only)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def write_stl(path, vertices, faces, name: str = "fdmgen") -> None:
    tri = np.asarray(vertices, np.float64)[np.asarray(faces)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
    rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    rec["n"], rec["v"] = n, tri
    header = name.encode("ascii", "replace")[:80].ljust(80, b" ")
    with Path(path).open("wb") as f:
        f.write(header)
        f.write(np.uint32(len(tri)).tobytes())
        f.write(rec.tobytes())
