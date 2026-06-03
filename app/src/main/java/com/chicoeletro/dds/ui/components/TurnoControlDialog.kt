package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.features.turno.*

private enum class Step { MENU, MOTIVO, KM, RECIBO_FINAL, AVISO_INTERJORNADA }

sealed class UnifiedHistoryItem {
    abstract val timestampMs: Long
    
    data class Servico(val ss: BdoSs) : UnifiedHistoryItem() {
        override val timestampMs: Long
            get() = ss.transitions.firstOrNull()?.timestampMs ?: 0L
    }
    
    data class Transicao(val trans: TurnoTransition) : UnifiedHistoryItem() {
        override val timestampMs: Long
            get() = trans.timestampMs
    }

    data class SemExecucao(
        val durationMs: Long,
        val startMs: Long,
        val endMs: Long,
        override val timestampMs: Long
    ) : UnifiedHistoryItem()
}

@Composable
fun TurnoControlScreen(
    equipe: String,
    snapshot: TurnoSnapshot,
    onDismiss: () -> Unit,
    onSaveNocSs: (String?) -> Unit,
    onRequestTransition: (RequisicaoTransicao) -> Unit,
    onOpenOdometerCamera: (EstadoTurno?, MotivoDeslocamentoEspecial?, String) -> Unit = { _, _, _ -> },
    prefillKmTotal: String? = null,
    startAtKmTarget: EstadoTurno? = null,
    prefillMotivo: MotivoDeslocamentoEspecial? = null,
    prefillMotivoOutro: String? = null,
    online: Boolean = false,
    teamType: String? = null,
    onClickEquipe: () -> Unit = {}
) {
    var step by remember(startAtKmTarget) {
        mutableStateOf(if (startAtKmTarget != null) Step.KM else Step.MENU)
    }
    var target by remember(startAtKmTarget) { mutableStateOf(startAtKmTarget) }
    var savedDeltaKm by remember { mutableStateOf<Int?>(null) }

    var motivo by remember(prefillMotivo) { mutableStateOf(prefillMotivo) }
    var motivoOutro by remember(prefillMotivoOutro) { mutableStateOf(prefillMotivoOutro ?: "") }

    var kmOutro by remember { mutableStateOf("") }
    var kmTotalFromPhoto by remember { mutableStateOf<Long?>(null) }

    var isDescansoSemanal by remember { mutableStateOf(false) }
    var pendingRequest by remember { mutableStateOf<RequisicaoTransicao?>(null) }

    val context = LocalContext.current
    var bdoList by remember(equipe) {
        mutableStateOf(BdoLocalStore.loadToday(context, equipe))
    }

    LaunchedEffect(prefillKmTotal) {
        val total = prefillKmTotal?.filter { it.isDigit() }?.take(9)?.toLongOrNull()
        if (total != null) {
            kmTotalFromPhoto = total
            kmOutro = ""
        }
    }

    val podeContinuarMotivo =
        motivo != null &&
            (motivo != MotivoDeslocamentoEspecial.OUTRO || motivoOutro.isNotBlank())

    val podeConfirmarKm =
        (kmTotalFromPhoto != null) || kmOutro.trim().isNotEmpty()

    fun confirmarKmDoTopo() {
        val totalAbs: Long? = kmTotalFromPhoto ?: run {
            val s = kmOutro.trim()
            if (s.isBlank()) null
            else if (s.length >= 4) s.toLongOrNull()
            else null
        }

        val last3: Int? = when {
            totalAbs != null -> (totalAbs % 1000).toInt()
            else -> kmOutro.trim().toIntOrNull()?.rem(1000)
        }

        if (last3 != null) {
            val targetState = requireNotNull(target)
            val isClosing = targetState == EstadoTurno.FECHADO

            if (isClosing) {
                val start = snapshot.kmInicioLast3
                if (start != null) {
                    val raw = last3 - start
                    savedDeltaKm = if (raw >= 0) raw else raw + 1000
                }
            }

            val req = RequisicaoTransicao(
                to = targetState,
                motivo = motivo,
                motivoOutro = motivoOutro.takeIf { it.isNotBlank() },
                kmTotalAbs = totalAbs,
                kmLast3 = last3
            )

            if (isClosing) {
                pendingRequest = req
                step = Step.RECIBO_FINAL
            } else {
                onRequestTransition(req)
                step = Step.MENU
            }
        }
    }

    fun alterarEstadoSs(ssId: String, novoStatus: SsStatus, reason: String? = null) {
        val list = BdoLocalStore.loadToday(context, equipe)
        val now = System.currentTimeMillis()
        val updated = list.map { ss ->
            if (ss.ssId == ssId) {
                val transitions = ss.transitions.toMutableList()
                if ((novoStatus == SsStatus.CONCLUSAO || novoStatus == SsStatus.CANCELADO) &&
                    !transitions.any { it.status == SsStatus.EXECUCAO }) {
                    transitions.add(SsTransition(SsStatus.EXECUCAO, now, snapshot.kmTotalAbs))
                }
                transitions.add(SsTransition(novoStatus, now, snapshot.kmTotalAbs))
                ss.copy(
                    status = novoStatus,
                    transitions = transitions,
                    cancelReason = reason ?: ss.cancelReason
                )
            } else {
                ss
            }
        }
        BdoLocalStore.saveToday(context, equipe, updated)
        bdoList = updated
        
        val ssAtiva = updated.find { it.status == SsStatus.DESLOCAMENTO || it.status == SsStatus.EXECUCAO }
        onSaveNocSs(ssAtiva?.ssId)
    }

    fun definirSsDirect(ssId: String) {
        val currentList = BdoLocalStore.loadToday(context, equipe)
        val now = System.currentTimeMillis()
        
        val updatedList = currentList.map { ss ->
            if (ss.status == SsStatus.DESLOCAMENTO || ss.status == SsStatus.EXECUCAO) {
                val transitions = ss.transitions.toMutableList()
                if (!transitions.any { it.status == SsStatus.EXECUCAO }) {
                    transitions.add(SsTransition(SsStatus.EXECUCAO, now, snapshot.kmTotalAbs))
                }
                transitions.add(SsTransition(SsStatus.CONCLUSAO, now, snapshot.kmTotalAbs))
                ss.copy(status = SsStatus.CONCLUSAO, transitions = transitions)
            } else {
                ss
            }
        }
        
        val newSs = BdoSs(
            ssId = ssId,
            status = SsStatus.DESLOCAMENTO,
            transitions = listOf(SsTransition(SsStatus.DESLOCAMENTO, now, snapshot.kmTotalAbs))
        )
        
        val newList = listOf(newSs) + updatedList
        BdoLocalStore.saveToday(context, equipe, newList)
        bdoList = newList
        onSaveNocSs(ssId)
    }

    var ssActiveConfirmingTransition by remember { mutableStateOf<BdoSs?>(null) }
    var pendingTurnoTarget by remember { mutableStateOf<EstadoTurno?>(null) }
    
    fun onSelectTargetDirect(newTarget: EstadoTurno) {
        if (newTarget == EstadoTurno.ABERTO && snapshot.estado == EstadoTurno.FECHADO) {
            val lastClosed = snapshot.lastClosedAtMs
            if (lastClosed != null) {
                val now = System.currentTimeMillis()
                val reqHours = if (snapshot.lastWasDescansoSemanal) 24 else 11
                val reqMillis = reqHours * 60 * 60 * 1000L
                if (now - lastClosed < reqMillis) {
                    target = newTarget
                    step = Step.AVISO_INTERJORNADA
                    return
                }
            }
        }

        target = newTarget
        step = when {
            newTarget == EstadoTurno.DESLOCAMENTO_ESPECIAL -> Step.MOTIVO
            TurnoRules.pedeKm(snapshot.estado, newTarget) -> Step.KM
            else -> {
                onRequestTransition(RequisicaoTransicao(to = newTarget))
                Step.MENU
            }
        }
    }
    
    fun handleSelectTarget(newTarget: EstadoTurno) {
        val activeSs = bdoList.find { it.status == SsStatus.DESLOCAMENTO || it.status == SsStatus.EXECUCAO }
        if (activeSs != null) {
            ssActiveConfirmingTransition = activeSs
            pendingTurnoTarget = newTarget
        } else {
            onSelectTargetDirect(newTarget)
        }
    }

    var showOpenTurnoPromptBySs by remember { mutableStateOf<String?>(null) }
    var pendingSsAfterOpenTurno by remember { mutableStateOf<String?>(null) }
    
    LaunchedEffect(snapshot.estado) {
        if (snapshot.estado == EstadoTurno.ABERTO) {
            pendingSsAfterOpenTurno?.let { ssId ->
                definirSsDirect(ssId)
                pendingSsAfterOpenTurno = null
            }
        }
    }

    var showCancelDialogForSs by remember { mutableStateOf<BdoSs?>(null) }
    var cancelReasonText by remember { mutableStateOf("") }

    if (ssActiveConfirmingTransition != null) {
        AlertDialog(
            onDismissRequest = {
                ssActiveConfirmingTransition = null
                pendingTurnoTarget = null
            },
            title = { Text("Serviço em Aberto") },
            text = { Text("Tem um serviço aberto (SS: ${ssActiveConfirmingTransition?.ssId}). Deseja fechar o serviço?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        val ss = ssActiveConfirmingTransition!!
                        val targetState = pendingTurnoTarget!!
                        alterarEstadoSs(ss.ssId, SsStatus.CONCLUSAO)
                        ssActiveConfirmingTransition = null
                        pendingTurnoTarget = null
                        onSelectTargetDirect(targetState)
                    }
                ) {
                    Text("Sim")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        ssActiveConfirmingTransition = null
                        pendingTurnoTarget = null
                    }
                ) {
                    Text("Não")
                }
            }
        )
    }

    if (showOpenTurnoPromptBySs != null) {
        AlertDialog(
            onDismissRequest = { showOpenTurnoPromptBySs = null },
            title = { Text("Turno Fechado/Pausado") },
            text = { Text("Deseja reativar/abrir o turno para iniciar a SS?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        val ssId = showOpenTurnoPromptBySs!!
                        pendingSsAfterOpenTurno = ssId
                        showOpenTurnoPromptBySs = null
                        onSelectTargetDirect(EstadoTurno.ABERTO)
                    }
                ) {
                    Text("Sim")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showOpenTurnoPromptBySs = null }
                ) {
                    Text("Não")
                }
            }
        )
    }

    if (showCancelDialogForSs != null) {
        AlertDialog(
            onDismissRequest = {
                showCancelDialogForSs = null
                cancelReasonText = ""
            },
            title = { Text("Cancelar Serviço") },
            text = {
                Column {
                    Text("Informe o motivo do cancelamento da SS ${showCancelDialogForSs?.ssId}:")
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = cancelReasonText,
                        onValueChange = { cancelReasonText = it },
                        label = { Text("Motivo") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val ss = showCancelDialogForSs!!
                        alterarEstadoSs(ss.ssId, SsStatus.CANCELADO, cancelReasonText)
                        showCancelDialogForSs = null
                        cancelReasonText = ""
                    },
                    enabled = cancelReasonText.isNotBlank()
                ) {
                    Text("Confirmar")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showCancelDialogForSs = null
                        cancelReasonText = ""
                    }
                ) {
                    Text("Voltar")
                }
            }
        )
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp)
        ) {
            if (step != Step.MENU) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = {
                            when (step) {
                                Step.MENU -> onDismiss()
                                Step.MOTIVO -> step = Step.MENU
                                Step.KM -> {
                                    step = if (target == EstadoTurno.DESLOCAMENTO_ESPECIAL) {
                                        Step.MOTIVO
                                    } else {
                                        Step.MENU
                                    }
                                }
                                Step.AVISO_INTERJORNADA -> step = Step.MENU
                                Step.RECIBO_FINAL -> {}
                            }
                        }
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Voltar"
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = when (step) {
                            Step.KM -> "Informar Quilometragem"
                            Step.MOTIVO -> "Motivo do Deslocamento"
                            Step.AVISO_INTERJORNADA -> "Alerta de Interjornada"
                            Step.RECIBO_FINAL -> "Recibo do Turno"
                            else -> "Controle de Turno"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.weight(1f))
                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Fechar"
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            Box(
                modifier = Modifier.weight(1f).fillMaxWidth()
            ) {
                if (step == Step.MENU) {
                    MenuStep(
                        snapshot = snapshot,
                        onDismiss = onDismiss,
                        onSelectTarget = { handleSelectTarget(it) },
                        equipe = equipe,
                        teamType = teamType,
                        onClickEquipe = onClickEquipe,
                        online = online,
                        bdoList = bdoList,
                        onDefinirSs = { ssId ->
                            if (snapshot.estado == EstadoTurno.ABERTO) {
                                definirSsDirect(ssId)
                            } else {
                                showOpenTurnoPromptBySs = ssId
                            }
                        },
                        onAlterarEstado = { ssId, novoStatus ->
                            if (novoStatus == SsStatus.CANCELADO) {
                                val ss = bdoList.find { it.ssId == ssId }
                                showCancelDialogForSs = ss
                                cancelReasonText = ""
                            } else {
                                alterarEstadoSs(ssId, novoStatus)
                            }
                        }
                    )
                } else {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState())
                    ) {
                        when (step) {
                            Step.AVISO_INTERJORNADA -> InterjornadaNotice(
                                snapshot = snapshot,
                                onProceed = {
                                    step = if (TurnoRules.pedeKm(snapshot.estado, target!!)) Step.KM else {
                                        onRequestTransition(RequisicaoTransicao(to = target!!))
                                        Step.MENU
                                    }
                                }
                            )
                            Step.MOTIVO -> MotivoStep(
                                currentMotivo = motivo,
                                currentMotivoOutro = motivoOutro,
                                onMotivoChanged = { m, text ->
                                    motivo = m
                                    motivoOutro = text
                                },
                                onContinue = { step = Step.KM },
                                canContinue = podeContinuarMotivo
                            )
                            Step.KM -> KmStep(
                                snapshot = snapshot,
                                targetState = requireNotNull(target),
                                kmTotalFromPhoto = kmTotalFromPhoto,
                                manualKm = kmOutro,
                                onManualKmChange = { kmOutro = it },
                                onOpenCamera = { onOpenOdometerCamera(target, motivo, motivoOutro) },
                                onConfirm = { confirmarKmDoTopo() },
                                canConfirm = podeConfirmarKm
                            )
                            Step.RECIBO_FINAL -> ReciboFinalStep(
                                deltaKm = savedDeltaKm ?: 0,
                                isDescansoSemanal = isDescansoSemanal,
                                onDescansoChanged = { isDescansoSemanal = it },
                                onConfirm = {
                                    pendingRequest?.let { req ->
                                        onRequestTransition(req.copy(isDescansoSemanal = isDescansoSemanal))
                                    }
                                    onDismiss()
                                }
                            )
                            else -> {}
                        }
                    }
                }
            }
        }
    }
}