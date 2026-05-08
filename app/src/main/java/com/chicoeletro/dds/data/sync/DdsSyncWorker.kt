// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/DdsSyncWorker.kt
// Função: Orquestrador de sincronização em segundo plano. Processa a fila de submissões pendentes, 
//         realiza upload de mídias e cria documentos no Firestore com lógica de fallback para erros.
// Tecnologias: WorkManager (CoroutineWorker), Firebase Storage/Firestore, Bitmap/Canvas.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.sync

import android.content.Context
import android.os.Build
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.chicoeletro.dds.data.local.PendingDdsStore
import com.chicoeletro.dds.domain.DdsSubmissionWindowException
import com.chicoeletro.dds.domain.RemoteDdsUploader
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import java.io.File
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.storage.ExecCacheEntry
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.storage.TrainingExecSyncState
import com.chicoeletro.dds.ui.training.trainingIsoDateFromId
import java.time.YearMonth

class DdsSyncWorker(
    ctx: Context,
    params: WorkerParameters
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val store = PendingDdsStore(applicationContext)
        val uploader = RemoteDdsUploader(FirebaseStorage.getInstance(), FirebaseFirestore.getInstance())
        val execRepo = TeamTrainingExecutionRepository()

        val collectionName = inputData.getString("collectionName") ?: "DDS"
        val pastaFotos = inputData.getString("pastaFotos") ?: "DDS_Fotos"
        val duracao = inputData.getString("duracaoDefault") ?: "" // opcional

        val pendentes = store.listPending()
        
        // Limpa qualquer "lixo" antigo que ficou esquecido no armazenamento antes das nossas correções
        cleanupOrphanedFiles(applicationContext, pendentes)

        if (pendentes.isEmpty()) return Result.success()

        var hasFailures = false

        for (s in pendentes) {
            // Regra de Auto-Limpeza/Quarentena (Evitar Head of Line Blocking Permanente)
            if (s.retryCount > 15) {
                // Fallback Gráfico: Desenha um JPEG cinza com placa de erro dinâmico
                try {
                    val fallbackFile = createFallbackImage(applicationContext)
                    val submissionSegura = s.copy(
                        localPhotoPath = fallbackFile.absolutePath,
                        localThumbPath = fallbackFile.absolutePath
                    )
                    
                    val duracaoEfetiva = s.duracao.ifBlank { duracao }
                    // Envio original aceitará o JPEG falso e gerará Link do Storage perfeito.
                    uploader.upload(submissionSegura, collectionName, pastaFotos, duracaoEfetiva)
                    
                    val ym = trainingIsoDateFromId(s.trainingName)?.let { YearMonth.from(it) } ?: YearMonth.now()
                    execRepo.markExecuted(s.equipe, ym, s.trainingName, s.dataConclusao, s.horaConclusao, duracaoEfetiva, Build.MODEL)
                    
                    val teamKey = TeamTrainingExecutionRepository.teamKeyOf(s.equipe)
                    TrainingExecLocalStore.upsert(
                        applicationContext, teamKey, ym.toString(), s.trainingName,
                        ExecCacheEntry(s.dataConclusao, s.horaConclusao, duracaoEfetiva, TrainingExecSyncState.SYNCED)
                    )
                } catch (e: Exception) {
                    // Sem conexão limpa nem mesmo pra Placa de Erro. Volte amanhã.
                    hasFailures = true
                    continue
                }

                // O expurgo apaga o registro local
                safeDelete(s.localPhotoPath)
                safeDelete(s.localThumbPath)
                store.removeById(s.submissionId)
                continue
            }

            try {
                store.update(s.copy(syncStatus = "UPLOADING", lastError = null))

                val duracaoEfetiva = s.duracao.ifBlank { duracao }
                uploader.upload(s, collectionName, pastaFotos, duracaoEfetiva)

                val ym = trainingIsoDateFromId(s.trainingName)?.let { YearMonth.from(it) } ?: YearMonth.now()
                execRepo.markExecuted(
                    teamName = s.equipe,
                    ym = ym,
                    trainingId = s.trainingName,
                    dataConclusao = s.dataConclusao,
                    horaConclusao = s.horaConclusao,
                    duracao = duracaoEfetiva,
                    deviceModel = Build.MODEL
                )

                val teamKey = TeamTrainingExecutionRepository.teamKeyOf(s.equipe)
                TrainingExecLocalStore.upsert(
                    context = applicationContext,
                    teamKey = teamKey,
                    month = ym.toString(),
                    trainingId = s.trainingName,
                    entry = ExecCacheEntry(
                        dataConclusao = s.dataConclusao,
                        horaConclusao = s.horaConclusao,
                        duracao = duracaoEfetiva,
                        syncState = TrainingExecSyncState.SYNCED
                    )
                )
                safeDelete(s.localPhotoPath)
                safeDelete(s.localThumbPath)
                store.removeById(s.submissionId)
            } catch (e: DdsSubmissionWindowException) {
                // Pendência inválida definitivamente: evita retry infinito.
                store.removeById(s.submissionId)
            } catch (e: Exception) {
                // Mantém na fila, incrementa falha e DEIXA a fila andar pro próximo relatório!
                store.update(s.copy(syncStatus = "ERROR", lastError = e.message, retryCount = s.retryCount + 1))
                hasFailures = true
            }
        }
        
        // Se algum dos documentos falhou, manda o Trabalhador acordar mais tarde via Backoff,
        // mas garante que os sucessos parciais do meio do caminho foram comemorados!
        return if (hasFailures) Result.retry() else Result.success()
    }

    private fun safeDelete(path: String?) {
        if (path.isNullOrBlank()) return
        runCatching {
            val f = File(path)
            if (f.exists()) f.delete()
        }
    }

    private fun createFallbackImage(context: Context): File {
        val bitmap = android.graphics.Bitmap.createBitmap(800, 600, android.graphics.Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(bitmap)
        canvas.drawColor(android.graphics.Color.DKGRAY)
        
        val paint = android.graphics.Paint().apply {
            color = android.graphics.Color.WHITE
            textSize = 50f
            textAlign = android.graphics.Paint.Align.CENTER
            isAntiAlias = true
        }
        
        canvas.drawText("FOTO CORROMPIDA", 400f, 280f, paint)
        canvas.drawText("OU INACESSÍVEL", 400f, 350f, paint)
        
        val f = File(context.cacheDir, "fallback_${System.currentTimeMillis()}.jpg")
        f.outputStream().use { 
            bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, it)
        }
        return f
    }

    private fun cleanupOrphanedFiles(context: Context, pendentes: List<com.chicoeletro.dds.data.FormSubmission>) {
        val activePaths = pendentes.flatMap { listOfNotNull(it.localPhotoPath, it.localThumbPath) }.toSet()
        // Considera órfão arquivos com mais de 2 horas de vida (7200000 ms) para evitar apagar fotos de um DDS que está sendo preenchido no momento
        val cutoffTime = System.currentTimeMillis() - 7200000

        // Limpa arquivos da filesDir (dds_, odo_)
        context.filesDir.listFiles()?.forEach { file ->
            val name = file.name
            if ((name.startsWith("dds_") || name.startsWith("odo_")) && file.lastModified() < cutoffTime) {
                if (!activePaths.contains(file.absolutePath)) {
                    runCatching { file.delete() }
                }
            }
        }

        // Limpa arquivos da cacheDir (thumb_, fallback_)
        context.cacheDir.listFiles()?.forEach { file ->
            val name = file.name
            if ((name.startsWith("thumb_") || name.startsWith("fallback_")) && file.lastModified() < cutoffTime) {
                if (!activePaths.contains(file.absolutePath)) {
                    runCatching { file.delete() }
                }
            }
        }
    }
}