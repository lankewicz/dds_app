package com.chicoeletro.dds.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

class DdsSyncScheduler(
    private val context: Context,
    private val collectionName: String,
    private val pastaFotos: String
) {
    fun schedule() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val input = Data.Builder()
            .putString("collectionName", collectionName)
            .putString("pastaFotos", pastaFotos)
            .build()

        val req = OneTimeWorkRequestBuilder<DdsSyncWorker>()
            .setConstraints(constraints)
            .setInputData(input)
            .build()

        WorkManager.getInstance(context)
            .enqueueUniqueWork("dds_sync_pending", ExistingWorkPolicy.KEEP, req)
    }
}
