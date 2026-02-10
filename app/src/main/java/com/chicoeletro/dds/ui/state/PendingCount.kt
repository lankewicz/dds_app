// Módulo: app/src/main/java/com/chicoeletro/dds/ui/state/PendingCount.kt
// Função: Expõe um Flow<Int> com a quantidade de DDS pendentes (fila offline), para UI exibir badge.
// Autor: Valdinei Lankewicz
//
// Histórico de Alterações:
// - 02/02/2026: Criação inicial do indicador "X pendentes" usando polling simples no DataStore.

package com.chicoeletro.dds.ui.state

import android.content.Context
import com.chicoeletro.dds.data.local.PendingDdsStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Emite periodicamente o total de submissões pendentes no PendingDdsStore.
 *
 * Observação:
 * - Usa polling (intervalMs) para evitar refatoração do DataStore agora.
 * - Depois, se quiser 100% reativo, dá para alterar o PendingDdsStore para expor Flow.
 */
fun pendingCountFlow(
    context: Context,
    intervalMs: Long = 2000L
): Flow<Int> = flow {
    val store = PendingDdsStore(context)
    while (true) {
        emit(store.listPending().size)
        delay(intervalMs)
    }
}
