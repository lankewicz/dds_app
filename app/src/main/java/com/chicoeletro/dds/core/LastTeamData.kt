// Módulo: app/src/main/java/com/chicoeletro/dds/core/LastTeamData.kt
// Função: Modelos de dados para gestão de equipes e cronogramas de trabalho. Define a estrutura da 
//         jornada diária e horários para validação das regras de interjornada (Art. 66/67 CLT).
// Tecnologias: Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/06/2025: Criação inicial.
//   - 12/06/2025: Adicionada anotação @Serializable para Kotlinx Serialization.

package com.chicoeletro.dds.core

import kotlinx.serialization.Serializable

@Serializable
data class DailySchedule(
    val dayOfWeek: Int, // 1 (Su) a 7 (Sa)
    val entry1: String = "08:00",
    val exit1: String = "12:00",
    val entry2: String = "14:00",
    val exit2: String = "18:00",
    val isRestDay: Boolean = false
)

@Serializable
data class WorkSchedule(
    val days: List<DailySchedule> = createDefaultSchedule()
) {
    companion object {
        fun createDefaultSchedule(): List<DailySchedule> {
            return (1..7).map { d ->
                when (d) {
                    1 -> DailySchedule(d, isRestDay = true) // Domingo
                    7 -> DailySchedule(d, entry2 = "", exit2 = "") // Sábado (só manhã)
                    else -> DailySchedule(d) // Seg-Sex (08-12/14-18)
                }
            }
        }
    }
}

@Serializable
data class LastTeamData(
    val equipe: String,
    val eletricistas: List<String>,
    // Se true, significa: "salvei local, mas ainda não confirmei write no Firestore"
    val pendingSync: Boolean = false,
    // Epoch millis do último sync concluído com sucesso
    val lastSyncedAt: Long? = null,
    // [LEGACY] Mantidos para compatibilidade durante transição
    val workStartHour: Int = 7,
    val workEndHour: Int = 18,
    // NOVO: Cronograma detalhado
    val workSchedule: WorkSchedule = WorkSchedule()
)