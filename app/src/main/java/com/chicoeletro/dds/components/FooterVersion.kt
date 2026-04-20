// Módulo: app/src/main/java/com/chicoeletro/dds/components/FooterVersion.kt
// Função: Componente de UI para o rodapé persistente. Exibe a versão do app, sinaliza ambientes 
//         de teste e apresenta status dinâmicos (sucesso/erro/aviso).
// Tecnologias: Jetpack Compose, Android PackageManager.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.Icon
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.Color

@Composable
fun FooterVersion(
    statusText: String? = null,   // compatibilidade
    status: FooterStatus? = null, // 👆 novo: status estruturado (cor + ícone)
    isTestVersion: Boolean = false
) {
    val ctx = LocalContext.current

    val versionName by remember {
        mutableStateOf(
            try {
                ctx.packageManager
                    .getPackageInfo(ctx.packageName, 0)
                    .versionName
            } catch (e: Exception) {
                "??"
            }
        )
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        // ---- STATUS (texto + ícone + cor) ----
        if (status != null && status.text.isNotBlank()) {
            val (icon, tint) = when (status.kind) {
                FooterStatusKind.WARNING -> Icons.Filled.WarningAmber to MaterialTheme.colorScheme.error
                FooterStatusKind.SUCCESS -> Icons.Filled.CheckCircle to Color(0xFF2E7D32)
                FooterStatusKind.NORMAL  -> Icons.Filled.Info to MaterialTheme.colorScheme.primary
            }

            Row(
                modifier = Modifier.weight(1f, fill = false),
                verticalAlignment = Alignment.CenterVertically
            ) {
                androidx.compose.material3.Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = tint,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    text = status.text,
                    style = MaterialTheme.typography.labelMedium,
                    color = tint,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

        } else {
            Spacer(Modifier.weight(1f, fill = false))
        }

        Text(
            text = "Versão: $versionName${if (isTestVersion) " (Versão de Testes)" else ""}",
            style = MaterialTheme.typography.labelSmall,
            color = if (isTestVersion) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}