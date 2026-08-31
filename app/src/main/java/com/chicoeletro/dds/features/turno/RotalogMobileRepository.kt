package com.chicoeletro.dds.features.turno

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.storage.FirebaseStorage
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
import java.io.ByteArrayInputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
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
    val protocol: String? = null
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
    private val etagMap = ConcurrentHashMap<String, String>()

    private val storage: FirebaseStorage by lazy {
        FirebaseStorage.getInstance("gs://dds-treinamentos.firebasestorage.app")
    }

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

    private suspend fun fetchTeamFromStorage(teamKey: String, dateIso: String? = null, allowCurrentFallback: Boolean = false): RotalogMobileTeam? {
        return runCatching {
            val requestedDate = dateIso ?: SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

            val dailyRef = storage.reference.child("_cache/rotalog/teams/daily/$requestedDate/$teamKey.json.gz")
            val bytes = runCatching {
                dailyRef.getBytes(5 * 1024 * 1024).await()
            }.getOrElse { error ->
                if (!allowCurrentFallback) throw error
                val currentRef = storage.reference.child("_cache/rotalog/teams/current/$teamKey.json.gz")
                currentRef.getBytes(5 * 1024 * 1024).await()
            }

            val rawStr = decodeBytesToString(bytes)
            val parsedObj = runCatching { JsonParser.parseString(rawStr).asJsonObject }.getOrNull() ?: return null

            val currentObj = parsedObj.getAsJsonObject("current")
            val turnStatus = currentObj?.get("turnStatus")?.asString
                ?: parsedObj.get("estadoConsolidado")?.asString
                ?: parsedObj.getAsJsonObject("turno")?.get("status")?.asString

            val version = currentObj?.get("version")?.asLong
                ?: parsedObj.get("version")?.asLong
                ?: 1L

            val updatedAt = parsedObj.get("updatedAt")?.asString
                ?: parsedObj.get("updatedAtIso")?.asString

            val turnoObj = parsedObj.getAsJsonObject("turno")
            val turnoInicio = turnoObj?.textOrNull("inicio")
            val turnoFim = turnoObj?.textOrNull("fim")

            val intervalsList = mutableListOf<RotalogMobileInterval>()
            turnoObj?.getAsJsonArray("intervalos")?.forEach { element ->
                if (element.isJsonObject) {
                    val interval = element.asJsonObject
                    intervalsList += RotalogMobileInterval(
                        startAt = interval.textOrNull("inicio"),
                        endAt = interval.textOrNull("fim")
                    )
                }
            }

            val serviceObj = currentObj?.getAsJsonObject("service")
                ?: parsedObj.getAsJsonObject("atividadeAtual")

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
                    protocol = s.textOrNull("protocolo") ?: s.textOrNull("protocol")
                )
            }

            val servicesList = mutableListOf<RotalogMobileService>()
            val servicesArray = parsedObj.getAsJsonArray("services")
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
                            protocol = s.textOrNull("protocolo") ?: s.textOrNull("protocol")
                        )
                    )
                }
            }

            RotalogMobileTeam(
                teamKey = teamKey,
                date = parsedObj.textOrNull("date") ?: requestedDate,
                version = version,
                updatedAt = updatedAt,
                turnStatus = turnStatus,
                turnoInicio = turnoInicio,
                turnoFim = turnoFim,
                intervals = intervalsList,
                service = service,
                services = servicesList
            )
        }.getOrNull()
    }


    suspend fun daily(teamKey: String, dateIso: String): RotalogMobileTeam? {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank() || !dateIso.matches(Regex("""\d{4}-\d{2}-\d{2}"""))) return null
        return fetchTeamFromStorage(normalizedKey, dateIso = dateIso, allowCurrentFallback = false)
    }
    suspend fun fetchDailyDebugJson(teamKey: String): String {
        val normalizedKey = teamKey.trim().uppercase()
        if (normalizedKey.isBlank()) return "{\n  \"erro\": \"Equipe em branco\"\n}"

        val prettyGson = GsonBuilder().setPrettyPrinting().create()
        val todayIso = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

        // 1. Tenta baixar diretamente do Storage (_cache/rotalog/teams/daily/YYYY-MM-DD/EQUIPE.json.gz)
        val directStorageResult = runCatching {
            val dailyRef = storage.reference.child("_cache/rotalog/teams/daily/$todayIso/$normalizedKey.json.gz")
            val bytes = dailyRef.getBytes(5 * 1024 * 1024).await()
            val rawStr = decodeBytesToString(bytes)
            val parsed = runCatching { JsonParser.parseString(rawStr) }.getOrNull()
            if (parsed != null) prettyGson.toJson(parsed) else rawStr
        }.getOrNull()

        if (!directStorageResult.isNullOrBlank()) {
            return directStorageResult
        }

        // 1b. Tenta baixar do Storage o arquivo current (_cache/rotalog/teams/current/EQUIPE.json.gz)
        val currentStorageResult = runCatching {
            val currentRef = storage.reference.child("_cache/rotalog/teams/current/$normalizedKey.json.gz")
            val bytes = currentRef.getBytes(5 * 1024 * 1024).await()
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
