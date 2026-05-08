// Módulo: app/src/main/java/com/chicoeletro/dds/features/viewer/ViewerScreen.kt
// Função: Tela de apresentação do conteúdo do DDS. Exibe os slides do treinamento, gerencia 
//         a navegação entre páginas e valida condições para habilitação do treinamento.
// Tecnologias: Jetpack Compose, Coil (Imagens), Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:



package com.chicoeletro.dds.features.viewer
// ------------------------------------------------------------------
// Tipos auxiliares (precisam ser TOP-LEVEL; Kotlin não permite enum local)
// ------------------------------------------------------------------


import android.net.Uri
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.filled.VideoCall
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.LocalLifecycleOwner
import coil.compose.rememberAsyncImagePainter
import coil.request.CachePolicy
import coil.request.ImageRequest
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import com.chicoeletro.dds.ui.sections.TrainingStatus
import com.chicoeletro.dds.components.FooterStatus
import com.chicoeletro.dds.components.FooterStatusKind
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private enum class WhyDialogMode {
    MIN_TIME,     // DDS normal: regra dos 2 minutos
    ONLINE_LOCK   // DDS online: bloqueio até liberar a janela (15 min)
}

@Composable
fun ViewerScreen(
    trainingId: String,
    viewModel: ViewerViewModel,
    status: TrainingStatus?,
    canConclude: Boolean = true,
    onOpenForm: () -> Unit,
    onEnterAgora: () -> Unit = {},
    onStatusChanged: (FooterStatus?) -> Unit = {},
    forceLandscape: Boolean = true
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    val ui by viewModel.ui.collectAsState()

    val currentIndex = ui.currentIndex
    val readOnlyMode = !canConclude

// ==========================================================
    // DDS ONLINE: liberação do acesso ao Agora apenas 15 min antes
    // ==========================================================
    val isOnlineDDS = remember(trainingId) {
        trainingId.contains("DDS-ONLINE", ignoreCase = true) ||
        trainingId.contains("DDS ONLINE", ignoreCase = true) ||
        trainingId.contains("ONLINE", ignoreCase = true)
    }

    // ticker simples para atualizar contagem (sem depender de recomposição externa)
    var nowMs by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(isOnlineDDS) {
        if (!isOnlineDDS) return@LaunchedEffect
        while (true) {
            nowMs = System.currentTimeMillis()
            delay(15_000) // atualiza a cada 15s (suficiente p/ "faltam X minutos")
        }
    }

    val scheduledStartMs = remember(trainingId) { parseScheduledStartMillis(trainingId) }
    val remainingMs = remember(nowMs, scheduledStartMs) {
        if (scheduledStartMs == null) null else (scheduledStartMs - nowMs)
    }
    val remainingMin = remember(remainingMs) {
        remainingMs?.let { ((it + 59_999) / 60_000).toInt() } // ceil em minutos
    }
    val canEnterOnline = remember(isOnlineDDS, remainingMs) {
        if (!isOnlineDDS) true
        else {
            // Se não conseguimos inferir horário, não bloqueia (fail-open),
            // para evitar impedir o acesso por dado incompleto.
            if (remainingMs == null) true
            else remainingMs <= 15L * 60_000L
        }
    }

    fun formatRemainingForMessage(min: Int?): String {
        if (min == null) return "em breve"
        return when {
            min <= 0 -> "agora"
            min == 1 -> "em 1 minuto"
            else -> "em $min minutos"
        }
    }


    // Tela cheia
    var fullscreen by remember { mutableStateOf(false) }
    // 🔁 Troca de treinamento → zera sessão atual
    LaunchedEffect(trainingId) {
        viewModel.resetSession()
    }

    // 🔄 Auto-start removido a pedido do usuário: agora exige clique em "INICIAR"
    // (O LaunchedEffect antigo que iniciava automaticamente foi deletado)

    // Carrega no start e observa mudanças na pasta
    LaunchedEffect(trainingId) {
        viewModel.load(trainingId)
        // Se arquivos chegarem depois (sync), recarrega
        scope.launch {
            viewModel.observeFolder(trainingId).collect {
                viewModel.load(trainingId)
            }
        }
    }
    // Observa ciclo de vida p/ pausar/retomar timers (foreground/background)
    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_START -> viewModel.onAppForegroundChanged(true)
                Lifecycle.Event.ON_STOP  -> viewModel.onAppForegroundChanged(false)
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs) }
    }

    val currentUri: Uri? = ui.images.getOrNull(currentIndex)
    val painter = currentUri?.let {
        rememberAsyncImagePainter(
            ImageRequest.Builder(context)
                .data(it)
                .diskCachePolicy(CachePolicy.ENABLED)   // ok para arquivos locais
                .memoryCachePolicy(CachePolicy.ENABLED)
                .crossfade(true)
                .build()
        )
    }
    // Texto de status que vai para o rodapé (junto da versão)
    val statusText: String? = remember(
        status,
        ui.elapsedMs,
        ui.sessionId,
        ui.conclusionInfo,
        ui.images,
        readOnlyMode
    ) {
        if (ui.images.isEmpty()) return@remember null

        val inner = when {
            status != null -> {
                // Veio do TrainingStatus (onCompleted)
                "Concluído em ${status.dataConclusao} às ${status.horaConclusao} • Tempo: ${status.duracao}"
            }
            ui.conclusionInfo != null -> {
                ui.conclusionInfo!!
            }
            readOnlyMode -> {
                return@remember null
            }
            else -> {
                "Tempo: ${formatMs(ui.elapsedMs)}  •  Sessão: ${ui.sessionId.take(8)}"
            }
        }
        "Status: $inner"
    }

    // Rodapé com severidade:
    // - WARNING quando houver blockMessage (tempo mínimo / ordem)
    // - SUCCESS quando concluído (status vindo do TrainingStatus ou conclusão local)
    // - NORMAL caso contrário
    val footerStatus: FooterStatus? = remember(
        ui.blockMessage,
        statusText,
        status,
        ui.conclusionInfo,
        ui.images,
        readOnlyMode
    ) {
        if (ui.images.isEmpty()) return@remember null
        when {
            !ui.blockMessage.isNullOrBlank() ->
                FooterStatus(ui.blockMessage!!, FooterStatusKind.WARNING)
            status != null || ui.conclusionInfo != null ->
                FooterStatus(statusText ?: "", FooterStatusKind.SUCCESS)
            readOnlyMode ->
                null
            else ->
                FooterStatus(statusText ?: "", FooterStatusKind.NORMAL)
        }
    }

    LaunchedEffect(footerStatus) { onStatusChanged(footerStatus) }


    // Activity já está travada em paisagem; não precisamos de fallback
    Column(Modifier.fillMaxSize().pointerInput(Unit) {
        detectTapGestures(onTap = { viewModel.onUserInteraction() })
    }) {
        // Alerta de Inatividade (8 min+)
        if (ui.inactivityWarning) {
            Surface(
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                color = MaterialTheme.colorScheme.errorContainer,
                shape = RoundedCornerShape(8.dp)
            ) {
                Row(
                    Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "ALERTA: O tempo limite do treinamento está terminando! Conclua agora para não perder o progresso.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        fontWeight = FontWeight.Bold,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }

        // Área principal da imagem ou placeholder de Início
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            contentAlignment = Alignment.Center
        ) {
            when {
                ui.isLoading -> CircularProgressIndicator()
                ui.error != null && ui.images.isEmpty() ->
                    Text(ui.error ?: "Erro ao carregar", color = MaterialTheme.colorScheme.error)
                ui.images.isEmpty() ->
                    Text("Sem conteúdo local para $trainingId")
                else -> {
                    painter?.let {
                        Image(
                            painter = it,
                            contentDescription = null,
                            modifier = Modifier
                                .fillMaxSize()
                                .clickable { fullscreen = true }
                        )
                    }
                }
            }
        }
        if (readOnlyMode && ui.images.isNotEmpty()) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 6.dp),
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.secondaryContainer,
                contentColor = MaterialTheme.colorScheme.onSecondaryContainer
            ) {
                Text(
                    text = "DDS antigo — somente visualização",
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }


        // Barra de navegação / paginação
        if (ui.images.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp)
                    .padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // ⬅️ Anterior (usa VM para mover)
                OutlinedButton(
                    onClick = {
                        val target = (currentIndex - 1).coerceAtLeast(0)
                        if (readOnlyMode) viewModel.showSlideReadOnly(target) else viewModel.requestGoToSlide(target)
                    },
                    enabled = currentIndex > 0
                ) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Anterior") }

                Text("${currentIndex + 1} de ${ui.images.size}")

                // ➡️ Próximo / ✅ Concluir / 🚀 Iniciar
                val isLast = currentIndex >= ui.images.lastIndex && ui.images.isNotEmpty()
                val jaConcluido = status != null
                val podeIniciar = !ui.started && canConclude && !jaConcluido

                when {
                    podeIniciar -> {
                        // 🚀 Botão INICIAR (somente se puder concluir e não tiver começado)
                        Button(
                            onClick = {
                                viewModel.onStartPressed(totalSlides = ui.images.size)
                                fullscreen = true
                            },
                            modifier = Modifier.height(52.dp).widthIn(min = 160.dp),
                            shape = RoundedCornerShape(28.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color(0xFF2E7D32),
                                contentColor = Color.White
                            ),
                            elevation = ButtonDefaults.buttonElevation(defaultElevation = 4.dp)
                        ) {
                            Text("INICIAR", fontWeight = FontWeight.Bold)
                            Spacer(Modifier.width(6.dp))
                            Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null)
                        }
                    }
                    !isLast -> {
                        // ➡️ Próximo (Sempre disponível se não for o último, permitindo visualização de treinamentos antigos)
                        Button(
                            onClick = {
                                val target = (currentIndex + 1).coerceAtMost(ui.images.lastIndex)
                                // Se já concluiu, está expirado ou não foi iniciado formalmente, navega em modo read-only
                                if (readOnlyMode || jaConcluido || !ui.started) {
                                    viewModel.showSlideReadOnly(target)
                                } else {
                                    viewModel.requestGoToSlide(target)
                                }
                            },
                            modifier = Modifier.height(52.dp).widthIn(min = 160.dp),
                            shape = RoundedCornerShape(28.dp),
                            elevation = ButtonDefaults.buttonElevation(defaultElevation = 2.dp)
                        ) {
                            Text("Próximo")
                            Spacer(Modifier.width(6.dp))
                            Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = "Próximo")
                        }
                    }
                    else -> {
                        // Slide Final: Concluir ou Mensagem de Status
                        if (jaConcluido) {
                            Text("DDS já executado", style = MaterialTheme.typography.bodyMedium, color = Color(0xFF2E7D32))
                        } else if (!canConclude) {
                            Text("Treinamento expirado", style = MaterialTheme.typography.bodyMedium)
                        } else if (!ui.started) {
                            // Caso raro: treinamento válido mas não iniciado e chegou ao fim (via navegação manual anterior)
                            Text("Não iniciado", style = MaterialTheme.typography.bodyMedium)
                        } else {
                            // ✅ Concluir / DDS Online (último slide)
                            var showWhyDialog by remember { mutableStateOf(false) }
                            var whyMode by remember { mutableStateOf(WhyDialogMode.MIN_TIME) }
                            var remainMs by remember { mutableStateOf(0L) }

                            val canFinish = ui.canTakePhoto && !ui.invalidated
                            val concluido = status != null

                            Button(
                                onClick = {
                                    if (isOnlineDDS) {
                                        if (canEnterOnline) onEnterAgora()
                                        else {
                                            whyMode = WhyDialogMode.ONLINE_LOCK
                                            showWhyDialog = true
                                        }
                                    } else {
                                        val minTotalMs = 120_000L
                                        val falta = minTotalMs - ui.elapsedMs
                                        if (falta > 0L) {
                                            remainMs = falta
                                            whyMode = WhyDialogMode.MIN_TIME
                                            showWhyDialog = true
                                        } else if (canFinish) {
                                            onOpenForm()
                                        } else {
                                            // 🚨 Caso o tempo total tenha dado (falta <= 0) mas o tempo por slide
                                            // ou visita de todos os slides ainda não tenha sido cumprido.
                                            remainMs = 0
                                            whyMode = WhyDialogMode.MIN_TIME
                                            showWhyDialog = true
                                        }
                                    }
                                },
                                enabled = !concluido && (!isOnlineDDS || canEnterOnline),
                                modifier = Modifier.height(56.dp).widthIn(min = 180.dp),
                                shape = RoundedCornerShape(28.dp),
                                elevation = ButtonDefaults.buttonElevation(defaultElevation = 3.dp)
                            ) {
                                if (isOnlineDDS) {
                                    Text("Entrar no DDS Online")
                                    Spacer(Modifier.width(6.dp))
                                    Icon(Icons.Filled.VideoCall, contentDescription = "Entrar no DDS Online")
                                } else {
                                    Text("Concluir")
                                    Spacer(Modifier.width(6.dp))
                                    Icon(Icons.Filled.Check, contentDescription = "Concluir")
                                }
                            }

                            if (showWhyDialog) {
                                AlertDialog(
                                    onDismissRequest = { showWhyDialog = false },
                                    confirmButton = {
                                        Button(onClick = { showWhyDialog = false }) { Text("Entendi") }
                                    },
                                    title = {
                                        Text(if (whyMode == WhyDialogMode.MIN_TIME) "Quase lá! ⏱️" else "DDS Online programado")
                                    },
                                    text = {
                                        val msg = when (whyMode) {
                                            WhyDialogMode.MIN_TIME ->
                                                "Para garantir atenção e retenção do conteúdo, este DDS requer pelo menos 2 minutos de dedicação.\n\nContinue discutindo o tema com a equipe; assim que completar o tempo, você poderá concluir."
                                            WhyDialogMode.ONLINE_LOCK ->
                                                if (scheduledStartMs == null) "Este DDS é online. O acesso é liberado 15 minutos antes do horário agendado."
                                                else "O acesso ao DDS Online é liberado 15 minutos antes do horário agendado.\n\n⏳ Liberação ${formatRemainingForMessage(remainingMin)}."
                                        }
                                        Text(msg)
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // -------- Tela cheia com navegação completa ----------
    if (fullscreen && painter != null) {
        Dialog(
            onDismissRequest = { fullscreen = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)
        ) {
            val scale = remember { mutableFloatStateOf(1f) }
            val offset = remember { mutableStateOf(Offset.Zero) }
            val origin = remember { mutableStateOf(TransformOrigin.Center) }

            Scaffold(
                containerColor = Color.Black,
                modifier = Modifier.fillMaxSize(),
                topBar = {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        horizontalArrangement = Arrangement.End
                    ) {
                        IconButton(onClick = { fullscreen = false }) {
                            Icon(Icons.Filled.Close, "Fechar", tint = Color.White)
                        }
                    }
                },
                bottomBar = {
                    // Reutiliza a lógica de navegação dentro do Scaffold do diálogo
                    Surface(
                        color = Color.Black.copy(alpha = 0.7f),
                        contentColor = Color.White
                    ) {
                        Column {
                            // Status bar superior (opcional no fullscreen, mas útil p/ tempo)
                            footerStatus?.let {
                                Text(
                                    text = it.text,
                                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = if (it.kind == FooterStatusKind.WARNING) Color.Yellow else Color.White
                                )
                            }
                            
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(64.dp)
                                    .padding(horizontal = 16.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Anterior
                                IconButton(
                                    onClick = {
                                        val target = (currentIndex - 1).coerceAtLeast(0)
                                        if (readOnlyMode) viewModel.showSlideReadOnly(target) else viewModel.requestGoToSlide(target)
                                    },
                                    enabled = currentIndex > 0
                                ) { 
                                    Icon(
                                        Icons.AutoMirrored.Filled.ArrowBack, 
                                        "Anterior", 
                                        tint = if (currentIndex > 0) Color.White else Color.Gray 
                                    ) 
                                }

                                Text("${currentIndex + 1} de ${ui.images.size}", color = Color.White)

                                // Próximo / Concluir
                                val isLast = currentIndex >= ui.images.lastIndex && ui.images.isNotEmpty()
                                if (!isLast) {
                                    Button(
                                        onClick = {
                                            val target = (currentIndex + 1).coerceAtMost(ui.images.lastIndex)
                                            if (readOnlyMode) viewModel.showSlideReadOnly(target) else viewModel.requestGoToSlide(target)
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                                    ) {
                                        Text("Próximo")
                                        Icon(Icons.AutoMirrored.Filled.ArrowForward, null)
                                    }
                                } else if (!readOnlyMode && canConclude) {
                                    // REGRAS DE CONCLUSÃO NO FULLSCREEN
                                    var showWhyDialogFull by remember { mutableStateOf(false) }
                                    var whyModeFull by remember { mutableStateOf(WhyDialogMode.MIN_TIME) }
                                    
                                    Button(
                                        onClick = {
                                            if (isOnlineDDS) {
                                                if (canEnterOnline) {
                                                    fullscreen = false
                                                    onEnterAgora()
                                                } else {
                                                    whyModeFull = WhyDialogMode.ONLINE_LOCK
                                                    showWhyDialogFull = true
                                                }
                                            } else {
                                                val minTotalMs = 120_000L
                                                val falta = minTotalMs - ui.elapsedMs
                                                if (falta > 0L) {
                                                    whyModeFull = WhyDialogMode.MIN_TIME
                                                    showWhyDialogFull = true
                                                } else if (ui.canTakePhoto && !ui.invalidated) {
                                                    fullscreen = false
                                                    onOpenForm()
                                                } else {
                                                    // Feedback para quando o tempo total deu mas falta o tempo por slide
                                                    whyModeFull = WhyDialogMode.MIN_TIME
                                                    showWhyDialogFull = true
                                                }
                                            }
                                        },
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = if (isOnlineDDS) MaterialTheme.colorScheme.secondary else Color(0xFF2E7D32)
                                        )
                                    ) {
                                        if (isOnlineDDS) {
                                            Text("Acessar Online")
                                            Icon(Icons.Filled.VideoCall, null)
                                        } else {
                                            Text("Concluir")
                                            Icon(Icons.Filled.Check, null)
                                        }
                                    }

                                    if (showWhyDialogFull) {
                                        AlertDialog(
                                            onDismissRequest = { showWhyDialogFull = false },
                                            confirmButton = { Button(onClick = { showWhyDialogFull = false }) { Text("OK") } },
                                            title = { Text(if (whyModeFull == WhyDialogMode.MIN_TIME) "Quase lá!" else "DDS Agendado") },
                                            text = {
                                                if (whyModeFull == WhyDialogMode.MIN_TIME) {
                                                    Text("Este DDS requer 2 minutos de dedicação para garantir a fixação do conteúdo.")
                                                } else {
                                                    Text("O acesso ao DDS Online será liberado 15min antes do horário agendado.")
                                                }
                                            }
                                        )
                                    }
                                } else {
                                    Spacer(Modifier.width(48.dp))
                                }
                            }
                        }
                    }
                }
            ) { padding ->
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    if (ui.inactivityWarning) {
                        Surface(
                            modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth().padding(16.dp),
                            color = Color.Red.copy(alpha = 0.8f),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text(
                                "⚠️ ATENÇÃO: CONCLUA O DDS AGORA PARA NÃO PERDER O TEMPO DECORRIDO!",
                                color = Color.White,
                                modifier = Modifier.padding(12.dp),
                                textAlign = TextAlign.Center,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    Crossfade(targetState = painter, label = "viewer-fullscreen") { p ->
                        Image(
                            painter = p,
                            contentDescription = null,
                            modifier = Modifier
                                .fillMaxSize()
                                .graphicsLayer(
                                    scaleX = scale.floatValue,
                                    scaleY = scale.floatValue,
                                    translationX = offset.value.x,
                                    translationY = offset.value.y,
                                    transformOrigin = origin.value
                                )
                                .pointerInput(Unit) {
                                    detectTransformGestures { centroid, pan, zoom, _ ->
                                        scale.floatValue = (scale.floatValue * zoom).coerceIn(1f, 5f)
                                        offset.value += pan
                                        origin.value = TransformOrigin(
                                            pivotFractionX = centroid.x / size.width,
                                            pivotFractionY = centroid.y / size.height
                                        )
                                    }
                                }
                                .pointerInput(Unit) {
                                    detectTapGestures(onDoubleTap = {
                                        scale.floatValue = 1f
                                        offset.value = Offset.Zero
                                        origin.value = TransformOrigin.Center
                                    })
                                }
                        )
                    }
                }
            }
        }
    }
}

fun formatMs(ms: Long): String {
        val s = ms / 1000
        val m = s / 60
        val sec = s % 60
        return "%02d:%02d".format(m, sec)
}

/**
* Tenta inferir o horário programado a partir do trainingId.
*
* Estratégia (robusta o suficiente para agora):
*  1) Data: tenta pegar o prefixo "YYYY-MM-DD" antes do primeiro " - " (padrão já usado no app).
*  2) Hora: tenta encontrar um token HHmm (ex.: "1507") no final do texto ou após hífen.
*
* Se não conseguir parsear, retorna null (o fluxo fail-open libera o botão).
*/
private fun parseScheduledStartMillis(trainingId: String): Long? {
    return runCatching {
        val zone = ZoneId.of("America/Sao_Paulo")

        // 1) Data (se existir)
        val datePart = trainingId.substringBefore(" - ").trim()
        val date = runCatching { LocalDate.parse(datePart, DateTimeFormatter.ISO_LOCAL_DATE) }
            .getOrNull()
            ?: return null

        // 2) Hora (procura HHmm no final ou após hífen)
        val hhmm = Regex("""(\d{3,4})\s*$""")
            .find(trainingId)
            ?.groupValues
            ?.getOrNull(1)
            ?.padStart(4, '0')
            ?: return null

        val hh = hhmm.substring(0, 2).toInt()
        val mm = hhmm.substring(2, 4).toInt()
        val time = LocalTime.of(hh, mm)

        val ldt = LocalDateTime.of(date, time)
        ldt.atZone(zone).toInstant().toEpochMilli()
    }.getOrNull()
}