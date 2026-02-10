// Módulo: app/src/main/java/com/chicoeletro/dds/components/PendingUi.kt
// Função: Fornece contador reutilizável e badge compacto para exibir "X pendentes" (fila offline de DDS).
// Autor: Valdinei Lankewicz
//
// Histórico de alterações:
// - 02/02/2026: Criação inicial (polling leve no DataStore) + badge compacto para Header/Footer.

package com.chicoeletro.dds.components

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.data.local.PendingDdsStore
import kotlinx.coroutines.delay

/**
 * Retorna e mantém atualizado o total de DDS pendentes no DataStore.
 *
 * Observação:
 * - usa polling leve para não refatorar o store agora.
 * - 1500~2500ms costuma ser imperceptível e suficiente.
 */
@Composable
fun rememberPendingDdsCount(intervalMs: Long = 2000L): Int {
    val context = LocalContext.current
    var count by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) {
        val store = PendingDdsStore(context)
        while (true) {
            count = runCatching { store.listPending().size }.getOrDefault(0)
            delay(intervalMs)
        }
    }
    return count
}

/** Badge compacto (ícone + número) para Header/Footer. */
@Composable
fun PendingCountBadge(
    count: Int,
    modifier: Modifier = Modifier,
    showText: Boolean = false
) {
    if (count <= 0) return

    if (showText) {
        Row(modifier = modifier) {
            Icon(Icons.Filled.CloudUpload, contentDescription = "Pendentes")
            Spacer(Modifier.width(6.dp))
            Text("$count pendente" + if (count == 1) "" else "s")
        }
        return
    }

    BadgedBox(
        badge = { Badge { Text(count.toString()) } },
        modifier = modifier
    ) {
        Icon(Icons.Filled.CloudUpload, contentDescription = "Pendentes")
    }
}
