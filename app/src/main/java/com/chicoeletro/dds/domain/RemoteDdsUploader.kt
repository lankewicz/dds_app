package com.chicoeletro.dds.domain

import android.net.Uri
import com.chicoeletro.dds.data.FormSubmission
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

        firestore.collection(collectionName).add(
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
                "submissionId" to submission.submissionId
            )
        ).await()
    }
}
