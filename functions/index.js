const admin = require("firebase-admin");
const { onDocumentUpdated } = require("firebase-functions/v2/firestore");
const { setGlobalOptions } = require("firebase-functions/v2");

admin.initializeApp();
const db = admin.firestore();

// IMPORTANTE: mesma região do Firestore (default)
setGlobalOptions({ region: "us-central1" });

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
    presence.lastSeenAt && presence.lastSeenAt.seconds
      ? presence.lastSeenAt.seconds
      : null;

  // Ordena por join para evitar bagunça
  const ordered = segs
    .map((s) => ({ join: s.join, leave: s.leave }))
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
        `[${ddsSessionId}] status=closed sem endedAt`
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
      after.startedAt
        ? after.endedAt.seconds - after.startedAt.seconds
        : 0;

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
      duracao: sessionDuration
        ? `${Math.floor(sessionDuration / 60)}m ${
            sessionDuration % 60
          }s`
        : "",
      origin: "online",
      ddsSessionId,
    };

    const ddsRef = await db.collection("DDS").add(ddsDoc);

    await sessionRef.update({
      finalizedAt: admin.firestore.FieldValue.serverTimestamp(),
      ddsDocId: ddsRef.id,
    });

    console.log(
      `[${ddsSessionId}] DDS criado: ${ddsRef.id}`
    );
  }
);
