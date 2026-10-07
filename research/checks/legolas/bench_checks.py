import numpy as np,time
from scipy import ndimage as ndi
rng=np.random.default_rng(0)
def blob(shape):
    a=ndi.gaussian_filter(rng.random(shape),4)>0.5
    return a
a=blob((750,400));t=time.perf_counter()
for _ in range(10): ndi.distance_transform_edt(a)
print('2D EDT 750x400 (0.2mm layer):',(time.perf_counter()-t)/10*1e3,'ms/layer -> x300 layers =',(time.perf_counter()-t)/10*300,'s')
b=blob((375,200,150));t=time.perf_counter();ndi.distance_transform_edt(b);print('3D EDT 11.25M vox:',time.perf_counter()-t,'s')
# erosion by disc radius 4 cells per layer (shell emulation) via binary_erosion
st=ndi.generate_binary_structure(2,1);st=ndi.iterate_structure(st,4)
t=time.perf_counter()
for _ in range(10): ndi.binary_erosion(a,st)
print('2D erosion r=4:',(time.perf_counter()-t)/10*1e3,'ms/layer')
