// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoRemoteModels.kt
// Função: Modelos de dados para representação remota de turnos. Define o formato dos 
//         documentos salvos no Firestore para compatibilidade com o histórico da nuvem.
// Tecnologias: Kotlin Data Classes.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

data class TurnoActor(
    val deviceId: String,
    val deviceModel: String,
    val appVersion: String
)

data class TurnoPhotoAudit(
    val required: Boolean,
    val photoId: String? = null,
    val storagePath: String? = null,
    val thumbPath: String? = null
)

/**
 * Evento imutável (append-only) vinculado a um turnoId.
 */
data class TurnoEventRemote(
    val empresa: String,
    val equipe: String,
    val turnoId: String,

    val eventId: String,

    // "quando aconteceu" (client) + string ISO para debug humano
    val occurredAtClientMs: Long,
    val clientCreatedAtIso: String,

    val from: String,
    val to: String,

    // OPÇÃO 1: KM total (quando disponível) + last3 (km4)
    val kmTotalAbs: Long? = null,

    // Início do turno (quando marcado no ABRIR)
    val kmInicioTotalAbs: Long? = null,

    val km4: Int? = null,
    val kmInicioTurno4: Int? = null,
    val kmDeltaTurno: Int? = null,

    val nocSs: String? = null,
    val motivo: String? = null,
    val motivoOutro: String? = null,

    // Auditoria forte (recomendado pelo menos em OPEN/CLOSE)
    val membersSnapshot: List<String>? = null,

    val photoAudit: TurnoPhotoAudit,
    val actor: TurnoActor
)

/**
 * Documento de monitoramento em tempo real (materialized view).
 * 1 doc por equipe, sempre apontando para o turno ativo (ou fechado).
 */
data class TurnoStateRemote(
    val empresa: String,
    val equipe: String,

    val turnoId: String? = null,
    val isOpen: Boolean = false,
    val membersSnapshot: List<String> = emptyList(),

    val openedAtClientMs: Long? = null,
    val closedAtClientMs: Long? = null,
    val closeReason: String? = null,

    val clientUpdatedAtMs: Long,
    val updatedAtIso: String,

    val lastEventId: String? = null,
    val lastEventAtClientMs: Long? = null,

    val estado: String,
    val nocSs: String? = null,

    // OPÇÃO 1: odometria persistida no current
    // - kmTotalAbs: última leitura total conhecida
    // - kmInicioTotalAbs: leitura total no início (se disponível)
    // - kmDeltaTurno: acumulado do turno (só faz sentido em ABERTO/FECHADO; opcional para monitor)
    val kmTotalAbs: Long? = null,
    val kmInicioTotalAbs: Long? = null,
    val kmDeltaTurno: Int? = null,

    val kmInicioTurno4: Int? = null,
    val inicioTurnoAtIso: String? = null,

    val odometroVerificado: Boolean,
    val ultimosKm4: List<Int>,
    val eventosKmCounter: Int,

    val lastMotivo: String? = null,
    val lastMotivoOutro: String? = null,

    val deviceIdLastWriter: String
)

/**
 * Sessão do turno (auditoria por turnoId).
 */
data class TurnoSessionRemote(
    val empresa: String,
    val equipe: String,
    val turnoId: String,

    val membersSnapshot: List<String>,

    val openedAtClientMs: Long,
    val closedAtClientMs: Long? = null,
    val closeReason: String? = null,

    val openedByUid: String? = null,
    val openedByDeviceId: String? = null,
    val closedByUid: String? = null,
    val closedByDeviceId: String? = null
)