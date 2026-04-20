// Módulo: app/src/main/java/com/chicoeletro/dds/data/TrainingRepository.kt
// Função: Interface de abstração para o fornecimento de dados de treinamento. Padroniza o acesso 
//         independente da fonte de dados (Firestore, Storage ou Local).
// Tecnologias: Kotlin Interface.
// Autor: Valdinei Lankewicz
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