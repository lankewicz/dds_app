// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TurnoControlDialog.kt
// Função: Dialog de controle para ações de jornada. Provê interface para iniciar, pausar e 
//         finalizar turnos, exibindo alertas sobre regras de descanso CLT.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.platform.LocalConfiguration
import com.chicoeletro.dds.features.turno.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private enum class Step { MENU, MOTIVO, KM, RECIBO_FINAL, AVISO_INTERJORNADA }

@Composable
fun TurnoControlDialog(
    snapshot: TurnoSnapshot,
    onDismiss: () -> Unit,
    onSaveNocSs: (String?) -> Unit,
    onRequestTransition: (RequisicaoTransicao) -> Unit,
    onOpenOdometerCamera: (EstadoTurno?, MotivoDeslocamentoEspecial?, String) -> Unit = { _, _, _ -> },
    prefillKmTotal: String? = null,
    startAtKmTarget: EstadoTurno? = null,
    prefillMotivo: MotivoDeslocamentoEspecial? = null,
    prefillMotivoOutro: String? = null
) {
    // Initial State Logic
    var step by remember(startAtKmTarget) {
        mutableStateOf(if (startAtKmTarget != null) Step.KM else Step.MENU)
    }
    var target by remember(startAtKmTarget) { mutableStateOf(startAtKmTarget) }

    // Final Receipt State
    var savedDeltaKm by remember { mutableStateOf<Int?>(null) }

    // Data State
    var motivo by remember(prefillMotivo) { mutableStateOf(prefillMotivo) }
    var motivoOutro by remember(prefillMotivoOutro) { mutableStateOf(prefillMotivoOutro ?: "") }

    // KM State
    var kmOutro by remember { mutableStateOf("") }
    var kmTotalFromPhoto by remember { mutableStateOf<Long?>(null) }

    // Interjornada State
    var isDescansoSemanal by remember { mutableStateOf(false) }
    var pendingRequest by remember { mutableStateOf<RequisicaoTransicao?>(null) }

    // Apply Prefill from OCR if available
    LaunchedEffect(prefillKmTotal) {
        val total = prefillKmTotal?.filter { it.isDigit() }?.take(9)?.toLongOrNull()
        if (total != null) {
            kmTotalFromPhoto = total
            kmOutro = "" // Clear manual input if photo is present
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
            else -> kmOutro.trim().toIntOrNull()
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
                onDismiss()
            }
        }
    }
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = MaterialTheme.shapes.large,
            tonalElevation = 4.dp,
            modifier = Modifier
                .padding(16.dp)
                .widthIn(min = 480.dp, max = 700.dp)
        ) {
            Column(
                Modifier.padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier.width(48.dp),
                        contentAlignment = Alignment.CenterStart
                    ) {
                        if (step != Step.RECIBO_FINAL) {
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
                                        Step.RECIBO_FINAL -> {} // Inalcançável
                                    }
                                }
                            ) {
                                Icon(
                                    imageVector = Icons.Filled.ArrowBack,
                                    contentDescription = "Voltar"
                                )
                            }
                        }
                    }

                    Column(
                        modifier = Modifier.weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            if (step == Step.RECIBO_FINAL) "Recibo do Turno" else "Controle de Turno",
                            style = MaterialTheme.typography.titleMedium
                        )
                        if (step != Step.RECIBO_FINAL) {
                            Text(
                                "Status atual: ${snapshot.estado.name}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    Box(
                        modifier = Modifier.width(48.dp),
                        contentAlignment = Alignment.CenterEnd
                    ) {
                        Surface(
                            onClick = onDismiss,
                            shape = androidx.compose.foundation.shape.RoundedCornerShape(0.dp),
                            color = androidx.compose.ui.graphics.Color(0xFFE81123),
                            modifier = Modifier.size(32.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    imageVector = Icons.Filled.Close,
                                    contentDescription = "Fechar",
                                    tint = androidx.compose.ui.graphics.Color.White,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState())
                ) {
                    // Step Content Switcher
                    when (step) {
                        Step.MENU -> MenuStep(
                            snapshot = snapshot,
                            onDismiss = onDismiss,
                            onSaveNocSs = onSaveNocSs,
                            onSelectTarget = { newTarget ->
                                target = newTarget
                                // Validação de interjornada APENAS ao ABRIR um turno
                                if (newTarget == EstadoTurno.ABERTO && snapshot.estado == EstadoTurno.FECHADO) {
                                    val lastClosed = snapshot.lastClosedAtMs
                                    if (lastClosed != null) {
                                        val now = System.currentTimeMillis()
                                        val reqHours = if (snapshot.lastWasDescansoSemanal) 24 else 11
                                        val reqMillis = reqHours * 60 * 60 * 1000L
                                        if (now - lastClosed < reqMillis) {
                                            step = Step.AVISO_INTERJORNADA
                                            return@MenuStep
                                        }
                                    }
                                }

                                step = when {
                                    newTarget == EstadoTurno.DESLOCAMENTO_ESPECIAL -> Step.MOTIVO
                                    TurnoRules.pedeKm(snapshot.estado, newTarget) -> Step.KM
                                    else -> {
                                        onRequestTransition(RequisicaoTransicao(to = newTarget))
                                        onDismiss()
                                        Step.MENU // Reset (technically unreachable as dialog closes)
                                    }
                                }
                            },
                        )

                        Step.AVISO_INTERJORNADA -> InterjornadaNotice(
                            snapshot = snapshot,
                            onProceed = {
                                step = if (TurnoRules.pedeKm(snapshot.estado, target!!)) Step.KM else {
                                    onRequestTransition(RequisicaoTransicao(to = target!!))
                                    onDismiss()
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
                    }
                }
            }
        }
    }
}

// --- Sub-Components for cleaner structure ---

@Composable
private fun MenuStep(
    snapshot: TurnoSnapshot,
    onDismiss: () -> Unit,
    onSaveNocSs: (String?) -> Unit,
    onSelectTarget: (EstadoTurno) -> Unit,
    onPasteNoc: (() -> Unit)? = null
) {
    var noc by remember { mutableStateOf(snapshot.nocSs ?: "") }
    var nocError by remember { mutableStateOf<String?>(null) }
    var isEditingNoc by remember { mutableStateOf(false) }

    val focusManager = LocalFocusManager.current
    val clipboard = LocalClipboardManager.current

    // Calculate options based on state logic
    val options = remember(snapshot.estado) {
        when (snapshot.estado) {
            EstadoTurno.FECHADO -> listOf(EstadoTurno.ABERTO, EstadoTurno.DESLOCAMENTO_ESPECIAL)
            EstadoTurno.ABERTO -> listOf(EstadoTurno.FECHADO, EstadoTurno.INTERVALO)
            EstadoTurno.INTERVALO -> listOf(EstadoTurno.ABERTO, EstadoTurno.DESLOCAMENTO_ESPECIAL)
            EstadoTurno.DESLOCAMENTO_ESPECIAL -> listOf(EstadoTurno.FECHADO, EstadoTurno.ABERTO)
        }
    }

    // NOC/SS Input (Only for ABERTO)
    if (snapshot.estado == EstadoTurno.ABERTO) {
        OutlinedTextField(
            value = noc,
            onValueChange = {
                noc = it
                nocError = null
            },
            label = { Text("NOC/SS (Opcional)") },
            isError = nocError != null,
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { isEditingNoc = it.isFocused },
            trailingIcon = {
                IconButton(onClick = {
                    // Cola do clipboard e normaliza (remove espaços/quebras)
                    val clip = clipboard.getText()?.text?.trim().orEmpty()
                    if (clip.isNotEmpty()) {
                        val normalized = clip
                            .replace("\n", " ")
                            .replace("\r", " ")
                            .replace("\t", " ")
                            .replace(" ", "")
                        noc = normalized
                        nocError = null
                    }
                }) {
                    Icon(Icons.Filled.ContentPaste, "Colar NOC/SS")
                }
            }
        )
        if (nocError != null) {
            Text(nocError!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = {
                val v = noc.trim()
                if (v.isNotEmpty() && !TurnoRules.isNocSsValido(v)) {
                    nocError = "Formato inválido"
                } else {
                    focusManager.clearFocus()
                    onSaveNocSs(v.ifEmpty { null })
                    onDismiss()
                }
            }) { Text("Salvar NOC/SS") }
        }
    }

    // Hide Action Buttons if editing NOC to prevent visual clutter
    AnimatedVisibility(visible = !isEditingNoc, enter = fadeIn(), exit = fadeOut()) {
        Column {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("Selecione a Ação", style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(8.dp))

            fun labelFor(st: EstadoTurno): String {
                return when (st) {
                    EstadoTurno.FECHADO -> "FECHAR TURNO"
                    EstadoTurno.ABERTO -> if (snapshot.estado == EstadoTurno.FECHADO) "ABRIR TURNO" else "RETOMAR TURNO"
                    EstadoTurno.INTERVALO -> "INICIAR INTERVALO"
                    EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO"
                }
            }

            options.forEach { st ->
                Button(
                    onClick = { onSelectTarget(st) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp)
                ) { Text(labelFor(st)) }
            }
        }
    }
}

@Composable
private fun MotivoStep(
    currentMotivo: MotivoDeslocamentoEspecial?,
    currentMotivoOutro: String,
    onMotivoChanged: (MotivoDeslocamentoEspecial, String) -> Unit,
    onContinue: () -> Unit,
    canContinue: Boolean
) {
    Text("Motivo do Deslocamento", style = MaterialTheme.typography.labelLarge)
    Spacer(Modifier.height(8.dp))

    val all = listOf(
        MotivoDeslocamentoEspecial.ABASTECIMENTO to "Abastecimento",
        MotivoDeslocamentoEspecial.BORRACHARIA to "Borracharia",
        MotivoDeslocamentoEspecial.OFICINA_AUTO_ELETRICA to "Oficina/Auto-Elétrica",
        MotivoDeslocamentoEspecial.ADMINISTRATIVO_PATO_BRANCO to "Adm. Pato Branco",
        MotivoDeslocamentoEspecial.VIAGEM_COPEL to "Viagem Copel",
        MotivoDeslocamentoEspecial.OUTRO to "Outro"
    )

    Column {
        all.forEach { (m, label) ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .selectable(selected = (currentMotivo == m), onClick = { onMotivoChanged(m, currentMotivoOutro) })
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                RadioButton(selected = (currentMotivo == m), onClick = { onMotivoChanged(m, currentMotivoOutro) })
                Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(start = 8.dp))
            }
        }

        if (currentMotivo == MotivoDeslocamentoEspecial.OUTRO) {
            OutlinedTextField(
                value = currentMotivoOutro,
                onValueChange = { onMotivoChanged(currentMotivo!!, it) },
                label = { Text("Informe o motivo") },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
            )
        }

        Spacer(Modifier.height(24.dp))
        Button(
            onClick = onContinue,
            enabled = canContinue,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Continuar")
        }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun KmStep(
    snapshot: TurnoSnapshot,
    targetState: EstadoTurno,
    kmTotalFromPhoto: Long?,
    manualKm: String,
    onManualKmChange: (String) -> Unit,
    onOpenCamera: () -> Unit,
    onConfirm: () -> Unit,
    canConfirm: Boolean
) {
    Text("Informar Quilometragem", style = MaterialTheme.typography.labelLarge)
    Spacer(Modifier.height(8.dp))

    // Helper to calculate Delta for preview
    fun calculateDeltaDisplay(): Int? {
        val start = snapshot.kmInicioLast3 ?: return null
        val endLast3 = kmTotalFromPhoto?.rem(1000)?.toInt() ?: manualKm.toIntOrNull() ?: return null

        // Rollover logic: 0..999
        val raw = endLast3 - start
        return if (raw >= 0) raw else raw + 1000
    }

    if (kmTotalFromPhoto != null) {
        // --- PHOTO MODE (Read Only) ---
        OutlinedTextField(
            value = kmTotalFromPhoto.toString(),
            onValueChange = {},
            label = { Text("KM Total (via Câmera)") },
            enabled = false, // Read-only
            modifier = Modifier.fillMaxWidth(),
            colors = OutlinedTextFieldDefaults.colors(
                disabledTextColor = MaterialTheme.colorScheme.onSurface,
                disabledLabelColor = MaterialTheme.colorScheme.primary
            ),
            trailingIcon = {
                IconButton(onClick = onOpenCamera) {
                    Icon(Icons.Filled.PhotoCamera, "Recapturar", tint = MaterialTheme.colorScheme.primary)
                }
            }
        )
        Text("Leitura automática via OCR. A foto é opcional neste fluxo.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
    } else {
        // --- MANUAL MODE (Last 3 or TOTAL) ---
        OutlinedTextField(
            value = manualKm,
            onValueChange = { input ->
                if (input.all { it.isDigit() } && input.length <= 7) {
                    onManualKmChange(input)
                }
            },
            label = { Text("KM (3 últimos dígitos ou total)") },
            modifier = Modifier.fillMaxWidth(),
            trailingIcon = {
                IconButton(onClick = onOpenCamera) {
                    Icon(Icons.Filled.PhotoCamera, "Usar Câmera")
                }
            }
        )
        Text("Você pode digitar os 3 últimos números, informar o KM total ou usar a câmera. A foto é opcional.", style = MaterialTheme.typography.bodySmall)
    }

    // Delta Preview (Closing Shift)
    if (snapshot.estado == EstadoTurno.ABERTO && targetState == EstadoTurno.FECHADO) {
        calculateDeltaDisplay()?.let { delta ->
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
                modifier = Modifier.padding(top = 12.dp).fillMaxWidth()
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text("Resumo do Turno", style = MaterialTheme.typography.labelMedium)
                    Text("Percorrido: $delta KM", fontWeight = FontWeight.Bold)
                }
            }
        }
    }

    Spacer(Modifier.height(24.dp))
    Button(
        onClick = onConfirm,
        enabled = canConfirm,
        modifier = Modifier.fillMaxWidth()
    ) {
        Text("Confirmar")
    }
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun ReciboFinalStep(
    deltaKm: Int,
    isDescansoSemanal: Boolean,
    onDescansoChanged: (Boolean) -> Unit,
    onConfirm: () -> Unit
) {
    val currentTime = remember<Long> { System.currentTimeMillis() }

    val futureDate = remember(isDescansoSemanal, currentTime) {
        val hoursToAdd = if (isDescansoSemanal) 24 else 11 // Art 67 (24h) e Art 66 (11h)
        Date(currentTime + (hoursToAdd * 60 * 60 * 1000L))
    }

    val showPredictionBanner = remember(futureDate) {
        val cal = java.util.Calendar.getInstance().apply { time = futureDate }
        val hour = cal.get(java.util.Calendar.HOUR_OF_DAY)
        hour >= 7
    }

    val displayDate = remember(isDescansoSemanal, futureDate) {
        val cal = java.util.Calendar.getInstance().apply { time = futureDate }
        val hour = cal.get(java.util.Calendar.HOUR_OF_DAY)
        val dateFormat = SimpleDateFormat("dd/MM", Locale("pt", "BR"))
        val timeFormat = SimpleDateFormat("HH:mm", Locale("pt", "BR"))
        
        if (isDescansoSemanal) {
            "Dia ${dateFormat.format(futureDate)}"
        } else {
            if (hour < 7) {
                "Dia ${dateFormat.format(futureDate)}"
            } else {
                "Dia ${dateFormat.format(futureDate)} às ${timeFormat.format(futureDate)}"
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            imageVector = Icons.Filled.CheckCircle,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(64.dp)
        )
        Spacer(Modifier.height(16.dp))
        Text(
            text = "Turno Encerrado!",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Você rodou $deltaKm KM neste turno.",
            style = MaterialTheme.typography.bodyLarge
        )
        
        Spacer(Modifier.height(24.dp))
        
        if (showPredictionBanner) {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(
                        text = "Horário Previsto para o Próximo Turno (Interjornada):",
                        style = MaterialTheme.typography.labelMedium
                    )
                    Spacer(Modifier.height(4.dp))
                    
                    Text(
                        text = displayDate, 
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyLarge
                    )
                }
            }

            Spacer(Modifier.height(16.dp))
        }

        Card(
            colors = CardDefaults.cardColors(
                containerColor = if (isDescansoSemanal) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant
            ),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp),
            shape = MaterialTheme.shapes.medium
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .selectable(selected = isDescansoSemanal, onClick = { onDescansoChanged(!isDescansoSemanal) })
                    .padding(16.dp)
            ) {
                Switch(
                    checked = isDescansoSemanal,
                    onCheckedChange = null // Handled by Row selectable
                )
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(
                        "Descanso Semanal (Art. 67)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (isDescansoSemanal) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        "Adiciona reposição de 24hrs",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (isDescansoSemanal) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = onConfirm,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Concluir Fechamento")
        }
    }
}