// -----------------------------------------------------------------------------
// Arquivo : static/app.js
// Objetivo: Orquestrador principal do monitor: sincronização Firebase em tempo real,
//           fallback de polling HTTP, ciclo de vida de renderização incremental,
//           navegação SPA e eventos globais do usuário.
// -----------------------------------------------------------------------------

const grid = document.getElementById("grid");
const empresaLabel = document.getElementById("empresaLabel");
const lastSync = document.getElementById("lastSync");
const nextRefresh = document.getElementById("nextRefresh");
const skeletonGrid = document.getElementById("skeletonGrid");
const empresaInput = document.getElementById("empresaInput");
const searchInput = document.getElementById("searchInput");
const teamSelect = document.getElementById("teamSelect");
const kpis = document.getElementById("kpis");
const refreshBtn = document.getElementById("refreshBtn");
const configBtn = document.getElementById("configBtn");
const sectorSelector = document.getElementById('sectorSelector');

function showSkeleton() {
  if (skeletonGrid) skeletonGrid.classList.remove('hidden');
  if (grid) {
    grid.classList.add('hidden');
    grid.innerHTML = '';
  }
}

let cfg = null;
let pollingSeconds = 600;
let pollingTimer = null;
let pollingEnabled = false;
let countdownTimer = null;
let alertTimer = null;
let nextTickAtMs = null;
let currentItems = [];
let allRealtimeItems = [];
let lastData = null;
let ddsDataLoaded = false;

function getPollingSeconds() {
  const seconds = Number(pollingSeconds);
  return Number.isFinite(seconds) && seconds > 0 ? Math.max(15, seconds) : 600;
}

function scheduleNextPoll() {
  if (pollingTimer) clearTimeout(pollingTimer);
  pollingTimer = null;
  nextTickAtMs = null;
  if (pollingEnabled) {
    const delayMs = getPollingSeconds() * 1000;
    nextTickAtMs = Date.now() + delayMs;
    pollingTimer = setTimeout(() => {
      pollingTimer = null;
      nextTickAtMs = null;
      load({ silent: true });
    }, delayMs);
  }
  setRefreshInfo();
}

function setRefreshInfo() {
  if (!nextRefresh) return;
  let nextText = "-";
  if (nextTickAtMs) {
    const diffSec = Math.ceil((nextTickAtMs - Date.now()) / 1000);
    nextText = (window.monitorUtils?.fmtMMSS || fmtMMSS)(diffSec);
  }
  nextRefresh.textContent = `Próxima: ${nextText}`;
}

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  setRefreshInfo();
  countdownTimer = setInterval(setRefreshInfo, 1000);
}

// ==========================================
// CONFIGURAÇÃO DO FIREBASE WEB SDK
// ==========================================
const firebaseConfig = {
  apiKey: "AIzaSyCbeHwFUdFNwlKgX1yiqqgRhlGdExiYTSQ",
  authDomain: "dds-treinamentos.firebaseapp.com",
  projectId: "dds-treinamentos"
};

let db = null;
if (typeof firebase !== 'undefined') {
  if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
  }
  db = firebase.firestore();
  window.db = db; // Expor globalmente para outros scripts (ex: requests.js)
} else {
  console.warn("Firebase SDK não está carregado. Usando fallback HTTP polling.");
}
let unsubMonitor = null;
let unsubActivityFeed = null;
// ==========================================

// Estado global unificado para team-form.js, messaging.js e requests.js
window.monitorState = {
  getConfig: () => cfg,
  getEmpresa: () => (window.monitorFilters?.getEmpresaValue?.() || empresaInput?.value || cfg?.defaultEmpresa || '').trim(),
  getViewMode: () => (window.monitorFilters?.getViewMode?.() || 'active'),
  findItem: (teamKey) => currentItems.find((item) => (window.monitorUtils?.detailValue?.(item.teamKey || item.equipe) === teamKey)) || null,
  reload: (options = {}) => load(options),
  getCurrentItems: () => [...currentItems],
  getCurrentSector: () => {
    const selector = document.getElementById('sectorSelector');
    return selector ? selector.value : (localStorage.getItem('dds_monitor_setor') || 'TODOS');
  },
};

function syncRealtimeData() {
  const mode = window.monitorFilters?.getViewMode?.() || 'active';
  if (mode === 'trash') return; // Lixeira usa fetch dedicado

  const isInactiveMode = mode === 'inactive';
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;

  // Estágio 1: Filtros de texto, equipe e ativo/inativo (usados para a contagem de KPIs)
  const baseFiltered = allRealtimeItems.filter(item => {
    const itemActive = item.active !== false;
    if (isInactiveMode && itemActive) return false;
    if (!isInactiveMode && !itemActive) return false;

    const q = sUpper(searchInput?.value);
    const selectedTeam = sUpper(teamSelect?.value);
    const eq = sUpper(item.equipe);
    const teamKey = sUpper(item.teamKey || item.equipe);

    const matchesText = !q || eq.includes(q) || teamKey.includes(q);
    const matchesTeam = !selectedTeam || teamKey === selectedTeam;

    return matchesText && matchesTeam;
  });

  // Estágio 2: Filtro de KPI (para determinar os cards exibidos)
  const activeKpi = window.monitorFilters?.getActiveKpiFilter?.() || "";
  const kpiFilter = window.monitorFilters?.normalizeKpiFilter?.(activeKpi);
  const normState = window.monitorCards?.normalizedState || normalizedState;
  const isAlertActive = window.monitorFilters?.activeAlertFilter || activeAlertFilter;

  const filtered = baseFiltered.filter(item => {
    const shown = normState(item.estado);
    const matchesKpi = !kpiFilter || (
      kpiFilter === "ALERTA" ? isAlertActive(item) :
        kpiFilter === "DDS_OK" ? item.ddsToday === "ok" :
          shown === kpiFilter
    );
    return matchesKpi;
  });

  currentItems = filtered;
  renderData(filtered, lastData || { empresa: window.monitorState.getEmpresa(), serverTime: new Date().toISOString() }, baseFiltered);
  window.monitorFeed?.refreshVisibleFeed?.();
}

function startPolling() {
  pollingEnabled = false;
  if (pollingTimer) clearTimeout(pollingTimer);
  pollingTimer = null;
  nextTickAtMs = null;
  if (countdownTimer) clearInterval(countdownTimer);
  if (alertTimer) clearInterval(alertTimer);

  if (typeof unsubMonitor === 'function') {
    try { unsubMonitor(); } catch (e) { console.warn("Erro ao desinscrever:", e); }
    unsubMonitor = null;
  }
  if (typeof unsubActivityFeed === 'function') {
    try { unsubActivityFeed(); } catch (e) { console.warn("Erro ao desinscrever activity feed:", e); }
    unsubActivityFeed = null;
  }

  // Verifica se o dia virou para resetar o cache (Lógica 00:00)
  triggerFullDailyReset();

  const empresa = window.monitorState.getEmpresa();
  const mode = window.monitorFilters?.getViewMode?.() || 'active';
  if (mode === 'trash') {
    load();
    return;
  }

  // A listagem do grid tem uma única fonte: as Torres de Controle via API.
  // O Firebase é consultado apenas pelos detalhes abertos a partir de um card.
  if (nextRefresh) nextRefresh.textContent = "Polling das Torres Ativo";
  pollingEnabled = true;
  scheduleNextPoll();

  countdownTimer = setInterval(() => {
    setRefreshInfo();
  }, 1000);

  alertTimer = setInterval(() => {
    recalculateLocalAlerts();
  }, 30000);
}

let uiSyncTimeout = null;
function requestUiSync() {
  if (uiSyncTimeout) return;
  uiSyncTimeout = setTimeout(() => {
    syncRealtimeData();
    uiSyncTimeout = null;
  }, 3000);
}

function recalculateLocalAlerts() {
  if (!allRealtimeItems.length || !cfg || !cfg.rules) return;
  const now = new Date();
  let changed = false;

  allRealtimeItems.forEach(item => {
    if (!item.updatedAt || item.estado === 'DESATUALIZADO') return;
    const updated = new Date(item.updatedAt);
    if (isNaN(updated.getTime())) return;

    const diffMins = Math.floor((now - updated) / 60000);
    let novoAlerta = "";

    if (diffMins >= cfg.rules.alertaPiscoMin) novoAlerta = "PULSE";
    else if (diffMins >= cfg.rules.alertaVermelhoMin) novoAlerta = "RED";
    else if (diffMins >= cfg.rules.alertaAmareloMin) novoAlerta = "YELLOW";

    if (item.alerta !== novoAlerta) {
      item.alerta = novoAlerta;
      changed = true;
    }
  });

  if (changed) {
    syncRealtimeData();
  }
}

async function loadConfig() {
  const r = await fetch('/api/config', { cache: 'no-store' });
  cfg = await r.json();
  if (!empresaInput.value) empresaInput.value = cfg.defaultEmpresa || '';
  pollingSeconds = Number(cfg.pollingSeconds) || 600;
  window.monitorConfig?.fillConfigForm?.(cfg);
}

async function loadDdsBackground(forceRefresh = false) {
  const empresa = window.monitorState.getEmpresa();
  const active = window.monitorFilters?.getActiveFilterValue?.() || 'all';
  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('active', active);
  if (forceRefresh) qs.set('refresh', 'manual');

  const sectorSelectorEl = document.getElementById('sectorSelector');
  const selectedSector = sectorSelectorEl ? sectorSelectorEl.value : (localStorage.getItem('dds_monitor_setor') || 'TODOS');
  if (selectedSector) qs.set('setor', selectedSector);

  try {
    const r = await fetch(`/api/turnos/dds?${qs.toString()}`, { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok || !Array.isArray(data.items)) return;

    const isNewer = window.monitorUtils?.isIsoNewer || isIsoNewer;
    let merged = false;
    data.items.forEach(ddsItem => {
      const idx = allRealtimeItems.findIndex(it => it.teamKey === ddsItem.teamKey);
      if (idx !== -1) {
        const current = allRealtimeItems[idx];
        const ddsContactIsNewer = isNewer(ddsItem.lastContact, current.lastContact);
        const ddsTurnIsNewer = isNewer(ddsItem.updatedAt, current.updatedAt);
        allRealtimeItems[idx] = {
          ...current,
          ddsHistory: ddsItem.ddsHistory,
          ddsDays: ddsItem.ddsDays,
          ddsTimes: ddsItem.ddsTimes,
          ddsToday: ddsItem.ddsToday,
          ...(ddsContactIsNewer ? {
            lastContact: ddsItem.lastContact,
            lastContactSource: ddsItem.lastContactSource || 'D',
          } : {}),
          ...(typeof ddsItem.active === 'boolean' ? { active: ddsItem.active } : {}),
          ...(ddsTurnIsNewer && ddsItem.estado ? { estado: ddsItem.estado } : {}),
          ...(ddsTurnIsNewer ? { updatedAt: ddsItem.updatedAt } : {}),
        };
        merged = true;
      }
    });

    ddsDataLoaded = true;
    if (merged) syncRealtimeData();
  } catch (e) {
    console.warn('Erro ao carregar DDS lazy:', e);
  }
}

async function load(options = {}) {
  if (pollingTimer) clearTimeout(pollingTimer);
  pollingTimer = null;
  nextTickAtMs = null;
  const forceRefresh = options.forceRefresh || false;
  const silent = options.silent === true;
  const refreshSpinner = document.getElementById('refreshSpinner');

  if (forceRefresh) {
    if (refreshBtn) refreshBtn.disabled = true;
    if (refreshSpinner) refreshSpinner.hidden = false;
  }

  const empresa = window.monitorState.getEmpresa();
  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('active', window.monitorFilters?.getActiveFilterValue?.() || 'all');

  const selectedSector = sectorSelector ? sectorSelector.value : (localStorage.getItem('dds_monitor_setor') || 'TODOS');
  if (selectedSector) qs.set('setor', selectedSector);

  if (forceRefresh) qs.set('refresh', 'manual');

  const mode = window.monitorFilters?.getViewMode?.() || 'active';
  let url = `/api/turnos?${qs.toString()}`;
  if (mode === 'trash') {
    url = `/api/teams/trash`;
  }

  if (!forceRefresh && !silent && !allRealtimeItems.length) {
    showSkeleton();
  }

  try {
    const r = await fetch(url, { cache: 'no-store' });
    const data = await r.json();

    if (mode === 'trash') {
      const teamsMap = data || {};
      const items = Object.values(teamsMap).map(t => ({
        ...t, equipe: t.displayName || t.teamKey, estado: 'DESCONHECIDO'
      }));
      renderData(items, { empresa: '-', serverTime: new Date().toISOString() });
      return;
    }

    allRealtimeItems = data.items || [];
    ddsDataLoaded = false;
    lastData = data;
    syncRealtimeData();

    loadDdsBackground();
    window.monitorFeed?.loadActivityFeed?.();
  } catch (e) {
    console.error('Erro ao carregar monitor:', e);
    if (lastSync) lastSync.textContent = 'Atualizado: ERRO';
    if (!silent || !allRealtimeItems.length) {
      if (grid) grid.innerHTML = '<div class="emptyState">Não foi possível carregar o monitor.</div>';
      if (kpis) kpis.innerHTML = `<div class="kpi">⚠ erro ao carregar</div>`;
      window.monitorFilters?.renderTeamCount?.([]);
    }
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
    if (refreshSpinner) refreshSpinner.hidden = true;

    scheduleNextPoll();
  }
}

function renderData(items, meta, kpiSourceItems) {
  if (skeletonGrid) skeletonGrid.classList.add('hidden');
  if (grid) grid.classList.remove('hidden');

  if (empresaLabel) empresaLabel.textContent = meta.empresa || '-';
  if (lastSync) lastSync.textContent = `Atualizado: ${(window.monitorUtils?.fmtTimeOnly || fmtTimeOnly)(meta.serverTime)}`;
  lastData = meta;

  const teamTypeOrder = {
    "cesto": 1,
    "stc_cesto": 1,
    "stc": 2,
    "ep": 3,
    "linha_viva": 4,
    "linha viva": 4,
    "lv": 4,
    "construcao": 5,
    "construção": 5,
    "rocada": 6,
    "roçada": 6
  };

  const sortedItems = [...(items || [])].sort((a, b) => {
    const typeA = (a.teamType || '').trim().toLowerCase();
    const typeB = (b.teamType || '').trim().toLowerCase();
    const orderA = teamTypeOrder[typeA] !== undefined ? teamTypeOrder[typeA] : 99;
    const orderB = teamTypeOrder[typeB] !== undefined ? teamTypeOrder[typeB] : 99;

    if (orderA !== orderB) {
      return orderA - orderB;
    }
    const nameA = (a.equipe || '').trim().toLowerCase();
    const nameB = (b.equipe || '').trim().toLowerCase();
    return nameA.localeCompare(nameB, 'pt-BR', { sensitivity: 'base' });
  });

  window.monitorFilters?.syncTeamSelect?.(sortedItems);
  currentItems = sortedItems;

  const mode = window.monitorFilters?.getViewMode?.() || 'active';
  if (mode !== 'trash') {
    window.monitorFilters?.renderKpis?.(kpiSourceItems || items);
    if (kpis) kpis.hidden = false;
  } else {
    if (kpis) kpis.hidden = true;
  }

  window.monitorFilters?.renderTeamCount?.(currentItems);

  if (!currentItems.length) {
    if (grid) grid.innerHTML = `<div class="emptyState">Nenhuma equipe encontrada nesta visualização.</div>`;
    return;
  }

  const container = grid;
  const existingIds = new Set();
  const tileFn = window.monitorCards?.tile || tile;
  const getSig = window.monitorCards?.getTeamUpdateSignature || getTeamUpdateSignature;
  const syncHover = window.monitorCards?.syncHoverPlacement || syncHoverPlacement;

  currentItems.forEach((item, index) => {
    const teamKey = item.teamKey || item.equipe;
    const cardId = `card-${teamKey.replace(/[^\w]/g, '_')}`;
    existingIds.add(cardId);

    let card = document.getElementById(cardId);
    const html = tileFn(item);
    const coreData = getSig(item);

    if (!card) {
      const temp = document.createElement('div');
      temp.innerHTML = html;
      card = temp.firstElementChild;
      card.id = cardId;
      card.dataset.core = coreData;
      card.style.order = index;
      card.addEventListener('mouseenter', () => syncHover(card));
      container.appendChild(card);
    } else {
      const hasChanged = card.dataset.core !== coreData;
      if (hasChanged) {
        const temp = document.createElement('div');
        temp.innerHTML = html;
        const newCard = temp.firstElementChild;
        if (newCard) {
          newCard.id = cardId;
          newCard.dataset.core = coreData;
          newCard.style.order = index;
          newCard.classList.add('flash-update');
          newCard.addEventListener('animationend', () => newCard.classList.remove('flash-update'), { once: true });
          newCard.addEventListener('mouseenter', () => syncHover(newCard));
          card.replaceWith(newCard);
        }
      } else {
        card.style.order = index;
      }
    }
  });

  Array.from(container.children).forEach(child => {
    if (child.id && child.id.startsWith('card-') && !existingIds.has(child.id)) {
      container.removeChild(child);
    }
  });

  if (window.teamForm?.refreshOpenTeam) {
    const openTeamKey = window.teamForm.getOpenTeamKey?.();
    if (openTeamKey) window.teamForm.refreshOpenTeam(window.monitorState.findItem(openTeamKey));
  }

  const globalMessagesBadge = document.getElementById('globalMessagesBadge');
  if (globalMessagesBadge) {
    const currentSector = (sectorSelector?.value || 'TODOS').toUpperCase();
    const totalUnread = items.reduce((acc, it) => {
      const unreadMap = it.unreadMap || {};
      if (currentSector === 'TODOS') {
        return acc + Object.values(unreadMap).reduce((a, b) => a + b, 0);
      }
      return acc + (Number(unreadMap[currentSector]) || 0);
    }, 0);
    globalMessagesBadge.textContent = totalUnread;
    globalMessagesBadge.hidden = totalUnread === 0;
  }
}

// Ações de gerenciamento de equipe (Lixeira, Restauração, Ativação)
window.restoreTeam = async function (teamKey) {
  if (!confirm(`Deseja restaurar a equipe ${teamKey}?`)) return;
  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/trash`, { method: 'DELETE' });
    if (r.ok) await load();
    else alert('Erro ao restaurar equipe.');
  } catch (e) {
    console.error(e);
  }
};

window.deleteTeamPermanent = async function (teamKey) {
  if (!confirm(`ATENÇÃO: Deseja excluir PERMANENTEMENTE a equipe ${teamKey} e TODO o histórico dela? Esta ação não pode ser desfeita.`)) return;
  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/permanent`, { method: 'DELETE' });
    const data = await r.json();
    if (r.ok) {
      if (data.logs && data.logs.length > 0) {
        alert("Resultado da Faxina:\n\n" + data.logs.join("\n"));
      }
      await load();
    } else {
      alert('Erro ao excluir equipe: ' + (data.message || ''));
    }
  } catch (e) {
    console.error(e);
    alert('Erro de comunicação com o servidor.');
  }
};

window.toggleTeamActive = async function (teamKey, active) {
  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/active?active=${active}`, { method: 'PATCH' });
    if (r.ok) await load();
    else {
      const data = await r.json();
      alert(data?.message || 'Erro ao alterar estado da equipe.');
    }
  } catch (e) {
    console.error(e);
  }
};

let pendingTrashTeamKey = null;
window.openTrashConfirmation = async function (teamKey) {
  pendingTrashTeamKey = teamKey;
  const modal = document.getElementById('trashConfirmModal');
  const backdrop = document.getElementById('trashConfirmModalBackdrop');

  document.getElementById('trashTeamName').textContent = teamKey;
  document.getElementById('trashMembersCount').textContent = '...';
  document.getElementById('trashDdsCount').textContent = '...';
  document.getElementById('trashHistoryCount').textContent = '...';

  modal.hidden = false;
  backdrop.hidden = false;
  document.body.classList.add('modalOpen');

  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/trash-preview`);
    const data = await r.json();
    document.getElementById('trashTeamName').textContent = data.displayName || teamKey;
    document.getElementById('trashMembersCount').textContent = data.membersCount || 0;
    document.getElementById('trashDdsCount').textContent = data.ddsCount || 0;
    document.getElementById('trashHistoryCount').textContent = data.equipmentHistoryCount || 0;
  } catch (e) {
    console.error('Erro ao carregar preview da lixeira:', e);
  }
};

function closeTrashConfirmation() {
  const modal = document.getElementById('trashConfirmModal');
  const backdrop = document.getElementById('trashConfirmModalBackdrop');
  if (modal) modal.hidden = true;
  if (backdrop) backdrop.hidden = true;
  if (document.getElementById('configModal')?.hidden && document.getElementById('teamFormModal')?.hidden) {
    document.body.classList.remove('modalOpen');
  }
  pendingTrashTeamKey = null;
}

document.getElementById('trashConfirmClose')?.addEventListener('click', closeTrashConfirmation);
document.getElementById('trashConfirmCancel')?.addEventListener('click', closeTrashConfirmation);
document.getElementById('trashConfirmModalBackdrop')?.addEventListener('click', closeTrashConfirmation);
document.getElementById('trashConfirmExecute')?.addEventListener('click', async () => {
  if (!pendingTrashTeamKey) return;
  const btn = document.getElementById('trashConfirmExecute');
  btn.disabled = true;
  btn.textContent = 'Movendo...';

  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(pendingTrashTeamKey)}/trash`, { method: 'POST' });
    if (r.ok) {
      closeTrashConfirmation();
      window.teamForm?.closeTeamForm?.();
      await load();
    } else {
      const data = await r.json();
      alert(data?.message || 'Erro ao mover para a lixeira.');
    }
  } catch (e) {
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sim, mover para lixeira';
  }
});

// Handlers de UI e eventos de filtro
refreshBtn?.addEventListener('click', async () => { await load({ forceRefresh: true }); startPolling(); });
configBtn?.addEventListener('click', () => window.monitorConfig?.openConfigModal?.(cfg));
document.getElementById("configModalClose")?.addEventListener('click', () => window.monitorConfig?.closeConfigModal?.());
document.getElementById("configModalCancel")?.addEventListener('click', () => window.monitorConfig?.closeConfigModal?.());
document.getElementById("configModalBackdrop")?.addEventListener('click', () => window.monitorConfig?.closeConfigModal?.());
document.getElementById("configModalSave")?.addEventListener('click', () => {
  window.monitorConfig?.saveConfigModal?.(async (updatedCfg) => {
    cfg = updatedCfg;
    pollingSeconds = Number(cfg.pollingSeconds) || 600;
    await load();
    startPolling();
  });
});

const ddsToggle = document.getElementById("ddsToggle");
const savedDdsState = localStorage.getItem('monitor_show_dds') === 'true';
if (ddsToggle) {
  ddsToggle.checked = savedDdsState;
  ddsToggle.addEventListener('change', () => {
    localStorage.setItem('monitor_show_dds', ddsToggle.checked);
    syncRealtimeData();
    if (ddsToggle.checked && !ddsDataLoaded) {
      loadDdsBackground();
    }
  });
}

searchInput?.addEventListener('input', () => syncRealtimeData());
teamSelect?.addEventListener('change', () => syncRealtimeData());

grid?.addEventListener('click', (event) => {
  if (event.target.closest('a, button, input, select, textarea')) return;
  const tileEl = event.target.closest('.tile');
  const mode = window.monitorFilters?.getViewMode?.() || 'active';
  if (!tileEl || mode === 'trash') return;
  window.teamForm?.openTeamForm?.(tileEl.dataset.team || '');
});

grid?.addEventListener('keydown', (event) => {
  const tileEl = event.target.closest('.tile');
  if (!tileEl) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    const mode = window.monitorFilters?.getViewMode?.() || 'active';
    if (mode === 'trash') return;
    window.teamForm?.openTeamForm?.(tileEl.dataset.team || '');
  }
});

kpis?.addEventListener('click', (event) => {
  const chip = event.target.closest('.kpi');
  if (!chip) return;
  const nextFilter = window.monitorFilters?.normalizeKpiFilter?.(chip.dataset.filter || chip.dataset.kpi);
  const currentActive = window.monitorFilters?.getActiveKpiFilter?.() || "";
  const sameFilter = window.monitorFilters?.normalizeKpiFilter?.(currentActive) === nextFilter;

  window.monitorFilters?.setActiveKpiFilter?.(sameFilter ? "" : nextFilter);
  window.monitorFilters?.syncKpiSelection?.();

  showSkeleton();
  setTimeout(() => {
    syncRealtimeData();
  }, 150);

  event.stopPropagation();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  window.teamForm?.closeTeamForm?.();
  window.monitorConfig?.closeConfigModal?.();
});

window.addEventListener('resize', () => {
  requestAnimationFrame(() => {
    document.querySelectorAll('.tile').forEach(t => window.monitorCards?.syncHoverPlacement?.(t));
  });
});

if (sectorSelector) {
  sectorSelector.value = localStorage.getItem('dds_monitor_setor') || 'TODOS';
  sectorSelector.addEventListener('change', () => {
    localStorage.setItem('dds_monitor_setor', sectorSelector.value);
    syncRealtimeData();
  });
}

// Navegação SPA e virada de dia
function initNavigation() {
  window.monitorConfig?.loadCrashReports?.();

  document.querySelectorAll('.viewTab').forEach(tab => {
    if (tab.id === 'requestsTab') return;

    tab.addEventListener('click', async (e) => {
      try {
        const href = tab.getAttribute('href') || '';
        const newMode = href.includes('inativas') ? 'inactive' :
          href.includes('lixeira') ? 'trash' : 'active';
        const oldMode = window.monitorFilters?.getViewMode?.() || 'active';

        if (newMode === oldMode) return;

        e.preventDefault();
        history.pushState({ mode: newMode }, '', tab.href);

        document.body.setAttribute('data-team-view', newMode);
        document.querySelectorAll('.viewTab').forEach(t => t.classList.remove('isActive'));
        tab.classList.add('isActive');

        const pageTitle = document.querySelector('.h1');
        if (pageTitle) {
          pageTitle.textContent = newMode === 'inactive' ? 'Equipes Inativas' :
            newMode === 'trash' ? 'Lixeira de Equipes' : 'Monitor de Turnos';
        }

        showSkeleton();

        if (newMode !== 'trash' && oldMode !== 'trash' && typeof unsubMonitor === 'function' && allRealtimeItems.length > 0) {
          syncRealtimeData();
        } else {
          startPolling();
        }
      } catch (err) {
        console.error("Erro na navegação dinâmica:", err);
        window.location.href = tab.href;
      }
    });
  });

  window.addEventListener('popstate', (e) => {
    const mode = e.state?.mode || 'active';
    document.body.dataset.teamView = mode;
    syncRealtimeData();
  });
}

function triggerFullDailyReset() {
  const lastReset = localStorage.getItem('dds_monitor_last_reset_day');
  const today = new Date().toISOString().split('T')[0];

  if (lastReset && lastReset !== today) {
    console.log("[DailyReset] Virada de dia detectada. Forçando recriação do cache.");
    load({ forceRefresh: true });
  }
  localStorage.setItem('dds_monitor_last_reset_day', today);
}

window.addEventListener("keydown", (event) => {
  if (event.key === "F5" || event.keyCode === 116) {
    event.preventDefault();
    load({ forceRefresh: true });
    startPolling();
  }
});

// Inicialização da aplicação
(async () => {
  try {
    await loadConfig();
  } catch (error) {
    console.error('Erro ao carregar configuração do monitor:', error);
    cfg = cfg || { defaultEmpresa: empresaInput?.value || '', pollingSeconds, rules: {} };
  }
  initNavigation();

  const isPageReload = (() => {
    try {
      const nav = performance.getEntriesByType('navigation')[0];
      if (nav && nav.type === 'reload') return true;
      if (window.performance && window.performance.navigation && window.performance.navigation.type === 1) return true;
    } catch (_) {}
    return false;
  })();

  await load({ forceRefresh: isPageReload });
  startPolling();
})();
