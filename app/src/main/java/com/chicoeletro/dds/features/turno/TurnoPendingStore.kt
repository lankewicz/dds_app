// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoPendingStore.kt
// Função: Fila de upload para registros de turno offline. Armazena turnos fechados sem 
//         conectividade para sincronização automática posterior.
// Tecnologias: Jetpack DataStore, Kotlinx Serialization.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object TurnoPendingStore {
    private const val PREFS = "dds_turno_pending"
    private const val KEY = "queue"

    fun enqueue(context: Context, item: TurnoEventRemote) {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val arr = JSONArray(sp.getString(KEY, "[]") ?: "[]")
        arr.put(toJson(item))
        sp.edit().putString(KEY, arr.toString()).apply()
    }

    fun peekAll(context: Context): List<TurnoEventRemote> {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val arr = JSONArray(sp.getString(KEY, "[]") ?: "[]")
        val out = mutableListOf<TurnoEventRemote>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            runCatching { out.add(fromJson(o)) }
        }
        return out
    }

    fun removeByEventId(context: Context, eventId: String) {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val arr = JSONArray(sp.getString(KEY, "[]") ?: "[]")
        val newArr = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("eventId") != eventId) newArr.put(o)
        }
        sp.edit().putString(KEY, newArr.toString()).apply()
    }

    // ---------------- JSON ----------------

    private fun toJson(ev: TurnoEventRemote): JSONObject = JSONObject().apply {
        put("empresa", ev.empresa)
        put("equipe", ev.equipe)
        put("turnoId", ev.turnoId)
        put("eventId", ev.eventId)
        put("occurredAtClientMs", ev.occurredAtClientMs)
        put("clientCreatedAtIso", ev.clientCreatedAtIso)

        put("from", ev.from)
        put("to", ev.to)

        putOptInt("km4", ev.km4)
        putOptInt("kmInicioTurno4", ev.kmInicioTurno4)
        putOptInt("kmDeltaTurno", ev.kmDeltaTurno)

        putOptString("nocSs", ev.nocSs)
        putOptString("motivo", ev.motivo)
        putOptString("motivoOutro", ev.motivoOutro)

        val m = JSONArray()
        (ev.membersSnapshot ?: emptyList()).forEach { m.put(it) }
        put("membersSnapshot", m)

        put("photoRequired", ev.photoAudit.required)
        putOptString("photoId", ev.photoAudit.photoId)
        putOptString("storagePath", ev.photoAudit.storagePath)
        putOptString("thumbPath", ev.photoAudit.thumbPath)

        put("actorDeviceId", ev.actor.deviceId)
        put("actorDeviceModel", ev.actor.deviceModel)
        put("actorAppVersion", ev.actor.appVersion)
    }

    private fun fromJson(o: JSONObject): TurnoEventRemote {
        fun optStringOrNull(key: String): String? =
            if (!o.has(key) || o.isNull(key)) null else o.optString(key).trim().ifEmpty { null }

        fun optIntOrNull(key: String): Int? =
            if (!o.has(key) || o.isNull(key)) null else o.optInt(key)

        val empresa = o.optString("empresa")
        val equipe = o.optString("equipe")
        val turnoId = o.optString("turnoId")
        val eventId = o.optString("eventId")
        val occurredAtMs = if (o.has("occurredAtClientMs") && !o.isNull("occurredAtClientMs")) o.optLong("occurredAtClientMs") else 0L
        val clientIso = o.optString("clientCreatedAtIso")

        val from = o.optString("from")
        val to = o.optString("to")

        val km4 = optIntOrNull("km4")
        val kmIni = optIntOrNull("kmInicioTurno4")
        val kmDelta = optIntOrNull("kmDeltaTurno")

        val nocSs = optStringOrNull("nocSs")
        val motivo = optStringOrNull("motivo")
        val motivoOutro = optStringOrNull("motivoOutro")


        val membersArr = o.optJSONArray("membersSnapshot") ?: JSONArray()
        val membersSnapshot = buildList {
            for (i in 0 until membersArr.length()) {
                val v = membersArr.optString(i).trim()
                if (v.isNotBlank()) add(v)
            }
        }.distinct().takeIf { it.isNotEmpty() }

        val required = o.optBoolean("photoRequired", false)
        val photoId = optStringOrNull("photoId")
        val storagePath = optStringOrNull("storagePath")
        val thumbPath = optStringOrNull("thumbPath")

        val actor = TurnoActor(
            deviceId = o.optString("actorDeviceId"),
            deviceModel = o.optString("actorDeviceModel"),
            appVersion = o.optString("actorAppVersion")
        )

        return TurnoEventRemote(
            empresa = empresa,
            equipe = equipe,
            turnoId = turnoId,
            eventId = eventId,
            occurredAtClientMs = occurredAtMs,
            clientCreatedAtIso = clientIso,
            from = from,
            to = to,
            km4 = km4,
            kmInicioTurno4 = kmIni,
            kmDeltaTurno = kmDelta,
            nocSs = nocSs,
            motivo = motivo,
            motivoOutro = motivoOutro,
            membersSnapshot = membersSnapshot,
            photoAudit = TurnoPhotoAudit(
                required = required,
                photoId = photoId,
                storagePath = storagePath,
                thumbPath = thumbPath
            ),
            actor = actor
        )
    }

    private fun JSONObject.putOptString(key: String, value: String?) {
        if (value == null) put(key, JSONObject.NULL) else put(key, value)
    }

    private fun JSONObject.putOptInt(key: String, value: Int?) {
        if (value == null) put(key, JSONObject.NULL) else put(key, value)
    }
}