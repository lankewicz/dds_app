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
        return TeamFormation(
            teamKey = teamKey,
            members = members,
            updatedAt = snap.getTimestamp("updatedAt"),
            updatedByUid = snap.getString("updatedByUid"),
            updatedByName = snap.getString("updatedByName"),
            updatedByEmail = snap.getString("updatedByEmail"),
        )
    }

    suspend fun saveAndAudit(teamKey: String, newMembers: List<String>) {
        val uid = ensureAuthUid()

        val before = getCurrent(teamKey)?.members ?: emptyList()

        val now = Timestamp.now()

        // Auditoria operacional por equipe (sem login Google)
        val whoName = teamKey
        val whoEmail = ""

        val currentPayload: Map<String, Any> = mapOf(
            "teamKey" to teamKey,
            "members" to newMembers,
            "updatedAt" to now,
            "updatedByUid" to uid,
            "updatedByName" to whoName,
            "updatedByEmail" to whoEmail,
            "deviceModel" to Build.MODEL
        )

        // Atualiza CURRENT (merge)
        doc(teamKey).set(currentPayload, SetOptions.merge()).await()

        // Escreve histórico (sempre que salvar)
        val action = if (before.isEmpty()) "CREATE" else "UPDATE"
        val histPayload: Map<String, Any> = mapOf(
            "action" to action,
            "changedAt" to now,
            "changedByUid" to uid,
            "changedByName" to whoName,
            "changedByEmail" to whoEmail,
            "deviceModel" to Build.MODEL,
            "beforeMembers" to before,
            "afterMembers" to newMembers
        )

        doc(teamKey).collection("history").add(histPayload).await()
    }
}