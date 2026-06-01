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
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.Alignment
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

    Surface(
        color = bg,
        shape = MaterialTheme.shapes.small,
        modifier = modifier.clickable { onClick() }
    ) {
        Box(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 12.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = label,
                color = fg,
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.ExtraBold),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}