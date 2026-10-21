import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root='C:/Users/user/Documents/project2/defense-dashboard';
const skill='C:/Users/user/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const runtime='C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies';
process.env.RUNTIME_NODE_MODULES=runtime+'/node/node_modules';
const {Presentation,PresentationFile}=await import(pathToFileURL(runtime+'/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs').href).catch(async()=>{
  const {createRequire}=await import('node:module');const req=createRequire(runtime+'/node/node_modules/_entry.cjs');return import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
});
const build=root+'/.ppt-build-19', out=root+'/data/experiments/발표자료';
await fs.mkdir(build+'/previews',{recursive:true});await fs.mkdir(out,{recursive:true});
const source=await fs.readFile(root+'/data/experiments/분석계획표.md','utf8');
const clean=s=>s.replace(/`/g,'').replace(/\*\*/g,'').replace(/\\\[|\\\]/g,'').trim();
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const font='Malgun Gothic'; deck.theme.defaultFont=font;
function text(slide,s,x,y,w,h,size=25,bold=false,color='#25364A'){
 const box=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 box.text=clean(s);box.text.style={typeface:font,fontSize:size,bold,color};return box;
}
function base(title){let s=deck.slides.add();s.background.fill='#FFFFFF';text(s,title,60,35,1160,85,34,true,'#173C59');text(s,'우주연   2026-10-21',60,676,800,24,16,false,'#6A7784');text(s,String(deck.slides.items.length),1160,676,60,24,16);s.speakerNotes.text='출처: data/experiments/분석계획표.md\n';return s;}
function tableSlide(title,values,widths){
 const s=base(title);const t=s.tables.add({rows:values.length,columns:2,left:60,top:135,width:1160,height:500,columnWidths:widths||[250,910],values:values.map(r=>r.map(clean))});
 t.borders.assign({fill:'#D7E0E8',width:1,style:'solid'});
 for(let i=0;i<values.length;i++){for(let j=0;j<2;j++){const c=t.getCell(i,j);c.fill=j===0?'#EDF3F7':'#FFFFFF';c.text.style={typeface:font,fontSize:j===0?23:24,bold:j===0,color:'#25364A'};}}
 s.speakerNotes.text+='\n'+values.map(r=>r.join(': ')).join('\n');return s;
}
function matrixSlide(title,headers,rows){
 const s=base(title);const values=[headers,...rows];const n=headers.length;
 const widths=n===3?[250,430,480]:[260,...Array(n-1).fill(900/(n-1))];
 const tb=s.tables.add({rows:values.length,columns:n,left:60,top:135,width:1160,height:500,columnWidths:widths,values:values.map(r=>r.map(clean))});
 tb.borders.assign({fill:'#D7E0E8',width:1,style:'solid'});
 for(let i=0;i<values.length;i++)for(let j=0;j<n;j++){let c=tb.getCell(i,j);c.fill=i===0?'#173C59':j===0?'#EDF3F7':'#FFFFFF';c.text.style={typeface:font,fontSize:i===0?22:23,bold:i===0||j===0,color:i===0?'#FFFFFF':'#25364A'};}
 s.speakerNotes.text+='\n'+values.map(r=>r.join(': ')).join('\n');
}
const cover=base('장병 체력 측정 데이터 분석계획표');
text(cover,'장병 체력 측정 데이터\n분석계획표',60,195,1120,170,58,true,'#173C59');
text(cover,'작성자 우주연\n작성일 2026-10-21',65,420,1100,110,30);
text(cover,'분석계획 19개 항목',65,570,1100,50,25);
let h2='',h3='',lines=source.split(/\r?\n/), chunks=[],p=[];
function flush(){if(p.length){chunks.push({type:'text',title:h3||h2,lines:p});p=[];}}
for(let i=0;i<lines.length;i++){
 let l=lines[i].trim();if(!l)continue;
 if(l.startsWith('# '))continue;
 if(l.startsWith('## ')){flush();h2=clean(l.slice(3));h3='';continue;}
 if(l.startsWith('### ')){flush();h3=clean(l.slice(4));continue;}
 if(l.startsWith('|')){flush();let rows=[];while(i<lines.length&&lines[i].trim().startsWith('|')){let cells=lines[i].trim().slice(1,-1).split('|').map(clean);if(!cells.every(c=>/^:?-+:?$/.test(c)))rows.push(cells);i++;}i--;chunks.push({type:'table',title:h3||h2,rows});continue;}
 if(l.startsWith('작성일:')||l.startsWith('작성자:'))continue;
 p.push(clean(l));
}flush();
chunks=chunks.filter(b=>b.type==='table' && b.title==='2. 분석계획표');
if(chunks.length!==1 || chunks[0].rows.length!==20)throw new Error('Expected 19 plan entries');
for(const block of chunks){
 if(block.type==='table'){
  const [headers,...rows]=block.rows;
  if(headers.length===3 || (headers.length===4 && rows.every(r=>r.join('').length<90))){let group=[],used=0;for(const row of rows){let h=Math.max(...row.map((c,j)=>Math.ceil(clean(c).length/(j===0?10:18))*30+22));if(used+h>420&&group.length){matrixSlide(block.title,headers,group);group=[];used=0;}group.push(row);used+=h;}if(group.length)matrixSlide(block.title,headers,group);}
  else if(headers.length>2){for(const row of rows){let title=block.title;if(headers[0]==='순서'){title=`분석 ${row[0]}  ${row[1]}`;tableSlide(title,headers.slice(2).map((h,j)=>[h,row[j+2]||'']));}else{tableSlide(`${block.title}  ${row[0]}`,headers.slice(1).map((h,j)=>[h,row[j+1]||'']));}}}
  else{let page=[],budget=0;for(const row of rows){let height=Math.max(60,Math.ceil(clean(row[1]||'').length/35)*31+24);if(budget+height>480&&page.length){tableSlide(block.title,page);page=[];budget=0;}page.push(row);budget+=height;}if(page.length)tableSlide(block.title,page);}
 }else{
  let page=[],used=0;function emit(){if(!page.length)return;let s=base(block.title);let y=140;for(const item of page){let h=Math.ceil(item.length/46)*36+20;text(s,item,65,y,1150,h,25);y+=h;}s.speakerNotes.text+='\n'+page.join('\n');page=[];used=0;}
  for(const item of block.lines){let h=Math.ceil(item.length/46)*36+20;if(used+h>490)emit();page.push(item);used+=h;}emit();
 }
}
await (await PresentationFile.exportPptx(deck)).save(build+'/candidate.pptx');
await fs.writeFile(build+'/slides.json',JSON.stringify({count:deck.slides.items.length},null,2));
for(let i=0;i<deck.slides.items.length;i++){
 try{let png=await deck.export({slide:deck.slides.items[i],format:'png',scale:0.8});await fs.writeFile(build+`/previews/${String(i+1).padStart(3,'0')}.png`,new Uint8Array(await png.arrayBuffer()));}catch(e){console.log('render error',i+1,String(e));throw e;}
}
const {finalizePresentation}=await import(pathToFileURL(skill+'/container_tools/artifact_tool_utils.mjs').href);
const final=out+'/분석계획표_19개항목_우주연_제출용.pptx';
await finalizePresentation({workspaceDir:root,candidatePath:build+'/candidate.pptx',finalPath:final,
 pythonExecutable:runtime+'/python/python.exe',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',
 layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000'],
 requiredNativeTableOwnerSlides:[],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:build+'/validation-final.json'});
console.log('DONE',deck.slides.items.length,final);

