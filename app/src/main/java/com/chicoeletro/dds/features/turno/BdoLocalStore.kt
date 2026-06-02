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

enum class SsStatus {
    DESLOCAMENTO,
    EXECUCAO,
    CONCLUSAO,
    CANCELADO
}

data class SsTransition(
    val status: SsStatus,
    val timestampMs: Long,
    val km: Long? = null
)

data class BdoSs(
    val ssId: String,
    val status: SsStatus,
    val transitions: List<SsTransition> = emptyList(),
    val cancelReason: String? = null
) {
    fun getTransitionTime(st: SsStatus): String {
        val trans = transitions.find { it.status == st } ?: return ""
        return SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR")).format(Date(trans.timestampMs))
    }
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
            if (ss.cancelReason != null) {
                o.put("cancelReason", ss.cancelReason)
            }
            
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
                add(BdoSs(ssId, status, trans, cancelReason))
            }
        }
    }
}
