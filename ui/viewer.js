/* Local STL preview. Candidate transforms map design millimetres to print millimetres. */
'use strict';
function parseSTL(buffer) {
  const view = new DataView(buffer), values = [];
  if (buffer.byteLength >= 84 && 84 + 50 * view.getUint32(80, true) === buffer.byteLength) {
    const count = view.getUint32(80, true);
    for (let i=0;i<count;i++) for(let j=0;j<9;j++) values.push(view.getFloat32(84+i*50+12+j*4,true));
  } else {
    const source=new TextDecoder().decode(buffer), pattern=/\bvertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)/g;
    for (const m of source.matchAll(pattern)) values.push(Number(m[1]),Number(m[2]),Number(m[3]));
  }
  if(!values.length || values.length%9 || !values.every(Number.isFinite))throw Error('STL must contain complete finite triangles.');
  return new Float64Array(values);
}
function transformMesh(vertices,R,t) {
  if(!Array.isArray(R)||R.length!==3||R.some(row=>!Array.isArray(row)||row.length!==3||!row.every(Number.isFinite))||!Array.isArray(t)||t.length!==3||!t.every(Number.isFinite))throw Error('Candidate has no valid design-to-print transform.');
  const out=new Float64Array(vertices.length);
  for(let i=0;i<vertices.length;i+=3)for(let a=0;a<3;a++)out[i+a]=t[a]+R[a][0]*vertices[i]+R[a][1]*vertices[i+1]+R[a][2]*vertices[i+2];
  return out;
}
class PartViewer {
  constructor(canvas) {
    this.canvas=canvas;this.vertices=null;this.yaw=-.65;this.pitch=.65;this.zoom=1;
    let start=null;
    canvas.addEventListener('pointerdown',e=>{start=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointerup',()=>start=null);canvas.addEventListener('pointercancel',()=>start=null);
    canvas.addEventListener('pointermove',e=>{if(!start)return;this.yaw+=(e.clientX-start[0])*.01;this.pitch=Math.max(-1.5,Math.min(1.5,this.pitch+(e.clientY-start[1])*.01));start=[e.clientX,e.clientY];this.schedule();});
    canvas.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();this.yaw+=e.key==='ArrowLeft'?-.15:e.key==='ArrowRight'?.15:0;this.pitch+=e.key==='ArrowUp'?.15:e.key==='ArrowDown'?-.15:0;this.schedule();});
    new ResizeObserver(()=>this.schedule()).observe(canvas);
  }
  set(vertices,R,t){this.vertices=transformMesh(vertices,R,t);this.schedule();}
  clear(){this.vertices=null;this.schedule();}
  view(name){this.yaw=name==='top'?0:-.65;this.pitch=name==='top'?Math.PI/2:.65;this.zoom=1;this.schedule();}
  schedule(){if(this.pending)return;this.pending=true;requestAnimationFrame(()=>{this.pending=false;this.draw();});}
  draw(){
    const canvas=this.canvas, width=canvas.clientWidth,height=canvas.clientHeight,dpr=window.devicePixelRatio||1;
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#eaf0e7';ctx.fillRect(0,0,width,height);
    if(!this.vertices){ctx.fillStyle='#53665a';ctx.font='15px system-ui';ctx.textAlign='center';ctx.fillText('Load the matching STL to preview this pose',width/2,height/2);return;}
    const v=this.vertices,lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    for(let i=0;i<v.length;i++) {const a=i%3;lo[a]=Math.min(lo[a],v[i]);hi[a]=Math.max(hi[a],v[i]);}
    const center=lo.map((x,i)=>(x+hi[i])/2),radius=Math.hypot(...hi.map((x,i)=>x-lo[i]))/2||1,scale=Math.min(width,height)*.4/radius;
    const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
    const project=(x,y,z)=>{x-=center[0];y-=center[1];z-=center[2];const xx=cy*x-sy*y,yy=sy*x+cy*y;return [width/2+scale*xx,height/2-scale*(cp*z-sp*yy),cp*yy+sp*z];};
    // A ground rectangle at print Z=0 gives an orientation cue, not a printer fit test.
    const pad=radius*.12,ground=[[lo[0]-pad,lo[1]-pad],[hi[0]+pad,lo[1]-pad],[hi[0]+pad,hi[1]+pad],[lo[0]-pad,hi[1]+pad]].map(p=>project(...p,0));
    ctx.beginPath();ground.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle='#d7dfd1';ctx.fill();ctx.strokeStyle='#adbda8';ctx.stroke();
    const faces=[];
    for(let i=0;i<v.length;i+=9){const p=[project(v[i],v[i+1],v[i+2]),project(v[i+3],v[i+4],v[i+5]),project(v[i+6],v[i+7],v[i+8])];
      const a=[v[i+3]-v[i],v[i+4]-v[i+1],v[i+5]-v[i+2]],b=[v[i+6]-v[i],v[i+7]-v[i+1],v[i+8]-v[i+2]],n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],norm=Math.hypot(...n)||1;
      const light=.5+.5*Math.abs((.25*n[0]-.45*n[1]+.86*n[2])/norm);faces.push({p,depth:p.reduce((s,p)=>s+p[2],0),light});}
    faces.sort((a,b)=>a.depth-b.depth);
    for(const {p,light} of faces){ctx.beginPath();p.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle=`hsl(151 24% ${28+light*30}%)`;ctx.fill();}
    ctx.fillStyle='#344d40';ctx.font='12px system-ui';ctx.fillText('Print Z ↑ · ground at Z = 0 · dimensions in mm',14,height-15);
  }
}
if(typeof module!=='undefined')module.exports={parseSTL,transformMesh};
