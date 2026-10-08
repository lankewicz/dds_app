// -----------------------------------------------------------------------------
// Arquivo : static/js/monitor_feed.js
// Objetivo: Gestão do feed de atividades, auditoria de mudanças em tempo real,
//           cache local em localStorage e renderização lateral.
// -----------------------------------------------------------------------------

// Nova versão descarta eventos antigos que usavam a hora da raspagem.
const getLocalFeedCacheKey = (empresa) => `dds_activity_feed_local_cache_v2_${empresa || 'default'}`;
const getFeedStateKey = (empresa) => `${getLocalFeedCacheKey(empresa)}_states`;
const RECENT_FEED_MS = 24 * 60 * 60 * 1000;
function isRecentFeedItem(item, now = Date.now()) {
  const timestamp = new Date(item.activityAt).getTime();
  return !item.snapshotOnly && Number.isFinite(timestamp) && timestamp <= now && now - timestamp <= RECENT_FEED_MS;
}

function reconcileActivityFeed(previous, incoming, states, now = Date.now()) {
  const changes = [];
  for (const item of incoming) {
    if (!item.stateKey) {
      if (isRecentFeedItem(item, now)) changes.push(item);
      continue;
    }
    const last = states[item.stateKey];
    states[item.stateKey] = item.stateValue;
    if (item.stateOnly) continue;
    if (last === item.stateValue) continue;
    if (!item.snapshotOnly) {
      if (isRecentFeedItem(item, now)) changes.push(item);
    } else if (last !== undefined) {
      const activityAt = new Date(now).toISOString();
      changes.push({...item, snapshotOnly: false, activityAt,
        eventId: `${item.stateKey}_${item.stateValue}_observed_${activityAt}`,
        label: `${item.label} (detectado pela torre)`,
        time: new Intl.DateTimeFormat('pt-BR', {timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit'}).format(new Date(now))});
    }
  }
  return mergeActivityFeedItems(previous.filter(item => isRecentFeedItem(item, now)), changes);
}
let currentFeedItems = [];
let latestFeedItems = [];
let summaryMode = 'execution';
let summaryTimer = null;
let currentFeedSummary = null;

function renderRotatingSummary() {
  const element = document.getElementById('activityFeedSummary');
  if (!element || !currentFeedSummary) return;
  const execution = summaryMode === 'execution';
  const counts = execution ? currentFeedSummary.execution : currentFeedSummary.queue;
  element.textContent = `${execution ? 'EXECUÇÃO' : 'FILA'}: ${counts.comercial} Comerciais · ${counts.emergencia} Emergências`;
}

function refreshVisibleFeed() {
  const teams = new Set((window.monitorState?.getCurrentItems?.() || [])
    .map(item => String(item.teamKey || item.equipe || '').trim().toUpperCase()));
  const visible = currentFeedItems.filter(item => teams.has(String(item.teamKey || item.equipe || '').trim().toUpperCase()));
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

function getLocalFeedCache(empresa) {
  try {
    const raw = localStorage.getItem(getLocalFeedCacheKey(empresa));
    const items = raw ? JSON.parse(raw) : [];
    return Array.isArray(items) ? items.filter(item => isRecentFeedItem(item)) : [];
  } catch (e) {
    console.warn("Erro ao ler cache local de atividades:", e);
    return [];
  }
}

function saveLocalFeedCache(empresa, items) {
  try {
    localStorage.setItem(getLocalFeedCacheKey(empresa), JSON.stringify(items));
  } catch (e) {
    console.warn("Erro ao salvar cache local de atividades:", e);
  }
}

function isUsefulActivityFeedItem(item) {
  const label = String(item?.label || '').trim().toUpperCase();
  if (!label || label === 'ROTALOG') return false;
  if (label.includes(' - FILA:')) return false;
  if (label.includes('DADOS OPERACIONAIS ATUALIZADOS')) return false;
  if (label.includes('INATIVADA') || label.includes('INATIVADO')) return false;
  if (label.includes('ATIVADA') || label.includes('ATIVADO')) return false;
  return true;
}

function mergeActivityFeedItems(localItems, newItems) {
  const mergedMap = new Map();
  const getUniqueKey = (item) => {
    if (item.eventId) return item.eventId;
    const timeKey = item.activityAt || item.time || '';
    const team = item.teamKey || item.equipe || '';
    const label = item.label || item.source || '';
    return `${timeKey}_${team}_${label}`;
  };

  (localItems || []).filter(isUsefulActivityFeedItem).forEach(item => {
    const key = getUniqueKey(item);
    if (key) mergedMap.set(key, item);
  });

  (newItems || []).filter(isUsefulActivityFeedItem).forEach(item => {
    const key = getUniqueKey(item);
    if (key) mergedMap.set(key, item);
  });

  const mergedList = Array.from(mergedMap.values());
  mergedList.sort((a, b) => {
    const dateA = a.activityAt ? new Date(a.activityAt).getTime() : 0;
    const dateB = b.activityAt ? new Date(b.activityAt).getTime() : 0;
    if (dateA && dateB) return dateB - dateA;
    const strA = a.activityAt || a.time || '';
    const strB = b.activityAt || b.time || '';
    return strB.localeCompare(strA);
  });

  return mergedList.slice(0, 1000);
}

function renderActivityFeed(items = [], summary = null) {
  const activityFeedPanel = document.getElementById("activityFeedPanel");
  const activityFeedList = document.getElementById("activityFeedList");
  const activityFeedSummary = document.getElementById("activityFeedSummary");

  if (!activityFeedPanel || !activityFeedList) return;
  if (activityFeedSummary && summary) {
    currentFeedSummary = summary;
    renderRotatingSummary();
    if (summaryTimer === null) {
      summaryTimer = setInterval(() => {
        summaryMode = summaryMode === 'execution' ? 'queue' : 'execution';
        renderRotatingSummary();
      }, 5000);
    }
  }
  const visible = items
    .filter(isUsefulActivityFeedItem)
    .slice(0, 1000);
  if (!visible.length) {
    activityFeedList.innerHTML = '<div class="activityFeedEmpty">Sem mudanças recentes</div>';
    return;
  }

  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
  const fmtHM = window.monitorUtils?.fmtHourMinute || fmtHourMinute;

  activityFeedList.innerHTML = visible.map((item) => {
    const time = esc(item.time || fmtHM(item.activityAt));
    const team = esc(String(item.teamKey || item.equipe || '-').trim().toUpperCase());
    let rawLabel = String(item.label || 'Mudança operacional').trim();

    // Se vier no formato antigo 'TEAM - Label', limpa o prefixo repetido
    if (rawLabel.toUpperCase().startsWith(`${team} - `)) {
      rawLabel = rawLabel.substring(team.length + 3).trim();
    } else if (rawLabel.toUpperCase().startsWith(`${team} `)) {
      rawLabel = rawLabel.substring(team.length + 1).trim();
    }

    const label = esc(rawLabel);
    const source = esc(item.source || '');
    return `<div class="activityFeedItem" data-source="${source}">` +
      `<span class="activityFeedTime">${time}</span>` +
      `<span class="activityFeedSep">|</span>` +
      `<span class="activityFeedTeam">${team}</span>` +
      `<span class="activityFeedSep">|</span>` +
      `<span class="activityFeedLabel">${label}</span>` +
    `</div>`;
  }).join('');
}

async function loadActivityFeed() {
  const activityFeedPanel = document.getElementById("activityFeedPanel");
  const getViewModeFn = window.monitorFilters?.getViewMode || (window.monitorState?.getViewMode) || getViewMode;
  if (!activityFeedPanel || (typeof getViewModeFn === 'function' && getViewModeFn() === 'trash')) return;

  const getEmpresaFn = window.monitorFilters?.getEmpresaValue || (window.monitorState?.getEmpresa) || getEmpresaValue;
  const empresa = typeof getEmpresaFn === 'function' ? getEmpresaFn() : '';

  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('limit', '1000');
  try {
    const r = await fetch(`/api/activity-feed?${qs.toString()}`, { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok || !Array.isArray(data.items)) {
      currentFeedItems = getLocalFeedCache(empresa);
      refreshVisibleFeed();
      return;
    }
    latestFeedItems = data.items;
    const previous = getLocalFeedCache(empresa);
    let states = {};
    try { states = JSON.parse(localStorage.getItem(getFeedStateKey(empresa)) || '{}') || {}; } catch (_) {}
    currentFeedItems = reconcileActivityFeed(previous, data.items, states);
    try { localStorage.setItem(getFeedStateKey(empresa), JSON.stringify(states)); } catch (_) {}
    saveLocalFeedCache(empresa, currentFeedItems);
    refreshVisibleFeed();
  } catch (error) {
    console.warn('Erro ao carregar feed de atividades:', error);
    currentFeedItems = getLocalFeedCache(empresa);
    refreshVisibleFeed();
  }
}

window.monitorFeed = {
  refreshVisibleFeed,
  reconcileActivityFeed,
  getLocalFeedCache,
  saveLocalFeedCache,
  isUsefulActivityFeedItem,
  mergeActivityFeedItems,
  renderActivityFeed,
  loadActivityFeed,
};
