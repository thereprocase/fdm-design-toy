"""Masked bracket connectivity audit (#4); connectivity is not a stiffness-rank test."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from bracket_gate import build
from fdmgen.fem.element import CORNERS
from fdmgen.adapters.spool_bracket import HANDOFF


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--sizes',default='3.2,1.6,0.8')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); rows=[]
    for h in map(float,a.sizes.split(',')):
        _,occ,g,fixed,b,bc=build(a.root,(h,)*3)
        _,face_count=ndimage.label(occ)
        labels,count=ndimage.label(occ,structure=np.ones((3,3,3)))
        nx,ny,nz=g.shape
        nodes=np.zeros((nx+1,ny+1,nz+1),np.int32)
        for c in CORNERS:
            view=nodes[c[0]:c[0]+nx,c[1]:c[1]+ny,c[2]:c[2]+nz]
            np.maximum(view,labels,out=view)
        full_clamp=np.all(fixed.reshape(-1,3)!=0,axis=1)
        loaded=np.any(b.reshape(-1,3)!=0,axis=1)
        mounts=np.bincount(nodes.ravel()[full_clamp],minlength=count+1)
        loads=np.bincount(nodes.ravel()[loaded],minlength=count+1)
        cells=np.bincount(labels.ravel(),minlength=count+1)
        components=[dict(cells=int(cells[i]),fully_clamped_nodes=int(mounts[i]),loaded_nodes=int(loads[i])) for i in range(1,count+1)]
        rows.append(dict(h_mm=h,grid=g.shape,body_cells=int(occ.sum()),face_connected_components=face_count,
                         node_connected_components=count,components=components,bc=bc))
        print(f'h={h}: face components={face_count}, node components={count}; {components}',flush=True)
    receipt=dict(evidence='measured masked geometry connectivity',rows=rows,
                 mesh_sha256=hashlib.sha256((a.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest(),
                 establishes='voxel connectivity and clamp/load membership at the recorded resolutions',
                 does_not_establish='positive-definite stiffness, full rigid-mode restraint, GPU convergence or bracket acceptance')
    a.out.write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
