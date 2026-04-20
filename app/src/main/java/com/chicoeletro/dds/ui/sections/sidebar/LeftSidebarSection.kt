// Módulo: app/src/main/java/com/chicoeletro/dds/ui/sections/sidebar/LeftSidebarSection.kt
// Função: Seção lateral esquerda de navegação. Provê atalhos para os módulos principais e 
//         exibe informações contextuais da equipe e o status de conexão.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:


package com.chicoeletro.dds.ui.sections.sidebar

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.DoneAll
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SignalWifiOff
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.filled.Done
import androidx.compose.animation.core.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.data.Training
import com.chicoeletro.dds.ui.training.buildTrainingDisplay
import com.chicoeletro.dds.ui.training.trainingTitleFromId
import com.chicoeletro.dds.ui.sections.TrainingStatus as UiTrainingStatus

import com.chicoeletro.dds.features.turno.EstadoTurno
import com.chicoeletro.dds.ui.components.TurnoBadge
import com.chicoeletro.dds.storage.TrainingExecSyncState



@Composable
fun LeftSidebarSection(
    widthDp: Int,
    online: Boolean,
    isSyncing: Boolean,
    overallTotal: Int,
    overallDone: Int,
    plannedTrainingsTotal: Int,
    currentTotal: Int,
    currentDone: Int,
    currentId: String?,
    onHome: () -> Unit,
    onSyncNow: () -> Unit,
    onPresenceReport: () -> Unit,
    trainings: List<Training>,
    selectedTraining: String?,
    trainingStatus: Map<String, UiTrainingStatus>, // containsKey(id) = concluído
    onSelectTraining: (String) -> Unit,

    // Destaque de acesso
    presenceReportAccessed: Boolean = true,

    // Turno
    turnoEstado: EstadoTurno = EstadoTurno.FECHADO,
    turnoNocSs: String? = null,
    onClickTurno: () -> Unit = {},

    // Equipe
    equipe: String,
    eletricistas: List<String>,
    onClickEquipe: () -> Unit
) {
    val infiniteTransition = rememberInfiniteTransition(label = "blink")
    val alpha by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 0.3f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "alpha"
    )

    Column(Modifier.width(widthDp.dp).background(Color(0xFFEFEFEF))) {

        Row(
            Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onHome) { Icon(Icons.Filled.Home, contentDescription = "Início") }

            IconButton(
                onClick = onSyncNow,
                enabled = !isSyncing
            ) {
                when {
                    isSyncing -> {
                        CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                    }
                    online -> {
                        Icon(Icons.Filled.Refresh, contentDescription = "Sincronizar agora")
                    }
                    else -> {
                        Icon(
                            Icons.Filled.SignalWifiOff,
                            contentDescription = "Offline — não é possível sincronizar",
                            tint = Color(0xFFF44336)
                        )
                    }
                }
            }
            IconButton(onClick = onPresenceReport) {
                val iconAlpha = if (!presenceReportAccessed) alpha else 1f
                Icon(
                    imageVector = Icons.Filled.CalendarMonth,
                    contentDescription = "Relatório de Produção da Equipe",
                    modifier = Modifier.size(30.dp),
                    tint = (if (!presenceReportAccessed) Color(0xFF4CAF50) else LocalContentColor.current).copy(alpha = iconAlpha)
                )
            }

            Icon(
                imageVector = if (online) Icons.Filled.Wifi else Icons.Filled.SignalWifiOff,
                contentDescription = if (online) "Online" else "Offline",
                tint = if (online) Color(0xFF4CAF50) else Color(0xFFF44336),
                modifier = Modifier.size(28.dp)
            )
        }

        if (isSyncing) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp)) {
                val pGlobal = if (overallTotal > 0) overallDone.toFloat() / overallTotal else 0f
                Text("Baixando: ${plannedTrainingsTotal} treinamento(s)", style = MaterialTheme.typography.bodySmall)
                LinearProgressIndicator(progress = { pGlobal }, modifier = Modifier.fillMaxWidth())

                Spacer(Modifier.height(6.dp))

                val pAtual = if (currentTotal > 0) currentDone.toFloat() / currentTotal else 0f
                val title = trainingTitleFromId(currentId ?: "")
                Text("Treinamento: $title — ${currentDone} / ${currentTotal}", style = MaterialTheme.typography.bodySmall)
                LinearProgressIndicator(progress = { pAtual }, modifier = Modifier.fillMaxWidth())
            }
        }

        LazyColumn(Modifier.weight(1f).padding(horizontal = 8.dp)) {
            items(trainings) { t ->
                val isSel = t.id == selectedTraining
                val display = buildTrainingDisplay(t)
                val status = trainingStatus[t.id]
                val isDone = status != null

                Card(
                    elevation = CardDefaults.cardElevation(defaultElevation = if (isSel) 8.dp else 0.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp)
                        .clickable { onSelectTraining(t.id) },
                    shape = RoundedCornerShape(4.dp),
                    colors = CardDefaults.cardColors(containerColor = if (isSel) Color(0xFFE0E0E0) else Color.Transparent)
                ) {
                    Row(modifier = Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (isDone) {
                            val icon = if (status?.syncState == TrainingExecSyncState.SYNCED) {
                                Icons.Filled.DoneAll
                            } else {
                                Icons.Filled.Done
                            }
                            val description = if (status?.syncState == TrainingExecSyncState.SYNCED) {
                                "Treinamento sincronizado"
                            } else {
                                "Treinamento salvo offline"
                            }
                            Icon(
                                icon,
                                contentDescription = description,
                                tint = Color(0xFF2E7D32),
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                        } else {
                            Spacer(Modifier.width(28.dp))
                        }
                        Column {
                            Text(display.line1, style = MaterialTheme.typography.bodyMedium)
                            Spacer(Modifier.height(4.dp))
                            Text(display.line2, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }

        Box(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp)) {
            TurnoBadge(
                estado = turnoEstado,
                nocSs = turnoNocSs,
                modifier = Modifier.fillMaxWidth(),
                onClick = onClickTurno
            )
        }


        Card(
            Modifier.fillMaxWidth().padding(8.dp).clickable { onClickEquipe() },
            colors = CardDefaults.cardColors(containerColor = Color(0xFFCCEEFF)),
            shape = RoundedCornerShape(8.dp)
        ) {
            Box(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(8.dp)) {
                    Text("Equipe: ${equipe.ifBlank { "(não definida)" }}", style = MaterialTheme.typography.bodyMedium)
                    if (eletricistas.isNotEmpty() && equipe.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        eletricistas.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                    }
                }
                IconButton(
                    onClick = onClickEquipe,
                    modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                ) {
                    Icon(Icons.Filled.Settings, contentDescription = "Editar equipe", tint = Color.DarkGray)
                }
            }
        }
    }
}