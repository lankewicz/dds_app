// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/TurnoReminderWorker.kt
// Função: Cobrança periódica do intervalo após seis horas contínuas de turno aberto.
// Tecnologias: WorkManager (PeriodicWork), Java Time API, TurnoController.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.chicoeletro.dds.core.LastTeamStore
import com.chicoeletro.dds.features.turno.EstadoTurno
import com.chicoeletro.dds.features.turno.TurnoController
import kotlinx.coroutines.flow.firstOrNull

class TurnoReminderWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val teamData = LastTeamStore.carregar(applicationContext).firstOrNull() ?: return Result.success()
        val teamName = teamData.equipe
        if (teamName.isBlank()) return Result.success()

        // O estado local é alimentado pelo status obtido automaticamente do ROTALOG.
        val turnoController = TurnoController(applicationContext, teamName)
        val snap = turnoController.current()
        if (snap.estado == EstadoTurno.ABERTO && snap.lastEventAtClientMs > 0L) {
            val elapsedHours = (System.currentTimeMillis() - snap.lastEventAtClientMs)
                .coerceAtLeast(0L) / (1000 * 60 * 60)
            if (elapsedHours >= NotificationConfig.SHIFT_ABERTO_MAX_HOURS) {
                NotificationHelper.showTurnoNotification(
                    applicationContext,
                    "Intervalo de Repouso",
                    "O turno está aberto há ${elapsedHours}h. Realize o intervalo obrigatório."
                )
            }
        }

        return Result.success()
    }
}
