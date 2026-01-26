// Módulo: app/src/main/java/com/example/dds/data/ImageListStore.kt
// Função: Armazena / recupera, em Preferences DataStore, a lista de URLs de imagens
//         associadas a cada trainingId. Isso evita acessar o Firebase Storage depois
//         que a lista já tiver sido baixada uma vez.
// Histórico de Alterações:
//   - 05/06/2025: Criação inicial para suportar cache offline das listas de URLs.

package com.chicoeletro.dds.data

import android.content.Context
import androidx.datastore.preferences.core.MutablePreferences
import androidx.datastore.preferences.core.edit
//import androidx.datastore.preferences.core.remove
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

// Cria um DataStore de Preferences chamado "image_list_prefs"
private val Context.imageListDataStore by preferencesDataStore(name = "image_list_prefs")

object ImageListStore {

    /**
     * Converte um trainingId arbitrário em uma chave válida para Preferences:
     *  - substitui todos caracteres não alfanuméricos por "_"
     *  - prefixa com "imgs_"
     */
    private fun keyForTraining(trainingId: String): String {
        // Substitui tudo que não for A–Z, a–z ou 0–9 por "_"
        val safe = trainingId.replace("[^A-Za-z0-9]".toRegex(), "_")
        return "imgs_$safe"
    }

    /**
     * Salva a lista de URLs de imagem (List<String>) associada a um dado trainingId.
     * O valor gravado no DataStore é um único JSON contendo a lista de URLs.
     */
    suspend fun saveImageList(context: Context, trainingId: String, urls: List<String>) {
        val keyName = keyForTraining(trainingId)
        val prefsKey = stringPreferencesKey(keyName)
        val jsonString = Json.encodeToString(urls)
        context.imageListDataStore.edit { prefs: MutablePreferences ->
            prefs[prefsKey] = jsonString
        }
    }

    /**
     * Retorna um Flow<List<String>?> que emite a lista de URLs armazenada para um determinado trainingId.
     * - Se não houver valor salvo, emite null.
     * - Se existe JSON válido, desserializa e retorna List<String>.
     */
    fun getImageList(context: Context, trainingId: String): Flow<List<String>?> {
        val keyName = keyForTraining(trainingId)
        val prefsKey = stringPreferencesKey(keyName)
        return context.imageListDataStore.data.map { prefs ->
            prefs[prefsKey]?.let { jsonString ->
                try {
                    Json.decodeFromString<List<String>>(jsonString)
                } catch (_: Exception) {
                    null
                }
            }
        }
    }

    /**
     * Para “deletar” o cache local de uma lista de URLs (por ex. em caso de atualização completa),
     * podemos remover a chave do Preferences.
     */
    suspend fun clearImageList(context: Context, trainingId: String) {
        val keyName = keyForTraining(trainingId)
        val prefsKey = stringPreferencesKey(keyName)
        context.imageListDataStore.edit { prefs ->
            prefs.remove(prefsKey)
        }
    }
}
