// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/DdsReminderWorker.kt
// Função: Worker para verificação e disparo de lembretes de DDS. Valida se o treinamento do 
//         dia foi realizado e respeita regras de silêncio (ex: Domingos).
// Tecnologias: WorkManager (CoroutineWorker), DataStore, Java Time API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.chicoeletro.dds.core.LastTeamStore
import com.chicoeletro.dds.features.turno.TurnoController
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import kotlinx.coroutines.flow.firstOrNull
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

class DdsReminderWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val now = LocalDateTime.now(ZoneId.of("America/Sao_Paulo"))
        
        // Silêncio absoluto aos Domingos
        if (now.dayOfWeek == java.time.DayOfWeek.SUNDAY) {
            return Result.success()
        }

        val teamData = LastTeamStore.carregar(applicationContext).firstOrNull() ?: return Result.success()
        val teamName = teamData.equipe
        if (teamName.isBlank()) return Result.success()

        val today = now.format(DateTimeFormatter.ISO_LOCAL_DATE)
        val teamKey = "team_${teamName.lowercase().trim()}"
        val monthId = today.substring(0, 7)

        val localRecords = TrainingExecLocalStore.flowMonth(applicationContext, teamKey, monthId).firstOrNull() ?: emptyMap()
        val alreadyDone = localRecords.values.any { it.dataConclusao == today }
        
        if (!alreadyDone) {
            val turnoController = TurnoController(applicationContext, teamName)
            val snap = turnoController.current()
            NotificationHelper.showDdsNotification(applicationContext, snap.estado.name)
        }

        return Result.success()
    }
}