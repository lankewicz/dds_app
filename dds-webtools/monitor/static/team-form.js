// -----------------------------------------------------------------------------
// Arquivo : static/team-form.js
// Objetivo: Abrir, preencher e salvar o formulário modal da equipe usando os
//           endpoints /api/team-form, incluindo a edição estruturada dos
//           equipamentos vinculados, motivo obrigatório para alteração e
//           controle de estado limpo/sujo para o botão principal.
// -----------------------------------------------------------------------------

const teamFormModal = document.getElementById('teamFormModal');
const teamFormBackdrop = document.getElementById('teamFormBackdrop');
const teamFormClose = document.getElementById('teamFormClose');
const teamFormCancel = document.getElementById('teamFormCancel');
const teamFormSave = document.getElementById('teamFormSave');
const teamFormDeleteIcon = document.getElementById('teamFormDeleteIcon');
const teamFormToggleActiveBtn = document.getElementById('teamFormToggleActiveBtn');
const textToggleActive = document.getElementById('textToggleActive');
const iconEyeOpen = document.getElementById('iconEyeOpen');
const iconEyeClosed = document.getElementById('iconEyeClosed');
const teamFormNotice = document.getElementById('teamFormNotice');
const teamFormMeta = document.getElementById('teamFormMeta');
const teamFormVehicle = document.getElementById('teamFormVehicle');
const teamFormTitle = document.getElementById('teamFormTitle');
const teamFormSubtitle = document.getElementById('teamFormSubtitle');
const teamLiveStatus = document.getElementById('teamLiveStatus');
const teamLiveActivity = document.getElementById('teamLiveActivity');
const teamLiveService = document.getElementById('teamLiveService');
const teamLiveProtocol = document.getElementById('teamLiveProtocol');
const teamLiveSource = document.getElementById('teamLiveSource');
const teamLiveUpdatedAt = document.getElementById('teamLiveUpdatedAt');
const teamLiveAgo = document.getElementById('teamLiveAgo');
const teamLiveDds = document.getElementById('teamLiveDds');
const equipmentHistoryTableBody = document.getElementById('equipmentHistoryTableBody');

const teamChatHistory = document.getElementById('teamChatHistory');
const teamChatSendBtn = document.getElementById('teamChatSendBtn');
const teamChatMessageInput = document.getElementById('teamChatMessageInput');
const teamChatConcludeBtn = document.getElementById('teamChatConcludeBtn');
const teamChatPopover = document.getElementById('teamChatPopover');
const chatPopoverClose = document.getElementById('chatPopoverClose');
const chatPopoverTeamName = document.getElementById('chatPopoverTeamName');
const teamFormCommBtn = document.getElementById('teamFormCommBtn');

const equipmentCardTablet = document.getElementById('equipmentCardTablet');
const equipmentCardCameraCopel = document.getElementById('equipmentCardCameraCopel');
const equipmentCardCameraVeicular = document.getElementById('equipmentCardCameraVeicular');
const equipmentCardDds = document.getElementById('equipmentCardDds');
const equipmentSummaryTablet = document.getElementById('equipmentSummaryTablet');
const equipmentSummaryCameraCopel = document.getElementById('equipmentSummaryCameraCopel');
const equipmentSummaryCameraVeicular = document.getElementById('equipmentSummaryCameraVeicular');
const equipmentSummaryDds = document.getElementById('equipmentSummaryDds');

const ddsHistoryModal = document.getElementById('ddsHistoryModal');
const ddsHistoryModalBackdrop = document.getElementById('ddsHistoryModalBackdrop');
const ddsHistoryModalClose = document.getElementById('ddsHistoryModalClose');
const ddsHistoryModalCloseBtn = document.getElementById('ddsHistoryModalCloseBtn');
const ddsHistoryModalContent = document.getElementById('ddsHistoryModalContent');
const ddsHistoryModalTitle = document.getElementById('ddsHistoryModalTitle');
const ddsHistoryModalSubtitle = document.getElementById('ddsHistoryModalSubtitle');

const equipmentModal = document.getElementById('equipmentModal');
const equipmentModalBackdrop = document.getElementById('equipmentModalBackdrop');
const equipmentModalClose = document.getElementById('equipmentModalClose');
const equipmentModalCancel = document.getElementById('equipmentModalCancel');
const equipmentModalSave = document.getElementById('equipmentModalSave');
const equipmentModalImage = document.getElementById('equipmentModalImage');
const equipmentModalTitle = document.getElementById('equipmentModalTitle');
const equipmentModalSubtitle = document.getElementById('equipmentModalSubtitle');
const equipmentModalMeta = document.getElementById('equipmentModalMeta');
const equipmentPatrimonioField = document.getElementById('equipmentPatrimonioField');
const equipmentImeiField = document.getElementById('equipmentImeiField');
const equipmentPhoneField = document.getElementById('equipmentPhoneField');
const equipmentEmailField = document.getElementById('equipmentEmailField');
const equipmentFormNotice = document.getElementById('equipmentFormNotice');
const equipmentLastChangedAt = document.getElementById('equipmentLastChangedAt');
const equipmentLastChangeReason = document.getElementById('equipmentLastChangeReason');
const equipmentIdentifier = document.getElementById('equipmentIdentifier');
const equipmentIdentifierField = document.getElementById('equipmentIdentifierField');
const equipmentSerial = document.getElementById('equipmentSerial');
const equipmentPatrimonio = document.getElementById('equipmentPatrimonio');
const equipmentImei = document.getElementById('equipmentImei');
const equipmentPhone = document.getElementById('equipmentPhone');
const equipmentEmail = document.getElementById('equipmentEmail');
const equipmentChangeReason = document.getElementById('equipmentChangeReason');

const formTeamKey = document.getElementById('formTeamKey');
const formEmpresa = document.getElementById('formEmpresa');
const formDisplayName = document.getElementById('formDisplayName');
const formTeamType = document.getElementById('formTeamType');
const formMembers = document.getElementById('formMembers');
const formActive = document.getElementById('formActive');
const formEstado = document.getElementById('formEstado');
const formNocSs = document.getElementById('formNocSs');
const formMotivo = document.getElementById('formMotivo');
const formHoraEntrada = document.getElementById('formHoraEntrada');
const formHoraSaida = document.getElementById('formHoraSaida');
const formObservacoes = document.getElementById('formObservacoes');

const EQUIPMENT_META = {
  tablet: {
    label: 'Tablet',
    image: '/static/img/tablet.svg',
    summaryEl: equipmentSummaryTablet,
    supportsPatrimonio: true,
    supportsImei: true,
    supportsPhoneNumber: true,
    supportsEmail: true,
    supportsIdentifier: true,
  },
  cameraCopel: {
    label: 'Câmera Copel',
    image: '/static/img/camera-corporal.svg',
    summaryEl: equipmentSummaryCameraCopel,
    supportsPatrimonio: true,
    supportsImei: false,
    supportsPhoneNumber: false,
    supportsEmail: false,
  },
  cameraVeicular: {
    label: 'Câmera veicular',
    image: '/static/img/camera-veicular.svg',
    summaryEl: equipmentSummaryCameraVeicular,
    supportsPatrimonio: false,
    supportsImei: true,
    supportsPhoneNumber: true,
    supportsEmail: false,
  },
};

let loadToken = 0;
let saveInFlight = false;
let openEquipmentType = null;
let equipmentState = buildEmptyEquipmentMap();
let equipmentHistory = [];
let savedFormSignature = '';
let currentDirty = false;
let suspendDirtyTracking = false;
let equipmentEditorBaseline = null;
let equipmentModalDirty = false;
let openTeamKey = null;
let currentThreadId = null;
let currentSubject = "Comunicação Equipe";

function escapeHtml(value) {
  return (value ?? "").toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function utils() { return window.monitorUtils || {}; }
function state() { return window.monitorState || {}; }
function detailValue(value) { return utils().detailValue ? utils().detailValue(value) : ((value ?? '').toString().trim() || '-'); }
function fmtDateTime(value) { return utils().fmtDateTime ? utils().fmtDateTime(value) : detailValue(value); }
function fmtAgeFromMinutes(value) { return utils().fmtAgeFromMinutes ? utils().fmtAgeFromMinutes(value) : detailValue(value); }
function stateLabel(value) { return utils().stateLabel ? utils().stateLabel(value) : detailValue(value); }
function vehicleFrameClass(value) { return utils().vehicleFrameClass ? utils().vehicleFrameClass(value) : 'vfGray'; }

function normalizeMembersText(value) {
  return (value || '')
    .split(/\r?\n|,|;/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, list) => list.findIndex((x) => x.toLowerCase() === item.toLowerCase()) === index);
}

function createMemberRowHtml(name = "", isDriver = false, isCoringa = false) {
  return `
    <div class="memberRow" style="display: flex; align-items: center; gap: 8px; width: 100%;">
      <input type="text" class="memberInput" value="${escapeHtml(name)}" placeholder="Nome do integrante" style="flex: 1; background: rgba(255, 255, 255, .06); border: 1px solid rgba(255, 255, 255, .10); color: #fff; border-radius: 14px; padding: 11px 12px; outline: none; font-size: 14px;">
      
      <button type="button" class="btnDriverToggle ${isDriver ? 'active' : ''}" title="Motorista" style="background: transparent; border: none; cursor: pointer; padding: 6px; color: ${isDriver ? '#2196F3' : 'rgba(255,255,255,0.35)'}; display: flex; align-items: center; transition: color 0.2s;" onclick="toggleRowDriver(this)">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M12,2C6.5,2 2,6.5 2,12C2,17.5 6.5,22 12,22C17.5,22 22,17.5 22,12C22,6.5 17.5,2 12,2M12,4C15.8,4 19,6.9 19.8,10.5H16.2C15.6,9 14,8 12,8C10,8 8.4,9 7.8,10.5H4.2C5,6.9 8.2,4 12,4M4.2,13.5H7.8C8.4,15 10,16 12,16C14,16 15.6,15 16.2,13.5H19.8C19,17.1 15.8,20 12,20C8.2,20 5,17.1 4.2,13.5Z"/></svg>
      </button>
      
      <button type="button" class="btnCoringaToggle ${isCoringa ? 'active' : ''}" title="Coringa" style="background: transparent; border: none; cursor: pointer; padding: 6px; color: ${isCoringa ? '#4CAF50' : 'rgba(255,255,255,0.35)'}; display: flex; align-items: center; transition: color 0.2s;" onclick="toggleRowCoringa(this)">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M17,20A3,3 0 0,0 20,17A3,3 0 0,0 17,14A3,3 0 0,0 14,17A3,3 0 0,0 17,20M7,12A3,3 0 0,0 10,9A3,3 0 0,0 7,6A3,3 0 0,0 4,9A3,3 0 0,0 7,12M17,22H7C4.67,22 2,20.83 2,18.5V18H22V18.5C22,20.83 19.33,22 17,22M17,12A1,1 0 0,0 18,11V9H21L17,5L13,9H16V11A1,1 0 0,0 17,12M7,4A1,1 0 0,0 6,5V7H3L7,11L11,7H8V5A1,1 0 0,0 7,4Z"/></svg>
      </button>
      
      <button type="button" class="btnRemoveMember" title="Remover" style="background: transparent; border: none; cursor: pointer; padding: 6px; color: rgba(244,67,54,0.7); display: flex; align-items: center; transition: color 0.2s;" onclick="removeMemberRow(this)">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>
      </button>
    </div>
  `;
}

window.toggleRowDriver = function(btn) {
  const row = btn.closest(".memberRow");
  const container = row.parentElement;
  const isActive = btn.classList.contains("active");
  
  container.querySelectorAll(".btnDriverToggle").forEach(b => {
    b.classList.remove("active");
    b.style.color = "rgba(255,255,255,0.35)";
  });
  
  if (!isActive) {
    btn.classList.add("active");
    btn.style.color = "#2196F3";
  }
  updateDirtyState();
};

window.toggleRowCoringa = function(btn) {
  const isActive = btn.classList.contains("active");
  if (isActive) {
    btn.classList.remove("active");
    btn.style.color = "rgba(255,255,255,0.35)";
  } else {
    btn.classList.add("active");
    btn.style.color = "#4CAF50";
  }
  updateDirtyState();
};

window.removeMemberRow = function(btn) {
  const row = btn.closest(".memberRow");
  row.remove();
  updateDirtyState();
};

window.addMemberRow = function(name = "", isDriver = false, isCoringa = false) {
  const container = document.getElementById("membersContainer");
  if (!container) return;
  
  const div = document.createElement("div");
  div.innerHTML = createMemberRowHtml(name, isDriver, isCoringa).trim();
  const row = div.firstChild;
  container.appendChild(row);
  
  const input = row.querySelector(".memberInput");
  input.addEventListener("input", updateDirtyState);
  
  updateDirtyState();
};

function setModalHidden(hidden) {
  if (!teamFormModal) return;
  teamFormModal.hidden = hidden;
  syncBodyModalState();
}

function setEquipmentModalHidden(hidden) {
  if (!equipmentModal) return;
  equipmentModal.hidden = hidden;
  if (hidden) {
    openEquipmentType = null;
    equipmentEditorBaseline = null;
    setEquipmentFormNotice('');
  }
  syncBodyModalState();
}

function syncBodyModalState() {
  const hasOpenModal = Boolean(teamFormModal && !teamFormModal.hidden) || Boolean(equipmentModal && !equipmentModal.hidden);
  document.body.classList.toggle('modalOpen', hasOpenModal);
}

function setBusy(isBusy, message = '') {
  if (teamFormSave) {
    teamFormSave.disabled = isBusy;
    teamFormSave.textContent = isBusy ? 'Salvando...' : (currentDirty ? 'Salvar' : 'Fechar');
  }
  if (teamFormCancel) teamFormCancel.disabled = isBusy;
  if (teamFormClose) teamFormClose.disabled = isBusy;
  if (message) teamFormMeta.textContent = message;
}

function setNotice(message = '', kind = 'info') {
  if (!teamFormNotice) return;
  if (!message) {
    teamFormNotice.hidden = true;
    teamFormNotice.textContent = '';
    teamFormNotice.className = 'formNotice';
    return;
  }
  teamFormNotice.hidden = false;
  teamFormNotice.textContent = message;
  teamFormNotice.className = `formNotice ${kind}`;
}

function setEquipmentFormNotice(message = '', kind = 'info') {
  if (!equipmentFormNotice) return;
  if (!message) {
    equipmentFormNotice.hidden = true;
    equipmentFormNotice.textContent = '';
    equipmentFormNotice.className = 'formNotice';
    return;
  }
  equipmentFormNotice.hidden = false;
  equipmentFormNotice.textContent = message;
  equipmentFormNotice.className = `formNotice ${kind}`;
}

function updateHeader(item, teamKey) {
  const frameCls = vehicleFrameClass(item?.estado);
  const teamTypeLabels = {
    'STC': 'STC',
    'STC_CESTO': 'STC - CESTO',
    'EP': 'EP (Manutenção)',
    'LINHA_VIVA': 'Linha Viva',
    'ROCADA': 'Roçada',
    'CONSTRUCAO': 'Construção'
  };
  const typeLabel = item?.teamType ? (teamTypeLabels[item.teamType] || item.teamType) : '';
  const typeSuffix = typeLabel ? ` - ${typeLabel}` : '';
  const titleText = (item?.equipe && item.equipe !== teamKey ? `${item.equipe} (${teamKey})` : (item?.equipe || teamKey || 'Equipe')) + typeSuffix;
  const empresa = state().getEmpresa ? state().getEmpresa() : '';
  
  const typeIcons = {
    'STC': '/static/img/stc_small.jpg',
    'STC_CESTO': '/static/img/stc_cesto_small.jpg',
    'LINHA_VIVA': '/static/img/linha_viva_small.jpg',
    'ROCADA': '/static/img/rocada_small.jpg',
    'CONSTRUCAO': '/static/img/construcao_small.jpg',
    'EP': '/static/img/ep_small.jpg'
  };

  teamFormVehicle.className = `modalVehicle ${frameCls}`;
  teamFormVehicle.style.fontSize = '';
  teamFormVehicle.innerHTML = '';
  
  if (item?.teamType) {
    if (typeIcons[item.teamType]) {
      teamFormVehicle.innerHTML = `<img src="${typeIcons[item.teamType]}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 14px;" alt="${item.teamType}" />`;
    } else {
      teamFormVehicle.textContent = '🚫';
      teamFormVehicle.style.fontSize = '24px';
    }
  } else {
    teamFormVehicle.textContent = '🚫';
    teamFormVehicle.style.fontSize = '24px';
  }

  teamFormTitle.textContent = titleText;
  teamFormSubtitle.textContent = empresa ? `Empresa ${empresa}` : 'Cadastro e situação atual do turno';
}

function normalizeOperationalProtocol(...candidates) {
  for (const candidate of candidates) {
    const raw = String(candidate || '').trim();
    const commercial = raw.match(/(?:^|\D)(202\d{11})(?:\D|$)/);
    if (commercial) return commercial[1];
    const normalized = raw.replace(/\.\d+(?:\.\d+)?$/, '');
    if (/^\d{7,8}$/.test(normalized)) return normalized;
  }
  return '';
}

function latestOperationalCommunicationAt(item) {
  const snapshot = item?.rotalogSnapshot || {};
  const candidates = [item?.operacional?.atualizadoEm, snapshot.updatedAtIso, snapshot.eventTimestampMs];
  let latestMs = null;
  for (const value of candidates) {
    if (value === null || value === undefined || value === '') continue;
    let parsedMs;
    if (typeof value === 'number' || /^\d+$/.test(String(value).trim())) {
      const numeric = Number(value);
      parsedMs = numeric > 100000000000 ? numeric : numeric * 1000;
    } else {
      parsedMs = new Date(value).getTime();
    }
    if (Number.isFinite(parsedMs) && (latestMs === null || parsedMs > latestMs)) latestMs = parsedMs;
  }
  return latestMs === null ? null : new Date(latestMs).toISOString();
}
function getOperationalRotalogData(item) {
  const snapshot = item?.rotalogSnapshot || {};
  const inProgress = Array.isArray(snapshot.ssEmAndamento) ? snapshot.ssEmAndamento : [];
  const completed = Array.isArray(snapshot.ssExecutadas) ? snapshot.ssExecutadas : [];
  const service = snapshot.atividadeAtual || inProgress[0] || completed[completed.length - 1] || null;
  const activity = service?.status
    || snapshot.estadoConsolidado
    || '-';
  const category = String(service?.categoria || '').trim();
  const type = String(service?.tipo || service?.descricao || service?.nome || '').trim();
  const serviceLabel = [category, type]
    .filter((value, index, values) => value && values.indexOf(value) === index)
    .join(' · ');
  const protocol = normalizeOperationalProtocol(
    service?.protocolo,
    service?.protocoloBruto,
    service?.ssId,
  );
  const updatedAt = latestOperationalCommunicationAt(item);
  const updatedMs = updatedAt ? Date.parse(updatedAt) : NaN;
  const ageMinutes = Number.isFinite(updatedMs)
    ? Math.max(0, Math.floor((Date.now() - updatedMs) / 60000))
    : item?.minutosDesdeAtualizacao;
  const fromRotalog = Boolean(item?.rotalogSnapshot);
  return {
    status: item?.operacional?.estado || snapshot.estadoConsolidado || '-',
    activity,
    serviceLabel: serviceLabel || 'Nenhum serviço em andamento',
    protocol: protocol || '-',
    updatedAt,
    ageMinutes,
    source: fromRotalog ? 'ROTALOG' : 'DDS',
  };
}

function operationalActivityLabel(value) {
  const raw = String(value || '-').trim().toUpperCase();
  if (raw === 'DESLOCAMENTO') return 'DESLOCAMENTO';
  if (raw === 'EXECUCAO') return 'EXECUÇÃO';
  if (raw === 'CONCLUSAO') return 'CONCLUSÃO';
  return stateLabel(raw);
}
function fmtTimeStr(value) {
  if (!value) return '';
  const s = String(value).trim();
  const m = s.match(/(\d{2}:\d{2})/);
  return m ? m[1] : '';
}

function parseToDate(isoOrTime) {
  if (!isoOrTime) return null;
  const s = String(isoOrTime).trim();
  if (s.includes('T')) {
    const d = new Date(s);
    if (!isNaN(d.getTime())) return d;
  }
  const m = s.match(/(\d{1,2}):(\d{2})/);
  if (m) {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(m[1], 10), parseInt(m[2], 10), 0);
  }
  return null;
}

function getDiffMinutes(startIso, endIso) {
  const d1 = parseToDate(startIso);
  const d2 = parseToDate(endIso);
  if (!d1 || !d2) return null;
  const diffMs = d2.getTime() - d1.getTime();
  if (diffMs <= 0) {
    return 0;
  }
  return Math.max(0, Math.round(diffMs / 60000));
}

function fmtRelMinutes(mins) {
  if (mins === null || mins === undefined || isNaN(mins)) return '';
  if (mins < 0) return '0m';
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function fmtHMS(totalMinutes) {
  if (!Number.isFinite(totalMinutes) || totalMinutes < 0) totalMinutes = 0;
  const totalSeconds = Math.round(totalMinutes * 60);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function fmtHM(totalMinutes) {
  if (!Number.isFinite(totalMinutes) || totalMinutes < 0) totalMinutes = 0;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.floor(totalMinutes % 60);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

function extractTeamServices(item) {
  if (!item) return [];
  const snapshot = item.rotalogSnapshot || item;
  
  // 1. Serviços regulares
  let rawServices = [];
  if (Array.isArray(snapshot.services) && snapshot.services.length > 0) {
    rawServices = snapshot.services.map(s => ({ ...s }));
  } else {
    const executadas = Array.isArray(snapshot.ssExecutadas) ? snapshot.ssExecutadas : [];
    const emAndamento = Array.isArray(snapshot.ssEmAndamento)
      ? snapshot.ssEmAndamento
      : (snapshot.atividadeAtual && snapshot.atividadeAtual.tipo ? [snapshot.atividadeAtual] : []);
    rawServices = [...executadas, ...emAndamento].filter(Boolean).map(s => ({ ...s }));
  }

  // Identificar serviços regulares vs Relocados vs Retirados pelo COD
  const services = rawServices.map(s => {
    const isRunning = ['EXECUCAO', 'DESLOCAMENTO'].includes(String(s.statusAtual || s.status || '').toUpperCase());
    const durExec = (s.inicioExecucao && (s.fimExecucao || s.termino))
      ? getDiffMinutes(s.inicioExecucao, s.fimExecucao || s.termino)
      : null;
    
    const statusUpper = String(s.statusAtual || s.status || s.semExecucaoType || '').toUpperCase();
    const isRelocado = statusUpper.includes('RELOC');
    const isRetiradoCod = statusUpper.includes('RETIRADO') || statusUpper.includes('REDIR');
    const isSpecialRedirect = isRelocado || isRetiradoCod || (!isRunning && Boolean(s.inicioDeslocamento) && (!s.inicioExecucao || durExec === 0 || durExec === null));

    let displayTipo = s.tipo;
    let displayCat = s.categoria;
    let semExecType = null;

    if (isRelocado) {
      displayTipo = s.tipo ? `${s.tipo} (RELOCADO)` : 'RELOCADO';
      displayCat = 'RELOCADO';
      semExecType = 'RELOCADO';
    } else if (isRetiradoCod || isSpecialRedirect) {
      displayTipo = s.tipo ? `${s.tipo} (RETIRADO COD)` : 'RETIRADO PELO COD';
      displayCat = 'RETIRADO PELO COD';
      semExecType = 'RETIRADO PELO COD';
    }

    return {
      ...s,
      isInterval: false,
      isGap: false,
      isRedirected: isSpecialRedirect,
      semExecucaoType: semExecType,
      tipo: displayTipo,
      categoria: displayCat,
    };
  });

  // 2. Intervalos de Refeição / Pausa do Turno
  const turno = snapshot.turno || {};
  const rawIntervalos = Array.isArray(turno.intervalos) ? turno.intervalos : (Array.isArray(snapshot.intervalos) ? snapshot.intervalos : []);
  if (rawIntervalos.length === 0 && snapshot.intervalo && (snapshot.intervalo.inicio_iso || snapshot.intervalo.inicioIso || snapshot.intervalo.inicio || snapshot.intervalo.inicio_ms)) {
    rawIntervalos.push(snapshot.intervalo);
  }

  const isEmIntervalo = String(snapshot.turnStatus || snapshot.estadoConsolidado || snapshot.estado || (snapshot.current && snapshot.current.turnStatus) || '').toUpperCase() === 'INTERVALO';

  const intervalEvents = rawIntervalos.map((it, idx) => {
    let inicio = it.inicio || it.inicio_iso || it.inicioIso;
    let fim = it.fim || it.fim_iso || it.fimIso;
    if (!inicio && it.inicio_ms) {
      inicio = new Date(Number(it.inicio_ms)).toISOString();
    }
    if (!fim && it.fim_ms) {
      fim = new Date(Number(it.fim_ms)).toISOString();
    }
    const isCurrent = !fim && isEmIntervalo;
    return {
      isInterval: true,
      isGap: false,
      isRedirected: false,
      tipo: 'INTERVALO',
      categoria: 'REFEIÇÃO',
      protocolo: null,
      inicioDeslocamento: null,
      inicioExecucao: inicio,
      fimExecucao: fim,
      statusAtual: isCurrent ? 'EXECUCAO' : 'CONCLUSAO',
      sequencia: null,
      serviceId: `interval_${idx}_${inicio || ''}`,
    };
  }).filter(it => Boolean(it.inicioExecucao));

  // 3. Detecção de GAPs >= 5 minutos entre eventos
  const allChronological = [...services, ...intervalEvents].filter(e => Boolean(e.inicioDeslocamento || e.inicioExecucao)).sort((a, b) => {
    const tA = a.inicioDeslocamento || a.inicioExecucao || '';
    const tB = b.inicioDeslocamento || b.inicioExecucao || '';
    return tA.localeCompare(tB);
  });

  const gapEvents = [];
  const GAP_THRESHOLD_MINUTES = 5;

  for (let i = 0; i < allChronological.length - 1; i++) {
    const current = allChronological[i];
    const next = allChronological[i + 1];

    const fimCurrent = current.fimExecucao || current.termino || current.retorno || current.inicioExecucao;
    const inicioNext = next.inicioDeslocamento || next.inicioExecucao;

    if (fimCurrent && inicioNext) {
      const gapMins = getDiffMinutes(fimCurrent, inicioNext);
      if (gapMins >= GAP_THRESHOLD_MINUTES && gapMins <= 480) {
        // Verificar se esse gap já está coberto por algum intervalo de refeição
        const isCoveredByInterval = intervalEvents.some(it => {
          const itIni = it.inicioExecucao;
          const itFim = it.fimExecucao;
          if (!itIni || !itFim) return false;
          return itIni <= fimCurrent && itFim >= inicioNext;
        });

        if (!isCoveredByInterval) {
          const fila = current.filaNaConclusao || {};
          const hasQueue = (Number(fila.emergencia || 0) > 0 || Number(fila.comercial || 0) > 0);
          const gapType = hasQueue ? 'SEM_PRODUCAO' : 'SEM_SERVICO';

          gapEvents.push({
            isInterval: false,
            isGap: true,
            isRedirected: false,
            gapType: gapType,
            semExecucaoType: gapType,
            tipo: hasQueue ? 'SEM PRODUÇÃO' : 'SEM SERVIÇO',
            categoria: hasQueue ? 'DEMORA P/ INICIAR OS' : 'AGUARDANDO DESPACHO',
            protocolo: hasQueue ? `Fila disponível (${fila.emergencia || 0} emerg, ${fila.comercial || 0} com)` : 'Fila zerada (sem OS atribuída)',
            inicioDeslocamento: null,
            inicioExecucao: fimCurrent,
            fimExecucao: inicioNext,
            durMin: gapMins,
            statusAtual: 'CONCLUSAO',
            sequencia: null,
            serviceId: `gap_${i}_${fimCurrent}`,
          });
        }
      }
    }
  }

  // Gap do início do turno até o primeiro evento
  const turnoInicio = turno.inicio;
  if (turnoInicio && allChronological.length > 0) {
    const primeiroEvento = allChronological[0];
    const inicioPrimeiro = primeiroEvento.inicioDeslocamento || primeiroEvento.inicioExecucao;
    if (inicioPrimeiro) {
      const gapInicialMins = getDiffMinutes(turnoInicio, inicioPrimeiro);
      if (gapInicialMins >= GAP_THRESHOLD_MINUTES && gapInicialMins <= 480) {
        gapEvents.push({
          isInterval: false,
          isGap: true,
          isRedirected: false,
          gapType: 'SEM_SERVICO',
          semExecucaoType: 'SEM_SERVICO',
          tipo: 'SEM SERVIÇO',
          categoria: 'INÍCIO DE TURNO / AGUARDANDO',
          protocolo: 'Aguardando primeiro despacho',
          inicioDeslocamento: null,
          inicioExecucao: turnoInicio,
          fimExecucao: inicioPrimeiro,
          durMin: gapInicialMins,
          statusAtual: 'CONCLUSAO',
          sequencia: null,
          serviceId: `gap_init_${turnoInicio}`,
        });
      }
    }
  }

  return [...services, ...intervalEvents, ...gapEvents];
}

function renderTeamTimeline(item) {
  const container = document.getElementById('teamTimelineList');
  const countBadge = document.getElementById('teamTimelineCount');
  const summaryBox = document.getElementById('teamTimelineSummaryBox');
  if (!container) return;

  const events = extractTeamServices(item);
  if (!events || events.length === 0) {
    container.innerHTML = '<div class="popoverEmpty">Nenhum atendimento registrado hoje</div>';
    if (countBadge) countBadge.textContent = '0 serviços';
    if (summaryBox) summaryBox.innerHTML = '';
    return;
  }

  const snapshot = (item && item.rotalogSnapshot) || item || {};
  const turno = snapshot.turno || {};

  const servicesOnly = events.filter(e => !e.isInterval && !e.isGap);
  const concluidosProdutivosCount = servicesOnly.filter(s => !s.isRedirected && String(s.statusAtual || s.status || '').toUpperCase() === 'CONCLUSAO').length;
  const redirecionadosCount = servicesOnly.filter(s => s.isRedirected).length;
  const andamentoCount = servicesOnly.filter(s => {
    const st = String(s.statusAtual || s.status || '').toUpperCase();
    return st === 'EXECUCAO' || st === 'DESLOCAMENTO';
  }).length;
  const intervalosCount = events.filter(e => e.isInterval).length;

  let totalDeslocMin = 0;
  let totalExecMin = 0;
  let totalIntervalMin = 0;
  let totalRedirecionadoMin = 0;
  let totalSemServicoMin = 0;
  let totalSemProducaoMin = 0;

  servicesOnly.forEach(s => {
    if (s.isRedirected) {
      // Tempo de deslocamento do serviço cancelado vai para Redirecionado
      const d = (s.inicioDeslocamento && (s.fimExecucao || s.inicioExecucao || s.termino))
        ? getDiffMinutes(s.inicioDeslocamento, s.fimExecucao || s.inicioExecucao || s.termino)
        : null;
      if (d && d > 0) totalRedirecionadoMin += d;
    } else {
      if (s.inicioDeslocamento && s.inicioExecucao) {
        const d = getDiffMinutes(s.inicioDeslocamento, s.inicioExecucao);
        if (d && d > 0) totalDeslocMin += d;
      }
      if (s.inicioExecucao) {
        const isRunning = ['EXECUCAO', 'DESLOCAMENTO'].includes(String(s.statusAtual || s.status || '').toUpperCase());
        const fim = s.fimExecucao || s.termino || (isRunning ? new Date().toISOString() : null);
        if (fim) {
          const e = getDiffMinutes(s.inicioExecucao, fim);
          if (e && e > 0) totalExecMin += e;
        }
      }
    }
  });

  events.filter(e => e.isInterval).forEach(it => {
    if (it.inicioExecucao) {
      const isRunning = it.statusAtual === 'EXECUCAO';
      const fim = it.fimExecucao || (isRunning ? new Date().toISOString() : null);
      if (fim) {
        const dur = getDiffMinutes(it.inicioExecucao, fim);
        if (dur && dur > 0) totalIntervalMin += dur;
      }
    }
  });

  events.filter(e => e.isGap).forEach(gap => {
    const dur = gap.durMin || (gap.inicioExecucao && gap.fimExecucao ? getDiffMinutes(gap.inicioExecucao, gap.fimExecucao) : 0);
    if (dur > 0) {
      if (gap.gapType === 'SEM_PRODUCAO') totalSemProducaoMin += dur;
      else totalSemServicoMin += dur;
    }
  });

  const totalSemExecucaoMin = totalRedirecionadoMin + totalSemServicoMin + totalSemProducaoMin;

  // Renderizar Box Completo de Indicadores Operacionais
  if (summaryBox) {
    summaryBox.innerHTML = `
      <div class="timelineSummaryGrid">
        <div class="timelineSummaryStatCard timelineSummaryStatCard--services" title="Total de atendimentos concluídos no dia">
          <div class="summaryStatIconWrap">📋</div>
          <div class="summaryStatData">
            <span class="summaryStatValue">${concluidosProdutivosCount} <small>concluído${concluidosProdutivosCount !== 1 ? 's' : ''}${andamentoCount > 0 ? ` · ${andamentoCount} atual` : ''}${redirecionadosCount > 0 ? ` · ${redirecionadosCount} redir` : ''}</small></span>
            <span class="summaryStatLabel">Serviços concluídos</span>
          </div>
        </div>

        <div class="timelineSummaryStatCard timelineSummaryStatCard--desloc" title="Tempo total gasto em deslocamento produtivo">
          <div class="summaryStatIconWrap">🚗</div>
          <div class="summaryStatData">
            <span class="summaryStatValue">${fmtHMS(totalDeslocMin)}</span>
            <span class="summaryStatLabel">Deslocamento</span>
          </div>
        </div>

        <div class="timelineSummaryStatCard timelineSummaryStatCard--exec" title="Tempo total em execução das ordens de serviço">
          <div class="summaryStatIconWrap">⚡</div>
          <div class="summaryStatData">
            <span class="summaryStatValue">${fmtHMS(totalExecMin)}</span>
            <span class="summaryStatLabel">Execução</span>
          </div>
        </div>

        <div class="timelineSummaryStatCard timelineSummaryStatCard--semexec" title="Tempo total sem atendimento (Redirecionado + Sem Serviço + Sem Produção)">
          <div class="summaryStatIconWrap">⏳</div>
          <div class="summaryStatData">
            <span class="summaryStatValue">${fmtHMS(totalSemExecucaoMin)}</span>
            <span class="summaryStatLabel">Sem Execução Total</span>
            <div class="summaryStatSubBreakdown">
              <span title="Redirecionado (deslocamento abortado por emergência)">🔀 ${fmtHM(totalRedirecionadoMin)}</span>
              <span title="Sem Serviço (fila zerada / aguardando despacho)">🟡 ${fmtHM(totalSemServicoMin)}</span>
              <span title="Sem Produção (fila disponível / demora p/ iniciar)">🔴 ${fmtHM(totalSemProducaoMin)}</span>
            </div>
          </div>
        </div>

        <div class="timelineSummaryStatCard timelineSummaryStatCard--interval" title="Pausas e intervalos de refeição">
          <div class="summaryStatIconWrap">☕</div>
          <div class="summaryStatData">
            <span class="summaryStatValue">${fmtHM(totalIntervalMin)}</span>
            <span class="summaryStatLabel">${intervalosCount} intervalo${intervalosCount !== 1 ? 's' : ''}</span>
          </div>
        </div>
      </div>
    `;
  }

  // Ordenar do mais recente (em cima) para o mais antigo (embaixo)
  const orderedEvents = [...events].sort((a, b) => {
    const aRunning = ['EXECUCAO', 'DESLOCAMENTO'].includes(String(a.statusAtual || a.status || '').toUpperCase());
    const bRunning = ['EXECUCAO', 'DESLOCAMENTO'].includes(String(b.statusAtual || b.status || '').toUpperCase());
    if (aRunning && !bRunning) return -1;
    if (!aRunning && bRunning) return 1;

    const timeA = a.fimExecucao || a.inicioExecucao || a.inicioDeslocamento || '';
    const timeB = b.fimExecucao || b.inicioExecucao || b.inicioDeslocamento || '';
    return timeB.localeCompare(timeA);
  });

  let html = '<div class="teamTimelineItems">';
  orderedEvents.forEach((srv, idx) => {
    const status = String(srv.statusAtual || srv.status || 'CONCLUSAO').toUpperCase();
    const isRunning = status === 'EXECUCAO' || status === 'DESLOCAMENTO';
    const isInterval = Boolean(srv.isInterval);
    const isGap = Boolean(srv.isGap);
    const isRedirected = Boolean(srv.isRedirected);

    const tipo = srv.tipo || (isInterval ? 'INTERVALO' : (isGap ? srv.tipo : (srv.serviceType || 'SS')));
    const categoria = srv.categoria || (isInterval ? 'REFEIÇÃO' : (srv.tipo === 'COMERCIAL' ? 'COMERCIAL' : 'EMERGÊNCIA'));
    const isEmergencia = String(categoria).toUpperCase().includes('EMERG');
    const protocolo = srv.protocolo || srv.protocol || srv.ssId || '-';
    
    let seq = srv.sequencia;
    if (!seq) {
      if (isInterval) seq = '☕';
      else if (isRedirected) seq = '🔀';
      else if (isGap) seq = (srv.gapType === 'SEM_PRODUCAO' ? '🔴' : '🟡');
      else seq = (orderedEvents.length - idx);
    }

    const desloc = fmtTimeStr(srv.inicioDeslocamento);
    const inicio = fmtTimeStr(srv.inicioExecucao || srv.inicioIso);
    const fim = fmtTimeStr(srv.fimExecucao || srv.termino || srv.fimIso);

    const durDesloc = (srv.inicioDeslocamento && srv.inicioExecucao)
      ? getDiffMinutes(srv.inicioDeslocamento, srv.inicioExecucao)
      : (isRedirected && srv.inicioDeslocamento && (srv.fimExecucao || srv.termino) ? getDiffMinutes(srv.inicioDeslocamento, srv.fimExecucao || srv.termino) : null);

    const durExec = (srv.inicioExecucao && (srv.fimExecucao || srv.termino))
      ? getDiffMinutes(srv.inicioExecucao, srv.fimExecucao || srv.termino)
      : (isRunning && srv.inicioExecucao ? getDiffMinutes(srv.inicioExecucao, new Date().toISOString()) : (isGap ? (srv.durMin || null) : null));

    const flexDesloc = (durDesloc && durDesloc > 0) ? durDesloc : 1;
    const flexExec = (durExec && durExec > 0) ? durExec : 2;

    let barHtml = '<div class="timelineBarTrack">';

    if (isInterval) {
      barHtml += `
        <div class="timelineBarSeg timelineBarSeg--interval ${isRunning ? 'timelineBarSeg--running' : ''}" style="flex: 1;" title="Intervalo: ${inicio}${durExec !== null ? ` (${fmtRelMinutes(durExec)})` : ''}">
          <span class="timelineBarIcon">☕</span>
          <span class="timelineBarTime">${inicio || '-'}</span>
          ${durExec !== null ? `<span class="timelineBarDur">${fmtRelMinutes(durExec)}</span>` : (isRunning ? `<span class="timelineBarDur">em andamento</span>` : '')}
        </div>
      `;

      if (fim) {
        barHtml += `
          <div class="timelineBarPoint timelineBarPoint--done" title="Fim do Intervalo: ${fim}">
            <span class="timelineBarIcon">✅</span>
            <span class="timelineBarTime">${fim}</span>
          </div>
        `;
      } else if (isRunning) {
        barHtml += `
          <div class="timelineBarPoint timelineBarPoint--running" title="Em intervalo">
            <span class="timelineBarIcon">⏳</span>
            <span class="timelineBarTime">Atual</span>
          </div>
        `;
      }
    } else if (isGap) {
      const isSemProd = srv.gapType === 'SEM_PRODUCAO';
      barHtml += `
        <div class="timelineBarSeg ${isSemProd ? 'timelineBarSeg--semproducao' : 'timelineBarSeg--semservico'}" style="flex: 1;" title="${srv.tipo}: ${inicio} até ${fim} (${fmtRelMinutes(durExec)})">
          <span class="timelineBarIcon">${isSemProd ? '🔴' : '🟡'}</span>
          <span class="timelineBarTime">${inicio || '-'}</span>
          ${durExec !== null ? `<span class="timelineBarDur">${fmtRelMinutes(durExec)}</span>` : ''}
        </div>
        <div class="timelineBarPoint timelineBarPoint--done" title="Término da Espera: ${fim}">
          <span class="timelineBarIcon">✅</span>
          <span class="timelineBarTime">${fim || '-'}</span>
        </div>
      `;
    } else if (isRedirected) {
      barHtml += `
        <div class="timelineBarSeg timelineBarSeg--redirecionado" style="flex: 1;" title="Deslocamento interrompido: ${desloc}${durDesloc !== null ? ` (${fmtRelMinutes(durDesloc)})` : ''}">
          <span class="timelineBarIcon">🔀</span>
          <span class="timelineBarTime">${desloc || inicio || '-'}</span>
          ${durDesloc !== null ? `<span class="timelineBarDur">${fmtRelMinutes(durDesloc)}</span>` : ''}
        </div>
        <div class="timelineBarPoint timelineBarPoint--done" style="background: rgba(168, 85, 247, 0.2); color: #d8b4fe;" title="Redirecionado p/ Emergência: ${fim || '-'}">
          <span class="timelineBarIcon">🚫</span>
          <span class="timelineBarTime">${fim || '-'}</span>
        </div>
      `;
    } else {
      if (desloc) {
        const showDesloc = desloc !== inicio || (durDesloc && durDesloc > 0);
        if (showDesloc) {
          barHtml += `
            <div class="timelineBarSeg timelineBarSeg--desloc" style="flex: ${flexDesloc};" title="Deslocamento: ${desloc}${durDesloc !== null ? ` (${fmtRelMinutes(durDesloc)})` : ''}">
              <span class="timelineBarIcon">🚗</span>
              <span class="timelineBarTime">${desloc}</span>
              ${durDesloc !== null ? `<span class="timelineBarDur">${fmtRelMinutes(durDesloc)}</span>` : ''}
            </div>
          `;
        }
      }

      if (inicio || isRunning) {
        barHtml += `
          <div class="timelineBarSeg timelineBarSeg--exec ${isRunning ? 'timelineBarSeg--running' : ''}" style="flex: ${flexExec};" title="Execução: ${inicio || desloc || '-'}${durExec !== null ? ` (${fmtRelMinutes(durExec)})` : ''}">
            <span class="timelineBarIcon">⚡</span>
            <span class="timelineBarTime">${inicio || desloc || '-'}</span>
            ${durExec !== null ? `<span class="timelineBarDur">${fmtRelMinutes(durExec)}</span>` : (isRunning ? `<span class="timelineBarDur">em andamento</span>` : '')}
          </div>
        `;
      }

      if (fim) {
        barHtml += `
          <div class="timelineBarPoint timelineBarPoint--done" title="Conclusão: ${fim}">
            <span class="timelineBarIcon">✅</span>
            <span class="timelineBarTime">${fim}</span>
          </div>
        `;
      } else if (isRunning) {
        barHtml += `
          <div class="timelineBarPoint timelineBarPoint--running" title="Em atendimento">
            <span class="timelineBarIcon">⏳</span>
            <span class="timelineBarTime">Atual</span>
          </div>
        `;
      }
    }

    barHtml += '</div>';

    let typeBadgeClass = 'timelineTypeBadge--comercial';
    if (isInterval) typeBadgeClass = 'timelineTypeBadge--intervalo';
    else if (isRedirected) typeBadgeClass = 'timelineTypeBadge--redirecionado';
    else if (isGap) typeBadgeClass = (srv.gapType === 'SEM_PRODUCAO' ? 'timelineTypeBadge--semproducao' : 'timelineTypeBadge--semservico');
    else if (isEmergencia) typeBadgeClass = 'timelineTypeBadge--emergencia';

    let cardExtraClass = '';
    if (isInterval) cardExtraClass = 'teamTimelineCard--interval';
    else if (isRedirected) cardExtraClass = 'teamTimelineCard--redirecionado';
    else if (isGap) cardExtraClass = (srv.gapType === 'SEM_PRODUCAO' ? 'teamTimelineCard--semproducao' : 'teamTimelineCard--semservico');

    let dotExtraClass = '';
    if (isInterval) dotExtraClass = 'timelineIndicatorDot--interval';
    else if (isRedirected) dotExtraClass = 'timelineIndicatorDot--redirecionado';
    else if (isGap) dotExtraClass = (srv.gapType === 'SEM_PRODUCAO' ? 'timelineIndicatorDot--semproducao' : 'timelineIndicatorDot--semservico');

    let statusText = 'Concluído';
    if (isRunning) {
      statusText = isInterval ? 'Em Intervalo' : (status === 'DESLOCAMENTO' ? 'Deslocamento' : 'Em Execução');
    } else if (isRedirected) {
      statusText = 'Redirecionado';
    } else if (isGap) {
      statusText = 'Sem Execução';
    }

    html += `
      <div class="teamTimelineCard ${isRunning ? 'teamTimelineCard--running' : ''} ${cardExtraClass}">
        <div class="teamTimelineCardIndicator">
          <span class="timelineIndicatorDot ${isRunning ? 'timelineIndicatorDot--pulse' : ''} ${dotExtraClass}"></span>
        </div>
        <div class="teamTimelineCardContent">
          <div class="teamTimelineCardHeader">
            <div class="teamTimelineCardTitleWrap">
              <span class="timelineSeqBadge">${isInterval ? '☕' : (isRedirected ? '🔀' : (isGap ? (srv.gapType === 'SEM_PRODUCAO' ? '🔴' : '🟡') : `#${seq}`))}</span>
              <span class="timelineTypeBadge ${typeBadgeClass}">${escapeHtml(tipo)}</span>
              <span class="timelineCategoryTag">${escapeHtml(categoria)}</span>
              ${!isInterval && !isGap && protocolo && protocolo !== '-' ? `
                <span class="timelineProtocolInline"><span class="timelineProtocolLabel">OS:</span> <strong class="timelineProtocolValue">${escapeHtml(protocolo)}</strong></span>
              ` : (isGap ? `
                <span class="timelineProtocolInline"><strong class="timelineProtocolValue" style="color: #94a3b8; font-size: 11px; font-weight: 500;">${escapeHtml(protocolo)}</strong></span>
              ` : (isInterval ? `
                <span class="timelineProtocolInline"><strong class="timelineProtocolValue" style="color: #94a3b8; font-size: 11px; font-weight: 500;">Intervalo da Equipe</strong></span>
              ` : ''))}
            </div>
            <span class="timelineStatusBadge ${isRunning ? 'timelineStatusBadge--running' : 'timelineStatusBadge--done'} ${isRedirected ? 'timelineStatusBadge--redirected' : ''}">
              ${statusText}
            </span>
          </div>
          
          <div class="teamTimelineCardBarWrap">
            ${barHtml}
          </div>
        </div>
      </div>
    `;
  });
  html += '</div>';

  container.innerHTML = html;
}

async function loadAndRenderTeamTimeline(teamKey, item) {
  const container = document.getElementById('teamTimelineList');
  const countBadge = document.getElementById('teamTimelineCount');
  
  const snapshot = (item && item.rotalogSnapshot) || item;
  if (snapshot && Array.isArray(snapshot.services) && snapshot.services.length > 0) {
    renderTeamTimeline(item);
  } else {
    if (container) {
      container.innerHTML = '<div class="popoverEmpty">Carregando atendimentos do dia...</div>';
      if (countBadge) countBadge.textContent = 'Carregando...';
    }
  }

  if (!teamKey) return;
  try {
    const today = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Sao_Paulo',
      year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    const resp = await fetch(`/api/rotalog/teams/${encodeURIComponent(teamKey)}/daily?date=${today}`, { cache: 'no-store' });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.daily && Array.isArray(data.daily.services)) {
        const enrichedItem = {
          ...(item || {}),
          rotalogSnapshot: {
            ...((item && item.rotalogSnapshot) || {}),
            services: data.daily.services,
            current: data.daily.current,
            turno: data.daily.turno,
          }
        };
        renderTeamTimeline(enrichedItem);
        return;
      }
    }
  } catch (err) {
    console.debug('Aviso: Não foi possível buscar o diário complementar:', err);
  }
  renderTeamTimeline(item);
}

function updateLiveSummary(item) {
  const operational = getOperationalRotalogData(item);
  teamLiveStatus.textContent = stateLabel(operational.status);
  if (teamLiveActivity) teamLiveActivity.textContent = operationalActivityLabel(operational.activity);
  if (teamLiveService) teamLiveService.textContent = operational.serviceLabel;
  if (teamLiveProtocol) teamLiveProtocol.textContent = operational.protocol;
  if (teamLiveSource) {
    teamLiveSource.textContent = operational.source;
    teamLiveSource.classList.toggle('isRotalog', operational.source === 'ROTALOG');
  }
  teamLiveUpdatedAt.textContent = fmtDateTime(operational.updatedAt);
  teamLiveAgo.textContent = Number.isFinite(operational.ageMinutes)
    ? `Há ${fmtAgeFromMinutes(operational.ageMinutes)}`
    : '-';

  const snapshot = (item && item.rotalogSnapshot) || item;
  if (snapshot && Array.isArray(snapshot.services) && snapshot.services.length > 0) {
    renderTeamTimeline(item);
  }
}

async function loadMessages(teamKey) {
  if (!teamChatHistory) return;
  teamChatHistory.innerHTML = '<div class="popoverEmpty">Carregando mensagens...</div>';
  
  try {
    const currentSector = state().getCurrentSector();
    const response = await fetch(`/api/mensagens/threads?setor=${encodeURIComponent(currentSector)}`);
    const data = await response.json();
    
    // Procura por uma thread que envolva esta equipe
    const thread = (data.threads || []).find(t => t.fromEquipe === teamKey || t.toEquipe === teamKey);
    
    if (thread) {
      currentThreadId = thread.threadId;
      currentSubject = thread.subject;
      await renderThread(currentThreadId, thread); // Pass thread info
      
      // "Apenas quando o destinatario abre a mensagem o status muda para LIDO"
      const amITheRecipient = thread.toSetor === currentSector;

      // Atualiza o botão do cabeçalho
      if (thread.status === 'NÃO LIDO' && amITheRecipient) {
        teamFormCommBtn?.classList.add('hasUnread');
      } else {
        teamFormCommBtn?.classList.remove('hasUnread');
      }

      // Marca como lida ao abrir se NÓS formos o destinatário e estiver não lido
      if (thread.status === 'NÃO LIDO' && amITheRecipient) {
        await fetch(`/api/mensagens/read?setor=${encodeURIComponent(currentSector)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ threadId: currentThreadId })
        });
        if (state().reload) state().reload(); // Recarrega o grid para limpar o badge
        teamFormCommBtn?.classList.remove('hasUnread');
      }
    } else {
      teamFormCommBtn?.classList.remove('hasUnread');
      currentThreadId = `thread_${teamKey}_${Date.now()}`;
      currentSubject = `Comunicação ${teamKey}`;
      teamChatHistory.innerHTML = '<div class="popoverEmpty">Nenhuma conversa ativa com esta equipe. Envie uma mensagem para iniciar.</div>';
    }
  } catch (error) {
    console.error('Erro ao carregar mensagens:', error);
    teamChatHistory.innerHTML = '<div class="popoverEmpty">Erro ao carregar histórico de mensagens.</div>';
  }
}

async function renderThread(threadId, threadInfo = null) {
  try {
    const response = await fetch(`/api/mensagens/thread/${threadId}`);
    const data = await response.json();
    const messages = data.messages || [];
    const currentSector = state().getCurrentSector();
    
    if (messages.length === 0) {
      teamChatHistory.innerHTML = '<div class="popoverEmpty">Nenhuma mensagem nesta conversa.</div>';
      return;
    }
    
    teamChatHistory.innerHTML = messages.map(msg => {
      // isMe: se a mensagem foi enviada por QUALQUER setor do monitor (não apenas o atual)
      // Mas para o visual "isMe", queremos destacar mensagens enviadas pelo monitor em geral?
      // O usuário quer que todos vejam, mas só o destinatário responda.
      const sentByMonitor = ['OFICINA', 'ALMOXARIFADO', 'PONTO', 'ROTALOG'].includes(msg.fromEquipe);
      const isMe = msg.fromEquipe === currentSector;
      
      const time = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
      
      let senderLabel = msg.fromEquipe;
      if (sentByMonitor) senderLabel = `Monitor (${msg.fromEquipe})`;
      else if (msg.fromEquipe === openTeamKey) senderLabel = `Equipe (${openTeamKey})`;

      return `
        <div class="messageBubble ${sentByMonitor ? 'isMe' : 'isThem'} ${isMe ? 'isCurrentMe' : ''}">
          <span class="messageSender">${escapeHtml(senderLabel)}</span>
          <div class="messageContent">${escapeHtml(msg.content)}</div>
          <div class="messageMeta">
            <span>${time}</span>
            ${isMe ? '<span>✓</span>' : ''}
          </div>
        </div>
      `;
    }).join('');
    
    // Lógica de Permissão de Resposta:
    // "todos os usuarios conseguem ver a mensagem, mas só a equipe destinada pode responder"
    const intendedSector = threadInfo ? threadInfo.toSetor : (messages.length > 0 ? messages[0].toSetor : null);
    const canIRespond = !intendedSector || intendedSector === currentSector;

    if (!canIRespond) {
      teamChatMessageInput.disabled = true;
      teamChatSendBtn.disabled = true;
      teamChatConcludeBtn.disabled = true; // Trava o botão de concluir também
      teamChatMessageInput.placeholder = `Somente o setor ${intendedSector} pode tratar esta mensagem.`;
      
      // Adiciona banner de aviso
      const banner = document.createElement('div');
      banner.className = 'permissionBanner';
      banner.style.background = 'rgba(239, 68, 68, 0.1)';
      banner.style.color = '#f87171';
      banner.style.padding = '8px';
      banner.style.borderRadius = '6px';
      banner.style.fontSize = '0.75rem';
      banner.style.marginBottom = '10px';
      banner.style.textAlign = 'center';
      banner.style.border = '1px solid rgba(239, 68, 68, 0.2)';
      banner.textContent = `⚠️ Visualização apenas. Resposta restrita ao setor ${intendedSector}.`;
      
      const existingBanner = teamChatHistory.querySelector('.permissionBanner');
      if (existingBanner) existingBanner.remove();
      teamChatHistory.prepend(banner);
    } else {
      teamChatConcludeBtn.disabled = false;
      const lastMsg = messages[messages.length - 1];
      const isAwaitingThem = lastMsg && lastMsg.fromEquipe === currentSector;
      if (isAwaitingThem) {
        teamChatMessageInput.disabled = true;
        teamChatSendBtn.disabled = true;
        teamChatMessageInput.placeholder = "Aguardando resposta da equipe...";
      } else {
        teamChatMessageInput.disabled = false;
        teamChatSendBtn.disabled = false;
        teamChatMessageInput.placeholder = "Digite uma mensagem...";
      }
    }

    teamChatHistory.scrollTop = teamChatHistory.scrollHeight;
  } catch (error) {
    console.error('Erro ao renderizar thread:', error);
  }
}

async function sendMessage() {
  const content = (teamChatMessageInput.value || '').trim();
  if (!content || !openTeamKey) return;
  
  teamChatMessageInput.disabled = true;
  teamChatSendBtn.disabled = true;
  
  try {
    const payload = {
      threadId: currentThreadId,
      subject: currentSubject,
      content: content,
      toEquipe: openTeamKey,
      toSetor: null, // Destinado à equipe
      fromEquipe: state().getCurrentSector()
    };
    
    const response = await fetch('/api/mensagens/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (response.ok) {
      teamChatMessageInput.value = '';
      await renderThread(currentThreadId);
    }
  } catch (error) {
    console.error('Erro ao enviar mensagem:', error);
  } finally {
    teamChatMessageInput.disabled = false;
    teamChatSendBtn.disabled = false;
    teamChatMessageInput.focus();
  }
}

async function concludeThread() {
  if (!currentThreadId || !confirm('Deseja marcar esta conversa como concluída e arquivá-la?')) return;
  
  try {
    const response = await fetch('/api/mensagens/conclude', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ threadId: currentThreadId })
    });
    
    if (response.ok) {
      currentThreadId = `thread_${openTeamKey}_${Date.now()}`;
      teamChatHistory.innerHTML = '<div class="popoverEmpty">Conversa concluída.</div>';
      if (state().reload) state().reload();
    }
  } catch (error) {
    console.error('Erro ao concluir thread:', error);
  }
}

function buildEmptyEquipmentMap() {
  return {
    tablet: normalizeEquipment({}, 'tablet'),
    cameraCopel: normalizeEquipment({}, 'cameraCopel'),
    cameraVeicular: normalizeEquipment({}, 'cameraVeicular'),
  };
}

function normalizeEquipment(value, equipmentType) {
  const meta = EQUIPMENT_META[equipmentType] || {};
  const raw = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};
  const normalized = {
    kind: equipmentType,
    label: meta.label || equipmentType,
    summary: ((raw.summary ?? '') + '').trim(),
    identifier: meta.supportsIdentifier ? (((raw.identifier ?? raw.identificacao ?? '') + '').trim().toUpperCase()) : '',
    serial: ((raw.serial ?? '') + '').trim(),
    patrimonio: meta.supportsPatrimonio ? (((raw.patrimonio ?? '') + '').trim()) : '',
    imei: meta.supportsImei ? (((raw.imei ?? '') + '').trim()) : '',
    phoneNumber: meta.supportsPhoneNumber ? (((raw.phoneNumber ?? raw.numeroTelefone ?? '') + '').trim()) : '',
    email: meta.supportsEmail === false ? (((raw.email ?? '') + '').trim()) : (((raw.email ?? '') + '').trim()),
    lastChangedAt: ((raw.lastChangedAt ?? '') + '').trim(),
    lastChangeReason: ((raw.lastChangeReason ?? '') + '').trim(),
    changeReason: ((raw.changeReason ?? '') + '').trim(),
    supportsPatrimonio: Boolean(meta.supportsPatrimonio),
    supportsImei: Boolean(meta.supportsImei),
    supportsPhoneNumber: Boolean(meta.supportsPhoneNumber),
    supportsEmail: meta.supportsEmail !== false,
  };
  if (!normalized.summary) normalized.summary = summarizeEquipment(normalized);
  return normalized;
}

function summarizeEquipment(value) {
  const parts = [value?.identifier, value?.serial, value?.patrimonio, value?.imei, value?.phoneNumber, value?.email]
    .map((item) => ((item ?? '') + '').trim())
    .filter(Boolean);
  return parts[0] || '';
}

function equipmentSignature(value) {
  const normalized = normalizeEquipment(value || {}, value?.kind || '');
  return JSON.stringify({
    identifier: normalized.identifier,
    serial: normalized.serial,
    patrimonio: normalized.patrimonio,
    imei: normalized.imei,
    phoneNumber: normalized.phoneNumber,
    email: normalized.email,
  });
}

function renderEquipmentCards() {
  Object.entries(EQUIPMENT_META).forEach(([equipmentType, meta]) => {
    const equipment = normalizeEquipment(equipmentState?.[equipmentType] || {}, equipmentType);
    const summary = equipment.identifier || equipment.summary || summarizeEquipment(equipment) || '';
    if (meta.summaryEl) meta.summaryEl.textContent = summary || 'Nenhum equipamento vinculado';
  });
  if (equipmentSummaryDds) {
    equipmentSummaryDds.textContent = 'Ver histórico (3 sem.)';
  }
}

function renderEquipmentHistoryTable(equipmentType = openEquipmentType) {
  if (!equipmentHistoryTableBody) return;
  const historyItems = Array.isArray(equipmentHistory)
    ? equipmentHistory.filter((entry) => !equipmentType || entry?.equipmentType === equipmentType)
    : [];

  if (!historyItems.length) {
    equipmentHistoryTableBody.innerHTML = `
      <tr>
        <td colspan="5" class="equipmentHistoryEmptyCell">Nenhuma alteração registrada.</td>
      </tr>
    `;
    return;
  }

  equipmentHistoryTableBody.innerHTML = historyItems.map((entry) => {
    const changedAt = fmtDateTime(entry?.changedAt);
    const identifier = entry?.after?.identifier || entry?.before?.identifier || '-';
    const serial = entry?.after?.serial || entry?.before?.serial || '-';
    const patrimonio = entry?.after?.patrimonio || entry?.before?.patrimonio || '-';
    const reason = detailValue(entry?.changeReason || 'Sem motivo informado');
    return `
      <tr>
        <td>${escapeHtml(changedAt)}</td>
        <td>${escapeHtml(identifier)}</td>
        <td>${escapeHtml(serial)}</td>
        <td>${escapeHtml(patrimonio)}</td>
        <td>${escapeHtml(reason)}</td>
      </tr>
    `;
  }).join('');
}

function escapeHtml(value) {
  return (value ?? '')
    .toString()
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function fillForm(data) {
  const team = data?.team || {};
  const turno = data?.turno || {};
  const meta = data?.meta || {};

  suspendDirtyTracking = true;
  formTeamKey.value = team.teamKey || turno.teamKey || openTeamKey || '';
  formEmpresa.value = turno.empresa || data?.empresa || state().getEmpresa?.() || '';
  formDisplayName.value = team.displayName || formTeamKey.value;
  if (formTeamType) formTeamType.value = team.teamType || '';
  const container = document.getElementById("membersContainer");
  if (container) {
    container.innerHTML = "";
    if (Array.isArray(team.members)) {
      team.members.forEach(member => {
        const normMember = member.trim().toUpperCase();
        const isDriver = normMember === (team.motorista || "").trim().toUpperCase();
        const isCoringa = Array.isArray(team.coringas) && team.coringas.some(c => c.trim().toUpperCase() === normMember);
        window.addMemberRow(member, isDriver, isCoringa);
      });
    }
  }
  equipmentState = {
    tablet: normalizeEquipment(team?.equipment?.tablet || {}, 'tablet'),
    cameraCopel: normalizeEquipment(team?.equipment?.cameraCopel || {}, 'cameraCopel'),
    cameraVeicular: normalizeEquipment(team?.equipment?.cameraVeicular || {}, 'cameraVeicular'),
  };
  equipmentHistory = Array.isArray(data?.equipmentHistory) ? data.equipmentHistory : [];
  renderEquipmentCards();
  renderEquipmentHistoryTable();
  
  const isActive = Boolean(team.active ?? true);
  formActive.value = isActive ? 'true' : 'false';
  updateActiveIcons(isActive);
  
  formEstado.value = turno.estado || 'DESCONHECIDO';
  formNocSs.value = turno.nocSs || '';
  formMotivo.value = turno.motivo || '';
  formHoraEntrada.value = turno.horaEntrada || '';
  formHoraSaida.value = turno.horaSaida || '';
  formObservacoes.value = turno.observacoes || '';
  teamFormMeta.textContent = `Cadastro base: ${meta.teamDocExists ? 'existente' : 'novo'} · Turno atual: ${meta.turnoDocExists ? 'existente' : 'novo'}`;
  if (teamFormDeleteIcon) {
    // Só permite mover para a lixeira se a equipe estiver INATIVA
    teamFormDeleteIcon.hidden = !meta.teamDocExists || isActive;
    
    // Opcional: adiciona um title explicativo se estiver ativa
    if (isActive) {
      teamFormDeleteIcon.title = "Desative a equipe primeiro para poder movê-la para a lixeira.";
    } else {
      teamFormDeleteIcon.title = "Mover para Lixeira";
    }
  }
  savedFormSignature = createFormSignature(collectPayload());
  suspendDirtyTracking = false;
  updateDirtyState();
}

function collectPayload() {
  const teamKey = (formTeamKey.value || openTeamKey || '').trim();
  const empresa = (formEmpresa.value || state().getEmpresa?.() || '').trim();
  return {
    team: {
      teamKey,
      displayName: (formDisplayName.value || teamKey).trim(),
      teamType: formTeamType ? formTeamType.value || null : null,
      members: Array.from(document.querySelectorAll("#membersContainer .memberRow")).map(row => row.querySelector(".memberInput").value.trim()).filter(Boolean),
      motorista: (() => {
        const driverRow = Array.from(document.querySelectorAll("#membersContainer .memberRow")).find(row => row.querySelector(".btnDriverToggle").classList.contains("active"));
        return driverRow ? driverRow.querySelector(".memberInput").value.trim() : null;
      })(),
      coringas: Array.from(document.querySelectorAll("#membersContainer .memberRow"))
        .filter(row => row.querySelector(".btnCoringaToggle").classList.contains("active"))
        .map(row => row.querySelector(".memberInput").value.trim())
        .filter(Boolean),
      equipment: {
        tablet: normalizeEquipment(equipmentState?.tablet || {}, 'tablet'),
        cameraCopel: normalizeEquipment(equipmentState?.cameraCopel || {}, 'cameraCopel'),
        cameraVeicular: normalizeEquipment(equipmentState?.cameraVeicular || {}, 'cameraVeicular'),
      },
      active: formActive.value === 'true',
    },
    turno: {
      empresa,
      teamKey,
      estado: formEstado.value,
      nocSs: formNocSs.value.trim(),
      motivo: formMotivo.value.trim(),
      horaEntrada: formHoraEntrada.value || '',
      horaSaida: formHoraSaida.value || '',
      observacoes: formObservacoes.value.trim(),
    },
  };
}

function createFormSignature(payload) {
  return JSON.stringify(payload || {});
}

function updatePrimaryActionState() {
  if (teamFormSave && !saveInFlight) {
    teamFormSave.textContent = currentDirty ? 'Salvar' : 'Fechar';
  }
  if (teamFormCancel && !saveInFlight) {
    teamFormCancel.hidden = !currentDirty;
  }
}

function updateDirtyState() {
  if (suspendDirtyTracking) return;
  currentDirty = createFormSignature(collectPayload()) !== savedFormSignature;
  updatePrimaryActionState();
}

function collectEquipmentEditorPayload() {
  return normalizeEquipment({
    identifier: equipmentIdentifier?.value,
    serial: equipmentSerial?.value,
    patrimonio: equipmentPatrimonio?.value,
    imei: equipmentImei?.value,
    phoneNumber: equipmentPhone?.value,
    email: equipmentEmail?.value,
  }, openEquipmentType || '');
}

function updateEquipmentPrimaryActionState() {
  if (!equipmentModalSave) return;
  equipmentModalSave.textContent = equipmentModalDirty ? 'Salvar' : 'Fechar';
  if (equipmentModalCancel) {
    equipmentModalCancel.hidden = !equipmentModalDirty;
  }
}

function updateEquipmentDirtyState() {
  if (!openEquipmentType) {
    equipmentModalDirty = false;
    updateEquipmentPrimaryActionState();
    return;
  }
  const baseline = normalizeEquipment(equipmentEditorBaseline || equipmentState?.[openEquipmentType] || {}, openEquipmentType);
  const draft = collectEquipmentEditorPayload();
  equipmentModalDirty = equipmentSignature(draft) !== equipmentSignature(baseline);
  updateEquipmentPrimaryActionState();
}

function openEquipmentEditor(equipmentType) {
  if (!equipmentModal || !EQUIPMENT_META[equipmentType]) return;
  openEquipmentType = equipmentType;
  const meta = EQUIPMENT_META[equipmentType];
  const current = normalizeEquipment(equipmentState?.[equipmentType] || {}, equipmentType);
  equipmentEditorBaseline = normalizeEquipment(current, equipmentType);
  equipmentModalTitle.textContent = meta.label;
  equipmentModalSubtitle.textContent = 'Dados do equipamento vinculado à equipe';
  equipmentModalImage.src = meta.image;
  equipmentModalImage.alt = meta.label;
  if (equipmentIdentifier) equipmentIdentifier.value = current.identifier || '';
  equipmentSerial.value = current.serial || '';
  equipmentPatrimonio.value = current.patrimonio || '';
  equipmentImei.value = current.imei || '';
  equipmentPhone.value = current.phoneNumber || '';
  equipmentEmail.value = current.email || '';
  equipmentChangeReason.value = '';
  if (equipmentIdentifierField) equipmentIdentifierField.hidden = !meta.supportsIdentifier;
  equipmentPatrimonioField.hidden = !meta.supportsPatrimonio;
  equipmentImeiField.hidden = !meta.supportsImei;
  equipmentPhoneField.hidden = !meta.supportsPhoneNumber;
  if (equipmentEmailField) equipmentEmailField.hidden = !meta.supportsEmail;
  equipmentModalMeta.textContent = `Editando ${meta.label.toLowerCase()} da equipe ${formTeamKey.value || openTeamKey || '-'}`;
  setEquipmentFormNotice('');
  renderEquipmentHistoryTable(equipmentType);
  equipmentModalDirty = false;
  updateEquipmentPrimaryActionState();
  setEquipmentModalHidden(false);
}

function closeEquipmentEditor() {
  equipmentModalDirty = false;
  updateEquipmentPrimaryActionState();
  setEquipmentModalHidden(true);
}

function saveEquipmentEditor() {
  if (!openEquipmentType) return;
  if (!equipmentModalDirty) {
    closeEquipmentEditor();
    return;
  }

  const edited = collectEquipmentEditorPayload();
  const baseline = normalizeEquipment(equipmentEditorBaseline || equipmentState?.[openEquipmentType] || {}, openEquipmentType);
  const changed = equipmentSignature(edited) !== equipmentSignature(baseline);
  const reason = (equipmentChangeReason?.value || '').trim();

  if (changed && !reason) {
    setEquipmentFormNotice('Selecione o motivo da substituição antes de salvar.', 'error');
    return;
  }

  equipmentState[openEquipmentType] = {
    ...edited,
    lastChangedAt: baseline.lastChangedAt || '',
    lastChangeReason: baseline.lastChangeReason || '',
    changeReason: changed ? reason : '',
  };
  renderEquipmentCards();
  updateDirtyState();
  if (changed) {
    teamFormMeta.textContent = `${EQUIPMENT_META[openEquipmentType].label} atualizado. Clique em Salvar para persistir.`;
  }
  closeEquipmentEditor();
}

async function openTeamForm(teamKey) {
  if (!teamKey) return;
  openTeamKey = teamKey;
  const currentItem = state().findItem ? state().findItem(teamKey) : null;

  // Limpa campos do formulário imediatamente para não mostrar dados da equipe anterior
  suspendDirtyTracking = true;
  if (formDisplayName) formDisplayName.value = '';
  if (formTeamType) formTeamType.value = '';
  const container = document.getElementById("membersContainer");
  if (container) container.innerHTML = '';
  if (formNocSs) formNocSs.value = '';
  if (formMotivo) formMotivo.value = '';
  if (formHoraEntrada) formHoraEntrada.value = '';
  if (formHoraSaida) formHoraSaida.value = '';
  if (formObservacoes) formObservacoes.value = '';
  if (formTeamKey) formTeamKey.value = teamKey;
  suspendDirtyTracking = false;

  updateHeader(currentItem, teamKey);
  if (currentItem) {
    updateLiveSummary(currentItem);
    loadAndRenderTeamTimeline(teamKey, currentItem);
  }

  equipmentState = buildEmptyEquipmentMap();
  equipmentHistory = [];
  savedFormSignature = '';
  currentDirty = false;
  renderEquipmentCards();
  renderEquipmentHistoryTable();
  setNotice('');
  setModalHidden(false);
  updatePrimaryActionState();
  
  if (teamChatPopover) teamChatPopover.hidden = true;
  if (chatPopoverTeamName) chatPopoverTeamName.textContent = teamKey;

  loadMessages(teamKey);
  setBusy(false, 'Carregando formulário...');
  const requestId = ++loadToken;
  const empresa = state().getEmpresa ? state().getEmpresa() : '';

  try {
    const response = await fetch(`/api/team-form?empresa=${encodeURIComponent(empresa)}&teamKey=${encodeURIComponent(teamKey)}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || 'Falha ao carregar formulário.');
    if (requestId !== loadToken) return;
    fillForm(data);
    const hasApiDds = Array.isArray(data.ddsHistory) && data.ddsHistory.length > 0;
    const liveItem = {
      ...(currentItem || {}),
      ddsHistory: hasApiDds ? data.ddsHistory : (currentItem?.ddsHistory || []),
      ddsDays: (Array.isArray(data.ddsDays) && data.ddsDays.length > 0) ? data.ddsDays : (currentItem?.ddsDays || []),
      ddsTimes: (data.ddsTimes && Object.keys(data.ddsTimes).length > 0) ? data.ddsTimes : (currentItem?.ddsTimes || {}),
      ddsPhotos: (data.ddsPhotos && Object.keys(data.ddsPhotos).length > 0) ? data.ddsPhotos : (currentItem?.ddsPhotos || {}),
      ddsToday: (data.ddsToday && data.ddsToday !== 'neutral') ? data.ddsToday : (currentItem?.ddsToday || 'neutral'),
    };
    updateHeader(liveItem, teamKey);
    updateLiveSummary(liveItem);
    loadAndRenderTeamTimeline(teamKey, liveItem);
    teamFormMeta.textContent = `Equipe ${teamKey} pronta para edição`;
  } catch (error) {
    setNotice(error?.message || 'Não foi possível carregar o formulário.', 'error');
    teamFormMeta.textContent = 'Falha ao carregar';
  }
}

function closeTeamForm() {
  if (saveInFlight) return;
  if (currentDirty) {
    if (!confirm('Existem alterações não salvas nesta equipe. Deseja sair mesmo assim?')) {
      return;
    }
  }
  closeEquipmentEditor();
  setModalHidden(true);
  setNotice('');
  openTeamKey = null;
  currentDirty = false;
  updatePrimaryActionState();
}

async function saveTeamForm() {
  if (saveInFlight) return;
  if (!currentDirty) {
    closeTeamForm();
    return;
  }
  const payload = collectPayload();
  if (!payload.team.teamKey) {
    setNotice('teamKey não localizado para salvar.', 'error');
    return;
  }
  if (!payload.turno.empresa) {
    setNotice('Empresa não informada.', 'error');
    return;
  }

  saveInFlight = true;
  setBusy(true, 'Persistindo alterações no Firestore...');
  setNotice('');

  try {
    const response = await fetch('/api/team-form', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || 'Falha ao salvar equipe.');

    equipmentState = {
      tablet: normalizeEquipment(data?.team?.equipment?.tablet || payload.team.equipment.tablet || {}, 'tablet'),
      cameraCopel: normalizeEquipment(data?.team?.equipment?.cameraCopel || payload.team.equipment.cameraCopel || {}, 'cameraCopel'),
      cameraVeicular: normalizeEquipment(data?.team?.equipment?.cameraVeicular || payload.team.equipment.cameraVeicular || {}, 'cameraVeicular'),
    };
    equipmentHistory = Array.isArray(data?.equipmentHistory) ? data.equipmentHistory : equipmentHistory;
    renderEquipmentCards();
    renderEquipmentHistoryTable();
    savedFormSignature = createFormSignature(collectPayload());
    currentDirty = false;
    updatePrimaryActionState();

    if (state().reload) await state().reload();
    const refreshed = state().findItem ? state().findItem(payload.team.teamKey) : null;
    const currentView = state().getViewMode ? state().getViewMode() : 'active';
    if (!payload.team.active && currentView !== 'inactive') {
      setNotice('Equipe salva com sucesso. Ela foi movida para a tela de inativas.', 'success');
    } else if (payload.team.active && currentView === 'inactive') {
      setNotice('Equipe salva com sucesso. Ela foi movida para a tela principal.', 'success');
    } else {
      setNotice(data?.message || 'Equipe salva com sucesso.', 'success');
    }
    teamFormMeta.textContent = `Equipe ${payload.team.teamKey} salva com sucesso`;
    updateHeader(refreshed, payload.team.teamKey);
    updateLiveSummary(refreshed);

    // "o bt SALVAR, salva e fecha"
    setTimeout(() => {
      closeTeamForm();
    }, 500);

  } catch (error) {
    setNotice(error?.message || 'Não foi possível salvar a equipe.', 'error');
    teamFormMeta.textContent = 'Falha ao salvar';
  } finally {
    saveInFlight = false;
    setBusy(false, teamFormMeta.textContent);
    updatePrimaryActionState();
  }
}

function refreshOpenTeam(item) {
  if (!openTeamKey || teamFormModal.hidden) return;
  updateHeader(item, openTeamKey);
  updateLiveSummary(item);
}

[equipmentCardTablet, equipmentCardCameraCopel, equipmentCardCameraVeicular].forEach((btn) => {
  btn?.addEventListener('click', () => openEquipmentEditor(btn.dataset.equipmentType || ''));
});

[
  formDisplayName,
  formTeamType,
  formActive,
  formEstado,
  formNocSs,
  formMotivo,
  formHoraEntrada,
  formHoraSaida,
  formObservacoes,
].forEach((field) => {
  field?.addEventListener('input', updateDirtyState);
  field?.addEventListener('change', updateDirtyState);
});

document.getElementById('btnAddMember')?.addEventListener('click', () => {
  window.addMemberRow('', false, false);
});

[equipmentIdentifier, equipmentSerial, equipmentPatrimonio, equipmentImei, equipmentPhone, equipmentEmail].forEach((field) => {
  field?.addEventListener('input', updateEquipmentDirtyState);
  field?.addEventListener('change', updateEquipmentDirtyState);
});

equipmentChangeReason?.addEventListener('change', updateEquipmentDirtyState);

teamFormSave?.addEventListener('click', saveTeamForm);

teamFormDeleteIcon?.addEventListener('click', () => {
  if (openTeamKey) {
    window.openTrashConfirmation(openTeamKey);
  }
});

function updateActiveIcons(isActive) {
  if (!iconEyeOpen || !iconEyeClosed) return;
  if (isActive) {
    iconEyeOpen.style.display = 'block';
    iconEyeClosed.style.display = 'none';
    if (textToggleActive) textToggleActive.textContent = 'Ocultar Equipe';
  } else {
    iconEyeOpen.style.display = 'none';
    iconEyeClosed.style.display = 'block';
    if (textToggleActive) textToggleActive.textContent = 'Ativar Equipe';
  }
}

teamFormToggleActiveBtn?.addEventListener('click', () => {
  const currentActive = formActive.value === 'true';
  const newActive = !currentActive;
  formActive.value = newActive ? 'true' : 'false';
  updateActiveIcons(newActive);
  updateDirtyState();
});

teamFormClose?.addEventListener('click', closeTeamForm);
teamFormCancel?.addEventListener('click', closeTeamForm);
teamFormBackdrop?.addEventListener('click', closeTeamForm);

const closeEquipmentHandler = () => closeEquipmentEditor();
const saveEquipmentHandler = () => {
  if (equipmentModalDirty) {
    saveEquipmentEditor();
    return;
  }
  closeEquipmentEditor();
};
equipmentModalClose?.addEventListener('click', closeEquipmentHandler);
equipmentModalCancel?.addEventListener('click', closeEquipmentHandler);
equipmentModalBackdrop?.addEventListener('click', closeEquipmentHandler);
equipmentModalSave?.addEventListener('click', saveEquipmentHandler);

teamChatSendBtn?.addEventListener('click', sendMessage);
teamChatMessageInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
teamChatConcludeBtn?.addEventListener('click', concludeThread);

teamFormCommBtn?.addEventListener('click', () => {
  if (!teamChatPopover) return;
  teamChatPopover.hidden = !teamChatPopover.hidden;
  if (!teamChatPopover.hidden) {
    teamChatHistory.scrollTop = teamChatHistory.scrollHeight;
    teamChatMessageInput?.focus();
  }
});

function openDdsHistoryModal() {
  if (!ddsHistoryModal) return;
  const currentItem = (state().findItem && openTeamKey) ? state().findItem(openTeamKey) : null;
  const teamDisplayName = formDisplayName?.value || openTeamKey || 'Equipe';

  if (ddsHistoryModalTitle) ddsHistoryModalTitle.textContent = `Presenças no DDS - ${teamDisplayName}`;
  if (ddsHistoryModalSubtitle) ddsHistoryModalSubtitle.textContent = 'Histórico das últimas 3 semanas de reuniões diárias';

  if (ddsHistoryModalContent) {
    const renderer = utils().renderDdsKpiHtml;
    if (typeof renderer === 'function') {
      ddsHistoryModalContent.innerHTML = renderer(currentItem || {}, {
        maxItems: 20,
        showDayLabels: true,
        showMeta: true,
        containerClass: 'ddsRowModal',
      });
    } else {
      ddsHistoryModalContent.innerHTML = '<div class="popoverEmpty">Nenhum registro de DDS encontrado.</div>';
    }
  }

  ddsHistoryModal.hidden = false;
}

function closeDdsHistoryModal() {
  if (ddsHistoryModal) ddsHistoryModal.hidden = true;
}

equipmentCardDds?.addEventListener('click', openDdsHistoryModal);
ddsHistoryModalClose?.addEventListener('click', closeDdsHistoryModal);
ddsHistoryModalCloseBtn?.addEventListener('click', closeDdsHistoryModal);
ddsHistoryModalBackdrop?.addEventListener('click', closeDdsHistoryModal);

window.teamForm = {
  openTeamForm,
  closeTeamForm,
  refreshOpenTeam,
  openDdsHistoryModal,
  closeDdsHistoryModal,
  getOpenTeamKey: () => openTeamKey,
};
