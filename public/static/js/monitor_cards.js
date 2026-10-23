// -----------------------------------------------------------------------------
// Arquivo : static/js/monitor_cards.js
// Objetivo: Lógica de apresentação dos cards de equipes, mapeamento de estados,
//           timeline de DDS com fotos em modal, hover panels e DOM incremental.
// -----------------------------------------------------------------------------

function normalizedState(state) {
  const raw = (window.monitorUtils?.safeUpper || safeUpper)(state);
  if (raw === "EXECUCAO") return "ABERTO";
  if (raw === "ESPECIAL" || raw === "DESLOCAMENTO") return "DESLOCAMENTO_ESPECIAL";
  return raw;
}

function stateLabel(state) {
  switch (normalizedState(state)) {
    case "DESLOCAMENTO_ESPECIAL": return "DESLOCAMENTO ESPECIAL";
    default: return normalizedState(state);
  }
}

function getOrigemChar(item) {
  return item?.rotalogSnapshot ? "R" : "D";
}

function getOrigemTitle(item) {
  const char = getOrigemChar(item);
  if (char === "R") return "Fonte operacional: JSON/cache do Rotalog";
  return "Sem snapshot operacional do Rotalog";
}

function serviceEventTimestampMs(value, referenceIso) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return value > 100000000000 ? value : value * 1000;
  const raw = String(value).trim();
  if (!raw) return null;
  if (/^\d{2}:\d{2}(:\d{2})?$/.test(raw)) {
    const reference = new Date(referenceIso || Date.now());
    const base = Number.isNaN(reference.getTime()) ? new Date() : reference;
    const [hours, minutes, seconds = '0'] = raw.split(':');
    base.setHours(Number(hours), Number(minutes), Number(seconds), 0);
    return base.getTime();
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
}

function serviceDisplayTime(rawValue, service, item, status) {
  if (status === 'CONCLUSAO') return rawValue;

  const serviceMs = serviceEventTimestampMs(rawValue, item?.updatedAt);
  const communicationRaw = item?.operacional?.atualizadoEm
    || item?.rotalogSnapshot?.updatedAtIso
    || item?.rotalogSnapshot?.eventTimestampMs
    || item?.updatedAt;
  const communicationMs = serviceEventTimestampMs(communicationRaw, item?.updatedAt);
  if (!serviceMs || !communicationMs) return rawValue;

  const localDay = (timestamp) => new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo',
  }).format(new Date(timestamp));
  const serviceIsFromAnotherDay = localDay(serviceMs) !== localDay(communicationMs);
  const serviceIsInFuture = serviceMs > communicationMs;
  return serviceIsFromAnotherDay || serviceIsInFuture ? communicationRaw : rawValue;
}

function getRotalogService(item) {
  if (!item?.rotalogSnapshot) return null;
  const snapshot = item.rotalogSnapshot;
  const current = snapshot.ordensServico?.atual || snapshot.atividadeAtual || null;
  const completed = Array.isArray(snapshot.ordensServico?.historico)
    ? snapshot.ordensServico.historico
    : (Array.isArray(snapshot.ssExecutadas) ? snapshot.ssExecutadas : []);
  const service = current || (completed.length ? completed[completed.length - 1] : null);
  if (!service) return null;

  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  const rawStatus = sUpper(service.statusAtual || service.status || item?.atividadeStatus || item?.monitorStatus);
  const statusChar = rawStatus === 'DESLOCAMENTO'
    ? 'D'
    : rawStatus === 'EXECUCAO'
      ? 'E'
      : rawStatus === 'CONCLUSAO'
        ? 'C'
        : '';
  const realProtocol = service.protocolo || service.ssId || '';
  const serviceId = service.protocoloBruto || service.ssId || '';
  const serviceType = service.tipo || '';
  const hasDistinctServiceId = serviceId && String(serviceId) !== String(serviceType);
  const identifier = realProtocol || (hasDistinctServiceId ? serviceId : serviceType);
  const identifierLabel = (realProtocol || hasDistinctServiceId) ? 'SS' : 'Tipo';
  if (!identifier) return null;
  const category = sUpper(service.categoria || service.category || '');
  const protocol = realProtocol && String(realProtocol) !== String(serviceType)
    ? String(realProtocol)
    : '';
  const conclusionAtMs = rawStatus === 'CONCLUSAO'
    ? serviceEventTimestampMs(
        service.retornoIso || service.fimIso || service.terminoIso || service.retorno || service.termino,
        snapshot.updatedAt || snapshot.updatedAtIso || item?.lastContact || item?.updatedAt
      )
    : null;
  const conclusionOlderThanTenMinutes = Boolean(
    conclusionAtMs && Date.now() - conclusionAtMs > 10 * 60 * 1000
  );
  const statusLabel = rawStatus === 'DESLOCAMENTO'
    ? 'Deslocamento'
    : rawStatus === 'EXECUCAO'
      ? 'Execução'
      : rawStatus === 'CONCLUSAO'
        ? 'Conclusão'
        : rawStatus;

  let effectiveRawTime = null;
  let effectiveStageLabel = '';

  if (rawStatus === 'EXECUCAO' || statusChar === 'E') {
    effectiveStageLabel = 'Início da Execução';
    let transitionTime = null;
    if (Array.isArray(service.transitions)) {
      const tr = [...service.transitions].reverse().find(t => sUpper(t?.status) === 'EXECUCAO');
      if (tr) transitionTime = tr.hora || tr.timestampMs;
    }
    effectiveRawTime = service.inicioExecucao || transitionTime || service.execucao || service.inicioHora || service.inicioIso || service.inicioDeslocamento || service.inicio;
  } else if (rawStatus === 'DESLOCAMENTO' || statusChar === 'D') {
    effectiveStageLabel = 'Início do Deslocamento';
    let transitionTime = null;
    if (Array.isArray(service.transitions)) {
      const tr = [...service.transitions].reverse().find(t => sUpper(t?.status) === 'DESLOCAMENTO');
      if (tr) transitionTime = tr.hora || tr.timestampMs;
    }
    effectiveRawTime = service.inicioDeslocamento || transitionTime || service.deslocamento || service.inicioHora || service.inicioIso || service.inicio;
  } else if (rawStatus === 'CONCLUSAO' || statusChar === 'C') {
    effectiveStageLabel = 'Conclusão';
    let transitionTime = null;
    if (Array.isArray(service.transitions)) {
      const tr = [...service.transitions].reverse().find(t => sUpper(t?.status) === 'CONCLUSAO');
      if (tr) transitionTime = tr.hora || tr.timestampMs;
    }
    effectiveRawTime = service.termino || service.fimExecucao || service.retorno || transitionTime || service.fimIso || service.retornoIso || service.terminoIso || service.inicioExecucao || service.inicioIso;
  } else {
    effectiveStageLabel = 'Atividade';
    effectiveRawTime = service.inicioExecucao || service.inicioDeslocamento || service.inicioHora || service.inicioIso || service.termino || service.fimIso;
  }

  effectiveRawTime = serviceDisplayTime(effectiveRawTime, service, item, rawStatus);

  const fmtEff = window.monitorUtils?.formatEffectiveServiceTime || formatEffectiveServiceTime;
  const effectiveTimeLabel = fmtEff(effectiveRawTime, service, item);

  let timeTooltip = '';
  if (effectiveStageLabel && effectiveTimeLabel) {
    const extraParts = [];
    if (rawStatus === 'EXECUCAO') {
      if (service.inicioDeslocamento && service.inicioDeslocamento !== effectiveRawTime) {
        extraParts.push(`Deslocamento: ${service.inicioDeslocamento}`);
      }
    } else if (rawStatus === 'CONCLUSAO') {
      if (service.inicioExecucao) {
        extraParts.push(`Execução: ${service.inicioExecucao}`);
      }
      if (service.inicioDeslocamento) {
        extraParts.push(`Deslocamento: ${service.inicioDeslocamento}`);
      }
    }
    const extraStr = extraParts.length ? ` (${extraParts.join(' • ')})` : '';
    timeTooltip = `${effectiveStageLabel}: ${effectiveTimeLabel}${extraStr}`;
  }

  const latitude = service.latitude ?? item.latitude ?? null;
  const longitude = service.longitude ?? item.longitude ?? null;

  return {
    identifier: String(identifier), identifierLabel, statusChar, statusLabel, rawStatus,
    category,
    serviceType: String(serviceType || identifier),
    protocol,
    conclusionOlderThanTenMinutes,
    effectiveRawTime,
    effectiveStageLabel,
    effectiveTimeLabel,
    timeTooltip,
    latitude,
    longitude,
  };
}

function operationalTimestamp(value) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return value > 100000000000 ? value : value * 1000;
  const raw = String(value).trim();
  if (!raw) return null;
  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw);
    return numeric > 100000000000 ? numeric : numeric * 1000;
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
}

function operationalTimeLabel(value) {
  const timestamp = operationalTimestamp(value);
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function getTurnSummary(item, shown) {
  if (shown !== 'FECHADO' && shown !== 'INTERVALO') return null;
  const snapshot = item?.rotalogSnapshot || {};
  const turno = snapshot?.jornada?.turno || snapshot?.turno || item?.turno || {};
  const intervals = Array.isArray(snapshot.intervalos) ? snapshot.intervalos : [];
  const latestInterval = intervals.length ? intervals[intervals.length - 1] : (snapshot.intervalo || {});
  const openedAt = turno.inicio_iso || turno.inicioIso || turno.inicio_ms || turno.inicio || item?.turnoInicio || item?.openedAtClientMs;
  const closedAt = turno.fim_iso || turno.fimIso || turno.fim_ms || turno.fim || item?.turnoFim || item?.closedAtClientMs || item?.updatedAt;
  const intervalAt = latestInterval.inicioIso || latestInterval.inicio_iso || latestInterval.inicio_ms || latestInterval.inicio || item?.updatedAt;
  const executedServices = Array.isArray(snapshot.ssExecutadas)
    ? snapshot.ssExecutadas.length
    : Number(snapshot?.ordensServico?.totalConcluidos ?? item?.totalConcluidos ?? snapshot.ssExecutadasCount ?? item?.ssExecutadasCount ?? 0);
  return {
    title: shown === 'FECHADO' ? 'ÚLTIMO TURNO' : 'TURNO ATUAL',
    openedAt: operationalTimeLabel(openedAt),
    endLabel: shown === 'FECHADO' ? 'Fechamento' : 'Intervalo',
    endAt: operationalTimeLabel(shown === 'FECHADO' ? closedAt : intervalAt),
    executedServices,
  };
}

function vehicleFrameClass(state) {
  switch (normalizedState(state)) {
    case "ABERTO": return "vfGreen";
    case "INTERVALO": return "vfYellow";
    case "DESLOCAMENTO_ESPECIAL": return "vfBlue";
    case "FECHADO": return "vfRed";
    case "DESATUALIZADO": return "vfGray";
    default: return "vfGray";
  }
}

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

function borderClass(alerta) {
  const sUpper = window.monitorUtils?.safeUpper || safeUpper;
  switch (sUpper(alerta)) {
    case "YELLOW": return "tileBorderYellow";
    case "RED": return "tileBorderRed";
    case "PULSE": return "tileBorderPulse";
    default: return "";
  }
}

function participantsHtml(list, motorista, coringas, extraClass = "") {
  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
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

    return `<li style="display:flex; align-items:center;">${esc(name)}${iconsHtml}</li>`;
  }).join("")}</ul>`;
}

function hoverRows(item) {
  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
  const fmtDT = window.monitorUtils?.fmtDateTime || fmtDateTime;
  const latestComm = window.monitorUtils?.latestCommunicationAt || latestCommunicationAt;
  const hasMeaningful = window.monitorUtils?.hasMeaningfulValue || hasMeaningfulValue;
  const dVal = window.monitorUtils?.detailValue || detailValue;

  const rows = [];
  rows.push(`<div class="hoverRow"><span>Atualizacao Rotalog</span><strong>${esc(fmtDT(latestComm(item)))}</strong></div>`);
  const rotalogService = getRotalogService(item);
  if (rotalogService?.effectiveTimeLabel && rotalogService.effectiveStageLabel) {
    rows.push(`<div class="hoverRow"><span>${esc(rotalogService.effectiveStageLabel)}</span><strong>${esc(rotalogService.effectiveTimeLabel)}</strong></div>`);
  }
  if (rotalogService?.protocol) rows.push(`<div class="hoverRow"><span>SS/NOC</span><strong>${esc(rotalogService.protocol)}</strong></div>`);
  const totalConcluidos = item.totalConcluidos ?? item.rotalogSnapshot?.ordensServico?.totalConcluidos;
  if (totalConcluidos !== undefined && totalConcluidos !== null) {
    rows.push(`<div class="hoverRow"><span>Serviços Concluídos (Hoje)</span><strong>${esc(String(totalConcluidos))}</strong></div>`);
  }
  const colab = item.colaborador ?? item.rotalogSnapshot?.conexao?.colaborador;
  if (colab) {
    rows.push(`<div class="hoverRow"><span>Colaborador</span><strong>${esc(colab)}</strong></div>`);
  }
  const lat = item.latitude ?? rotalogService?.latitude;
  const lon = item.longitude ?? rotalogService?.longitude;
  if (lat && lon) {
    rows.push(`<div class="hoverRow"><span>GPS</span><strong><a class="gpsMapLink" href="https://maps.google.com/?q=${encodeURIComponent(lat)},${encodeURIComponent(lon)}" target="_blank" rel="noopener noreferrer">📍 Ver no Mapa</a></strong></div>`);
  }
  if (normalizedState(item.estado) === 'DESLOCAMENTO_ESPECIAL' && hasMeaningful(item.motivo)) {
    rows.push(`<div class="hoverRow"><span>Motivo</span><strong>${esc(dVal(item.motivo))}</strong></div>`);
  }
  return rows.join('');
}

function normalizeDdsEntry(value) {
  if (value === true) return "ok";
  if (value === false) return "fail";
  const raw = (window.monitorUtils?.safeUpper || safeUpper)(value);
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

  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
  const raw = Array.isArray(item.ddsHistory)
    ? item.ddsHistory
    : Array.isArray(item.ddsSequence)
      ? item.ddsSequence
      : [];
  const days = Array.isArray(item.ddsDays) ? item.ddsDays : [];

  let dots = "";

  if (showDayLabels) {
    const numWeeks = maxItems > 14 ? 3 : 2;
    const totalDays = numWeeks * 7;

    const todayStr = days.length > 0 ? days[days.length - 1] : new Date().toISOString().split('T')[0];
    const todayParts = todayStr.split("-");
    const todayDate = new Date(Number(todayParts[0]), Number(todayParts[1]) - 1, Number(todayParts[2]));

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
        <span class="ddsDayDot${hasPhotoClass}" title="${esc(tooltip)}" aria-label="${esc(tooltip)}" ${photoUrl ? `data-photo="${esc(photoUrl)}"` : ""}>
          <span class="ddsDayLabel">${esc(dayLabel)}</span>
          <span class="ddsDotWrap${isToday ? " isCurrent" : ""}">
            <span class="ddsDot ddsDot--${status}${isToday ? " ddsDot--current" : ""}"></span>
          </span>
        </span>
      `);
    }
    dots = calendarDots.join("");
  } else {
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
        <span class="ddsDotWrap${isCurrent ? " isCurrent" : ""}${hasPhotoClass}" title="${esc(tooltip)}" aria-label="${esc(tooltip)}" ${photoUrl ? `data-photo="${esc(photoUrl)}"` : ""}>
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
          <span class="ddsLabel">${esc(label)}</span>
          <span class="ddsHint">${esc(actualHintText)}</span>
        </div>
      ` : ""}
      <div class="${trackClass}" role="list">
        ${dots}
      </div>
    </div>
  `;
}

function formatStatusWithTime(item, shown, art66Active, art66EndAt) {
  const lbl = stateLabel(shown);
  const normState = normalizedState(shown);
  const snapshot = item?.rotalogSnapshot || {};
  const turno = snapshot?.jornada?.turno || snapshot?.turno || item?.turno || {};
  const intervalos = Array.isArray(snapshot?.intervalos) ? snapshot.intervalos : [];
  const latestInterval = intervalos.length ? intervalos[intervalos.length - 1] : (snapshot?.intervalo || {});

  let dateLike = null;
  if (normState === "ABERTO" || normState === "EXECUCAO" || normState === "DESLOCAMENTO" || normState === "DESLOCAMENTO_ESPECIAL") {
    dateLike = turno.inicio_iso || turno.inicioIso || turno.inicio || item?.turnoInicio || item?.inicioIso || item?.openedAtClientMs || item?.updatedAt;
  } else if (normState === "FECHADO") {
    dateLike = turno.fim_iso || turno.fimIso || turno.fim || item?.turnoFim || item?.fimIso || item?.closedAtClientMs || item?.updatedAt;
  } else if (normState === "INTERVALO") {
    dateLike = latestInterval.inicioIso || latestInterval.inicio_iso || latestInterval.inicio || item?.updatedAt;
  } else {
    dateLike = item?.lastContact || item?.updatedAt;
  }

  if (!dateLike) {
    return lbl;
  }

  const dt = dateLike instanceof Date ? dateLike : new Date(dateLike);
  if (Number.isNaN(dt.getTime())) {
    return lbl;
  }

  const today = new Date();
  const isToday = dt.getDate() === today.getDate() &&
                  dt.getMonth() === today.getMonth() &&
                  dt.getFullYear() === today.getFullYear();

  const timeStr = dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const dd = String(dt.getDate()).padStart(2, "0");
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dayMonthStr = `${dd}/${mm}`;

  const fmtHM = window.monitorUtils?.fmtHourMinute || fmtHourMinute;

  if (normState === "FECHADO" && art66Active) {
    const isBeforeSeven = art66EndAt && art66EndAt.getHours() < 7;
    const art66EndLabel = isBeforeSeven ? "" : fmtHM(art66EndAt);
    if (!isBeforeSeven && art66EndLabel) {
      if (isToday) {
        return `${lbl}: ${timeStr} → ${art66EndLabel}`;
      } else {
        return `${lbl}: ${dayMonthStr} ${timeStr} → ${art66EndLabel}`;
      }
    }
  }

  if (isToday) {
    return `${lbl}: ${timeStr}`;
  } else {
    return `${lbl}: ${dayMonthStr} ${timeStr}`;
  }
}

function tile(item) {
  const esc = window.monitorUtils?.escapeHtml || escapeHtml;
  const dVal = window.monitorUtils?.detailValue || detailValue;
  const isArt66 = window.monitorUtils?.isArt66Active || isArt66Active;
  const getArt66End = window.monitorUtils?.getArt66EndAt || getArt66EndAt;
  const fmtHM = window.monitorUtils?.fmtHourMinute || fmtHourMinute;
  const latestComm = window.monitorUtils?.latestCommunicationAt || latestCommunicationAt;
  const fmtLast = window.monitorUtils?.fmtLastContact || fmtLastContact;
  const getViewModeFn = window.monitorFilters?.getViewMode || (window.monitorState?.getViewMode) || getViewMode;

  const shown = normalizedState(item.estado);
  const border = borderClass(item.alerta);
  const stateCard = stateCardClass(shown);
  const crit = item.critico === true && shown === "DESATUALIZADO";
  const equipe = dVal(item.equipe);
  const teamKey = dVal(item.teamKey || item.equipe);
  const veiculoOperacional = item?.operacional?.veiculo
    || item?.rotalogSnapshot?.veiculo
    || item?.rotalogSnapshot?.conexao?.veiculo
    || item?.operacional?.identificadorEquipamento
    || item?.rotalogSnapshot?.identificadorEquipamento
    || item?.rotalogSnapshot?.conexao?.identificadorEquipamento;
  const veiculoLabel = veiculoOperacional ? String(veiculoOperacional).trim() : "-";
  const participantes = participantsHtml(item.participantes, item.motorista, item.coringas, 'hoverParticipantsList');
  const details = hoverRows(item);
  const statusLabel = stateLabel(shown);
  const art66Active = isArt66(item, shown);
  const art66EndAt = getArt66End(item, shown);
  const isBeforeSeven = art66EndAt && art66EndAt.getHours() < 7;
  const art66EndLabel = isBeforeSeven ? "" : fmtHM(art66EndAt);

  const statusLineFormatted = formatStatusWithTime(item, shown, art66Active, art66EndAt);

  const badgeLabel = item.lastWasDescansoSemanal ? "ART 67" : "ART 66";
  const badgeHtml = art66Active
    ? `<div class="topRightTab art66Tab"><div class="tabLine1">${badgeLabel}</div>${isBeforeSeven ? '' : `<div class="tabLine2">${esc(art66EndLabel)}</div>`}</div>`
    : (crit ? `<div class="topRightTab criticalTab"><div class="tabLine1">CRÍTICO</div></div>` : ``);

  const sectorSelector = document.getElementById('sectorSelector');
  const currentSector = (sectorSelector?.value || 'TODOS').toUpperCase();
  const unreadMap = item.unreadMap || {};

  let unreadCurrent = 0;
  if (currentSector === 'TODOS') {
    unreadCurrent = Object.values(unreadMap).reduce((a, b) => a + b, 0);
  } else {
    unreadCurrent = Number(unreadMap[currentSector] || 0);
  }

  const totalUnread = Object.values(unreadMap).reduce((a, b) => a + b, 0);

  let messageIconHtml = "";
  if (totalUnread > 0) {
    const iconClass = unreadCurrent > 0 ? "tileMessageIcon active" : "tileMessageIcon others";
    const title = unreadCurrent > 0
      ? `${unreadCurrent} mensagens para seu setor (${currentSector})`
      : `Mensagens pendentes para outros setores`;

    messageIconHtml = `
      <div class="${iconClass}" title="${esc(title)}">
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

  const lastContactLabel = fmtLast(latestComm(item));
  const tabletLabel = dVal(item.tablet || item?.rotalogSnapshot?.identificadorEquipamento);
  const origemTitle = getOrigemTitle(item);
  const rotalogService = getRotalogService(item);
  const turnSummary = getTurnSummary(item, shown);
  const serviceTimeDisplay = rotalogService?.effectiveTimeLabel || lastContactLabel;
  const serviceTimeTooltip = rotalogService?.timeTooltip
    ? (lastContactLabel && lastContactLabel !== '-' ? `${rotalogService.timeTooltip} • Sincronizado: ${lastContactLabel}` : rotalogService.timeTooltip)
    : (lastContactLabel ? `Última sincronização: ${lastContactLabel}` : '');
  const serviceStageHtml = rotalogService?.statusChar
    ? `<span class="contactServiceStage contactServiceStage--${rotalogService.statusChar}" title="${esc(rotalogService.statusLabel)}">${rotalogService.statusChar}</span>`
    : '';
  const serviceContactHtml = rotalogService ? `
    <div class="contactServiceDetails">
      <span class="contactServiceCategory">Tipo: ${esc(rotalogService.category === 'EMERGENCIA' ? 'Emergência' : rotalogService.category === 'COMERCIAL' ? 'Comercial' : rotalogService.category || '-')}</span>
      <span class="contactServiceType">${esc(rotalogService.serviceType)} ${serviceStageHtml}</span>
      <span class="contactServiceProtocol">${rotalogService.conclusionOlderThanTenMinutes ? 'SEM EXECUÇÃO' : rotalogService.protocol ? esc(rotalogService.protocol) : '&nbsp;'}</span>
    </div>` : `
    <div class="contactServiceDetails contactServiceDetails--empty">
      <span class="contactServiceCategory">&nbsp;</span>
      <span class="contactServiceType">&nbsp;</span>
      <span class="contactServiceProtocol">&nbsp;</span>
    </div>`;
  const turnSummaryHtml = turnSummary ? `
    <div class="turnSummary">
      <span class="turnSummaryTitle">${esc(turnSummary.title)}</span>
      <span class="turnSummaryLine"><span>Abertura</span><strong>${esc(turnSummary.openedAt)}</strong></span>
      <span class="turnSummaryLine"><span>${esc(turnSummary.endLabel)}</span><strong>${esc(turnSummary.endAt)}</strong></span>
      <span class="turnSummaryServices">${turnSummary.executedServices} ${turnSummary.executedServices === 1 ? 'serviço executado' : 'serviços executados'}</span>
    </div>` : '';

  const isTrash = typeof getViewModeFn === 'function' && getViewModeFn() === 'trash';
  const trashActions = isTrash ? `
    <div class="tileTrashActions">
      <button class="btnRestore" type="button" title="Restaurar Equipe" onclick="event.stopPropagation(); window.restoreTeam('${esc(teamKey)}')">Restaurar</button>
      <button class="btnPermanentDelete" type="button" title="Excluir Permanentemente" onclick="event.stopPropagation(); window.deleteTeamPermanent('${esc(teamKey)}')">Excluir Permanente</button>
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
  if (item.teamType && typeIcons[item.teamType]) {
    teamTypeIconHtml = `<img class="teamTypeBadgeIcon" src="${typeIcons[item.teamType]}" loading="lazy" alt="${esc(item.teamType)}" />`;
  }

  return `<article class="tile ${stateCard} ${border} ${isTrash ? 'isTrashTile' : ''}" tabindex="0" role="button" data-team="${esc(teamKey)}" aria-label="Equipe ${esc(equipe)}, status ${esc(statusLabel)}">
    ${badgeHtml}
    ${messageIconHtml}
    <div class="tileMain">
      <div class="tileTopRow">
        <div class="tileIdentity">
          <div class="tileTitleBlock tileTitleBlockFull">
            <div class="teamIdentityBadge" title="${esc(equipe)}">
              ${teamTypeIconHtml}
              <div class="teamIdentityContent">
                <div class="equipeCompact equipeCompactInline">${esc(equipe)}</div>
                <div class="veiculoLine">${esc(veiculoLabel)}</div>
                ${isTrash ? '' : `<div class="statusLineSub">${esc(statusLineFormatted)}</div>`}
              </div>
            </div>
          </div>
        </div>
      </div>
      ${isTrash ? trashActions : `
        <div class="tileContactRow" title="${esc(origemTitle)}">
           ${turnSummaryHtml || serviceContactHtml}
           ${turnSummary ? '' : `<span class="contactValue" title="${esc(serviceTimeTooltip)}">${esc(serviceTimeDisplay)}</span>`}
         </div>
        ${ddsRow}
      `}
    </div>
    ${isTrash ? '' : `
    <div class="tileHoverPanel" aria-hidden="true">
      <div class="tileHoverTop">
        <div class="tileHoverTitles">
          <div class="teamIdentityBadge teamIdentityBadgeHover" title="${esc(equipe)}">
            ${teamTypeIconHtml}
            <div class="teamIdentityTextHover">
              <div class="equipeCompact equipeCompactHover">${esc(equipe)}</div>
              <div class="tabletCompactHover">${esc(tabletLabel)}</div>
            </div>
          </div>
          <div class="badge badgeCompact">
            ${esc(stateLabel(shown))}
          </div>
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

function getTeamUpdateSignature(item) {
  return JSON.stringify({
    teamKey: item?.teamKey || item?.equipe || null,
    equipe: item?.equipe || null,
    teamType: item?.teamType || null,
    tablet: item?.tablet || null,
    estado: item?.estado || null,
    alerta: item?.alerta || null,
    critico: item?.critico || false,
    updatedAt: item?.updatedAt || null,
    lastContact: item?.lastContact || null,
    lastContactSource: item?.lastContactSource || null,
    ss: item?.ss || null,
    motivo: item?.motivo || null,
    participantes: item?.participantes || [],
    motorista: item?.motorista || null,
    coringas: item?.coringas || [],
    rotalogSnapshot: item?.rotalogSnapshot || null,
    unreadMap: item?.unreadMap || {},
    ddsHistory: item?.ddsHistory || [],
    ddsDays: item?.ddsDays || [],
    ddsTimes: item?.ddsTimes || {},
    ddsPhotos: item?.ddsPhotos || {},
    showDds: Boolean(document.getElementById("ddsToggle")?.checked),
  });
}

function syncHoverPlacement(tileEl) {
  const grid = document.getElementById("grid");
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

function updateSingleTeamCard(item) {
  const teamKey = item.teamKey || item.equipe;
  if (!teamKey) return;
  const cardId = `card-${teamKey.replace(/[^\w]/g, '_')}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  const coreData = getTeamUpdateSignature(item);
  const oldCore = card.dataset.core;
  const hasChanged = oldCore !== coreData;
  if (!hasChanged) return;

  const temp = document.createElement('div');
  temp.innerHTML = tile(item);
  const newCard = temp.firstElementChild;
  if (!newCard) return;
  newCard.id = cardId;
  newCard.dataset.core = coreData;
  newCard.style.order = card.style.order || '0';
  newCard.classList.add('flash-update');
  newCard.addEventListener('animationend', () => newCard.classList.remove('flash-update'), { once: true });
  newCard.addEventListener('mouseenter', () => syncHoverPlacement(newCard));
  card.replaceWith(newCard);
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
  modal.offsetHeight; // Força reflow
  modal.style.opacity = "1";
  img.style.transform = "scale(1)";
}

// Listener global para clique em bolinhas com foto
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

// Registra e expõe
window.monitorCards = {
  normalizedState,
  stateLabel,
  getOrigemChar,
  getOrigemTitle,
  serviceEventTimestampMs,
  getRotalogService,
  operationalTimestamp,
  operationalTimeLabel,
  getTurnSummary,
  vehicleFrameClass,
  stateCardClass,
  borderClass,
  participantsHtml,
  normalizeDdsEntry,
  formatDdsDayOnly,
  formatDdsFullDate,
  ddsStatusLabel,
  ddsSequenceHtml,
  showDdsPhotoModal,
  hoverRows,
  formatStatusWithTime,
  tile,
  getTeamUpdateSignature,
  updateSingleTeamCard,
  syncHoverPlacement,
};

// Extensão em window.monitorUtils para garantir contrato de team-form.js
window.monitorUtils = window.monitorUtils || {};
Object.assign(window.monitorUtils, {
  normalizedState,
  stateLabel,
  vehicleFrameClass,
  participantsHtml,
  renderDdsKpiHtml: ddsSequenceHtml,
});
