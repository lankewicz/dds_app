// Módulo: app/src/main/java/com/chicoeletro/dds/domain/RemoteDdsUploader.kt
// Função: Componente de upload para a nuvem. Realiza o envio físico da imagem para o Firebase 
//         Storage e a criação do registro correspondente no Firestore.
// Tecnologias: Firebase Storage, Firebase Firestore, Kotlin Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.domain

import android.net.Uri
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.ui.training.isWithinTrainingConclusionWindow
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.tasks.await
import java.io.File

class RemoteDdsUploader(
    private val storage: FirebaseStorage,
    private val firestore: FirebaseFirestore
) {
    suspend fun upload(
        submission: FormSubmission,
        collectionName: String,
        pastaFotos: String,
        duracaoFormatada: String
    ) {
        validateSubmissionWindow(submission)

        val nowNome = submission.submittedAt.replace(" ", "_").replace(":", "-")
        val nomeFoto = "${submission.trainingName}_${submission.equipe}_$nowNome.jpg"

        val photoPath = requireNotNull(submission.localPhotoPath) { "localPhotoPath vazio" }
        val photoFile = File(photoPath)

        val storageRef = storage.reference.child("$pastaFotos/ChicoEletro/Fotos/$nomeFoto")
        storageRef.putFile(Uri.fromFile(photoFile)).await()
        val fotoUrl = storageRef.downloadUrl.await().toString()

        val thumbUrl = submission.localThumbPath?.let { p ->
            val thumbFile = File(p)
            val thumbRef = storage.reference.child("$pastaFotos/ChicoEletro/Thumb/$nomeFoto")
            thumbRef.putFile(Uri.fromFile(thumbFile)).await()
            thumbRef.downloadUrl.await().toString()
        } ?: fotoUrl

        firestore.collection(collectionName).document(submission.submissionId).set(
            mapOf(
                "dataHora" to "${submission.dataConclusao} - ${submission.horaConclusao}",
                "duracao" to duracaoFormatada,
                "trainingName" to submission.trainingName,
                "equipe" to submission.equipe,
                "tema" to submission.tema,
                "eletricistas" to submission.eletricistas,
                "DataConclusao" to submission.dataConclusao,
                "HoraConclusao" to submission.horaConclusao,
                "headerDate" to submission.headerDate,
                "headerTitle" to submission.headerTitle,
                "fotoUrl" to fotoUrl,
                "thumbUrl" to thumbUrl,
                "submissionId" to submission.submissionId,
                "submittedAt" to submission.submittedAt
            )
        ).await()
    }



    private fun validateSubmissionWindow(submission: FormSubmission) {
        if (!isWithinTrainingConclusionWindow(submission.trainingName, submission.dataConclusao)) {
            throw DdsSubmissionWindowException(
                "O DDS ${submission.trainingName} está fora da janela permitida para conclusão."
            )
        }
    }
}