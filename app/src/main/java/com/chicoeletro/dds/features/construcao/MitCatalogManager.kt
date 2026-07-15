// Módulo: app/src/main/java/com/chicoeletro/dds/features/construcao/MitCatalogManager.kt
// Função: Gerenciador de catálogo de atividades do MIT para download e uso offline nos tablets.
// Tecnologias: Firebase Storage, Kotlin Coroutines, kotlinx.serialization.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.construcao

import android.content.Context
import android.util.Log
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.tasks.await
import kotlinx.serialization.json.Json
import java.io.File

object MitCatalogManager {
    private const val TAG = "MitCatalogManager"

    // Configuração para ignorar chaves desconhecidas do JSON de forma tolerante
    private val jsonConfig = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
    }

    /**
     * Determina o nome do arquivo no Firebase Storage com base no tipo da equipe.
     */
    fun getStoragePathForTeamType(teamType: String): String {
        val type = teamType.uppercase().trim()
        return when {
            type == "CONSTRUCAO" -> "catalogo/catalogo_mit_construcao.json"
            type == "STC" || type == "STC_CESTO" -> "catalogo/catalogo_mit_stc.json"
            // EP, LINHA_VIVA, ROCADA utilizam o manual de manutenção unificado
            else -> "catalogo/catalogo_mit_manutencao.json"
        }
    }

    /**
     * Retorna a referência do arquivo local no dispositivo.
     */
    fun getLocalFile(context: Context, teamType: String): File {
        val storagePath = getStoragePathForTeamType(teamType)
        val fileName = storagePath.substringAfterLast("/")
        return File(context.filesDir, fileName)
    }

    /**
     * Realiza o download do arquivo JSON do Firebase Storage se estiver online.
     */
    suspend fun downloadCatalog(context: Context, teamType: String): Boolean {
        return try {
            val storagePath = getStoragePathForTeamType(teamType)
            val localFile = getLocalFile(context, teamType)
            
            Log.i(TAG, "Iniciando download do catalogo para equipe $teamType de '$storagePath'...")
            
            val storage = FirebaseStorage.getInstance()
            val ref = storage.reference.child(storagePath)
            
            // Garante que o diretório pai existe
            localFile.parentFile?.mkdirs()
            
            ref.getFile(localFile).await()
            Log.i(TAG, "Download concluído com sucesso. Salvo em: ${localFile.absolutePath}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Falha ao baixar catalogo do Storage para equipe $teamType: ${e.message}", e)
            false
        }
    }

    /**
     * Carrega as atividades do arquivo local.
     */
    fun loadLocalCatalog(context: Context, teamType: String): List<Atividade> {
        val localFile = getLocalFile(context, teamType)
        if (!localFile.exists()) {
            Log.w(TAG, "Arquivo local de catalogo nao encontrado em: ${localFile.absolutePath}")
            return emptyList()
        }

        return try {
            val jsonString = localFile.readText(Charsets.UTF_8)
            jsonConfig.decodeFromString<List<Atividade>>(jsonString)
        } catch (e: Exception) {
            Log.e(TAG, "Erro ao decodificar catalogo local para equipe $teamType: ${e.message}", e)
            emptyList()
        }
    }
}
