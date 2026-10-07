import sys,time,numpy as np,trimesh
sys.path.insert(0,r'D:\Code\Models\spool-wall-rack\analysis\rev-g2')
import warp as wp
wp.config.quiet=True
from gpu_hex import HexOperator,CORNERS
from scipy import ndimage as ndi
m=trimesh.load(r'D:\Code\Models\spool-wall-rack\designs\rev-g2\print-controls\ef-core-asa-4w-1p6\body-only.stl')
h=float(sys.argv[1]);dil=int(sys.argv[2])
t0=time.perf_counter()
vg=m.voxelized(h).fill()
mask=vg.matrix.copy()
if dil: mask=ndi.binary_dilation(mask,iterations=dil)
cells=np.argwhere(mask).astype(np.int64)
tv=time.perf_counter()-t0
cs=np.asarray(CORNERS,int)
corner=(cells[:,None,:]+cs[None]).reshape(-1,3)
shape=np.array(mask.shape)+1
lin=(corner[:,0]*shape[1]+corner[:,1])*shape[2]+corner[:,2]
u,inv=np.unique(lin,return_inverse=True)
t=inv.reshape(-1,8).astype(np.int32)
uc=np.stack(np.unravel_index(u,shape),-1)
p=uc*h
tb0=time.perf_counter()
op=HexOperator(p,t,(h,h,h));tb=time.perf_counter()-tb0
x=wp.array(np.random.rand(op.ndof),dtype=wp.float64,device='cuda:0');y=wp.zeros_like(x)
A=op.operator(np.array([0,1,2]))
A.matvec(x,y,y,1.,0.);wp.synchronize()
t1=time.perf_counter()
for _ in range(30):A.matvec(x,y,y,1.,0.)
wp.synchronize();tmv=(time.perf_counter()-t1)/30
print(f"h={h} dil={dil} grid={tuple(mask.shape)} cells={len(t):,} ({len(t)/mask.size:.1%} of box {mask.size:,}) dof={op.ndof:,} voxelise={tv:.1f}s unique+build={tb:.1f}s matvec={tmv*1e3:.2f}ms ({len(t)/tmv/1e6:.0f} Mcell/s)")
if len(sys.argv)>3:
    px=p[:,0];py=p[:,1]
    # clamp the lowest-y 3 mm slab, load the highest-y nodes in -x
    fixed_nodes=np.where(py<py.min()+3)[0]
    fixed=(3*fixed_nodes[:,None]+np.arange(3)).ravel()
    top=np.where(py>py.max()-1.0)[0]
    f=np.zeros(op.ndof);f[3*top]=-1.0/len(top)
    t2=time.perf_counter()
    try:
        u,r,info=op.solve(f,fixed,maxiter=int(sys.argv[3]));print('solve',info)
    except Exception as e: print('solve fail',str(e)[:160])
    print('solve wall',time.perf_counter()-t2)
