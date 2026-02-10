// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoStatusModels.kt
// Caminho completo: [PROJECT_ROOT]/app/src/main/java/com/chicoeletro/dds/features/turno/TurnoStatusModels.kt
// Descrição: Modelos de dados do Status do Turno (offline-first):
//            1) Estado local atual por equipe;
//            2) Entrada de log (histórico) para auditoria e rastreio.
// Autor: Valdinei Lankewicz
// Criado em: 04/02/2026
// Histórico de alterações:
//   - 04/02/2026: Versão inicial.

package com.chicoeletro.dds.features.turno

/**
 * Fonte única de verdade dos modelos do Turno.
 * Evita duplicação entre UI / Sync / LocalStore.
 */
enum class TurnoStatus {
    FECHADO,
    INTERVALO,
    ABERTO,
    DESLOCAMENTO_ESPECIAL
}

data class TurnoStatusLocal(
    val equipe: String,
    val eletricistas: List<String>,
    val status: TurnoStatus,

    // timestamp do STATUS (não do SS/NOC)
    val changedAtIso: String,
    val changedAtUi: String,

    val pendingSync: Boolean,

    // extras
    val deslocamentoMotivo: String? = null,

    // SS/NOC pode ser alterado mesmo sem trocar status
    val ssNoc: String? = null,
    val ssNocChangedAtIso: String? = null,
    val ssNocChangedAtUi: String? = null
)

data class TurnoStatusLogEntry(
    val equipe: String,
    val eletricistas: List<String>,
    val statusAnterior: TurnoStatus?,
    val statusNovo: TurnoStatus,

    // timestamp do EVENTO (log)
    val changedAtClientIso: String,

    val deslocamentoMotivo: String? = null,
    val ssNoc: String? = null,
    val ssNocChangedAtClientIso: String? = null
)