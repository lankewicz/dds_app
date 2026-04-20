// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoFirestoreUploader.kt
// Função: Componente de upload para registros de turno. Transmite os períodos de trabalho 
//         fechados para o Firestore para fins de auditoria e relatórios.
// Tecnologias: Firebase Firestore.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

import android.util.Log
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

object TurnoFirestoreUploader {

    private const val TAG = "DDS-TURNO"

    /**
     * Tenta enviar todos os eventos pendentes.
     * - Em sucesso: remove da fila
     * - Em falha: mantém (retry futuro)
     *
     * Observação: por simplicidade, aqui usamos callbacks (não suspend).
     */
    fun tryPushPending(
        context: android.content.Context,
        online: Boolean
    ) {
        if (!online) return

        val pending = TurnoPendingStore.peekAll(context)
        if (pending.isEmpty()) return

        val db = FirebaseFirestore.getInstance()

        // Batch no Firestore permite até 500 operações. Útil para limpeza em massa offline-first.
        pending.chunked(400).forEach { batchList ->
            val batch = db.batch()
            batchList.forEach { ev ->
                val turnoDoc = turnoDoc(db, ev.empresa, ev.turnoId)
                val eventDoc = turnoDoc.collection("events").document(ev.eventId)
                batch.set(eventDoc, ev.toFirestoreMap())
            }

            batch.commit().addOnSuccessListener {
                // Isolamento para I/O em Batch para não travar a UI caso haja enxurrada.
                kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                    batchList.forEach { ev ->
                        TurnoPendingStore.removeByEventId(context, ev.eventId)
                    }
                    Log.d(TAG, "Lote de ${batchList.size} eventos (Turno) enviados ao Firebase/Cachê local.")
                }
            }.addOnFailureListener { e ->
                Log.w(TAG, "Falha ao sincronizar eventos: ${e.message}")
            }
        }
    }

    /**
     * Atualiza o "state" atual (último vence) no doc DDS/{empresa}/turno/{equipe}.
     * Dica: chamar após cada transição confirmada.
     */
    fun pushState(
        empresa: String,
        equipe: String,
        state: TurnoStateRemote
    ) {
        val db = FirebaseFirestore.getInstance()
        val teamDoc = teamDoc(db, empresa, equipe)

        db.runTransaction { tx ->
            val snap = tx.get(teamDoc)
            val currentMs = snap.getLong("clientUpdatedAtMs") ?: -1L
            if (state.clientUpdatedAtMs >= currentMs) {
                tx.set(teamDoc, state.toFirestoreMap(), com.google.firebase.firestore.SetOptions.merge())
            }
            null
        }.addOnSuccessListener {
            Log.d(TAG, "State salvo (safe): $empresa/$equipe clientUpdatedAtMs=${state.clientUpdatedAtMs}")
        }.addOnFailureListener { e ->
            Log.w(TAG, "Falha ao salvar state (safe) ${empresa}/${equipe}: ${e.message}")
        }
    }


    
    /**
     * Upsert da sessão do turno (auditoria).
     * - Na abertura: preenche openedAtServer somente se doc ainda não existir.
     * - No fechamento: preenche closedAtServer somente se ainda estiver nulo.
     */
    suspend fun upsertTurnoSession(session: TurnoSessionRemote) {
        val db = FirebaseFirestore.getInstance()
        val doc = turnoDoc(db, session.empresa, session.turnoId)

        val base = mutableMapOf<String, Any?>(
            "empresa" to session.empresa,
            "equipe" to session.equipe,
            "turnoId" to session.turnoId,
            "membersSnapshot" to session.membersSnapshot,
            "openedAtClientMs" to session.openedAtClientMs,
            "closeReason" to session.closeReason,
            "openedByUid" to session.openedByUid,
            "openedByDeviceId" to session.openedByDeviceId,
            "closedByUid" to session.closedByUid,
            "closedByDeviceId" to session.closedByDeviceId
        )

        // Regra Offline-First Nativa Firebase SDK:
        if (session.closedAtClientMs != null) {
            base["closedAtClientMs"] = session.closedAtClientMs
            base["closedAtServer"] = FieldValue.serverTimestamp()
        } else {
            base["openedAtServer"] = FieldValue.serverTimestamp()
        }

        try {
            // merge() nunca falhará offline. Ele é absorvido ou atualizado instantaneamente sob demanda.
            doc.set(base, com.google.firebase.firestore.SetOptions.merge()).await()
            Log.d(TAG, "Sessão de turno sincronizada com suporte offline: ${session.turnoId}")
        } catch (e: Exception) {
            Log.w(TAG, "Não foi possível concluir gravação Firestore: ${e.message}")
        }
    }

// ----------------- Helpers -----------------

        // ✅ ROOT: "turno"
        // state: turno/{empresa}/equipes/{equipe}
        // events: turno/{empresa}/turnos/{turnoId}/events/{eventId}
        private fun turnoDoc(db: FirebaseFirestore, empresa: String, turnoId: String) =
            db.collection("turno")
                .document(empresa)
                .collection("turnos")
                .document(turnoId)

        private fun teamDoc(db: FirebaseFirestore, empresa: String, equipe: String) =
            db.collection("turno")
                .document(empresa)
                .collection("equipes")
                .document(equipe)

    private fun TurnoEventRemote.toFirestoreMap(): Map<String, Any?> = mapOf(
        "empresa" to empresa,
        "equipe" to equipe,
        "eventId" to eventId,
        "turnoId" to turnoId,
        "clientCreatedAtIso" to clientCreatedAtIso,
        "occurredAtClientMs" to occurredAtClientMs,
        "receivedAtServer" to FieldValue.serverTimestamp(),

        "from" to from,
        "to" to to,

        "kmTotalAbs" to kmTotalAbs,
        "kmInicioTotalAbs" to kmInicioTotalAbs,
        "km4" to km4,
        "kmInicioTurno4" to kmInicioTurno4,
        "kmDeltaTurno" to kmDeltaTurno,

        "nocSs" to nocSs,
        "motivo" to motivo,
        "motivoOutro" to motivoOutro,

        "photoAudit" to mapOf(
            "required" to photoAudit.required,
            "photoId" to photoAudit.photoId,           // null quando não tiver
            "storagePath" to photoAudit.storagePath,   // null quando não tiver
            "thumbPath" to photoAudit.thumbPath        // null quando não tiver
        ),

        "actor" to mapOf(
            "deviceId" to actor.deviceId,
            "deviceModel" to actor.deviceModel,
            "appVersion" to actor.appVersion
        )
    )

    private fun TurnoStateRemote.toFirestoreMap(): Map<String, Any?> = mapOf(
        "empresa" to empresa,
        "equipe" to equipe,
        "turnoId" to turnoId,
        "isOpen" to isOpen,
        "membersSnapshot" to membersSnapshot,
        "openedAtClientMs" to openedAtClientMs,
        "closedAtClientMs" to closedAtClientMs,
        "closeReason" to closeReason,

        "clientUpdatedAtMs" to clientUpdatedAtMs,
        "updatedAtIso" to updatedAtIso,
        "serverUpdatedAt" to FieldValue.serverTimestamp(),

        "lastEventId" to lastEventId,
        "lastEventAtClientMs" to lastEventAtClientMs,
        "lastEventAtServer" to FieldValue.serverTimestamp(),

        "estado" to estado,
        "nocSs" to nocSs,

        "kmTotalAbs" to kmTotalAbs,
        "kmInicioTotalAbs" to kmInicioTotalAbs,
        "kmDeltaTurno" to kmDeltaTurno,
        "kmInicioTurno4" to kmInicioTurno4,
        "inicioTurnoAtIso" to inicioTurnoAtIso,

        "odometroVerificado" to odometroVerificado,
        "ultimosKm4" to ultimosKm4,
        "eventosKmCounter" to eventosKmCounter,

        "lastMotivo" to lastMotivo,
        "lastMotivoOutro" to lastMotivoOutro,

        "deviceIdLastWriter" to deviceIdLastWriter
    )
}