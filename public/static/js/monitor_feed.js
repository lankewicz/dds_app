// Current collector window. Event history is never reconstructed from card snapshots.
const getLocalFeedCacheKey = empresa => `dds_activity_feed_window_v3_${String(empresa).trim().toLowerCase()}`;
const FEED_STATUS = {
  DESLOCAMENTO: 'Deslocamento', EXECUCAO: 'Execução', CONCLUSAO: 'Conclusão',
  TURNO_ABERTO: 'Turno aberto', TURNO_FECHADO: 'Turno fechado',
  INTERVALO_INICIADO: 'Intervalo iniciado', INTERVALO_ENCERRADO: 'Intervalo encerrado',
};
let currentFeedItems = [];
let latestFeedItems = []; // Per-team counts retain the existing source, independently of events.
let summaryMode = 'execution';
let summaryTimer = null;
let currentFeedSummary = null;
let feedCompany = null;
let feedInFlight = null;
let feedUnavailable = null;
let feedHasWindow = false;
let feedUpdatedAt = null;

function getFeedCompany() {
  const getter = window.monitorFilters?.getEmpresaValue || window.monitorState?.getEmpresa;
  return String(typeof getter === 'function' ? getter() : '').trim();
}

function validFeedDate(value) {
  const parts = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!parts || !Number.isFinite(Date.parse(value))) return false;
  const [year, month, day, hour, minute, second] = parts.slice(1).map(Number);
  const days = [31, year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1] && hour < 24 && minute < 60 && second < 60;
}

function validateFeedWindow(data, empresa) {
  if (!data || data.schemaVersion !== 1 || data.windowHours !== 24 || data.timezone !== 'America/Sao_Paulo'
      || typeof data.company !== 'string' || data.company.trim().toLowerCase() !== empresa.trim().toLowerCase()
      || !validFeedDate(data.updatedAt) || !Array.isArray(data.items)) throw new Error('Janela de eventos inválida');
  const byId = new Map();
  for (const item of data.items) {
    if (!item || !['id', 'teamKey', 'entityId', 'timeSource'].every(key => typeof item[key] === 'string' && item[key].trim())
        || !Object.hasOwn(FEED_STATUS, item.status) || !validFeedDate(item.occurredAt)
        || !Object.hasOwn(item, 'type') || !['C', 'E', null].includes(item.type)
        || !Object.hasOwn(item, 'protocol') || !(item.protocol === null || typeof item.protocol === 'string')) {
      throw new Error('Evento inválido');
    }
    byId.set(item.id, item);
  }
  return [...byId.values()].sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt) || b.id.localeCompare(a.id));
}

function getLocalFeedCache(empresa) {
  try {
    const data = JSON.parse(localStorage.getItem(getLocalFeedCacheKey(empresa)) || 'null');
    return data ? { ...data, items: validateFeedWindow(data, empresa) } : null;
  } catch (_) { return null; }
}

function saveLocalFeedCache(empresa, data) {
  try {
    const {schemaVersion, company, timezone, windowHours, updatedAt, items} = data;
    localStorage.setItem(getLocalFeedCacheKey(empresa), JSON.stringify({schemaVersion, company, timezone, windowHours, updatedAt, items}));
  } catch (_) { /* Storage may be disabled; the in-memory window remains valid. */ }
}

function selectFeedCompany(empresa) {
  if (empresa === feedCompany) return;
  feedCompany = empresa;
  const cached = getLocalFeedCache(empresa);
  currentFeedItems = cached?.items || [];
  latestFeedItems = [];
  feedHasWindow = !!cached;
  feedUpdatedAt = cached?.updatedAt || null;
  feedUnavailable = null;
}

function renderRotatingSummary() {
  const element = document.getElementById('activityFeedSummary');
  if (!element || !currentFeedSummary) return;
  const execution = summaryMode === 'execution';
  const counts = execution ? currentFeedSummary.execution : currentFeedSummary.queue;
  element.textContent = `${execution ? 'EXECUÇÃO' : 'FILA'}: ${counts.comercial} Comerciais · ${counts.emergencia} Emergências`;
}

function refreshVisibleFeed() {
  selectFeedCompany(getFeedCompany());
  if (window.orangeEventsEnabled) latestFeedItems = feedCountsFromCards();
  const teams = new Set((window.monitorState?.getCurrentItems?.() || [])
    .map(item => String(item.teamKey || item.equipe || '').trim().toUpperCase()));
  const visible = currentFeedItems.filter(item => teams.has(String(item.teamKey).trim().toUpperCase()));
  const counted = new Set();
  const summary = { execution: { comercial: 0, emergencia: 0 }, queue: { comercial: 0, emergencia: 0 } };
  latestFeedItems.filter(item => teams.has(String(item.teamKey || item.equipe || '').trim().toUpperCase())).forEach(item => {
    const key = String(item.teamKey || item.equipe || '').trim().toUpperCase();
    if (counted.has(key)) return;
    counted.add(key);
    for (const kind of ['execution', 'queue']) {
      for (const category of ['comercial', 'emergencia']) {
        summary[kind][category] += Math.max(0, Number(item[kind]?.[category]) || 0);
      }
    }
  });
  renderActivityFeed(visible, summary);
}

function feedCountsFromCards() {
  // Same snapshot fields and rules as the existing server summary. No events are derived here.
  return (window.monitorState?.getCurrentItems?.() || []).filter(item =>
    !item.origemAtualizacao || String(item.origemAtualizacao).toUpperCase() === 'TORRE_CONTROLE').map(item => {
    const snapshot = item.rotalogSnapshot || {};
    const service = [item.operacional?.servicoAtual, snapshot.ordensServico?.atual, snapshot.atividadeAtual]
      .find(value => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length) || {};
    const status = String(service.statusAtual || service.status || item.estado || '').toUpperCase();
    const category = String(service.categoria || service.category || '').toUpperCase();
    const queue = snapshot.fila && typeof snapshot.fila === 'object' && !Array.isArray(snapshot.fila) ? snapshot.fila :
      {comercial: snapshot.ssPendentesComercialCount, emergencia: snapshot.ssPendentesEmergenciaCount};
    return {teamKey: item.teamKey || item.equipe,
      execution: {comercial: Number(status === 'EXECUCAO' && category.includes('COMERC')),
        emergencia: Number(status === 'EXECUCAO' && category.includes('EMERG'))},
      queue: {comercial: Math.max(0, Number(queue.comercial) || 0), emergencia: Math.max(0, Number(queue.emergencia) || 0)}};
  });
}

async function readActivityWindow(empresa) {
  if (window.orangeEventsEnabled) {
    if (window.orangeMonitorEnabled) {
      const {data, source} = await window.orangeTorre.snapshot('events', empresa, validateFeedWindow);
      return {...data, empresa, available: true, source};
    }
    try {
      const data = await window.orangeTorre.read('/api/rotalog/events', empresa);
      validateFeedWindow(data, empresa);
      return {...data, empresa, available: true, source: 'orangepi'};
    } catch (error) {
      console.warn('Orange indisponível; consultando arquivo Firebase:', error);
    }
  }
  // Existing authorized Storage reader remains the fallback; no public download URLs.
  const response = await fetch(`/api/activity-feed?${new URLSearchParams({empresa, limit: '1000'})}`, {cache: 'no-store'});
  const data = await response.json();
  if (!response.ok) throw new Error('Feed indisponível');
  return data;
}

function feedEscape(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
}

function displayFeedProtocol(item) {
  if (item.status.startsWith('TURNO_') || item.status.startsWith('INTERVALO_')) return '—';
  const protocol = item.protocol;
  if (!protocol) return '—';
  // Recognized commercial year prefix; the original value is always retained.
  return item.type === 'C' && /^(?:19|20)\d{12}$/.test(protocol) ? protocol.slice(4) : protocol;
}

function renderActivityFeed(items = [], summary = null) {
  const panel = document.getElementById('activityFeedPanel');
  const list = document.getElementById('activityFeedList');
  if (!panel || !list) return;
  if (summary) {
    currentFeedSummary = summary;
    renderRotatingSummary();
    if (summaryTimer === null) summaryTimer = setInterval(() => {
      summaryMode = summaryMode === 'execution' ? 'queue' : 'execution';
      renderRotatingSummary();
    }, 5000);
  }
  const warning = feedUnavailable === true ? '<div class="activityFeedError" role="status">Eventos indisponíveis' +
    (feedHasWindow ? ' · exibindo última lista válida' : '') + '</div>' :
    feedUnavailable === null ? '<div class="activityFeedEmpty" role="status">Carregando eventos…</div>' : '';
  if (!items.length) {
    list.innerHTML = warning + (feedUnavailable === false && feedHasWindow
      ? '<div class="activityFeedEmpty">Sem eventos nas últimas 24 horas</div>' : '');
    return;
  }
  const clock = new Intl.DateTimeFormat('pt-BR', {timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
  const date = new Intl.DateTimeFormat('pt-BR', {timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'medium'});
  list.innerHTML = warning + '<table class="activityFeedTable"><thead><tr><th>Hora</th><th>Equipe</th><th>Tipo</th><th>Protocolo</th><th>Status</th></tr></thead><tbody>' +
    items.map(item => {
      const stamp = new Date(item.occurredAt);
      const estimated = item.timeSource === 'inferred';
      const source = `${estimated ? 'Horário estimado · ' : ''}timeSource: ${item.timeSource}${item.timeSource === 'consolidated' ? ' · recebido do diário' : ''}`;
      const type = item.type === 'C' ? 'Comercial' : item.type === 'E' ? 'Emergência' : 'Sem tipo';
      return `<tr data-event-id="${feedEscape(item.id)}">` +
        `<td class="activityFeedTime" title="${feedEscape(date.format(stamp) + ' · ' + item.occurredAt + ' · ' + source)}">${feedEscape(clock.format(stamp))}${estimated ? '<span class="activityFeedEstimated" aria-label="Horário estimado"> ≈</span>' : ''}</td>` +
        `<td class="activityFeedTeam">${feedEscape(item.teamKey)}</td>` +
        `<td title="${type}">${item.type || '—'}</td>` +
        `<td title="${feedEscape(item.protocol || '—')}">${feedEscape(displayFeedProtocol(item))}</td>` +
        `<td class="activityFeedStatus status-${feedEscape(item.status)}" title="${feedEscape(source + ' · ocorrência: ' + item.entityId)}">${feedEscape(FEED_STATUS[item.status])}</td></tr>`;
    }).join('') + '</tbody></table>';
}

async function loadActivityFeed() {
  const view = window.monitorFilters?.getViewMode || window.monitorState?.getViewMode;
  if (!document.getElementById('activityFeedPanel') || (typeof view === 'function' && view() === 'trash')) return;
  const empresa = getFeedCompany();
  selectFeedCompany(empresa);
  if (feedInFlight) return feedInFlight;
  feedInFlight = (async () => {
    try {
      const data = await readActivityWindow(empresa);
      if (getFeedCompany() !== empresa) return;
      if (data.empresa !== empresa || typeof data.available !== 'boolean') throw new Error('Feed indisponível');
      if (Array.isArray(data.teamSummary)) latestFeedItems = data.teamSummary;
      const items = data.items === null && !data.available ? null : validateFeedWindow(data, empresa);
      if (items !== null) {
        // A delayed publication must not undo a correction already received from the same producer.
        // This compares two known window revisions, not the age of updatedAt against the clock.
        if (window.orangeEventsEnabled && data.source !== 'orangepi' && feedUpdatedAt
            && Date.parse(data.updatedAt) < Date.parse(feedUpdatedAt)) {
          throw new Error('Arquivo alternativo anterior à última janela válida');
        }
        currentFeedItems = items; // Complete replacement also handles removals and same-id corrections.
        feedHasWindow = true;
        feedUpdatedAt = data.updatedAt;
        saveLocalFeedCache(empresa, {...data, items});
      }
      feedUnavailable = !data.available;
    } catch (error) {
      if (getFeedCompany() === empresa) feedUnavailable = true;
      console.warn('Eventos indisponíveis:', error);
    } finally {
      feedInFlight = null;
      refreshVisibleFeed();
      if (getFeedCompany() !== empresa) loadActivityFeed();
    }
  })();
  return feedInFlight;
}

window.monitorFeed = {refreshVisibleFeed, getLocalFeedCache, saveLocalFeedCache, renderActivityFeed,
  loadActivityFeed, validateFeedWindow, displayFeedProtocol};
