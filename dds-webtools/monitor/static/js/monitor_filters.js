// -----------------------------------------------------------------------------
// Arquivo : static/js/monitor_filters.js
// Objetivo: Filtros operacionais, seleção de KPIs, busca por texto, filtro
//           por setor e cálculo de contadores de equipes do monitor.
// -----------------------------------------------------------------------------

let activeKpiFilter = "";

function getViewMode() {
  const mode = document.body?.dataset?.teamView;
  if (mode === 'inactive') return 'inactive';
  if (mode === 'trash') return 'trash';
  return 'active';
}

function getActiveFilterValue() {
  const mode = getViewMode();
  if (mode === 'trash') return 'all';
  return 'all';
}

function getTeamCountLabel() {
  const mode = getViewMode();
  if (mode === 'inactive') return 'Inativas';
  if (mode === 'trash') return 'Na Lixeira';
  return 'Equipes';
}

function getEmpresaValue() {
  const empresaInput = document.getElementById("empresaInput");
  const cfg = window.monitorState?.getConfig?.();
  return (empresaInput?.value || cfg?.defaultEmpresa || '').trim();
}

function normalizeKpiFilter(value) {
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const raw = sUpper(value);
  switch (raw) {
    case "ABERTO":
      return "ABERTO";
    case "INTERVALO":
      return "INTERVALO";
    case "FECHADO":
      return "FECHADO";
    case "DESATUALIZADO":
      return "DESATUALIZADO";
    case "ALERTA":
      return "ALERTA";
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
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const alerta = sUpper(item?.alerta);
  return alerta === "YELLOW" || alerta === "RED" || alerta === "PULSE";
}

function syncKpiSelection() {
  const kpis = document.getElementById("kpis");
  if (!kpis) return;
  const current = normalizeKpiFilter(activeKpiFilter);
  kpis.querySelectorAll(".kpi").forEach((chip) => {
    const chipFilter = normalizeKpiFilter(chip.dataset.filter || chip.dataset.kpi);
    const isActive = Boolean(current) && chipFilter === current;
    chip.classList.toggle("kpiFilterActive", isActive);
    chip.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function getItemTeamKey(item) {
  const dVal = window.monitorUtils?.detailValue || detailValue;
  return dVal(item.teamKey || item.equipe);
}

function getItemEquipe(item) {
  const dVal = window.monitorUtils?.detailValue || detailValue;
  return dVal(item.equipe || item.teamKey);
}

function buildTeamOptionLabel(item) {
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const equipe = getItemEquipe(item);
  const teamKey = getItemTeamKey(item);
  return sUpper(equipe) === sUpper(teamKey) ? equipe : `${equipe} — ${teamKey}`;
}

function syncTeamSelect(items) {
  const teamSelect = document.getElementById("teamSelect");
  if (!teamSelect) return;
  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
  const previous = teamSelect.value || '';
  const unique = new Map();
  (items || []).forEach((item) => {
    const key = getItemTeamKey(item);
    if (!key || key === '-') return;
    if (!unique.has(key)) unique.set(key, buildTeamOptionLabel(item));
  });
  const ordered = [...unique.entries()].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR', { sensitivity: 'base' }));
  teamSelect.innerHTML = `<option value="">Todas as equipes</option>${ordered.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join('')}`;
  if (previous && unique.has(previous)) teamSelect.value = previous;
}

function applyFilters(items) {
  const searchInput = document.getElementById("searchInput");
  const teamSelect = document.getElementById("teamSelect");
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const normState = window.monitorCards?.normalizedState || normalizedState;

  const q = sUpper(searchInput?.value);
  const selectedTeam = sUpper(teamSelect?.value);
  const kpiFilter = normalizeKpiFilter(activeKpiFilter);

  return (items || []).filter((it) => {
    const eq = sUpper(it.equipe);
    const teamKey = sUpper(it.teamKey || it.equipe);
    const shown = normState(it.estado);
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
  const kpis = document.getElementById("kpis");
  if (!kpis) return;
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const normState = window.monitorCards?.normalizedState || normalizedState;

  const counts = { ABERTO: 0, INTERVALO: 0, DESLOCAMENTO_ESPECIAL: 0, FECHADO: 0, DESATUALIZADO: 0, DESCONHECIDO: 0, ALERTA: 0 };
  let ddsOk = 0;
  let ddsTotal = 0;

  (items || []).forEach((it) => {
    const st = normState(it.estado);
    if (counts[st] !== undefined) counts[st]++;
    const alerta = sUpper(it.alerta);
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
  const teamCount = document.getElementById("teamCount");
  if (teamCount) teamCount.textContent = `${getTeamCountLabel()}: ${Array.isArray(items) ? items.length : 0}`;
}

function findItem(teamKey, itemsList) {
  const list = itemsList || window.monitorState?.getCurrentItems?.() || [];
  const dVal = window.monitorUtils?.detailValue || detailValue;
  return list.find((item) => dVal(item.teamKey || item.equipe) === teamKey) || null;
}

window.monitorFilters = {
  getViewMode,
  getActiveFilterValue,
  getTeamCountLabel,
  getEmpresaValue,
  normalizeKpiFilter,
  activeAlertFilter,
  syncKpiSelection,
  getItemTeamKey,
  getItemEquipe,
  buildTeamOptionLabel,
  syncTeamSelect,
  applyFilters,
  renderKpis,
  renderTeamCount,
  findItem,
  getActiveKpiFilter: () => activeKpiFilter,
  setActiveKpiFilter: (val) => { activeKpiFilter = val; },
};
