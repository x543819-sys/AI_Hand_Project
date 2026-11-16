// Native Chromium renders the real viewer. Camera samples are synthetic.
const {chromium}=require(process.env.AIRHAND_PLAYWRIGHT_PATH || 'playwright');
const {spawn}=require('child_process');
const path=require('path');
const fs=require('fs');
const assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const python=process.env.AIRHAND_TEST_PYTHON||path.resolve(root,'.venv/Scripts/python.exe');
const child=spawn(python,[path.join(__dirname,'verify_viewer3d.py')],{cwd:root,stdio:['pipe','pipe','inherit'],windowsHide:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function glb(){
  const vertices=Buffer.alloc(36);[-1,0,0,1,0,0,0,2,0].forEach((v,i)=>vertices.writeFloatLE(v,i*4));
  const json=Buffer.from(JSON.stringify({asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes:[{name:'Test triangle',mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0},material:0}]}],materials:[{doubleSided:true,pbrMetallicRoughness:{baseColorFactor:[.2,.8,.5,1]}}],buffers:[{byteLength:36}],bufferViews:[{buffer:0,byteOffset:0,byteLength:36}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[-1,0,0],max:[1,2,0]}]}));
  const pad=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,32)]),total=12+8+pad.length+8+36,head=Buffer.alloc(20),bin=Buffer.alloc(8);
  head.writeUInt32LE(0x46546c67,0);head.writeUInt32LE(2,4);head.writeUInt32LE(total,8);head.writeUInt32LE(pad.length,12);head.writeUInt32LE(0x4e4f534a,16);bin.writeUInt32LE(36,0);bin.writeUInt32LE(0x004e4942,4);
  return Buffer.concat([head,pad,bin,vertices]);
}
(async()=>{
  let browser;
  try{
    const info=await new Promise((resolve,reject)=>{let s='';const timer=setTimeout(()=>reject(Error('Test server timeout')),20000);child.stdout.on('data',b=>{s+=b;const line=s.split('\n')[0];if(line.includes('port')){clearTimeout(timer);resolve(JSON.parse(line));}});child.on('exit',code=>{if(code)reject(Error('Test server exited '+code));});});
    const base=`http://127.0.0.1:${info.port}`;
    const unauth=await fetch(base+'/api/state');assert.equal(unauth.status,403);
    const forbidden=await fetch(base+'/api/command',{method:'POST',headers:{'Origin':'https://example.com','Content-Type':'application/json','X-AirHand-Token':info.token},body:'{"action":"start"}'});assert.equal(forbidden.status,403);
    const hiddenFile=await fetch(base+'/../../settings.json');assert.equal(hiddenFile.status,404);
    browser=await chromium.launch({...(process.env.AIRHAND_BROWSER ? {executablePath:process.env.AIRHAND_BROWSER} : {channel:'chrome'}),headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
    const page=await browser.newPage({viewport:{width:1440,height:980},deviceScaleFactor:1});
    const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))external.push(r.url());});
    await page.goto(base+'/#'+info.token);await page.waitForFunction(()=>window.airhandDiagnostics?.().parts===6);
    await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('已连接'));
    await page.locator('.part').nth(4).click();assert((await page.evaluate(()=>airhandDiagnostics().selected)).includes('光学镜组'));
    await page.locator('#explode').evaluate(e=>{e.value='.7';e.dispatchEvent(new Event('input'));});
    assert.equal((await page.evaluate(()=>airhandDiagnostics())).explode,.7);
    const screenshots=path.join(root,'screenshots');fs.mkdirSync(screenshots,{recursive:true});
    await page.screenshot({path:path.join(screenshots,'viewer3d.png'),fullPage:true});
    await page.locator('#isolate').click();await page.locator('#show-all').click();await page.locator('#reset').click();
    await page.locator('#camera-toggle').click();await page.waitForFunction(()=>!document.querySelector('#enable').disabled);await page.locator('#enable').click();
    await page.waitForFunction(()=>airhandDiagnostics().active===true);
    child.stdin.write(JSON.stringify({pose:'release',x:.5,y:.5})+'\n');await sleep(200);
    child.stdin.write(JSON.stringify({pose:'pinch'})+'\n');await sleep(220);
    child.stdin.write(JSON.stringify({x:.60})+'\n');
    await page.waitForFunction(()=>airhandDiagnostics().rotation[0]>.4);
    await sleep(300); // Wait for display interpolation to settle before loss.
    const before=(await page.evaluate(()=>airhandDiagnostics())).rotation[0];
    child.stdin.write(JSON.stringify({pose:'none'})+'\n');await sleep(220);
    child.stdin.write(JSON.stringify({pose:'pinch',x:.2,y:.2})+'\n');await sleep(250);
    assert(Math.abs((await page.evaluate(()=>airhandDiagnostics())).rotation[0]-before)<.15);
    await page.keyboard.press('Escape');await page.waitForFunction(()=>!airhandDiagnostics().active);
    await page.locator('#file').setInputFiles({name:'fixture.glb',mimeType:'model/gltf-binary',buffer:glb()});
    await page.waitForFunction(()=>airhandDiagnostics().parts===1);assert.equal(await page.locator('#model-title').textContent(),'fixture.glb');
    await page.locator('#file').setInputFiles({name:'broken.glb',mimeType:'model/gltf-binary',buffer:Buffer.from('bad')});await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('导入失败'));assert.equal((await page.evaluate(()=>airhandDiagnostics())).parts,1);
    await page.locator('#builtin').click();await page.waitForFunction(()=>airhandDiagnostics().parts===6);
    await page.setViewportSize({width:1024,height:768});await sleep(200);assert(await page.locator('#reset').isVisible());
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    await page.locator('#exit').click();
    console.log(JSON.stringify({result:'PASS',webgl:true,builtin_parts:6,local_glb_import:true,invalid_glb_preserves_model:true,synthetic_pinch_rotation:true,loss_reentry_no_jump:true,esc_pause:true,no_external_requests:true,api_auth:true,camera_opened:false}));
  }finally{if(browser)await browser.close();child.stdin.end();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
