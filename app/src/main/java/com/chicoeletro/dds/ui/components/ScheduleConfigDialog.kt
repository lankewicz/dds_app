// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/ScheduleConfigDialog.kt
// Função: Interface para configuração de cronograma semanal. Permite definir horários de 
//         trabalho diários e gerenciar a escala da equipe de forma interativa.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.chicoeletro.dds.core.DailySchedule
import com.chicoeletro.dds.core.WorkSchedule
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScheduleConfigDialog(
    initialSchedule: WorkSchedule,
    onDismiss: () -> Unit,
    onSave: (WorkSchedule) -> Unit
) {
    var days by remember { mutableStateOf(initialSchedule.days) }

    fun calculateTotal(day: DailySchedule): String {
        if (day.isRestDay) return "0:00"
        val d1 = duration(day.entry1, day.exit1)
        val d2 = duration(day.entry2, day.exit2)
        val totalMinutes = d1 + d2
        val h = totalMinutes / 60
        val m = totalMinutes % 60
        return "%d:%02d".format(h, m)
    }

    fun updateDay(index: Int, block: (DailySchedule) -> DailySchedule) {
        val newList = days.toMutableList()
        val old = newList[index]
        val updated = block(old)
        newList[index] = updated

        // Regra de Redistribuição do Sábado
        if (index == 6) { // Sábado (índice 6 se 1=Dom, 2=Seg...)
            // Na nossa lista (1..7), índice 6 é Sábado se a lista for [Dom, Seg, Ter, Qua, Qui, Sex, Sab]
            // Vamos garantir a ordem: 1=Dom, 2=Seg, ..., 7=Sab.
            if (updated.isRestDay && !old.isRestDay) {
                // Marcou folga no sábado -> redistribui para Seg-Sex (índices 1 a 5)
                for (i in 1..5) {
                    newList[i] = newList[i].copy(
                        entry1 = "07:42", exit1 = "12:00",
                        entry2 = "13:30", exit2 = "18:00"
                    )
                }
            } else if (!updated.isRestDay && old.isRestDay) {
                // Desmarcou folga no sábado -> volta padrão 8h
                for (i in 1..5) {
                    newList[i] = newList[i].copy(
                        entry1 = "08:00", exit1 = "12:00",
                        entry2 = "14:00", exit2 = "18:00"
                    )
                }
                newList[6] = updated.copy(entry1 = "08:00", exit1 = "12:00", entry2 = "", exit2 = "")
            }
        }
        days = newList
    }

    fun copyDown(fromIndex: Int) {
        val source = days[fromIndex]
        val newList = days.toMutableList()
        // Copia para os próximos dias ÚTEIS (Segunda a Sexta)
        // Se for Segunda (1), copia para 2,3,4,5.
        for (i in (fromIndex + 1)..5) {
            newList[i] = newList[i].copy(
                entry1 = source.entry1, exit1 = source.exit1,
                entry2 = source.entry2, exit2 = source.exit2,
                isRestDay = source.isRestDay
            )
        }
        days = newList
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier.fillMaxSize().padding(16.dp),
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surface
        ) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Configurar Horário de Trabalho", style = MaterialTheme.typography.headlineSmall)
                    IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, null) }
                }

                Spacer(Modifier.height(16.dp))

                // Cabeçalho da Tabela
                Row(
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.primaryContainer).padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Dia", Modifier.weight(1.2f), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("Entrada 1", Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text("Saída 1", Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text("Entrada 2", Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text("Saída 2", Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text("Total", Modifier.weight(0.8f), fontWeight = FontWeight.Bold, fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text("Descanso", Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 11.sp, textAlign = TextAlign.Center)
                }

                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    days.forEachIndexed { index, day ->
                        val dayName = when(day.dayOfWeek) {
                            1 -> "Domingo"
                            2 -> "2ª feira"
                            3 -> "3ª feira"
                            4 -> "4ª feira"
                            5 -> "5ª feira"
                            6 -> "6ª feira"
                            7 -> "Sábado"
                            else -> ""
                        }

                        Row(
                            Modifier.fillMaxWidth().border(0.5.dp, Color.LightGray).padding(vertical = 4.dp, horizontal = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(Modifier.weight(1.2f), verticalAlignment = Alignment.CenterVertically) {
                                Text(dayName, fontSize = 13.sp)
                                if (index == 1) { // 2ª feira
                                    IconButton(onClick = { copyDown(1) }, modifier = Modifier.size(24.dp).padding(start = 4.dp)) {
                                        Icon(Icons.Default.ArrowDownward, "Copiar para próximos", Modifier.size(16.dp), tint = MaterialTheme.colorScheme.primary)
                                    }
                                }
                            }
                            
                            // Time inputs
                            TimeInput(Modifier.weight(1f), day.entry1, enabled = !day.isRestDay) { newValue -> updateDay(index) { it.copy(entry1 = newValue) } }
                            TimeInput(Modifier.weight(1f), day.exit1, enabled = !day.isRestDay) { newValue -> updateDay(index) { it.copy(exit1 = newValue) } }
                            TimeInput(Modifier.weight(1f), day.entry2, enabled = !day.isRestDay) { newValue -> updateDay(index) { it.copy(entry2 = newValue) } }
                            TimeInput(Modifier.weight(1f), day.exit2, enabled = !day.isRestDay) { newValue -> updateDay(index) { it.copy(exit2 = newValue) } }

                            Text(calculateTotal(day), Modifier.weight(0.8f), textAlign = TextAlign.Center, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                            
                            Checkbox(
                                checked = day.isRestDay,
                                onCheckedChange = { isChecked -> updateDay(index) { it.copy(isRestDay = isChecked) } },
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                }

                // Total Semanal
                val weeklyTotalMinutes = days.sumOf { day ->
                    if (day.isRestDay) 0L
                    else duration(day.entry1, day.exit1) + duration(day.entry2, day.exit2)
                }
                val weeklyTotalStr = "%d:%02d".format(weeklyTotalMinutes / 60, weeklyTotalMinutes % 60)

                Row(
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("TOTAL SEMANAL", Modifier.weight(5.2f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text(weeklyTotalStr, Modifier.weight(0.8f), textAlign = TextAlign.Center, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.weight(1f))
                }

                Spacer(Modifier.height(16.dp))
                
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) { Text("Cancelar") }
                    Spacer(Modifier.width(8.dp))
                    Button(onClick = { onSave(WorkSchedule(days)) }) { Text("Confirmar") }
                }
            }
        }
    }
}

@Composable
fun TimeInput(
    modifier: Modifier,
    value: String,
    enabled: Boolean,
    onValueChange: (String) -> Unit
) {
    var text by remember(value) { mutableStateOf(value) }
    
    OutlinedTextField(
        value = text,
        onValueChange = { newValue ->
            // Permite apenas números e : e limita tamanho
            val filtered = newValue.filter { c -> c.isDigit() || c == ':' }.take(5)
            text = filtered
        },
        enabled = enabled,
        modifier = modifier.padding(2.dp).onFocusChanged { state ->
            if (!state.isFocused) {
                onValueChange(formatTimeStr(text))
            }
        },
        textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, textAlign = TextAlign.Center),
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
    )
}

// Helpers
private fun duration(start: String, end: String): Long {
    return try {
        val s = LocalTime.parse(formatTimeStr(start))
        val e = LocalTime.parse(formatTimeStr(end))
        if (e.isBefore(s)) 0 else ChronoUnit.MINUTES.between(s, e)
    } catch (e: Exception) { 0 }
}

private fun formatTimeStr(raw: String): String {
    if (raw.isBlank()) return ""
    val clean = raw.replace(":", "")
    if (clean.isEmpty()) return ""
    
    return when (clean.length) {
        1 -> "0$clean:00"
        2 -> "$clean:00"
        3 -> "${clean.substring(0,2)}:0${clean.substring(2)}"
        4 -> "${clean.substring(0,2)}:${clean.substring(2)}"
        else -> "00:00"
    }
}