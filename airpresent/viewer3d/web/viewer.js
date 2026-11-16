import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const $ = id => document.getElementById(id);
const token = location.hash.slice(1);
history.replaceState(null, '', location.pathname);
const stage = $('stage');
let renderer, camera, controls;
const scene = new THREE.Scene();
const pivot = new THREE.Group();
scene.add(pivot);
let parts = [], selected = null, state = {}, imageTime = 0, revision = 0, selectionId = 0;
let explode = 0, currentScale = 1, yaw = 0, pitch = 0, pan = new THREE.Vector3();
let lastFresh = performance.now(), suspended = false;
let lastDraw = performance.now();
const raycaster = new THREE.Raycaster();
const notice = text => { $('notice').textContent = text; };

async function command(action, extra = {}) {
  const response = await fetch('/api/command', {method:'POST', headers:{'Content-Type':'application/json','X-AirHand-Token':token}, body:JSON.stringify({action,...extra})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作未完成');
}
const run = (action, extra) => command(action, extra).catch(e => notice(e.message));

function init() {
  renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.setClearColor(0x10151e,0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  stage.appendChild(renderer.domElement);
  camera = new THREE.PerspectiveCamera(38,1,.01,100);
  camera.position.set(3,2.3,4.5);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 1.5;
  controls.maxDistance = 18;
  controls.target.set(0,0,0);
  scene.add(new THREE.HemisphereLight(0xe2f1ff,0x283849,2.5));
  for (const [color,intensity,pos] of [[0xffffff,4,[3,5,4]],[0x8ebeff,2,[-4,2,-3]],[0x6fffcf,1,[1,-1,-3]]]) {
    const light = new THREE.DirectionalLight(color,intensity); light.position.set(...pos); scene.add(light);
  }
  const grid = new THREE.GridHelper(14,28,0x3a4c5c,0x253343);
  grid.position.y = -1.3;
  grid.material.transparent = true; grid.material.opacity = .5;
  scene.add(grid);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(1.7,80),new THREE.MeshBasicMaterial({color:0x172d35,transparent:true,opacity:.6}));
  ground.rotation.x = -Math.PI/2; ground.position.y = -1.29; scene.add(ground);
  new ResizeObserver(() => {const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(stage);
  let down;
  renderer.domElement.addEventListener('pointerdown', e => down=[e.clientX,e.clientY]);
  renderer.domElement.addEventListener('pointerup',e => {
    if (down && Math.hypot(e.clientX-down[0],e.clientY-down[1])<5) {
      const rect=renderer.domElement.getBoundingClientRect(); pick((e.clientX-rect.left)/rect.width,(e.clientY-rect.top)/rect.height);
    }
    down=null;
  });
  builtin();
  renderer.setAnimationLoop(draw);
}

function material(color, metalness=.6, roughness=.3) {return new THREE.MeshStandardMaterial({color,metalness,roughness});}
function mesh(geometry,mat,parent,x=0,y=0,z=0) {const m=new THREE.Mesh(geometry,mat);m.position.set(x,y,z);parent.add(m);return m;}
function group(name,description,y,delta) {
  const g=new THREE.Group();g.name=name;g.position.y=y;g.userData.description=description;
  g.userData.explodeAxis=new THREE.Vector3(0,delta,0);pivot.add(g);return g;
}
function builtin() {
  clearModel();
  const dark=material(0x233846,.7,.32), silver=material(0xb7c8cd,.8,.25), teal=material(0x45b99c,.65,.25);
  const gold=material(0xc8a46e,.7,.3), glass=material(0x1f6c84,.35,.12);
  const base=group('01 · 安装底座','承载与定位结构。当前为程序生成的展示示意模型。',-1.05,-.65);
  mesh(new THREE.CylinderGeometry(.76,.84,.22,64),dark,base);
  mesh(new THREE.CylinderGeometry(.82,.82,.035,64),teal,base,0,.11);
  for(let i=0;i<4;i++) mesh(new THREE.CylinderGeometry(.045,.045,.02,12),silver,base,.60*Math.cos(i*Math.PI/2),.14,.60*Math.sin(i*Math.PI/2));
  const core=group('02 · 主体外壳','铝合金风格的主体外壳，外侧环形散热筋用于展示结构层次。',-.32,-.18);
  mesh(new THREE.CylinderGeometry(.54,.60,1.12,64),silver,core);
  for(let i=0;i<7;i++) mesh(new THREE.CylinderGeometry(.64,.64,.035,64),dark,core,0,-.40+i*.12);
  const ring=group('03 · 状态灯环','绿色环形指示区，突出外壳与光学组件之间的连接。',.31,.22);
  mesh(new THREE.CylinderGeometry(.61,.61,.12,64),teal,ring);
  const mount=group('04 · 光学支架','连接主体与前部镜组，可通过拆解查看上下装配关系。',.55,.65);
  mesh(new THREE.CylinderGeometry(.52,.58,.30,64),dark,mount);
  mesh(new THREE.CylinderGeometry(.57,.57,.045,64),gold,mount,0,.14);
  const lens=group('05 · 光学镜组','蓝色表面表示光学窗口，仅为视觉示意，不模拟真实光学性能。',.78,1.12);
  mesh(new THREE.CylinderGeometry(.46,.46,.16,64),glass,lens);
  const rim=mesh(new THREE.TorusGeometry(.48,.045,16,80),silver,lens,0,.09);rim.rotation.x=Math.PI/2;
  const cover=group('06 · 防护压环','顶部防护与压紧结构，拆解后可单独选择查看。',.95,1.60);
  const t=mesh(new THREE.TorusGeometry(.52,.055,16,80),dark,cover);t.rotation.x=Math.PI/2;
  parts=pivot.children.slice(); setupParts(); resetLocal();
  $('model-title').textContent='模块化光学探头';
  notice('内置模型已加载。试试拖动“结构拆解”，再点击某个零件。');
}

function clearModel() {
  selected=null;
  const geometries=new Set(),materials=new Set(),textures=new Set();
  pivot.traverse(n=>{if(n.geometry)geometries.add(n.geometry);if(n.material)for(const m of (Array.isArray(n.material)?n.material:[n.material]))materials.add(m);});
  materials.forEach(m=>{for(const v of Object.values(m))if(v?.isTexture)textures.add(v);m.dispose();});
  textures.forEach(t=>{t.dispose();t.source?.data?.close?.();});
  geometries.forEach(g=>g.dispose());
  pivot.clear(); parts=[];
}
function setupParts() {
  pivot.updateMatrixWorld(true);
  parts.forEach((p,i)=>{
    p.userData.originalPosition=p.position.clone();
    if(!p.userData.explodeAxis) {
      const c=new THREE.Box3().setFromObject(p).getCenter(new THREE.Vector3());
      const origin=new THREE.Vector3();p.parent.worldToLocal(c);p.parent.worldToLocal(origin);
      const dir=c.sub(origin);if(dir.length()<.001)dir.set(Math.cos(i*2.4),.4,Math.sin(i*2.4));
      p.userData.explodeAxis=dir.normalize().multiplyScalar(.7);
    }
    p.traverse(n=>{if(n.material){n.material=Array.isArray(n.material)?n.material.map(m=>m.clone()):n.material.clone();}});
  });
  $('parts').replaceChildren();$('part-count').textContent=parts.length+' PARTS';
  parts.forEach((part,i)=>{const b=document.createElement('button');b.className='part';const dot=document.createElement('i'),label=document.createElement('span'),num=document.createElement('small');label.textContent=part.name||`零件 ${i+1}`;num.textContent=String(i+1).padStart(2,'0');b.append(dot,label,num);b.onclick=()=>select(part);$('parts').appendChild(b);});
}
function select(part) {
  if(!part)return;
  selected=part;
  [...$('parts').children].forEach((el,i)=>el.classList.toggle('active',parts[i]===part));
  $('selected-name').textContent=part.name||'未命名零件';
  $('selected-description').textContent=part.userData.description||'导入模型的组成部分。可单独查看或通过列表切换选择。';
}
function pick(x,y) {
  raycaster.setFromCamera(new THREE.Vector2(x*2-1,1-y*2),camera);
  const hits=raycaster.intersectObjects(parts,true).filter(h=>{let n=h.object;while(n&&n!==pivot){if(!n.visible)return false;n=n.parent;}return true;});
  if(hits.length){let n=hits[0].object;while(n&&!parts.includes(n))n=n.parent;select(n);}
}
function resetLocal() {
  yaw=pitch=0;currentScale=1;pan.set(0,0,0);pivot.rotation.set(0,0,0);pivot.scale.setScalar(1);pivot.position.set(0,0,0);
  camera.position.set(3,2.3,4.5);controls.target.set(0,0,0);controls.update();
  explode=0;$('explode').value=0;$('explode-label').textContent='0%';
  parts.forEach(p=>p.visible=true);
}
function draw() {
  const now = performance.now(), alpha = 1-Math.exp(-Math.min(.1,(now-lastDraw)/1000)/.07);lastDraw=now;
  const fresh=performance.now()-lastFresh<700;
  if(state.active&&fresh&&!suspended) {
    yaw=THREE.MathUtils.lerp(yaw,state.yaw,alpha);pitch=THREE.MathUtils.lerp(pitch,state.pitch,alpha);
    currentScale=THREE.MathUtils.lerp(currentScale,state.scale,alpha);
    pan.lerp(new THREE.Vector3(state.pan_x,state.pan_y,0),alpha);
  }
  pivot.rotation.set(pitch,yaw,0);pivot.scale.setScalar(currentScale);pivot.position.copy(pan);
  for(const p of parts){p.position.copy(p.userData.originalPosition).addScaledVector(p.userData.explodeAxis,explode);p.traverse(n=>{if(n.material)for(const m of (Array.isArray(n.material)?n.material:[n.material])){m.wireframe=$('wireframe').checked;if(m.emissive){m.emissive.setHex(p===selected?0x164e42:0);m.emissiveIntensity=.7;}}});}
  controls.update();renderer.render(scene,camera);
}

async function importGLB(file) {
  if(!file)return;
  try {
    if(file.size>50*1024*1024)throw new Error('模型超过 50 MB，请先简化。');
    const buffer=await file.arrayBuffer(), view=new DataView(buffer);
    if(buffer.byteLength<20||view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2||view.getUint32(8,true)!==buffer.byteLength)throw new Error('请选择有效的 glTF 2.0 .glb 文件。');
    const length=view.getUint32(12,true);
    if(view.getUint32(16,true)!==0x4e4f534a||20+length>buffer.byteLength)throw new Error('GLB 结构不完整。');
    const json=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,length)));
    for(const item of [...(json.buffers||[]),...(json.images||[])])if(item.uri&&!item.uri.startsWith('data:'))throw new Error('请导出资源全部内嵌的 GLB，本版不加载外部文件。');
    const unsupported=['KHR_draco_mesh_compression','KHR_texture_basisu','EXT_meshopt_compression'];
    if((json.extensionsUsed||[]).some(x=>unsupported.includes(x)))throw new Error('本版暂不支持 Draco / Meshopt / KTX2 压缩，请导出未压缩 GLB。');
    const loaded=await new GLTFLoader().parseAsync(buffer,'');
    const object=loaded.scene;object.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(object),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
    const max=Math.max(size.x,size.y,size.z);if(!Number.isFinite(max)||max<=0)throw new Error('模型没有可显示的几何体。');
    const meshes=[];object.traverse(n=>{if(n.isMesh)meshes.push(n);});
    if(meshes.length>300)throw new Error('网格超过 300 个，请先合并或简化模型。');
    clearModel();
    const normalized=new THREE.Group();normalized.scale.setScalar(2.2/max);object.position.sub(center);normalized.add(object);pivot.add(normalized);
    parts=meshes;setupParts();resetLocal();
    $('model-title').textContent=file.name;
    notice(`已导入 ${file.name}。拆解按网格近似分离，单网格模型无法按真实零件拆解；动画暂不播放。`);
    run('reset');
  } catch(e) {notice('导入失败：'+e.message);}
  $('file').value='';
}

let polling=false;
async function poll() {
  if(polling)return;polling=true;
  try {
    const response=await fetch('/api/state',{headers:{'X-AirHand-Token':token},signal:AbortSignal.timeout(2000)});
    if(!response.ok)throw new Error('会话连接失败，请重新启动工作台');
    state=await response.json();lastFresh=performance.now();
    $('connection').textContent='● 本机服务已连接';
    $('active-state').textContent=state.active?'已启用':'已暂停';
    $('active-state').classList.toggle('amber',!state.active);
    $('enable').disabled=!state.ready;$('enable').textContent=state.active?'暂停手势控制':'启用手势控制';
    $('camera-toggle').textContent=state.ready?'关闭摄像头':state.camera.includes('正在')?'连接 / 关闭中…':'开启摄像头';
    $('camera-status').textContent=state.camera;$('gesture-status').textContent=state.status;
    $('fps').textContent=state.fps?state.fps.toFixed(0)+' FPS':'— FPS';
    if(state.image&&state.image_time!==imageTime){$('camera-image').src='data:image/jpeg;base64,'+state.image;imageTime=state.image_time;}
    $('camera-image').hidden=!state.image;$('camera-placeholder').hidden=!!state.image;
    // CSS display:flex would override the HTML hidden attribute on this element.
    $('camera-placeholder').style.display=state.image?'none':'flex';
    if(state.revision!==revision){revision=state.revision;resetLocal();}
    const cursor=$('hand-cursor');cursor.hidden=!(state.active&&state.cursor&&state.mode==='select');
    if(!cursor.hidden){const x=THREE.MathUtils.clamp((state.cursor[0]-.12)/.76,0,1),y=THREE.MathUtils.clamp((state.cursor[1]-.12)/.76,0,1);cursor.style.left=x*100+'%';cursor.style.top=y*100+'%';if(state.selection_id!==selectionId)pick(x,y);}
    selectionId=state.selection_id;
  }catch(e){$('connection').textContent='连接中断';$('gesture-status').textContent='手势已停止输出，请重启工作台。';$('hand-cursor').hidden=true;}
  finally{polling=false;}
}

$('camera-toggle').onclick=()=>run(state.ready||state.camera?.includes('正在')?'stop':'start',{camera:Number($('camera-index').value)});
$('enable').onclick=()=>run('enable',{value:!state.active});
$('reset').onclick=()=>{resetLocal();run('reset');};
$('builtin').onclick=()=>{builtin();run('reset');};
$('explode').oninput=e=>{explode=Number(e.target.value);$('explode-label').textContent=Math.round(explode*100)+'%';};
$('file').onchange=e=>importGLB(e.target.files[0]);
$('isolate').onclick=()=>{if(!selected)return notice('先点击模型或列表选择零件。');parts.forEach(p=>p.visible=p===selected);};
$('show-all').onclick=()=>parts.forEach(p=>p.visible=true);
$('sensitivity').oninput=e=>{$('sensitivity-label').textContent=Number(e.target.value).toFixed(1)+'×';};
$('sensitivity').onchange=e=>run('sensitivity',{value:Number(e.target.value)});
for(const b of document.querySelectorAll('[data-mode]'))b.onclick=()=>{document.querySelectorAll('[data-mode]').forEach(n=>n.classList.toggle('chosen',n===b));run('mode',{value:b.dataset.mode});};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.key==='Escape')run('enable',{value:false});if(e.key.toLowerCase()==='r')$('reset').click();if('1234'.includes(e.key))document.querySelectorAll('[data-mode]')[Number(e.key)-1]?.click();});
document.addEventListener('visibilitychange',()=>{suspended=document.hidden;if(suspended)run('enable',{value:false});});
addEventListener('pagehide',()=>navigator.sendBeacon('/api/command',JSON.stringify({action:'stop',token})));
$('exit').onclick=async()=>{await run('exit');$('connection').textContent='工作台已关闭';$('enable').disabled=true;notice('摄像头与本机服务将关闭，现在可以关闭此标签页。');};

try{init();setInterval(poll,50);poll();}catch(e){$('empty-error').hidden=false;$('empty-error').textContent='三维渲染启动失败：'+e.message+'。请使用支持 WebGL 的 Chrome 或 Edge。';}

// Read-only test/diagnostic snapshot. No fake hand input is exposed by the app.
window.airhandDiagnostics=()=>({parts:parts.length,selected:selected?.name||null,rotation:[yaw,pitch],scale:currentScale,explode,rendered:!!renderer,mode:state.mode,active:state.active});
