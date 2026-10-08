// Synthetic contract data for consumer controls; never a producer receipt.
module.exports=(table,sha,keepout)=>({
 schema:'fdmgen/interface-render@0.1',units:'mm',frame:'design',scope:'Synthetic render-only consumer test; extra clearance not included.',
 table:{sha256:sha},mesh:table.mesh,problem:keepout.problem,installed_to_design:keepout.installed_to_design,clip:keepout.clip,
 items:table.interfaces.map(d=>{
  const plane={X:['center_yz_mm',[1,2]],Y:['center_xz_mm',[0,2]],Z:['center_xy_mm',[0,1]]}[d.axis],k='XYZ'.indexOf(d.axis);
  if(!plane||!['rod_seat','screw_clearance'].includes(d.type))return {id:d.id,type:d.type,rendered:false,reason:'Unsupported model for consumer test.'};
  const start=[0,0,0],end=[0,0,0];start[k]=keepout.clip.bbox_mm[0][k];end[k]=keepout.clip.bbox_mm[1][k];plane[1].forEach((a,j)=>start[a]=end[a]=d[plane[0]][j]);
  return {id:d.id,type:d.type,role:d.role,support:d.support,axis:d.axis,rendered:true,base_radius_mm:d.type==='rod_seat'?Math.max(...d.seat_radius_mm):d.d_mm/2,
   model:d.type==='rod_seat'?'rod seat modelled as a cylinder of its largest seat radius':'screw bore modelled as a cylinder of its clearance diameter; washer and driver access are not modelled',
   centre_plane:{key:plane[0],value:d[plane[0]]},axis_start_mm:start,axis_end_mm:end,unbounded:[`min_${d.axis.toLowerCase()}`,`max_${d.axis.toLowerCase()}`],source_fields:d.type==='rod_seat'?{seat_radius_mm:d.seat_radius_mm}:{d_mm:d.d_mm}};
 })});
