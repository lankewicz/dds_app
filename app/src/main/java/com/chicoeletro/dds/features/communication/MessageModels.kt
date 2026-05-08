// Módulo: app/src/main/java/com/chicoeletro/dds/features/communication/MessageModels.kt
// Função: Modelos de dados para o sistema de comunicação entre equipes e setores.

package com.chicoeletro.dds.features.communication

import com.google.firebase.firestore.ServerTimestamp
import java.util.Date

data class TeamMessage(
    val id: String = "",
    val threadId: String = "", // Agrupador de mensagens da mesma conversa
    val fromEquipe: String = "",
    val toSetor: String = "", // OFICINA, ALMOXARIFADO, ROTALOG
    val toEquipe: String = "", // Para mensagens diretas a uma equipe específica
    val subject: String = "", // Assunto da conversa (setado na primeira mensagem)
    val content: String = "",
    @ServerTimestamp
    val timestamp: Date? = null,
    val status: String = "NÃO LIDO" // "NÃO LIDO", "LIDO", "CONCLUIDA"
)

object CommunicationSetors {
    const val OFICINA = "OFICINA"
    const val ALMOXARIFADO = "ALMOXARIFADO"
    const val ROTALOG = "ROTALOG"
    const val PONTO = "PONTO"
}
