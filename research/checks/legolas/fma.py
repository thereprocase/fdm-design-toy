import warp as wp,time
wp.config.quiet=True
@wp.kernel
def k64(o:wp.array[wp.float64],n:int):
    i=wp.tid();a=wp.float64(i)*wp.float64(1e-9);b=wp.float64(1.0000001)
    c0=wp.float64(0.5);c1=wp.float64(0.6);c2=wp.float64(0.7);c3=wp.float64(0.8)
    for j in range(n):
        c0=c0*b+a;c1=c1*b+a;c2=c2*b+a;c3=c3*b+a
    o[i]=c0+c1+c2+c3
@wp.kernel
def k32(o:wp.array[wp.float32],n:int):
    i=wp.tid();a=float(i)*1e-9;b=float(1.0000001)
    c0=float(0.5);c1=float(0.6);c2=float(0.7);c3=float(0.8)
    for j in range(n):
        c0=c0*b+a;c1=c1*b+a;c2=c2*b+a;c3=c3*b+a
    o[i]=c0+c1+c2+c3
N=1<<20
for name,k,dt in (('fp64',k64,wp.float64),('fp32',k32,wp.float32)):
    o=wp.zeros(N,dtype=dt,device='cuda:0');wp.launch(k,dim=N,inputs=[o,10],device='cuda:0');wp.synchronize()
    t=time.perf_counter();wp.launch(k,dim=N,inputs=[o,2000],device='cuda:0');wp.synchronize();d=time.perf_counter()-t
    print(name,'GFLOP/s (2 per FMA):',2*4*N*2000/d/1e9)
