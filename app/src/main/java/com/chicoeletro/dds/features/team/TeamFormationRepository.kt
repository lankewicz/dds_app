// Módulo: app/src/main/java/com/chicoeletro/dds/features/team/TeamFormationRepository.kt
// Função: Gerenciador da formação das equipes. Provê acesso aos dados mestre de composição 
//         dos grupos e gerencia a persistência local e remota da estrutura operacional.
// Tecnologias: Firebase Firestore, DataStore, Kotlin Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

// -----------------------------------------------------------------------------
// Arquivo : TeamFormationRepository.kt
// Módulo  : DDS / Equipes (Persistência + Histórico)
// Objetivo: Consultar a última formação da equipe pelo prefixo e registrar
//           histórico de alterações (quem/quando/antes/depois) no Firestore.
// -----------------------------------------------------------------------------
package com.chicoeletro.dds.features.team

import android.os.Build
import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import kotlinx.coroutines.tasks.await

data class TeamFormation(
    val teamKey: String,
    val members: List<String>,
    val workSchedule: Map<String, Any>? = null,
    val updatedAt: Timestamp? = null,
    val updatedByUid: String? = null,
    val updatedByName: String? = null,
    val updatedByEmail: String? = null,
)

class TeamFormationRepository(
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
) {
    companion object {
        private const val ROOT = "dds_teams"
    }

    private suspend fun ensureAuthUid(): String {
        val u = auth.currentUser
        if (u != null) return u.uid
        val res = auth.signInAnonymously().await()
        return res.user?.uid ?: throw IllegalStateException("Falha ao autenticar no Firebase")
    }

    private fun doc(teamKey: String) = db.collection(ROOT).document(teamKey)

    suspend fun getCurrent(teamKey: String): TeamFormation? {
        // garante sessão (anônima ok)
        ensureAuthUid()
        val snap = doc(teamKey).get().await()
        if (!snap.exists()) return null

        val members = (snap.get("members") as? List<*>)?.mapNotNull { it as? String } ?: emptyList()
        @Suppress("UNCHECKED_CAST")
        val schedule = snap.get("workSchedule") as? Map<String, Any>

        return TeamFormation(
            teamKey = teamKey,
            members = members,
            workSchedule = schedule,
            updatedAt = snap.getTimestamp("updatedAt"),
            updatedByUid = snap.getString("updatedByUid"),
            updatedByName = snap.getString("updatedByName"),
            updatedByEmail = snap.getString("updatedByEmail"),
        )
    }

    suspend fun saveAndAudit(teamKey: String, newMembers: List<String>, workSchedule: Map<String, Any>? = null) {
        val uid = ensureAuthUid()

        val before = getCurrent(teamKey)
        val beforeMembers = before?.members ?: emptyList()

        val now = Timestamp.now()

        // Auditoria operacional por equipe (sem login Google)
        val whoName = teamKey
        val whoEmail = ""

        val currentPayload: MutableMap<String, Any> = mutableMapOf(
            "teamKey" to teamKey,
            "members" to newMembers,
            "updatedAt" to now,
            "updatedByUid" to uid,
            "updatedByName" to whoName,
            "updatedByEmail" to whoEmail,
            "deviceModel" to Build.MODEL
        )
        if (workSchedule != null) {
            currentPayload["workSchedule"] = workSchedule
        }

        // Atualiza CURRENT (merge)
        doc(teamKey).set(currentPayload, SetOptions.merge()).await()

        // Escreve histórico (sempre que salvar)
        val action = if (beforeMembers.isEmpty()) "CREATE" else "UPDATE"
        val histPayload: MutableMap<String, Any> = mutableMapOf(
            "action" to action,
            "changedAt" to now,
            "changedByUid" to uid,
            "changedByName" to whoName,
            "changedByEmail" to whoEmail,
            "deviceModel" to Build.MODEL,
            "beforeMembers" to beforeMembers,
            "afterMembers" to newMembers
        )
        if (workSchedule != null) {
            histPayload["afterSchedule"] = workSchedule
        }
        if (before?.workSchedule != null) {
            histPayload["beforeSchedule"] = before.workSchedule
        }

        doc(teamKey).collection("history").add(histPayload).await()
    }
}