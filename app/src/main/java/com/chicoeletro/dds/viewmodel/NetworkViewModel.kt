// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/NetworkViewModel.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.viewmodel

import android.app.Application
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.util.NetworkStatusObserver
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Módulo: app/src/main/java/com/example/dds/viewmodel/NetworkViewModel.kt
 * Descrição: ViewModel que expõe um StateFlow<Boolean> que indica online/offline.
 * Autor: Valdinei Lankewicz
 * Data de Criação: 02/06/2025
 */
@HiltViewModel
class NetworkViewModel @Inject constructor(application: Application) : ViewModel() {

    private val _isOnline = MutableStateFlow(true)
    val isOnline: StateFlow<Boolean> = _isOnline

    private val observer = NetworkStatusObserver(application.applicationContext)

    init {
        viewModelScope.launch {
            observer.observe().collectLatest { status ->
                _isOnline.value = status
            }
        }
    }
}