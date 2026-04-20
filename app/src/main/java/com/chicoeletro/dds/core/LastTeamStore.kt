// Módulo: app/src/main/java/com/chicoeletro/dds/core/LastTeamStore.kt
// Função: Gerenciamento de persistência local para os dados da equipe. Utiliza Jetpack DataStore 
//         com serialização JSON para armazenar e recuperar o estado da última equipe.
// Tecnologias: Jetpack DataStore (Preferences), Kotlinx Serialization (JSON), Coroutines (Flow).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/06/2025: Criação inicial.
//   - 12/06/2025: Garantido que gravação (suspend fun) seja chamada dentro de coroutine.

package com.chicoeletro.dds.core

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

private val Context.lastTeamDataStore: DataStore<Preferences> by preferencesDataStore(name = "last_team_prefs")

object LastTeamStore {
    private val KEY_LAST_TEAM = stringPreferencesKey("last_team_data")

    /**
     * Carrega do DataStore, desserializando de JSON para LastTeamData.
     * Em caso de valor ausente, retorna null.
     */
    fun carregar(context: Context): Flow<LastTeamData?> =
        context.lastTeamDataStore.data.map { prefs ->
            prefs[KEY_LAST_TEAM]?.let { jsonString ->
                try {
                    Json.decodeFromString<LastTeamData>(jsonString)
                } catch (_: Exception) {
                    null
                }
            }
        }

    /**
     * Grava no DataStore, serializando LastTeamData em JSON.
     * Como é `suspend`, deve ser chamado dentro de coroutine.
     */
    suspend fun salvar(context: Context, lastTeamData: LastTeamData) {
        context.lastTeamDataStore.edit { prefs ->
            val jsonString = Json.encodeToString(lastTeamData)
            prefs[KEY_LAST_TEAM] = jsonString
        }
    }
}