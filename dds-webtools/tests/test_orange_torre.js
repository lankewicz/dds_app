const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let credentials = 0;
let reads = 0;
let nextResponse;
const context = vm.createContext({URL, AbortSignal,
  window: {portalReady: Promise.resolve({email: 'user'})},
  fetch: async (url, options) => {
    if (url === '/api/torre/access') {
      credentials++;
      return {ok: true, json: async () => ({url: 'https://orange.test', company: 'ChicoEletro', token: 'temporary', expiresIn: 600})};
    }
    reads++;
    assert.equal(url, 'https://orange.test/api/rotalog/events');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers.Authorization, 'Bearer temporary');
    if (reads > 1) assert.equal(options.headers['If-None-Match'], '"version-1"');
    return nextResponse;
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../hosting/orange-torre.js'), 'utf8'), context);
const client = context.window.orangeTorre;
(async () => {
  const data = {company: 'ChicoEletro', items: []};
  nextResponse = {ok: true, status: 200, headers: {get: () => '"version-1"'}, json: async () => data};
  assert.equal(await client.read('/api/rotalog/events', 'ChicoEletro'), data);
  nextResponse = {ok: false, status: 304};
  assert.equal(await client.read('/api/rotalog/events', 'ChicoEletro'), data);
  assert.equal(credentials, 1);
  await assert.rejects(() => client.read('/api/rotalog/events', 'Outra'), /outra empresa/);
  await assert.rejects(() => client.read('/.env', 'ChicoEletro'), /não permitida/);
  nextResponse = {ok: false, status: 401};
  await assert.rejects(() => client.read('/api/rotalog/events', 'ChicoEletro'), /indisponíveis/);
  // Credential is renewed after 401. Reconfigure fetch to ensure a bad-company payload is rejected.
  context.fetch = async (url, options) => url === '/api/torre/access'
    ? {ok: true, json: async () => ({url: 'https://orange.test', company: 'ChicoEletro', token: 'renewed', expiresIn: 600})}
    : {ok: true, status: 200, json: async () => ({company: 'Outra'})};
  await assert.rejects(() => client.read('/api/rotalog/events', 'ChicoEletro'), /outra empresa/);
  context.fetch = async (url, options) => {
    assert.equal(options.method, 'GET');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers.Authorization, 'Bearer renewed');
    assert.ok(url.startsWith('https://orange.test/api/data'));
    return {ok: true, headers: {get: () => 'ssd'}, json: async () => ({company: 'ChicoEletro', entries: []}),
      blob: async () => 'raw-file-bytes'};
  };
  assert.equal((await client.listData('rotalog/equipes', 'ChicoEletro')).source, 'ssd');
  assert.equal((await client.downloadData('rotalog/equipes/current/index.json.gz', 'ChicoEletro')).blob, 'raw-file-bytes');
  await assert.rejects(() => client.downloadData('../.env', 'ChicoEletro'), /inválido/);
  await assert.rejects(() => client.listData('', 'Outra'), /outra empresa/);
  console.log('OK: credencial reutilizada, leitura HTTPS direta, 304 autenticado, isolamento e renovação.');
})().catch(error => {console.error(error); process.exitCode = 1;});
