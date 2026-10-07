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
