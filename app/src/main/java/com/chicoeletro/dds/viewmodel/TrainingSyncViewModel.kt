// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingSyncViewModel.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.data.sync.FileLocalDataSource
import com.chicoeletro.dds.data.sync.FirebaseRemoteDataSource
import com.chicoeletro.dds.data.sync.UpdateTrainingsUseCase
import com.chicoeletro.dds.util.NetworkStatusObserver
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

class TrainingSyncViewModel(application: Application) : AndroidViewModel(application) {
    private val TAG = "TrainingSyncVM"

    private val _state = MutableStateFlow(TrainingSyncUiState())
    val state: StateFlow<TrainingSyncUiState> = _state.asStateFlow()

    // ✅ Mensagens one-shot para UI (Toast/Snackbar)
    private val _uiMessages = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val uiMessages = _uiMessages.asSharedFlow()


    /**
    * UI pode coletar e chamar trainingViewModel.refreshTrainings()
    * (mantém separação: sync VM não depende do TrainingViewModel)
    */
    private val _refreshRequests = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val refreshRequests = _refreshRequests.asSharedFlow()

    private val didAutoSync = AtomicBoolean(false)
    private val didStartupSync = AtomicBoolean(false)
    private val running = AtomicBoolean(false)

    // tracking interno para “restantes”
    private val pendingIds = linkedSetOf<String>()
    private val finishedIds = linkedSetOf<String>()

    /**
     * Sync automática no startup.
     * - roda no máximo 1x por processo (VM vive no processo)
     * - se rodar aqui, impede autoSync duplicada no Compose quando online mudar
     */

    fun startupSyncIfNeeded(online: Boolean) {
        if (!online) return
        // Se já rodou startup sync, não roda auto-sync novamente
        if (didStartupSync.get()) return
        if (didStartupSync.compareAndSet(false, true)) {
            // evita segunda execução automática via autoSyncIfNeeded()
            didAutoSync.set(true)
            syncNow()
        }
    }


    fun autoSyncIfNeeded(online: Boolean) {
        if (!online) return
        if (didAutoSync.compareAndSet(false, true)) {
            syncNow()
        }
    }

    fun syncNow() {
        val ctx = getApplication<Application>().applicationContext

        // ✅ Gate definitivo: nunca inicia sync quando offline (evita "travamento" por timeout)
        if (!NetworkStatusObserver.isOnlineNow(ctx)) {
            // garante que UI não fica presa em "syncing" por alguma corrida anterior
            _state.update { it.copy(isSyncing = false, currentId = null) }
            _uiMessages.tryEmit("OFFLINE — conecte-se à internet para sincronizar.")
            return
        }

        if (!running.compareAndSet(false, true)) return

        // reset tracking
        pendingIds.clear()
        finishedIds.clear()
        _state.value = TrainingSyncUiState(isSyncing = true)

        viewModelScope.launch(Dispatchers.IO) {

            try {
                val remote = FirebaseRemoteDataSource(
                    FirebaseFirestore.getInstance(),
                    FirebaseStorage.getInstance(),
                    ctx
                )
                val local = FileLocalDataSource(ctx)
                val useCase = UpdateTrainingsUseCase(remote, local)

                runCatching {
                    // ✅ Timeout global do sync para evitar “preso” em rede ruim.
                    // Ajuste conforme sua realidade: 60–180s costuma ser bom.
                    withTimeout(120_000L) {
                        useCase.executeWithProgress(
                            onOverallPrepare = { trainingsToDownload, _, _, overallToDownload ->
                                _state.update {
                                    it.copy(
                                        isSyncing = true,
                                        overallDone = 0,
                                        overallTotal = overallToDownload,
                                        plannedTrainingsTotal = 0,
                                        pendingTrainings = 0,
                                        finishedTrainings = 0,
                                        remainingTrainings = 0,
                                        currentId = null,
                                        currentDone = 0,
                                        currentTotal = 0
                                    )
                                }
                            },
                            onOverallProgress = { done, total ->
                                _state.update { it.copy(overallDone = done, overallTotal = total) }
                            },
                            onTrainingStart = { id, _, expected, existing ->
                                val hasPending = expected > existing
                                if (hasPending) pendingIds.add(id)

                                _state.update {
                                    it.copy(
                                        currentId = id,
                                        currentTotal = expected,
                                        currentDone = existing.coerceAtMost(expected),
                                        // ✅ Contagem real de treinamentos baixando = quantos têm pendência
                                        plannedTrainingsTotal = pendingIds.size,
                                        pendingTrainings = pendingIds.size,
                                        remainingTrainings = (pendingIds.size - finishedIds.size).coerceAtLeast(
                                            0
                                        )

                                    )
                                }
                            },
                            onTrainingProgress = { id, done, expected, oDone, oTotal ->
                                if (expected > 0 && done >= expected) finishedIds.add(id)
                                _state.update {
                                    it.copy(
                                        currentId = id,
                                        currentDone = done,
                                        currentTotal = expected,
                                        overallDone = oDone,
                                        overallTotal = oTotal,
                                        finishedTrainings = finishedIds.size,
                                        pendingTrainings = pendingIds.size,
                                        remainingTrainings = (pendingIds.size - finishedIds.size).coerceAtLeast(
                                            0
                                        )
                                    )
                                }
                            }
                        )
                    }

                    useCase.cleanupAllOrphans(
                        onTrainingCleanup = { _, _ -> /* opcional */ },
                        dryRun = false
                    )
                }.onSuccess {
                    _refreshRequests.tryEmit(Unit)
                }.onFailure { e: Throwable ->
                    if (e is TimeoutCancellationException) {
                        Log.w(TAG, "Sync cancelado por timeout (conexão lenta/instável).", e)
                        _uiMessages.tryEmit("Falha na sincronização: ${e.message ?: "erro desconhecido"}")
                    } else {
                        Log.w(TAG, "Sync falhou: ${e.message}", e)
                    }
                   }
            } finally {
                _state.update { it.copy(isSyncing = false, currentId = null) }
                running.set(false)
            }
        }
    }
}