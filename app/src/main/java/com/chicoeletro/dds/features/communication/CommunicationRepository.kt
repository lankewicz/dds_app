// Módulo: app/src/main/java/com/chicoeletro/dds/features/communication/CommunicationRepository.kt
// Função: Gerenciamento de mensagens no Firebase Firestore.

package com.chicoeletro.dds.features.communication

import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await

class CommunicationRepository {
    private val db = FirebaseFirestore.getInstance()
    private val collection = db.collection("mensagens_comunicacao")

    suspend fun sendMessage(message: TeamMessage): Result<String> {
        return try {
            val docRef = collection.add(message).await()
            Result.success(docRef.id)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getHistory(equipe: String): List<TeamMessage> {
        return try {
            val query = collection
                .whereEqualTo("fromEquipe", equipe)
                .orderBy("timestamp", com.google.firebase.firestore.Query.Direction.DESCENDING)
                .get()
                .await()
            
            query.toObjects(TeamMessage::class.java)
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun listenIncoming(equipe: String, onUpdate: (List<TeamMessage>) -> Unit): com.google.firebase.firestore.ListenerRegistration {
        return collection
            .whereEqualTo("toEquipe", equipe)
            .addSnapshotListener { snapshot, _ ->
                val msgs = snapshot?.documents?.mapNotNull { doc ->
                    doc.toObject(TeamMessage::class.java)?.copy(id = doc.id)
                } ?: emptyList()
                onUpdate(msgs)
            }
    }

    fun listenOutgoing(equipe: String, onUpdate: (List<TeamMessage>) -> Unit): com.google.firebase.firestore.ListenerRegistration {
        return collection
            .whereEqualTo("fromEquipe", equipe)
            .addSnapshotListener { snapshot, _ ->
                val msgs = snapshot?.documents?.mapNotNull { doc ->
                    doc.toObject(TeamMessage::class.java)?.copy(id = doc.id)
                } ?: emptyList()
                onUpdate(msgs)
            }
    }

    suspend fun markAsRead(messageId: String) {
        try {
            collection.document(messageId).update("status", "LIDO").await()
        } catch (e: Exception) {
            // Log error
        }
    }

    suspend fun markThreadAsConcluded(threadId: String) {
        try {
            val query = collection.whereEqualTo("threadId", threadId).get().await()
            val batch = db.batch()
            query.documents.forEach { doc ->
                batch.update(doc.reference, "status", "CONCLUIDA")
            }
            batch.commit().await()
        } catch (e: Exception) {
            // Log error
        }
    }

    fun listenThread(threadId: String, onUpdate: (List<TeamMessage>) -> Unit): com.google.firebase.firestore.ListenerRegistration {
        return collection
            .whereEqualTo("threadId", threadId)
            .orderBy("timestamp", com.google.firebase.firestore.Query.Direction.ASCENDING)
            .addSnapshotListener { snapshot, _ ->
                val msgs = snapshot?.documents?.mapNotNull { doc ->
                    doc.toObject(TeamMessage::class.java)?.copy(id = doc.id)
                } ?: emptyList()
                onUpdate(msgs)
            }
    }

    suspend fun reopenThread(threadId: String) {
        try {
            val query = collection.whereEqualTo("threadId", threadId).get().await()
            val batch = db.batch()
            query.documents.forEach { doc ->
                if (doc.getString("status") == "CONCLUIDA") {
                    batch.update(doc.reference, "status", "LIDO")
                }
            }
            batch.commit().await()
        } catch (e: Exception) {
            // Log error
        }
    }

    suspend fun deleteMessage(messageId: String): Result<Unit> {
        return try {
            collection.document(messageId).delete().await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
