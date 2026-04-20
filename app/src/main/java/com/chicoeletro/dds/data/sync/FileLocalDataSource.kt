// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/FileLocalDataSource.kt
// Função: Gerenciador de armazenamento físico dos binários de treinamento (PDF/Imagens). 
//         Responsável por salvar conteúdo baixado e verificar arquivos no disco interno.
// Tecnologias: Java File API, Context.filesDir.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.data.sync

import android.content.Context
import java.io.File

class FileLocalDataSource(
    private val context: Context
) : ContentLocalDataSource {
    fun trainingRoot(): File = File(context.filesDir, "trainings")
    fun trainingDir(id: String): File = File(trainingRoot(), id)

    /**
     * Remove do armazenamento local qualquer treinamento que não esteja no conjunto "keepIds".
     * Usado para retenção (ex: manter 5 últimos + atual + 5 próximos).
     */
    fun purgeTrainingsNotIn(keepIds: Set<String>) {
        val root = trainingRoot()
        if (!root.exists()) return

        root.listFiles()
            ?.filter { it.isDirectory && !it.name.startsWith(".") }
            ?.forEach { dir ->
                if (dir.name !in keepIds) {
                    dir.deleteRecursively()
                }
            }
    }

    override suspend fun getPendingItems(remoteManifest: List<ManifestItem>): List<ManifestItem> {
        // Delegate to DataStoreLocalDataSource for manifest diff
        return DataStoreLocalDataSource(context).getPendingItems(remoteManifest)
    }

    override suspend fun saveManifest(remoteManifest: List<ManifestItem>) {
        // Delegate manifest persistence
        DataStoreLocalDataSource(context).saveManifest(remoteManifest)
    }
}