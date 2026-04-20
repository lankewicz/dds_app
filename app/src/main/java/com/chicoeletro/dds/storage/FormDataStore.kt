// Módulo: app/src/main/java/com/chicoeletro/dds/storage/FormDataStore.kt
// Função: Persistência de dados temporários de formulários. Armazena rascunhos e preenchimentos 
//         parciais para evitar perda de dados durante a navegação.
// Tecnologias: Jetpack DataStore (Preferences).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/06/2025: Criação inicial.

package com.chicoeletro.dds.storage

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.chicoeletro.dds.data.FormSubmission
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

private const val DATASTORE_NAME = "form_submissions"
private val Context.dataStore by preferencesDataStore(name = DATASTORE_NAME)

object FormDataStore {

    /**
    * Salva a submissão [submission] no DataStore local, usando submissionId como chave estável.
     */
    suspend fun saveSubmission(context: Context, submission: FormSubmission) {
        val key = stringPreferencesKey(submission.submissionId)
        context.dataStore.edit { prefs ->
            prefs[key] = Json.encodeToString(submission)
        }
    }

    /**
     * Retorna um Flow que emite a lista de todas as submissões salvas localmente.
     */
    fun getAllSubmissions(context: Context): Flow<List<FormSubmission>> {
        return context.dataStore.data.map { prefs ->
            prefs.asMap().mapNotNull { entry ->
                val jsonString = entry.value as? String ?: return@mapNotNull null
                try {
                    Json.decodeFromString<FormSubmission>(jsonString)
                } catch (_: Exception) {
                    null
                }
            }
        }
    }

    /**
     * Remove a submissão pela chave [submissionId] do DataStore.
     */
    suspend fun deleteSubmission(context: Context, submissionId: String) {
        val key = stringPreferencesKey(submissionId)
        context.dataStore.edit { prefs ->
            prefs.remove(key)
        }
    }
}