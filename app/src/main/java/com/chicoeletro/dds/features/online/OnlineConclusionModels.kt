package com.chicoeletro.dds.features.online

/**
 * Dados do Form de Conclusão do DDS Online.
 *
 * OBS: tempo oficial por usuário será preenchido na próxima etapa
 * (lendo Firestore + regra grace/teto). Por enquanto, este form salva:
 * - identificação
 * - confirmação (foto)
 * - declaração do usuário
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
    val deviceInfo: String? = null,
)