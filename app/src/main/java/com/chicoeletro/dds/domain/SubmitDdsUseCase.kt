// Módulo: app/src/main/java/com/chicoeletro/dds/domain/SubmitDdsUseCase.kt
// Função: Caso de uso que orquestra o fluxo de submissão de um DDS. Valida dados, gerencia a 
//         fila offline e dispara o upload remoto via RemoteDdsUploader.
// Tecnologias: Clean Architecture, Kotlin Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.domain

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import androidx.core.net.toFile
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.data.local.PendingDdsStore
import com.chicoeletro.dds.ui.training.isWithinTrainingConclusionWindow
import com.chicoeletro.dds.sync.DdsSyncScheduler
import java.io.File

class SubmitDdsUseCase(
    private val context: Context,
    private val pendingStore: PendingDdsStore,

    private val scheduler: DdsSyncScheduler
) {
    suspend fun submitLocalFirst(
        submission: FormSubmission,
        fotoUri: Uri,
        thumbUri: Uri?,
        collectionName: String,
        pastaFotos: String,
        duracaoFormatada: String
    ): FormSubmission {
        validateSubmissionWindow(submission)

        // Converta o Uri de FileProvider em File real (armazenamento privado)
        // Se o Uri não for file://, usamos copy para filesDir
        val photoFile = uriToPrivateFile(fotoUri, "dds_${submission.submissionId}.jpg", context.filesDir)

        val thumbFile = thumbUri?.let {
            uriToPrivateFile(it, "thumb_${submission.submissionId}.jpg", context.cacheDir)
        }

        val enriched = submission.copy(
            localPhotoPath = photoFile.absolutePath,
            localThumbPath = thumbFile?.absolutePath,
            syncStatus = "PENDING",
            retryCount = 0,
            lastError = null
        )

        pendingStore.enqueue(enriched)
        scheduler.schedule()
        return enriched
    }
    private fun validateSubmissionWindow(submission: FormSubmission) {
        if (!isWithinTrainingConclusionWindow(submission.trainingName, submission.dataConclusao)) {
            throw DdsSubmissionWindowException(
                "O DDS ${submission.trainingName} está fora da janela permitida para conclusão."
            )
        }
    }

    private fun safeDelete(path: String?) {
        if (path.isNullOrBlank()) return
        runCatching {
            val f = File(path)
            if (f.exists()) f.delete()
        }
    }

    private fun uriToPrivateFile(uri: Uri, fileName: String, dir: File): File {
        // Se for um file://, pode converter direto
        return runCatching {
            val f = uri.toFile()
            if (f.exists()) f else throw IllegalStateException("file uri não existe")
        }.getOrElse {
            // copia do contentResolver para diretório privado
            val out = File(dir, fileName).apply { parentFile?.mkdirs() }
            context.contentResolver.openInputStream(uri).use { input ->
                requireNotNull(input) { "Não foi possível abrir inputStream do uri" }
                out.outputStream().use { input.copyTo(it) }
            }
            out
        }
    }

    private fun isOnline(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(net) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}