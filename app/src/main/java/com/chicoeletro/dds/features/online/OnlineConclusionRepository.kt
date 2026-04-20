// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/OnlineConclusionRepository.kt
// Função: Repositório para persistência das conclusões do DDS Online. Gerencia o armazenamento 
//         das presenças e evidências coletadas em reuniões virtuais.
// Tecnologias: Firebase Firestore, DataStore.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.online

import android.net.Uri
import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.tasks.await

object OnlineConclusionRepository {
    private val auth = FirebaseAuth.getInstance()
    private val db = FirebaseFirestore.getInstance()
    private val storage = FirebaseStorage.getInstance()

    private suspend fun ensureAuth() {
        if (auth.currentUser == null) {
            auth.signInAnonymously().await()
        }
    }

    /**
     * NOVO: Cria (ou sobrescreve) um rascunho de conclusão SEM foto.
     * Regra: ao clicar em "Sair", os dados devem ficar gravados mesmo que o usuário não consiga tirar foto.
     *
     * ID do documento: uid autenticado (idempotente por usuário na sessão).
     */
    suspend fun createDraftWithoutPhoto(
        sessionId: String,
        form: OnlineConclusionForm,
    ) {
        ensureAuth()
        val uid = auth.currentUser!!.uid

        val docRef = db.collection("DDS_Sessions")
            .document(sessionId)
            .collection("conclusions")
            .document(uid)

        val payload = hashMapOf(
            "userId" to uid,
            "displayName" to form.displayName,
            "teamName" to form.teamName,
            "role" to form.role,
            "sessionId" to form.sessionId,
            "presentationTitle" to form.presentationTitle,
            "notes" to form.notes,
            "confirmPresence" to form.confirmPresence,
            "confirmPhoto" to false,
            "deviceInfo" to form.deviceInfo,
            "photoPath" to null,
            "thumbPath" to null,
            "status" to "draft",
            "createdAt" to Timestamp.now(),
        )

        docRef.set(payload).await()
    }

    /**
     * NOVO: Faz upload da foto (e thumb opcional) e atualiza o documento da conclusão.
     * Pode ser chamado depois do rascunho.
     */
    suspend fun attachPhoto(
        sessionId: String,
        photoUri: Uri,
        thumbUri: Uri?,
    ) {
        ensureAuth()
        val uid = auth.currentUser!!.uid

        val photoPath = "dds_sessions/$sessionId/conclusions/$uid/photo.jpg"
        val thumbPath = "dds_sessions/$sessionId/conclusions/$uid/thumb.jpg"

        val photoRef = storage.reference.child(photoPath)
        photoRef.putFile(photoUri).await()

        val thumbSavedPath = if (thumbUri != null) {
            val thumbRef = storage.reference.child(thumbPath)
            thumbRef.putFile(thumbUri).await()
            thumbPath
        } else null

        val docRef = db.collection("DDS_Sessions")
            .document(sessionId)
            .collection("conclusions")
            .document(uid)

        docRef.update(
            mapOf(
                "photoPath" to photoPath,
                "thumbPath" to thumbSavedPath,
                "confirmPhoto" to true
            )
        ).await()
    }

    /**
     * NOVO: Marca a conclusão como finalizada (com ou sem foto).
     */
    suspend fun markCompleted(sessionId: String) {
        ensureAuth()
        val uid = auth.currentUser!!.uid

        val docRef = db.collection("DDS_Sessions")
            .document(sessionId)
            .collection("conclusions")
            .document(uid)

        docRef.update(
            mapOf(
                "status" to "completed",
                "completedAt" to Timestamp.now()
            )
        ).await()
    }


    suspend fun saveConclusion(
        sessionId: String,
        form: OnlineConclusionForm,
        photoUri: Uri,
        thumbUri: Uri?,
    ) {
        ensureAuth()
        val uid = auth.currentUser!!.uid

        val photoPath = "dds_sessions/$sessionId/conclusions/$uid/photo.jpg"
        val thumbPath = "dds_sessions/$sessionId/conclusions/$uid/thumb.jpg"

        val photoRef = storage.reference.child(photoPath)
        photoRef.putFile(photoUri).await()

        val thumbSavedPath = if (thumbUri != null) {
            val thumbRef = storage.reference.child(thumbPath)
            thumbRef.putFile(thumbUri).await()
            thumbPath
        } else null

        val docRef = db.collection("DDS_Sessions")
            .document(sessionId)
            .collection("conclusions")
            .document(uid)

        val payload = hashMapOf(
            "userId" to uid,
            "displayName" to form.displayName,
            "teamName" to form.teamName,
            "role" to form.role,
            "sessionId" to form.sessionId,
            "presentationTitle" to form.presentationTitle,
            "notes" to form.notes,
            "confirmPresence" to form.confirmPresence,
            "confirmPhoto" to form.confirmPhoto,
            "deviceInfo" to form.deviceInfo,
            "photoPath" to photoPath,
            "thumbPath" to thumbSavedPath,
            "createdAt" to Timestamp.now(),
            "status" to "completed",
            "completedAt" to Timestamp.now(),
        )

        docRef.set(payload).await()
    }
}