const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = {
  activityFeedPanel: {}, activityFeedList: { innerHTML: '' },
  activityFeedSummary: { textContent: '' },
};
let visibleTeams = [{ teamKey: 'T1' }];
let tick;
let timerCount = 0;
const context = vm.createContext({
  setInterval: (callback, delay) => { assert.equal(delay, 5000); tick = callback; timerCount++; return 1; },
  window: { monitorState: { getCurrentItems: () => visibleTeams }, monitorUtils: { escapeHtml: s => String(s), fmtHourMinute: () => '10:00' } },
  document: { getElementById: key => elements[key] }, console,
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../monitor/static/js/monitor_feed.js'), 'utf8'), context);
vm.runInContext(`currentFeedItems = [
  {teamKey:'T1', label:'Execução', time:'10:00', turnOpen:true, execution:{comercial:1, emergencia:0}, queue:{comercial:3, emergencia:2}},
  {teamKey:'T2', label:'Turno Fechado', time:'09:00', turnOpen:false, queue:{comercial:99, emergencia:99}}
]; latestFeedItems = currentFeedItems; refreshVisibleFeed();`, context);
assert.ok(elements.activityFeedList.innerHTML.includes('T1'));
assert.ok(!elements.activityFeedList.innerHTML.includes('T2'));
assert.equal(elements.activityFeedSummary.textContent, 'EXECUÇÃO: 1 Comerciais · 0 Emergências');
tick();
assert.equal(elements.activityFeedSummary.textContent, 'FILA: 3 Comerciais · 2 Emergências');
tick();
assert.equal(elements.activityFeedSummary.textContent, 'EXECUÇÃO: 1 Comerciais · 0 Emergências');
visibleTeams = [{ teamKey: 'T2' }];
context.window.monitorFeed.refreshVisibleFeed();
assert.ok(!elements.activityFeedList.innerHTML.includes('T1'));
assert.ok(elements.activityFeedList.innerHTML.includes('T2'));
tick();
assert.equal(elements.activityFeedSummary.textContent, 'FILA: 99 Comerciais · 99 Emergências');
visibleTeams = [];
context.window.monitorFeed.refreshVisibleFeed();
assert.equal(elements.activityFeedSummary.textContent, 'FILA: 0 Comerciais · 0 Emergências');
assert.equal(timerCount, 1);
console.log('OK: eventos e fila seguem as equipes visíveis e os filtros.');

const reconcile = context.window.monitorFeed.reconcileActivityFeed;
const now = Date.parse('2026-10-08T18:00:00-03:00');
const closed = {teamKey:'T1', stateKey:'team_T1', stateValue:'FECHADO',
  label:'Equipe: Turno Fechado', eventId:'closed', activityAt:'2026-10-08T17:00:00-03:00'};
let states = {};
let history = reconcile([], [closed], states, now);
assert.equal(history.length, 1);
history = reconcile(history, [{...closed, eventId:'scrape', activityAt:'2026-10-08T18:00:00-03:00'}], states, now);
assert.equal(history.length, 1);
assert.equal(history[0].activityAt, closed.activityAt);
states = {};
const unknown = {...closed, snapshotOnly:true, activityAt:null};
assert.equal(reconcile([], [unknown], states, now).length, 0);
assert.equal(reconcile([], [unknown], states, now + 60000).length, 0);
assert.equal(reconcile([], [{...closed, activityAt:'2026-10-06T17:00:00-03:00'}], {}, now).length, 0);
states = {team_T1:'ABERTO'};
history = reconcile([], [unknown], states, now);
assert.equal(history.length, 1);
assert.ok(history[0].label.includes('detectado pela torre'));
assert.equal(reconcile(history, [unknown], states, now + 60000).length, 1);
console.log('OK: fechamento recente aparece uma vez; raspagem não renova horário; estado inicial e fechamento antigo não geram eventos.');
