// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/UpdateTrainingsUseCase.kt
// Função: Caso de uso que orquestra a sincronização do repositório de treinamentos. Combina 
//         manifesto remoto, estado local e downloads para manter o conteúdo atualizado.
// Tecnologias: Kotlin Coroutines (Flow), Clean Architecture.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:


package com.chicoeletro.dds.data.sync

import android.util.Log
import kotlinx.coroutines.CancellationException
import java.io.File
import java.util.Locale
import java.time.LocalDate
import java.time.ZoneId



class UpdateTrainingsUseCase(
    private val remote: ContentRemoteDataSource,
    private val local: ContentLocalDataSource
) {
    /**
     * Sincronização com progress callbacks.
     *
     * @param onOverallPrepare(totalTrainings, overallExpected, overallExisting, overallToDownload)
     * @param onOverallProgress(done, total)           Progresso global (arquivos baixados vs total a baixar)
     * @param onTrainingStart(trainingId, index, expected, existing)
     * @param onTrainingProgress(trainingId, done, expected, overallDone, overallTotal)
     * @param onTrainingEnd(trainingId, downloadedNow)
     *
     * Retorna o total efetivamente baixado (arquivos novos gravados).
     */
    suspend fun executeWithProgress(
        onOverallPrepare: (Int, Int, Int, Int) -> Unit = { _, _, _, _ -> },
        onOverallProgress: (Int, Int) -> Unit = { _, _ -> },
        onTrainingStart: (String, Int, Int, Int) -> Unit = { _, _, _, _ -> },
        onTrainingProgress: (String, Int, Int, Int, Int) -> Unit = { _, _, _, _, _ -> },
        onTrainingEnd: (String, Int) -> Unit = { _, _ -> },
    ): Int {

        // 1) Manifest (treinamentos)
        val items = remote.fetchManifest()

        // 2) Cast do local (precisamos do FileLocalDataSource para purge e leitura de cache)
        val fld = (local as? FileLocalDataSource)
            ?: error("UpdateTrainingsUseCase requer FileLocalDataSource para a sync de arquivos")

        // ====================== RETENÇÃO OFFLINE (5 + ATUAL + 5) ======================
        // Define quais treinamentos ficam no tablet para evitar baixar o ano inteiro.
        val today = LocalDate.now(ZoneId.of("America/Sao_Paulo"))

        val keys = items.mapNotNull { it ->
            val d = parseTrainingDateFromId(it.id) ?: return@mapNotNull null
            TrainingKey(id = it.id, date = d)
        }

        val keepIds = computeKeepTrainingIds(
            allTrainings = keys,
            today = today,
            keepPast = 5,
            keepFuture = 5
        )

        // Se não conseguiu calcular (ids fora do padrão), não filtra para evitar "sumir" tudo.
        val itemsFiltered = if (keepIds.isNotEmpty()) {
            val filtered = items.filter { it.id in keepIds }
            Log.d("UpdateUseCase", "Retenção offline ativa. Mantendo ${filtered.size}/${items.size} treinamentos no tablet.")
            filtered
        } else {
            Log.w("UpdateUseCase", "Retenção offline: keepIds vazio (ids fora do padrão?). Sync sem filtro.")
            items
        }


        // 3) Lista de IMAGENS esperadas por treinamento (caminhos completos do Storage)
        val remoteFb = remote as? FirebaseRemoteDataSource
        var purgeEligible = false
        val expectedByTraining: Map<String, List<String>> = itemsFiltered.associate { item ->
            val imgs = try {
                val got = remoteFb?.listImagesFor(item.id) ?: emptyList()
                // ✅ "Contato válido" com a origem: permite purge somente se houver alta confiança
                // (manifest do Firestore ou lista.json baixada fresh; não permite purge baseado em stale)
                if (remoteFb?.canPurgeWithConfidence() == true) purgeEligible = true
                got
            } catch (e: Exception) {
                Log.w("UpdateUseCase", "Falha ao listar imagens para ${item.id}: ${e.message}")
                emptyList()
            }
            item.id to imgs
        }

        // 4) trainingsRoot (mantido, caso queira usar em logs/futuro)
        // val trainingsRoot = fld.trainingRoot()

        // 5) Converter esperados (FULL) → RELATIVOS (preservando subpastas após o trainingId)
        //    e calcular existentes RELATIVOS no cache local.
        val expectedRelByTraining: Map<String, Set<String>> = expectedByTraining.mapValues { (id, fulls) ->
            fulls.map { f ->
                val rel = remoteFb?.relativeLocalPathFor(f, id) ?: f.substringAfterLast('/')
                rel.replace('\\', '/').lowercase(Locale.ROOT)
            }.toSet()
        }

        var overallExpected = 0
        var overallExisting = 0
        expectedRelByTraining.forEach { (id, expectedRel) ->
            val dir = fld.trainingDir(id)
            val existingRel = listRelativeFiles(dir).toSet()
            overallExpected += expectedRel.size
            overallExisting += existingRel.intersect(expectedRel).size
        }

        val overallToDownload = (overallExpected - overallExisting).coerceAtLeast(0)
        onOverallPrepare(itemsFiltered.size, overallExpected, overallExisting, overallToDownload)

        // 6) Baixar apenas o que falta, emitindo progresso global e por pasta
        var overallDone = 0
        onOverallProgress(overallDone, overallToDownload)
        var totalDownloaded = 0

        itemsFiltered.forEachIndexed { index, item ->
            val dir = fld.trainingDir(item.id).apply { if (!exists()) mkdirs() }
            val expectedRel = expectedRelByTraining[item.id].orEmpty()
            var existingRel = listRelativeFiles(dir).toMutableSet()

            val expected = expectedRel.size
            var doneThis = existingRel.intersect(expectedRel).size
            onTrainingStart(item.id, index, expected, doneThis)

            // Modo legado se não há lista detalhada
            if (expected == 0 || remoteFb == null) {
                try {
                    val before = listRelativeFiles(dir).size
                    remote.downloadAndSave(item)
                    val after = listRelativeFiles(dir).size
                    val downloadedNow = (after - before).coerceAtLeast(0)
                    totalDownloaded += downloadedNow
                    overallDone += downloadedNow
                    onTrainingProgress(item.id, doneThis, expected, overallDone, overallToDownload)
                    onTrainingEnd(item.id, downloadedNow)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Log.w("UpdateUseCase", "Falha em ${item.id} (modo legado): ${e.message}")
                    onTrainingEnd(item.id, 0)
                }
                return@forEachIndexed
            }

            // Baixa um a um comparando por CAMINHO RELATIVO
            var downloadedNow = 0
            expectedByTraining[item.id].orEmpty().forEach { fullPath ->
                val rel = (remoteFb.relativeLocalPathFor(fullPath, item.id))
                    .replace('\\','/').lowercase(Locale.ROOT)

                if (rel in existingRel) {
                    doneThis += 1
                    onTrainingProgress(item.id, doneThis, expected, overallDone, overallToDownload)
                    return@forEach
                }
                try {
                    val ok = remoteFb.downloadImageForTraining(fullPath, item.id, dir)
                    if (ok) {
                        existingRel.add(rel)
                        downloadedNow += 1
                        totalDownloaded += 1
                        overallDone += 1
                        doneThis += 1
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Log.w("UpdateUseCase", "Erro baixando '$fullPath' (${item.id}): ${e.message}")
                } finally {
                    onTrainingProgress(item.id, doneThis, expected, overallDone, overallToDownload)
                }
            }
        }
        // ✅ Purge local: remove pastas que não estão no conjunto mantido.
        // Só executa se houver evidência de remoto válido (purgeEligible).
        // Isso evita apagar cache offline quando não foi possível ler/listar a lista remota.
        if (purgeEligible && keepIds.isNotEmpty() && itemsFiltered.size != items.size) {
            runCatching { fld.purgeTrainingsNotIn(keepIds) }
                .onFailure { e -> Log.w("UpdateUseCase", "Falha ao purgar cache local: ${e.message}") }
        } else {
            Log.d(
                "UpdateUseCase",
                "Purge ignorado (offline/sem lista.json válida). purgeEligible=$purgeEligible keepIds=${keepIds.size}"
            )
        }

        Log.d("UpdateUseCase", "Baixados (novos): $totalDownloaded")
        return totalDownloaded
    }

    // Compatibilidade: mantém execute() simples para quem não precisa de progress
    suspend fun execute(): Int = executeWithProgress()

    // ====================== LIMPEZA DE ÓRFÃOS ======================
    /**
     * Remove do cache local (files/trainings/<trainingId>/...) os arquivos de IMAGEM
     * cujo caminho RELATIVO não conste mais em DDSv2/lista.json.
     * @return quantidade de arquivos removidos
     */
    suspend fun cleanupTrainingOrphans(trainingId: String, dryRun: Boolean = false): Int {
        val remoteFb = remote as? FirebaseRemoteDataSource ?: return 0
        val fld = (local as? FileLocalDataSource) ?: return 0
        val root = fld.trainingDir(trainingId).apply { if (!exists()) return 0 }

        val expectedRel = remoteFb.listImagesFor(trainingId)
            .map { remoteFb.relativeLocalPathFor(it, trainingId).replace('\\','/').lowercase(Locale.ROOT) }
            .toSet()

        var removed = 0
        val q = ArrayDeque<File>()
        q.add(root)
        while (q.isNotEmpty()) {
            val d = q.removeFirst()
            d.listFiles()?.forEach { f ->
                if (f.isDirectory) { q.add(f) } else {
                    val rel = f.absolutePath
                        .removePrefix(root.absolutePath)
                        .trimStart(File.separatorChar)
                        .replace('\\','/')
                        .lowercase(Locale.ROOT)
                    val isImage = f.extension.lowercase(Locale.ROOT) in setOf("jpg","jpeg","png","webp")
                    if (isImage && rel !in expectedRel) {
                        if (dryRun) {
                            Log.d("UpdateUseCase","(dry-run) remover: ${f.absolutePath}")
                        } else if (runCatching { f.delete() }.getOrDefault(false)) {
                            removed++
                        } else {
                            Log.w("UpdateUseCase","falha ao remover: ${f.absolutePath}")
                        }
                    }
                }
            }
        }
        // Apaga diretórios vazios
        fun deleteEmpty(dir: File) {
            dir.listFiles()?.forEach { f ->
                if (f.isDirectory) {
                    deleteEmpty(f)
                    if (f.listFiles()?.isEmpty() == true) runCatching { f.delete() }
                }
            }
        }
        deleteEmpty(root)
        return removed
    }

    /**
    * Remove pastas inteiras de treinamentos locais que não existem mais no manifest remoto.
    * Ex.: se o servidor apagou "2026-01-10 - TEMA X", essa pasta deve sumir do tablet.
    * @return quantidade de treinamentos (pastas) removidos
    */
    suspend fun cleanupRemovedTrainings(
            remoteIds: Set<String>,
            dryRun: Boolean = false,
            onRemoved: (String) -> Unit = {}
        ): Int {
            val fld = (local as? FileLocalDataSource) ?: return 0
            val root = fld.trainingRoot()
            if (!root.exists()) return 0

            val localDirs = root.listFiles()
                ?.filter { it.isDirectory && !it.name.startsWith(".") }
                .orEmpty()

            var removedTrainings = 0
            for (dir in localDirs) {
                val id = dir.name
                if (id !in remoteIds) {
                    if (dryRun) {
                        Log.d("UpdateUseCase", "(dry-run) remover treinamento local: ${dir.absolutePath}")
                        onRemoved(id)
                        removedTrainings++
                    } else {
                        val ok = runCatching { dir.deleteRecursively() }.getOrDefault(false)
                        if (ok) {
                            onRemoved(id)
                            removedTrainings++
                        } else {
                            Log.w("UpdateUseCase", "Falha ao remover pasta do treinamento: ${dir.absolutePath}")
                        }
                    }
                }
            }
            return removedTrainings
        }

    /** Limpa órfãos de TODOS os treinamentos do manifest. */
    suspend fun cleanupAllOrphans(
        onTrainingCleanup: (String, Int) -> Unit = { _, _ -> },
        dryRun: Boolean = false
    ): Int {
        val items = remote.fetchManifest()
        val remoteIds = items.map { it.id }.toSet()
        var total = 0
        for (item in items) {
            val r = cleanupTrainingOrphans(item.id, dryRun)
            total += r
            onTrainingCleanup(item.id, r)
        }

        // ✅ NOVO: remove treinamentos locais que não existem mais no servidor
        val removedTrainings = cleanupRemovedTrainings(
            remoteIds = remoteIds,
            dryRun = dryRun,
            onRemoved = { id -> Log.d("UpdateUseCase", "Removido do cache (treinamento apagado no servidor): $id") }
        )
        if (removedTrainings > 0) {
            Log.d("UpdateUseCase", "Treinamentos removidos do cache (não existem mais no servidor): $removedTrainings")
        }

        return total
    }

    // ====================== HELPERS LOCAIS ======================
    /** Lista arquivos relativos (lowercase, com '/') em uma raiz. */
    private fun listRelativeFiles(root: File?): List<String> {
        if (root == null || !root.exists()) return emptyList()
        val out = mutableListOf<String>()
        val q = ArrayDeque<File>()
        q.add(root)
        while (q.isNotEmpty()) {
            val d = q.removeFirst()
            d.listFiles()?.forEach { f ->
                if (f.isDirectory) q.add(f) else {
                    val rel = f.absolutePath
                        .removePrefix(root.absolutePath)
                        .trimStart(File.separatorChar)
                        .replace('\\','/')
                        .lowercase(Locale.ROOT)
                    out += rel
                }
            }
        }
        return out
    }
}