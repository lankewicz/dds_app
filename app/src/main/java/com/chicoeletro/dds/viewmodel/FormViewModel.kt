// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/FormViewModel.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/06/2025: Implementação inicial de FormViewModel para gerenciar FormScreen.
//   - 10/06/2025: Removida toda declaração de TrainingViewModel para eliminar duplicação.

package com.chicoeletro.dds.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.storage.FormDataStore
import kotlinx.coroutines.launch

class FormViewModel(application: Application) : AndroidViewModel(application) {

    /**
     * 04/06/2025: Salva a submissão no DataStore local.
     */
    fun saveSubmission(submission: FormSubmission) {
        viewModelScope.launch {
            FormDataStore.saveSubmission(getApplication(), submission)
        }
    }
}