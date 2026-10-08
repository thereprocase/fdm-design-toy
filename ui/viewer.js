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
function boxCorners(geometry) {
  const vertices=new Float64Array(24);
  for(let i=0;i<8;i++)for(let a=0;a<3;a++)vertices[3*i+a]=geometry.center_mm[a]+((i>>a)&1?.5:-.5)*geometry.size_mm[a];
  return vertices;
}
function pickSurface(vertices,project,x,y) {
  let best=null,depth=-Infinity;
  for(let i=0;i<vertices.length;i+=9){
    const p=[0,3,6].map(j=>project(vertices[i+j],vertices[i+j+1],vertices[i+j+2]));
    const den=(p[1][1]-p[2][1])*(p[0][0]-p[2][0])+(p[2][0]-p[1][0])*(p[0][1]-p[2][1]);
    if(Math.abs(den)<1e-12)continue;
    const a=((p[1][1]-p[2][1])*(x-p[2][0])+(p[2][0]-p[1][0])*(y-p[2][1]))/den;
    const b=((p[2][1]-p[0][1])*(x-p[2][0])+(p[0][0]-p[2][0])*(y-p[2][1]))/den,c=1-a-b;
    if(Math.min(a,b,c)<-1e-9)continue;
    const z=a*p[0][2]+b*p[1][2]+c*p[2][2];
    if(z>depth){depth=z;best=[0,1,2].map(j=>a*vertices[i+j]+b*vertices[i+3+j]+c*vertices[i+6+j]);}
  }
  return best;
}
function designAxesInView(R,yaw,pitch){
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  return [0,1,2].map(a=>{
    const x=R[0][a],y=R[1][a],z=R[2][a],yy=sy*x+cy*y;
    return [cy*x-sy*y,sp*yy-cp*z,cp*yy+sp*z];
  });
}
const AXIS_PANEL={x:8,y:8,width:122,height:116};
class PartViewer {
  constructor(canvas) {
    this.canvas=canvas;this.vertices=null;this.yaw=-.65;this.pitch=.65;this.zoom=1;this.regions=[];this.onPick=null;
    let start=null,down=null;
    const onOverlay=e=>{
      const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
      return this.vertices&&x>=AXIS_PANEL.x&&x<=AXIS_PANEL.x+AXIS_PANEL.width&&y>=AXIS_PANEL.y&&y<=AXIS_PANEL.y+AXIS_PANEL.height;
    };
    canvas.addEventListener('pointerdown',e=>{if(onOverlay(e)){start=down=null;return;}start=down=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointerup',e=>{
      if(this.onPick&&down&&!onOverlay(e)&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<4&&this.project&&this.vertices){
        const rect=canvas.getBoundingClientRect(),point=pickSurface(this.vertices,this.project,e.clientX-rect.left,e.clientY-rect.top);
        const design=point?[0,1,2].map(a=>this.R.reduce((sum,row,j)=>sum+row[a]*(point[j]-this.t[j]),0)):null;
        this.onPick(design);
      }
      start=down=null;
    });canvas.addEventListener('pointercancel',()=>{start=down=null;});
    canvas.addEventListener('pointermove',e=>{if(!start)return;this.yaw+=(e.clientX-start[0])*.01;this.pitch=Math.max(-1.5,Math.min(1.5,this.pitch+(e.clientY-start[1])*.01));start=[e.clientX,e.clientY];this.schedule();});
    canvas.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();this.yaw+=e.key==='ArrowLeft'?-.15:e.key==='ArrowRight'?.15:0;this.pitch+=e.key==='ArrowUp'?.15:e.key==='ArrowDown'?-.15:0;this.schedule();});
    new ResizeObserver(()=>this.schedule()).observe(canvas);
  }
  set(vertices,R,t){this.R=R;this.t=t;this.vertices=transformMesh(vertices,R,t);this.schedule();}
  setRegions(regions){this.regions=regions;this.schedule();}
  clear(){this.vertices=null;this.onPick=null;this.canvas.style.cursor='';this.schedule();}
  zoomBy(factor){this.zoom=Math.max(.5,Math.min(8,this.zoom*factor));this.schedule();}
  view(name){
    const angles={top:[0,Math.PI/2],'print-x':[Math.PI/2,0],'print-y':[0,0],iso:[-.65,.65]};
    [this.yaw,this.pitch]=angles[name]||angles.iso;this.zoom=1;this.schedule();
  }
  schedule(){if(this.pending)return;this.pending=true;requestAnimationFrame(()=>{this.pending=false;this.draw();});}
  draw(){
    const canvas=this.canvas, width=canvas.clientWidth,height=canvas.clientHeight,dpr=window.devicePixelRatio||1;
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#eaf0e7';ctx.fillRect(0,0,width,height);
    if(!this.vertices){ctx.fillStyle='#53665a';ctx.font='15px system-ui';ctx.textAlign='center';ctx.fillText('Load the matching STL to preview this pose',width/2,height/2);return;}
    const v=this.vertices,lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    for(let i=0;i<v.length;i++) {const a=i%3;lo[a]=Math.min(lo[a],v[i]);hi[a]=Math.max(hi[a],v[i]);}
    const center=lo.map((x,i)=>(x+hi[i])/2),radius=Math.hypot(...hi.map((x,i)=>x-lo[i]))/2||1,scale=Math.min(width,height)*.4/radius*this.zoom;
    const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
    const project=(x,y,z)=>{x-=center[0];y-=center[1];z-=center[2];const xx=cy*x-sy*y,yy=sy*x+cy*y;return [width/2+scale*xx,height/2-scale*(cp*z-sp*yy),cp*yy+sp*z];};
    this.project=project;
    // A ground rectangle at print Z=0 gives an orientation cue, not a printer fit test.
    const pad=radius*.12,ground=[[lo[0]-pad,lo[1]-pad],[hi[0]+pad,lo[1]-pad],[hi[0]+pad,hi[1]+pad],[lo[0]-pad,hi[1]+pad]].map(p=>project(...p,0));
    ctx.beginPath();ground.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle='#d7dfd1';ctx.fill();ctx.strokeStyle='#adbda8';ctx.stroke();
    const faces=[];
    for(let i=0;i<v.length;i+=9){const p=[project(v[i],v[i+1],v[i+2]),project(v[i+3],v[i+4],v[i+5]),project(v[i+6],v[i+7],v[i+8])];
      const a=[v[i+3]-v[i],v[i+4]-v[i+1],v[i+5]-v[i+2]],b=[v[i+6]-v[i],v[i+7]-v[i+1],v[i+8]-v[i+2]],n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],norm=Math.hypot(...n)||1;
      const light=.5+.5*Math.abs((.25*n[0]-.45*n[1]+.86*n[2])/norm);faces.push({p,depth:p.reduce((s,p)=>s+p[2],0),light});}
    faces.sort((a,b)=>a.depth-b.depth);
    for(const {p,light} of faces){ctx.beginPath();p.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle=`hsl(151 24% ${28+light*30}%)`;ctx.fill();}
    for(const region of [...this.regions].sort((a,b)=>Number(!!a.active)-Number(!!b.active))){
      const corners=transformMesh(boxCorners(region.geometry),this.R,this.t),points=[];
      for(let i=0;i<24;i+=3)points.push(project(corners[i],corners[i+1],corners[i+2]));
      ctx.strokeStyle=region.active?'#175caa':'#ad501c';ctx.lineWidth=region.active?3:2;ctx.setLineDash(region.active?[]:[5,3]);ctx.beginPath();
      for(let i=0;i<8;i++)for(let a=0;a<3;a++){const j=i^(1<<a);if(j>i){ctx.moveTo(points[i][0],points[i][1]);ctx.lineTo(points[j][0],points[j][1]);}}
      ctx.stroke();ctx.setLineDash([]);ctx.font='bold 12px system-ui';ctx.fillStyle=region.active?'#174d89':'#84360f';ctx.fillText((region.active?'Editing: ':'')+(region.name||'Planning region'),points[7][0]+5,points[7][1]-5);
    }
    // Directions follow both the design-to-print rotation and camera, without translation.
    ctx.fillStyle='rgba(255,255,255,.9)';ctx.fillRect(AXIS_PANEL.x,AXIS_PANEL.y,AXIS_PANEL.width,AXIS_PANEL.height);
    ctx.fillStyle='#344d40';ctx.font='12px system-ui';ctx.fillText('Design axes',18,26);
    const origin=[67,75],length=28,colors=['#a52e2e','#267142','#235ca4'];
    designAxesInView(this.R,this.yaw,this.pitch).forEach(([x,y,depth],i)=>{
      const tip=[origin[0]+length*x,origin[1]+length*y];ctx.strokeStyle=colors[i];ctx.fillStyle=colors[i];ctx.lineWidth=2;
      ctx.beginPath();
      if(Math.hypot(x,y)<.1){
        ctx.arc(...origin,4,0,Math.PI*2);ctx.stroke();
        if(depth>0){ctx.beginPath();ctx.arc(...origin,1.5,0,Math.PI*2);ctx.fill();}
        else {ctx.beginPath();ctx.moveTo(origin[0]-3,origin[1]-3);ctx.lineTo(origin[0]+3,origin[1]+3);ctx.moveTo(origin[0]+3,origin[1]-3);ctx.lineTo(origin[0]-3,origin[1]+3);ctx.stroke();}
        ctx.fillText('+'+'XYZ'[i],origin[0]+8,origin[1]-8);
      }else{
        ctx.moveTo(...origin);ctx.lineTo(...tip);ctx.stroke();ctx.beginPath();ctx.arc(...tip,2,0,Math.PI*2);ctx.fill();
        ctx.fillText('+'+'XYZ'[i],tip[0]+(x<0?-18:4),tip[1]+(y>0?13:-4));
      }
    });
    ctx.fillStyle='#344d40';ctx.font='11px system-ui';ctx.fillText('Bed plane: print Z = 0 · mm',14,height-15);
  }
}
if(typeof module!=='undefined')module.exports={parseSTL,transformMesh,boxCorners,pickSurface,designAxesInView};
