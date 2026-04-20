// Módulo: app/src/main/java/com/chicoeletro/dds/storage/TrainingDataStore.kt
// Função: Armazenamento persistente para metadados de treinamentos. Gerencia o cache 
//         de temas, cronogramas e status de disponibilidade offline.
// Tecnologias: Jetpack DataStore (Preferences).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 01/06/2025: Criação inicial.
//   - 05/06/2025: Ajustes para remover chaves obsoletas e gravar json string.
//   - 07/06/2025: Validar que funcione com a lista vinda do Repository em vez de Firestore.
//   - 17/06/2025 — adição de getManifest() e saveManifest()

package com.chicoeletro.dds.storage

import android.content.Context
import android.util.Log
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.chicoeletro.dds.data.Training
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

private const val DATASTORE_NAME = "trainings_cache"
private val Context.trainingDataStore by preferencesDataStore(name = DATASTORE_NAME)

object TrainingDataStore {
    private val MANIFEST_KEY = stringPreferencesKey("manifest_json")

    private val PERMISSIONS_ONBOARDING_DONE = booleanPreferencesKey("permissions_onboarding_done")

    /** Indica se o app já executou o onboarding de permissões no 1º acesso. */
    fun getPermissionsOnboardingDone(context: Context): Flow<Boolean> =
        context.trainingDataStore.data.map { prefs ->
            prefs[PERMISSIONS_ONBOARDING_DONE] ?: false
        }

    /** Marca que o onboarding de permissões já foi concluído. */
    suspend fun setPermissionsOnboardingDone(context: Context, done: Boolean) {
        context.trainingDataStore.edit { prefs ->
            prefs[PERMISSIONS_ONBOARDING_DONE] = done
        }
    }


    /** Retorna o manifest local ou lista vazia */
    fun getManifest(context: Context): Flow<List<com.chicoeletro.dds.data.sync.ManifestItem>> =
        context.trainingDataStore.data.map { prefs ->
            prefs[MANIFEST_KEY]?.let {
                Json.decodeFromString(it)
            } ?: emptyList()
        }

    /** Persiste o manifest completo como JSON */
    suspend fun saveManifest(context: Context, manifest: List<com.chicoeletro.dds.data.sync.ManifestItem>) {
        val text = Json.encodeToString(manifest)
        context.trainingDataStore.edit { prefs ->
            prefs[MANIFEST_KEY] = text
        }
    }

    /**
     * Sincroniza o cache local com a lista de [trainings].
     */
    suspend fun syncCache(context: Context, trainings: List<Training>) {
        val dataStore = context.trainingDataStore
        val idsParaManter = trainings.map { it.id }.toSet()

        dataStore.edit { prefs ->
            // 1) Remover chaves antigas cujo nome não esteja em idsParaManter
            val todasChaves = prefs.asMap().keys
            for (key in todasChaves) {
                if (!idsParaManter.contains(key.name)) {
                    @Suppress("UNCHECKED_CAST")
                    prefs.remove(key as androidx.datastore.preferences.core.Preferences.Key<String>)
                }
            }
            // 2) Inserir/atualizar cada treinamento novo ou alterado
            for (training in trainings) {
                val key = stringPreferencesKey(training.id)
                val json = Json.encodeToString(training)
                prefs[key] = json
            }
        }
    }

    /**
     * Retorna um Flow que emite a lista de todos os Trainings salvos localmente,
     * ordenados por data (campo date) em ordem decrescente.
     */
    fun getAllTrainings(context: Context): Flow<List<Training>> {
        return context.trainingDataStore.data.map { prefs ->
            val lista = prefs.asMap()
                .mapNotNull { entry ->
                    val jsonString = entry.value as? String ?: return@mapNotNull null
                    try {
                        Json.decodeFromString<Training>(jsonString)
                    } catch (_: Exception) {
                        null
                    }
                }
                .sortedByDescending { it.date }
            Log.d("TrainingDS", "Lista do DataStore: $lista")
            lista
        }
    }
}