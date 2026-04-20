// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/PresenceFirestore.kt
// Função: Gerenciador de presença em tempo real via Firestore. Controla eventos de entrada, 
//         saída e batimento cardíaco (heartbeat) para monitoramento das salas virtuais.
// Tecnologias: Firebase Firestore, Kotlin Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.online

import com.google.firebase.Timestamp
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await

class PresenceFirestore(
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
) {
    private fun nowEpochSec(): Long = System.currentTimeMillis() / 1000

    private suspend fun ensureAuth() {
        if (auth.currentUser == null) {
            auth.signInAnonymously().await()
        }
    }

    private fun presenceDoc(sessionId: String, uid: String) =
        db.collection("DDS_Sessions").document(sessionId)
            .collection("presence").document(uid)

    suspend fun join(sessionId: String, displayName: String, role: String) {
        ensureAuth()
        val uid = auth.currentUser!!.uid
        val docRef = presenceDoc(sessionId, uid)

        db.runTransaction { tx ->
            val snap = tx.get(docRef)
            val data = snap.data ?: emptyMap<String, Any>()
            val segs = (data["segments"] as? List<Map<String, Any>>)?.toMutableList() ?: mutableListOf()

            val last = segs.lastOrNull()
            val lastHasLeave = last?.containsKey("leave") == true

            // se já tem segmento aberto, não abre outro
            if (segs.isEmpty() || lastHasLeave) {
                segs.add(mapOf("join" to nowEpochSec()))
            }

            val base = mapOf(
                "userId" to uid,
                "displayName" to displayName,
                "role" to role,
                "segments" to segs,
                "lastSeenAt" to FieldValue.serverTimestamp()
            )

            tx.set(docRef, base, com.google.firebase.firestore.SetOptions.merge())
            null
        }.await()
    }

    suspend fun heartbeat(sessionId: String) {
        ensureAuth()
        val uid = auth.currentUser!!.uid
        presenceDoc(sessionId, uid).update(
            mapOf("lastSeenAt" to FieldValue.serverTimestamp())
        ).await()
    }

    suspend fun leave(sessionId: String) {
        ensureAuth()
        val uid = auth.currentUser!!.uid
        val docRef = presenceDoc(sessionId, uid)

        db.runTransaction { tx ->
            val snap = tx.get(docRef)
            val data = snap.data ?: return@runTransaction null

            val segs = (data["segments"] as? List<Map<String, Any>>)?.toMutableList() ?: return@runTransaction null
            if (segs.isEmpty()) return@runTransaction null

            val last = segs.last().toMutableMap()
            val hasLeave = last.containsKey("leave")

            if (!hasLeave) {
                last["leave"] = nowEpochSec()
                segs[segs.lastIndex] = last
                tx.update(docRef, mapOf(
                    "segments" to segs,
                    "lastSeenAt" to FieldValue.serverTimestamp()
                ))
            } else {
                // mesmo se já fechou, atualiza lastSeen (opcional)
                tx.update(docRef, "lastSeenAt", FieldValue.serverTimestamp())
            }
            null
        }.await()
    }
}