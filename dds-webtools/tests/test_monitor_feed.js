const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = {activityFeedPanel: {}, activityFeedList: {innerHTML: ''}, activityFeedSummary: {textContent: ''}};
let empresa = 'ChicoEletro';
let visibleTeams = [{teamKey: 'T1'}, {teamKey: 'T2'}];
let tick;
let timerCount = 0;
let fetchCount = 0;
let fetchImpl;
const storage = new Map();
const context = vm.createContext({
  URLSearchParams, console: {warn() {}},
  localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
  setInterval: (callback, delay) => {assert.equal(delay, 5000); tick = callback; timerCount++; return 1;},
  fetch: (...args) => {fetchCount++; return fetchImpl(...args);},
  window: {monitorState: {getCurrentItems: () => visibleTeams, getEmpresa: () => empresa, getViewMode: () => 'active'}},
  document: {getElementById: key => elements[key]},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../monitor/static/js/monitor_feed.js'), 'utf8'), context);
const feed = context.window.monitorFeed;
const event = (id, changes = {}) => ({id, teamKey: 'T1', entityId: 'service-1', type: 'C', protocol: '20265804191700',
  status: 'EXECUCAO', occurredAt: '2026-10-20T00:01:00-03:00', timeSource: 'consolidated', ...changes});
const counts = [{teamKey: 'T1', execution: {comercial: 1, emergencia: 0}, queue: {comercial: 3, emergencia: 2}},
  {teamKey: 'T2', execution: {comercial: 0, emergencia: 1}, queue: {comercial: 5, emergencia: 4}}];
const payload = (items, changes = {}) => ({empresa, company: empresa, schemaVersion: 1, timezone: 'America/Sao_Paulo',
  windowHours: 24, updatedAt: '2026-10-20T00:02:00-03:00', available: true, items, teamSummary: counts, ...changes});
const reply = data => ({ok: true, json: async () => data});
const load = async data => {fetchImpl = async () => reply(data); await feed.loadActivityFeed();};
const html = () => elements.activityFeedList.innerHTML;

(async () => {
  await load(payload([event('old', {occurredAt: '2026-10-19T23:59:00-03:00'}), event('new', {teamKey: 'T2'})]));
  assert.ok(html().indexOf('data-event-id="new"') < html().indexOf('data-event-id="old"'));
  assert.ok(html().includes('>00:01</td>'));
  assert.ok(html().includes('19/10/2026'));
  assert.ok(html().includes('title="20265804191700">5804191700'));
  for (const header of ['Hora', 'Equipe', 'Tipo', 'Protocolo', 'Status']) assert.ok(html().includes(`<th>${header}</th>`));
  assert.equal(elements.activityFeedSummary.textContent, 'EXECUÇÃO: 1 Comerciais · 1 Emergências');
  tick();
  assert.equal(elements.activityFeedSummary.textContent, 'FILA: 8 Comerciais · 6 Emergências');
  visibleTeams = [{teamKey: 'T1'}];
  feed.refreshVisibleFeed();
  assert.ok(!html().includes('data-event-id="new"'));
  assert.equal(elements.activityFeedSummary.textContent, 'FILA: 3 Comerciais · 2 Emergências');
  assert.equal(timerCount, 1);

  await load(payload([event('corrected'), event('removed')]));
  await load(payload([event('corrected', {occurredAt: '2026-10-20T08:19:00-03:00'})]));
  assert.equal((html().match(/data-event-id="corrected"/g) || []).length, 1);
  assert.ok(html().includes('>08:19</td>'));
  assert.ok(!html().includes('removed'));
  fetchImpl = async () => {throw Error('offline');};
  await feed.loadActivityFeed();
  assert.ok(html().includes('indisponíveis') && html().includes('corrected'));
  assert.ok(!html().includes('Sem eventos'));
  for (const data of [payload([event('invalid', {occurredAt: 'bad'})]),
    payload([event('invalid', {occurredAt: '2026-02-30T08:00:00-03:00'})]), payload([], {schemaVersion: 2}),
    payload([], {company: 'Outra'}), payload(null, {available: false})]) {
    await load(data);
    assert.ok(html().includes('corrected'));
    assert.ok(html().includes('indisponíveis'));
  }
  await load(payload([]));
  assert.ok(html().includes('Sem eventos nas últimas 24 horas'));
  assert.ok(!html().includes('corrected') && !html().includes('indisponíveis'));

  assert.equal(feed.displayFeedProtocol(event('c')), '5804191700');
  assert.equal(feed.displayFeedProtocol(event('e', {type: 'E'})), '20265804191700');
  assert.equal(feed.displayFeedProtocol(event('null', {type: null})), '20265804191700');
  assert.equal(feed.displayFeedProtocol(event('badyear', {protocol: '99995804191700'})), '99995804191700');
  assert.equal(feed.displayFeedProtocol(event('short', {protocol: '51063369'})), '51063369');
  for (const status of ['TURNO_ABERTO', 'TURNO_FECHADO', 'INTERVALO_INICIADO', 'INTERVALO_ENCERRADO']) {
    assert.equal(feed.displayFeedProtocol(event('shift', {status})), '—');
  }
  await load(payload([event('estimated', {timeSource: 'inferred', protocol: '<img src=x onerror="x">', entityId: '"><script>x</script>'}),
    event('emergency', {type: 'E', protocol: '51063369'}), event('unknown', {type: null, status: 'TURNO_ABERTO'})]));
  assert.ok(html().includes('Horário estimado') && html().includes('≈'));
  assert.ok(html().includes('timeSource: inferred') && html().includes('recebido do diário'));
  assert.ok(html().includes('>51063369</td>'));
  assert.ok(html().includes('title="Sem tipo">—'));
  assert.ok(!html().includes('<img') && !html().includes('<script>'));
  assert.ok(html().includes('&lt;img') && html().includes('&quot;'));

  // A slow response cannot cross companies; overlapping refreshes share one request.
  let release;
  const before = fetchCount;
  fetchImpl = () => new Promise(resolve => {release = resolve;});
  const old = feed.loadActivityFeed();
  const duplicate = feed.loadActivityFeed();
  assert.equal(fetchCount, before + 1);
  empresa = 'Outra';
  feed.refreshVisibleFeed();
  assert.ok(!html().includes('estimated'));
  const next = payload([event('other')]);
  fetchImpl = async () => reply(next);
  release(reply(payload([event('leak')], {empresa: 'ChicoEletro', company: 'ChicoEletro'})));
  await old;
  await duplicate;
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(html().includes('other') && !html().includes('leak'));
  assert.ok(feed.getLocalFeedCache('ChicoEletro').items.some(item => item.id === 'estimated'));
  assert.ok(feed.getLocalFeedCache('Outra').items.some(item => item.id === 'other'));

  await load(payload(Array.from({length: 1101}, (_, index) => event(`full-${index}`))));
  assert.equal((html().match(/data-event-id=/g) || []).length, 1101);

  empresa = 'SemArquivo';
  await load(payload(null, {available: false}));
  assert.ok(html().includes('indisponíveis') && !html().includes('Sem eventos'));

  // Healthy Orange reads never call the event API on Cloud Run. Counts use the same card snapshot fields.
  empresa = 'ChicoEletro';
  visibleTeams = [{teamKey: 'T1', origemAtualizacao: 'TORRE_CONTROLE', operacional: {servicoAtual: {}}, rotalogSnapshot: {
    fila: {comercial: 3, emergencia: 2}, ordensServico: {atual: {statusAtual: 'EXECUCAO', categoria: 'COMERCIAL'}}}}];
  context.window.orangeEventsEnabled = true;
  let directReads = 0;
  context.window.orangeTorre = {read: async (route, company) => {
    assert.equal(route, '/api/rotalog/events'); assert.equal(company, empresa); directReads++;
    return payload([event('direct')]);
  }};
  const beforeDirect = fetchCount;
  fetchImpl = async () => {throw Error('No event request should reach Cloud Run');};
  await feed.loadActivityFeed();
  await feed.loadActivityFeed();
  assert.equal(fetchCount, beforeDirect);
  assert.equal(directReads, 2);
  assert.ok(html().includes('direct'));
  const firstHeader = elements.activityFeedSummary.textContent;
  tick();
  assert.deepEqual(new Set([firstHeader, elements.activityFeedSummary.textContent]),
    new Set(['EXECUÇÃO: 1 Comerciais · 0 Emergências', 'FILA: 3 Comerciais · 2 Emergências']));
  context.window.orangeTorre.read = async () => {throw Error('Orange offline');};
  await load(payload([event('firebase-backup')]));
  assert.ok(html().includes('firebase-backup'));
  assert.equal(fetchCount, beforeDirect + 1);
  context.window.orangeTorre.read = async () => payload([]);
  await feed.loadActivityFeed();
  assert.ok(html().includes('Sem eventos nas últimas 24 horas'));
  assert.equal(fetchCount, beforeDirect + 1);
  context.window.orangeTorre.read = async () => payload([event('latest-revision')], {updatedAt: '2026-10-20T08:10:00-03:00'});
  await feed.loadActivityFeed();
  context.window.orangeTorre.read = async () => {throw Error('Orange offline');};
  await load(payload([event('old-revision')], {updatedAt: '2026-10-20T08:00:00-03:00'}));
  assert.ok(html().includes('latest-revision') && !html().includes('old-revision'));
  assert.ok(html().includes('indisponíveis'));
  console.log('OK: janela, ordenação, correções, remoções, protocolos, filtros, totais, falhas, escape e isolamento.');
})().catch(error => {console.error(error); process.exitCode = 1;});
