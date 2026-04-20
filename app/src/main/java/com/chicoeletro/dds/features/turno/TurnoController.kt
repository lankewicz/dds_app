// Módulo: app/src/main/java/com/chicoeletro/dds/features/turno/TurnoController.kt
// Função: Controlador central da jornada de trabalho. Gerencia a abertura e fechamento de turnos, 
//         valida regras de interjornada (CLT) e orquestra a persistência local e remota.
// Tecnologias: Kotlin, DataStore, Firestore Integration, Java Time API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.turno

import android.content.Context
import java.time.Instant

class TurnoController(
    private val context: Context,
    private val equipe: String
) {
    // Mantido como referência para futura política de auditoria por foto.
    private val chanceEveryN = 5
    private val kmStep = 1000

    private fun shouldRequestPhoto(
        from: EstadoTurno,
        to: EstadoTurno,
        proposedKmTotalAbs: Long?,
        firstExecution: Boolean,
        snap: TurnoSnapshot
    ): Boolean {
        // Regra atual: foto opcional em todas as transições.
        // Deixamos o helper centralizado para voltar a exigir foto apenas
        // em situações específicas quando o fluxo de upload estiver pronto.
        return false
    }

    fun current(): TurnoSnapshot = TurnoLocalStore.load(context, equipe)

    private fun normalizeIdPart(v: String): String =
        v.trim().uppercase().replace(Regex("[^A-Z0-9_-]"), "_")

    private fun normalizeMembers(membersSnapshot: List<String>): List<String> =
        membersSnapshot.map { it.trim().uppercase() }.filter { it.isNotBlank() }.distinct()


    /**
     * Abre uma nova sessão de turno (turnoId determinístico) e congela o roster.
     * Regra de negócio: mudança de membros implica FECHAR e ABRIR novo turno.
     */
    fun abrirTurno(empresa: String, membersSnapshot: List<String>): TurnoSnapshot {
        val snapToPreserve = current()
        val nowMs = System.currentTimeMillis()
        val emp = normalizeIdPart(empresa)
        val team = normalizeIdPart(equipe)
        val turnoId = "${emp}_${team}_${nowMs}"

        // Novo turno: zera odometria/contadores para não vazar entre sessões
        val updated = TurnoSnapshot(
            turnoId = turnoId,
            isOpen = true,
            openedAtClientMs = nowMs,
            membersSnapshot = normalizeMembers(membersSnapshot),
            clientUpdatedAtMs = nowMs,
            lastEventAtClientMs = nowMs,
            estado = EstadoTurno.FECHADO, // operacionalmente ainda FECHADO até a 1ª transição (ex.: ABRIR com KM)
            lastClosedAtMs = snapToPreserve.lastClosedAtMs,
            lastWasDescansoSemanal = snapToPreserve.lastWasDescansoSemanal
        )

        TurnoLocalStore.save(context, equipe, updated)
        return updated
    }

    fun fecharTurno(closeReason: String? = null): TurnoSnapshot {
        val snap = current()
        if (!snap.isOpen) return snap

        val nowMs = System.currentTimeMillis()
        val updated = snap.copy(
            isOpen = false,
            clientUpdatedAtMs = maxOf(snap.clientUpdatedAtMs, nowMs),
            lastEventAtClientMs = maxOf(snap.lastEventAtClientMs, nowMs),
            // encerra o ciclo operacional (próximo turno começa limpo)
            estado = EstadoTurno.FECHADO,
            kmInicioTotalAbs = null,
            kmInicioLast3 = null,
            inicioTurnoAtIso = null,
            nocSs = null
        )

        TurnoLocalStore.save(context, equipe, updated)
        return updated
    }

    fun atualizarNocSs(noc: String?): TurnoSnapshot {
        val snap = current()
        require(snap.isOpen && snap.estado == EstadoTurno.ABERTO) { "NOC/SS só pode ser alterado com o turno ABERTO." }
        val v = noc?.trim()?.ifEmpty { null }
        if (v != null) require(TurnoRules.isNocSsValido(v)) { "NOC/SS inválido." }

        val nowMs = System.currentTimeMillis()
        val nowIso = Instant.ofEpochMilli(nowMs).toString()

        val updated = snap.copy(
            nocSs = v,
            clientUpdatedAtMs = maxOf(snap.clientUpdatedAtMs, nowMs),
            lastChangedAtIso = nowIso
        )
        TurnoLocalStore.save(context, equipe, updated)
        return updated
    }

    fun plan(to: EstadoTurno, proposedKmTotalAbs: Long?, proposedKmLast3: Int?): PlanoTransicao {
        val snap = current()
        val from = snap.estado

        require(snap.isOpen && !snap.turnoId.isNullOrBlank()) { "Turno não está aberto. Use 'ABRIR TURNO' antes." }
        require(TurnoRules.podeTransitar(from, to)) { "Transição inválida: $from -> $to" }

        val pedeKm = TurnoRules.pedeKm(from, to)
        val primeira = pedeKm && !snap.odometroVerificado
        val pedeMotivo = TurnoRules.pedeMotivo(to)

        val pedeFoto = if (!pedeKm) {
            false
        } else {
            shouldRequestPhoto(
                from = from,
                to = to,
                proposedKmTotalAbs = proposedKmTotalAbs,
                firstExecution = primeira,
                snap = snap
            )
        }

        return PlanoTransicao(
            from = from,
            to = to,
            pedeKm = pedeKm,
            pedeFoto = pedeFoto,
            primeiraExecucao = primeira,
            pedeMotivo = pedeMotivo
        )
    }

    fun confirm(req: RequisicaoTransicao, photoProvided: Boolean): TurnoSnapshot {
        val snap = current()
        val from = snap.estado

        require(snap.isOpen && !snap.turnoId.isNullOrBlank()) { "Turno não está aberto. Use 'ABRIR TURNO' antes." }
        val to = req.to

        require(TurnoRules.podeTransitar(from, to)) { "Transição inválida: $from -> $to" }

        // Motivo obrigatório ao entrar em deslocamento especial
        if (TurnoRules.pedeMotivo(to)) {
            require(req.motivo != null) { "Motivo obrigatório." }
            if (req.motivo == MotivoDeslocamentoEspecial.OUTRO) {
                require(!req.motivoOutro.isNullOrBlank()) { "Informe o motivo (Outro)." }
            }
        }

        val plano = plan(to, req.kmTotalAbs, req.kmLast3)

        if (plano.pedeKm) {
            val hasAny = (req.kmTotalAbs != null) || (req.kmLast3 != null)
            require(hasAny) { "Quilometragem obrigatória." }
            if (req.kmLast3 != null) require(req.kmLast3 in 0..999) { "KM (3 últimos) inválido (0..999)." }
            if (req.kmTotalAbs != null) require(req.kmTotalAbs in 0..9_999_999L) { "KM total inválido (0..9.999.999)." }
            // 1ª execução: exige KM completo, mas não bloqueia por ausência de foto.
            if (plano.primeiraExecucao) {
                require(req.kmTotalAbs != null) { "Na 1ª execução, informe o KM total (câmera ou digitado completo)." }
            }
        }

        val nowMs = System.currentTimeMillis()
        val nowIso = Instant.now().toString()
        var updated = snap.copy(
            estado = to,
            lastChangedAtIso = nowIso,
            clientUpdatedAtMs = maxOf(snap.clientUpdatedAtMs, nowMs),
            lastEventAtClientMs = maxOf(snap.lastEventAtClientMs, nowMs)
        )

        // -------- ODOMETRIA (sempre somando) --------
        // Normaliza o "currLast3" mesmo quando veio KM total
        val currLast3: Int? = req.kmLast3 ?: req.kmTotalAbs?.rem(1000)?.toInt()

        if (plano.pedeKm) {
            require(currLast3 != null && currLast3 in 0..999) { "KM (3 últimos) inválido." }

            val delta: Int = if (req.kmTotalAbs != null && snap.kmTotalAbs != null) {
                val d = req.kmTotalAbs - snap.kmTotalAbs
                require(d >= 0) { "KM total menor que o anterior. Verifique a leitura." }
                d.toInt()
            } else {
                val prev = snap.kmLast3 ?: snap.kmInicioLast3 ?: currLast3
                val raw = currLast3 - prev
                if (raw >= 0) raw else raw + 1000
            }

            val cnt = snap.eventosKmCounter + 1
            val hist = (snap.ultimosKmLast3 + currLast3).distinct().takeLast(4)

            val newKmTotalAbs = req.kmTotalAbs ?: snap.kmTotalAbs
            val newLastFotoTotalAbs =
                if (plano.pedeFoto && photoProvided && req.kmTotalAbs != null) req.kmTotalAbs else snap.lastFotoTotalAbs

            updated = updated.copy(
                // acumulado do turno
                kmDeltaTurno = snap.kmDeltaTurno + delta,
                // última leitura
                kmTotalAbs = newKmTotalAbs,
                kmLast3 = currLast3,
                // histórico e política
                ultimosKmLast3 = hist,
                eventosKmCounter = cnt,
                odometroVerificado = snap.odometroVerificado || plano.primeiraExecucao,
                lastFotoTotalAbs = newLastFotoTotalAbs
            )
        }

        // Marca início do turno quando entra em ABERTO pela 1ª vez nesta sessão
        if (to == EstadoTurno.ABERTO && snap.inicioTurnoAtIso == null && plano.pedeKm) {
            updated = updated.copy(
                kmInicioTotalAbs = req.kmTotalAbs,
                kmInicioLast3 = currLast3,
                inicioTurnoAtIso = nowIso
            )
        }

        // NOC/SS só faz sentido no estado ABERTO.
        // Ao mudar de status, limpa automaticamente antes de persistir/publicar o state.
        if (from != to && to != EstadoTurno.ABERTO && updated.nocSs != null) {
            updated = updated.copy(nocSs = null)
        }

        // Ao fechar, limpa os dados da sessão, mas guarda metadados de interjornada
        if (to == EstadoTurno.FECHADO) {
            updated = updated.copy(
                isOpen = false,
                kmInicioTotalAbs = null,
                kmInicioLast3 = null,
                inicioTurnoAtIso = null,
                nocSs = null, // opcional: limpa NOC/SS ao fechar
                lastClosedAtMs = nowMs,
                lastWasDescansoSemanal = req.isDescansoSemanal
            )
        }

        if (to == EstadoTurno.DESLOCAMENTO_ESPECIAL) {
            updated = updated.copy(
                lastMotivo = req.motivo,
                lastMotivoOutro = req.motivoOutro?.trim()?.takeIf { it.isNotBlank() }
            )
        }

        TurnoLocalStore.save(context, equipe, updated)
        return updated
    }
}