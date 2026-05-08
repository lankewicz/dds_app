// Módulo: app/src/main/java/com/chicoeletro/dds/features/team/TeamChangeRequestRepository.kt
// Função: Gerencia solicitações de alteração de prefixo que precisam de aprovação remota.
// Tecnologias: Firebase Firestore.

package com.chicoeletro.dds.features.team

import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.ListenerRegistration
import com.google.firebase.firestore.SetOptions
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import java.time.Instant

enum class RequestStatus {
    PENDING,
    APPROVED,
    REJECTED
}

data class TeamChangeRequest(
    val id: String = "",
    val oldPrefix: String = "",
    val newPrefix: String = "",
    val reason: String = "", // TeamChangeReason.name
    val status: String = RequestStatus.PENDING.name,
    val requestedAt: String = "",
    val deviceId: String = "",
    val appVersion: String = ""
)

class TeamChangeRequestRepository(private val db: FirebaseFirestore = FirebaseFirestore.getInstance()) {

    fun createRequest(
        oldPrefix: String,
        newPrefix: String,
        reason: String,
        deviceId: String,
        appVersion: String
    ): String {
        val docRef = db.collection("prefix_change_requests").document()
        val request = TeamChangeRequest(
            id = docRef.id,
            oldPrefix = oldPrefix.trim().uppercase(),
            newPrefix = newPrefix.trim().uppercase(),
            reason = reason,
            status = RequestStatus.PENDING.name,
            requestedAt = Instant.now().toString(),
            deviceId = deviceId,
            appVersion = appVersion
        )
        docRef.set(request)
        return docRef.id
    }

    fun observeRequest(requestId: String): Flow<TeamChangeRequest?> = callbackFlow {
        val docRef = db.collection("prefix_change_requests").document(requestId)
        val listener = docRef.addSnapshotListener { snapshot, error ->
            if (error != null) {
                close(error)
                return@addSnapshotListener
            }
            val req = snapshot?.toObject(TeamChangeRequest::class.java)
            trySend(req)
        }
        awaitClose { listener.remove() }
    }

    suspend fun deleteRequest(requestId: String) {
        db.collection("prefix_change_requests").document(requestId).delete()
    }
}
