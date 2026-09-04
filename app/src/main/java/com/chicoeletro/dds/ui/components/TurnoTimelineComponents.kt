// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TurnoTimelineComponents.kt
// Função: Componentes de interface da timeline do BDO. Renderiza cartões de serviços, transições de turno e faixas de ociosidade ("SEM EXECUÇÃO").
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.HourglassEmpty
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.features.turno.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

@Composable
fun ServicoItem(
    ss: BdoSs,
    ordinalLabel: String,
    turnoTransitions: List<TurnoTransition>,
    nowMs: Long,
    onAlterarEstado: (SsStatus) -> Unit,
    readOnly: Boolean = false
) {
    val isCancelled = ss.status == SsStatus.CANCELADO || !ss.cancelReason.isNullOrBlank()
    val displayStatus = ss.cancelReason ?: ss.rawStatus ?: ss.status.name
    val statusColor = when {
        isCancelled -> Color(0xFFC62828)
        ss.status == SsStatus.DESLOCAMENTO -> Color(0xFF1565C0)
        ss.status == SsStatus.EXECUCAO -> Color(0xFFEF6C00)
        ss.status == SsStatus.CONCLUSAO -> Color(0xFF2E7D32)
        else -> MaterialTheme.colorScheme.onSurface
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    ) {
        Column(
            modifier = Modifier.padding(12.dp)
        ) {
            // Header: ordinal & ID & status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "$ordinalLabel: ",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    if (!readOnly) {
                        Text(
                            text = ss.ssId,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
                
                Surface(
                    color = statusColor.copy(alpha = 0.12f),
                    shape = MaterialTheme.shapes.small
                ) {
                    Text(
                        text = displayStatus,
                        color = statusColor,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            if (readOnly) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Tipo do serviço", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(ss.serviceType ?: "Não informado", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Protocolo", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(ss.protocol ?: "Não informado", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }

            // State indicators / actions
            if (!readOnly && (ss.status == SsStatus.DESLOCAMENTO || ss.status == SsStatus.EXECUCAO)) {
                val tDesl = ss.getTransitionTime(SsStatus.DESLOCAMENTO)
                val tExec = ss.getTransitionTime(SsStatus.EXECUCAO)
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Button(
                        onClick = {},
                        enabled = false,
                        colors = ButtonDefaults.buttonColors(
                            disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Desl. ${if (tDesl.isNotEmpty()) "($tDesl)" else ""}", style = MaterialTheme.typography.labelSmall)
                    }
                    
                    val isExecActive = ss.status == SsStatus.EXECUCAO
                    val isExecEnabled = ss.status == SsStatus.DESLOCAMENTO
                    Button(
                        onClick = { onAlterarEstado(SsStatus.EXECUCAO) },
                        enabled = isExecEnabled,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            disabledContainerColor = if (isExecActive) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                            disabledContentColor = if (isExecActive) Color.White else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Exec. ${if (tExec.isNotEmpty()) "($tExec)" else ""}", style = MaterialTheme.typography.labelSmall)
                    }
                    
                    Button(
                        onClick = { onAlterarEstado(SsStatus.CONCLUSAO) },
                        enabled = true,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFFE8F5E9),
                            contentColor = Color(0xFF2E7D32)
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Concl.", style = MaterialTheme.typography.labelSmall)
                    }
                    
                    Button(
                        onClick = { onAlterarEstado(SsStatus.CANCELADO) },
                        enabled = true,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFFFFEBEE),
                            contentColor = Color(0xFFC62828)
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Canc.", style = MaterialTheme.typography.labelSmall)
                    }
                }
            } else {
                // Completed service grid
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    val tDesl = ss.getTransitionTime(SsStatus.DESLOCAMENTO)
                    val tExec = ss.getTransitionTime(SsStatus.EXECUCAO)
                    val tConcl = ss.getTransitionTime(SsStatus.CONCLUSAO)
                    val tCanc = ss.getTransitionTime(SsStatus.CANCELADO)
                    
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Deslocamento", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(tDesl.ifEmpty { "-" }, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Execução", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(tExec.ifEmpty { "-" }, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                    }
                    if (ss.status == SsStatus.CONCLUSAO) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                            Text("Conclusão", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(tConcl.ifEmpty { "-" }, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall, color = Color(0xFF2E7D32))
                        }
                    } else {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                            Text("Cancelamento", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(tCanc.ifEmpty { "-" }, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall, color = Color(0xFFC62828))
                        }
                    }
                }
            }

            if (ss.status == SsStatus.CANCELADO && !ss.cancelReason.isNullOrBlank()) {
                Spacer(Modifier.height(4.dp))
                Surface(
                    color = Color(0xFFFFEBEE),
                    shape = MaterialTheme.shapes.small,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Warning,
                            contentDescription = null,
                            tint = Color(0xFFC62828),
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "Motivo: ${ss.cancelReason}",
                            color = Color(0xFFC62828),
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.padding(vertical = 8.dp))

            // Net durations display
            val (deslMs, execMs, totalMs) = obterTemposServico(ss, turnoTransitions, nowMs)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                    Text("Tempo Desloc.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(formatDuration(deslMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                    Text("Tempo Exec.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(formatDuration(execMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                    Text("Tempo Total", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(formatDuration(totalMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}

@Composable
fun TransicaoItem(
    trans: TurnoTransition,
    todasTrans: List<TurnoTransition>
) {
    val (transBg, transFg) = obterCoresTransicao(trans.estado)
    val formattedTime = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).apply {
        timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
    }.format(Date(trans.timestampMs))
    
    Surface(
        color = transBg,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val icon = when (trans.estado) {
                    EstadoTurno.ABERTO -> Icons.Filled.PlayArrow
                    EstadoTurno.INTERVALO -> Icons.Filled.Pause
                    EstadoTurno.DESLOCAMENTO_ESPECIAL -> Icons.Filled.DirectionsCar
                    EstadoTurno.FECHADO -> Icons.Filled.Stop
                }
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = transFg,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = obterTextoTransicao(trans, todasTrans),
                    color = transFg,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            Text(
                text = formattedTime,
                color = transFg,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
fun SemExecucaoItem(item: UnifiedHistoryItem.SemExecucao) {
    val yellowBg = Color(0xFFFFFDE7) // Light yellow/amber
    val yellowFg = Color(0xFFF57F17) // Amber/Yellow
    val timeFormat = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).apply {
        timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
    }
    val startStr = timeFormat.format(Date(item.startMs))
    val endStr = timeFormat.format(Date(item.endMs))
    
    Surface(
        color = yellowBg,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, yellowFg.copy(alpha = 0.3f)),
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Filled.HourglassEmpty,
                    contentDescription = null,
                    tint = yellowFg,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "SEM EXECUÇÃO (${formatDuration(item.durationMs)})",
                    color = yellowFg,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            Text(
                text = "$startStr às $endStr",
                color = yellowFg,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
fun ServiceTableHeader() {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TableCell("#", 0.35f, true)
            TableCell("Tipo", 0.7f, true)
            TableCell("Categoria", 1.05f, true)
            TableCell("Protocolo", 1.25f, true)
            TableCell("Desloc.", 0.8f, true)
            TableCell("Execução", 0.8f, true)
            TableCell("Conclusão", 0.8f, true)
            TableCell("Status", 1.2f, true)
        }
    }
}

@Composable
fun ServiceTableRow(ss: BdoSs, position: Int) {
    val isCancelled = ss.status == SsStatus.CANCELADO || !ss.cancelReason.isNullOrBlank()
    val displayStatus = if (isCancelled) {
        ss.cancelReason?.takeIf { it.isNotBlank() } ?: ss.rawStatus?.takeIf { it.isNotBlank() } ?: "CANCELADO"
    } else {
        ss.rawStatus?.takeIf { it.isNotBlank() } ?: ss.status.name
    }
    val statusColor = when {
        isCancelled -> Color(0xFFC62828)
        ss.status == SsStatus.DESLOCAMENTO -> Color(0xFF1565C0)
        ss.status == SsStatus.EXECUCAO -> Color(0xFFEF6C00)
        ss.status == SsStatus.CONCLUSAO -> Color(0xFF2E7D32)
        else -> MaterialTheme.colorScheme.onSurface
    }
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(4.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TableCell(position.toString(), 0.35f)
            TableCell(ss.serviceType ?: "—", 0.7f)
            TableCell(ss.category ?: "—", 1.05f)
            TableCell(ss.protocol ?: "Não informado", 1.25f)
            TableCell(ss.getTransitionTime(SsStatus.DESLOCAMENTO).ifEmpty { "—" }, 0.8f)
            TableCell(ss.getTransitionTime(SsStatus.EXECUCAO).ifEmpty { "—" }, 0.8f)
            TableCell(ss.getTransitionTime(SsStatus.CONCLUSAO).ifEmpty { "—" }, 0.8f)
            TableCell(displayStatus, 1.2f, color = statusColor)
        }
    }
}

@Composable
fun IntervalTableRow(startMs: Long, endMs: Long) {
    val timeFormat = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).apply {
        timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
    }
    val startStr = if (startMs > 0) timeFormat.format(Date(startMs)) else "—"
    val endStr = if (endMs > 0) timeFormat.format(Date(endMs)) else "—"
    val orangeColor = Color(0xFFE65100)

    Surface(
        color = Color(0xFFFFF3E0),
        shape = RoundedCornerShape(4.dp),
        border = BorderStroke(1.dp, orangeColor.copy(alpha = 0.35f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TableCell("—", 0.35f, color = orangeColor)
            TableCell("INTERVALO", 0.7f, color = orangeColor, header = true)
            TableCell("REFEIÇÃO", 1.05f, color = orangeColor)
            TableCell("—", 1.25f, color = orangeColor)
            TableCell("—", 0.8f, color = orangeColor)
            TableCell(startStr, 0.8f, color = orangeColor)
            TableCell(endStr, 0.8f, color = orangeColor)
            TableCell("INTERVALO", 1.2f, color = orangeColor, header = true)
        }
    }
}

@Composable
fun IntervaloTimelineItem(startMs: Long, endMs: Long) {
    val timeFormat = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).apply {
        timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
    }
    val startStr = if (startMs > 0) timeFormat.format(Date(startMs)) else "—"
    val endStr = if (endMs > 0) timeFormat.format(Date(endMs)) else "—"
    val orangeColor = Color(0xFFE65100)
    val durationMs = if (endMs > startMs && startMs > 0) endMs - startMs else 0L

    Surface(
        color = Color(0xFFFFF3E0),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, orangeColor.copy(alpha = 0.3f)),
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Filled.Pause,
                    contentDescription = null,
                    tint = orangeColor,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(8.dp))
                val durText = if (durationMs > 0) " (${formatDuration(durationMs)})" else ""
                Text(
                    text = "INTERVALO$durText",
                    color = orangeColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            Text(
                text = "$startStr às $endStr",
                color = orangeColor,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
private fun RowScope.TableCell(
    value: String,
    weight: Float,
    header: Boolean = false,
    color: Color = MaterialTheme.colorScheme.onSurface
) {
    Text(
        text = value,
        modifier = Modifier.weight(weight).padding(horizontal = 2.dp),
        style = MaterialTheme.typography.labelSmall,
        fontWeight = if (header) FontWeight.Bold else FontWeight.Medium,
        color = color,
        maxLines = 1,
        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis
    )
}
