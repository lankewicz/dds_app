// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/PendingBadge.kt
// Função: Indicador visual para itens pendentes de sincronização. Exibe contadores de 
//         formulários e turnos aguardando envio para a nuvem.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
// - 02/02/2026: Criação inicial do chip "X pendentes" (AssistChip) com ícone de upload.

package com.chicoeletro.dds.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun PendingBadge(
    count: Int,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null
) {
    if (count <= 0) return

    val label = "$count pendente" + if (count == 1) "" else "s"

    AssistChip(
        onClick = { onClick?.invoke() },
        label = { Text(label) },
        leadingIcon = {
            Icon(
                imageVector = Icons.Filled.CloudUpload,
                contentDescription = "Pendentes para envio"
            )
        },
        modifier = modifier
    )
}