// Módulo: app/src/main/java/com/chicoeletro/dds/components/FooterStatus.kt
// Função: Definições de modelos de dados (Data Class e Enum) para as mensagens informativo-visuais 
//         exibidas no rodapé do sistema.
// Tecnologias: Kotlin Data Classes, Enums.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.components

enum class FooterStatusKind {
    NORMAL,
    WARNING,
    SUCCESS
}

data class FooterStatus(
    val text: String,
    val kind: FooterStatusKind = FooterStatusKind.NORMAL
)