// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoCalculations.kt
// Função: Funções puras de cálculo de tempo ativo, intervalos, tempos de serviço e análise de lacunas ociosas ("SEM EXECUÇÃO").
// Tecnologias: Kotlin, Jetpack Compose.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.turno

import androidx.compose.ui.graphics.Color
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// Cores e Auxiliares de Apresentação
fun getTurnoColor(estado: EstadoTurno): Color {
    return when (estado) {
        EstadoTurno.ABERTO -> Color(0xFF2E7D32) // Green 800
        EstadoTurno.INTERVALO -> Color(0xFFEF6C00) // Orange 800
        EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFF1565C0) // Blue 800
        EstadoTurno.FECHADO -> Color(0xFFC62828) // Red 800
    }
}

fun getTurnoBgColor(estado: EstadoTurno): Color {
    return when (estado) {
        EstadoTurno.ABERTO -> Color(0xFFE8F5E9) // Light Green
        EstadoTurno.INTERVALO -> Color(0xFFFFF3E0) // Light Orange
        EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFFE3F2FD) // Light Blue
        EstadoTurno.FECHADO -> Color(0xFFFFEBEE) // Light Red
    }
}

fun obterTextoTransicao(trans: TurnoTransition, todasTrans: List<TurnoTransition>): String {
    return when (trans.estado) {
        EstadoTurno.ABERTO -> {
            val ordenadas = todasTrans.sortedBy { it.timestampMs }
            val index = ordenadas.indexOf(trans)
            val temAnteriorAberto = if (index > 0) {
                ordenadas.subList(0, index).any { it.estado == EstadoTurno.ABERTO }
            } else false
            if (temAnteriorAberto) "Retomada de Turno" else "Abertura de Turno"
        }
        EstadoTurno.INTERVALO -> "Intervalo"
        EstadoTurno.DESLOCAMENTO_ESPECIAL -> "Deslocamento Especial"
        EstadoTurno.FECHADO -> "Fim de Turno"
    }
}

fun obterCoresTransicao(estado: EstadoTurno): Pair<Color, Color> {
    return when (estado) {
        EstadoTurno.ABERTO -> Color(0xFFE8F5E9) to Color(0xFF2E7D32)
        EstadoTurno.INTERVALO -> Color(0xFFFFF3E0) to Color(0xFFEF6C00)
        EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFFE3F2FD) to Color(0xFF1565C0)
        EstadoTurno.FECHADO -> Color(0xFFFFEBEE) to Color(0xFFC62828)
    }
}

// Lógica de Cálculo de Tempos
fun calcularTempoIntervalo(transitions: List<TurnoTransition>, nowMs: Long): Long {
    var totalIntervalMs = 0L
    var intervalStartMs: Long? = null
    
    val sorted = transitions.sortedBy { it.timestampMs }
    for (t in sorted) {
        if (t.estado == EstadoTurno.INTERVALO) {
            intervalStartMs = t.timestampMs
        } else if (intervalStartMs != null) {
            totalIntervalMs += (t.timestampMs - intervalStartMs)
            intervalStartMs = null
        }
    }
    
    if (intervalStartMs != null) {
        totalIntervalMs += (nowMs - intervalStartMs)
    }
    return totalIntervalMs
}

fun calcularTempoAtivo(transitions: List<TurnoTransition>, openedAtMs: Long?, nowMs: Long): Long {
    val startMs = openedAtMs ?: transitions.minOfOrNull { it.timestampMs } ?: return 0L
    val endMs = transitions.find { it.estado == EstadoTurno.FECHADO }?.timestampMs ?: nowMs
    val elapsed = endMs - startMs
    val interval = calcularTempoIntervalo(transitions, nowMs)
    return maxOf(0L, elapsed - interval)
}

fun calcularIntervaloSobreposto(
    serviceStartMs: Long,
    serviceEndMs: Long,
    transitions: List<TurnoTransition>,
    nowMs: Long
): Long {
    var overlappedMs = 0L
    val sorted = transitions.sortedBy { it.timestampMs }
    var intervalStartMs: Long? = null
    
    for (t in sorted) {
        if (t.estado == EstadoTurno.INTERVALO) {
            intervalStartMs = t.timestampMs
        } else if (intervalStartMs != null) {
            val intervalEndMs = t.timestampMs
            val overlapStart = maxOf(serviceStartMs, intervalStartMs)
            val overlapEnd = minOf(serviceEndMs, intervalEndMs)
            if (overlapStart < overlapEnd) {
                overlappedMs += (overlapEnd - overlapStart)
            }
            intervalStartMs = null
        }
    }
    
    if (intervalStartMs != null) {
        val intervalEndMs = nowMs
        val overlapStart = maxOf(serviceStartMs, intervalStartMs)
        val overlapEnd = minOf(serviceEndMs, intervalEndMs)
        if (overlapStart < overlapEnd) {
            overlappedMs += (overlapEnd - overlapStart)
        }
    }
    
    return overlappedMs
}

fun obterTemposServico(
    ss: BdoSs,
    turnoTransitions: List<TurnoTransition>,
    nowMs: Long
): Triple<Long, Long, Long> {
    val tDesl = ss.transitions.find { it.status == SsStatus.DESLOCAMENTO }?.timestampMs
        ?: ss.transitions.firstOrNull()?.timestampMs
        ?: return Triple(0L, 0L, 0L)
        
    val tExec = ss.transitions.find { it.status == SsStatus.EXECUCAO }?.timestampMs
    val tEnd = ss.transitions.find { it.status == SsStatus.CONCLUSAO || it.status == SsStatus.CANCELADO }?.timestampMs
    
    val displacementMs: Long
    val executionMs: Long
    val totalMs: Long
    
    if (tEnd != null) {
        val actualExec = tExec ?: tEnd
        displacementMs = maxOf(0L, actualExec - tDesl)
        executionMs = maxOf(0L, tEnd - actualExec)
        totalMs = maxOf(0L, tEnd - tDesl)
    } else if (tExec != null) {
        displacementMs = maxOf(0L, tExec - tDesl)
        executionMs = maxOf(0L, nowMs - tExec)
        totalMs = maxOf(0L, nowMs - tDesl)
    } else {
        displacementMs = maxOf(0L, nowMs - tDesl)
        executionMs = 0L
        totalMs = maxOf(0L, nowMs - tDesl)
    }
    
    val endDesl = tExec ?: tEnd ?: nowMs
    val intervalDesl = calcularIntervaloSobreposto(tDesl, endDesl, turnoTransitions, nowMs)
    val netDesl = maxOf(0L, displacementMs - intervalDesl)
    
    val netExec = if (tExec != null || tEnd != null) {
        val startExec = tExec ?: tEnd!!
        val endExec = tEnd ?: nowMs
        val intervalExec = calcularIntervaloSobreposto(startExec, endExec, turnoTransitions, nowMs)
        maxOf(0L, executionMs - intervalExec)
    } else {
        0L
    }
    
    val netTotal = netDesl + netExec
    
    return Triple(netDesl, netExec, netTotal)
}

fun formatDuration(ms: Long): String {
    if (ms <= 0) return "0s"
    val seconds = ms / 1000
    val minutes = seconds / 60
    val hours = minutes / 60
    
    return when {
        hours > 0 -> {
            val remMinutes = minutes % 60
            if (remMinutes > 0) "${hours}h ${remMinutes}m" else "${hours}h"
        }
        minutes > 0 -> {
            val remSeconds = seconds % 60
            if (remSeconds > 0) "${minutes}m ${remSeconds}s" else "${minutes}m"
        }
        else -> "${seconds}s"
    }
}

// Algoritmo de Cálculo de Lacunas SEM EXECUÇÃO
fun calcularLacunasSemExecucao(
    bdoList: List<BdoSs>,
    transicoes: List<TurnoTransition>,
    nowMs: Long
): List<Pair<Long, Pair<Long, Long>>> { // Retorna lista de Pair(Duração, Pair(Início, Fim))
    if (transicoes.isEmpty()) return emptyList()

    // 1. Encontrar períodos ativos de turno (ABERTO / DESLOCAMENTO_ESPECIAL)
    val sortedTrans = transicoes.sortedBy { it.timestampMs }
    val activeIntervals = mutableListOf<Pair<Long, Long>>()
    var activeStart: Long? = null

    for (t in sortedTrans) {
        if (t.estado == EstadoTurno.ABERTO || t.estado == EstadoTurno.DESLOCAMENTO_ESPECIAL) {
            if (activeStart == null) {
                activeStart = t.timestampMs
            }
        } else if (t.estado == EstadoTurno.INTERVALO || t.estado == EstadoTurno.FECHADO) {
            if (activeStart != null) {
                activeIntervals.add(Pair(activeStart, t.timestampMs))
                activeStart = null
            }
        }
    }
    if (activeStart != null) {
        activeIntervals.add(Pair(activeStart, nowMs))
    }

    // 2. Coletar intervalos de serviços ativos/concluídos
    val serviceIntervals = bdoList.mapNotNull { ss ->
        val tDesl = ss.transitions.find { it.status == SsStatus.DESLOCAMENTO }?.timestampMs
            ?: ss.transitions.firstOrNull()?.timestampMs
            ?: return@mapNotNull null
        val tEnd = ss.transitions.find { it.status == SsStatus.CONCLUSAO || it.status == SsStatus.CANCELADO }?.timestampMs
        val endMs = tEnd ?: nowMs
        Pair(tDesl, endMs)
    }

    // 3. Mesclar intervalos de serviço que se sobrepõem
    val sortedServiceIntervals = serviceIntervals.sortedBy { it.first }
    val mergedBusy = mutableListOf<Pair<Long, Long>>()
    for (interval in sortedServiceIntervals) {
        if (mergedBusy.isEmpty()) {
            mergedBusy.add(interval)
        } else {
            val last = mergedBusy.last()
            if (interval.first <= last.second) {
                mergedBusy[mergedBusy.lastIndex] = Pair(last.first, maxOf(last.second, interval.second))
            } else {
                mergedBusy.add(interval)
            }
        }
    }

    // 4. Subtrair intervalos de serviço de cada período ativo de turno para achar lacunas
    val gaps = mutableListOf<Pair<Long, Pair<Long, Long>>>()
    val fiveMinutesMs = 5 * 60 * 1000L

    for (active in activeIntervals) {
        val activeStartMs = active.first
        val activeEndMs = active.second

        // Encontrar os períodos ocupados dentro deste período ativo
        val clampedBusyInActive = mergedBusy.mapNotNull { busy ->
            val start = maxOf(busy.first, activeStartMs)
            val end = minOf(busy.second, activeEndMs)
            if (start < end) Pair(start, end) else null
        }.sortedBy { it.first }

        var lastEnd = activeStartMs
        for (busy in clampedBusyInActive) {
            if (busy.first > lastEnd) {
                val diff = busy.first - lastEnd
                if (diff > fiveMinutesMs) {
                    gaps.add(Pair(diff, Pair(lastEnd, busy.first)))
                }
            }
            lastEnd = maxOf(lastEnd, busy.second)
        }

        if (activeEndMs > lastEnd) {
            val diff = activeEndMs - lastEnd
            if (diff > fiveMinutesMs) {
                gaps.add(Pair(diff, Pair(lastEnd, activeEndMs)))
            }
        }
    }

    return gaps
}
