// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TurnoBadge.kt
// Função: Indicador visual de status do turno. Exibe reativamente o estado atual da jornada 
//         (Aberto, Intervalo, Fechado) na interface principal.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontWeight
import com.chicoeletro.dds.features.turno.EstadoTurno

@Composable
fun TurnoBadge(
    estado: EstadoTurno,
    nocSs: String? = null,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {

    val (label, bg, fg) = when (estado) {
        EstadoTurno.FECHADO -> Triple("FECHADO", Color(0xFFFFEBEE), Color(0xFFEE0303))
        EstadoTurno.ABERTO -> Triple("ABERTO", Color(0xFFE8F5E9), Color(0xFF069A0A))
        EstadoTurno.INTERVALO -> Triple("INTERVALO", Color(0xFFFFF8E1), Color(0xFFFF5722))
        EstadoTurno.DESLOCAMENTO_ESPECIAL -> Triple("DESLOCAMENTO", Color(0xFFE3F2FD), Color(
            0xFF063BC2
        )
        )
    }

    val nocLabel = nocSs?.trim()?.takeIf { it.isNotEmpty() }?.let { "SS/NOC: $it" }
    val textColor = Color.White

    Surface(
        color = fg,
        shape = MaterialTheme.shapes.small,
        modifier = modifier.clickable { onClick() }
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally
        ) {
            // Linha 0: Rótulo
            Text(
                text = "Turno:",
                color = textColor,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1
            )

            Spacer(Modifier.height(2.dp))

            // Linha 1: Estado
            Text(
                text = label,
                color = textColor, // texto claro
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.ExtraBold),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )

            // Linha 2: SS/NOC (somente quando tiver valor)
            if (nocLabel != null) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = nocLabel,
                    color = textColor,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}