// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingSyncUiState.kt
// Função: ViewModels para gerenciamento de estado e fluxo de dados para a UI.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.viewmodel

data class TrainingSyncUiState(
    val isSyncing: Boolean = false,

    // progresso global
    val overallDone: Int = 0,
    val overallTotal: Int = 0,

    // progresso do treinamento atual (pasta)
    val currentId: String? = null,
    val currentDone: Int = 0,
    val currentTotal: Int = 0,

    // contadores para UI
    val plannedTrainingsTotal: Int = 0,
    val pendingTrainings: Int = 0,
    val finishedTrainings: Int = 0,
    val remainingTrainings: Int = 0
)