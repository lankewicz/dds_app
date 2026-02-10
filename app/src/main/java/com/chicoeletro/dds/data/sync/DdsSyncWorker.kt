package com.chicoeletro.dds.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.chicoeletro.dds.data.local.PendingDdsStore
import com.chicoeletro.dds.domain.RemoteDdsUploader
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import java.io.File

class DdsSyncWorker(
    ctx: Context,
    params: WorkerParameters
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val store = PendingDdsStore(applicationContext)
        val uploader = RemoteDdsUploader(FirebaseStorage.getInstance(), FirebaseFirestore.getInstance())

        val collectionName = inputData.getString("collectionName") ?: "DDS"
        val pastaFotos = inputData.getString("pastaFotos") ?: "DDS_Fotos"
        val duracao = inputData.getString("duracaoDefault") ?: "" // opcional

        val pendentes = store.listPending()
        if (pendentes.isEmpty()) return Result.success()

        for (s in pendentes) {
            try {
                uploader.upload(s, collectionName, pastaFotos, duracao)
                safeDelete(s.localPhotoPath)
                safeDelete(s.localThumbPath)
                store.removeById(s.submissionId)
            } catch (e: Exception) {
                // mantém na fila para retry
                store.update(s.copy(syncStatus = "ERROR", lastError = e.message, retryCount = s.retryCount + 1))
                return Result.retry()
            }
        }
        return Result.success()
    }

    private fun safeDelete(path: String?) {
        if (path.isNullOrBlank()) return
        runCatching {
            val f = File(path)
            if (f.exists()) f.delete()
        }
    }
}
