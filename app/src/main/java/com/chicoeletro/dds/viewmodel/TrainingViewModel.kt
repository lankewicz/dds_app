// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingViewModel.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.data.StorageTrainingRepository
import com.chicoeletro.dds.data.Training
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.storage.ExecCacheEntry
import com.chicoeletro.dds.storage.LocalTrainingIndex
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.storage.TrainingExecSyncState
import com.chicoeletro.dds.util.NetworkStatusObserver
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.YearMonth

data class TrainingStatus(
    val dataConclusao: String,
    val horaConclusao: String,
    val duracao: String,
    val syncState: String = TrainingExecSyncState.SYNCED
)

@HiltViewModel
class TrainingViewModel @Inject constructor(
    private val application: Application,
    private val repository: StorageTrainingRepository
) : ViewModel() {

    private val _isInitializing = MutableStateFlow(true)
    val isInitializing: StateFlow<Boolean> = _isInitializing.asStateFlow()

    private val _trainings = MutableStateFlow<List<Training>>(emptyList())
    val trainings: StateFlow<List<Training>> = _trainings.asStateFlow()

    private val _trainingStatus = MutableStateFlow<Map<String, TrainingStatus>>(emptyMap())
    val trainingStatus: StateFlow<Map<String, TrainingStatus>> = _trainingStatus.asStateFlow()

    private val execRepo = TeamTrainingExecutionRepository()

    companion object {
        var listaCompleta: List<String>? = null
    }

    init {
        refreshTrainings()
    }

    fun updateTeamAndMonth(equipe: String, month: YearMonth) {
        if (equipe.isBlank()) {
            _trainingStatus.value = emptyMap()
            return
        }

        val teamKey = TeamTrainingExecutionRepository.teamKeyOf(equipe)
        val monthId = month.toString()

        viewModelScope.launch {
            TrainingExecLocalStore
                .flowMonth(application, teamKey, monthId)
                .collect { localMap ->
                    _trainingStatus.value = localMap.mapValues { (_, st) ->
                        TrainingStatus(st.dataConclusao, st.horaConclusao, st.duracao, st.syncState)
                    }
                }
        }

        // Remote listener
        viewModelScope.launch {
             execRepo.listenMonth(
                teamName = equipe,
                ym = month,
                onUpdate = { map ->
                    val cache = map.mapValues { (_, st) ->
                        ExecCacheEntry(
                            st.dataConclusao,
                            st.horaConclusao,
                            st.duracao,
                            TrainingExecSyncState.SYNCED
                        )
                    }
                    viewModelScope.launch {
                        TrainingExecLocalStore.mergeRemoteMonth(application, teamKey, monthId, cache)
                    }
                }
            )
        }
    }

    fun refreshTrainings() = viewModelScope.launch {
        _isInitializing.value = true
        val isOnlineNow = NetworkStatusObserver.isOnlineNow(application.applicationContext)

        val locais = LocalTrainingIndex.list(application, useCache = false)
        if (locais.isNotEmpty()) {
            _trainings.value = locais
            _isInitializing.value = false
            return@launch
        }

        if (!isOnlineNow) {
            _trainings.value = emptyList()
            _isInitializing.value = false
            return@launch
        }

        try {
            val (lista, arquivos) = repository.fetchTrainingsComArquivos()
            listaCompleta = arquivos
            _trainings.value = lista
        } catch (e: Exception) {
            Log.e("TrainingVM", "Erro ao atualizar lista", e)
            _trainings.value = emptyList()
        }
        _isInitializing.value = false
    }
}
