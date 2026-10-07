import numpy as np, scipy.sparse as sp, time, sys, pyamg
import scipy.sparse.linalg as sla
def ke_hex(h,E=1.0,nu=0.35):
    C=E/((1+nu)*(1-2*nu))*np.array([[1-nu,nu,nu,0,0,0],[nu,1-nu,nu,0,0,0],[nu,nu,1-nu,0,0,0],[0,0,0,(1-2*nu)/2,0,0],[0,0,0,0,(1-2*nu)/2,0],[0,0,0,0,0,(1-2*nu)/2]])
    corners=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)
    g=1/np.sqrt(3);K=np.zeros((24,24))
    for xi in (-g,g):
      for et in (-g,g):
        for ze in (-g,g):
          dN=0.125*np.stack([corners[:,0]*(1+et*corners[:,1])*(1+ze*corners[:,2]),
                             corners[:,1]*(1+xi*corners[:,0])*(1+ze*corners[:,2]),
                             corners[:,2]*(1+xi*corners[:,0])*(1+et*corners[:,1])])*(2/h)
          B=np.zeros((6,24))
          for a in range(8):
            bx,by,bz=dN[:,a]
            B[0,3*a]=bx;B[1,3*a+1]=by;B[2,3*a+2]=bz
            B[3,3*a]=by;B[3,3*a+1]=bx;B[4,3*a+1]=bz;B[4,3*a+2]=by;B[5,3*a]=bz;B[5,3*a+2]=bx
          K+=B.T@C@B*(h/2)**3
    return K
def build(nx,ny,nz,h,Efield=None):
    nn=(nx+1)*(ny+1)*(nz+1)
    idx=np.arange(nn).reshape(nx+1,ny+1,nz+1)
    c=np.stack([idx[:-1,:-1,:-1],idx[1:,:-1,:-1],idx[1:,1:,:-1],idx[:-1,1:,:-1],
                idx[:-1,:-1,1:],idx[1:,:-1,1:],idx[1:,1:,1:],idx[:-1,1:,1:]],-1).reshape(-1,8)
    dof=(3*c[:,:,None]+np.arange(3)).reshape(-1,24).astype(np.int32)
    Ke=ke_hex(h)
    ne=len(dof)
    rows=np.repeat(dof,24,axis=1).ravel();cols=np.tile(dof,(1,24)).ravel()
    data=np.tile(Ke.ravel(),(ne,1))
    if Efield is not None: data=data*Efield[:,None]
    A=sp.coo_matrix((data.ravel(),(rows,cols)),shape=(3*nn,3*nn)).tocsr()
    return A,idx,ne
def run(h,L=(150,80,60),contrast=None,tol=1e-8):
    nx,ny,nz=[int(round(l/h)) for l in L]
    t0=time.perf_counter()
    E=None
    if contrast:
        rng=np.random.default_rng(0)
        # smooth-ish random 0/1 field ~50% void, lattice-like: stripes of 4 cells
        i,j,k=np.meshgrid(np.arange(nx),np.arange(ny),np.arange(nz),indexing='ij')
        E=np.where(((i//4+j//4+k//4)%2==0)|(rng.random((nx,ny,nz))<0.3),1.0,contrast).ravel()
    A,idx,ne=build(nx,ny,nz,h,E)
    t_asm=time.perf_counter()-t0
    # clamp x=0 face, load on x=max face in -z
    fixed=(3*idx[0].ravel()[:,None]+np.arange(3)).ravel()
    n=A.shape[0];free=np.setdiff1d(np.arange(n),fixed)
    f=np.zeros(n);f[3*idx[-1].ravel()+2]=-1.0
    Aff=A[free][:,free].tocsr();b=f[free]
    # near-nullspace: translations+rotations on free nodes
    xyz=np.stack(np.meshgrid(np.arange(nx+1),np.arange(ny+1),np.arange(nz+1),indexing='ij'),-1).reshape(-1,3)*h
    fn=np.unique(free//3)
    # free dofs map: assume all 3 dofs of a node are free or fixed -> yes
    p=xyz[fn];B=np.zeros((len(fn),3,6));B[:,:,:3]=np.eye(3)
    B[:,:,3:]=np.cross(np.eye(3)[None],(p-p.mean(0))[:,None,:]).transpose(0,2,1)
    B=B.reshape(-1,6)
    t1=time.perf_counter()
    ml=pyamg.smoothed_aggregation_solver(Aff.tobsr(blocksize=(3,3)),B=B,max_coarse=500,smooth=('jacobi',{'omega':4/3}),strength=('symmetric',{'theta':0.0}))
    t_setup=time.perf_counter()-t1
    res=[]
    t2=time.perf_counter()
    x=ml.solve(b,tol=tol,accel='cg',residuals=res,maxiter=200)
    t_solve=time.perf_counter()-t2
    # matvec rate
    v=np.random.rand(Aff.shape[0]);t3=time.perf_counter()
    for _ in range(10): Aff@v
    t_mv=(time.perf_counter()-t3)/10
    r=np.linalg.norm(b-Aff@x)/np.linalg.norm(b)
    print(f"h={h} contrast={contrast} cells={ne:,} dof={n:,} nnz={Aff.nnz:,} asm={t_asm:.1f}s setup={t_setup:.1f}s solve={t_solve:.1f}s its={len(res)-1} relres={r:.1e} matvec={t_mv*1e3:.0f}ms opcx={ml.operator_complexity():.2f} mem_A={(Aff.data.nbytes+Aff.indices.nbytes)/1e9:.2f}GB",flush=True)
if __name__=='__main__':
    h=float(sys.argv[1]);c=float(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2]!='0' else None
    run(h,contrast=c)
