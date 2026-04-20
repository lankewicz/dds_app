// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/OnlineConclusionModels.kt
// Função: Modelos de dados para o processo de conclusão do DDS Online. Define a estrutura para 
//         registros de presença e submissões das reuniões virtuais.
// Tecnologias: Kotlin Data Classes.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.online

/**
 * Modelo de dados para o formulário de conclusão do DDS Online.
 */
data class OnlineConclusionForm(
    val displayName: String,
    val teamName: String?,
    val role: String,
    val sessionId: String,
    val presentationTitle: String?,
    val notes: String?,
    val confirmPresence: Boolean,
    val confirmPhoto: Boolean,
    val deviceInfo: String
)
