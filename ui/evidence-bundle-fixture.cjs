// Synthetic bundle contract fixture. Existing real receipts are inputs, not relabelled artifacts.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const read=p=>fs.readFileSync(path.join(__dirname,p));
const parse=p=>JSON.parse(read(p));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
module.exports=function(){
 const draft=parse('fixtures/seed-draft.json'),report=parse('fixtures/seed-export-report.json'),reportHash=sha(read('fixtures/seed-export-report.json'));
 const slice=parse('fixtures/seed-slice-evidence.json'),project=parse('fixtures/seed-project-shell-check-v03.json'),baseline=parse('fixtures/seed-baseline-shell-check-v03.json');
 const bridge=parse('../tests/fixtures/bridge/facet-00-shell-only.bridge-check.json');
 const copyBridge=s=>({...structuredClone(bridge),gcode:s.gcode,pose:s.pose,table:s.table,mesh:s.mesh,placement:s.placement});
 const values=[['massing-evidence','project',slice],['shell-check','project',project],['shell-check','shell-only',baseline],['bridge-check','project',copyBridge(project)],['bridge-check','shell-only',copyBridge(baseline)]];
 const files=values.map(([check,kind,r])=>({name:check+'-'+kind+'.json',buffer:Buffer.from(JSON.stringify(r))}));
 const manifest={schema:'fdmgen/evidence-bundle@0.1',pose:report.plan.candidate_id,inputs:{report_sha256:reportHash,table_sha256:report.plan.table_sha256,gcode_sha256:{project:project.gcode.gcode_sha256,'shell-only':baseline.gcode.gcode_sha256}},receipts:values.map(([check,slice_kind,r],i)=>({check,slice_kind,path:files[i].name,sha256:sha(files[i].buffer),schema:r.schema,verdict:check==='massing-evidence'?'PASS':r.result.verdict})),paired:{},establishes:'Synthetic test only',does_not_establish:'Real bundle generation'};
 return {files,manifest,context:{report,draft,reportHash}};
};
module.exports.sha=sha;
