package com.chicoeletro.dds.domain

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import androidx.core.net.toFile
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.data.local.PendingDdsStore
import com.chicoeletro.dds.sync.DdsSyncScheduler
import java.io.File

class SubmitDdsUseCase(
    private val context: Context,
    private val pendingStore: PendingDdsStore,
    private val remote: RemoteDdsUploader,
    private val scheduler: DdsSyncScheduler
) {
    suspend fun submit(
        submission: FormSubmission,
        fotoUri: Uri,
        thumbUri: Uri?,
        collectionName: String,
        pastaFotos: String,
        duracaoFormatada: String
    ): SubmitResult {
        // Converta o Uri de FileProvider em File real (armazenamento privado)
        // Se o Uri não for file://, usamos copy para filesDir
        val photoFile = uriToPrivateFile(fotoUri, "dds_${submission.submissionId}.jpg", context.filesDir)

        val thumbFile = thumbUri?.let {
            uriToPrivateFile(it, "thumb_${submission.submissionId}.jpg", context.cacheDir)
        }

        val enriched = submission.copy(
            localPhotoPath = photoFile.absolutePath,
            localThumbPath = thumbFile?.absolutePath,
            syncStatus = "PENDING"
        )

        return if (isOnline(context)) {
            // tenta online
            runCatching {
                remote.upload(enriched, collectionName, pastaFotos, duracaoFormatada)
                // se OK: limpa local
                safeDelete(enriched.localPhotoPath)
                safeDelete(enriched.localThumbPath)
                SubmitResult.SentOnline
            }.getOrElse {
                // falhou (mesmo online): cai para fila offline
                pendingStore.enqueue(enriched.copy(syncStatus = "ERROR", lastError = it.message))
                scheduler.schedule()
                SubmitResult.SavedOffline
            }
        } else {
            // offline: enfileira e agenda sync
            pendingStore.enqueue(enriched)
            scheduler.schedule()
            SubmitResult.SavedOffline
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

sealed class SubmitResult {
    data object SentOnline : SubmitResult()
    data object SavedOffline : SubmitResult()
}
