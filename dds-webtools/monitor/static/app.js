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
const cfgPollingSeconds = document.getElementById("cfgPollingSeconds");


let cfg = null;
let pollingSeconds = 600;
let pollingTimer = null;
let countdownTimer = null;
let nextTickAtMs = null;
let currentItems = [];
let activeKpiFilter = "";
let configSaveInFlight = false;

let lastData = null;

function safeUpper(v) { return (v || "").toString().trim().toUpperCase(); }
function escapeHtml(value) { return (value ?? "").toString().replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;"); }
function fmtDateTime(iso) {
  if (!iso) return "-"; const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-"; return d.toLocaleString("pt-BR");
}
function fmtTimeOnly(iso) {
  if (!iso) return "-"; const d = new Date(iso); if (Number.isNaN(d.getTime())) return "-"; return d.toLocaleTimeString("pt-BR");
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
  return addHours(item.updatedAt, 11);
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

function fillConfigForm(config) {
  const rules = config?.rules || {};
  if (cfgAlertaAmareloMin) cfgAlertaAmareloMin.value = rules.alertaAmareloMin ?? '';
  if (cfgAlertaVermelhoMin) cfgAlertaVermelhoMin.value = rules.alertaVermelhoMin ?? '';
  if (cfgAlertaPiscoMin) cfgAlertaPiscoMin.value = rules.alertaPiscoMin ?? '';
  if (cfgFechadoViraDesatualizadoHoras) cfgFechadoViraDesatualizadoHoras.value = rules.fechadoViraDesatualizadoHoras ?? '';
  if (cfgDesatualizadoCriticoHoras) cfgDesatualizadoCriticoHoras.value = rules.desatualizadoCriticoHoras ?? '';
  if (cfgPollingSeconds) cfgPollingSeconds.value = config?.pollingSeconds ?? '';
  syncConfigSummary();
}

function collectConfigPayload() {
  return {
    pollingSeconds: Number(cfgPollingSeconds?.value || 0),
    rules: {
      alertaAmareloMin: Number(cfgAlertaAmareloMin?.value || 0),
      alertaVermelhoMin: Number(cfgAlertaVermelhoMin?.value || 0),
      alertaPiscoMin: Number(cfgAlertaPiscoMin?.value || 0),
      fechadoViraDesatualizadoHoras: Number(cfgFechadoViraDesatualizadoHoras?.value || 0),
      desatualizadoCriticoHoras: Number(cfgDesatualizadoCriticoHoras?.value || 0),
    },
  };
}

function syncConfigSummary() {
  if (!configSummary) return;
  const payload = collectConfigPayload();
  const rules = payload.rules || {};
  configSummary.textContent = `Amarelo em ${rules.alertaAmareloMin || '-'} min, vermelho em ${rules.alertaVermelhoMin || '-'} min, pisco em ${rules.alertaPiscoMin || '-'} min. FECHADO vira DESATUALIZADO em ${rules.fechadoViraDesatualizadoHoras || '-'}h e CRÍTICO em ${rules.desatualizadoCriticoHoras || '-'}h. Atualização automática a cada ${payload.pollingSeconds || '-'}s.`;
}

function openConfigModal() {
  fillConfigForm(cfg || {});
  setConfigNotice('');

  if (configModalMeta) configModalMeta.textContent = 'Edite os tempos e confirme para aplicar.';
  setConfigModalHidden(false);
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
    fillConfigForm(cfg);
    setConfigNotice(data?.message || 'Configurações salvas com sucesso.', 'success');
    if (configModalMeta) configModalMeta.textContent = 'Configurações salvas com sucesso.';
    await load();
    startPolling();
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
function participantsHtml(list, extraClass = "") { const names = Array.isArray(list) ? list.filter(Boolean) : []; const cls = ["participantsList", extraClass].filter(Boolean).join(" "); if (!names.length) return `<div class="popoverEmpty">Nenhum participante informado</div>`; return `<ul class="${cls}">${names.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ul>`; }
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
  if (mode === 'inactive') return 'false';
  if (mode === 'trash') return 'all';
  return 'true';
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
      return raw;
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

  const recentRaw = raw.slice(-maxItems);
  const recentDays = days.slice(-maxItems);

  const normalized = recentRaw.map(normalizeDdsEntry);
  while (normalized.length < maxItems) normalized.unshift("neutral");
  while (recentDays.length < maxItems) recentDays.unshift("");

  const dots = normalized.map((status, idx) => {
    const isCurrent = idx === normalized.length - 1;
    const day = recentDays[idx];
    const statusText = ddsStatusLabel(status);
    const tooltip = day ? `${formatDdsFullDate(day)} • ${statusText}` : statusText;
    const dayLabel = formatDdsDayOnly(day);

    if (showDayLabels) {
      return `
        <span class="ddsDayDot" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
          <span class="ddsDayLabel">${escapeHtml(dayLabel || "–")}</span>
          <span class="ddsDotWrap${isCurrent ? " isCurrent" : ""}">
            <span class="ddsDot ddsDot--${status}${isCurrent ? " ddsDot--current" : ""}"></span>
          </span>
        </span>
      `;
    }

    return `
      <span class="ddsDotWrap${isCurrent ? " isCurrent" : ""}" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
        <span class="ddsDot ddsDot--${status}${isCurrent ? " ddsDot--current" : ""}"></span>
      </span>
    `;
  }).join("");

  const rowClass = ["ddsRow", containerClass, showDayLabels ? "ddsRowExpanded" : ""]
    .filter(Boolean)
    .join(" ");

  const trackClass = ["ddsTrack", showDayLabels ? "ddsTrackExpanded" : ""]
    .filter(Boolean)
    .join(" ");

  return `
    <div class="${rowClass}" aria-label="DDS últimos ${maxItems} dias">
      ${showMeta ? `
        <div class="ddsMeta">
          <span class="ddsLabel">${escapeHtml(label)}</span>
          <span class="ddsHint">${escapeHtml(hintText)}</span>
        </div>
      ` : ""}
      <div class="${trackClass}" role="list" aria-label="Histórico DDS últimos ${maxItems} dias">

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
  const participantes = participantsHtml(item.participantes, 'hoverParticipantsList');
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

  const badgeHtml = art66Active
    ? `<div class="critical art66Badge"><div class="art66Line1">ART 66</div>${isBeforeSeven ? '' : `<div class="art66Line2">até ${escapeHtml(art66EndLabel)}</div>`}</div>`
    : (crit ? `<div class="critical">CRÍTICO</div>` : ``);
  
  const unreadCount = Number(item.unreadMessages || 0);
  const messageIconHtml = unreadCount > 0
    ? `<div class="tileMessageIcon" title="${unreadCount} mensagens não lidas">
         <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="3">
           <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 1 1-7.6-11.8 8.38 8.38 0 0 1 3.8.9L21 3l-1.4 4.7a8.38 8.38 0 0 1 .9 3.8Z" stroke-linecap="round" stroke-linejoin="round"/>
         </svg>
       </div>`
    : "";

  const ddsRow = ddsSequenceHtml(item, { maxItems: 5, showDayLabels: false, showMeta: true, label: "DDS", hintText: "Últimas 5" });
 
  const isTrash = getViewMode() === 'trash';
  const trashActions = isTrash ? `
    <div class="tileTrashActions">
      <button class="btnRestore" title="Restaurar Equipe" onclick="event.stopPropagation(); window.restoreTeam('${escapeHtml(teamKey)}')">Restaurar</button>
      <button class="btnPermanentDelete" title="Excluir Permanentemente" onclick="event.stopPropagation(); window.deleteTeamPermanent('${escapeHtml(teamKey)}')">Excluir Permanente</button>
    </div>
  ` : '';

  return `<article class="tile ${stateCard} ${border} ${isTrash ? 'isTrashTile' : ''}" tabindex="0" role="button" data-team="${escapeHtml(teamKey)}" aria-label="Equipe ${escapeHtml(equipe)}, status ${escapeHtml(statusLabel)}">
    ${badgeHtml}
    ${messageIconHtml}
    <div class="tileMain">
      <div class="tileTopRow">
        <div class="tileIdentity">
          <div class="tileTitleBlock tileTitleBlockFull">
            <div class="teamIdentityBadge" title="${escapeHtml(equipe)}">
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
      ${isTrash ? trashActions : ddsRow}
    </div>
    ${isTrash ? '' : `
    <div class="tileHoverPanel" aria-hidden="true">
      <div class="tileHoverTop">
        <div class="tileHoverTitles">
          <div class="teamIdentityBadge teamIdentityBadgeHover" title="${escapeHtml(equipe)}">
            <div class="equipeCompact equipeCompactHover">${escapeHtml(equipe)}</div>
          </div>
          <div class="badge badgeCompact">${escapeHtml(stateLabel(shown))}</div>
        </div>
      </div>
      <div class="tileHoverBody">
        <div class="hoverRows">${details}</div>
        <div class="hoverSection">
          <div class="hoverSectionTitle">Presenças no DDS (Últimos 10 dias)</div>
          ${ddsSequenceHtml(item, { maxItems: 10, showDayLabels: true, showMeta: false, containerClass: "ddsRowHover" })}
        </div>
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
      (kpiFilter === "ALERTA" ? activeAlertFilter(it) : shown === kpiFilter);
    return matchesText && matchesTeam && matchesKpi;
  });
}

function renderKpis(items) {
  const counts = { ABERTO: 0, INTERVALO: 0, DESLOCAMENTO_ESPECIAL: 0, FECHADO: 0, DESATUALIZADO: 0, DESCONHECIDO: 0, ALERTA: 0 };
  (items || []).forEach((it) => {
    const st = normalizedState(it.estado);
    if (counts[st] !== undefined) counts[st]++;
    const alerta = safeUpper(it.alerta);
    if (alerta === "YELLOW" || alerta === "RED" || alerta === "PULSE") counts.ALERTA++;
  });
  kpis.innerHTML = `
    <button class="kpi kpiHintWrap" type="button" data-kpi="aberto" data-filter="ABERTO" aria-label="Filtrar equipes abertas" aria-pressed="false"><span class="kpiDot dotGreen"></span><span>${counts.ABERTO}</span><span class="kpiHint">Equipes em aberto</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="intervalo" data-filter="INTERVALO" aria-label="Filtrar equipes em intervalo" aria-pressed="false"><span class="kpiDot dotYellow"></span><span>${counts.INTERVALO}</span><span class="kpiHint">Equipes em intervalo</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="deslocamento" data-filter="DESLOCAMENTO_ESPECIAL" aria-label="Filtrar deslocamento especial" aria-pressed="false"><span class="kpiDot dotBlue"></span><span>${counts.DESLOCAMENTO_ESPECIAL}</span><span class="kpiHint">Deslocamento especial</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="fechado" data-filter="FECHADO" aria-label="Filtrar equipes fechadas" aria-pressed="false"><span class="kpiDot dotRed"></span><span>${counts.FECHADO}</span><span class="kpiHint">Equipes fechadas</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="desatualizado" data-filter="DESATUALIZADO" aria-label="Filtrar equipes desatualizadas" aria-pressed="false"><span class="kpiDot dotGray"></span><span>${counts.DESATUALIZADO}</span><span class="kpiHint">Equipes desatualizadas</span></button>
    <button class="kpi kpiHintWrap" type="button" data-kpi="alerta" data-filter="ALERTA" aria-label="Filtrar equipes em alerta" aria-pressed="false"><span class="kpiWarn">⚠</span><span>${counts.ALERTA}</span><span class="kpiHint">Alertas de atualização</span></button>`;
  syncKpiSelection();
}

function renderTeamCount(items) {
  if (teamCount) teamCount.textContent = `${getTeamCountLabel()}: ${Array.isArray(items) ? items.length : 0}`;
}
function findItem(teamKey) { return currentItems.find((item) => detailValue(item.teamKey || item.equipe) === teamKey) || null; }
function getEmpresaValue() { return (empresaInput.value || cfg?.defaultEmpresa || '').trim(); }

function syncHoverPlacement() {
  if (!grid) return;

  const gridRect = grid.getBoundingClientRect();
  const viewportLeft = Math.max(12, gridRect.left);
  const viewportRight = Math.min(window.innerWidth - 12, gridRect.right);

  grid.querySelectorAll('.tile').forEach((tileEl) => {
    tileEl.classList.remove('tileHoverShiftLeft');
    tileEl.classList.remove('tileHoverShiftRight');

    const tileRect = tileEl.getBoundingClientRect();
    const hoverWidth = Math.min((tileRect.width * 2) + 12, 420);

    const defaultLeft = tileRect.left - (hoverWidth * 0.25);
    const defaultRight = defaultLeft + hoverWidth;

    if (defaultRight > viewportRight) {
      tileEl.classList.add('tileHoverShiftLeft');
      return;
    }

    if (defaultLeft < viewportLeft) {
      tileEl.classList.add('tileHoverShiftRight');
    }
  });
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
    const selector = document.getElementById('setorSelector');
    return selector ? selector.value : (localStorage.getItem('dds_monitor_setor') || 'OFICINA');
  },
};

function startPolling() {
  if (pollingTimer) clearInterval(pollingTimer);
  const safeSeconds = Math.max(15, pollingSeconds);
  nextTickAtMs = Date.now() + safeSeconds * 1000;
  startCountdown();
  pollingTimer = setInterval(() => { load(); }, safeSeconds * 1000);
}

async function loadConfig() {
  const r = await fetch('/api/config', { cache: 'no-store' });
  cfg = await r.json();
  if (!empresaInput.value) empresaInput.value = cfg.defaultEmpresa || '';
  pollingSeconds = Number(cfg.pollingSeconds) || 600;
  fillConfigForm(cfg);
}

async function load(options = {}) {
  const { forceRefresh = false } = options || {};
  const empresa = getEmpresaValue();
  const qs = new URLSearchParams();
  if (empresa) qs.set('empresa', empresa);
  qs.set('active', getActiveFilterValue());
  
  const sectorSelector = document.getElementById('setorSelector');
  const selectedSector = sectorSelector ? sectorSelector.value : (localStorage.getItem('dds_monitor_setor') || 'OFICINA');
  if (selectedSector) qs.set('setor', selectedSector);

  if (forceRefresh) qs.set('refresh', 'manual');
  
  const mode = getViewMode();
  let url = `/api/turnos?${qs.toString()}`;
  if (mode === 'trash') {
    url = `/api/teams/trash`;
  }

  try {
    const r = await fetch(url, { cache: 'no-store' });
    const data = await r.json();
    
    // Se for lixeira, o formato é um mapa de equipes direto, não o objeto de turnos
    if (mode === 'trash') {
      const teamsMap = data || {};
      const items = Object.values(teamsMap).map(t => ({
        ...t,
        equipe: t.displayName || t.teamKey,
        estado: 'DESCONHECIDO'
      }));
      renderData(items, { empresa: '-', serverTime: new Date().toISOString() });
      return;
    }

    renderData(data.items || [], data);
  } catch (e) {
    console.error('Erro ao carregar monitor:', e);
    lastSync.textContent = 'Atualizado: ERRO';
    grid.innerHTML = '<div class="emptyState">Não foi possível carregar o monitor.</div>';
    if (kpis) kpis.innerHTML = `<div class="kpi">⚠ erro ao carregar</div>`;
    renderTeamCount([]);
  } finally {
    const safeSeconds = Math.max(15, pollingSeconds);
    nextTickAtMs = Date.now() + safeSeconds * 1000;
    setRefreshInfo();
  }
}

function renderData(items, meta) {
    if (empresaLabel) empresaLabel.textContent = meta.empresa || '-';
    lastSync.textContent = `Atualizado: ${fmtTimeOnly(meta.serverTime)}`;
    lastData = meta;
    
    syncTeamSelect(items);
    const filtered = applyFilters(items);
    currentItems = filtered;
    
    if (getViewMode() !== 'trash') {
        renderKpis(items);
        kpis.hidden = false;
    } else {
        kpis.hidden = true;
    }
    
    renderTeamCount(filtered);
    grid.innerHTML = filtered.length ? filtered.map(tile).join('') : `<div class="emptyState">Nenhuma equipe encontrada nesta visualização.</div>`;
    requestAnimationFrame(syncHoverPlacement);
    
    if (window.teamForm?.refreshOpenTeam) {
      const openTeamKey = window.teamForm.getOpenTeamKey?.();
      if (openTeamKey) window.teamForm.refreshOpenTeam(findItem(openTeamKey));
    }
    
    const globalMessagesBadge = document.getElementById('globalMessagesBadge');
    if (globalMessagesBadge) {
      const totalUnread = items.reduce((acc, it) => acc + (Number(it.unreadMessages) || 0), 0);
      globalMessagesBadge.textContent = totalUnread;
      globalMessagesBadge.hidden = totalUnread === 0;
    }
}

window.restoreTeam = async function(teamKey) {
  if (!confirm(`Deseja restaurar a equipe ${teamKey}?`)) return;
  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/trash`, { method: 'DELETE' });
    if (r.ok) await load();
    else alert('Erro ao restaurar equipe.');
  } catch (e) {
    console.error(e);
  }
};

window.deleteTeamPermanent = async function(teamKey) {
  if (!confirm(`ATENÇÃO: Deseja excluir PERMANENTEMENTE a equipe ${teamKey} e TODO o histórico dela? Esta ação não pode ser desfeita.`)) return;
  try {
    const r = await fetch(`/api/teams/${encodeURIComponent(teamKey)}/permanent`, { method: 'DELETE' });
    if (r.ok) await load();
    else alert('Erro ao excluir equipe.');
  } catch (e) {
    console.error(e);
  }
};

window.toggleTeamActive = async function(teamKey, active) {
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
window.openTrashConfirmation = async function(teamKey) {
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

searchInput.addEventListener('input', load);
teamSelect?.addEventListener('change', load);

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
  load();
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

const sectorSelector = document.getElementById('setorSelector');
if (sectorSelector) {
  const savedSector = localStorage.getItem('dds_monitor_setor');
  if (savedSector) sectorSelector.value = savedSector;
  sectorSelector.addEventListener('change', () => {
    localStorage.setItem('dds_monitor_setor', sectorSelector.value);
    load({ forceRefresh: true });
  });
}

(async () => {
  try {
    await loadConfig();
  } catch (error) {
    console.error('Erro ao carregar configuração do monitor:', error);
    cfg = cfg || { defaultEmpresa: empresaInput?.value || '', pollingSeconds, rules: {} };
  }
  await load();
  startPolling();
})();