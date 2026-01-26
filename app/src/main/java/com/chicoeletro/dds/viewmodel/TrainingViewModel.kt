// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingViewModel.kt
// Descrição: ViewModel responsável por carregar lista de treinamentos (offline-first com fallback online).
// Autor: Valdinei Lankewicz
// Atualizado: 07/11/2025
//
// Histórico de alterações:
//   - 20/06/2025: Inicial
//   - 30/06/2025: Removido suporte offline; funcionamento totalmente online.
//   - 30/06/2025: Adicionado campo listaCompleta para acelerar carregamento via lista.json.
//   - 07/11/2025: OFFLINE-FIRST com fallback online; usa LocalTrainingIndex antes do repositório.

package com.chicoeletro.dds.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.data.StorageTrainingRepository
import com.chicoeletro.dds.data.Training
import com.chicoeletro.dds.storage.LocalTrainingIndex
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

        // 1) Índice local (já sincronizado na abertura do app)
        val locais = LocalTrainingIndex.list(getApplication())
        if (locais.isNotEmpty()) {
            _trainings.value = locais
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
