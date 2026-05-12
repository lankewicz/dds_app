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
const teamLiveSs = document.getElementById('teamLiveSs');
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
const equipmentSummaryTablet = document.getElementById('equipmentSummaryTablet');
const equipmentSummaryCameraCopel = document.getElementById('equipmentSummaryCameraCopel');
const equipmentSummaryCameraVeicular = document.getElementById('equipmentSummaryCameraVeicular');

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
const equipmentSerial = document.getElementById('equipmentSerial');
const equipmentPatrimonio = document.getElementById('equipmentPatrimonio');
const equipmentImei = document.getElementById('equipmentImei');
const equipmentPhone = document.getElementById('equipmentPhone');
const equipmentEmail = document.getElementById('equipmentEmail');
const equipmentChangeReason = document.getElementById('equipmentChangeReason');

const formTeamKey = document.getElementById('formTeamKey');
const formEmpresa = document.getElementById('formEmpresa');
const formDisplayName = document.getElementById('formDisplayName');
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
    teamFormSave.textContent = isBusy ? 'Salvando...' : 'Salvar';
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
  const titleText = item?.equipe && item.equipe !== teamKey ? `${item.equipe} (${teamKey})` : (item?.equipe || teamKey || 'Equipe');
  const empresa = state().getEmpresa ? state().getEmpresa() : '';
  teamFormVehicle.className = `modalVehicle ${frameCls}`;
  teamFormVehicle.textContent = '🚚';
  teamFormTitle.textContent = titleText;
  teamFormSubtitle.textContent = empresa ? `Empresa ${empresa}` : 'Cadastro e situação atual do turno';
}

function updateLiveSummary(item) {
  teamLiveStatus.textContent = stateLabel(item?.estado || '-');
  teamLiveSs.textContent = detailValue(item?.ss);
  teamLiveUpdatedAt.textContent = fmtDateTime(item?.updatedAt);
  teamLiveAgo.textContent = Number.isFinite(item?.minutosDesdeAtualizacao) ? fmtAgeFromMinutes(item.minutosDesdeAtualizacao) : '-';

  if (teamLiveDds) {
    const renderer = utils().renderDdsKpiHtml;
    if (typeof renderer === 'function') {
      teamLiveDds.innerHTML = renderer(item || {}, {
        maxItems: 20,
        showDayLabels: true,
        showMeta: false,
        containerClass: 'ddsRowModal',
      });
    } else {
      teamLiveDds.innerHTML = '<div class="popoverEmpty" style="margin-top: 0;">Nenhum DDS registrado recentemente</div>';
    }
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
  const parts = [value?.serial, value?.patrimonio, value?.imei, value?.phoneNumber, value?.email]
    .map((item) => ((item ?? '') + '').trim())
    .filter(Boolean);
  return parts[0] || '';
}

function equipmentSignature(value) {
  const normalized = normalizeEquipment(value || {}, value?.kind || '');
  return JSON.stringify({
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
    const summary = equipment.summary || summarizeEquipment(equipment) || '';
    if (meta.summaryEl) meta.summaryEl.textContent = summary || 'Nenhum equipamento vinculado';
  });
}

function renderEquipmentHistoryTable(equipmentType = openEquipmentType) {
  if (!equipmentHistoryTableBody) return;
  const historyItems = Array.isArray(equipmentHistory)
    ? equipmentHistory.filter((entry) => !equipmentType || entry?.equipmentType === equipmentType)
    : [];

  if (!historyItems.length) {
    equipmentHistoryTableBody.innerHTML = `
      <tr>
        <td colspan="4" class="equipmentHistoryEmptyCell">Nenhuma alteração registrada.</td>
      </tr>
    `;
    return;
  }

  equipmentHistoryTableBody.innerHTML = historyItems.map((entry) => {
    const changedAt = fmtDateTime(entry?.changedAt);
    const serial = entry?.after?.serial || entry?.before?.serial || '-';
    const patrimonio = entry?.after?.patrimonio || entry?.before?.patrimonio || '-';
    const reason = detailValue(entry?.changeReason || 'Sem motivo informado');
    return `
      <tr>
        <td>${escapeHtml(changedAt)}</td>
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
  formMembers.value = Array.isArray(team.members) ? team.members.join('\n') : '';
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
      members: normalizeMembersText(formMembers.value),
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
    teamFormSave.textContent = 'Salvar';
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
  equipmentSerial.value = current.serial || '';
  equipmentPatrimonio.value = current.patrimonio || '';
  equipmentImei.value = current.imei || '';
  equipmentPhone.value = current.phoneNumber || '';
  equipmentEmail.value = current.email || '';
  equipmentChangeReason.value = '';
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
  updateHeader(currentItem, teamKey);
  updateLiveSummary(currentItem);
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
    updateHeader(currentItem, teamKey);
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
  formMembers,
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

[equipmentSerial, equipmentPatrimonio, equipmentImei, equipmentPhone, equipmentEmail].forEach((field) => {
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

chatPopoverClose?.addEventListener('click', () => {
  if (teamChatPopover) teamChatPopover.hidden = true;
});


window.teamForm = {
  openTeamForm,
  closeTeamForm,
  refreshOpenTeam,
  getOpenTeamKey: () => openTeamKey,
};
