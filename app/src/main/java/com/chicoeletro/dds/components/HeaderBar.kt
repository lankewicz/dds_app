// Módulo: app/src/main/java/com/chicoeletro/dds/components/HeaderBar.kt
// Função: Cabeçalho superior da aplicação. Exibe o título do DDS, contador de pendências e a 
//         régua visual de participação mensal da equipe.
// Tecnologias: Jetpack Compose, Kotlin State Objects.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:


package com.chicoeletro.dds.components
// --- Android/Compose
import androidx.compose.foundation.border
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material.icons.filled.Chat
import androidx.compose.ui.platform.LocalContext
import android.widget.Toast
import androidx.compose.runtime.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// --- Projeto
import com.chicoeletro.dds.R
import com.chicoeletro.dds.components.PendingCountBadge
import com.chicoeletro.dds.components.rememberPendingDdsCount
import com.chicoeletro.dds.ui.training.MonthParticipationDay



// Estado global para compartilhar partes do título entre módulos
object HeaderBarState {
    var datePart: String = ""
    var titlePart: String = ""
}

@Composable
fun HeaderBar(
    overlayAlpha: Float,
    selectedTraining: String?,
    monthParticipationDays: List<MonthParticipationDay> = emptyList(),
    showTestCameraButton: Boolean = false,
    onTestCameraClick: (() -> Unit)? = null,
    onCommunicationClick: () -> Unit = {},
    bubbleColor: Color = Color.Gray
) {
    val pendingCount = rememberPendingDdsCount()

    val raw = selectedTraining.orEmpty()
    val hasSelection = !selectedTraining.isNullOrBlank()

    val date = if (hasSelection) raw.substringBefore(" -").trim() else ""
    val title = if (hasSelection) {
        raw.substringAfter("- ")
            .trim()
            .takeUnless { it.isBlank() }
            ?: "Diálogo Diário de Segurança"
    } else {
        "Diálogo Diário de Segurança"
    }
    val context = LocalContext.current

    HeaderBarState.datePart = date
    HeaderBarState.titlePart = title

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 62.dp, max = 96.dp)
            .background(Color.LightGray)
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .alpha(overlayAlpha),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier.weight(1f),
            contentAlignment = Alignment.CenterStart
        ) {
            Image(
                painter = painterResource(id = R.drawable.logo_chico),
                contentDescription = "Logo Chico Eletro",
                modifier = Modifier
                    .heightIn(min = 36.dp, max = 48.dp)
                    .padding(end = 8.dp)
            )
        }

        Column(
            modifier = Modifier.weight(4f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleLarge,
                maxLines = 2,
                textAlign = TextAlign.Center,
                overflow = TextOverflow.Ellipsis
            )

            if (monthParticipationDays.isNotEmpty()) {
                MonthParticipationStrip(days = monthParticipationDays)
            }
        }

        Box(
            modifier = Modifier.weight(1f),
            contentAlignment = Alignment.CenterEnd
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                PendingCountBadge(count = pendingCount)

                if (showTestCameraButton && onTestCameraClick != null) {
                    IconButton(
                        onClick = onTestCameraClick,
                        modifier = Modifier
                            .size(40.dp)
                            .background(Color.DarkGray, CircleShape)
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Videocam,
                            contentDescription = "Teste reunião online",
                            tint = Color.White
                        )
                    }
                }

                // Ícone de Comunicação (Futuro)
                var lastClickTime by remember { mutableStateOf(0L) }
                IconButton(
                    onClick = {
                        val now = System.currentTimeMillis()
                        if (now - lastClickTime < 800) {
                            onCommunicationClick()
                        } else {
                            Toast.makeText(context, "Função de comunicação ainda não disponível", Toast.LENGTH_SHORT).show()
                        }
                        lastClickTime = now
                    }
                ) {
                    Icon(
                        imageVector = Icons.Filled.Chat,
                        contentDescription = "Comunicação",
                        modifier = Modifier.size(28.dp),
                        tint = bubbleColor
                    )
                }
            }
        }
    }
}

@Composable
private fun MonthParticipationStrip(days: List<MonthParticipationDay>) {
    val scrollState = rememberScrollState()

    Row(
        modifier = Modifier
            .padding(top = 4.dp)
            .horizontalScroll(scrollState),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Top
    ) {
        days.forEach { day ->
            DayParticipationCell(day = day)
        }
    }
}

@Composable
private fun DayParticipationCell(day: MonthParticipationDay) {
    val borderColor = when {
        day.isPresent -> Color(0xFF2E7D32)
        day.isAbsent -> Color(0xFFC62828)
        day.isSelected -> MaterialTheme.colorScheme.primary
        else -> Color.Gray
    }

    val backgroundColor = if (day.isSelected) {
        MaterialTheme.colorScheme.primary.copy(alpha = 0.08f)
    } else {
        Color.Transparent
    }

    val symbol = when {
        day.isPresent -> "✓"
        day.isAbsent -> "✕"
        else -> ""
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .size(width = 16.dp, height = 16.dp)
                .background(backgroundColor, RoundedCornerShape(3.dp))
                .border(1.dp, borderColor, RoundedCornerShape(3.dp)),
            contentAlignment = Alignment.Center
        ) {
            if (symbol.isNotEmpty()) {
                Text(
                    text = symbol,
                    fontSize = 9.sp,
                    lineHeight = 9.sp,
                    fontWeight = FontWeight.Bold,
                    color = borderColor
                )
            }
        }

        Text(
            text = day.dayNumber.toString(),
            fontSize = 7.sp,
            lineHeight = 7.sp,
            color = if (day.isSelected) MaterialTheme.colorScheme.primary else Color.DarkGray
        )
    }
}