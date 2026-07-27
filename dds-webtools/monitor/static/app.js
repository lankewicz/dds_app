// -----------------------------------------------------------------------------
// Arquivo : static/app.js
// Objetivo: Renderizar o grid do monitor, aplicar filtros/polling, separar a
//           visualização entre equipes ativas/inativas e delegar a abertura do
//           formulário de equipe ao modal específico.
// -----------------------------------------------------------------------------

const grid = document.getElementById("grid");
const empresaLabel = document.getElementById("empresaLabel");
const lastSync = document.getElementById("lastSync");
const nextRefresh = document.getElementById("nextRefresh");
const teamCount = document.getElementById("teamCount");
const skeletonGrid = document.getElementById("skeletonGrid");

function showSkeleton() {
  if (skeletonGrid) skeletonGrid.classList.remove('hidden');
  if (grid) {
    grid.classList.add('hidden');
    grid.innerHTML = '';
  }
}

const empresaInput = document.getElementById("empresaInput");
const searchInput = document.getElementById("searchInput");
const teamSelect = document.getElementById("teamSelect");
const kpis = document.getElementById("kpis");
const refreshBtn = document.getElementById("refreshBtn");
const configBtn = document.getElementById("configBtn");
const configModal = document.getElementById("configModal");
const configModalBackdrop = document.getElementById("configModalBackdrop");
const configModalClose = document.getElementById("configModalClose");
const configModalCancel = document.getElementById("configModalCancel");
const configModalSave = document.getElementById("configModalSave");
const configModalMeta = document.getElementById("configModalMeta");
const configNotice = document.getElementById("configNotice");
const configSummary = document.getElementById("configSummary");
const cfgAlertaAmareloMin = document.getElementById("cfgAlertaAmareloMin");
const cfgAlertaVermelhoMin = document.getElementById("cfgAlertaVermelhoMin");
const cfgAlertaPiscoMin = document.getElementById("cfgAlertaPiscoMin");
const cfgFechadoViraDesatualizadoHoras = document.getElementById("cfgFechadoViraDesatualizadoHoras");
const cfgDesatualizadoCriticoHoras = document.getElementById("cfgDesatualizadoCriticoHoras");
const cfgAutoCloseOpenHours = document.getElementById("cfgAutoCloseOpenHours");
const cfgAutoInactivateHours = document.getElementById("cfgAutoInactivateHours");
const cfgPollingSeconds = document.getElementById("cfgPollingSeconds");
const activityFeedPanel = document.getElementById("activityFeedPanel");
const activityFeedList = document.getElementById("activityFeedList");


let cfg = null;
let pollingSeconds = 600;
let pollingTimer = null;
let countdownTimer = null;
let nextTickAtMs = null;
let currentItems = [];
let allRealtimeItems = []; // Guarda todos os items do onSnapshot
let activeKpiFilter = "";
let configSaveInFlight = false;

let lastData = null;
let ddsDataLoaded = false; // Flag: DDS lazy-load já foi executado para o ciclo atual

// ==========================================
// CONFIGURAÇÃO DO FIREBASE WEB SDK
// ==========================================
// IMPORTANTE: Insira sua apiKey real aqui para o onSnapshot funcionar
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

function safeUpper(v) { return (v || "").toString().trim().toUpperCase(); }
function escapeHtml(value) { return (value ?? "").toString().replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;"); }
function fmtDateTime(iso) {
  if (!iso) return "-"; const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-"; return d.toLocaleString("pt-BR");
}
function fmtTimeOnly(iso) {
  if (!iso) return "-"; const d = new Date(iso); if (Number.isNaN(d.getTime())) return "-"; return d.toLocaleTimeString("pt-BR");
}
function fmtLastContact(iso, source) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const time = d.toLocaleTimeString("pt-BR", { hour: '2-digit', minute: '2-digit' });
  const srcSuffix = source ? ` (${source})` : "";
  return `${day}/${month} - ${time}${srcSuffix}`;
}

function isIsoNewer(candidateIso, currentIso) {
  if (!candidateIso) return false;
  const candidate = new Date(candidateIso);
  if (Number.isNaN(candidate.getTime())) return false;
  if (!currentIso) return true;
  const current = new Date(currentIso);
  if (Number.isNaN(current.getTime())) return true;
  return candidate.getTime() > current.getTime();
}

const getLocalFeedCacheKey = (empresa) => `dds_activity_feed_local_cache_${empresa || 'default'}`;

function getLocalFeedCache(empresa) {
  try {
    const raw = localStorage.getItem(getLocalFeedCacheKey(empresa));
    return raw ? JSON.parse(raw) : [];
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

function mergeActivityFeedItems(localItems, newItems) {
  const mergedMap = new Map();
  const getUniqueKey = (item) => {
    if (item.eventId) return item.eventId;
    const timeKey = item.activityAt || item.time || '';
    const team = item.teamKey || item.equipe || '';
    const label = item.label || item.source || '';
    return `${timeKey}_${team}_${label}`;
  };

  (localItems || []).forEach(item => {
    const key = getUniqueKey(item);
    if (key) mergedMap.set(key, item);
  });

  (newItems || []).forEach(item => {
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

  return mergedList.slice(0, 30);
}

function renderActivityFeed(items = []) {
  if (!activityFeedPanel || !activityFeedList) return;
  const visible = items.slice(0, 30);
  if (!visible.length) {
    activityFeedList.innerHTML = '<div class="activityFeedEmpty">Sem atividades recentes</div>';
    return;
  }
  activityFeedList.innerHTML = visible.map((item) => {
    const time = escapeHtml(item.time || fmtHourMinute(item.activityAt));
    const team = escapeHtml(item.teamKey || item.equipe || '-');
    const label = escapeHtml(item.label || item.source || 'Atividade');
    const source = escapeHtml(item.source || '');
    return `<div class="activityFeedItem" data-source="${source}"><span class="activityFeedTime">${time}</span><span class="activityFeedTeam">${team}</span><span class="activityFeedLabel">${label}</span></div>`;
  }).join('');
}

async function loadActivityFeed() {
  if (!activityFeedPanel || getViewMode() === 'trash') return;
  const empresa = getEmpresaValue();

  const initialCached = getLocalFeedCache(empresa);
  if (initialCached.length > 0) {
    renderActivityFeed(initialCached);
  }

  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('limit', '5');
  try {
    const r = await fetch(`/api/activity-feed?${qs.toString()}`, { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok || !Array.isArray(data.items)) {
      if (initialCached.length === 0) {
        renderActivityFeed([]);
      }
      return;
    }
    const updatedCache = mergeActivityFeedItems(initialCached, data.items);
    saveLocalFeedCache(empresa, updatedCache);
    renderActivityFeed(updatedCache);
  } catch (error) {
    console.warn('Erro ao carregar feed de atividades:', error);
    if (initialCached.length === 0) {
      renderActivityFeed([]);
    }
  }
}

function addHours(dateLike, hours) {
  if (!dateLike) return null;
  const dt = dateLike instanceof Date ? new Date(dateLike.getTime()) : new Date(dateLike);
  if (Number.isNaN(dt.getTime())) return null;
  dt.setHours(dt.getHours() + hours);
  return dt;
}

function getArt66EndAt(item, shown) {
  if (normalizedState(shown) !== "FECHADO" || !item?.updatedAt) return null;
  const hours = item.lastWasDescansoSemanal ? 24 : 11;
  return addHours(item.updatedAt, hours);
}

function isArt66Active(item, shown) {
  const endAt = getArt66EndAt(item, shown);
  if (!endAt) return false;
  return endAt.getTime() > Date.now();
}

function fmtHourMinute(dateLike) {
  if (!dateLike) return "-";
  const dt = dateLike instanceof Date ? dateLike : new Date(dateLike);
  if (Number.isNaN(dt.getTime())) return "-";
  return dt.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtMMSS(totalSeconds) { const s = Math.max(0, Math.floor(totalSeconds)); const mm = String(Math.floor(s / 60)).padStart(2, "0"); const ss = String(s % 60).padStart(2, "0"); return `${mm}:${ss}`; }
function fmtAgeFromMinutes(mins) { if (!Number.isFinite(mins) || mins < 0) return "-"; if (mins < 60) return `${mins} min`; const hours = Math.floor(mins / 60); const remMin = mins % 60; if (hours < 24) return `${hours}h ${String(remMin).padStart(2, "0")}m`; const days = Math.floor(hours / 24); const remHours = hours % 24; return `${days}d ${remHours}h`; }


function setRefreshInfo() {
  if (!nextRefresh) return;
  let nextText = "-";
  if (nextTickAtMs) {
    const diffSec = Math.ceil((nextTickAtMs - Date.now()) / 1000);
    nextText = fmtMMSS(diffSec);
  }
  nextRefresh.textContent = `Próxima: ${nextText}`;
}
function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer); setRefreshInfo(); countdownTimer = setInterval(setRefreshInfo, 1000);
}

function setConfigModalHidden(hidden) {
  if (!configModal) return;
  configModal.hidden = hidden;
  document.body.classList.toggle('modalOpen', !hidden || !document.getElementById('teamFormModal')?.hidden);
}

function setConfigNotice(message = '', type = '') {
  if (!configNotice) return;
  const text = (message || '').trim();
  configNotice.hidden = !text;
  configNotice.textContent = text;
  configNotice.className = 'formNotice';
  if (type) configNotice.classList.add(type);
}

function formatMinToHoursText(min) {
  if (!min || min <= 0) return '-';
  const hrs = (min / 60).toFixed(1).replace('.0', '');
  return `⏱️ aprox. ${hrs} hora(s)`;
}

let isAlertUnitHours = false;

function toggleAlertUnit(useHours) {
  isAlertUnitHours = useHours;
  const labels = [
    document.getElementById("unitLabelAmarelo"),
    document.getElementById("unitLabelVermelho"),
    document.getElementById("unitLabelPisco")
  ];
  labels.forEach(lbl => {
    if (lbl) lbl.textContent = useHours ? 'h' : 'min';
  });

  const inputs = [cfgAlertaAmareloMin, cfgAlertaVermelhoMin, cfgAlertaPiscoMin];
  inputs.forEach(inp => {
    if (inp && inp.value !== '') {
      let val = parseFloat(inp.value);
      if (!isNaN(val)) {
        if (useHours) {
          inp.value = (val / 60).toFixed(1).replace('.0', '');
        } else {
          inp.value = Math.round(val * 60);
        }
      }
    }
  });
  syncConfigSummary();
}

function fillConfigForm(config) {
  const rules = config?.rules || {};
  const isHours = Boolean(cfgAlertUnitHoursToggle && cfgAlertUnitHoursToggle.checked);
  
  if (cfgAlertaAmareloMin) {
    const minVal = rules.alertaAmareloMin ?? '';
    cfgAlertaAmareloMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }
  if (cfgAlertaVermelhoMin) {
    const minVal = rules.alertaVermelhoMin ?? '';
    cfgAlertaVermelhoMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }
  if (cfgAlertaPiscoMin) {
    const minVal = rules.alertaPiscoMin ?? '';
    cfgAlertaPiscoMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }

  if (cfgAutoCloseOpenHours) cfgAutoCloseOpenHours.value = rules.autoCloseOpenHours ?? '';
  if (cfgFechadoViraDesatualizadoHoras) {
    cfgFechadoViraDesatualizadoHoras.value = rules.autoDesatualizaFechadoHours ?? rules.fechadoViraDesatualizadoHoras ?? '';
  }
  if (cfgDesatualizadoCriticoHoras) cfgDesatualizadoCriticoHoras.value = rules.desatualizadoCriticoHoras ?? '';
  if (cfgAutoInactivateHours) cfgAutoInactivateHours.value = rules.autoInactivateHours ?? '';
  if (cfgPollingSeconds) cfgPollingSeconds.value = config?.pollingSeconds ?? '';
  syncConfigSummary();
}

function collectConfigPayload() {
  const isHours = Boolean(cfgAlertUnitHoursToggle && cfgAlertUnitHoursToggle.checked);
  
  const parseAlertMin = (inp) => {
    let val = parseFloat(inp?.value || 0);
    if (isNaN(val)) return 0;
    return isHours ? Math.round(val * 60) : Math.round(val);
  };

  return {
    pollingSeconds: Number(cfgPollingSeconds?.value || 0),
    rules: {
      alertaAmareloMin: parseAlertMin(cfgAlertaAmareloMin),
      alertaVermelhoMin: parseAlertMin(cfgAlertaVermelhoMin),
      alertaPiscoMin: parseAlertMin(cfgAlertaPiscoMin),
      autoCloseOpenHours: Number(cfgAutoCloseOpenHours?.value || 0),
      autoDesatualizaFechadoHours: Number(cfgFechadoViraDesatualizadoHoras?.value || 0),
      desatualizadoCriticoHoras: Number(cfgDesatualizadoCriticoHoras?.value || 0),
      autoInactivateHours: Number(cfgAutoInactivateHours?.value || 0),
    },
  };
}

function syncConfigSummary() {
  const payload = collectConfigPayload();
  const rules = payload.rules || {};
  
  const hintAmarelo = document.getElementById("hintAlertaAmarelo");
  const hintVermelho = document.getElementById("hintAlertaVermelho");
  const hintPisco = document.getElementById("hintAlertaPisco");
  
  const minAmarelo = rules.alertaAmareloMin || 0;
  const minVermelho = rules.alertaVermelhoMin || 0;
  const minPisco = rules.alertaPiscoMin || 0;
  
  const totalVermelho = (minVermelho > minAmarelo) ? minVermelho : (minAmarelo + minVermelho);
  const totalPisco = (minPisco > totalVermelho) ? minPisco : (totalVermelho + minPisco);

  if (hintAmarelo) hintAmarelo.textContent = `⏱️ ${(minAmarelo/60).toFixed(1).replace('.0','')}h sem contato`;
  if (hintVermelho) hintVermelho.textContent = `⏱️ ${(totalVermelho/60).toFixed(1).replace('.0','')}h acumulado`;
  if (hintPisco) hintPisco.textContent = `⏱️ ${(totalPisco/60).toFixed(1).replace('.0','')}h acumulado`;

  const hOpen = rules.autoCloseOpenHours || 0;
  const hClosed = rules.autoDesatualizaFechadoHours || rules.fechadoViraDesatualizadoHoras || 0;
  const hCrit = rules.desatualizadoCriticoHoras || 0;
  const hInact = rules.autoInactivateHours || 0;
  
  const acc1 = hOpen;
  const acc2 = hOpen + hClosed;
  const acc3 = acc2 + hCrit;
  const acc4 = acc3 + hInact;

  const accStep1 = document.getElementById("accStep1");
  const accStep2 = document.getElementById("accStep2");
  const accStep3 = document.getElementById("accStep3");
  const accStep4 = document.getElementById("accStep4");

  if (accStep1) accStep1.textContent = `Acumulado: ${acc1}h`;
  if (accStep2) accStep2.textContent = `Acumulado: ${acc2}h (${(acc2/24).toFixed(1).replace('.0','')}d)`;
  if (accStep3) accStep3.textContent = `Acumulado: ${acc3}h (${(acc3/24).toFixed(1).replace('.0','')}d)`;
  if (accStep4) accStep4.textContent = `Tolerância Total: ${acc4}h (~${(acc4/24).toFixed(1).replace('.0','')} dias)`;
}

function attachConfigInputListeners() {
  const inputs = [
    cfgAlertaAmareloMin, cfgAlertaVermelhoMin, cfgAlertaPiscoMin,
    cfgAutoCloseOpenHours, cfgFechadoViraDesatualizadoHoras,
    cfgDesatualizadoCriticoHoras, cfgAutoInactivateHours, cfgPollingSeconds
  ];
  inputs.forEach(inp => {
    if (inp && !inp.dataset.listenerAttached) {
      inp.dataset.listenerAttached = 'true';
      inp.addEventListener('input', syncConfigSummary);
    }
  });

  const toggleSwitch = document.getElementById("cfgAlertUnitHoursToggle");
  if (toggleSwitch && !toggleSwitch.dataset.listenerAttached) {
    toggleSwitch.dataset.listenerAttached = 'true';
    toggleSwitch.addEventListener('change', (e) => {
      toggleAlertUnit(e.target.checked);
    });
  }
}

function openConfigModal() {
  fillConfigForm(cfg || {});
  attachConfigInputListeners();
  attachCrashReportListeners();
  setConfigNotice('');
  loadCrashReports();

  if (configModalMeta) configModalMeta.textContent = 'Edite os tempos e confirme para aplicar.';
  setConfigModalHidden(false);
}

function attachCrashReportListeners() {
  const btnRefresh = document.getElementById("btnRefreshCrashReports");
  if (btnRefresh && !btnRefresh.dataset.listenerAttached) {
    btnRefresh.dataset.listenerAttached = 'true';
    btnRefresh.addEventListener("click", loadCrashReports);
  }
  const btnClear = document.getElementById("btnClearCrashReports");
  if (btnClear && !btnClear.dataset.listenerAttached) {
    btnClear.dataset.listenerAttached = 'true';
    btnClear.addEventListener("click", clearAllCrashReports);
  }
}

async function loadCrashReports() {
  const container = document.getElementById("crashReportsContainer");
  const badge = document.getElementById("crashConfigBadge");
  const btnRefresh = document.getElementById("btnRefreshCrashReports");

  if (btnRefresh) btnRefresh.disabled = true;

  try {
    const res = await fetch("/api/crash-reports");
    if (!res.ok) throw new Error("Falha ao carregar relatórios");
    const data = await res.json();
    const reports = data.reports || [];

    if (badge) {
      if (reports.length > 0) {
        badge.textContent = reports.length;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }

    if (!container) return;

    if (reports.length === 0) {
      container.innerHTML = `<div class="crashReportsEmpty">✅ Nenhum relatório de erro/fechamento anormal registrado até o momento.</div>`;
      return;
    }

    container.innerHTML = reports.map(r => {
      const errName = (r.exceptionType || "Exception").split('.').pop();
      const deviceStr = r.device ? `${r.device} (Android ${r.androidVersion || '?'})` : "Dispositivo Desconhecido";
      const appVerStr = r.appVersion ? `v${r.appVersion}` : "";
      
      return `
        <div class="crashCard" data-id="${r.id}">
          <div class="crashCardHeader">
            <div class="crashCardMeta">
              <span>📅 ${r.timestamp || '-'}</span>
              <span class="crashBadgeDevice">📱 ${deviceStr}</span>
              ${appVerStr ? `<span class="crashBadgeDevice">${appVerStr}</span>` : ''}
            </div>
            <span class="crashBadgeError">❌ ${errName}</span>
          </div>
          <div class="crashCardMessage">💬 ${r.message || 'Sem mensagem detalhada'}</div>
          
          <details class="crashCardDetails">
            <summary>🔍 Ver Pilha de Chamadas (Stacktrace)</summary>
            <pre class="crashStackTraceBox"><code>${r.stackTrace || 'Sem stacktrace'}</code></pre>
          </details>

          <div class="crashCardActions">
            <button type="button" class="btnSecondary" style="font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; background: rgba(255,255,255,0.08); color: #fff; border: none; cursor: pointer;" onclick="copyCrashStackTrace('${r.id}')">
              📋 Copiar Stacktrace
            </button>
            <button type="button" class="btnDanger" style="font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.3); cursor: pointer;" onclick="deleteCrashReport('${r.id}')">
              🗑️ Excluir
            </button>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error("Erro ao carregar crash reports:", err);
    if (container) container.innerHTML = `<div class="crashReportsEmpty" style="color: #f87171;">⚠️ Erro ao carregar relatórios do servidor.</div>`;
  } finally {
    if (btnRefresh) btnRefresh.disabled = false;
  }
}

window.copyCrashStackTrace = function(reportId) {
  const card = document.querySelector(`.crashCard[data-id="${reportId}"]`);
  if (!card) return;
  const code = card.querySelector(".crashStackTraceBox")?.textContent || "";
  navigator.clipboard.writeText(code).then(() => {
    alert("Stacktrace copiado para a área de transferência!");
  }).catch(() => {
    alert("Não foi possível copiar o texto.");
  });
};

window.deleteCrashReport = async function(reportId) {
  if (!confirm("Deseja realmente excluir este relatório de erro?")) return;
  try {
    const res = await fetch(`/api/crash-reports/${reportId}`, { method: 'DELETE' });
    if (res.ok) {
      loadCrashReports();
    } else {
      alert("Falha ao excluir o relatório.");
    }
  } catch (err) {
    alert("Erro de conexão ao excluir o relatório.");
  }
};

async function clearAllCrashReports() {
  if (!confirm("Deseja realmente limpar TODOS os relatórios de erros do servidor? Essa ação não pode ser desfeita.")) return;
  try {
    const res = await fetch("/api/crash-reports", { method: 'DELETE' });
    if (res.ok) {
      loadCrashReports();
    } else {
      alert("Falha ao limpar relatórios.");
    }
  } catch (err) {
    alert("Erro ao conectar com o servidor.");
  }
}

function closeConfigModal() {
  if (configSaveInFlight) return;
  setConfigModalHidden(true);
  setConfigNotice('');
}

async function saveConfigModal() {
  if (configSaveInFlight) return;
  const payload = collectConfigPayload();
  configSaveInFlight = true;
  if (configModalMeta) configModalMeta.textContent = 'Salvando configurações...';
  setConfigNotice('');

  try {
    const response = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || 'Falha ao salvar as configurações.');
    cfg = {
      defaultEmpresa: data.defaultEmpresa || cfg?.defaultEmpresa || '',
      pollingSeconds: data.pollingSeconds,
      rules: data.rules || {},
    };
    pollingSeconds = Number(cfg.pollingSeconds) || 600;
    setConfigNotice(data?.message || 'Configurações salvas com sucesso.', 'success');
    if (configModalMeta) configModalMeta.textContent = 'Configurações salvas com sucesso.';
    await load();
    startPolling();
    setTimeout(() => {
      closeConfigModal();
    }, 600);
  } catch (error) {
    setConfigNotice(error?.message || 'Não foi possível salvar as configurações.', 'error');
    if (configModalMeta) configModalMeta.textContent = 'Falha ao salvar';
  } finally {
    configSaveInFlight = false;
  }
}


function normalizedState(state) {
  const raw = safeUpper(state);
  if (raw === "ESPECIAL" || raw === "DESLOCAMENTO") return "DESLOCAMENTO_ESPECIAL"; return raw;
}
function stateLabel(state) { switch (normalizedState(state)) { case "DESLOCAMENTO_ESPECIAL": return "DESLOCAMENTO ESPECIAL"; default: return normalizedState(state); } }
function vehicleFrameClass(state) { switch (normalizedState(state)) { case "ABERTO": return "vfGreen"; case "INTERVALO": return "vfYellow"; case "DESLOCAMENTO_ESPECIAL": return "vfBlue"; case "FECHADO": return "vfRed"; case "DESATUALIZADO": return "vfGray"; default: return "vfGray"; } }
function stateCardClass(state) {
  switch (normalizedState(state)) {
    case "ABERTO": return "tileStateOpen";
    case "INTERVALO": return "tileStateInterval";
    case "DESLOCAMENTO_ESPECIAL": return "tileStateSpecial";
    case "FECHADO": return "tileStateClosed";
    case "DESATUALIZADO": return "tileStateStale";
    default: return "tileStateUnknown";
  }
}
function borderClass(alerta) { switch (safeUpper(alerta)) { case "YELLOW": return "tileBorderYellow"; case "RED": return "tileBorderRed"; case "PULSE": return "tileBorderPulse"; default: return ""; } }
function participantsHtml(list, motorista, coringas, extraClass = "") {
  const names = Array.isArray(list) ? list.filter(Boolean) : [];
  const cls = ["participantsList", extraClass].filter(Boolean).join(" ");
  if (!names.length) return `<div class="popoverEmpty">Nenhum participante informado</div>`;
  
  const normMotorista = (motorista || "").trim().toUpperCase();
  const normCoringas = Array.isArray(coringas) ? coringas.map(c => (c || "").trim().toUpperCase()) : [];

  return `<ul class="${cls}">${names.map((name) => {
    const normName = name.trim().toUpperCase();
    const isDriver = normName === normMotorista;
    const isCoringa = normCoringas.includes(normName);
    
    let iconsHtml = "";
    if (isDriver) {
      iconsHtml += `<svg class="monitorIcon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="display:inline-block; vertical-align:middle; margin-left:6px; color:#2196F3;" title="Motorista"><path d="M12,2C6.5,2 2,6.5 2,12C2,17.5 6.5,22 12,22C17.5,22 22,17.5 22,12C22,6.5 17.5,2 12,2M12,4C15.8,4 19,6.9 19.8,10.5H16.2C15.6,9 14,8 12,8C10,8 8.4,9 7.8,10.5H4.2C5,6.9 8.2,4 12,4M4.2,13.5H7.8C8.4,15 10,16 12,16C14,16 15.6,15 16.2,13.5H19.8C19,17.1 15.8,20 12,20C8.2,20 5,17.1 4.2,13.5Z"/></svg>`;
    }
    if (isCoringa) {
      iconsHtml += `<svg class="monitorIcon" viewBox="0 0 24 24" width="14" height="14" style="display:inline-block; vertical-align:middle; margin-left:6px;" title="Coringa"><path fill="#4CAF50" d="M8,7.5c0,-0.83 0.67,-1.5 1.5,-1.5h6.5V4.5c0,-0.45 0.54,-0.67 0.85,-0.35l4.5,4.5c0.2,0.2 0.2,0.5 0,0.7l-4.5,4.5c-0.31,0.32 -0.85,0.1 -0.85,-0.35V10.5h-6.5C8.67,10.5 8,9.83 8,9V7.5z"/><path fill="#E53935" d="M16,16.5c0,0.83 -0.67,1.5 -1.5,1.5h-6.5V19.5c0,0.45 -0.54,0.67 -0.85,0.35l-4.5,-4.5c-0.2,-0.2 -0.2,-0.5 0,-0.7l4.5,-4.5c0.31,-0.32 0.85,-0.1 0.85,0.35V13.5h6.5C15.33,13.5 16,14.17 16,15V16.5z"/></svg>`;
    }

    return `<li style="display:flex; align-items:center;">${escapeHtml(name)}${iconsHtml}</li>`;
  }).join("")}</ul>`;
}
function detailValue(value) { if (value === null || value === undefined) return "-"; const text = String(value).trim(); return text || "-"; }
function hasMeaningfulValue(value) { const text = detailValue(value); return text !== '-' && safeUpper(text) !== 'NULL'; }
function getViewMode() {
  const mode = document.body?.dataset?.teamView;
  if (mode === 'inactive') return 'inactive';
  if (mode === 'trash') return 'trash';
  return 'active';
}
function getActiveFilterValue() {
  const mode = getViewMode();
  if (mode === 'trash') return 'all'; // Na lixeira buscamos tudo da lixeira
  return 'all'; // Para Ativas/Inativas, buscamos tudo para manter em cache
}
function getTeamCountLabel() {
  const mode = getViewMode();
  if (mode === 'inactive') return 'Inativas';
  if (mode === 'trash') return 'Na Lixeira';
  return 'Equipes';
}

function normalizeKpiFilter(value) {
  const raw = safeUpper(value);
  switch (raw) {
    case "ABERTO":
    case "INTERVALO":
    case "FECHADO":
    case "DESATUALIZADO":
    case "ALERTA":
    case "DDS_OK":
    case "DDS":
      return "DDS_OK";
    case "DESLOCAMENTO":
    case "DESLOCAMENTO_ESPECIAL":
      return "DESLOCAMENTO_ESPECIAL";
    default:
      return "";
  }
}

function activeAlertFilter(item) {
  const alerta = safeUpper(item?.alerta);
  return alerta === "YELLOW" || alerta === "RED" || alerta === "PULSE";
}

function syncKpiSelection() {
  if (!kpis) return;
  const current = normalizeKpiFilter(activeKpiFilter);
  kpis.querySelectorAll(".kpi").forEach((chip) => {
    const chipFilter = normalizeKpiFilter(chip.dataset.filter || chip.dataset.kpi);
    const isActive = Boolean(current) && chipFilter === current;
    chip.classList.toggle("kpiFilterActive", isActive);
    chip.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function hoverRows(item) {
  const rows = [];
  rows.push(`<div class="hoverRow"><span>Atualizado</span><strong>${escapeHtml(fmtDateTime(item.updatedAt))}</strong></div>`);
  if (hasMeaningfulValue(item.ss)) rows.push(`<div class="hoverRow"><span>SS/NOC</span><strong>${escapeHtml(detailValue(item.ss))}</strong></div>`);
  if (normalizedState(item.estado) === 'DESLOCAMENTO_ESPECIAL' && hasMeaningfulValue(item.motivo)) rows.push(`<div class="hoverRow"><span>Motivo</span><strong>${escapeHtml(detailValue(item.motivo))}</strong></div>`);
  return rows.join('');
}

function normalizeDdsEntry(value) {
  if (value === true) return "ok";
  if (value === false) return "fail";
  const raw = safeUpper(value);
  if (["OK", "FEITO", "SIM", "TRUE", "DONE", "CHECK", "CHECKED", "CONCLUIDO", "CONCLUÍDO"].includes(raw)) return "ok";
  if (["X", "NAO", "NÃO", "FALSE", "PENDENTE", "NAO_FEITO", "NÃO_FEITO", "FAIL"].includes(raw)) return "fail";
  return "neutral";
}

function formatDdsDayOnly(day) {
  if (!day) return "";
  const parts = String(day).split("-");
  if (parts.length !== 3) return String(day);
  return String(Number(parts[2]));
}

function formatDdsFullDate(day) {
  if (!day) return "";
  const parts = String(day).split("-");
  if (parts.length !== 3) return String(day);
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

function ddsStatusLabel(status) {
  if (status === "ok") return "DDS feito";
  if (status === "fail") return "Equipe sem DDS";
  return "Sem DDS no dia";
}

function ddsSequenceHtml(item, options = {}) {
  const ddsToggle = document.getElementById("ddsToggle");
  if (!ddsToggle || !ddsToggle.checked) return "";
  const {
    maxItems = 5,
    showDayLabels = false,
    showMeta = true,
    label = "DDS",
    hintText = `Últimos ${maxItems}`,
    containerClass = "",
  } = options;

  const raw = Array.isArray(item.ddsHistory)
    ? item.ddsHistory
    : Array.isArray(item.ddsSequence)
      ? item.ddsSequence
      : [];
  const days = Array.isArray(item.ddsDays) ? item.ddsDays : [];

  let dots = "";

  if (showDayLabels) {
    // Modo de Grade Calendário (Ex: Popover/Modal)
    // Calcula o número de semanas com base em maxItems (10 -> 2 semanas, 20 -> 3 semanas)
    const numWeeks = maxItems > 14 ? 3 : 2;
    const totalDays = numWeeks * 7;

    // Encontra o "hoje" baseado no último dia de histórico enviado pelo back
    const todayStr = days.length > 0 ? days[days.length - 1] : new Date().toISOString().split('T')[0];
    const todayParts = todayStr.split("-");
    const todayDate = new Date(Number(todayParts[0]), Number(todayParts[1]) - 1, Number(todayParts[2]));

    // Encontra o domingo inicial
    const weeksBefore = numWeeks - 1;
    const startSunday = new Date(todayDate);
    startSunday.setDate(todayDate.getDate() - todayDate.getDay() - (weeksBefore * 7));

    const calendarDots = [];
    for (let i = 0; i < totalDays; i++) {
      const d = new Date(startSunday);
      d.setDate(startSunday.getDate() + i);

      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const dateStr = `${yyyy}-${mm}-${dd}`;

      const dayLabel = d.getDate();
      const dayIdx = days.indexOf(dateStr);

      let status = "neutral";
      let isFuture = false;

      if (dateStr > todayStr) {
        status = "future";
        isFuture = true;
      } else if (dayIdx !== -1) {
        status = normalizeDdsEntry(raw[dayIdx]);
      }

      const statusText = isFuture ? "Dia futuro" : ddsStatusLabel(status);
      const timeStr = (status === "ok" && item.ddsTimes && item.ddsTimes[dateStr]) ? ` (${item.ddsTimes[dateStr]})` : "";
      const tooltip = `${formatDdsFullDate(dateStr)} • ${statusText}${timeStr}`;
      const isToday = dateStr === todayStr;

      const photoUrl = (status === "ok" && item.ddsPhotos && item.ddsPhotos[dateStr]) ? item.ddsPhotos[dateStr] : "";
      const hasPhotoClass = photoUrl ? " has-photo" : "";

      calendarDots.push(`
        <span class="ddsDayDot${hasPhotoClass}" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}" ${photoUrl ? `data-photo="${escapeHtml(photoUrl)}"` : ""}>
          <span class="ddsDayLabel">${escapeHtml(dayLabel)}</span>
          <span class="ddsDotWrap${isToday ? " isCurrent" : ""}">
            <span class="ddsDot ddsDot--${status}${isToday ? " ddsDot--current" : ""}"></span>
          </span>
        </span>
      `);
    }
    dots = calendarDots.join("");
  } else {
    // Modo Compacto (Ex: Card principal)
    const recentRaw = raw.slice(-maxItems);
    const recentDays = days.slice(-maxItems);

    const normalized = recentRaw.map(normalizeDdsEntry);
    while (normalized.length < maxItems) normalized.unshift("neutral");
    while (recentDays.length < maxItems) recentDays.unshift("");

    dots = normalized.map((status, idx) => {
      const isCurrent = idx === normalized.length - 1;
      const day = recentDays[idx];
      const statusText = ddsStatusLabel(status);
      const timeStr = (status === "ok" && day && item.ddsTimes && item.ddsTimes[day]) ? ` (${item.ddsTimes[day]})` : "";
      const tooltip = day ? `${formatDdsFullDate(day)} • ${statusText}${timeStr}` : statusText;

      const photoUrl = (status === "ok" && day && item.ddsPhotos && item.ddsPhotos[day]) ? item.ddsPhotos[day] : "";
      const hasPhotoClass = photoUrl ? " has-photo" : "";

      return `
        <span class="ddsDotWrap${isCurrent ? " isCurrent" : ""}${hasPhotoClass}" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}" ${photoUrl ? `data-photo="${escapeHtml(photoUrl)}"` : ""}>
          <span class="ddsDot ddsDot--${status}${isCurrent ? " ddsDot--current" : ""}"></span>
        </span>
      `;
    }).join("");
  }

  const rowClass = ["ddsRow", containerClass, showDayLabels ? "ddsRowExpanded" : "", showMeta ? "" : "ddsRowCompact"]
    .filter(Boolean)
    .join(" ");

  const trackClass = ["ddsTrack", showDayLabels ? "ddsTrackExpanded" : "", showMeta ? "" : "ddsTrackCompact"]
    .filter(Boolean)
    .join(" ");

  const actualHintText = showDayLabels ? `Últimas ${maxItems > 14 ? 3 : 2} semanas` : hintText;

  return `
    <div class="${rowClass}" aria-label="DDS">
      ${showMeta ? `
        <div class="ddsMeta">
          <span class="ddsLabel">${escapeHtml(label)}</span>
          <span class="ddsHint">${escapeHtml(actualHintText)}</span>
        </div>
      ` : ""}
      <div class="${trackClass}" role="list">
        ${dots}
      </div>
    </div>
  `;
}


function tile(item) {
  const shown = normalizedState(item.estado);
  const border = borderClass(item.alerta);
  const stateCard = stateCardClass(shown);
  const crit = item.critico === true;
  const equipe = detailValue(item.equipe);
  const teamKey = detailValue(item.teamKey || item.equipe);
  const participantes = participantsHtml(item.participantes, item.motorista, item.coringas, 'hoverParticipantsList');
  const details = hoverRows(item);
  const statusLabel = stateLabel(shown);
  const hideTimeLine = shown === "DESATUALIZADO";
  const art66Active = isArt66Active(item, shown);
  const art66EndAt = getArt66EndAt(item, shown);
  const closedAtLabel = fmtTimeOnly(item.updatedAt);
  const isBeforeSeven = art66EndAt && art66EndAt.getHours() < 7;
  const art66EndLabel = isBeforeSeven ? "" : fmtHourMinute(art66EndAt);

  const timeLabel = (art66Active && !isBeforeSeven)
    ? `${closedAtLabel} → ${art66EndLabel}`
    : closedAtLabel;

  const badgeLabel = item.lastWasDescansoSemanal ? "ART 67" : "ART 66";
  const badgeHtml = art66Active
    ? `<div class="critical art66Badge"><div class="art66Line1">${badgeLabel}</div>${isBeforeSeven ? '' : `<div class="art66Line2">até ${escapeHtml(art66EndLabel)}</div>`}</div>`
    : (crit ? `<div class="critical">CRÍTICO</div>` : ``);

  // Lógica de Mensagens Global por Setor (Estratégia 4)
  const currentSector = (sectorSelector?.value || 'TODOS').toUpperCase();
  const unreadMap = item.unreadMap || {};

  let unreadCurrent = 0;
  if (currentSector === 'TODOS') {
    unreadCurrent = Object.values(unreadMap).reduce((a, b) => a + b, 0);
  } else {
    unreadCurrent = Number(unreadMap[currentSector] || 0);
  }

  const totalUnread = Object.values(unreadMap).reduce((a, b) => a + b, 0);
  const hasOthers = totalUnread > unreadCurrent;

  let messageIconHtml = "";
  if (totalUnread > 0) {
    const iconClass = unreadCurrent > 0 ? "tileMessageIcon active" : "tileMessageIcon others";
    const title = unreadCurrent > 0
      ? `${unreadCurrent} mensagens para seu setor (${currentSector})`
      : `Mensagens pendentes para outros setores`;

    messageIconHtml = `
      <div class="${iconClass}" title="${escapeHtml(title)}">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="3">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 1 1-7.6-11.8 8.38 8.38 0 0 1 3.8.9L21 3l-1.4 4.7a8.38 8.38 0 0 1 .9 3.8Z" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        ${unreadCurrent > 0 ? `<span class="messageBadge">${unreadCurrent}</span>` : ""}
      </div>`;
  }

  const ddsToggle = document.getElementById("ddsToggle");
  const isDdsChecked = ddsToggle ? ddsToggle.checked : false;

  const hoverDdsHtml = isDdsChecked ? `
        <div class="hoverSection">
          <div class="hoverSectionTitle">Presenças no DDS (Últimas 2 semanas)</div>
          ${ddsSequenceHtml(item, { maxItems: 10, showDayLabels: true, showMeta: false, containerClass: "ddsRowHover" })}
        </div>
  ` : '';

  const ddsRow = ddsSequenceHtml(item, { maxItems: 5, showDayLabels: false, showMeta: false, containerClass: "tileDdsCompact" });

  const lastContactLabel = fmtLastContact(item.lastContact, item.lastContactSource);
  const isTrash = getViewMode() === 'trash';
  const trashActions = isTrash ? `
    <div class="tileTrashActions">
      <button class="btnRestore" type="button" title="Restaurar Equipe" onclick="event.stopPropagation(); window.restoreTeam('${escapeHtml(teamKey)}')">Restaurar</button>
      <button class="btnPermanentDelete" type="button" title="Excluir Permanentemente" onclick="event.stopPropagation(); window.deleteTeamPermanent('${escapeHtml(teamKey)}')">Excluir Permanente</button>
    </div>
  ` : '';

  const typeIcons = {
    'STC': '/static/img/stc_small.jpg',
    'STC_CESTO': '/static/img/stc_cesto_small.jpg',
    'LINHA_VIVA': '/static/img/linha_viva_small.jpg',
    'ROCADA': '/static/img/rocada_small.jpg',
    'CONSTRUCAO': '/static/img/construcao_small.jpg',
    'EP': '/static/img/ep_small.jpg'
  };

  let teamTypeIconHtml = '';
  if (item.teamType) {
    if (typeIcons[item.teamType]) {
      teamTypeIconHtml = `<img class="teamTypeBadgeIcon" src="${typeIcons[item.teamType]}" loading="lazy" alt="${escapeHtml(item.teamType)}" />`;
    } else {
      teamTypeIconHtml = `<div class="teamTypeBadgeIcon emojiIcon" title="Sem Definição">🚫</div>`;
    }
  } else {
    teamTypeIconHtml = `<div class="teamTypeBadgeIcon emojiIcon" title="Sem Definição">🚫</div>`;
  }

  return `<article class="tile ${stateCard} ${border} ${isTrash ? 'isTrashTile' : ''}" tabindex="0" role="button" data-team="${escapeHtml(teamKey)}" aria-label="Equipe ${escapeHtml(equipe)}, status ${escapeHtml(statusLabel)}">
    ${badgeHtml}
    ${messageIconHtml}
    <div class="tileMain">
      <div class="tileTopRow">
        <div class="tileIdentity">
          <div class="tileTitleBlock tileTitleBlockFull">
            <div class="teamIdentityBadge" title="${escapeHtml(equipe)}">
              ${teamTypeIconHtml}
              <div class="equipeCompact equipeCompactInline">${escapeHtml(equipe)}</div>
            </div>
            ${isTrash ? '' : `
            <div class="statusBlock">
              <div class="statusLine">${escapeHtml(statusLabel)}</div>
              <div class="timeLine ${hideTimeLine ? "timeLineHidden" : ""}">
                ${escapeHtml(timeLabel)}
              </div>
            </div>
            `}
          </div>
        </div>
      </div>
      ${isTrash ? trashActions : `
        <div class="tileContactRow">
           <span class="contactLabel">Último Contato:</span>
           <span class="contactValue">${escapeHtml(lastContactLabel)}</span>
         </div>
        ${ddsRow}
      `}
    </div>
    ${isTrash ? '' : `
    <div class="tileHoverPanel" aria-hidden="true">
      <div class="tileHoverTop">
        <div class="tileHoverTitles">
          <div class="teamIdentityBadge teamIdentityBadgeHover" title="${escapeHtml(equipe)}">
            ${teamTypeIconHtml}
            <div class="equipeCompact equipeCompactHover">${escapeHtml(equipe)}</div>
          </div>
          <div class="badge badgeCompact">${escapeHtml(stateLabel(shown))}</div>
        </div>
      </div>
      <div class="tileHoverBody">
        <div class="hoverRows">${details}</div>
        ${hoverDdsHtml}
        <div class="hoverSection">
          <div class="hoverSectionTitle">Participantes</div>
          ${participantes}
        </div>
      </div>
    </div>
    `}
  </article>`;
}

function getItemTeamKey(item) { return detailValue(item.teamKey || item.equipe); }
function getItemEquipe(item) { return detailValue(item.equipe || item.teamKey); }
function buildTeamOptionLabel(item) {
  const equipe = getItemEquipe(item);
  const teamKey = getItemTeamKey(item);
  return safeUpper(equipe) === safeUpper(teamKey) ? equipe : `${equipe} — ${teamKey}`;
}
function syncTeamSelect(items) {
  if (!teamSelect) return;
  const previous = teamSelect.value || '';
  const unique = new Map();
  (items || []).forEach((item) => {
    const key = getItemTeamKey(item);
    if (!key || key === '-') return;
    if (!unique.has(key)) unique.set(key, buildTeamOptionLabel(item));
  });
  const ordered = [...unique.entries()].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR', { sensitivity: 'base' }));
  teamSelect.innerHTML = `<option value="">Todas as equipes</option>${ordered.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('')}`;
  if (previous && unique.has(previous)) teamSelect.value = previous;
}
function applyFilters(items) {
  const q = safeUpper(searchInput.value);
  const selectedTeam = safeUpper(teamSelect?.value);
  const kpiFilter = normalizeKpiFilter(activeKpiFilter);
  return (items || []).filter((it) => {
    const eq = safeUpper(it.equipe);
    const teamKey = safeUpper(it.teamKey || it.equipe);
    const shown = normalizedState(it.estado);
    const matchesText = !q || eq.includes(q) || teamKey.includes(q);
    const matchesTeam = !selectedTeam || teamKey === selectedTeam;
    const matchesKpi =
      !kpiFilter ||
      (kpiFilter === "ALERTA" ? activeAlertFilter(it) :
        kpiFilter === "DDS_OK" ? it.ddsToday === "ok" :
          shown === kpiFilter);
    return matchesText && matchesTeam && matchesKpi;
  });
}

function renderKpis(items) {
  const counts = { ABERTO: 0, INTERVALO: 0, DESLOCAMENTO_ESPECIAL: 0, FECHADO: 0, DESATUALIZADO: 0, DESCONHECIDO: 0, ALERTA: 0 };
  let ddsOk = 0;
  let ddsTotal = 0;

  (items || []).forEach((it) => {
    const st = normalizedState(it.estado);
    if (counts[st] !== undefined) counts[st]++;
    const alerta = safeUpper(it.alerta);
    if (alerta === "YELLOW" || alerta === "RED" || alerta === "PULSE") counts.ALERTA++;

    if (it.ddsToday === "ok") {
      ddsOk++;
      ddsTotal++;
    } else if (it.ddsToday === "fail") {
      ddsTotal++;
    }
  });

  const ddsToggle = document.getElementById("ddsToggle");
  const showDdsKpi = ddsToggle && ddsToggle.checked;
  const ddsKpiHtml = showDdsKpi ? `
    <button class="kpi kpiHintWrap" type="button" data-kpi="dds_ok" data-filter="DDS_OK" aria-label="Filtrar equipes com DDS concluído" aria-pressed="false">
      <span class="kpiDot dotTeal"></span>
      <span>${ddsOk}/${ddsTotal}</span>
      <span class="kpiHint">DDS Realizado</span>
    </button>
  ` : '';

  kpis.innerHTML = `
    <button class="kpi kpiHintWrap" type="button" data-kpi="aberto" data-filter="ABERTO" aria-label="Filtrar equipes abertas" aria-pressed="false"><span class="kpiDot dotGreen"></span><span>${counts.ABERTO}</span><span class="kpiHint">Equipes em aberto</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="intervalo" data-filter="INTERVALO" aria-label="Filtrar equipes em intervalo" aria-pressed="false"><span class="kpiDot dotYellow"></span><span>${counts.INTERVALO}</span><span class="kpiHint">Equipes em intervalo</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="deslocamento" data-filter="DESLOCAMENTO_ESPECIAL" aria-label="Filtrar deslocamento especial" aria-pressed="false"><span class="kpiDot dotBlue"></span><span>${counts.DESLOCAMENTO_ESPECIAL}</span><span class="kpiHint">Deslocamento especial</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="fechado" data-filter="FECHADO" aria-label="Filtrar equipes fechadas" aria-pressed="false"><span class="kpiDot dotRed"></span><span>${counts.FECHADO}</span><span class="kpiHint">Equipes fechadas</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="desatualizado" data-filter="DESATUALIZADO" aria-label="Filtrar equipes desatualizadas" aria-pressed="false"><span class="kpiDot dotGray"></span><span>${counts.DESATUALIZADO}</span><span class="kpiHint">Equipes desatualizadas</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="alerta" data-filter="ALERTA" aria-label="Filtrar equipes em alerta" aria-pressed="false"><span class="kpiWarn">⚠</span><span>${counts.ALERTA}</span><span class="kpiHint">Alertas de atualização</span></button>
    ${ddsKpiHtml}`;
  syncKpiSelection();
}

function renderTeamCount(items) {
  if (teamCount) teamCount.textContent = `${getTeamCountLabel()}: ${Array.isArray(items) ? items.length : 0}`;
}
function findItem(teamKey) { return currentItems.find((item) => detailValue(item.teamKey || item.equipe) === teamKey) || null; }
function getEmpresaValue() { return (empresaInput.value || cfg?.defaultEmpresa || '').trim(); }

function syncHoverPlacement(tileEl) {
  if (!grid || !tileEl) return;

  const gridRect = grid.getBoundingClientRect();
  const viewportLeft = Math.max(12, gridRect.left);
  const viewportRight = Math.min(window.innerWidth - 12, gridRect.right);

  tileEl.classList.remove('tileHoverShiftLeft');
  tileEl.classList.remove('tileHoverShiftRight');

  const tileRect = tileEl.getBoundingClientRect();
  const hoverWidth = Math.min((tileRect.width * 2) + 12, 420);

  const defaultLeft = tileRect.left - (hoverWidth * 0.25);
  const defaultRight = defaultLeft + hoverWidth;

  if (defaultRight > viewportRight) {
    tileEl.classList.add('tileHoverShiftLeft');
  } else if (defaultLeft < viewportLeft) {
    tileEl.classList.add('tileHoverShiftRight');
  }
}

window.monitorUtils = {
  safeUpper,
  escapeHtml,
  fmtDateTime,
  fmtTimeOnly,
  fmtAgeFromMinutes,
  normalizedState,
  stateLabel,
  vehicleFrameClass,
  participantsHtml,
  renderDdsKpiHtml: ddsSequenceHtml,
  detailValue,
};

window.monitorState = {
  getConfig: () => cfg,
  getEmpresa: () => getEmpresaValue(),
  getViewMode,
  findItem,
  reload: (options = {}) => load(options),
  getCurrentItems: () => [...currentItems],
  getCurrentSector: () => {
    const selector = document.getElementById('sectorSelector');
    return selector ? selector.value : (localStorage.getItem('dds_monitor_setor') || 'TODOS');
  },
};

function syncRealtimeData() {
  const mode = getViewMode();
  if (mode === 'trash') return; // Lixeira ainda usa fetch normal

  // Applica os filtros em cima da memória (allRealtimeItems)
  const isInactiveMode = mode === 'inactive';

  // Estágio 1: Filtros de texto, equipe e ativo/inativo (usados para a contagem de KPIs)
  const baseFiltered = allRealtimeItems.filter(item => {
    // 1. Filtro de Ativa/Inativa
    const itemActive = item.active !== false; // Padrão é true
    if (isInactiveMode && itemActive) return false;
    if (!isInactiveMode && !itemActive) return false;

    // O Filtro de Setor (TIPO) agora é apenas para mensagens e requisições.
    // As equipes aparecem globais para todos os setores conforme solicitado.

    // 3. Filtros de Pesquisa e KPI (já existentes)
    const q = safeUpper(searchInput.value);
    const selectedTeam = safeUpper(teamSelect?.value);

    const eq = safeUpper(item.equipe);
    const teamKey = safeUpper(item.teamKey || item.equipe);

    const matchesText = !q || eq.includes(q) || teamKey.includes(q);
    const matchesTeam = !selectedTeam || teamKey === selectedTeam;

    return matchesText && matchesTeam;
  });

  // Estágio 2: Filtro de KPI (para determinar os cards exibidos)
  const kpiFilter = normalizeKpiFilter(activeKpiFilter);
  const filtered = baseFiltered.filter(item => {
    const shown = normalizedState(item.estado);
    const matchesKpi = !kpiFilter || (
      kpiFilter === "ALERTA" ? activeAlertFilter(item) :
        kpiFilter === "DDS_OK" ? item.ddsToday === "ok" :
          shown === kpiFilter
    );
    return matchesKpi;
  });

  currentItems = filtered;
  renderData(filtered, lastData || { empresa: getEmpresaValue(), serverTime: new Date().toISOString() }, baseFiltered);
}

function startPolling() {
  if (pollingTimer) clearInterval(pollingTimer);
  if (countdownTimer) clearInterval(countdownTimer);

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

  const empresa = getEmpresaValue();

  const mode = getViewMode();
  if (mode === 'trash') {
    // A lixeira ainda usa fetch normal
    load();
    return;
  }

  if (!db) {
    // Fallback: usar HTTP polling normal
    nextRefresh.textContent = "Polling Ativo ⏳";
    const safeSeconds = Math.max(15, pollingSeconds);
    pollingTimer = setInterval(() => {
      load({ forceRefresh: true });
    }, safeSeconds * 1000);

    countdownTimer = setInterval(() => {
      setRefreshInfo();
    }, 1000);
    return;
  }

  // ==========================================
  // ESTRATÉGIA 3: ONSNAPSHOT REALTIME
  // ==========================================
  nextRefresh.textContent = "Real-time Ativo ⚡";
  let initialSnapshot = true;

  unsubMonitor = db.collection("turno").doc(empresa).collection("realtime")
    .onSnapshot((snapshot) => {
      // Usamos docChanges para identificar exatamente o que mudou e avisar o servidor (patch incremental)
      snapshot.docChanges().forEach((change) => {
        const item = change.doc.data();
        const teamKey = item.teamKey || item.equipe;

        if (change.type === "added" || change.type === "modified") {
          // Atualiza nosso cache local em memória
          const idx = allRealtimeItems.findIndex(it => (it.teamKey || it.equipe) === teamKey);
          if (idx !== -1) {
            allRealtimeItems[idx] = item;
          } else {
            allRealtimeItems.push(item);
          }
          if (!initialSnapshot && change.type === "modified") {
            updateSingleTeamCard(item);
          }
        } else if (change.type === "removed") {
          allRealtimeItems = allRealtimeItems.filter(it => (it.teamKey || it.equipe) !== teamKey);
        }
      });

      // Amortecedor (Throttle): Na primeira carga, renderiza IMEDIATO. 
      // Depois, segura a interface a cada 10 segundos para economizar CPU.
      if (initialSnapshot) {
        syncRealtimeData();
        initialSnapshot = false;
      } else {
        requestUiSync();
      }
    }, (error) => {
      console.error("Erro no onSnapshot do Firebase:", error);
      lastSync.textContent = "Atualizado: ERRO DE PERMISSÃO";
    });

  unsubActivityFeed = db.collection("webtools").doc("monitor").collection("activity_feed").doc(empresa)
    .onSnapshot((doc) => {
      if (doc.exists) {
        const data = doc.data();
        if (data && Array.isArray(data.items)) {
          const initialCached = getLocalFeedCache(empresa);
          const updatedCache = mergeActivityFeedItems(initialCached, data.items);
          saveLocalFeedCache(empresa, updatedCache);
          renderActivityFeed(updatedCache);
        }
      }
    }, (error) => {
      console.warn("Erro ao assinar activity_feed no Firestore:", error);
    });

  // Reloginho Local: Atualiza as cores (Amarelo, Vermelho) a cada 30 segundos
  // sem fazer nenhuma leitura a mais no banco de dados!
  pollingTimer = setInterval(() => {
    recalculateLocalAlerts();
  }, 30000);
}

let uiSyncTimeout = null;
function requestUiSync() {
  if (uiSyncTimeout) return; // Já existe uma atualização agendada

  uiSyncTimeout = setTimeout(() => {
    syncRealtimeData();
    uiSyncTimeout = null;
  }, 3000); // 3 segundos de espera
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
  fillConfigForm(cfg);
}

async function loadDdsBackground(forceRefresh = false) {
  const empresa = getEmpresaValue();
  const active = getActiveFilterValue();
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

    // Merge dos campos DDS em allRealtimeItems
    let merged = false;
    data.items.forEach(ddsItem => {
      const idx = allRealtimeItems.findIndex(it => it.teamKey === ddsItem.teamKey);
      if (idx !== -1) {
        const current = allRealtimeItems[idx];
        const ddsContactIsNewer = isIsoNewer(ddsItem.lastContact, current.lastContact);
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
          ...(ddsItem.estado ? { estado: ddsItem.estado } : {}),
          ...(ddsItem.updatedAt ? { updatedAt: ddsItem.updatedAt } : {}),
        };
        merged = true;
      }
    });

    ddsDataLoaded = true;
    if (merged) syncRealtimeData(); // Re-renderiza silenciosamente com DDS
  } catch (e) {
    console.warn('Erro ao carregar DDS lazy:', e);
  }
}

async function load(options = {}) {
  const forceRefresh = options.forceRefresh || false;
  const refreshSpinner = document.getElementById('refreshSpinner');

  if (forceRefresh) {
    if (refreshBtn) refreshBtn.disabled = true;
    if (refreshSpinner) refreshSpinner.hidden = false;
  }

  const empresa = getEmpresaValue();
  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('active', getActiveFilterValue());

  const sectorSelector = document.getElementById('sectorSelector');
  const selectedSector = sectorSelector ? sectorSelector.value : (localStorage.getItem('dds_monitor_setor') || 'TODOS');
  if (selectedSector) qs.set('setor', selectedSector);

  if (forceRefresh) qs.set('refresh', 'manual');

  const mode = getViewMode();
  let url = `/api/turnos?${qs.toString()}`;
  if (mode === 'trash') {
    url = `/api/teams/trash`;
  }

  if (!forceRefresh) {
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



    // Atualiza o cache local com os dados frescos do servidor
    allRealtimeItems = data.items || [];
    ddsDataLoaded = false; // Reseta flag: DDS precisa ser carregado novamente
    lastData = data;
    syncRealtimeData();

    // Carga lazy de DDS e feed em background (sem bloquear a UI)
    loadDdsBackground(forceRefresh);
    loadActivityFeed();
  } catch (e) {
    console.error('Erro ao carregar monitor:', e);
    lastSync.textContent = 'Atualizado: ERRO';
    grid.innerHTML = '<div class="emptyState">Não foi possível carregar o monitor.</div>';
    if (kpis) kpis.innerHTML = `<div class="kpi">⚠ erro ao carregar</div>`;
    renderTeamCount([]);
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
    if (refreshSpinner) refreshSpinner.hidden = true;

    const safeSeconds = Math.max(15, pollingSeconds);
    nextTickAtMs = Date.now() + safeSeconds * 1000;
    setRefreshInfo();
  }
}

function updateSingleTeamCard(item) {
  const teamKey = item.teamKey || item.equipe;
  if (!teamKey) return;
  const cardId = `card-${teamKey.replace(/[^\w]/g, '_')}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  const coreData = JSON.stringify({
    st: item.estado,
    al: item.alerta,
    cr: item.critico,
    ss: item.ss,
    msg: item.unreadMap,
    dds: (item.ddsHistory || []).slice(-1)[0]
  });

  const oldCore = card.dataset.core;
  const hasChanged = oldCore !== coreData;
  if (!hasChanged) return;

  const html = tile(item);
  const flashClass = ' flash-update';
  const order = card.style.order || '0';

  card.outerHTML = html.replace('class="tile', `id="${cardId}" style="order: ${order}" data-core='${coreData}' class="tile${flashClass}`);

  const newCard = document.getElementById(cardId);
  if (newCard) {
    newCard.addEventListener('mouseenter', () => syncHoverPlacement(newCard));
  }
}

function renderData(items, meta, kpiSourceItems) {
  if (skeletonGrid) skeletonGrid.classList.add('hidden');
  if (grid) grid.classList.remove('hidden');

  if (empresaLabel) empresaLabel.textContent = meta.empresa || '-';
  lastSync.textContent = `Atualizado: ${fmtTimeOnly(meta.serverTime)}`;
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

  syncTeamSelect(sortedItems);
  currentItems = sortedItems;

  if (getViewMode() !== 'trash') {
    renderKpis(kpiSourceItems || items);
    kpis.hidden = false;
  } else {
    kpis.hidden = true;
  }

  renderTeamCount(currentItems);

  if (!currentItems.length) {
    grid.innerHTML = `<div class="emptyState">Nenhuma equipe encontrada nesta visualização.</div>`;
    return;
  }

  // RENDERIZAÇÃO INCREMENTAL:
  // Em vez de limpar o grid, vamos atualizar apenas os cards que mudaram.
  const container = grid;
  const existingIds = new Set();

  currentItems.forEach((item, index) => {
    const teamKey = item.teamKey || item.equipe;
    const cardId = `card-${teamKey.replace(/[^\w]/g, '_')}`;
    existingIds.add(cardId);

    let card = document.getElementById(cardId);
    const html = tile(item);

    // Dados vitais para decidir se deve 'piscar' (ignora relógio)
    const coreData = JSON.stringify({
      st: item.estado,
      al: item.alerta,
      cr: item.critico,
      ss: item.ss,
      msg: item.unreadMap,
      dds: (item.ddsHistory || []).slice(-1)[0]
    });

    if (!card) {
      const temp = document.createElement('div');
      temp.innerHTML = html;
      card = temp.firstElementChild;
      card.id = cardId;
      card.dataset.core = coreData;
      card.style.order = index;
      card.addEventListener('mouseenter', () => syncHoverPlacement(card));
      container.appendChild(card);
    } else {
      const oldCore = card.dataset.core;
      const hasChanged = oldCore !== coreData;

      // Sempre atualiza o HTML para manter o relógio fresco, 
      // mas só aplica o 'flash-update' se o dado vital mudou
      const flashClass = hasChanged ? ' flash-update' : '';
      card.outerHTML = html.replace('class="tile', `id="${cardId}" style="order: ${index}" data-core='${coreData}' class="tile${flashClass}`);

      const newCard = document.getElementById(cardId);
      if (newCard) newCard.addEventListener('mouseenter', () => syncHoverPlacement(newCard));
    }
  });

  // Remove cards que não estão mais na lista filtrada
  Array.from(container.children).forEach(child => {
    if (child.id && child.id.startsWith('card-') && !existingIds.has(child.id)) {
      container.removeChild(child);
    }
  });

  if (window.teamForm?.refreshOpenTeam) {
    const openTeamKey = window.teamForm.getOpenTeamKey?.();
    if (openTeamKey) window.teamForm.refreshOpenTeam(findItem(openTeamKey));
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

  // Limpa estado anterior
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
  document.getElementById('trashConfirmModal').hidden = true;
  document.getElementById('trashConfirmModalBackdrop').hidden = true;
  if (configModal?.hidden && document.getElementById('teamFormModal')?.hidden) {
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
      window.teamForm?.closeTeamForm?.(); // Fecha a tela de detalhes da equipe
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

refreshBtn.addEventListener('click', async () => { await load({ forceRefresh: true }); startPolling(); });
configBtn?.addEventListener('click', openConfigModal);
configModalClose?.addEventListener('click', closeConfigModal);
configModalCancel?.addEventListener('click', closeConfigModal);
configModalBackdrop?.addEventListener('click', closeConfigModal);
configModalSave?.addEventListener('click', saveConfigModal);
[cfgAlertaAmareloMin, cfgAlertaVermelhoMin, cfgAlertaPiscoMin, cfgFechadoViraDesatualizadoHoras, cfgDesatualizadoCriticoHoras, cfgPollingSeconds].forEach((el) => el?.addEventListener('input', syncConfigSummary));

const ddsToggle = document.getElementById("ddsToggle");
const savedDdsState = localStorage.getItem('monitor_show_dds') === 'true';
if (ddsToggle) {
  ddsToggle.checked = savedDdsState;
  ddsToggle.addEventListener('change', () => {
    localStorage.setItem('monitor_show_dds', ddsToggle.checked);
    // Se ligou o DDS e os dados ainda não foram carregados, carrega agora
    if (ddsToggle.checked && !ddsDataLoaded) {
      loadDdsBackground();
    } else {
      syncRealtimeData();
    }
  });
}

searchInput.addEventListener('input', () => syncRealtimeData());
teamSelect?.addEventListener('change', () => syncRealtimeData());

grid.addEventListener('click', (event) => {
  const tileEl = event.target.closest('.tile');
  if (!tileEl || getViewMode() === 'trash') return;
  window.teamForm?.openTeamForm?.(tileEl.dataset.team || '');
});

grid.addEventListener('keydown', (event) => {
  const tileEl = event.target.closest('.tile');
  if (!tileEl) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (getViewMode() === 'trash') return;
    window.teamForm?.openTeamForm?.(tileEl.dataset.team || '');
  }
});

kpis.addEventListener('click', (event) => {
  const chip = event.target.closest('.kpi');
  if (!chip) return;
  const nextFilter = normalizeKpiFilter(chip.dataset.filter || chip.dataset.kpi);
  const sameFilter = normalizeKpiFilter(activeKpiFilter) === nextFilter;

  if (sameFilter) {
    activeKpiFilter = "";
  } else {
    activeKpiFilter = nextFilter;
  }

  syncKpiSelection();

  // O usuário solicitou que ao trocar o status (mesmo em memória), mostre o skeleton
  showSkeleton();

  // Pequeno delay apenas para o skeleton ser visível e dar sensação de "processamento"
  // e satisfazer o requisito visual do usuário.
  setTimeout(() => {
    syncRealtimeData();
  }, 150);

  event.stopPropagation();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  window.teamForm?.closeTeamForm?.();
  closeConfigModal();
});

window.addEventListener('resize', () => {
  requestAnimationFrame(syncHoverPlacement);
});

const sectorSelector = document.getElementById('sectorSelector');
if (sectorSelector) {
  sectorSelector.value = localStorage.getItem('dds_monitor_setor') || 'TODOS';
  sectorSelector.addEventListener('change', () => {
    localStorage.setItem('dds_monitor_setor', sectorSelector.value);
    syncRealtimeData();
  });
}

// Lógica de Navegação Dinâmica (SPA)
function initNavigation() {
  // Carrega contagem de crash reports ao iniciar
  loadCrashReports();

  document.querySelectorAll('.viewTab').forEach(tab => {
    // A aba de solicitações tem comportamento próprio, ignoramos aqui
    if (tab.id === 'requestsTab') return;

    tab.addEventListener('click', async (e) => {
      try {
        const href = tab.getAttribute('href') || '';
        const newMode = href.includes('inativas') ? 'inactive' :
          href.includes('lixeira') ? 'trash' : 'active';
        const oldMode = getViewMode();

        if (newMode === oldMode) return;

        e.preventDefault();

        // 1. Atualiza a URL sem recarregar
        history.pushState({ mode: newMode }, '', tab.href);

        // 2. Atualiza o estado visual
        document.body.setAttribute('data-team-view', newMode);
        document.querySelectorAll('.viewTab').forEach(t => t.classList.remove('isActive'));
        tab.classList.add('isActive');

        // 3. Atualiza o título da página
        const pageTitle = document.querySelector('.h1');
        if (pageTitle) {
          pageTitle.textContent = newMode === 'inactive' ? 'Equipes Inativas' :
            newMode === 'trash' ? 'Lixeira de Equipes' : 'Monitor de Turnos';
        }

        // 4. Limpa a lista atual imediatamente (mostra skeleton) para feedback instantâneo
        showSkeleton();

        // 5. Reinicia o monitoramento/polling para o novo modo
        // Se for apenas troca entre Ativas/Inativas, e já temos o listener e dados, basta filtrar em memória.
        // Se allRealtimeItems estiver vazio, forçamos o reinício para garantir a carga.
        if (newMode !== 'trash' && oldMode !== 'trash' && typeof unsubMonitor === 'function' && allRealtimeItems.length > 0) {
          syncRealtimeData();
        } else {
          startPolling();
        }
      } catch (err) {
        console.error("Erro na navegação dinâmica:", err);
        window.location.href = tab.href; // Fallback para navegação real
      }
    });
  });

  // Trata o botão "Voltar" do navegador
  window.addEventListener('popstate', (e) => {
    const mode = e.state?.mode || 'active';
    document.body.dataset.teamView = mode;
    syncRealtimeData();
  });
}



// Lógica de Reset Diário (00:00)
function triggerFullDailyReset() {
  const lastReset = localStorage.getItem('dds_monitor_last_reset_day');
  const today = new Date().toISOString().split('T')[0];

  if (lastReset && lastReset !== today) {
    console.log("[DailyReset] Virada de dia detectada. Forçando recriação do cache.");
    load({ forceRefresh: true });
  }
  localStorage.setItem('dds_monitor_last_reset_day', today);
}

// Estilos dinâmicos para hover e cursor nas bolinhas com fotos
(() => {
  const style = document.createElement("style");
  style.textContent = `
    .has-photo {
      cursor: pointer !important;
    }
    .has-photo:hover .ddsDot {
      transform: scale(1.3);
      filter: brightness(1.2);
      box-shadow: 0 0 8px var(--green, #22c55e);
      transition: transform 0.2s ease, filter 0.2s ease, box-shadow 0.2s ease;
    }
    @keyframes ddsModalSpin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
})();

function showDdsPhotoModal(photoUrl) {
  let modal = document.getElementById("ddsPhotoModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "ddsPhotoModal";
    modal.style.position = "fixed";
    modal.style.top = "0";
    modal.style.left = "0";
    modal.style.width = "100%";
    modal.style.height = "100%";
    modal.style.backgroundColor = "rgba(10, 15, 30, 0.9)";
    modal.style.display = "none";
    modal.style.alignItems = "center";
    modal.style.justifyContent = "center";
    modal.style.zIndex = "4000";
    modal.style.opacity = "0";
    modal.style.transition = "opacity 0.2s ease";
    modal.style.cursor = "pointer";

    // Loader spinner
    const loader = document.createElement("div");
    loader.id = "ddsPhotoModalLoader";
    loader.style.border = "4px solid rgba(255, 255, 255, 0.1)";
    loader.style.borderTop = "4px solid var(--green, #22c55e)";
    loader.style.borderRadius = "50%";
    loader.style.width = "45px";
    loader.style.height = "45px";
    loader.style.position = "absolute";
    loader.style.animation = "ddsModalSpin 1s linear infinite";
    loader.style.display = "none";
    loader.style.zIndex = "4001";

    const img = document.createElement("img");
    img.id = "ddsPhotoModalImg";
    img.style.maxWidth = "85%";
    img.style.maxHeight = "85%";
    img.style.borderRadius = "12px";
    img.style.border = "1px solid rgba(255, 255, 255, 0.1)";
    img.style.boxShadow = "0 12px 40px rgba(0, 0, 0, 0.7)";
    img.style.cursor = "default";
    img.style.transition = "transform 0.2s ease";
    img.style.transform = "scale(0.95)";

    img.addEventListener("click", (e) => e.stopPropagation());

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "×";
    closeBtn.style.position = "absolute";
    closeBtn.style.top = "20px";
    closeBtn.style.right = "30px";
    closeBtn.style.background = "none";
    closeBtn.style.border = "none";
    closeBtn.style.color = "rgba(255, 255, 255, 0.8)";
    closeBtn.style.fontSize = "48px";
    closeBtn.style.cursor = "pointer";
    closeBtn.style.lineHeight = "1";

    closeBtn.addEventListener("mouseenter", () => closeBtn.style.color = "#fff");
    closeBtn.addEventListener("mouseleave", () => closeBtn.style.color = "rgba(255, 255, 255, 0.8)");

    modal.appendChild(loader);
    modal.appendChild(img);
    modal.appendChild(closeBtn);
    document.body.appendChild(modal);

    modal.addEventListener("click", () => {
      modal.style.opacity = "0";
      img.style.transform = "scale(0.95)";
      setTimeout(() => {
        modal.style.display = "none";
      }, 200);
    });
  }

  const img = document.getElementById("ddsPhotoModalImg");
  const loader = document.getElementById("ddsPhotoModalLoader");

  // Oculta a imagem anterior e exibe o loader
  img.style.display = "none";
  if (loader) loader.style.display = "block";

  img.onload = () => {
    if (loader) loader.style.display = "none";
    img.style.display = "block";
  };
  img.onerror = () => {
    if (loader) loader.style.display = "none";
  };

  img.src = photoUrl;

  modal.style.display = "flex";
  // Forçar reflow
  modal.offsetHeight;
  modal.style.opacity = "1";
  img.style.transform = "scale(1)";
}

// Listener de clique global para bolinhas com fotos
document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-photo]");
  if (target) {
    const photoUrl = target.getAttribute("data-photo");
    if (photoUrl) {
      event.preventDefault();
      event.stopPropagation();
      showDdsPhotoModal(photoUrl);
    }
  }
});

(async () => {
  try {
    await loadConfig();
  } catch (error) {
    console.error('Erro ao carregar configuração do monitor:', error);
    cfg = cfg || { defaultEmpresa: empresaInput?.value || '', pollingSeconds, rules: {} };
  }
  initNavigation(); // Inicializa a navegação SPA
  await load();
  startPolling();
})();