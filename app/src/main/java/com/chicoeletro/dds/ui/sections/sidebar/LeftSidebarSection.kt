// Módulo: app/src/main/java/com/chicoeletro/dds/ui/sections/sidebar/LeftSidebarSection.kt
// Caminho completo: [PROJECT_ROOT]/app/src/main/java/com/chicoeletro/dds/ui/sections/sidebar/LeftSidebarSection.kt
// Descrição: Composable responsável pela barra lateral esquerda do DDS, incluindo:
//            1) Ações rápidas (Home/Sync/Relatório/Online);
//            2) Barras de progresso do sync;
//            3) Lista de treinamentos com indicação de concluído;
//            4) Card Status do Turno (NOVO) acima do card de Equipe;
//            5) Card de Equipe e participantes.
// Autor: Valdinei Lankewicz
// Criado em: 04/02/2026
// Histórico de alterações:
//   - 04/02/2026: Versão inicial (extraída do MainLayoutContainer; inclui Status do Turno).

package com.chicoeletro.dds.ui.sections.sidebar

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

import com.chicoeletro.dds.data.Training
import com.chicoeletro.dds.features.turno.TurnoStatus
import com.chicoeletro.dds.features.turno.TurnoStatusCard
import com.chicoeletro.dds.ui.training.buildTrainingDisplay
import com.chicoeletro.dds.ui.training.trainingTitleFromId
import com.chicoeletro.dds.ui.sections.TrainingStatus as UiTrainingStatus

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

    // Turno
    turnoStatus: TurnoStatus,
    turnoLastChangedAt: String?,
    turnoAttention: Boolean,
    turnoDeslocamentoMotivo: String?,
    onClickTurno: () -> Unit,

    // Equipe
    equipe: String,
    eletricistas: List<String>,
    onClickEquipe: () -> Unit
) {
    Column(Modifier.width(widthDp.dp).background(Color(0xFFEFEFEF))) {

        Row(
            Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onHome) { Icon(Icons.Filled.Home, contentDescription = "Início") }

            IconButton(onClick = onSyncNow) {
                if (isSyncing) {
                    CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Filled.Refresh, contentDescription = "Sincronizar agora")
                }
            }

            IconButton(onClick = onPresenceReport) {
                Icon(Icons.Filled.CalendarMonth, contentDescription = "Relatório de Presenças", modifier = Modifier.size(30.dp))
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
                val title = trainingTitleFromId(currentId?:"")
                Text("Treinamento: $title — ${currentDone} / ${currentTotal}", style = MaterialTheme.typography.bodySmall)
                LinearProgressIndicator(progress = { pAtual }, modifier = Modifier.fillMaxWidth())
            }
        }

        LazyColumn(Modifier.weight(1f).padding(horizontal = 8.dp)) {
            items(trainings) { t ->
                val isSel = t.id == selectedTraining
                val display = buildTrainingDisplay(t)
                val isDone = trainingStatus.containsKey(t.id)

                Card(
                    elevation = CardDefaults.cardElevation(defaultElevation = if (isSel) 8.dp else 0.dp),
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).clickable { onSelectTraining(t.id) },
                    shape = RoundedCornerShape(4.dp),
                    colors = CardDefaults.cardColors(containerColor = if (isSel) Color(0xFFE0E0E0) else Color.Transparent)
                ) {
                    Row(modifier = Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (isDone) {
                            Icon(Icons.Filled.DoneAll, contentDescription = "Treinamento executado", tint = Color(0xFF2E7D32), modifier = Modifier.size(20.dp))
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

        // NOVO: Status do Turno
        TurnoStatusCard(
            status = turnoStatus,
            lastChangedAt = turnoLastChangedAt,
            deslocamentoMotivo = turnoDeslocamentoMotivo,
            attention = turnoAttention,
            onClick = onClickTurno
        )

        // Equipe
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
