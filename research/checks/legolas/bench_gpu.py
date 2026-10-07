import sys,time,numpy as np
sys.path.insert(0,r'D:\Code\Models\spool-wall-rack\analysis\rev-g2')
import warp as wp
wp.config.quiet=True
from gpu_hex import HexOperator
def grid(nx,ny,nz,h):
    idx=np.arange((nx+1)*(ny+1)*(nz+1)).reshape(nx+1,ny+1,nz+1)
    X,Y,Z=np.meshgrid(np.arange(nx+1),np.arange(ny+1),np.arange(nz+1),indexing='ij')
    p=np.stack([X,Y,Z],-1).reshape(-1,3)*h
    from gpu_hex import CORNERS
    base=np.stack([idx[:-1,:-1,:-1]],-1).reshape(-1)
    # corner order from gpu_hex.CORNERS
    cs=np.asarray(CORNERS,int)
    t=np.stack([idx[cs[k,0]:nx+cs[k,0],cs[k,1]:ny+cs[k,1],cs[k,2]:nz+cs[k,2]].reshape(-1) for k in range(8)],-1)
    return p,t,idx
h=float(sys.argv[1]);L=(150,80,60)
nx,ny,nz=[int(round(l/h)) for l in L]
t0=time.perf_counter();p,t,idx=grid(nx,ny,nz,h);tg=time.perf_counter()-t0
t0=time.perf_counter();op=HexOperator(p,t,(h,h,h));tb=time.perf_counter()-t0
fixed=(3*idx[0].ravel()[:,None]+np.arange(3)).ravel()
f=np.zeros(op.ndof);f[3*idx[-1].ravel()+2]=-1.
# matvec timing
x=wp.array(np.random.rand(op.ndof),dtype=wp.float64,device='cuda:0');y=wp.zeros_like(x)
A=op.operator(fixed)
A.matvec(x,y,y,1.,0.);wp.synchronize()
t0=time.perf_counter()
for _ in range(50):A.matvec(x,y,y,1.,0.)
wp.synchronize();tmv=(time.perf_counter()-t0)/50
t0=time.perf_counter()
try:
    u,r,info=op.solve(f,fixed,maxiter=int(sys.argv[2]) if len(sys.argv)>2 else 3000)
    print('solve',info)
except Exception as e: print('solve fail',str(e)[:200]); info=None
ts=time.perf_counter()-t0
print(f"h={h} cells={len(t):,} dof={op.ndof:,} grid={tg:.1f}s build={tb:.1f}s matvec={tmv*1e3:.2f}ms ({len(t)/tmv/1e6:.0f} Mcell/s) solve_total={ts:.1f}s")
print(wp.get_device('cuda:0').name)
