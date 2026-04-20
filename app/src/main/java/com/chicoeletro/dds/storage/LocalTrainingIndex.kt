// Módulo: app/src/main/java/com/chicoeletro/dds/storage/LocalTrainingIndex.kt
// Função: Gerenciador do índice local de treinamentos. Controla quais DDS estão disponíveis 
//         offline e suas respectivas versões no dispositivo.
// Tecnologias: Jetpack DataStore, Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 08/06/2025: Criação inicial.

package com.chicoeletro.dds.storage

import android.content.Context
import com.chicoeletro.dds.data.Training
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter

/**
 * Indexador local de treinamentos (OFFLINE-FIRST).
 * Pastas esperadas: filesDir/trainings/<ID>, onde <ID> = "YYYY-MM-DD - Título"
 */
object LocalTrainingIndex {

    private val ISO = DateTimeFormatter.ISO_LOCAL_DATE            // "yyyy-MM-dd"
    private val OUT = DateTimeFormatter.ofPattern("dd/MM/yyyy")   // exibição na UI
    private val ID_REGEX = Regex("""^\s*(\d{4}-\d{2}-\d{2})\s*[-–]\s*(.+?)\s*$""")

    // Cache simples para evitar re-scan constante; invalida ao mudar timestamp do diretório/filhos
    @Volatile private var cacheStamp: Long = -1L
    @Volatile private var cache: List<Training> = emptyList()

    /** Lista treinamentos indexando as pastas locais. */
    fun list(context: Context, useCache: Boolean = true): List<Training> {
        val dir = File(context.filesDir, "trainings")
        if (!dir.exists()) return emptyList()

        // "Stamp" barato: XOR do lastModified do diretório com o max dos filhos
        val children = dir.listFiles()?.filter { it.isDirectory && !it.name.startsWith(".") }.orEmpty()
        val stamp = children.fold(dir.lastModified()) { acc, f -> acc xor f.lastModified() }
        if (useCache && stamp == cacheStamp) return cache

        val result = children.asSequence()
            .mapNotNull { folder -> parseId(folder.name) }      // Pair(Training, LocalDate)
            .sortedByDescending { it.second }                   // ordena por LocalDate
            .map { it.first }                                   // mapeia para Training (id/date/title)
            .toList()

        if (useCache) {
            cache = result
            cacheStamp = stamp
        }
        return result
    }

    /** Faz o parse do ID "YYYY-MM-DD - Título" -> Pair(Training, LocalDate). */
    private fun parseId(name: String): Pair<Training, LocalDate>? {
        val m = ID_REGEX.matchEntire(name) ?: return null
        val iso = m.groupValues[1]
        val title = m.groupValues[2].trim().ifEmpty { return null }
        val date = runCatching { LocalDate.parse(iso, ISO) }.getOrNull() ?: return null
        val training = Training(
            id = name,
            date = date.format(OUT),
            title = title
        )
        return training to date
    }

    /** Utilitários úteis para outras partes do app. */
    fun resolveFolder(context: Context, trainingId: String): File =
        File(context.filesDir, "trainings/$trainingId")

    fun exists(context: Context, trainingId: String): Boolean =
        resolveFolder(context, trainingId).exists()

    fun buildId(date: LocalDate, title: String): String =
        "${date.format(ISO)} - ${title.trim()}"

    /** Parse reverso: retorna Triple(id, data, título) ou null se inválido. */
    fun parseIdTriple(id: String): Triple<String, LocalDate, String>? {
        val m = ID_REGEX.matchEntire(id) ?: return null
        val iso = m.groupValues[1]
        val title = m.groupValues[2].trim()
        val date = runCatching { LocalDate.parse(iso, ISO) }.getOrNull() ?: return null
        return Triple(id, date, title)
    }
}