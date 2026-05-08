package com.chicoeletro.dds.features.online

import android.util.Log
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.tasks.await

class MeetingRepository(
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
) {
    // Agora apontando para a coleção correta (criada pelo backend)
    private val collection = db.collection("DDS_Sessions")

    fun observeActiveSessions(): Flow<List<DdsSession>> = callbackFlow {
        // Observa reuniões que estão "scheduled" (ou outros status ativos)
        val listener = collection
            .whereEqualTo("type", "online")
            .whereIn("status", listOf("scheduled", "active"))
            .addSnapshotListener { snapshot, error ->
                if (error != null) {
                    Log.e("MeetingRepository", "Erro ao observar DDS_Sessions", error)
                    close(error)
                    return@addSnapshotListener
                }
                
                val sessions = snapshot?.documents?.mapNotNull { doc ->
                    try {
                        doc.toObject(DdsSession::class.java)?.copy(id = doc.id)
                    } catch (e: Exception) {
                        Log.w("MeetingRepository", "Erro ao converter documento ${doc.id}", e)
                        null
                    }
                } ?: emptyList()
                
                trySend(sessions)
            }
            
        awaitClose { listener.remove() }
    }

    suspend fun updateSessionStatus(sessionId: String, newStatus: String) {
        try {
            collection.document(sessionId).update("status", newStatus).await()
            Log.d("MeetingRepository", "Status da sessão $sessionId atualizado para $newStatus")
        } catch (e: Exception) {
            Log.e("MeetingRepository", "Erro ao atualizar status da sessão $sessionId", e)
            throw e
        }
    }
}
