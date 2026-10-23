// -----------------------------------------------------------------------------
// Arquivo : static/js/monitor_utils.js
// Objetivo: Utilitários puros de texto, escape de HTML, formatação de datas,
//           parsing de horários de serviço e vigência de jornada (Art. 66/67).
// -----------------------------------------------------------------------------

function safeUpper(v) {
  return (v || "").toString().trim().toUpperCase();
}

function escapeHtml(value) {
  return (value ?? "")
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function detailValue(value) {
  if (value === null || value === undefined) return "-";
  const text = String(value).trim();
  return text || "-";
}

function hasMeaningfulValue(value) {
  const text = detailValue(value);
  return text !== '-' && safeUpper(text) !== 'NULL';
}

function fmtDateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("pt-BR");
}

function fmtTimeOnly(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleTimeString("pt-BR");
}

function isDateToday(d) {
  if (!d || !(d instanceof Date) || isNaN(d.getTime())) return false;
  const now = new Date();
  return d.getDate() === now.getDate() &&
         d.getMonth() === now.getMonth() &&
         d.getFullYear() === now.getFullYear();
}

function fmtLastContact(iso, source) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const time = d.toLocaleTimeString("pt-BR", { hour: '2-digit', minute: '2-digit' });
  const srcSuffix = source ? ` (${source})` : "";
  if (isDateToday(d)) {
    return `${time}${srcSuffix}`;
  }
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return `${day}/${month} - ${time}${srcSuffix}`;
}

function parseServiceDate(value, service, item) {
  if (!value) return null;
  if (value instanceof Date && !isNaN(value.getTime())) return value;
  if (typeof value === 'number' || /^\d{10,13}$/.test(String(value).trim())) {
    const num = Number(value);
    const ms = num > 100000000000 ? num : num * 1000;
    const d = new Date(ms);
    if (!isNaN(d.getTime())) return d;
  }
  const str = String(value).trim();
  if (!str) return null;
  if (str.includes('-') && (str.includes('T') || str.includes(' '))) {
    const d = new Date(str.replace(' ', 'T'));
    if (!isNaN(d.getTime())) return d;
  }
  const matchTime = str.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (matchTime) {
    const h = parseInt(matchTime[1], 10);
    const m = parseInt(matchTime[2], 10);
    const s = matchTime[3] ? parseInt(matchTime[3], 10) : 0;
    const refIso = service?.inicioIso || service?.fimIso || service?.baseDay || item?.rotalogSnapshot?.updatedAtIso || item?.lastContact || item?.updatedAt;
    let baseDate = new Date();
    if (refIso) {
      if (typeof refIso === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(refIso.trim())) {
        const parts = refIso.trim().split('-');
        baseDate = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      } else {
        const parsedRef = new Date(refIso);
        if (!isNaN(parsedRef.getTime())) baseDate = parsedRef;
      }
    }
    return new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate(), h, m, s);
  }
  const d = new Date(str);
  return !isNaN(d.getTime()) ? d : null;
}

function formatEffectiveServiceTime(rawTime, service, item) {
  if (!rawTime) return null;
  const d = parseServiceDate(rawTime, service, item);
  if (!d) {
    if (/^\d{2}:\d{2}$/.test(String(rawTime).trim())) return String(rawTime).trim();
    return null;
  }
  const timeStr = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (isDateToday(d)) {
    return timeStr;
  }
  const dd = String(d.getDate()).padStart(2, '0');
  const mon = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mon} - ${timeStr}`;
}

function latestCommunicationAt(item) {
  const snapshot = item?.rotalogSnapshot || {};
  const candidates = [
    item?.operacional?.atualizadoEm,
    snapshot.updatedAt,
    snapshot.updatedAtIso,
    snapshot.eventTimestampMs,
    item?.updatedAt,
    item?.lastContact,
  ];
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

function isIsoNewer(candidateIso, currentIso) {
  if (!candidateIso) return false;
  const candidate = new Date(candidateIso);
  if (Number.isNaN(candidate.getTime())) return false;
  if (!currentIso) return true;
  const current = new Date(currentIso);
  if (Number.isNaN(current.getTime())) return true;
  return candidate.getTime() > current.getTime();
}

function addHours(dateLike, hours) {
  if (!dateLike) return null;
  const dt = dateLike instanceof Date ? new Date(dateLike.getTime()) : new Date(dateLike);
  if (Number.isNaN(dt.getTime())) return null;
  dt.setHours(dt.getHours() + hours);
  return dt;
}

function getArt66EndAt(item, shown) {
  const normState = window.monitorCards?.normalizedState ? window.monitorCards.normalizedState(shown) : safeUpper(shown);
  if (normState !== "FECHADO") return null;
  const closedTime = item?.turnoFim || item?.turno?.fim || item?.fimIso || item?.updatedAt;
  if (!closedTime) return null;
  const hours = item.lastWasDescansoSemanal ? 24 : 11;
  return addHours(closedTime, hours);
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

function fmtMMSS(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function fmtAgeFromMinutes(mins) {
  if (!Number.isFinite(mins) || mins < 0) return "-";
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  const remMin = mins % 60;
  if (hours < 24) return `${hours}h ${String(remMin).padStart(2, "0")}m`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return `${days}d ${remHours}h`;
}

// Inicializa o namespace monitorUtils no window
window.monitorUtils = window.monitorUtils || {};
Object.assign(window.monitorUtils, {
  safeUpper,
  escapeHtml,
  fmtDateTime,
  fmtTimeOnly,
  isDateToday,
  fmtLastContact,
  parseServiceDate,
  formatEffectiveServiceTime,
  latestCommunicationAt,
  isIsoNewer,
  addHours,
  getArt66EndAt,
  isArt66Active,
  fmtHourMinute,
  fmtMMSS,
  fmtAgeFromMinutes,
  detailValue,
  hasMeaningfulValue,
});
