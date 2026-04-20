// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/TrainingRetention.kt
// Função: Política de retenção de dados locais. Gerencia o expurgo de treinamentos antigos e 
//         limpeza de arquivos temporários para otimização do armazenamento.
// Tecnologias: Java Time API, File API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

import java.time.LocalDate

data class TrainingKey(
    val id: String,      // Ex: "2026-02-19 - Tema"
    val date: LocalDate
)

/**
 * Extrai LocalDate do id no padrão "YYYY-MM-DD - ...".
 * Retorna null se não bater o padrão.
 */
fun parseTrainingDateFromId(trainingId: String): LocalDate? {
    val datePart = trainingId.split(" - ", limit = 2).firstOrNull()?.trim() ?: return null
    return runCatching { LocalDate.parse(datePart) }.getOrNull()
}

private fun currentIndex(sortedAsc: List<TrainingKey>, today: LocalDate): Int {
    if (sortedAsc.isEmpty()) return -1

    val exact = sortedAsc.indexOfFirst { it.date == today }
    if (exact >= 0) return exact

    val lastPast = sortedAsc.indexOfLast { !it.date.isAfter(today) } // <= hoje
    if (lastPast >= 0) return lastPast

    return 0 // tudo futuro
}

/** Calcula conjunto de IDs a manter no tablet. */
fun computeKeepTrainingIds(
    allTrainings: List<TrainingKey>,
    today: LocalDate = LocalDate.now(),
    keepPast: Int = 5,
    keepFuture: Int = 5
): Set<String> {
    val sorted = allTrainings.sortedBy { it.date } // asc
    val idx = currentIndex(sorted, today)
    if (idx < 0) return emptySet()

    val start = (idx - keepPast).coerceAtLeast(0)
    val end = (idx + keepFuture).coerceAtMost(sorted.lastIndex)

    return sorted.subList(start, end + 1).map { it.id }.toSet()
}