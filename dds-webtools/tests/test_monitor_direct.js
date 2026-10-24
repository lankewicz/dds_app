const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const zlib = require('node:zlib');
const stamp = '2026-10-21T12:00:00-03:00';
const card = key => ({teamKey:key, active:true, setor:'A', updatedAt:stamp,
  ddsHistory:['ok'], ddsDays:['2026-10-21'], ddsTimes:{}, operacional:{}});
const projection = {schemaVersion:1, company:'ChicoEletro', collectedAt:stamp, composedAt:stamp, stale:false,
  sources:Object.fromEntries(['rotalog','cadastro','dds'].map(key=>[key,{updatedAt:stamp, stale:false}])), items:[card('E1')]};
const dateParts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone:'America/Sao_Paulo',
  year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(new Date()).map(part=>[part.type,part.value]));
const day = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
const personnel = {schemaVersion:1, data:day, empresa:'ChicoEletro', registros:[{equipe:'e1', tablet:'CA231',
  eletricistas:[{registro:'123456', nome:'MATEUS COMPLETO'}, {registro:'654321', nome:'GUILHERME COMPLETO'}]}]};
let orangeFails = false, backupFails = false, issued = 0, backups = 0, direct = 0;
const context = vm.createContext({URL,URLSearchParams,Map,Set,Date,Promise,JSON,Uint8Array,TextDecoder,Response,Blob,
  DecompressionStream,AbortSignal,console, window:{portalReady:Promise.resolve()},
  fetch:async (url, options={}) => {
    if (url === '/api/torre/access') {
      issued++;
      return Response.json({url:'https://orange.test',token:'temporary',company:'ChicoEletro',expiresIn:600,
        backup:{monitor:'https://storage.googleapis.com/private/monitor?signature=test'}});
    }
    if (url.startsWith('https://orange.test/api/data/rotalog/eletricistas/diario')) {
      direct++; assert.equal(options.credentials,'omit');
      assert.ok(options.headers.Authorization.startsWith('Bearer '));
      if (url.endsWith('/rotalog/eletricistas/diario')) {
        return Response.json({company:'ChicoEletro', entries:[{name:`${day}.json.gz`,
          path:`rotalog/eletricistas/diario/${day}.json.gz`, kind:'file'}]});
      }
      if (url.endsWith(`/${day}.json.gz`)) {
        return new Response(zlib.gzipSync(JSON.stringify(personnel)));
      }
      return new Response('',{status:404});
    }
    if (url.startsWith('https://orange.test')) {
      direct++; assert.equal(options.credentials,'omit');
      assert.ok(options.headers.Authorization.startsWith('Bearer '));
      if (orangeFails) return new Response('',{status:503});
      return Response.json(projection);
    }
    backups++; assert.equal(options.credentials,'omit'); assert.equal(options.headers,undefined);
    if (backupFails) return new Response('',{status:503});
    return new Response(zlib.gzipSync(JSON.stringify(projection)));
  }});
for (const file of ['hosting/orange-torre.js','hosting/monitor-direct.js'])
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'..',file),'utf8'),context);
(async()=>{
  const validate = context.window.monitorDirect.validate;
  assert.throws(()=>validate({...projection, company:'Other'},'ChicoEletro'));
  assert.throws(()=>validate({...projection, items:[card('E1'),card('E1')]},'ChicoEletro'));
  assert.throws(()=>validate({...projection, sources:{}},'ChicoEletro'));
  const result = await context.window.monitorDirect.turnos(new URLSearchParams({empresa:'ChicoEletro',active:'true',setor:'A'}));
  assert.equal(result.items.length,1); assert.equal(result.dataSource,'orangepi');
  assert.deepEqual(JSON.parse(JSON.stringify(result.items[0].copelPersonnel)), [
    {registro:'123456', nome:'MATEUS COMPLETO'},
    {registro:'654321', nome:'GUILHERME COMPLETO'},
  ]);
  assert.equal(result.items[0].copelTablet,'CA231');
  assert.equal((await context.window.monitorDirect.turnos(new URLSearchParams({empresa:'ChicoEletro',setor:'B'}))).items.length,0);
  assert.equal(issued,1); assert.equal(backups,0);
  await new Promise(resolve=>setTimeout(resolve,1050)); orangeFails=true;
  const fallback=await context.window.orangeTorre.snapshot('monitor','ChicoEletro',validate);
  assert.equal(fallback.source,'firebase'); assert.equal(backups,1);
  await new Promise(resolve=>setTimeout(resolve,1050)); backupFails=true;
  await assert.rejects(context.window.orangeTorre.snapshot('monitor','ChicoEletro',validate));
  assert.equal(issued,1);
  await assert.rejects(context.window.orangeTorre.snapshot('monitor','Other',validate));
  console.log('OK: projeção completa, filtros, isolamento, leitura direta, backup gzip privado e falha explícita.');
})().catch(error=>{console.error(error);process.exitCode=1});
