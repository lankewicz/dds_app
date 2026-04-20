// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingViewModelFactory.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

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