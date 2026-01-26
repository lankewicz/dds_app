// Módulo: app/src/main/java/com/example/dds/data/TrainingRepository.kt
// Função: Interface que define de onde vem a lista de treinamentos.
// Histórico de Alterações:
//   - 07/06/2025: Criada para abstrair diferentes fontes de dados (JSON no Storage, Firestore, API).

package com.chicoeletro.dds.data

/**
 * Interface que representa um provedor de treinamentos.
 * Pode buscar JSON no Storage, Firestore, API REST, etc.
 */
interface TrainingRepository {
    /**
     * Busca a lista atual de treinamentos e devolve como List<Training>.
     */
    suspend fun fetchTrainings(): List<Training>
}
