// Módulo: app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingSyncUiState.kt
// Descrição: Estado único exposto para UI durante sincronização.
//
// Criado: 14/01/2026

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