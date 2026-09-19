package com.chicoeletro.dds.features.training

import android.content.Context
import com.chicoeletro.dds.storage.ExecCacheEntry
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.storage.TrainingExecSyncState
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Sincroniza a torre mensal no máximo uma vez por dia para cada equipe/mês. */
object TrainingExecutionDailySync {
    private val mutex = Mutex()
    private val zoneId = ZoneId.of("America/Sao_Paulo")

    suspend fun syncIfNeeded(
        context: Context,
        teamName: String,
        month: YearMonth,
        repository: TeamTrainingExecutionRepository = TeamTrainingExecutionRepository()
    ): Boolean {
        val appContext = context.applicationContext
        val teamKey = TeamTrainingExecutionRepository.teamKeyOf(teamName)
        val monthId = month.toString()
        val today = LocalDate.now(zoneId).toString()

        if (TrainingExecLocalStore.wasRemoteSyncedOn(appContext, teamKey, monthId, today)) {
            return false
        }

        return mutex.withLock {
            if (TrainingExecLocalStore.wasRemoteSyncedOn(appContext, teamKey, monthId, today)) {
                return@withLock false
            }

            val remote = repository.getExecutedTrainingsForMonth(teamName, month)
            val cache = remote.mapValues { (_, item) ->
                ExecCacheEntry(
                    dataConclusao = item.dataConclusao,
                    horaConclusao = item.horaConclusao,
                    duracao = item.duracao,
                    syncState = TrainingExecSyncState.SYNCED
                )
            }
            TrainingExecLocalStore.replaceRemoteMonthPreservingPending(
                context = appContext,
                teamKey = teamKey,
                month = monthId,
                remoteMap = cache,
                syncedOn = today
            )
            true
        }
    }
}
