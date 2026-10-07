import json
import os
from pathlib import Path

import numpy as np
import pytest

from fdmgen.adapters import spool_bracket as sb

FIX = json.loads((Path(__file__).parent / "fixtures" / "g2_interface_loads.json").read_text())
ROOT = os.environ.get("SPOOL_RACK_ROOT", r"D:\Code\Models\spool-wall-rack")


def test_load_parity_p0g():
    """P0-G: ported interface loads reproduce the pinned reference to 1e-12 and sum to the total."""
    L = sb.interface_loads(FIX["load_N"])
    assert np.allclose(L["rear_seat"], FIX["rear_seat_target_N"], rtol=1e-12, atol=1e-12)
    assert np.allclose(L["front_seat"], FIX["front_seat_target_N"], rtol=1e-12, atol=1e-12)
    assert np.allclose(L["rear_seat"] + L["front_seat"], [0, -FIX["load_N"], 0], atol=1e-12)


@pytest.mark.skipif(not Path(ROOT).exists(), reason="spool-wall-rack checkout not available")
def test_frames_and_voxel_volume():
    from fdmgen.geom.voxel import voxelise
    br = sb.Bracket.load(ROOT)
    assert np.allclose(br.R_I_to_P, np.diag([-1.0, -1.0, 1.0]))        # 180 deg about Z (measured)
    assert np.allclose(br.t_I_to_P, [250.0, 182.0, 0.0], atol=1e-3)
    rear_I = np.array([*sb.ROD_AXES_I["rear_seat"], 12.0])
    assert br.mesh().contains([br.to_print(rear_I + [0, -13.0, 0])])[0]   # seat material below the rear rod
    assert np.allclose(sum(br.loads_print().values()), [0, 117.72, 0])  # gravity points +Y in the print frame
    occ, g = voxelise(br.mesh(), h=(1.0, 1.0, 1.2), multiple=4)
    vox = occ.sum() * np.prod(g.h)
    assert abs(vox - br.mesh().volume) / br.mesh().volume < 0.03   # coarse 1 mm grid
