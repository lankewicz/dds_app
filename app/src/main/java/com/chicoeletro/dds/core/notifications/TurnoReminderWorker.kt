// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/TurnoReminderWorker.kt
// Função: Monitoramento de jornada em background. Dispara lembretes sobre status de turno, 
//         abertura/fechamento e validação de intervalos (Art. 66/67 CLT).
// Tecnologias: WorkManager (PeriodicWork), Java Time API, TurnoController.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.chicoeletro.dds.core.LastTeamStore
import com.chicoeletro.dds.features.turno.EstadoTurno
import com.chicoeletro.dds.features.turno.TurnoController
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import kotlinx.coroutines.flow.firstOrNull
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Calendar

class TurnoReminderWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val now = LocalDateTime.now(ZoneId.of("America/Sao_Paulo"))
        
        // Identifica a equipe ativa
        val teamData = LastTeamStore.carregar(applicationContext).firstOrNull() ?: return Result.success()
        val teamName = teamData.equipe
        if (teamName.isBlank()) return Result.success()

        // 1. Identifica o cronograma de hoje
        // java.time.DayOfWeek: Mon=1...Sun=7. 
        // Nosso modelo: Sun=1, Mon=2...Sat=7
        val dayIdx = now.dayOfWeek.value % 7 + 1
        val schedule = teamData.workSchedule.days.find { it.dayOfWeek == dayIdx } ?: com.chicoeletro.dds.core.DailySchedule(dayIdx)

        // 2. Silêncio absoluto em dias de descanso
        if (schedule.isRestDay) {
            return Result.success()
        }

        // 3. Obtém o status do turno
        val turnoController = TurnoController(applicationContext, teamName)
        val snap = turnoController.current()
        
        // Determina horas de início e fim baseadas no cronograma
        val startHour = schedule.entry1.split(":").firstOrNull()?.toIntOrNull() ?: 8
        // endHour é o horário da última saída preenchida
        val endHour = (schedule.exit2.ifBlank { schedule.exit1 }).split(":").firstOrNull()?.toIntOrNull() ?: 18
        
        val currentHour = now.hour

        // --- LÓGICA DE TRABALHO (Durante a jornada) ---
        if (currentHour in startHour until endHour) {
            if (snap.estado == EstadoTurno.FECHADO) {
                // Se for a primeira hora, usamos o tom de "Bom dia"
                if (currentHour == startHour) {
                    val lastClosedMs = snap.lastClosedAtMs ?: 0L
                    val diffHours = (System.currentTimeMillis() - lastClosedMs) / (1000 * 60 * 60)

                    if (snap.lastWasDescansoSemanal) {
                        // ART 67: Só avisa se já passou 24h
                        if (diffHours >= NotificationConfig.INTERJORNADA_ART67_HOURS) {
                            NotificationHelper.showTurnoNotification(
                                applicationContext,
                                "Hora de começar!",
                                "O intervalo de 24h (Art. 67) foi concluído. Abra o turno para iniciar as atividades."
                            )
                        }
                    } else {
                        // Normal: Avisa se já passou o descanso de 11h
                        if (diffHours >= NotificationConfig.INTERJORNADA_NORMAL_HOURS) {
                            NotificationHelper.showTurnoNotification(
                                applicationContext,
                                "Equipe ${teamName}",
                                "Bom dia! Não esqueça de abrir o turno e realizar o DDS."
                            )
                        }
                    }
                }
            } else {
                // Se o turno não está fechado (Aberto, Intervalo, etc), verifica DDS sempre
                checkDdsAndNotify(teamName, snap.estado.name)
            }
        }

        // --- LÓGICA PERIÓDICA (A cada 1h) ---
        val lastChangedMs = snap.lastEventAtClientMs
        val timeSinceChangeHours = (System.currentTimeMillis() - lastChangedMs) / (1000 * 60 * 60)

        when (snap.estado) {
            EstadoTurno.ABERTO -> {
                if (timeSinceChangeHours >= NotificationConfig.SHIFT_ABERTO_MAX_HOURS) {
                    if (currentHour < endHour) {
                        NotificationHelper.showTurnoNotification(
                            applicationContext,
                            "Intervalo de Repouso",
                            "Você está com o turno aberto há ${timeSinceChangeHours}h. Considere realizar seu intervalo."
                        )
                    } else {
                        NotificationHelper.showTurnoNotification(
                            applicationContext,
                            "Fim de Jornada?",
                            "Já passamos das ${endHour}:00. Deseja realizar o intervalo ou fechar o turno?"
                        )
                    }
                } else if (currentHour >= endHour) {
                    // Mesmo que não tenha dado 6h, se passou do horário de fim, avisa uma vez
                    NotificationHelper.showTurnoNotification(
                        applicationContext,
                        "Atenção ao Horário",
                        "Turno ainda está aberto após às ${endHour}:00. Favor informar intervalo ou fechamento."
                    )
                }
            }

            EstadoTurno.INTERVALO -> {
                if (timeSinceChangeHours >= NotificationConfig.SHIFT_INTERVALO_MAX_HOURS) {
                    if (currentHour < endHour) {
                        NotificationHelper.showTurnoNotification(
                            applicationContext,
                            "Retorno do Intervalo",
                            "O intervalo está ativo há ${timeSinceChangeHours}h. Favor abrir o turno para continuar."
                        )
                    }
                    // Se for após o endHour, silenciamos conforme regra.
                }
            }

            EstadoTurno.DESLOCAMENTO_ESPECIAL -> {
                if (timeSinceChangeHours >= NotificationConfig.SHIFT_DESLOCAMENTO_INITIAL_HOURS) {
                    NotificationHelper.showTurnoNotification(
                        applicationContext,
                        "Confirmação de Status",
                        "Você está em Deslocamento Especial há ${timeSinceChangeHours}h. Confirme sua situação.",
                        isDeslocamento = true
                    )
                }
            }

            EstadoTurno.FECHADO -> {
                // Nag se estiver fechado há muito tempo (status esquecido?)
                val threshold = if (snap.lastWasDescansoSemanal) NotificationConfig.INTERJORNADA_ART67_HOURS else NotificationConfig.INTERJORNADA_NAG_THRESHOLD
                if (timeSinceChangeHours >= threshold && currentHour in startHour..endHour) {
                    NotificationHelper.showTurnoNotification(
                        applicationContext,
                        "Verificar Status",
                        "O turno está fechado há ${timeSinceChangeHours}h. Deseja abrir o turno?"
                    )
                }
            }
        }

        return Result.success()
    }

    private suspend fun checkDdsAndNotify(teamName: String, statusTurno: String) {
        val today = LocalDateTime.now(ZoneId.of("America/Sao_Paulo")).format(DateTimeFormatter.ISO_LOCAL_DATE)
        val teamKey = "team_${teamName.lowercase().trim()}"
        val monthId = today.substring(0, 7) // YYYY-MM
        
        val localRecords = TrainingExecLocalStore.flowMonth(applicationContext, teamKey, monthId).firstOrNull() ?: emptyMap()
        val alreadyDone = localRecords.values.any { it.dataConclusao == today }
        
        if (!alreadyDone) {
            NotificationHelper.showDdsNotification(applicationContext, statusTurno)
        }
    }
}