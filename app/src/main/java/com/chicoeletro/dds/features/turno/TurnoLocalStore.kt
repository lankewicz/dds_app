// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoLocalStore.kt
// Função: Persistência local para o estado do turno atual. Mantém os dados de jornada 
//         em cache persistente até que o fechamento ocorra.
// Tecnologias: Jetpack DataStore (Preferences).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object TurnoLocalStore {
    private const val PREFS = "dds_turno"
    private fun key(team: String) = "turno__${team.trim().lowercase()}"

    fun load(context: Context, team: String): TurnoSnapshot {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = sp.getString(key(team), null) ?: return TurnoSnapshot()
        return runCatching { fromJson(raw) }.getOrElse { TurnoSnapshot() }
    }

    fun save(context: Context, team: String, snap: TurnoSnapshot) {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        sp.edit().putString(key(team), toJson(snap)).apply()
    }

    private fun toJson(s: TurnoSnapshot): String {
        val o = JSONObject()

        // Sessão / roster
        o.put("turnoId", s.turnoId)
        o.put("isOpen", s.isOpen)
        o.put("openedAtClientMs", s.openedAtClientMs)
        o.put("clientUpdatedAtMs", s.clientUpdatedAtMs)
        o.put("lastEventId", s.lastEventId)
        o.put("lastEventAtClientMs", s.lastEventAtClientMs)

        val members = JSONArray()
        s.membersSnapshot.forEach { members.put(it) }
        o.put("membersSnapshot", members)

        // Operacional
        o.put("estado", s.estado.name)
        o.put("lastChangedAtIso", s.lastChangedAtIso)
        o.put("nocSs", s.nocSs)
        o.put("odometroVerificado", s.odometroVerificado)
        o.put("eventosKmCounter", s.eventosKmCounter)

        // OPÇÃO 1
        o.put("kmInicioTotalAbs", s.kmInicioTotalAbs)
        o.put("kmInicioLast3", s.kmInicioLast3)
        o.put("inicioTurnoAtIso", s.inicioTurnoAtIso)

        o.put("kmTotalAbs", s.kmTotalAbs)
        o.put("kmLast3", s.kmLast3)
        o.put("kmDeltaTurno", s.kmDeltaTurno)

        o.put("lastFotoTotalAbs", s.lastFotoTotalAbs)

        o.put("lastMotivo", s.lastMotivo?.name)
        o.put("lastMotivoOutro", s.lastMotivoOutro)

        o.put("lastClosedAtMs", s.lastClosedAtMs)
        o.put("lastWasDescansoSemanal", s.lastWasDescansoSemanal)

        val arr = JSONArray()
        s.ultimosKmLast3.forEach { arr.put(it) }
        o.put("ultimosKmLast3", arr)
        return o.toString()
    }
    private fun fromJson(raw: String): TurnoSnapshot {
        val o = JSONObject(raw)

        // Sessão / roster (backward compatible)
        val turnoId = o.optString("turnoId", "").trim().ifEmpty { null }
        val isOpen = o.optBoolean("isOpen", false)
        val openedAtClientMs = if (o.has("openedAtClientMs") && !o.isNull("openedAtClientMs")) o.optLong("openedAtClientMs") else null
        val clientUpdatedAtMs = if (o.has("clientUpdatedAtMs") && !o.isNull("clientUpdatedAtMs")) o.optLong("clientUpdatedAtMs") else 0L
        val lastEventId = o.optString("lastEventId", "").trim().ifEmpty { null }
        val lastEventAtClientMs = if (o.has("lastEventAtClientMs") && !o.isNull("lastEventAtClientMs")) o.optLong("lastEventAtClientMs") else 0L

        val membersArr = o.optJSONArray("membersSnapshot") ?: JSONArray()
        val members = buildList {
            for (i in 0 until membersArr.length()) {
                val v = membersArr.optString(i).trim()
                if (v.isNotBlank()) add(v)
            }
        }.distinct()

        val estado = EstadoTurno.valueOf(o.optString("estado", EstadoTurno.FECHADO.name))
        val iso = o.optString("lastChangedAtIso", "").ifEmpty { null }
        val noc = o.optString("nocSs", "").trim().ifEmpty { null }
        val ver = o.optBoolean("odometroVerificado", false)
        val cnt = o.optInt("eventosKmCounter", 0)

        // OPÇÃO 1: odometria nova
        val kmInicioTotalAbs = if (o.has("kmInicioTotalAbs") && !o.isNull("kmInicioTotalAbs")) o.optLong("kmInicioTotalAbs") else null
        val kmInicioLast3 = if (o.has("kmInicioLast3") && !o.isNull("kmInicioLast3")) o.optInt("kmInicioLast3") else null
        val inicioTurnoAtIso = o.optString("inicioTurnoAtIso", "").ifEmpty { null }

        val kmTotalAbs = if (o.has("kmTotalAbs") && !o.isNull("kmTotalAbs")) o.optLong("kmTotalAbs") else null
        val kmLast3 = if (o.has("kmLast3") && !o.isNull("kmLast3")) o.optInt("kmLast3") else null
        val kmDeltaTurno = if (o.has("kmDeltaTurno") && !o.isNull("kmDeltaTurno")) o.optInt("kmDeltaTurno") else 0

        val lastFotoTotalAbs = if (o.has("lastFotoTotalAbs") && !o.isNull("lastFotoTotalAbs")) o.optLong("lastFotoTotalAbs") else null


        val motivo = o.optString("lastMotivo", "").ifEmpty { null }
            ?.let { runCatching { MotivoDeslocamentoEspecial.valueOf(it) }.getOrNull() }
        val motivoOutro = o.optString("lastMotivoOutro", "").trim().ifEmpty { null }

        val lastClosedAtMs = if (o.has("lastClosedAtMs") && !o.isNull("lastClosedAtMs")) o.optLong("lastClosedAtMs") else null
        val lastWasDescansoSemanal = o.optBoolean("lastWasDescansoSemanal", false)

        // OPÇÃO 1: lista nova
        val arrLast3 = o.optJSONArray("ultimosKmLast3") ?: JSONArray()
        val listLast3 = buildList {
            for (i in 0 until arrLast3.length()) add(arrLast3.optInt(i))
        }.filter { it in 0..999 }.distinct().takeLast(4)

        // ---------- Backward compatibility ----------
        // Se não houver campos novos, tenta derivar a partir dos antigos (snapshots antigos no device)
        val legacyKmInicioTurno = if (o.has("kmInicioTurno") && !o.isNull("kmInicioTurno")) o.optInt("kmInicioTurno") else null
        val legacyArr = o.optJSONArray("ultimosKm") ?: JSONArray()
        val legacyList = buildList {
            for (i in 0 until legacyArr.length()) add(legacyArr.optInt(i))
        }.filter { it in 0..999 }.distinct().takeLast(4)
        val legacyLastFotoKm = if (o.has("lastFotoKm") && !o.isNull("lastFotoKm")) o.optInt("lastFotoKm") else null

        val finalKmInicioLast3 = kmInicioLast3 ?: legacyKmInicioTurno
        val finalUltimosLast3 = if (listLast3.isNotEmpty()) listLast3 else legacyList
        val finalKmLast3 = kmLast3 ?: finalUltimosLast3.lastOrNull()
        val finalLastFotoTotalAbs = lastFotoTotalAbs ?: legacyLastFotoKm?.toLong()


        return TurnoSnapshot(
            turnoId = turnoId,
            isOpen = isOpen,
            openedAtClientMs = openedAtClientMs,
            membersSnapshot = members,

            clientUpdatedAtMs = clientUpdatedAtMs,
            lastEventId = lastEventId,
            lastEventAtClientMs = lastEventAtClientMs,

            estado = estado,
            lastChangedAtIso = iso,
            nocSs = noc,

            kmInicioTotalAbs = kmInicioTotalAbs,
            kmInicioLast3 = finalKmInicioLast3,
            inicioTurnoAtIso = inicioTurnoAtIso,

            kmTotalAbs = kmTotalAbs,
            kmLast3 = finalKmLast3,
            kmDeltaTurno = kmDeltaTurno,

            odometroVerificado = ver,
            eventosKmCounter = cnt,
            lastFotoTotalAbs = finalLastFotoTotalAbs,
            lastMotivo = motivo,
            lastMotivoOutro = motivoOutro,
            lastClosedAtMs = lastClosedAtMs,
            lastWasDescansoSemanal = lastWasDescansoSemanal
        )
    }
}