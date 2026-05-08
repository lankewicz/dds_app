// Módulo: app/src/main/java/com/chicoeletro/dds/storage/TrainingExecLocalStore.kt
// Função: Persistência do histórico local de execuções de DDS. Mantém o registro de quais 
//         treinamentos foram concluídos pela equipe como cache offline do Firestore.
// Tecnologias: Jetpack DataStore, Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 28/06/2025: Criação inicial.

// -----------------------------------------------------------------------------
// Arquivo : TrainingExecLocalStore.kt
// Módulo  : DDS / Treinamentos (Cache Local)
// Objetivo: Manter no tablet um espelho (cache) do status de execução de
//           treinamentos por equipe/mês, permitindo conferência sem rede.
//
// Regra de negócio:
//   - Um treinamento é "executado" após tirar a foto e clicar em Concluir.
//   - O Firestore é a fonte de verdade; este store é um cache local resiliente.
//
// Observações:
//   - Implementação simples via DataStore + JSON (sem dependências extras).
//   - Chave composta: teamKey + yyyy-MM.
// -----------------------------------------------------------------------------
package com.chicoeletro.dds.storage

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.json.JSONObject

private val Context.trainingExecDataStore by preferencesDataStore(name = "training_exec_cache")

data class ExecCacheEntry(
    val dataConclusao: String,
    val horaConclusao: String,
    val duracao: String,
    val syncState: String = TrainingExecSyncState.SYNCED
)


object TrainingExecSyncState {
    const val LOCAL_ONLY = "LOCAL_ONLY"
    const val SYNCED = "SYNCED"
    const val ERROR = "ERROR"
}

object TrainingExecLocalStore {

    private fun key(teamKey: String, month: String): Preferences.Key<String> =
        stringPreferencesKey("exec_${teamKey}_${month}") // month: yyyy-MM

    /**
     * Retorna um Flow com o mapa trainingId -> ExecCacheEntry do cache local.
     */
    fun flowMonth(
        context: Context,
        teamKey: String,
        month: String
    ): Flow<Map<String, ExecCacheEntry>> {
        val prefKey = key(teamKey, month)
        return context.trainingExecDataStore.data.map { prefs ->
            val raw = prefs[prefKey] ?: return@map emptyMap()
            parse(raw)
        }
    }

    /**
     * Sobrescreve o cache local do mês inteiro (mais simples e robusto).
     */
    suspend fun saveMonth(
        context: Context,
        teamKey: String,
        month: String,
        map: Map<String, ExecCacheEntry>
    ) {
        val prefKey = key(teamKey, month)
        val json = toJson(map)
        context.trainingExecDataStore.edit { prefs ->
            prefs[prefKey] = json
        }
    }

    suspend fun mergeRemoteMonth(
        context: Context,
        teamKey: String,
        month: String,
        remoteMap: Map<String, ExecCacheEntry>
    ) {
        val prefKey = key(teamKey, month)
        context.trainingExecDataStore.edit { prefs ->
            val current = prefs[prefKey]
            val map = if (current.isNullOrBlank()) mutableMapOf() else parse(current).toMutableMap()
            for ((trainingId, entry) in remoteMap) {
                map[trainingId] = entry.copy(syncState = TrainingExecSyncState.SYNCED)
            }
            prefs[prefKey] = toJson(map)
        }
    }

    /**
     * Atualiza/insere um único trainingId no cache local (write otimista).
     */
    suspend fun upsert(
        context: Context,
        teamKey: String,
        month: String,
        trainingId: String,
        entry: ExecCacheEntry
    ) {
        val prefKey = key(teamKey, month)
        context.trainingExecDataStore.edit { prefs ->
            val current = prefs[prefKey]
            val map = if (current.isNullOrBlank()) mutableMapOf() else parse(current).toMutableMap()
            prefs[prefKey] = toJson(map)
        }
    }

    /**
     * Migra todo o histórico local de uma equipe para um novo prefixo.
     * Útil quando há mudança de veículo mas a equipe permanece a mesma.
     */
    suspend fun migrateTeam(context: Context, oldTeam: String, newTeam: String) {
        val oldPrefix = "exec_${oldTeam.trim().uppercase()}_"
        val newPrefix = "exec_${newTeam.trim().uppercase()}_"
        
        context.trainingExecDataStore.edit { prefs ->
            val allEntries = prefs.asMap()
            val toMove = allEntries.filter { it.key.name.startsWith(oldPrefix) }
            
            for ((oldKey, value) in toMove) {
                val month = oldKey.name.removePrefix(oldPrefix)
                val newKey = stringPreferencesKey(newPrefix + month)
                
                // Forçamos syncState = LOCAL_ONLY para que o app tente subir esse 
                // histórico para o NOVO prefixo no Firestore.
                val updatedValue = runCatching {
                    val json = JSONObject(value as String)
                    val keys = json.keys()
                    while(keys.hasNext()){
                        val id = keys.next()
                        json.optJSONObject(id)?.put("syncState", TrainingExecSyncState.LOCAL_ONLY)
                    }
                    json.toString()
                }.getOrElse { value as String }

                prefs[newKey] = updatedValue
                prefs.remove(oldKey)
            }
        }
    }

    private fun toJson(map: Map<String, ExecCacheEntry>): String {
        val root = JSONObject()
        for ((id, e) in map) {
            val o = JSONObject()
            o.put("dataConclusao", e.dataConclusao)
            o.put("horaConclusao", e.horaConclusao)
            o.put("duracao", e.duracao)
            o.put("syncState", e.syncState)
            root.put(id, o)
        }
        return root.toString()
    }

    private fun parse(raw: String): Map<String, ExecCacheEntry> {
        return runCatching {
            val root = JSONObject(raw)
            val keys = root.keys()
            val out = mutableMapOf<String, ExecCacheEntry>()
            while (keys.hasNext()) {
                val id = keys.next()
                val o = root.optJSONObject(id) ?: continue
                val data = o.optString("dataConclusao", "")
                val hora = o.optString("horaConclusao", "")
                val dur = o.optString("duracao", "")
                val syncState = o.optString("syncState", TrainingExecSyncState.SYNCED)
                if (data.isNotBlank() && hora.isNotBlank()) {
                    out[id] = ExecCacheEntry(data, hora, dur, syncState)
                }
            }
            out.toMap()
        }.getOrElse { emptyMap() }
    }
    /**
     * Limpa todo o histórico local de uma equipe específica.
     */
    suspend fun clearLocalOnly(context: Context, teamName: String) {
        val prefix = "exec_${teamName.trim().uppercase()}_"
        context.trainingExecDataStore.edit { prefs ->
            val keysToRemove = prefs.asMap().keys.filter { it.name.startsWith(prefix) }
            keysToRemove.forEach { prefs.remove(it) }
        }
    }
}