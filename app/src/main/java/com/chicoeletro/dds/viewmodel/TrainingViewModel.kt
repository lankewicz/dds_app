// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingViewModel.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.data.StorageTrainingRepository
import com.chicoeletro.dds.data.Training
import com.chicoeletro.dds.storage.LocalTrainingIndex
import com.chicoeletro.dds.util.NetworkStatusObserver
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TrainingViewModel(
    application: Application,
    private val repository: StorageTrainingRepository
) : AndroidViewModel(application) {

    private val _isInitializing = MutableStateFlow(true)
    val isInitializing: StateFlow<Boolean> = _isInitializing.asStateFlow()

    private val _trainings = MutableStateFlow<List<Training>>(emptyList())
    val trainings: StateFlow<List<Training>> = _trainings.asStateFlow()

    companion object {
        // Lista de caminhos completos dos arquivos do lista.json (imagens) — mantida por compatibilidade
        var listaCompleta: List<String>? = null
    }

    init {
        refreshTrainings()
    }

    /**
     * OFFLINE-FIRST:
     * 1) Tenta listar a partir do conteúdo local (filesDir/trainings/<id>).
     * 2) Se vazio, faz fallback online via Storage para obter a lista mais recente.
     */
    fun refreshTrainings() = viewModelScope.launch {
        _isInitializing.value = true

        val isOnlineNow = NetworkStatusObserver.isOnlineNow(getApplication<Application>().applicationContext)


        // 1) Índice local (já sincronizado na abertura do app)
        val locais = LocalTrainingIndex.list(getApplication())
        if (locais.isNotEmpty()) {
            _trainings.value = locais
            _isInitializing.value = false
            return@launch
        }

        // 1.5) OFFLINE + sem cache local → não tenta Storage (evita "travamento" / timeout)
        if (!isOnlineNow) {
            Log.w("TrainingVM", "OFFLINE e sem cache local. Ignorando fallback online.")
            _trainings.value = emptyList()
            _isInitializing.value = false
            return@launch
        }


        // 2) Fallback online: usa fetchTrainingsComArquivos()
        try {
            val (lista, arquivos) = repository.fetchTrainingsComArquivos()
            listaCompleta = arquivos
            _trainings.value = lista
        } catch (e: Exception) {
            Log.e("TrainingVM", "Erro ao atualizar lista (fallback online)", e)
            _trainings.value = emptyList()
        }

        _isInitializing.value = false
    }
}