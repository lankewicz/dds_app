// Módulo: app/src/main/java/com/chicoeletro/dds/features/training/TeamTrainingExecutionRepository.kt
// Função: Repositório para registro e consulta das execuções de treinamento da equipe. 
//         Sincroniza o estado de conclusão entre o cache local e o histórico no Firestore.
// Tecnologias: Firebase Firestore, DataStore Integration.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

// -----------------------------------------------------------------------------
// Arquivo : com.chicoeletro.dds\features\training\TeamTrainingExecutionRepository.kt
// Módulo  : DDS / Treinamentos (Persistência)
// Objetivo: Persistir no Firebase (Firestore) a lista de treinamentos executados
//           por equipe, por mês, garantindo continuidade mesmo ao trocar de tablet.
//
// Regra de negócio:
//   - Um treinamento é considerado "executado" após tirar a foto e clicar em Concluir.
//   - A checagem de "já executado" deve consultar a fonte de verdade (Firestore),
//     e não apenas o armazenamento local do dispositivo.
//
// Estrutura no Firestore:
//   dds_training_exec/{teamKey}/months/{yyyy-MM}
//     - executedTrainings: map(trainingId -> { dataConclusao, horaConclusao, duracao, executedAt, byUid, deviceModel })
//     - updatedAt, updatedBy
//
// Observações:
//   - Usa Auth anônimo quando necessário (offline-first e auditoria básica).
//   - A escrita é idempotente por trainingId dentro do mês.
// -----------------------------------------------------------------------------

package com.chicoeletro.dds.features.training

import com.google.firebase.Timestamp
import com.chicoeletro.dds.domain.DdsSubmissionWindowException
import com.chicoeletro.dds.ui.training.isWithinTrainingConclusionWindow
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.DocumentSnapshot
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.tasks.await
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.text.Normalizer
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.zip.GZIPInputStream

/**
 * Fonte de verdade (Firestore) para "treinamentos executados pela equipe".
 *
 * Estrutura:
 * dds_training_exec/{teamKey}/months/{yyyy-MM}
 * - executedTrainings: map(trainingId -> { dataConclusao, horaConclusao, duracao, executedAt, byUid, deviceModel })
 * - updatedAt, updatedBy
 */
class TeamTrainingExecutionRepository(
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val storage: FirebaseStorage = FirebaseStorage.getInstance(),
) {
    companion object {
        private const val ROOT = "dds_training_exec"
        private const val CONTROL_ROOT = "dados/chicoeletro/dds/controle"
        private const val MAX_PROJECTION_BYTES = 1024L * 1024L

        fun teamKeyOf(teamName: String): String {
            val raw = teamName.trim().uppercase().replace("\\(\\d+\\)\\s*$".toRegex(), "")
            val noAccents = Normalizer.normalize(raw, Normalizer.Form.NFD)
                .replace("\\p{InCombiningDiacriticalMarks}+".toRegex(), "")
            return noAccents
                .replace("[^A-Z0-9]+".toRegex(), "_")
                .trim('_')
                .ifEmpty { "TEAM" }
        }
    }

    private suspend fun ensureAuth(): String {
        val current = auth.currentUser
        if (current != null) return current.uid
        val res = auth.signInAnonymously().await()
        return res.user?.uid ?: throw IllegalStateException("Falha ao autenticar no Firebase")
    }

    private fun monthDoc(teamKey: String, ym: YearMonth) =
        db.collection(ROOT).document(teamKey)
            .collection("months").document(ym.toString()) // yyyy-MM

    data class ExecStatus(
        val dataConclusao: String,
        val horaConclusao: String,
        val duracao: String
    )

    suspend fun getExecutedTrainingsForMonth(teamName: String, ym: java.time.YearMonth): Map<String, ExecStatus> {
        val teamKey = teamKeyOf(teamName)
        ensureAuth()
        val bytes = storage.reference
            .child("$CONTROL_ROOT/monthly/${ym}/$teamKey.json.gz")
            .getBytes(MAX_PROJECTION_BYTES)
            .await()
        val decoded = if (bytes.size >= 2 && bytes[0] == 0x1f.toByte() && bytes[1] == 0x8b.toByte()) {
            GZIPInputStream(ByteArrayInputStream(bytes)).bufferedReader(Charsets.UTF_8).use { it.readText() }
        } else {
            bytes.toString(Charsets.UTF_8)
        }
        val root = JSONObject(decoded)
        val executions = root.optJSONObject("executions") ?: return emptyMap()
        val output = mutableMapOf<String, ExecStatus>()
        val keys = executions.keys()
        while (keys.hasNext()) {
            val trainingId = keys.next()
            val item = executions.optJSONObject(trainingId) ?: continue
            val completedAt = item.optString("completedAt", "")
            val local = runCatching {
                OffsetDateTime.parse(completedAt).atZoneSameInstant(ZoneId.of("America/Sao_Paulo"))
            }.getOrNull()
            val headerDate = runCatching {
                LocalDate.parse(item.optString("headerDate", ""))
                    .format(DateTimeFormatter.ofPattern("dd-MM-yyyy"))
            }.getOrNull()
            val date = headerDate
                ?: local?.format(DateTimeFormatter.ofPattern("dd-MM-yyyy"))
                ?: ""
            val time = local?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: "00:00"
            if (date.isNotBlank()) output[trainingId] = ExecStatus(date, time, "")
        }
        return output
    }

    /**
     * Marca um treinamento como executado (idempotente: escreve no mesmo caminho).
     */
    suspend fun markExecuted(
        teamName: String,
        ym: YearMonth,
        trainingId: String,
        dataConclusao: String,
        horaConclusao: String,
        duracao: String,
        deviceModel: String,
    ) {
        if (!isWithinTrainingConclusionWindow(trainingId, dataConclusao)) {
            throw DdsSubmissionWindowException(
                "O DDS $trainingId está fora da janela permitida para conclusão."
            )
        }

        val uid = ensureAuth()
        val teamKey = teamKeyOf(teamName)
        val ref = monthDoc(teamKey, ym)

        val payload: Map<String, Any> = mapOf(
            "dataConclusao" to dataConclusao,
            "horaConclusao" to horaConclusao,
            "duracao" to duracao,
            "executedAt" to Timestamp.now(),
            "byUid" to uid,
            "deviceModel" to deviceModel
        )

        // ✅ MERGE seguro via mapa aninhado (sem FieldPath)
        // Isso faz merge apenas em executedTrainings[trainingId]
        val update: Map<String, Any> = mapOf(
            "teamName" to teamName,
            "month" to ym.toString(),
            "updatedAt" to Timestamp.now(),
            "updatedBy" to uid,
            "executedTrainings" to mapOf(trainingId to payload)
        )

        ref.set(update, com.google.firebase.firestore.SetOptions.merge()).await()
    }

    private fun parseExecutedTrainings(snap: DocumentSnapshot): Map<String, ExecStatus> {
        val raw = snap.get("executedTrainings") as? Map<*, *> ?: return emptyMap()
        val out = mutableMapOf<String, ExecStatus>()
        for ((k, v) in raw) {
            val id = k as? String ?: continue
            val obj = v as? Map<*, *> ?: continue
            val data = obj["dataConclusao"] as? String ?: continue
            val hora = obj["horaConclusao"] as? String ?: continue
            val dur = obj["duracao"] as? String ?: ""
            out[id] = ExecStatus(data, hora, dur)
        }
        return out
    }
}
