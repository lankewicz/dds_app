package com.chicoeletro.dds.ui.training

import com.chicoeletro.dds.data.Training
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

data class TrainingDisplay(
    val line1: String,
    val line2: String
)

private val ISO_DATE: DateTimeFormatter = DateTimeFormatter.ISO_LOCAL_DATE
private val BR_DATE: DateTimeFormatter = DateTimeFormatter.ofPattern("dd/MM/yyyy")


// -----------------------------------------------------------------------------
// Datas / parsing
// -----------------------------------------------------------------------------
/**
 * Extrai data ISO do id no formato "YYYY-MM-DD - TÍTULO".
 * Retorna null se não conseguir parsear.
 */
fun trainingIsoDateFromId(id: String): LocalDate? {
    val iso = id.substringBefore(" - ").trim()
    return runCatching { LocalDate.parse(iso, ISO_DATE) }.getOrNull()
}

// -----------------------------------------------------------------------------
// Título "bonitinho" (usado no progresso de sync)
// -----------------------------------------------------------------------------
/**
 * Ex.: "2025-12-12 - DIREITO DE RECUSA E APR" -> "Direito De Recusa E Apr"
 * Mantém comportamento atual, apenas fora do MainLayoutContainer.
*/
fun trainingTitleFromId(id: String?, locale: Locale = Locale.getDefault()): String {
    if (id.isNullOrBlank()) return "..."
    val raw = id.substringAfter(" - ", id).trim()
    return raw
        .lowercase(locale)
        .split(" ")
        .joinToString(" ") { w ->
            w.replaceFirstChar { ch ->
                if (ch.isLowerCase()) ch.titlecase(locale) else ch.toString()
            }
        }
}

// -----------------------------------------------------------------------------
// Expiração (vencimento = data do treinamento + 2 dias úteis)
// -----------------------------------------------------------------------------
private fun isBusinessDay(date: LocalDate): Boolean =
    date.dayOfWeek.value in 1..5 // seg(1) a sex(5)

private fun addBusinessDays(start: LocalDate, days: Int): LocalDate {
    var result = start
    var added = 0
    while (added < days) {
        result = result.plusDays(1)
        if (isBusinessDay(result)) added++
    }
    return result
}

/**
* Retorna true quando o treinamento (ID no formato "YYYY-MM-DD - ...") está expirado.
* Regra atual do app: vencimento = data + 2 dias úteis.
*/
fun isExpiredTrainingId(trainingId: String, today: LocalDate = LocalDate.now()): Boolean {
    val trainingDate = trainingIsoDateFromId(trainingId) ?: return false
    val dueDate = addBusinessDays(trainingDate, 2)
    return today.isAfter(dueDate)
}


/**
 * Identifica se o treinamento é DDS ONLINE.
 * Regra: título iniciado por "DDS ONLINE" (case-insensitive).
 */
fun isDdsOnline(training: Training): Boolean {
    return training.title.trim().startsWith("DDS ONLINE", ignoreCase = true)
}

/**
 * Para DDS ONLINE, tenta extrair horário do final do título:
 * ex: "DDS ONLINE - 2300" => "23:00"
 * Se não bater, retorna null e exibe apenas a data.
 */
fun parseDdsOnlineTime(title: String): String? {
    val raw = title.trim()
    if (!raw.startsWith("DDS ONLINE", ignoreCase = true)) return null

    val parts = raw.split(" - ", limit = 2)
    val timeDigits = parts.getOrNull(1)?.trim() ?: return null
    if (timeDigits.length != 4 || timeDigits.any { !it.isDigit() }) return null

    val hh = timeDigits.substring(0, 2)
    val mm = timeDigits.substring(2, 4)
    return "$hh:$mm"
}

/**
 * Regra de visibilidade solicitada:
 * - DDS ONLINE: mostrar de (data - 2 dias) até (data + 10 dias)
 * - Outros: mostrar somente a partir do dia agendado, até (data + 10 dias)
 *
 * Observação: isso também atende "treinamentos antigos aparecem até 10 dias depois".
 */
fun shouldShowTraining(training: Training, today: LocalDate = LocalDate.now()): Boolean {
    val scheduled = trainingIsoDateFromId(training.id) ?: return false
    val lastVisible = scheduled.plusDays(10)
    if (today.isAfter(lastVisible)) return false

    return if (isDdsOnline(training)) {
        val firstVisible = scheduled.minusDays(2)
        !today.isBefore(firstVisible)
    } else {
        // Não adianta treinamento comum: só no dia e depois (até +10)
        !today.isBefore(scheduled)
    }
}

/**
 * Monta as 2 linhas exibidas no card:
 *
 * - DDS ONLINE - 2300 => "dd/MM/yyyy - 23:00" e "DDS ONLINE"
 * - DDS ONLINE (sem horário) => "dd/MM/yyyy" e "DDS ONLINE"
 * - Outros => usa Training.date e Training.title como estão hoje
 */
fun buildTrainingDisplay(training: Training): TrainingDisplay {
    if (isDdsOnline(training)) {
        val scheduled = trainingIsoDateFromId(training.id)
        val dateText = scheduled?.format(BR_DATE) ?: training.date

        val hhmm = parseDdsOnlineTime(training.title)
        val line1 = if (hhmm != null) "$dateText - $hhmm" else dateText

        return TrainingDisplay(
            line1 = line1,
            line2 = "DDS ONLINE"
        )
    }

    return TrainingDisplay(
        line1 = training.date,
        line2 = training.title
    )
}
