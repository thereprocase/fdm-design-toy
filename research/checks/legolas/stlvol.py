import trimesh,numpy as np
m=trimesh.load(r'D:\Code\Models\spool-wall-rack\designs\rev-g2\print-controls\ef-core-asa-4w-1p6\body-only.stl')
print('extents',m.extents,'bounds',m.bounds.tolist(),'volume',m.volume,'watertight',m.is_watertight,'box',np.prod(m.extents),'frac',m.volume/np.prod(m.extents))
