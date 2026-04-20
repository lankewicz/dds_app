// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/EstadoTurno.kt
// Função: Modelo de dados para o estado do turno de trabalho. Controla horários de abertura, 
//         fechamento e indicadores de tempo decorrido.
// Tecnologias: Kotlin Data Classes.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

enum class EstadoTurno {
    FECHADO,
    ABERTO,
    INTERVALO,
    DESLOCAMENTO_ESPECIAL
}

enum class MotivoDeslocamentoEspecial {
    ABASTECIMENTO,
    BORRACHARIA,
    OFICINA_AUTO_ELETRICA,
    ADMINISTRATIVO_PATO_BRANCO,
    VIAGEM_COPEL,
    OUTRO
}

data class TurnoSnapshot(
    // Sessão (turno determinístico)
    val turnoId: String? = null,                 // {EMPRESA}_{EQUIPE}_{openAtClientMs}
    val isOpen: Boolean = false,
    val openedAtClientMs: Long? = null,          // usado no turnoId (offline-first)
    val membersSnapshot: List<String> = emptyList(), // eletricistas (congelado no ABRIR)

    // Controle anti-regressão / auditoria rápida
    val clientUpdatedAtMs: Long = 0L,
    val lastEventId: String? = null,
    val lastEventAtClientMs: Long = 0L,

    // Estado operacional
    val estado: EstadoTurno = EstadoTurno.FECHADO,
    val lastChangedAtIso: String? = null,

    // NOC/SS (opcional, só faz sentido quando ABERTO)
    val nocSs: String? = null,

    // Início do turno (marcado quando entra em ABERTO pela primeira vez nesta sessão)
    val kmInicioTotalAbs: Long? = null,      // quando disponível (OCR ou digitado total)
    val kmInicioLast3: Int? = null,          // sempre (0..999)
    val inicioTurnoAtIso: String? = null,

    // Odometria (sempre somando)
    val kmTotalAbs: Long? = null,            // última leitura total conhecida
    val kmLast3: Int? = null,                // última leitura last3 conhecida (0..999)
    val kmDeltaTurno: Int = 0,               // acumulado do turno (sempre soma deltas)

    // Política de foto / auditoria
    val odometroVerificado: Boolean = false, // marca que a 1ª leitura válida do odômetro já foi feita
    val ultimosKmLast3: List<Int> = emptyList(), // manter 4 últimos last3 distintos
    val eventosKmCounter: Int = 0,            // 20% determinístico (1/5)

    // Foto do painel: guarda o "totalAbs" quando a última foto foi registrada (preferido)
    val lastFotoTotalAbs: Long? = null,

    // Último deslocamento especial registrado (ao ENTRAR em DESLOCAMENTO_ESPECIAL)
    val lastMotivo: MotivoDeslocamentoEspecial? = null,
    val lastMotivoOutro: String? = null,

    // Controle de Interjornada (Art 66 e 67)
    val lastClosedAtMs: Long? = null,
    val lastWasDescansoSemanal: Boolean = false
)

data class PlanoTransicao(
    val from: EstadoTurno,
    val to: EstadoTurno,
    val pedeKm: Boolean,
    val pedeFoto: Boolean,
    val primeiraExecucao: Boolean,
    val pedeMotivo: Boolean
)

data class RequisicaoTransicao(
    val to: EstadoTurno,
    val kmTotalAbs: Long? = null, // 0..9_999_999 (ou maior se quiser)
    val kmLast3: Int? = null,     // 0..999 (inclui 000)
    val motivo: MotivoDeslocamentoEspecial? = null,
    val motivoOutro: String? = null,
    val isDescansoSemanal: Boolean = false
)