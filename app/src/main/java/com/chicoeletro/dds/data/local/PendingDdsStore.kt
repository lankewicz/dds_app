package com.chicoeletro.dds.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.chicoeletro.dds.data.FormSubmission
import kotlinx.coroutines.flow.first
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.decodeFromString

private val Context.dataStore by preferencesDataStore(name = "dds_pending")

class PendingDdsStore(private val context: Context) {
    private val KEY = stringPreferencesKey("pending_submissions_json")
    private val json = Json { ignoreUnknownKeys = true }

    private suspend fun readAll(): MutableList<FormSubmission> {
        val prefs = context.dataStore.data.first()
        val raw = prefs[KEY] ?: "[]"
        return runCatching { json.decodeFromString<List<FormSubmission>>(raw).toMutableList() }
            .getOrElse { mutableListOf() }
    }

    private suspend fun writeAll(list: List<FormSubmission>) {
        val raw = json.encodeToString(list)
        context.dataStore.edit { it[KEY] = raw }
    }

    suspend fun enqueue(submission: FormSubmission) {
        val list = readAll()
        list.add(submission)
        writeAll(list)
    }

    suspend fun listPending(): List<FormSubmission> = readAll()

    suspend fun removeById(submissionId: String) {
        val list = readAll().filterNot { it.submissionId == submissionId }
        writeAll(list)
    }

    suspend fun update(updated: FormSubmission) {
        val list = readAll().map { if (it.submissionId == updated.submissionId) updated else it }
        writeAll(list)
    }
}
