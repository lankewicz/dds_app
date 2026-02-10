// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoLocalStore.kt
// Caminho completo: [PROJECT_ROOT]/app/src/main/java/com/chicoeletro/dds/features/turno/TurnoLocalStore.kt
// Descrição: Persistência local (offline-first) do Status do Turno por equipe:
//            - status atual + timestamps
//            - fila local de logs pendentes
// Autor: Valdinei Lankewicz
// Criado em: 04/02/2026
// Histórico de alterações:
//   - 04/02/2026: Ajustado para usar TurnoStatusModels como fonte única; retrocompat de leitura; escrita atômica (anti-corrupção).
//   - 04/02/2026: flowStatus com FileObserver (atualiza UI ao salvar localmente).

package com.chicoeletro.dds.features.turno

import android.content.Context
import android.os.FileObserver
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object TurnoLocalStore {
    private fun baseDir(context: Context) = File(context.filesDir, "turno").apply { mkdirs() }

    private fun writeAtomic(target: File, content: String) {
        val tmp = File(target.parentFile, target.name + ".tmp")
        tmp.writeText(content)
        if (target.exists()) target.delete()
        tmp.renameTo(target)
    }

    private fun statusFile(context: Context, teamKey: String) =
        File(baseDir(context), "turno_status_${teamKey}.json")

    private fun logFile(context: Context, teamKey: String) =
        File(baseDir(context), "turno_log_pending_${teamKey}.json")

    fun flowStatus(context: Context, teamKey: String): Flow<TurnoStatusLocal?> = callbackFlow {
        trySend(readStatusOnce(context, teamKey))

        val dir = baseDir(context)
        val statusName = statusFile(context, teamKey).name

        val obs = object : FileObserver(dir.absolutePath, CLOSE_WRITE or MOVED_TO or CREATE) {
            override fun onEvent(event: Int, path: String?) {
                if (path == statusName) trySend(readStatusOnce(context, teamKey))
            }
        }
        obs.startWatching()
        awaitClose { obs.stopWatching() }
    }.distinctUntilChanged()

    fun readStatusOnce(context: Context, teamKey: String): TurnoStatusLocal? {
        val f = statusFile(context, teamKey)
        if (!f.exists()) return null
        val obj = runCatching { JSONObject(f.readText()) }.getOrNull() ?: return null

        val statusName = obj.optString("status", "")
        val st = runCatching { TurnoStatus.valueOf(statusName) }.getOrNull() ?: return null

        val equipe = obj.optString("equipe", teamKey)
        val eletricistasArr = obj.optJSONArray("eletricistas") ?: JSONArray()
        val eletricistas = (0 until eletricistasArr.length()).mapNotNull { idx ->
            eletricistasArr.optString(idx, null)
        }

        val deslocamentoMotivo = obj.optString("deslocamentoMotivo", "").takeIf { it.isNotBlank() }
        val ssNoc = obj.optString("ssNoc", "").takeIf { it.isNotBlank() }

        return TurnoStatusLocal(
            equipe = equipe,
            eletricistas = eletricistas,
            status = st,
            changedAt = obj.optString("changedAt", ""),
            pendingSync = obj.optBoolean("pendingSync", false),
            deslocamentoMotivo = deslocamentoMotivo,
            ssNoc = ssNoc
        )
    }

    fun saveStatus(context: Context, teamKey: String, value: TurnoStatusLocal) {
        val obj = JSONObject().apply {
            put("equipe", value.equipe)
            put("eletricistas", JSONArray(value.eletricistas))
            put("status", value.status.name)
            put("changedAt", value.changedAt)
            put("pendingSync", value.pendingSync)
            put("deslocamentoMotivo", value.deslocamentoMotivo)
            put("ssNoc", value.ssNoc)
        }
        writeAtomic(statusFile(context, teamKey), obj.toString())
    }

    data class PendingTurnoLog(
        val equipe: String,
        val eletricistas: List<String>,
        val statusAnterior: TurnoStatus?,
        val statusNovo: TurnoStatus,
        val changedAtClient: String,
        val deslocamentoMotivo: String? = null,
        val ssNoc: String? = null
    )

    fun enqueueLog(context: Context, teamKey: String, entry: PendingTurnoLog) {
        val f = logFile(context, teamKey)
        val arr = if (f.exists()) runCatching { JSONArray(f.readText()) }.getOrElse { JSONArray() } else JSONArray()

        val obj = JSONObject().apply {
            put("equipe", entry.equipe)
            put("eletricistas", JSONArray(entry.eletricistas))
            put("statusAnterior", entry.statusAnterior?.name)
            put("statusNovo", entry.statusNovo.name)
            put("changedAtClient", entry.changedAtClient)
            put("deslocamentoMotivo", entry.deslocamentoMotivo)
            put("ssNoc", entry.ssNoc)
        }
        arr.put(obj)
        writeAtomic(f, arr.toString())
    }

    fun readPendingLogsOnce(context: Context, teamKey: String): List<PendingTurnoLog> {
        val f = logFile(context, teamKey)
        if (!f.exists()) return emptyList()
        val arr = runCatching { JSONArray(f.readText()) }.getOrElse { return emptyList() }

        val out = mutableListOf<PendingTurnoLog>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val equipe = o.optString("equipe", "")
            val eletricistasArr = o.optJSONArray("eletricistas") ?: JSONArray()
            val eletricistas = (0 until eletricistasArr.length()).mapNotNull { idx ->
                eletricistasArr.optString(idx, null)
            }

            val prevName = o.optString("statusAnterior", "")
            val prev = runCatching { TurnoStatus.valueOf(prevName) }.getOrNull()

            val novoName = o.optString("statusNovo", "")
            val novo = runCatching { TurnoStatus.valueOf(novoName) }.getOrNull() ?: continue

            val changed = o.optString("changedAtClient", "")
            val motivo = o.optString("deslocamentoMotivo", "").takeIf { it.isNotBlank() }
            val ssNoc = o.optString("ssNoc", "").takeIf { it.isNotBlank() }

            out.add(
                PendingTurnoLog(
                    equipe = equipe,
                    eletricistas = eletricistas,
                    statusAnterior = prev,
                    statusNovo = novo,
                    changedAtClient = changed,
                    deslocamentoMotivo = motivo,
                    ssNoc = ssNoc
                )
            )
        }
        return out
    }

    fun markSynced(context: Context, teamKey: String) {
        val cur = readStatusOnce(context, teamKey) ?: return
        saveStatus(context, teamKey, cur.copy(pendingSync = false))
    }

    fun clearPendingLogs(context: Context, teamKey: String) {
        val f = logFile(context, teamKey)
        if (f.exists()) f.delete()
    }
}