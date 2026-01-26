package com.chicoeletro.dds.features.viewer
/**
* Motivos padronizados de bloqueio e mensagens institucionais.
*
* Nota: as mensagens retornam texto pronto para UI (barra de status).
* Caso queira internacionalizar no futuro, substitua por resource strings.
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
            "Atenção necessária: este primeiro slide traz informações essenciais de segurança. " +
            "Aguarde ${s}s para garantir a leitura completa antes de avançar."

        BlockReason.MIN_DWELL_OTHER_SLIDE ->
            "Conteúdo de segurança: este slide orienta a execução segura das atividades. " +
            "Aguarde ${s}s para avançar e evitar falhas por leitura apressada."
    }
}