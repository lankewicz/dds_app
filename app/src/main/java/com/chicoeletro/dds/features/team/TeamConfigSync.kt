// Módulo: app/src/main/java/com/chicoeletro/dds/features/team/TeamConfigSync.kt
// Função: Sincronizador da configuração de equipe. Garante que as mudanças locais no cadastro 
//         de membros e horários sejam replicadas para o Firestore, mantendo a consistência na nuvem.
// Tecnologias: Firebase Firestore, DataStore, java.time (YearMonth).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.team

import android.content.Context
import android.util.Log
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.core.LastTeamStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull

object TeamConfigSync {
    private val repo = TeamFormationRepository()

    private const val TAG = "TeamConfigSync"

    fun observeLocal(context: Context): Flow<LastTeamData?> =
        LastTeamStore.carregar(context)

    suspend fun savePendingLocal(
        context: Context,
        teamKey: String,
        members: List<String>,
        schedule: com.chicoeletro.dds.core.WorkSchedule,
        teamType: String? = null,
        motorista: String? = null,
        coringas: List<String> = emptyList()
    ) {
        val data = LastTeamData(
            equipe = teamKey,
            eletricistas = members,
            pendingSync = true,
            lastSyncedAt = null,
            workSchedule = schedule,
            teamType = teamType,
            motorista = motorista,
            coringas = coringas
        )
        LastTeamStore.salvar(context, data)
        Log.i(TAG, "savePendingLocal: team=$teamKey members=${members.size} teamType=$teamType pendingSync=true")
    }

    /**
     * Salva somente o tipo de equipe localmente, preservando o restante.
     */
    suspend fun saveTeamTypeLocal(context: Context, teamType: String) {
        val current = observeLocal(context).firstOrNull()
        if (current != null) {
            val updated = current.copy(teamType = teamType, pendingSync = true)
            LastTeamStore.salvar(context, updated)
            Log.i(TAG, "saveTeamTypeLocal: team=${current.equipe} type=$teamType")
            
            // Download do catalogo correspondente imediatamente no background
            try {
                com.chicoeletro.dds.features.construcao.MitCatalogManager.downloadCatalog(context, teamType)
            } catch (e: Exception) {
                Log.e(TAG, "Erro ao baixar catalogo na mudanca de tipo de equipe: ${e.message}", e)
            }
        }
    }

    /**
     * Salva somente o cache local (sem marcar pendência).
     * Útil para telas que apenas "persistem o último time" sem significar alteração operacional.
     */
    suspend fun saveLocalCache(context: Context, data: LastTeamData) {
        LastTeamStore.salvar(context, data.copy(pendingSync = false))
        Log.d(TAG, "saveLocalCache: team=${data.equipe} members=${data.eletricistas.size} pendingSync=false")
    }

    /**
     * Tenta enviar se:
     * - online
     * - data.pendingSync == true
     * - team/members válidos
     *
     * Em caso de sucesso, limpa pendingSync e grava lastSyncedAt.
     */
    suspend fun tryPushPending(context: Context, online: Boolean, data: LastTeamData?) {
        if (!online) return
        val d = data ?: return
        if (!d.pendingSync) return
        if (d.equipe.isBlank() || d.eletricistas.isEmpty()) return

        Log.i(TAG, "tryPushPending: attempting team=${d.equipe} members=${d.eletricistas.size}")
        
        // Converte WorkSchedule para Map (Firestore)
        val scheduleMap = d.workSchedule.days.map { day ->
            mapOf(
                "dayOfWeek" to day.dayOfWeek,
                "entry1" to day.entry1,
                "exit1" to day.exit1,
                "entry2" to day.entry2,
                "exit2" to day.exit2,
                "isRestDay" to day.isRestDay
            )
        }
        val payloadSchedule = mapOf("days" to scheduleMap)

        val ok = runCatching {
            repo.saveAndAudit(
                teamKey = d.equipe,
                newMembers = d.eletricistas,
                workSchedule = payloadSchedule,
                teamType = d.teamType,
                motorista = d.motorista,
                coringas = d.coringas
            )
        }.isSuccess

        if (ok) {
            LastTeamStore.salvar(
                context,
                d.copy(
                    pendingSync = false,
                    lastSyncedAt = System.currentTimeMillis()
                )
            )
            Log.i(TAG, "tryPushPending: SUCCESS team=${d.equipe} pendingSync=false")
        } else {
            Log.w(TAG, "tryPushPending: FAILED team=${d.equipe}; manterá pendingSync=true")
        }
    }

    /**
     * Puxa a formação mais recente do Firestore se:
     * - online
     * - não há pendência local (pendingSync=false)
     *
     * Se remoto divergir, atualiza o cache local.
     */
    suspend fun pullLatestIfSafe(context: Context, online: Boolean, data: LastTeamData?) {
        if (!online) return
        val d = data ?: return
        if (d.equipe.isBlank()) return
        if (d.pendingSync) return // não sobrescreve alterações locais pendentes

        val remote = runCatching { repo.getCurrent(d.equipe) }.getOrNull() ?: return
        val remoteMembers = remote.members
        
        // Converte o Map do Firestore de volta para WorkSchedule
        val remoteSchedule = remote.workSchedule?.let { map ->
            val daysList = (map["days"] as? List<*>)?.mapNotNull { it as? Map<*, *> }
            if (daysList != null) {
                val dailySchedules = daysList.map { m ->
                    com.chicoeletro.dds.core.DailySchedule(
                        dayOfWeek = (m["dayOfWeek"] as? Long)?.toInt() ?: 1,
                        entry1 = m["entry1"] as? String ?: "08:00",
                        exit1 = m["exit1"] as? String ?: "12:00",
                        entry2 = m["entry2"] as? String ?: "14:00",
                        exit2 = m["exit2"] as? String ?: "18:00",
                        isRestDay = m["isRestDay"] as? Boolean ?: false
                    )
                }
                com.chicoeletro.dds.core.WorkSchedule(dailySchedules)
            } else null
        }

        val remoteCoringas = remote.coringas
        val membersChanged = remoteMembers.isNotEmpty() && remoteMembers != d.eletricistas
        val scheduleChanged = remoteSchedule != null && remoteSchedule != d.workSchedule
        val remoteTeamType = remote.teamType
        val typeChanged = remoteTeamType != null && remoteTeamType != d.teamType
        val remoteMotorista = remote.motorista
        val motoristaChanged = remoteMotorista != null && remoteMotorista != d.motorista
        val coringasChanged = remoteCoringas != d.coringas

        if (membersChanged || scheduleChanged || typeChanged || motoristaChanged || coringasChanged) {
            LastTeamStore.salvar(
                context,
                d.copy(
                    eletricistas = if (membersChanged) remoteMembers else d.eletricistas,
                    workSchedule = if (scheduleChanged) remoteSchedule!! else d.workSchedule,
                    teamType = if (typeChanged) remoteTeamType else d.teamType,
                    motorista = if (motoristaChanged) remoteMotorista else d.motorista,
                    coringas = if (coringasChanged) remoteCoringas else d.coringas,
                    pendingSync = false,
                    lastSyncedAt = System.currentTimeMillis()
                )
            )
            Log.i(TAG, "pullLatestIfSafe: UPDATED team=${d.equipe} (members=$membersChanged, schedule=$scheduleChanged, type=$typeChanged)")
        } else {
            Log.d(TAG, "pullLatestIfSafe: no change team=${d.equipe}")
        }
    }
}