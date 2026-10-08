const test=require('node:test');
const assert=require('node:assert/strict');
const {parseSTL,transformMesh}=require('./viewer.js');

test('ASCII and binary STL recover identical triangle coordinates',()=>{
 const coords=[0,0,0,2,0,0,0,3,0];
 const binary=new ArrayBuffer(134),v=new DataView(binary);v.setUint32(80,1,true);
 coords.forEach((x,i)=>v.setFloat32(96+i*4,x,true));
 const ascii=new TextEncoder().encode('solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 2 0 0\nvertex 0 3 0\nendloop\nendfacet\nendsolid a');
 assert.deepEqual(Array.from(parseSTL(binary)),coords);
 assert.deepEqual(Array.from(parseSTL(ascii.buffer)),coords);
});
test('design-to-print transform rotates then translates',()=>{
 assert.deepEqual(Array.from(transformMesh(new Float64Array([1,2,3]),[[0,-1,0],[1,0,0],[0,0,1]],[10,20,30])),[8,21,33]);
});
test('incomplete and nonfinite triangles are rejected',()=>{
 assert.throws(()=>parseSTL(new TextEncoder().encode('vertex 0 1 2').buffer));
 const bad=new ArrayBuffer(134),view=new DataView(bad);view.setUint32(80,1,true);view.setFloat32(96,NaN,true);
 assert.throws(()=>parseSTL(bad));
});
test('orthographic surface picking finds the front triangle, not the one behind',()=>{
 const {pickSurface}=require('./viewer.js');
 const v=new Float64Array([0,0,0,2,0,0,0,2,0,0,0,3,2,0,3,0,2,3]);
 assert.deepEqual(pickSurface(v,(x,y,z)=>[x,y,z],.5,.5),[.5,.5,3]);
 assert.equal(pickSurface(v,(x,y,z)=>[x,y,z],4,4),null);
});
test('box corners rotate with the part and preserve edge lengths',()=>{
 const {boxCorners}=require('./viewer.js');const c=boxCorners({center_mm:[10,20,30],size_mm:[2,4,6]});
 assert.deepEqual(Array.from(c.slice(0,3)),[9,18,27]);
 assert.deepEqual(Array.from(c.slice(21,24)),[11,22,33]);
 const rotated=transformMesh(c,[[0,-1,0],[1,0,0],[0,0,1]],[0,0,0]);
 assert.deepEqual(Array.from(rotated.slice(0,3)),[-18,9,27]);
});

test('axis indicator follows pose rotation and camera without translation',()=>{
 const {designAxesInView}=require('./viewer.js'),I=[[1,0,0],[0,1,0],[0,0,1]];
 const close=(actual,expected)=>actual.flat().forEach((v,i)=>assert(Math.abs(v-expected.flat()[i])<1e-12));
 close(designAxesInView(I,0,Math.PI/2),[[1,0,0],[0,1,0],[0,0,1]]); // top: Z toward camera
 close(designAxesInView(I,0,0),[[1,0,0],[0,0,1],[0,-1,0]]); // front: Z screen-up
 close(designAxesInView([[0,-1,0],[1,0,0],[0,0,1]],0,Math.PI/2),[[0,1,0],[-1,0,0],[0,0,1]]);
 close(designAxesInView(I,Math.PI/2,0),[[0,0,1],[-1,0,0],[0,-1,0]]);
});
