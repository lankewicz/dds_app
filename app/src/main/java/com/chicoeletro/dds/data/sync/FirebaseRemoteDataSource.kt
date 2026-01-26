// Módulo: app/src/main/java/com/chicoeletro/dds/data/sync/FirebaseRemoteDataSource.kt
// Descrição: Implementa ContentRemoteDataSource usando Firestore e Firebase Storage.
// Correção: conversão de items (List<Map<String, Any?>>) → List<ManifestItem>; logs de depuração.
// Atualizado: 10/11/2025

package com.chicoeletro.dds.data.sync

import android.content.Context
import android.util.Log
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale

class FirebaseRemoteDataSource(
    private val firestore: FirebaseFirestore,
    private val storage: FirebaseStorage,
    private val context: Context
) : ContentRemoteDataSource {

    private var cachedList: Pair<Long, String>? = null
    private val LIST_TTL_MS = 60_000L  // 1 min (ajuste)

    // ------------------------------------------------------------
    // Helpers de caminho relativo (preserva subpastas após o trainingId)
    // Ex.: "DDSv2/2025-11-10 - TÍTULO/sub/Slide4.JPG" -> "sub/Slide4.JPG"
    private fun computeRelativeLocalPath(originalPath: String, trainingId: String): String {
        val norm = originalPath.replace('\\','/')
        val i = norm.lowercase().indexOf(trainingId.lowercase())
        val rel = if (i >= 0) norm.substring(i + trainingId.length) else norm.substringAfterLast('/')
        return rel.trimStart('/')
    }

    /** Exposto para quem quiser reutilizar fora (UseCase/UI). */
    fun relativeLocalPathFor(originalPath: String, trainingId: String): String =
        computeRelativeLocalPath(originalPath, trainingId)



    // ---------------- Manifest ----------------
    override suspend fun fetchManifest(): List<ManifestItem> {
        val fs = runCatching { fetchManifestFromFirestore() }.getOrNull()
        if (!fs.isNullOrEmpty()) return fs
        return fetchManifestFromListJson()
    }

    private suspend fun fetchManifestFromFirestore(): List<ManifestItem> {
        val snap = firestore.collection("manifests").document("latest").get().await()
        @Suppress("UNCHECKED_CAST")
        val raw = snap.get("items") as? List<Map<String, Any?>> ?: emptyList()
        val items = raw.mapNotNull { m ->
            val id  = (m["id"] as? String)?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val url = (m["url"] as? String)?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val ver = when (val v = m["version"]) {
                is Number -> v.toLong()
                is String -> v.toLongOrNull() ?: 0L
                else -> 0L
            }
            val hash = (m["hash"] as? String).orEmpty()
            ManifestItem(id = id, version = ver, url = url, hash = hash)
        }
        Log.d("RemoteDS", "fetchManifest(Firestore): ${items.size} itens")
        return items
    }

    private suspend fun fetchManifestFromListJson(): List<ManifestItem> {
        val url = "gs://"+storage.reference.bucket+"/DDSv2/lista.json"
        val json = getListJson(url)
        val ids = parseAllPaths(json).mapNotNull { extractTrainingId(it) }.toSet().sorted()
        return ids.map { id -> ManifestItem(id = id, version = 0, url = url, hash = "") }
    }

    // ---------------- Baixa “em lote” (modo legado) ----------------
    override suspend fun downloadAndSave(item: ManifestItem) {
        val destDir = File(context.filesDir, "trainings/${item.id}")
        if (!destDir.exists()) destDir.mkdirs()

        val isJson = item.url.substringAfterLast('/').endsWith(".json", true)
        if (!isJson) {
            // raro no nosso fluxo, mas garanta subpasta se vier caminho
            val rel = computeRelativeLocalPath(item.url, item.id)
            val out = File(destDir, rel).apply { parentFile?.mkdirs() }
            storage.getReferenceFromUrl(item.url).getFile(out).await()
            return
        }

        val json = getListJson(item.url)
        val imgs = parseAllPaths(json).filter { pathMatchesTraining(it, item.id) }
        Log.d("RemoteDS", "LISTA contém ${imgs.size} imagens para '${item.id}' (modo legado)")

        imgs.forEach { p -> downloadImageForTraining(p, item.id, destDir) }
    }

    // ---------------- Novos utilitários p/ progress ----------------

    /** Lista todas as imagens de um treinamento (a partir do DDSv2/lista.json em cache). */
    suspend fun listImagesFor(trainingId: String): List<String> {
        val url = "gs://${storage.reference.bucket}/DDSv2/lista.json"
        val json = getListJson(url)
        return parseAllPaths(json).filter { full ->
            // Normaliza e pega o segmento logo após DDSv2/
            val norm = full.replace('\\','/').removePrefix("gs://").removePrefix("https://")
            val path = norm.substringAfter('/', norm)          // tira "bucket/"
            val afterDDS = path.substringAfter("DDSv2/", path)
            val firstSeg = afterDDS.substringBefore('/')
            firstSeg.equals(trainingId, ignoreCase = true)
        }
    }

    /**
    * Baixa UMA imagem (tenta com 'DDSv2/', sem prefixo, e a partir do próprio trainingId).
    * Salva em destDir **preservando subpastas** após o trainingId.
    * Retorna true se conseguiu salvar.
    */

    suspend fun downloadImageForTraining(originalPath: String, trainingId: String, destDir: File): Boolean {
        val candidates = candidatePaths(originalPath, trainingId)
        val rel = computeRelativeLocalPath(originalPath, trainingId)   // ← "sub/Slide4.JPG" ou "Slide4.JPG"
        val outFile = File(destDir, rel).apply { parentFile?.mkdirs() }
        for (p in candidates) {
            try {
                val ref = if (p.startsWith("gs://") || p.startsWith("https://"))
                    storage.getReferenceFromUrl(p) else storage.getReference(p)
                Log.d("RemoteDS", "Tentando: $p → ${outFile.invariantSeparatorsPath}")
                ref.getFile(outFile).await()
                Log.d("RemoteDS", "OK: $p")
                return true
            } catch (e: Exception) {
                Log.w("RemoteDS", "Falha '$p' ($trainingId): ${e.message}")
            }
        }
        Log.e("RemoteDS", "Desisti do arquivo: $originalPath")
        return false
    }

    // ---------------- Cache do lista.json + parsing ----------------
    private suspend fun getListJson(url: String): String {
        val now = System.currentTimeMillis()
        cachedList?.let { (ts, txt) ->
            if (now - ts < LIST_TTL_MS) return txt
        }
        val bytes = try {
            storage.getReferenceFromUrl(url).getBytes(10L * 1024 * 1024).await()
        } catch (_: Exception) {
            storage.getReference("DDSv2/lista.json").getBytes(10L * 1024 * 1024).await()
        }
        return bytes.toString(Charsets.UTF_8).also { cachedList = now to it }
    }

    private fun parseAllPaths(json: String): List<String> {
        runCatching {
            val arr = JSONArray(json)
            return (0 until arr.length()).mapNotNull { arr.optString(it, null) }.filter { it.isNotBlank() }
        }
        val obj = runCatching { JSONObject(json) }.getOrNull() ?: return emptyList()
        val keys = listOf("files", "imagens", "urls", "items", "pictures", "fotos", "arquivos")
        for (k in keys) obj.opt(k)?.let { any -> parsePathsFromAny(any)?.let { return it } }
        return buildList {
            if (obj.has("url")) add(obj.optString("url"))
            if (obj.has("path")) add(obj.optString("path"))
        }
    }

    private fun parsePathsFromAny(any: Any?): List<String>? = when (any) {
        is JSONArray -> buildList {
            for (i in 0 until any.length()) when (val el = any.opt(i)) {
                is String -> if (el.isNotBlank()) add(el)
                is JSONObject -> {
                    val u = when {
                        el.has("url")  -> el.optString("url")
                        el.has("path") -> el.optString("path")
                        else -> null
                    }
                    if (!u.isNullOrBlank()) add(u)
                }
            }
        }
        is JSONObject -> when {
            any.has("url")  -> listOfNotNull(any.optString("url"))
            any.has("path") -> listOfNotNull(any.optString("path"))
            else -> {
                val keys = listOf("files", "imagens", "urls", "items", "pictures", "fotos", "arquivos")
                keys.firstNotNullOfOrNull { k -> parsePathsFromAny(any.opt(k)) }
            }
        }
        else -> null
    }

    private fun extractTrainingId(path: String): String? {
        val p = path.removePrefix("gs://").removePrefix("https://").trimStart('/')
        val noBucket = if (p.contains("/")) p.substringAfter('/') else p
        val withoutDDS = noBucket.removePrefix("DDSv2/").removePrefix("DDS/")
        return withoutDDS.substringBefore('/', "").takeIf { it.isNotBlank() }
    }

    private fun pathMatchesTraining(path: String, trainingId: String): Boolean {
        if (path.isBlank()) return false
        return path.lowercase(Locale.ROOT).contains(trainingId.lowercase(Locale.ROOT))
    }

    private fun candidatePaths(original: String, trainingId: String): List<String> {
        val p0 = original.trim().trimStart('/')
        val out = mutableListOf<String>()
        out += p0
        if (p0.startsWith("DDSv2/", true)) out += p0.removePrefix("DDSv2/")
        if (p0.startsWith("DDS/",   true)) out += p0.removePrefix("DDS/")
        val idx = p0.indexOf(trainingId)
        if (idx >= 0) out += p0.substring(idx)
        return out.distinct()
    }
}
