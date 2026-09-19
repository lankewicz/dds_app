/*
 * Agenda uma reconstrução única das Torres DDS existentes.
 * Execute após o deploy.
 */
const admin = require("firebase-admin");
const {getFunctions} = require("firebase-admin/functions");

const projectId = process.env.GOOGLE_CLOUD_PROJECT;
const serviceAccountId = process.env.FUNCTIONS_SERVICE_ACCOUNT;
if (!projectId || !serviceAccountId) {
  throw new Error(
      "Defina GOOGLE_CLOUD_PROJECT e FUNCTIONS_SERVICE_ACCOUNT " +
          "antes do backfill.",
  );
}
admin.initializeApp({projectId, serviceAccountId});
const db = admin.firestore();

/**
 * Retorna um argumento CLI no formato --nome=valor.
 * @param {string} name Nome do argumento.
 * @return {string} Valor informado ou string vazia.
 */
function argument(name) {
  const prefix = `--${name}=`;
  const found = process.argv.find((value) => value.startsWith(prefix));
  return found ? found.slice(prefix.length) : "";
}

/** Localiza as datas e as envia para uma única tarefa de backfill. */
async function main() {
  const start = argument("start");
  const end = argument("end");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    throw new Error("Use --start=AAAA-MM-DD --end=AAAA-MM-DD");
  }

  const snapshot = await db.collection("DDS")
      .where("headerDate", ">=", start)
      .where("headerDate", "<=", `${end}\uf8ff`)
      .select("headerDate")
      .get();
  const days = new Set();
  snapshot.docs.forEach((doc) => {
    const match = String((doc.data() || {}).headerDate || "")
        .match(/\b(\d{4}-\d{2}-\d{2})\b/);
    if (match) days.add(match[1]);
  });

  const windowId = `backfill-${Date.now()}`;
  let batch = db.batch();
  let count = 0;
  for (const day of days) {
    batch.set(db.collection("dds_projection_pending").doc(day), {
      day,
      windowId,
      revision: admin.firestore.FieldValue.increment(1),
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    }, {merge: true});
    count += 1;
    if (count % 450 === 0) {
      await batch.commit();
      batch = db.batch();
    }
  }
  if (count % 450 !== 0) await batch.commit();

  await db.collection("dds_projection_windows").doc(windowId).set({
    status: "SCHEDULED",
    backfill: true,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
  });
  await getFunctions().taskQueue("ddsProjectionBatch").enqueue({windowId});
  console.log(`${days.size} datas agendadas no lote ${windowId}.`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
