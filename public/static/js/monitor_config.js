// -----------------------------------------------------------------------------
// Arquivo : static/js/monitor_config.js
// Objetivo: Modal de configuração operacional (regras de alerta amarelo/vermelho/pisco,
//           tolerâncias de turno, inativação) e painel de crash reports da equipe.
// -----------------------------------------------------------------------------

let configSaveInFlight = false;
let isAlertUnitHours = false;

function getConfigModalElements() {
  return {
    configModal: document.getElementById("configModal"),
    configModalBackdrop: document.getElementById("configModalBackdrop"),
    configModalClose: document.getElementById("configModalClose"),
    configModalCancel: document.getElementById("configModalCancel"),
    configModalSave: document.getElementById("configModalSave"),
    configModalMeta: document.getElementById("configModalMeta"),
    configNotice: document.getElementById("configNotice"),
    configSummary: document.getElementById("configSummary"),
    cfgAlertaAmareloMin: document.getElementById("cfgAlertaAmareloMin"),
    cfgAlertaVermelhoMin: document.getElementById("cfgAlertaVermelhoMin"),
    cfgAlertaPiscoMin: document.getElementById("cfgAlertaPiscoMin"),
    cfgFechadoViraDesatualizadoHoras: document.getElementById("cfgFechadoViraDesatualizadoHoras"),
    cfgDesatualizadoCriticoHoras: document.getElementById("cfgDesatualizadoCriticoHoras"),
    cfgAutoCloseOpenHours: document.getElementById("cfgAutoCloseOpenHours"),
    cfgAutoInactivateHours: document.getElementById("cfgAutoInactivateHours"),
    cfgPollingSeconds: document.getElementById("cfgPollingSeconds"),
    cfgAlertUnitHoursToggle: document.getElementById("cfgAlertUnitHoursToggle"),
  };
}

function setConfigModalHidden(hidden) {
  const el = getConfigModalElements();
  if (!el.configModal) return;
  el.configModal.hidden = hidden;
  document.body.classList.toggle('modalOpen', !hidden || !document.getElementById('teamFormModal')?.hidden);
}

function setConfigNotice(message = '', type = '') {
  const el = getConfigModalElements();
  if (!el.configNotice) return;
  const text = (message || '').trim();
  el.configNotice.hidden = !text;
  el.configNotice.textContent = text;
  el.configNotice.className = 'formNotice';
  if (type) el.configNotice.classList.add(type);
}

function formatMinToHoursText(min) {
  if (!min || min <= 0) return '-';
  const hrs = (min / 60).toFixed(1).replace('.0', '');
  return `⏱️ aprox. ${hrs} hora(s)`;
}

function toggleAlertUnit(useHours) {
  isAlertUnitHours = useHours;
  const el = getConfigModalElements();
  const labels = [
    document.getElementById("unitLabelAmarelo"),
    document.getElementById("unitLabelVermelho"),
    document.getElementById("unitLabelPisco")
  ];
  labels.forEach(lbl => {
    if (lbl) lbl.textContent = useHours ? 'h' : 'min';
  });

  const inputs = [el.cfgAlertaAmareloMin, el.cfgAlertaVermelhoMin, el.cfgAlertaPiscoMin];
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
  const el = getConfigModalElements();
  const rules = config?.rules || {};
  const isHours = Boolean(el.cfgAlertUnitHoursToggle && el.cfgAlertUnitHoursToggle.checked);

  if (el.cfgAlertaAmareloMin) {
    const minVal = rules.alertaAmareloMin ?? '';
    el.cfgAlertaAmareloMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }
  if (el.cfgAlertaVermelhoMin) {
    const minVal = rules.alertaVermelhoMin ?? '';
    el.cfgAlertaVermelhoMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }
  if (el.cfgAlertaPiscoMin) {
    const minVal = rules.alertaPiscoMin ?? '';
    el.cfgAlertaPiscoMin.value = (isHours && minVal) ? (minVal / 60).toFixed(1).replace('.0', '') : minVal;
  }

  if (el.cfgAutoCloseOpenHours) el.cfgAutoCloseOpenHours.value = rules.autoCloseOpenHours ?? '';
  if (el.cfgFechadoViraDesatualizadoHoras) {
    el.cfgFechadoViraDesatualizadoHoras.value = rules.autoDesatualizaFechadoHours ?? rules.fechadoViraDesatualizadoHoras ?? '';
  }
  if (el.cfgDesatualizadoCriticoHoras) el.cfgDesatualizadoCriticoHoras.value = rules.desatualizadoCriticoHoras ?? '';
  if (el.cfgAutoInactivateHours) el.cfgAutoInactivateHours.value = rules.autoInactivateHours ?? '';
  if (el.cfgPollingSeconds) el.cfgPollingSeconds.value = config?.pollingSeconds ?? '';
  syncConfigSummary();
}

function collectConfigPayload() {
  const el = getConfigModalElements();
  const isHours = Boolean(el.cfgAlertUnitHoursToggle && el.cfgAlertUnitHoursToggle.checked);

  const parseAlertMin = (inp) => {
    let val = parseFloat(inp?.value || 0);
    if (isNaN(val)) return 0;
    return isHours ? Math.round(val * 60) : Math.round(val);
  };

  return {
    pollingSeconds: Number(el.cfgPollingSeconds?.value || 0),
    rules: {
      alertaAmareloMin: parseAlertMin(el.cfgAlertaAmareloMin),
      alertaVermelhoMin: parseAlertMin(el.cfgAlertaVermelhoMin),
      alertaPiscoMin: parseAlertMin(el.cfgAlertaPiscoMin),
      autoCloseOpenHours: Number(el.cfgAutoCloseOpenHours?.value || 0),
      autoDesatualizaFechadoHours: Number(el.cfgFechadoViraDesatualizadoHoras?.value || 0),
      desatualizadoCriticoHoras: Number(el.cfgDesatualizadoCriticoHoras?.value || 0),
      autoInactivateHours: Number(el.cfgAutoInactivateHours?.value || 0),
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
  const el = getConfigModalElements();
  const inputs = [
    el.cfgAlertaAmareloMin, el.cfgAlertaVermelhoMin, el.cfgAlertaPiscoMin,
    el.cfgAutoCloseOpenHours, el.cfgFechadoViraDesatualizadoHoras,
    el.cfgDesatualizadoCriticoHoras, el.cfgAutoInactivateHours, el.cfgPollingSeconds
  ];
  inputs.forEach(inp => {
    if (inp && !inp.dataset.listenerAttached) {
      inp.dataset.listenerAttached = 'true';
      inp.addEventListener('input', syncConfigSummary);
    }
  });

  const toggleSwitch = el.cfgAlertUnitHoursToggle;
  if (toggleSwitch && !toggleSwitch.dataset.listenerAttached) {
    toggleSwitch.dataset.listenerAttached = 'true';
    toggleSwitch.addEventListener('change', (e) => {
      toggleAlertUnit(e.target.checked);
    });
  }
}

function openConfigModal(currentCfg) {
  const el = getConfigModalElements();
  fillConfigForm(currentCfg || window.monitorState?.getConfig?.() || {});
  attachConfigInputListeners();
  attachCrashReportListeners();
  setConfigNotice('');
  loadCrashReports();

  if (el.configModalMeta) el.configModalMeta.textContent = 'Edite os tempos e confirme para aplicar.';
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

async function saveConfigModal(onConfigSaved) {
  if (configSaveInFlight) return;
  const el = getConfigModalElements();
  const payload = collectConfigPayload();
  configSaveInFlight = true;
  if (el.configModalMeta) el.configModalMeta.textContent = 'Salvando configurações...';
  setConfigNotice('');

  try {
    const response = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || 'Falha ao salvar as configurações.');
    
    const updatedCfg = {
      defaultEmpresa: data.defaultEmpresa || window.monitorState?.getConfig?.()?.defaultEmpresa || '',
      pollingSeconds: data.pollingSeconds,
      rules: data.rules || {},
    };

    setConfigNotice(data?.message || 'Configurações salvas com sucesso.', 'success');
    if (el.configModalMeta) el.configModalMeta.textContent = 'Configurações salvas com sucesso.';

    if (typeof onConfigSaved === 'function') {
      await onConfigSaved(updatedCfg);
    } else if (window.monitorState?.reload) {
      await window.monitorState.reload();
    }

    setTimeout(() => {
      closeConfigModal();
    }, 600);
  } catch (error) {
    setConfigNotice(error?.message || 'Não foi possível salvar as configurações.', 'error');
    if (el.configModalMeta) el.configModalMeta.textContent = 'Falha ao salvar';
  } finally {
    configSaveInFlight = false;
  }
}

window.monitorConfig = {
  setConfigModalHidden,
  setConfigNotice,
  formatMinToHoursText,
  toggleAlertUnit,
  fillConfigForm,
  collectConfigPayload,
  syncConfigSummary,
  attachConfigInputListeners,
  openConfigModal,
  closeConfigModal,
  saveConfigModal,
  loadCrashReports,
  clearAllCrashReports,
  attachCrashReportListeners,
};
