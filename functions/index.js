/* eslint-disable max-len, require-jsdoc */
const admin = require("firebase-admin");
const {onDocumentUpdated, onDocumentWritten} = require("firebase-functions/v2/firestore");
const {onTaskDispatched} = require("firebase-functions/v2/tasks");
const {setGlobalOptions} = require("firebase-functions/v2");
const {getFunctions} = require("firebase-admin/functions");
const zlib = require("zlib");

admin.initializeApp();
const db = admin.firestore();

// IMPORTANTE: mesma região do Firestore (default)
setGlobalOptions({region: "us-central1"});

function formatDate(ts) {
  const d = new Date(ts.seconds * 1000);
  return d.toLocaleDateString("pt-BR");
}

function formatTime(ts) {
  const d = new Date(ts.seconds * 1000);
  return d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSubmittedAt(ts) {
  const d = new Date(ts.seconds * 1000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}-${mm}-${yyyy}-${hh}:${min}`;
}

function calcTotalSeconds(presence, startedAt, endedAt, graceSeconds) {
  const segs = Array.isArray(presence.segments) ? presence.segments : [];
  const startedSec = startedAt.seconds;
  const endedSec = endedAt.seconds;

  const sessionDuration = Math.max(0, endedSec - startedSec);

  const lastSeenSec =
    presence.lastSeenAt && presence.lastSeenAt.seconds ?
      presence.lastSeenAt.seconds :
      null;

  // Ordena por join para evitar bagunça
  const ordered = segs
      .map((s) => ({join: s.join, leave: s.leave}))
      .filter((s) => typeof s.join === "number")
      .sort((a, b) => a.join - b.join);

  let total = 0;
  let prevLeave = startedSec; // para evitar sobreposição (cap simples)

  for (const seg of ordered) {
    const joinRaw = seg.join;

    // join nunca antes da sessão
    const join = Math.max(joinRaw, startedSec, prevLeave);

    let leave;
    if (typeof seg.leave === "number") {
      leave = seg.leave;
    } else {
      // segmento aberto: fecha por lastSeen + grace (com teto em endedAt)
      if (lastSeenSec != null) {
        leave = Math.min(endedSec, lastSeenSec + graceSeconds);
      } else {
        // fallback conservador: fecha no endedAt (ou pode ignorar)
        leave = endedSec;
      }
    }

    // leave nunca depois do fim
    leave = Math.min(leave, endedSec);

    if (leave > join) {
      total += (leave - join);
      prevLeave = leave;
    }
  }

  // teto absoluto: nunca maior que duração total da sessão
  return Math.min(total, sessionDuration);
}

// 🔥 FUNÇÃO PRINCIPAL
exports.onDdsSessionClosed = onDocumentUpdated(
    "DDS_Sessions/{ddsSessionId}",
    async (event) => {
      const before = event.data.before.data();
      const after = event.data.after.data();
      const ddsSessionId = event.params.ddsSessionId;

      if (!before || !after) return;

      // Só executa quando open -> closed
      if (before.status === "closed") return;
      if (after.status !== "closed") return;

      // Idempotência
      if (after.finalizedAt || after.ddsDocId) {
        console.log(`[${ddsSessionId}] já finalizado`);
        return;
      }

      if (!after.endedAt) {
        console.warn(
            `[${ddsSessionId}] status=closed sem endedAt`,
        );
        return;
      }

      console.log(`[${ddsSessionId}] consolidando presença`);

      const sessionRef = db
          .collection("DDS_Sessions")
          .doc(ddsSessionId);

      const presenceSnap = await sessionRef
          .collection("presence")
          .get();

      const minSeconds = after.minPresenceSeconds || 0;

      const validNames = [];

      presenceSnap.forEach((doc) => {
        const p = doc.data();
        const totalSeconds = calcTotalSeconds(p, after.startedAt, after.endedAt, 30);

        if (totalSeconds >= minSeconds) {
          validNames.push(p.displayName || doc.id);
        }
      });

      const sessionDuration =
      after.startedAt ?
        after.endedAt.seconds - after.startedAt.seconds :
        0;

      const ddsDoc = {
        equipe: after.equipe || "",
        tema: after.tema || "",
        eletricistas: validNames,
        headerDate: after.headerDate || "",
        headerTitle: after.headerTitle || "",
        trainingName: after.trainingName || "",
        dataConclusao: formatDate(after.endedAt),
        horaConclusao: formatTime(after.endedAt),
        submittedAt: formatSubmittedAt(after.endedAt),
        duracao: sessionDuration ?
        `${Math.floor(sessionDuration / 60)}m ${
          sessionDuration % 60
        }s` :
        "",
        origin: "online",
        ddsSessionId,
      };

      const ddsRef = await db.collection("DDS").add(ddsDoc);

      await sessionRef.update({
        finalizedAt: admin.firestore.FieldValue.serverTimestamp(),
        ddsDocId: ddsRef.id,
      });

      console.log(
          `[${ddsSessionId}] DDS criado: ${ddsRef.id}`,
      );
    },
);

// -----------------------------------------------------------------------------
// Torre de Controle dos DDS
// -----------------------------------------------------------------------------

const DDS_COLLECTION = process.env.DDS_COLLECTION_NAME || "DDS";
const DDS_COMPANY = process.env.DDS_EMPRESA_PADRAO || "ChicoEletro";
const DDS_COMPANY_KEY = process.env.DDS_COMPANY_KEY || "chicoeletro";
const DDS_BUCKET_NAME = process.env.DDS_BUCKET_NAME || "dds-treinamentos.firebasestorage.app";
const DDS_CONTROL_PREFIX = (process.env.DDS_CONTROL_PREFIX ||
  `dados/${DDS_COMPANY_KEY}/dds/controle`).replace(/^\/+|\/+$/g, "");
const DDS_PROJECTION_START_HOUR = Number(process.env.DDS_PROJECTION_START_HOUR || 7);
const DDS_TIMEZONE = process.env.DDS_TIMEZONE || "America/Sao_Paulo";

function extractIsoDay(value) {
  const match = String(value || "").match(/\b(\d{4}-\d{2}-\d{2})\b/);
  return match ? match[1] : null;
}

function normalizeTeamKey(value) {
  const withoutVariant = String(value || "").trim().toUpperCase().replace(/\(\d+\)\s*$/, "");
  if (!withoutVariant) return "";
  return withoutVariant
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^A-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
}

function localClockParts(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: DDS_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)]));
}

function nextProjectionSlot(now = new Date()) {
  const local = localClockParts(now);
  let delaySeconds;
  if (local.hour < DDS_PROJECTION_START_HOUR) {
    delaySeconds = ((DDS_PROJECTION_START_HOUR - local.hour) * 60 - local.minute) * 60 - local.second;
  } else {
    delaySeconds = (30 - (local.minute % 30)) * 60 - local.second;
  }
  delaySeconds = Math.max(1, delaySeconds);
  const scheduledAt = new Date(now.getTime() + delaySeconds * 1000);
  const slot = localClockParts(scheduledAt);
  const slotId = `${slot.year}${String(slot.month).padStart(2, "0")}${String(slot.day).padStart(2, "0")}` +
    `-${String(slot.hour).padStart(2, "0")}${String(slot.minute).padStart(2, "0")}`;
  return {delaySeconds, scheduledAt, slotId};
}

function completionIso(data, fallbackDay) {
  const submitted = String(data.submittedAt || "").trim();
  let match = submitted.match(/^(\d{2})[-/](\d{2})[-/](\d{4})\s*-?\s*(\d{1,2}):(\d{2})/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T${match[4].padStart(2, "0")}:${match[5]}:00-03:00`;
  }
  const dateText = String(data.dataConclusao || "").trim();
  const timeText = String(data.horaConclusao || "").trim();
  match = dateText.match(/^(\d{2})[-/](\d{2})[-/](\d{4})$/);
  const timeMatch = timeText.match(/^(\d{1,2}):(\d{2})/);
  if (match && timeMatch) {
    return `${match[3]}-${match[2]}-${match[1]}T${timeMatch[1].padStart(2, "0")}:${timeMatch[2]}:00-03:00`;
  }
  if (timeMatch) {
    return `${fallbackDay}T${timeMatch[1].padStart(2, "0")}:${timeMatch[2]}:00-03:00`;
  }
  return null;
}

function compactExecution(doc, day) {
  const data = doc.data() || {};
  const teamKey = normalizeTeamKey(data.equipe || data.teamName || data.teamKey);
  const trainingId = String(data.trainingName || data.trainingId || "").trim();
  const timestamp = completionIso(data, day) ||
    (doc.createTime && doc.createTime.toDate().toISOString()) || null;
  return {
    teamKey,
    trainingId,
    headerDate: day,
    completedAt: timestamp,
    submissionId: String(data.submissionId || doc.id),
  };
}

async function readCompressedJson(blob) {
  try {
    const [buffer] = await blob.download();
    const raw = buffer[0] === 0x1f && buffer[1] === 0x8b ? zlib.gunzipSync(buffer) : buffer;
    return JSON.parse(raw.toString("utf8"));
  } catch (error) {
    if (Number(error.code) !== 404) {
      console.warn(`Falha ao ler ${blob.name}: ${error.message}`);
    }
    return null;
  }
}

async function writeCompressedJson(blob, payload) {
  const raw = Buffer.from(JSON.stringify(payload), "utf8");
  const compressed = zlib.gzipSync(raw, {level: 9});
  await blob.save(compressed, {
    resumable: false,
    contentType: "application/json; charset=utf-8",
    metadata: {
      contentEncoding: "gzip",
      cacheControl: "no-cache, max-age=0",
    },
  });
}

async function rebuildDdsDay(day, revision) {
  const bucket = admin.storage().bucket(DDS_BUCKET_NAME);
  const dailyBlob = bucket.file(`${DDS_CONTROL_PREFIX}/daily/${day}.json.gz`);
  const previousDaily = await readCompressedJson(dailyBlob);
  const endKey = `${day}\uf8ff`;
  const snapshot = await db.collection(DDS_COLLECTION)
      .where("headerDate", ">=", day)
      .where("headerDate", "<=", endKey)
      .get();

  const grouped = new Map();
  snapshot.docs.forEach((doc) => {
    const execution = compactExecution(doc, day);
    if (!execution.teamKey) return;
    if (!grouped.has(execution.teamKey)) grouped.set(execution.teamKey, []);
    grouped.get(execution.teamKey).push(execution);
  });

  const teams = {};
  grouped.forEach((executions, teamKey) => {
    executions.sort((left, right) => String(left.completedAt || "").localeCompare(String(right.completedAt || "")));
    const first = executions[0];
    teams[teamKey] = {
      trainingId: first.trainingId,
      completedAt: first.completedAt,
      submissionId: first.submissionId,
      executionCount: executions.length,
      ...(executions.length > 1 ? {duplicateDetected: true} : {}),
    };
  });

  const generatedAt = new Date().toISOString();
  const dailyPayload = {
    schemaVersion: 1,
    company: DDS_COMPANY,
    date: day,
    generatedAt,
    revision,
    totalTeams: Object.keys(teams).length,
    teams,
  };
  await writeCompressedJson(dailyBlob, dailyPayload);

  const previousTeams = Object.keys((previousDaily && previousDaily.teams) || {});
  const affectedTeams = new Set([...previousTeams, ...Object.keys(teams)]);
  const month = day.slice(0, 7);
  for (const teamKey of affectedTeams) {
    const monthlyBlob = bucket.file(`${DDS_CONTROL_PREFIX}/monthly/${month}/${teamKey}.json.gz`);
    const previousMonthly = await readCompressedJson(monthlyBlob);
    const executions = {...((previousMonthly && previousMonthly.executions) || {})};
    Object.keys(executions).forEach((trainingId) => {
      if (executions[trainingId] && executions[trainingId].headerDate === day) delete executions[trainingId];
    });
    const dailyExecution = teams[teamKey];
    if (dailyExecution && dailyExecution.trainingId) {
      executions[dailyExecution.trainingId] = {
        headerDate: day,
        completedAt: dailyExecution.completedAt,
        submissionId: dailyExecution.submissionId,
      };
    }
    await writeCompressedJson(monthlyBlob, {
      schemaVersion: 1,
      company: DDS_COMPANY,
      teamKey,
      month,
      generatedAt,
      executions,
    });
  }
  console.log(`Torre DDS ${day}: ${snapshot.size} documentos, ${Object.keys(teams).length} equipes.`);
}

exports.onDdsProjectionSourceWritten = onDocumentWritten(
    {document: `${DDS_COLLECTION}/{submissionId}`, retry: true},
    async (event) => {
      const beforeData = event.data.before.exists ? (event.data.before.data() || {}) : {};
      const afterData = event.data.after.exists ? (event.data.after.data() || {}) : {};
      const days = new Set([
        extractIsoDay(beforeData.headerDate),
        extractIsoDay(afterData.headerDate),
      ].filter(Boolean));
      if (!days.size) {
        console.warn(`[${event.params.submissionId}] DDS sem headerDate ISO; projeção ignorada.`);
        return;
      }

      const slot = nextProjectionSlot();
      const windowRef = db.collection("dds_projection_windows").doc(slot.slotId);
      let createTask = false;
      await db.runTransaction(async (transaction) => {
        const windowSnap = await transaction.get(windowRef);
        days.forEach((day) => {
          const pendingRef = db.collection("dds_projection_pending").doc(day);
          transaction.set(pendingRef, {
            day,
            windowId: slot.slotId,
            revision: admin.firestore.FieldValue.increment(1),
            updatedAt: admin.firestore.FieldValue.serverTimestamp(),
          }, {merge: true});
        });
        if (!windowSnap.exists) {
          createTask = true;
          transaction.create(windowRef, {
            status: "SCHEDULED",
            scheduledAt: admin.firestore.Timestamp.fromDate(slot.scheduledAt),
            createdAt: admin.firestore.FieldValue.serverTimestamp(),
          });
        }
      });

      if (!createTask) return;
      try {
        await getFunctions().taskQueue("ddsProjectionBatch").enqueue(
            {windowId: slot.slotId},
            {scheduleDelaySeconds: slot.delaySeconds},
        );
        console.log(`Consolidação DDS ${slot.slotId} agendada em ${slot.delaySeconds}s.`);
      } catch (error) {
        await windowRef.delete().catch(() => {});
        throw error;
      }
    },
);

exports.ddsProjectionBatch = onTaskDispatched(
    {
      retryConfig: {maxAttempts: 5, minBackoffSeconds: 300, maxBackoffSeconds: 900},
      rateLimits: {maxConcurrentDispatches: 1},
      timeoutSeconds: 1800,
      maxInstances: 1,
      concurrency: 1,
    },
    async (request) => {
      const windowId = String((request.data && request.data.windowId) || "");
      if (!windowId) throw new Error("windowId ausente");
      const windowRef = db.collection("dds_projection_windows").doc(windowId);
      await windowRef.set({status: "PROCESSING", startedAt: admin.firestore.FieldValue.serverTimestamp()}, {merge: true});

      try {
        const pending = await db.collection("dds_projection_pending").where("windowId", "==", windowId).get();
        for (const pendingDoc of pending.docs) {
          const marker = pendingDoc.data() || {};
          const day = extractIsoDay(marker.day || pendingDoc.id);
          if (!day) continue;
          const revision = Number(marker.revision || 0);
          await rebuildDdsDay(day, revision);
          await db.runTransaction(async (transaction) => {
            const current = await transaction.get(pendingDoc.ref);
            const currentData = current.data() || {};
            if (current.exists && currentData.windowId === windowId && Number(currentData.revision || 0) === revision) {
              transaction.delete(pendingDoc.ref);
            }
          });
        }
        // A janela é apenas coordenação efêmera; os JSONs são o resultado durável.
        await windowRef.delete();
      } catch (error) {
        await windowRef.set({
          status: "ERROR",
          lastError: String(error.message || error),
          failedAt: admin.firestore.FieldValue.serverTimestamp(),
        }, {merge: true});
        throw error;
      }
    },
);
