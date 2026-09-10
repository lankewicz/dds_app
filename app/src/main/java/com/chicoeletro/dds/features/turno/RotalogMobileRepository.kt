package com.chicoeletro.dds.features.turno

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.storage.FirebaseStorage
import com.google.firebase.storage.StorageReference
import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import com.google.gson.JsonObject
import kotlinx.coroutines.tasks.await
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Path
import android.content.Context
import java.io.ByteArrayInputStream
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.ConcurrentHashMap
import java.util.zip.GZIPInputStream

data class RotalogMobileService(
    val serviceId: String? = null,
    val type: String? = null,
    val category: String? = null,
    val status: String? = null,
    val startTravel: String? = null,
    val startExecution: String? = null,
    val endExecution: String? = null,
    val returnAt: String? = null,
    val protocol: String? = null,
    val semExecucaoType: String? = null,
    val sequence: String? = null
)

data class RotalogMobileInterval(
    val startAt: String? = null,
    val endAt: String? = null
)
data class RotalogMobileTeam(
    val teamKey: String? = null,
    val date: String? = null,
    val version: Long? = null,
    val updatedAt: String? = null,
    val turnStatus: String? = null,
    val turnoInicio: String? = null,
    val turnoFim: String? = null,
    val intervals: List<RotalogMobileInterval> = emptyList(),
    val service: RotalogMobileService? = null,
    val services: List<RotalogMobileService> = emptyList()
)

private data class RotalogMobileResponse(val ok: Boolean = false, val team: RotalogMobileTeam? = null)

private interface RotalogMobileApi {
    @GET("api/rotalog/mobile/{teamKey}/current")
    suspend fun current(
        @Path("teamKey") teamKey: String,
        @Header("Authorization") authorization: String,
        @Header("If-None-Match") ifNoneMatch: String? = null
    ): Response<RotalogMobileResponse>

    @GET("api/rotalog/mobile/{teamKey}/daily")
    suspend fun dailyRaw(
        @Path("teamKey") teamKey: String,
        @Header("Authorization") authorization: String
    ): Response<ResponseBody>
}

private fun JsonObject.textOrNull(key: String): String? =
    get(key)?.takeUnless { it.isJsonNull }?.asString?.takeIf { it.isNotBlank() }

object RotalogMobileRepository {
    private const val ROTALOG_TEAMS_ROOT = "dados/chicoeletro/rotalog/equipes"
    private const val MAX_TEAM_FILE_BYTES = 5L * 1024 * 1024
    private val etagMap = ConcurrentHashMap<String, String>()

    private val storage: FirebaseStorage by lazy {
        FirebaseStorage.getInstance()
    }

    private fun teamFileRef(relativePath: String): StorageReference =
        storage.reference.child("$ROTALOG_TEAMS_ROOT/$relativePath")

    private val api: RotalogMobileApi by lazy {
        val client = OkHttpClient.Builder()
            .followRedirects(false)
            .followSslRedirects(false)
            .build()

        Retrofit.Builder()
            .baseUrl("https://chicoeletro.web.app/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(RotalogMobileApi::class.java)
    }

    private fun decodeBytesToString(bytes: ByteArray): String {
        if (bytes.size >= 2 && bytes[0] == 0x1f.toByte() && bytes[1] == 0x8b.toByte()) {
            return runCatching {
                GZIPInputStream(ByteArrayInputStream(bytes)).bufferedReader(Charsets.UTF_8).use { it.readText() }
            }.getOrElse { String(bytes, Charsets.UTF_8) }
        }
        return String(bytes, Charsets.UTF_8)
    }

    suspend fun current(teamKey: String): RotalogMobileTeam? {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank()) return null

        // 1. Tenta baixar o arquivo JSON diretamente do Firebase Storage
        val directStorageTeam = fetchTeamFromStorage(normalizedKey, allowCurrentFallback = true)
        if (directStorageTeam != null) {
            return directStorageTeam
        }

        // 2. Fallback: consulta a API HTTP caso o arquivo direto não seja encontrado
        return runCatching {
            val auth = FirebaseAuth.getInstance()
            val user = auth.currentUser ?: auth.signInAnonymously().await().user ?: return null
            val token = user.getIdToken(false).await().token ?: return null
            val currentEtag = etagMap[normalizedKey]

            val response = api.current(normalizedKey, "Bearer $token", currentEtag)
            if (response.code() == 304 || response.code() == 303 || response.code() == 302) {
                return null
            }
            if (response.isSuccessful) {
                val newEtag = response.headers()["ETag"]
                if (!newEtag.isNullOrBlank()) {
                    etagMap[normalizedKey] = newEtag
                }
                return response.body()?.team
            }
            android.util.Log.w("RotalogRepo", "Erro ${response.code()} ao consultar equipe $normalizedKey: ${response.errorBody()?.string()}")
            null
        }.getOrElse { e ->
            android.util.Log.w("RotalogRepo", "Excecao ao consultar equipe $normalizedKey: ${e.message}")
            null
        }
    }
    private suspend fun ensureAuth() {
        runCatching {
            val auth = FirebaseAuth.getInstance()
            if (auth.currentUser == null) {
                auth.signInAnonymously().await()
            }
        }
    }

    private fun getCacheFile(context: Context, teamKey: String, dateIso: String): File {
        val dir = File(context.cacheDir, "rotalog_daily/$teamKey")
        if (!dir.exists()) dir.mkdirs()
        return File(dir, "$dateIso.json")
    }

    fun readLocalCache(context: Context, teamKey: String, dateIso: String): String? {
        return runCatching {
            val file = getCacheFile(context, teamKey, dateIso)
            if (file.exists() && file.length() > 0) {
                file.readText(Charsets.UTF_8)
            } else null
        }.getOrNull()
    }

    fun saveLocalCache(context: Context, teamKey: String, dateIso: String, json: String, hash: String? = null) {
        runCatching {
            val file = getCacheFile(context, teamKey, dateIso)
            file.writeText(json, Charsets.UTF_8)
            if (!hash.isNullOrBlank()) {
                val sp = context.getSharedPreferences("rotalog_cache_meta", Context.MODE_PRIVATE)
                sp.edit().putString("hash__${teamKey}__$dateIso", hash).apply()
            }
        }
    }

    fun getCachedHash(context: Context, teamKey: String, dateIso: String): String? {
        return runCatching {
            val sp = context.getSharedPreferences("rotalog_cache_meta", Context.MODE_PRIVATE)
            sp.getString("hash__${teamKey}__$dateIso", null)
        }.getOrNull()
    }

    fun parseJsonToTeam(rawStr: String, fallbackTeamKey: String, fallbackDate: String): RotalogMobileTeam? {
        return runCatching {
            val parsedObj = runCatching { JsonParser.parseString(rawStr).asJsonObject }.getOrNull() ?: return null

            val currentObj = parsedObj.get("current")?.takeIf { it.isJsonObject }?.asJsonObject
            val turnoObj = parsedObj.get("turno")?.takeIf { it.isJsonObject }?.asJsonObject

            val turnStatus = currentObj?.textOrNull("turnStatus")
                ?: parsedObj.textOrNull("estadoConsolidado")
                ?: turnoObj?.textOrNull("status")

            val version = currentObj?.get("version")?.takeIf { it.isJsonPrimitive }?.asLong
                ?: parsedObj.get("version")?.takeIf { it.isJsonPrimitive }?.asLong
                ?: 1L

            val updatedAt = parsedObj.textOrNull("updatedAt")
                ?: parsedObj.textOrNull("updatedAtIso")

            val turnoInicio = turnoObj?.textOrNull("inicio")
            val turnoFim = turnoObj?.textOrNull("fim")

            val intervalsList = mutableListOf<RotalogMobileInterval>()
            turnoObj?.get("intervalos")?.takeIf { it.isJsonArray }?.asJsonArray?.forEach { element ->
                if (element.isJsonObject) {
                    val interval = element.asJsonObject
                    intervalsList += RotalogMobileInterval(
                        startAt = interval.textOrNull("inicio"),
                        endAt = interval.textOrNull("fim")
                    )
                }
            }

            val serviceObj = currentObj?.get("service")?.takeIf { it.isJsonObject }?.asJsonObject
                ?: parsedObj.get("atividadeAtual")?.takeIf { it.isJsonObject }?.asJsonObject

            val service = serviceObj?.let { s ->
                RotalogMobileService(
                    serviceId = s.textOrNull("serviceId"),
                    type = s.textOrNull("tipo") ?: s.textOrNull("type"),
                    category = s.textOrNull("categoria") ?: s.textOrNull("category"),
                    status = s.textOrNull("statusAtual") ?: s.textOrNull("status"),
                    startTravel = s.textOrNull("inicioDeslocamento") ?: s.textOrNull("startTravel"),
                    startExecution = s.textOrNull("inicioExecucao") ?: s.textOrNull("startExecution"),
                    endExecution = s.textOrNull("fimExecucao") ?: s.textOrNull("termino") ?: s.textOrNull("endExecution"),
                    returnAt = s.textOrNull("retorno") ?: s.textOrNull("returnAt"),
                    protocol = s.textOrNull("protocolo") ?: s.textOrNull("protocol"),
                    semExecucaoType = s.textOrNull("semExecucaoType"),
                    sequence = s.textOrNull("sequencia") ?: s.textOrNull("sequence")
                )
            }

            val servicesList = mutableListOf<RotalogMobileService>()
            val servicesArray = parsedObj.get("services")?.takeIf { it.isJsonArray }?.asJsonArray
            servicesArray?.forEach { elem ->
                if (elem.isJsonObject) {
                    val s = elem.asJsonObject
                    servicesList.add(
                        RotalogMobileService(
                            serviceId = s.textOrNull("serviceId"),
                            type = s.textOrNull("tipo") ?: s.textOrNull("type"),
                            category = s.textOrNull("categoria") ?: s.textOrNull("category"),
                            status = s.textOrNull("statusAtual") ?: s.textOrNull("status"),
                            startTravel = s.textOrNull("inicioDeslocamento") ?: s.textOrNull("startTravel"),
                            startExecution = s.textOrNull("inicioExecucao") ?: s.textOrNull("startExecution"),
                            endExecution = s.textOrNull("fimExecucao") ?: s.textOrNull("termino") ?: s.textOrNull("endExecution"),
                            returnAt = s.textOrNull("retorno") ?: s.textOrNull("returnAt"),
                            protocol = s.textOrNull("protocolo") ?: s.textOrNull("protocol"),
                            semExecucaoType = s.textOrNull("semExecucaoType"),
                            sequence = s.textOrNull("sequencia") ?: s.textOrNull("sequence")
                        )
                    )
                }
            }

            android.util.Log.i("RotalogRepo", "parseJsonToTeam: sucesso para $fallbackTeamKey! services=${servicesList.size}, status=$turnStatus")

            RotalogMobileTeam(
                teamKey = parsedObj.textOrNull("teamKey") ?: fallbackTeamKey,
                date = parsedObj.textOrNull("date") ?: fallbackDate,
                version = version,
                updatedAt = updatedAt,
                turnStatus = turnStatus,
                turnoInicio = turnoInicio,
                turnoFim = turnoFim,
                intervals = intervalsList,
                service = service,
                services = servicesList
            )
        }.onFailure { e ->
            android.util.Log.e("RotalogRepo", "parseJsonToTeam: falha ao parsear JSON: ${e.message}", e)
        }.getOrNull()
    }

    suspend fun fetchDailyWithCache(context: Context, teamKey: String, dateIso: String): RotalogMobileTeam? {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank() || !dateIso.matches(Regex("""\d{4}-\d{2}-\d{2}"""))) return null

        val todayIso = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
        }.format(Date())

        val isToday = (dateIso == todayIso)

        // 1. Dias anteriores: se já estiver em cache local, retorna direto do cache sem chamada de rede
        if (!isToday) {
            val cachedJson = readLocalCache(context, normalizedKey, dateIso)
            if (!cachedJson.isNullOrBlank()) {
                val cachedTeam = parseJsonToTeam(cachedJson, normalizedKey, dateIso)
                if (cachedTeam != null) {
                    return cachedTeam
                }
            }
        }

        // 2. Garante autenticação Firebase para acesso ao Storage
        ensureAuth()

        val dailyRef = teamFileRef("daily/$dateIso/$normalizedKey.json.gz")
        val currentRef = teamFileRef("current/$normalizedKey.json.gz")

        // 3. Se for o dia de hoje: verifica se o hash do arquivo remoto é idêntico
        if (isToday) {
            val cachedHash = getCachedHash(context, normalizedKey, dateIso)
            val cachedJson = readLocalCache(context, normalizedKey, dateIso)

            // Tenta obter metadados para checagem rápida de hash
            val remoteMeta = runCatching { dailyRef.metadata.await() }.getOrNull()
                ?: runCatching { currentRef.metadata.await() }.getOrNull()
            val remoteHash = remoteMeta?.md5Hash ?: remoteMeta?.let { "${it.updatedTimeMillis}_${it.sizeBytes}" }

            // Se o hash bate e o cache local existe, usa o cache local
            if (!cachedJson.isNullOrBlank() && remoteHash != null && cachedHash == remoteHash) {
                val team = parseJsonToTeam(cachedJson, normalizedKey, dateIso)
                if (team != null) {
                    android.util.Log.i("RotalogRepo", "fetchDailyWithCache [$normalizedKey $dateIso]: cache local atualizado por hash ($remoteHash)")
                    return team
                }
            }

            // Baixa diretamente do Storage (dailyRef ou currentRef)
            val downloaded = runCatching {
                val bytes = runCatching { dailyRef.getBytes(MAX_TEAM_FILE_BYTES).await() }
                    .getOrElse { currentRef.getBytes(MAX_TEAM_FILE_BYTES).await() }
                val rawStr = decodeBytesToString(bytes)
                saveLocalCache(context, normalizedKey, dateIso, rawStr, remoteHash)
                android.util.Log.i("RotalogRepo", "fetchDailyWithCache [$normalizedKey $dateIso]: baixado com sucesso do Storage (${bytes.size} bytes)")
                parseJsonToTeam(rawStr, normalizedKey, dateIso)
            }.onFailure { e ->
                android.util.Log.w("RotalogRepo", "fetchDailyWithCache [$normalizedKey $dateIso]: falha no Storage: ${e.message}")
            }.getOrNull()

            if (downloaded != null) return downloaded
        } else {
            // Dia anterior: não encontrado no cache local, baixa do Firebase Storage daily e salva no cache
            val downloaded = runCatching {
                val bytes = dailyRef.getBytes(MAX_TEAM_FILE_BYTES).await()
                val rawStr = decodeBytesToString(bytes)
                val meta = runCatching { dailyRef.metadata.await() }.getOrNull()
                val hash = meta?.md5Hash ?: meta?.updatedTimeMillis?.toString()
                saveLocalCache(context, normalizedKey, dateIso, rawStr, hash)
                android.util.Log.i("RotalogRepo", "fetchDailyWithCache [$normalizedKey $dateIso]: baixado dia anterior do Storage (${bytes.size} bytes)")
                parseJsonToTeam(rawStr, normalizedKey, dateIso)
            }.onFailure { e ->
                android.util.Log.w("RotalogRepo", "fetchDailyWithCache [$normalizedKey $dateIso]: falha no Storage (dia anterior): ${e.message}")
            }.getOrNull()

            if (downloaded != null) return downloaded
        }

        // 4. Fallback: consulta a API HTTP caso o Firebase Storage não tenha o arquivo ou falhe
        return runCatching {
            val auth = FirebaseAuth.getInstance()
            val user = auth.currentUser ?: auth.signInAnonymously().await().user ?: return null
            val token = user.getIdToken(false).await().token ?: return null
            val currentEtag = etagMap[normalizedKey]

            if (isToday) {
                val currentResp = api.current(normalizedKey, "Bearer $token", currentEtag)
                if (currentResp.isSuccessful && currentResp.body()?.team != null) {
                    return currentResp.body()?.team
                }
            }

            val dailyResp = api.dailyRaw(normalizedKey, "Bearer $token")
            if (dailyResp.isSuccessful) {
                val bytes = dailyResp.body()?.bytes()
                if (bytes != null && bytes.isNotEmpty()) {
                    val rawStr = decodeBytesToString(bytes)
                    saveLocalCache(context, normalizedKey, dateIso, rawStr)
                    return parseJsonToTeam(rawStr, normalizedKey, dateIso)
                }
            }

            // Fallback final: usa o cache existente se houver
            val fallbackCache = readLocalCache(context, normalizedKey, dateIso)
            if (!fallbackCache.isNullOrBlank()) {
                parseJsonToTeam(fallbackCache, normalizedKey, dateIso)
            } else null
        }.getOrElse {
            val fallbackCache = readLocalCache(context, normalizedKey, dateIso)
            if (!fallbackCache.isNullOrBlank()) {
                parseJsonToTeam(fallbackCache, normalizedKey, dateIso)
            } else null
        }
    }

    private suspend fun fetchTeamFromStorage(teamKey: String, dateIso: String? = null, allowCurrentFallback: Boolean = false): RotalogMobileTeam? {
        ensureAuth()
        return runCatching {
            val todayIso = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
            }.format(Date())
            val requestedDate = dateIso ?: todayIso

            val dailyRef = teamFileRef("daily/$requestedDate/$teamKey.json.gz")
            android.util.Log.d("RotalogRepo", "fetchTeamFromStorage: tentando ${dailyRef.path}")
            val bytes = runCatching {
                dailyRef.getBytes(MAX_TEAM_FILE_BYTES).await()
            }.onFailure { e ->
                android.util.Log.w("RotalogRepo", "fetchTeamFromStorage: falha nos arquivos daily: ${e.message}")
            }.getOrElse { error ->
                if (!allowCurrentFallback) throw error
                val currentRef = teamFileRef("current/$teamKey.json.gz")
                android.util.Log.d("RotalogRepo", "fetchTeamFromStorage: tentando ${currentRef.path}")
                currentRef.getBytes(MAX_TEAM_FILE_BYTES).await()
            }

            val rawStr = decodeBytesToString(bytes)
            android.util.Log.i("RotalogRepo", "fetchTeamFromStorage: sucesso para $teamKey! bytes=${bytes.size}")
            parseJsonToTeam(rawStr, teamKey, requestedDate)
        }.onFailure { e ->
            android.util.Log.e("RotalogRepo", "fetchTeamFromStorage: falha geral para $teamKey: ${e.message}", e)
        }.getOrNull()
    }

    suspend fun daily(teamKey: String, dateIso: String, context: Context? = null): RotalogMobileTeam? {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank() || !dateIso.matches(Regex("""\d{4}-\d{2}-\d{2}"""))) return null
        if (context != null) {
            return fetchDailyWithCache(context, normalizedKey, dateIso)
        }
        return fetchTeamFromStorage(normalizedKey, dateIso = dateIso, allowCurrentFallback = true)
    }

    suspend fun fetchDailyDebugJson(teamKey: String): String {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank()) return "{\n  \"erro\": \"Equipe em branco\"\n}"

        val prettyGson = GsonBuilder().setPrettyPrinting().create()
        val todayIso = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

        // 1. Tenta o repositório permanente.
        val directStorageResult = runCatching {
            val bytes = teamFileRef("daily/$todayIso/$normalizedKey.json.gz")
                .getBytes(MAX_TEAM_FILE_BYTES).await()
            val rawStr = decodeBytesToString(bytes)
            val parsed = runCatching { JsonParser.parseString(rawStr) }.getOrNull()
            if (parsed != null) prettyGson.toJson(parsed) else rawStr
        }.getOrNull()

        if (!directStorageResult.isNullOrBlank()) {
            return directStorageResult
        }

        // 1b. Tenta baixar do Storage o arquivo current.
        val currentStorageResult = runCatching {
            val bytes = teamFileRef("current/$normalizedKey.json.gz")
                .getBytes(MAX_TEAM_FILE_BYTES).await()
            val rawStr = decodeBytesToString(bytes)
            val parsed = runCatching { JsonParser.parseString(rawStr) }.getOrNull()
            if (parsed != null) prettyGson.toJson(parsed) else rawStr
        }.getOrNull()

        if (!currentStorageResult.isNullOrBlank()) {
            return currentStorageResult
        }

        // 2. Fallback: Se não encontrar no Storage, tenta a API HTTP
        return runCatching {
            val auth = FirebaseAuth.getInstance()
            var user = auth.currentUser
            if (user == null) {
                user = auth.signInAnonymously().await().user
            }
            if (user == null) {
                return prettyGson.toJson(mapOf("erro" to "Falha na autenticação Firebase (usuário nulo)"))
            }
            val tokenResult = user.getIdToken(false).await()
            val token = tokenResult.token
                ?: return prettyGson.toJson(mapOf("erro" to "Falha ao obter Token ID do Firebase"))

            val response = api.dailyRaw(normalizedKey, "Bearer $token")
            if (response.isSuccessful) {
                val bytes = response.body()?.bytes()
                if (bytes != null && bytes.isNotEmpty()) {
                    val rawStr = decodeBytesToString(bytes)
                    val parsed = runCatching { JsonParser.parseString(rawStr) }.getOrNull()
                    if (parsed != null) {
                        return prettyGson.toJson(parsed)
                    }
                    return rawStr
                }
            }

            val currentResp = api.current(normalizedKey, "Bearer $token")
            if (currentResp.isSuccessful) {
                val teamObj = currentResp.body()?.team
                if (teamObj != null) {
                    return prettyGson.toJson(
                        mapOf(
                            "origem" to "/api/rotalog/mobile/$normalizedKey/current",
                            "status_http" to 200,
                            "dados" to teamObj
                        )
                    )
                }
            } else {
                val errStr = currentResp.errorBody()?.string() ?: ""
                return prettyGson.toJson(
                    mapOf(
                        "origem" to "/api/rotalog/mobile/$normalizedKey/current",
                        "status_http" to currentResp.code(),
                        "mensagem" to errStr,
                        "equipe" to normalizedKey
                    )
                )
            }

            prettyGson.toJson(mapOf("erro" to "Dados não encontrados para a equipe $normalizedKey"))
        }.getOrElse { ex ->
            prettyGson.toJson(
                mapOf(
                    "excecao" to (ex.javaClass.simpleName ?: "Exception"),
                    "mensagem" to (ex.message ?: "Erro desconhecido ao consultar API"),
                    "equipe" to normalizedKey
                )
            )
        }
    }
}
