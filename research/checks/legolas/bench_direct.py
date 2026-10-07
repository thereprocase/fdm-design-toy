import time,numpy as np,scipy.sparse.linalg as sla
from bench_cpu import build
for h in (4.0,3.2,2.4):
    nx,ny,nz=[int(round(l/h)) for l in (150,80,60)]
    A,idx,ne=build(nx,ny,nz,h)
    fixed=(3*idx[0].ravel()[:,None]+np.arange(3)).ravel()
    free=np.setdiff1d(np.arange(A.shape[0]),fixed)
    Aff=A[free][:,free].tocsc();b=np.zeros(len(free));b[::97]=1
    t=time.perf_counter();lu=sla.splu(Aff,permc_spec='COLAMD');tf=time.perf_counter()-t
    t=time.perf_counter();lu.solve(b);ts=time.perf_counter()-t
    print(f"h={h} cells={ne:,} dof={Aff.shape[0]:,} splu factor={tf:.1f}s solve={ts:.2f}s fill={(lu.L.nnz+lu.U.nnz)/1e6:.0f}M nnz",flush=True)
