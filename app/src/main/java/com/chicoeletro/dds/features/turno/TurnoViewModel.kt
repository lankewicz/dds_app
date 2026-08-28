package com.chicoeletro.dds.features.turno

import android.content.Context
import android.os.Build
import android.provider.Settings
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import javax.inject.Inject

@HiltViewModel
class TurnoViewModel @Inject constructor(
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _turnoSnapshot = MutableStateFlow(TurnoSnapshot())
    val turnoSnapshot: StateFlow<TurnoSnapshot> = _turnoSnapshot.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val _rotalogState = MutableStateFlow<RotalogMobileTeam?>(null)
    val rotalogState: StateFlow<RotalogMobileTeam?> = _rotalogState.asStateFlow()

    private val _rawDailyJson = MutableStateFlow<String?>(null)
    val rawDailyJson: StateFlow<String?> = _rawDailyJson.asStateFlow()

    private var currentEquipe: String = ""
    private var controller: TurnoController? = null
    private var rotalogPollingJob: Job? = null

    private val deviceId: String by lazy {
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
    }

    private val appVersion: String by lazy {
        runCatching {
            val pm = context.packageManager
            val pkg = context.packageName
            val pInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                pm.getPackageInfo(pkg, android.content.pm.PackageManager.PackageInfoFlags.of(0))
            } else {
                @Suppress("DEPRECATION")
                pm.getPackageInfo(pkg, 0)
            }
            pInfo.versionName ?: "unknown"
        }.getOrElse { "unknown" }
    }

    fun init(equipe: String) {
        if (currentEquipe == equipe) return
        currentEquipe = equipe
        if (equipe.isNotBlank()) {
            controller = TurnoController(context, equipe)
            refresh()
            startRotalogPolling(equipe)
        }
    }

    fun refresh() {
        controller?.let {
            _turnoSnapshot.value = it.current()
        }
        if (currentEquipe.isNotBlank()) {
            startRotalogPolling(currentEquipe)
        }
    }

    companion object {
        private const val ROTALOG_POLLING_INTERVAL_MS = 5 * 60_000L // 5 minutos (alinhado com o ciclo de raspagem de 10 min)
    }

    private fun startRotalogPolling(equipe: String) {
        rotalogPollingJob?.cancel()
        rotalogPollingJob = viewModelScope.launch {
            while (true) {
                runCatching {
                    val debugJson = RotalogMobileRepository.fetchDailyDebugJson(equipe)
                    _rawDailyJson.value = debugJson
                }.onFailure { e ->
                    android.util.Log.w("TurnoViewModel", "fetchDailyDebugJson indisponível: ${e.message}")
                }

                runCatching {
                    val remote = RotalogMobileRepository.current(equipe)
                    if (remote != null) {
                        reconcileTurnoState(remote)
                        _rotalogState.value = remote
                    }
                }.onFailure { e ->
                    android.util.Log.w("TurnoViewModel", "current indisponível: ${e.message}")
                }

                delay(ROTALOG_POLLING_INTERVAL_MS)
            }
        }
    }

    private fun parseIsoMs(isoStr: String?): Long {
        if (isoStr.isNullOrBlank()) return 0L
        return runCatching {
            val normalized = isoStr.trim().let {
                if (it.contains("+") || it.endsWith("Z")) it else "${it}Z"
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                try {
                    java.time.OffsetDateTime.parse(normalized).toInstant().toEpochMilli()
                } catch (e: Exception) {
                    Instant.parse(normalized.replace(Regex("\\+\\d{2}:\\d{2}$"), "Z")).toEpochMilli()
                }
            } else {
                java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US).parse(normalized)?.time ?: 0L
            }
        }.getOrElse { 0L }
    }

    private fun reconcileTurnoState(remote: RotalogMobileTeam) {
        reconcileBdoServices(remote)

        val currentSnap = _turnoSnapshot.value
        val rawStatus = remote.turnStatus?.trim()?.uppercase() ?: return

        val remoteState = when {
            rawStatus.contains("INTERVALO") || rawStatus.contains("PAUSA") -> EstadoTurno.INTERVALO
            rawStatus.contains("ABERTO") || rawStatus.contains("EXECUC") || rawStatus.contains("DESLOCA") -> EstadoTurno.ABERTO
            rawStatus.contains("FECHADO") || rawStatus.contains("FINALIZ") -> EstadoTurno.FECHADO
            else -> null
        } ?: return

        val remoteMs = parseIsoMs(remote.updatedAt)
        val localMs = currentSnap.lastEventAtClientMs.takeIf { it > 0 }
            ?: parseIsoMs(currentSnap.lastChangedAtIso)

        val ctrl = controller ?: return

        if (currentSnap.estado == EstadoTurno.DESLOCAMENTO_ESPECIAL) {
            // Regra: Deslocamento Especial pode ser sobreposto por estado obtido com horário posterior pela raspagem
            if (remoteMs > localMs) {
                _turnoSnapshot.value = ctrl.syncRemoteEstado(remoteState, remote.updatedAt)
            }
        } else if (currentSnap.estado != remoteState) {
            // Se o app local estiver FECHADO e o Rotalog raspado trouxer ABERTO ou INTERVALO, atualiza imediatamente
            if (currentSnap.estado == EstadoTurno.FECHADO && (remoteState == EstadoTurno.ABERTO || remoteState == EstadoTurno.INTERVALO)) {
                _turnoSnapshot.value = ctrl.syncRemoteEstado(remoteState, remote.updatedAt)
            } else if (remoteMs >= localMs || localMs == 0L) {
                _turnoSnapshot.value = ctrl.syncRemoteEstado(remoteState, remote.updatedAt)
            }
        }
    }

    private fun reconcileBdoServices(remote: RotalogMobileTeam) {
        val current = BdoLocalStore.loadToday(context, currentEquipe)
        val merged = mergeBdoServices(current, remote.toBdoSsList())
        if (merged != current) {
            BdoLocalStore.saveToday(context, currentEquipe, merged)
        }
    }
    fun clearError() {
        _errorMessage.value = null
    }

    fun atualizarNocSs(noc: String?, empresa: String) {
        viewModelScope.launch {
            runCatching {
                val ctrl = controller ?: return@launch
                val after = ctrl.atualizarNocSs(noc)
                _turnoSnapshot.value = after

                val bdoList = BdoLocalStore.loadToday(context, currentEquipe)
                val state = TurnoStateRemote(
                    empresa = empresa,
                    equipe = currentEquipe,
                    turnoId = after.turnoId,
                    isOpen = after.isOpen,
                    membersSnapshot = after.membersSnapshot,
                    openedAtClientMs = after.openedAtClientMs,
                    closedAtClientMs = null,
                    closeReason = null,
                    clientUpdatedAtMs = after.clientUpdatedAtMs,
                    updatedAtIso = after.lastChangedAtIso ?: Instant.ofEpochMilli(after.clientUpdatedAtMs).toString(),
                    lastEventId = after.lastEventId,
                    lastEventAtClientMs = after.lastEventAtClientMs,
                    estado = after.estado.name,
                    nocSs = after.nocSs,
                    kmTotalAbs = after.kmTotalAbs,
                    kmInicioTotalAbs = after.kmInicioTotalAbs,
                    kmDeltaTurno = after.kmDeltaTurno,
                    kmInicioTurno4 = after.kmInicioLast3,
                    inicioTurnoAtIso = after.inicioTurnoAtIso,
                    odometroVerificado = after.odometroVerificado,
                    ultimosKm4 = after.ultimosKmLast3,
                    eventosKmCounter = after.eventosKmCounter,
                    lastMotivo = after.lastMotivo?.name,
                    lastMotivoOutro = after.lastMotivoOutro,
                    lastWasDescansoSemanal = after.lastWasDescansoSemanal,
                    deviceIdLastWriter = deviceId,
                    bdoList = bdoList
                )
                TurnoFirestoreUploader.pushState(empresa, currentEquipe, state)
            }.onFailure { e ->
                _errorMessage.value = e.message ?: "Erro ao atualizar NOC/SS"
            }
        }
    }

    fun requestTransition(req: RequisicaoTransicao, empresa: String, eletricistas: List<String>, isOnline: Boolean): Boolean {
        val ctrl = controller ?: return false
        val before = _turnoSnapshot.value

        // ===== ABRIR TURNO =====
        if (!before.isOpen && (req.to == EstadoTurno.ABERTO || req.to == EstadoTurno.DESLOCAMENTO_ESPECIAL)) {
            val opened = runCatching { ctrl.abrirTurno(empresa, eletricistas) }.getOrNull() ?: return false
            _turnoSnapshot.value = opened
            BdoLocalStore.saveToday(context, currentEquipe, emptyList())

            val sessionOpen = TurnoSessionRemote(
                empresa = empresa,
                equipe = currentEquipe,
                turnoId = opened.turnoId!!,
                membersSnapshot = opened.membersSnapshot,
                openedAtClientMs = opened.openedAtClientMs!!,
                openedByUid = null,
                openedByDeviceId = deviceId
            )
            viewModelScope.launch {
                runCatching { TurnoFirestoreUploader.upsertTurnoSession(sessionOpen) }
            }
        }

        val plano = runCatching {
            ctrl.plan(req.to, req.kmTotalAbs, req.kmLast3)
        }.onFailure { e ->
            _errorMessage.value = e.message ?: "Falha ao planejar transição"
        }.getOrNull() ?: return false

        val after = runCatching { ctrl.confirm(req, photoProvided = false) }.onFailure { e ->
            _errorMessage.value = e.message ?: "Falha ao confirmar transição"
        }.getOrNull() ?: return false

        _turnoSnapshot.value = after

        // Sync Firebase
        val occurredAtMs = after.lastEventAtClientMs
        val tsIso = Instant.ofEpochMilli(occurredAtMs).toString()
        val eventId = "${deviceId}_${occurredAtMs}_${req.to.name}"
        val kmDeltaTurno: Int? = if (before.estado == EstadoTurno.ABERTO && req.to == EstadoTurno.FECHADO) after.kmDeltaTurno else null
        
        val actor = TurnoActor(deviceId, Build.MODEL ?: "unknown", appVersion)
        val photoAudit = TurnoPhotoAudit(plano.pedeFoto, null, null, null)
        val bdoList = BdoLocalStore.loadToday(context, currentEquipe)

        val event = TurnoEventRemote(
            empresa = empresa, equipe = currentEquipe, turnoId = after.turnoId!!, eventId = eventId,
            occurredAtClientMs = occurredAtMs, clientCreatedAtIso = tsIso, from = before.estado.name, to = req.to.name,
            kmTotalAbs = req.kmTotalAbs, km4 = req.kmLast3, kmInicioTotalAbs = before.kmInicioTotalAbs,
            kmInicioTurno4 = before.kmInicioLast3, kmDeltaTurno = kmDeltaTurno, nocSs = before.nocSs,
            motivo = req.motivo?.name, motivoOutro = req.motivoOutro?.trim()?.takeIf { it.isNotBlank() },
            photoAudit = photoAudit, actor = actor, bdoList = bdoList
        )

        val state = TurnoStateRemote(
            empresa = empresa, equipe = currentEquipe, turnoId = after.turnoId, isOpen = after.isOpen,
            membersSnapshot = after.membersSnapshot, openedAtClientMs = after.openedAtClientMs,
            closedAtClientMs = if (req.to == EstadoTurno.FECHADO) occurredAtMs else null,
            closeReason = null, clientUpdatedAtMs = after.clientUpdatedAtMs,
            updatedAtIso = after.lastChangedAtIso ?: tsIso, lastEventId = eventId,
            lastEventAtClientMs = occurredAtMs, estado = after.estado.name, nocSs = after.nocSs,
            kmTotalAbs = after.kmTotalAbs, kmInicioTotalAbs = after.kmInicioTotalAbs, kmDeltaTurno = after.kmDeltaTurno,
            kmInicioTurno4 = after.kmInicioLast3, inicioTurnoAtIso = after.inicioTurnoAtIso,
            odometroVerificado = after.odometroVerificado, ultimosKm4 = after.ultimosKmLast3,
            eventosKmCounter = after.eventosKmCounter, lastMotivo = after.lastMotivo?.name,
            lastMotivoOutro = after.lastMotivoOutro, lastWasDescansoSemanal = after.lastWasDescansoSemanal,
            deviceIdLastWriter = deviceId, bdoList = bdoList
        )

        if (req.to == EstadoTurno.FECHADO && before.isOpen && !before.turnoId.isNullOrBlank()) {
            val sessionClose = TurnoSessionRemote(
                empresa = empresa, equipe = currentEquipe, turnoId = before.turnoId,
                membersSnapshot = before.membersSnapshot, openedAtClientMs = before.openedAtClientMs ?: 0L,
                closedAtClientMs = occurredAtMs, closeReason = null, openedByUid = null,
                openedByDeviceId = deviceId, closedByUid = null, closedByDeviceId = deviceId
            )
            viewModelScope.launch {
                runCatching { TurnoFirestoreUploader.upsertTurnoSession(sessionClose) }
            }
        }

        TurnoPendingStore.enqueue(context, event)
        TurnoFirestoreUploader.pushState(empresa, currentEquipe, state)
        TurnoFirestoreUploader.tryPushPending(context, isOnline)

        return true
    }
}
