// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/BdoLocalStore.kt
// Função: Armazenamento local das solicitações de serviço (SS) vinculadas ao Boletim Diário de Obra (BDO) integrado com estados de turno.
// Tecnologias: Android SharedPreferences, JSON.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.turno

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

enum class SsStatus {
    DESLOCAMENTO,
    EXECUCAO,
    CONCLUSAO,
    CANCELADO
}

data class SsTransition(
    val status: SsStatus = SsStatus.DESLOCAMENTO,
    val timestampMs: Long = 0L,
    val km: Long? = null
)

data class BdoSs(
    val ssId: String = "",
    val status: SsStatus = SsStatus.DESLOCAMENTO,
    val transitions: List<SsTransition> = emptyList(),
    val cancelReason: String? = null,
    val remoteServiceId: String? = null,
    val serviceType: String? = null,
    val protocol: String? = null,
    val category: String? = null,
    val rawStatus: String? = null
) {
    fun getTransitionTime(st: SsStatus): String {
        val trans = transitions.find { it.status == st }
            ?: (if (st == SsStatus.CONCLUSAO) transitions.find { it.status == SsStatus.CANCELADO } else null)
            ?: return ""
        val sdf = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).apply {
            timeZone = TimeZone.getTimeZone("America/Sao_Paulo")
        }
        return sdf.format(Date(trans.timestampMs))
    }
}

fun parseIsoToMs(isoStr: String?): Long {
    if (isoStr.isNullOrBlank()) return 0L
    return runCatching {
        val normalized = isoStr.trim().let {
            if (it.endsWith("Z") || Regex("[+-]\\d{2}:\\d{2}$").containsMatchIn(it)) it else "${it}Z"
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            try {
                java.time.OffsetDateTime.parse(normalized).toInstant().toEpochMilli()
            } catch (e: Exception) {
                java.time.Instant.parse(normalized.replace(Regex("\\+\\d{2}:\\d{2}$"), "Z")).toEpochMilli()
            }
        } else {
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).parse(normalized)?.time ?: 0L
        }
    }.getOrElse { 0L }
}

fun RotalogMobileTeam.toBdoSsList(): List<BdoSs> {
    val allServices = mutableListOf<RotalogMobileService>()
    allServices.addAll(services)
    if (service != null && services.none { it.serviceId == service.serviceId }) {
        allServices.add(service)
    }
    return allServices.mapNotNull { s ->
        val identifier = s.serviceId?.takeIf { it.isNotBlank() }
            ?: s.protocol?.takeIf { it.isNotBlank() }
            ?: s.type?.takeIf { it.isNotBlank() }
            ?: return@mapNotNull null

        val statusRaw = s.status?.trim()?.uppercase()
        val semExec = s.semExecucaoType?.trim()
        val isCancelledOrRelocated = when (statusRaw) {
            "RELOCADO", "RETIRADO PELO COD", "REDIRECIONADO", "CANCELADO", "DESLOCAMENTO CANCELADO" -> true
            else -> !semExec.isNullOrBlank()
        }

        val transitions = mutableListOf<SsTransition>()
        val travelMs = parseIsoToMs(s.startTravel)
        if (travelMs > 0) transitions.add(SsTransition(SsStatus.DESLOCAMENTO, travelMs))

        val execMs = parseIsoToMs(s.startExecution)
        if (execMs > 0) transitions.add(SsTransition(SsStatus.EXECUCAO, execMs))

        val endMs = parseIsoToMs(s.endExecution).takeIf { it > 0 } ?: parseIsoToMs(s.returnAt)
        if (endMs > 0) {
            val finalStatus = if (isCancelledOrRelocated) SsStatus.CANCELADO else SsStatus.CONCLUSAO
            transitions.add(SsTransition(finalStatus, endMs))
        }

        val statusEnum = when {
            isCancelledOrRelocated -> SsStatus.CANCELADO
            statusRaw in listOf("CONCLUSAO", "CONCLUÍDO", "FINALIZADO") -> SsStatus.CONCLUSAO
            statusRaw in listOf("EXECUCAO", "EXECUÇÃO", "EM EXECUÇÃO") -> SsStatus.EXECUCAO
            statusRaw in listOf("DESLOCAMENTO", "EM DESLOCAMENTO") -> SsStatus.DESLOCAMENTO
            endMs > 0 -> SsStatus.CONCLUSAO
            execMs > 0 -> SsStatus.EXECUCAO
            travelMs > 0 -> SsStatus.DESLOCAMENTO
            else -> SsStatus.DESLOCAMENTO
        }

        val cancelReason = if (isCancelledOrRelocated) {
            semExec?.takeIf { it.isNotBlank() } ?: s.status
        } else null

        BdoSs(
            ssId = identifier,
            status = statusEnum,
            transitions = transitions,
            cancelReason = cancelReason,
            remoteServiceId = s.serviceId?.takeIf { it.isNotBlank() },
            serviceType = s.type?.takeIf { it.isNotBlank() },
            protocol = s.protocol?.takeIf { it.isNotBlank() },
            category = s.category?.takeIf { it.isNotBlank() },
            rawStatus = s.status
        )
    }
}

fun mergeBdoServices(local: List<BdoSs>, remote: List<BdoSs>): List<BdoSs> {
    if (remote.isEmpty()) return local
    val merged = local.toMutableList()
    remote.forEach { incoming ->
        val index = merged.indexOfFirst { existing ->
            (!incoming.remoteServiceId.isNullOrBlank() &&
                existing.remoteServiceId.equals(incoming.remoteServiceId, ignoreCase = true)) ||
                existing.ssId.equals(incoming.ssId, ignoreCase = true)
        }
        if (index < 0) {
            merged += incoming
        } else {
            val existing = merged[index]
            merged[index] = incoming.copy(
                cancelReason = existing.cancelReason ?: incoming.cancelReason,
                remoteServiceId = incoming.remoteServiceId ?: existing.remoteServiceId,
                rawStatus = incoming.rawStatus ?: existing.rawStatus,
                category = incoming.category ?: existing.category
            )
        }
    }
    return merged.sortedBy { it.transitions.firstOrNull()?.timestampMs ?: Long.MAX_VALUE }
}

object BdoLocalStore {
    private const val PREFS = "dds_bdo"
    
    private fun key(team: String, dateStr: String) = "bdo__${team.trim().lowercase()}__$dateStr"
    
    private fun getCurrentDateStr(): String {
        return SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }
    
    fun loadToday(context: Context, team: String): List<BdoSs> {
        val dateStr = getCurrentDateStr()
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = sp.getString(key(team, dateStr), null) ?: return emptyList()
        return runCatching { fromJson(raw) }.getOrElse { emptyList() }
    }
    
    fun saveToday(context: Context, team: String, list: List<BdoSs>) {
        val dateStr = getCurrentDateStr()
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        sp.edit().putString(key(team, dateStr), toJson(list)).apply()
    }
    
    private fun toJson(list: List<BdoSs>): String {
        val arr = JSONArray()
        list.forEach { ss ->
            val o = JSONObject()
            o.put("ssId", ss.ssId)
            o.put("status", ss.status.name)
            if (ss.remoteServiceId != null) o.put("remoteServiceId", ss.remoteServiceId)
            if (ss.serviceType != null) o.put("serviceType", ss.serviceType)
            if (ss.protocol != null) o.put("protocol", ss.protocol)
            if (ss.category != null) o.put("category", ss.category)
            if (ss.cancelReason != null) {
                o.put("cancelReason", ss.cancelReason)
            }
            if (ss.rawStatus != null) o.put("rawStatus", ss.rawStatus)
            
            val transArr = JSONArray()
            ss.transitions.forEach { t ->
                val to = JSONObject()
                to.put("status", t.status.name)
                to.put("timestampMs", t.timestampMs)
                if (t.km != null) {
                    to.put("km", t.km)
                }
                transArr.put(to)
            }
            o.put("transitions", transArr)
            arr.put(o)
        }
        return arr.toString()
    }
    
    private fun fromJson(raw: String): List<BdoSs> {
        val arr = JSONArray(raw)
        return buildList {
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                val ssId = o.getString("ssId")
                val status = SsStatus.valueOf(o.getString("status"))
                val cancelReason = if (o.has("cancelReason")) o.getString("cancelReason") else null
                val remoteServiceId = o.optString("remoteServiceId").takeIf { it.isNotBlank() }
                val serviceType = o.optString("serviceType").takeIf { it.isNotBlank() }
                val protocol = o.optString("protocol").takeIf { it.isNotBlank() }
                val category = o.optString("category").takeIf { it.isNotBlank() }
                val rawStatus = o.optString("rawStatus").takeIf { it.isNotBlank() }
                
                val transArr = o.optJSONArray("transitions") ?: JSONArray()
                val trans = buildList {
                    for (j in 0 until transArr.length()) {
                        val to = transArr.getJSONObject(j)
                        val kmVal = if (to.has("km") && !to.isNull("km")) to.getLong("km") else null
                        add(
                            SsTransition(
                                status = SsStatus.valueOf(to.getString("status")),
                                timestampMs = to.getLong("timestampMs"),
                                km = kmVal
                            )
                        )
                    }
                }
                add(BdoSs(ssId, status, trans, cancelReason, remoteServiceId, serviceType, protocol, category, rawStatus))
            }
        }
    }
}
