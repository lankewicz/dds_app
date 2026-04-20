// Módulo: app/src/main/java/com/chicoeletro/dds/data/StorageTrainingRepository.kt
// Função: Repositório para carregamento de treinamentos via Firebase Storage. Gerencia o download 
//         do índice mestre e a listagem de arquivos remotos para atualização de cache.
// Tecnologias: Firebase Storage, Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 06/06/2025: Criação inicial.
//   - 30/06/2025: Removido suporte offline; acessa URLs diretas. Adicionado fetchTrainingsComArquivos().

package com.chicoeletro.dds.data

import android.content.Context
import android.util.Log
import com.google.firebase.Firebase
import com.google.firebase.storage.FirebaseStorage
import com.google.firebase.storage.storage
import kotlinx.coroutines.tasks.await
import kotlinx.serialization.json.Json
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class StorageTrainingRepository(
    private val context: Context
) : TrainingRepository {

    private val storage: FirebaseStorage = Firebase.storage

    // Pastas base no Firebase Storage
    private companion object {
        const val PASTA_LISTA = "DDSv2"
        const val PASTA_IMAGENS = "DDSv2"
    }

    /**
     * Nova versão que retorna os arquivos completos e os treinamentos derivados deles.
     */
    suspend fun fetchTrainingsComArquivos(): Pair<List<Training>, List<String>> = runCatching {
        val bytes = storage.reference
            .child("$PASTA_LISTA/lista.json")
            .getBytes(5 * 1024 * 1024)
            .await()

        val wrapper = Json.decodeFromString<ListaJson>(bytes.toString(Charsets.UTF_8))
        val arquivos = wrapper.files

        val treinamentos = arquivos
            .mapNotNull { path ->
                path.removePrefix("$PASTA_IMAGENS/").substringBefore('/', "").takeIf { it.isNotBlank() }
            }
            .toSet()
            .mapNotNull { pasta ->
                pasta.split(" - ", limit = 2).takeIf { it.size == 2 }?.let { partes ->
                    val date = LocalDate.parse(partes[0].trim(), DateTimeFormatter.ISO_LOCAL_DATE)
                    Training(
                        id = pasta,
                        date = date.format(DateTimeFormatter.ofPattern("dd/MM/yyyy")),
                        title = partes[1].trim()
                    )
                }
            }
            .sortedByDescending {
                LocalDate.parse(it.date, DateTimeFormatter.ofPattern("dd/MM/yyyy"))
            }

        Pair(treinamentos, arquivos)
    }.getOrElse {
        Log.e("StorageRepo", "Erro ao carregar lista completa", it)
        Pair(emptyList(), emptyList())
    }

    /**
     * Função legada (ainda usada como fallback se necessário).
     */
    override suspend fun fetchTrainings(): List<Training> = fetchTrainingsComArquivos().first

    /**
     * Lista as URLs das imagens disponíveis dentro da pasta de um treinamento específico.
     */
    suspend fun getImagesForTraining(trainingId: String): List<String> = runCatching {
        val folderRef = storage.reference.child(PASTA_IMAGENS).child(trainingId)
        val items = folderRef.listAll().await().items
        items.map { it.downloadUrl.await().toString() }.sorted()
    }.getOrElse { e ->
        Log.e("StorageRepo", "Erro ao listar imagens para $trainingId", e)
        emptyList()
    }
}