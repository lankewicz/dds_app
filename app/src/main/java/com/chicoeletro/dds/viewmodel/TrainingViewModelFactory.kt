// Módulo: app/src/main/java/com/example/dds/viewmodel/TrainingViewModelFactory.kt
// Atualização: 22/06/2025 — injetando StorageTrainingRepository para preloadAssets.
// Função: Factory para criar instâncias de TrainingViewModel com dependências configuradas.

package com.chicoeletro.dds.viewmodel

import android.app.Application
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.chicoeletro.dds.data.StorageTrainingRepository

class TrainingViewModelFactory(
    private val application: Application
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(TrainingViewModel::class.java)) {
            val repo = StorageTrainingRepository(application)
            return TrainingViewModel(application, repo) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
    }
}
