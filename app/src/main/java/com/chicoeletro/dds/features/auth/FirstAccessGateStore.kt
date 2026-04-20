// Módulo: app/src/main/java/com/chicoeletro/dds/features/auth/FirstAccessGateStore.kt
// Função: Gerenciador de persistência para o estado de configuração inicial. Armazena a flag 
//         que indica se o onboarding da equipe foi concluído.
// Tecnologias: Jetpack DataStore (Preferences).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.auth

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.firstAccessDataStore by preferencesDataStore(name = "dds_first_access")

class FirstAccessGateStore(
    private val context: Context
) {
    private object Keys {
        val DEVICE_UNLOCKED = booleanPreferencesKey("device_unlocked")
    }

    val unlockedFlow: Flow<Boolean> =
        context.firstAccessDataStore.data.map { prefs ->
            prefs[Keys.DEVICE_UNLOCKED] ?: false
        }

    suspend fun unlockDevice() {
        context.firstAccessDataStore.edit { prefs ->
            prefs[Keys.DEVICE_UNLOCKED] = true
        }
    }

    suspend fun resetDeviceLock() {
        context.firstAccessDataStore.edit { prefs ->
            prefs[Keys.DEVICE_UNLOCKED] = false
        }
    }
}