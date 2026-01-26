package com.chicoeletro.dds.features.team

import android.content.Context
import android.util.Log
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.core.LastTeamStore
import kotlinx.coroutines.flow.Flow

/**
 * Responsável por:
 * - Persistência local (offline-first)
 * - Push para Firestore com auditoria (quando online)
 * - Pull da configuração mais recente (quando online e seguro)
 * - Retry automático quando voltar a internet (pendingSync)
 */
class TeamConfigSync(
    private val repo: TeamFormationRepository = TeamFormationRepository()
) {

    private companion object {
        private const val TAG = "TeamConfigSync"
    }

    fun observeLocal(context: Context): Flow<LastTeamData?> =
        LastTeamStore.carregar(context)

    suspend fun savePendingLocal(context: Context, teamKey: String, members: List<String>) {
        val data = LastTeamData(
            equipe = teamKey,
            eletricistas = members,
            pendingSync = true,
            lastSyncedAt = null
        )
        LastTeamStore.salvar(context, data)
        Log.i(TAG, "savePendingLocal: team=$teamKey members=${members.size} pendingSync=true")
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
        val ok = runCatching {
            repo.saveAndAudit(teamKey = d.equipe, newMembers = d.eletricistas)
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
        if (remoteMembers.isEmpty()) return

        if (remoteMembers != d.eletricistas) {
            LastTeamStore.salvar(
                context,
                d.copy(
                    eletricistas = remoteMembers,
                    pendingSync = false,
                    lastSyncedAt = System.currentTimeMillis()
                )
            )
            Log.i(TAG, "pullLatestIfSafe: UPDATED team=${d.equipe} members=${remoteMembers.size}")
        } else {
            Log.d(TAG, "pullLatestIfSafe: no change team=${d.equipe}")
        }
    }
}
