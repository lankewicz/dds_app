// Módulo: app/src/main/java/com/chicoeletro/dds/features/auth/FirstAccessGate.kt
// Função: Componente de controle de acesso inicial. Verifica se a equipe está configurada no 
//         dispositivo e redireciona para a configuração caso necessário.
// Tecnologias: Jetpack Compose, DataStore.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:


package com.chicoeletro.dds.features.auth

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.launch

@Composable
fun FirstAccessGate(
    content: @Composable () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember(context) {
        FirstAccessGateStore(context.applicationContext)
    }

    val unlocked by store.unlockedFlow.collectAsState(initial = false)

    if (unlocked) {
        content()
    } else {
        FirstAccessScreen(
            onUnlocked = {
                scope.launch {
                    store.unlockDevice()
                }
            }
        )
    }
}