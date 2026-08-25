// Módulo: app/src/main/java/com/chicoeletro/dds/features/viewer/BlockReason.kt
// Função: Define os motivos para o bloqueio de visualização de treinamentos. Gerencia mensagens 
//         explicativas sobre pendências de DDS ou status impeditivo de turno.
// Tecnologias: Kotlin Sealed Classes / Enums.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.viewer

/**
 * Motivos para o bloqueio de navegação no visualizador de DDS.
 */
enum class BlockReason {
    NOT_STARTED,
    ORDER_ENFORCED,
    MIN_DWELL_FIRST_SLIDE,
    MIN_DWELL_OTHER_SLIDE
}

fun BlockReason.message(remainSeconds: Long): String {
    // remainSeconds já deve vir arredondado para cima.
    val s = remainSeconds.coerceAtLeast(0)
    return when (this) {
        BlockReason.NOT_STARTED ->
            "Início necessário: toque em INICIAR para começar o DDS e registrar o tempo de participação."

        BlockReason.ORDER_ENFORCED ->
            "Navegação orientada: visite os slides na ordem para evitar perda de informações de segurança."

        BlockReason.MIN_DWELL_FIRST_SLIDE ->
            "⏳ Aguarde mais ${s}s de leitura neste 1º slide para liberar o próximo."

        BlockReason.MIN_DWELL_OTHER_SLIDE ->
            "⏳ Aguarde mais ${s}s de leitura neste slide para liberar o próximo."
    }
}