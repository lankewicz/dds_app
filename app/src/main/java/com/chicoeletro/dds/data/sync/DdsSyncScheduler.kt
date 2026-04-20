// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/DdsSyncScheduler.kt
// Função: Agendador de tarefas de sincronização. Configura e dispara o DdsSyncWorker utilizando 
//         o WorkManager com restrições de conectividade.
// Tecnologias: WorkManager, Constraints API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 08/06/2025: Criação inicial.

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