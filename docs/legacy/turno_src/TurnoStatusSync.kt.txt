    // Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoStatusSync.kt
// Caminho completo: [PROJECT_ROOT]/app/src/main/java/com/chicoeletro/dds/features/turno/TurnoStatusSync.kt
// Descrição: Sincronização do Status do Turno (offline-first):
//            - Estado atual por equipe (local + Firestore);
//            - Log de alterações (Firestore);
//            - Fila local de pendências e retry automático ao voltar online.
// Autor: Valdinei Lankewicz
// Criado em: 04/02/2026
// Histórico de alterações:
//   - 04/02/2026: Ajustado para TurnoStatusModels (TurnoStatusLocal com equipe/eletricistas) e fila local PendingTurnoLog.

package com.chicoeletro.dds.features.turno

import android.content.Context
import com.google.android.gms.tasks.Task
import com.google.firebase.Timestamp
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.suspendCancellableCoroutine
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Coleções (sugestão):
 * - DDS_TURNO_STATUS/{teamKey}  (doc com status atual)
 * - DDS_TURNO_LOG/{teamKey}/log/{autoId} (histórico)
 */
class TurnoStatusSync(
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()
) {
    private val fmt = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm").withZone(ZoneId.systemDefault())

    fun observeLocal(context: Context, equipe: String): Flow<TurnoStatusLocal?> {
        val key = teamKeyOf(equipe)
        return TurnoLocalStore.flowStatus(context, key)
    }

    suspend fun setStatus(
        context: Context,
        equipe: String,
        eletricistas: List<String>,
        novoStatus: TurnoStatus,
        deslocamentoMotivo: String? = null,
        ssNoc: String? = null
    ) {
        val key = teamKeyOf(equipe)

        val anterior = prev?.status

        val nowIso = Instant.now().toString()
        val nowUi = fmt.format(Instant.now())

        val statusChanged = prev?.status != novoStatus
        val motivoChanged = (prev?.deslocamentoMotivo ?: "") != (deslocamentoMotivo ?: "")
        val ssNocTrim = ssNoc?.trim()?.takeIf { it.isNotBlank() }
        val ssNocChanged = (prev?.ssNoc ?: "") != (ssNocTrim ?: "")

        // Mantém timestamp do STATUS se não mudou status.
        val statusChangedAtIso = if (statusChanged || prev == null) nowIso else prev.changedAtIso
        val statusChangedAtUi  = if (statusChanged || prev == null) nowUi else prev.changedAtUi

        // Timestamp do SS/NOC é separado.
        val ssNocChangedAtIso = if (ssNocChanged) nowIso else prev?.ssNocChangedAtIso
        val ssNocChangedAtUi  = if (ssNocChanged) nowUi else prev?.ssNocChangedAtUi

        val pending = statusChanged || motivoChanged || ssNocChanged

        // 1) salva local (estado atual)
        TurnoLocalStore.saveStatus(
            context = context,
            teamKey = key,
            value = TurnoStatusLocal(
                equipe = equipe.trim(),
                eletricistas = eletricistas.map { it.trim() }.filter { it.isNotBlank() },
                status = novoStatus,
                changedAtIso = statusChangedAtIso,
                changedAtUi = statusChangedAtUi,
                pendingSync = pending,
                deslocamentoMotivo = deslocamentoMotivo,
                ssNoc = ssNocTrim,
                ssNocChangedAtIso = ssNocChangedAtIso,
                ssNocChangedAtUi = ssNocChangedAtUi
            )
        )

        // Log só quando algo realmente mudou
        if (pending) {
            TurnoLocalStore.enqueueLog(
                context = context,
                teamKey = key,
                entry = TurnoLocalStore.PendingTurnoLog(
                    equipe = equipe.trim(),
                    eletricistas = eletricistas.map { it.trim() }.filter { it.isNotBlank() },
                    statusAnterior = anterior,
                    statusNovo = novoStatus,
                    changedAtClientIso = nowIso,
                    changedAtUi = nowUi,
                    deslocamentoMotivo = deslocamentoMotivo,
                    ssNoc = ssNocTrim,
                    ssNocOnly = !statusChanged && ssNocChanged
                )
            )
        }
    }

    /**
     * Envia pendências locais para o Firestore.
     */
    suspend fun tryPushPending(context: Context, online: Boolean, equipe: String) {
        if (!online) return
        val key = teamKeyOf(equipe)

        val statusLocal = TurnoLocalStore.readStatusOnce(context, key) ?: return
        if (!statusLocal.pendingSync) return

        val pendingLogs = TurnoLocalStore.readPendingLogsOnce(context, key)

        val statusDoc = mapOf(
            "teamName" to equipe.trim(),
            "teamKey" to key,
            "status" to statusLocal.status.name,
            "changedAt" to Timestamp.now(),
            "changedAtClientIso" to statusLocal.changedAtIso,
            "changedAtUi" to statusLocal.changedAtUi,
            "deslocamentoMotivo" to statusLocal.deslocamentoMotivo,
            "ssNoc" to statusLocal.ssNoc,
            "ssNocChangedAtClientIso" to statusLocal.ssNocChangedAtIso,
            "ssNocChangedAtUi" to statusLocal.ssNocChangedAtUi
        )

        db.collection("DDS_TURNO_STATUS")
            .document(key)
            .set(statusDoc)
            .await()

        val logCol = db.collection("DDS_TURNO_LOG").document(key).collection("log")
        for (l in pendingLogs) {
            val logDoc = mapOf(
                "equipe" to l.equipe,
                "teamKey" to key,
                "eletricistas" to l.eletricistas,
                "statusAnterior" to l.statusAnterior?.name,
                "statusNovo" to l.statusNovo.name,
                "changedAt" to Timestamp.now(),
                "changedAtUi" to l.changedAtUi,
                "deslocamentoMotivo" to l.deslocamentoMotivo,
                "ssNoc" to l.ssNoc,
                "ssNocOnly" to l.ssNocOnly
            )
            logCol.add(logDoc).await()
        }

        TurnoLocalStore.markSynced(context, key)
        TurnoLocalStore.clearPendingLogs(context, key)
    }
    companion object {
        fun teamKeyOf(teamName: String): String =
            teamName.trim().lowercase()
                .replace("\\s+".toRegex(), "_")
                .replace("[^a-z0-9_\\-]".toRegex(), "")
    }
}

    /**
     * Faz pull do Firestore para o local, se estiver online.
     * Política simples: sempre aplica o remoto se existir.
     */
    suspend fun pullLatestIfSafe(context: Context, online: Boolean, equipe: String) {
        if (!online) return
        val key = teamKeyOf(equipe)

        val snap = db.collection("DDS_TURNO_STATUS").document(key).get().await()
        if (!snap.exists()) return

        val statusName = snap.getString("status") ?: return
        val st = runCatching { TurnoStatus.valueOf(statusName) }.getOrNull() ?: return

        val changedAtUi = snap.getString("changedAtUi")
            ?: fmt.format(Instant.now())

        val changedAtClientIso = snap.getString("changedAtClientIso")
            ?: Instant.now().toString()

        val deslocMotivo = snap.getString("deslocamentoMotivo")
        val ssNoc = snap.getString("ssNoc")
        val ssNocChangedAtIso = snap.getString("ssNocChangedAtClientIso")
        val ssNocChangedAtUi = snap.getString("ssNocChangedAtUi")

        TurnoLocalStore.saveStatus(
            context = context,
            teamKey = key,
            value = TurnoStatusLocal(
                equipe = snap.getString("teamName") ?: equipe.trim(),
                eletricistas = emptyList(), // opcional: só se você decidir persistir eletricistas no doc de status
                status = st,
                changedAtIso = changedAtClientIso,
                changedAtUi = changedAtUi,
                pendingSync = false,
                deslocamentoMotivo = deslocMotivo,
                ssNoc = ssNoc,
                ssNocChangedAtIso = ssNocChangedAtIso,
                ssNocChangedAtUi = ssNocChangedAtUi
            )
        )
    }

    fun lastChangedAtNowString(): String = fmt.format(Instant.now())

    companion object {
        fun teamKeyOf(teamName: String): String =
            teamName.trim().lowercase()
                .replace("\\s+".toRegex(), "_")
                .replace("[^a-z0-9_\\-]".toRegex(), "")
    }
}

/**
 * Pequeno helper para Tasks do Firebase em corrotinas, sem depender de play-services-ktx explícito.
 * Se você já usa kotlinx-coroutines-play-services, pode remover isso e usar .await() nativo.
 */
suspend fun <T> Task<T>.await(): T =
    suspendCancellableCoroutine { cont ->
        addOnSuccessListener { cont.resume(it) }
        addOnFailureListener { cont.resumeWithException(it) }
    }