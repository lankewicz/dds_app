// Módulo: app/src/main/java/com/chicoeletro/dds/features/viewer/ViewerScreen.kt
// Estratégia: OFFLINE-FIRST — exibe apenas arquivos locais em filesDir/trainings/<trainingId>
// Recursos: setas de navegação, contador "n de N", tela cheia com zoom/pan e double-tap para reset.
// Atualizado: 11/2025



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

    // 🔄 Auto-start: assim que as imagens chegarem, inicia a sessão (sem botão INICIAR)
    LaunchedEffect(ui.images, ui.started) {
        if (ui.images.isNotEmpty() && !ui.started) {
            viewModel.onStartPressed(totalSlides = ui.images.size)
        }
    }

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
        ui.images
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
        ui.images
    ) {
        if (ui.images.isEmpty()) return@remember null
        when {
            !ui.blockMessage.isNullOrBlank() ->
                FooterStatus(ui.blockMessage!!, FooterStatusKind.WARNING)
            status != null || ui.conclusionInfo != null ->
                FooterStatus(statusText ?: "", FooterStatusKind.SUCCESS)
            else ->
                FooterStatus(statusText ?: "", FooterStatusKind.NORMAL)
        }
    }

    LaunchedEffect(footerStatus) { onStatusChanged(footerStatus) }


    // Activity já está travada em paisagem; não precisamos de fallback
    Column(Modifier.fillMaxSize().pointerInput(Unit) {
        detectTapGestures(onTap = { viewModel.onUserInteraction() })
    }) {
        // Área principal da imagem
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
                    onClick = { viewModel.requestGoToSlide((currentIndex - 1).coerceAtLeast(0)) },
                    enabled = currentIndex > 0
                ) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Anterior") }

                Text("${currentIndex + 1} de ${ui.images.size}")

                // ➡️ Próximo / ✅ Concluir
                val isLast = currentIndex >= ui.images.lastIndex && ui.images.isNotEmpty()
                if (!isLast) {
                    // Botão Próximo...
                    Button(
                        onClick = {
                            viewModel.requestGoToSlide((currentIndex + 1).coerceAtMost(ui.images.lastIndex))
                        },
                        modifier = Modifier.height(52.dp).widthIn(min = 160.dp),
                        shape = RoundedCornerShape(28.dp),
                        elevation = ButtonDefaults.buttonElevation(defaultElevation = 2.dp)
                    ) {
                        Text("Próximo")
                        Spacer(Modifier.width(6.dp))
                        Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = "Próximo")
                    }
                } else {
                    // Sempre deixa clicável; bloqueia a navegação se < 2min e mostra mensagem educativa
                    var showWhyDialog by remember { mutableStateOf(false) }
                    var whyMode by remember { mutableStateOf(WhyDialogMode.MIN_TIME) }
                    var remainMs by remember { mutableStateOf(0L) } // usado no MIN_TIME

                    val canFinish = ui.canTakePhoto && !ui.invalidated
                    val concluido = status != null        // 👈 AGORA EXISTE
                    if (canConclude) {
                        Button(
                            onClick = {
                                if (isOnlineDDS) {
                                    // DDS ONLINE: entra no Agora somente dentro da janela
                                    if (canEnterOnline) {
                                        onEnterAgora()
                                    } else {
                                        whyMode = WhyDialogMode.ONLINE_LOCK
                                        showWhyDialog = true
                                    }
                                } else {
                                    // DDS NORMAL: mantém atuação atual (2min + regras)
                                    val minTotalMs = 120_000L
                                    val falta = minTotalMs - ui.elapsedMs
                                    if (falta > 0L) {
                                        remainMs = falta
                                        whyMode = WhyDialogMode.MIN_TIME
                                        showWhyDialog = true
                                    } else if (canFinish) {
                                        onOpenForm() // ok, pode concluir
                                    } else {
                                        // Regras extras (ex.: 10s por slide / todos vistos) ainda não cumpridas
                                        // Mantemos silêncio aqui para não poluir; o topo da tela já avisa via blockMessage.
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
                        } else {
                        // Opcional: manter espaço/estética sem botão, ou exibir um label "Expirado"
                        Text("Treinamento expirado", style = MaterialTheme.typography.bodyMedium)
                    }

                    // Diálogo educativo: por que pedimos 2 minutos
                    if (showWhyDialog) {
                        AlertDialog(
                            onDismissRequest = { showWhyDialog = false },
                            confirmButton = {
                                Button(onClick = { showWhyDialog = false }) { Text("Entendi") }
                            },
                            title = {
                                when (whyMode) {
                                    WhyDialogMode.MIN_TIME -> Text("Quase lá! ⏱️")
                                    WhyDialogMode.ONLINE_LOCK -> Text("DDS Online programado")
                                }
                            },
                            text = {
                                //val faltante = formatRemaining(remainMs)
                                when (whyMode) {
                                    WhyDialogMode.MIN_TIME -> {
                                        Text(
                                            "Para garantir atenção e retenção do conteúdo, " +
                                            "este DDS requer pelo menos 2 minutos de dedicação.\n\n" +
                                            "Isso reduz o risco de acidentes por leitura superficial " +
                                            "e ajuda a equipe a fixar os pontos críticos.\n\n" +
                                            "Continue discutindo o tema com a equipe; " +
                                            "assim que completar o tempo, você poderá concluir."
                                        )
                                    }
                                    WhyDialogMode.ONLINE_LOCK -> {
                                        val msg = if (scheduledStartMs == null) {
                                            "Este DDS é online. O acesso ao DDS Online é liberado 15 minutos antes do horário agendado.\n\n" +
                                            "Horário agendado não identificado neste treinamento."
                                        } else {
                                            "O acesso ao DDS Online é liberado 15 minutos antes do horário agendado.\n\n" +
                                            "⏳ Liberação ${formatRemainingForMessage(remainingMin)}."
                                        }
                                        Text(msg)
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    // -------- Tela cheia com zoom/pan ----------
    if (fullscreen && painter != null) {
        Dialog(
            onDismissRequest = { fullscreen = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)
        ) {
            val scale = remember { mutableFloatStateOf(1f) }
            val offset = remember { mutableStateOf(Offset.Zero) }
            val origin = remember { mutableStateOf(TransformOrigin.Center) }

            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black),
                contentAlignment = Alignment.Center
            ) {
                // Anterior (fullscreen)
                if (currentIndex > 0) {
                    IconButton(
                        onClick = { viewModel.requestGoToSlide((currentIndex - 1).coerceAtLeast(0)) },
                        modifier = Modifier.align(Alignment.CenterStart).padding(16.dp)
                    ) { Icon(Icons.AutoMirrored.Filled.ArrowBack, null, tint = Color.White) }
                }
                // Próxima
                if (currentIndex < ui.images.lastIndex) {
                    IconButton(
                        onClick = { viewModel.requestGoToSlide((currentIndex + 1).coerceAtMost(ui.images.lastIndex)) },
                        modifier = Modifier.align(Alignment.CenterEnd).padding(16.dp)
                    ) { Icon(Icons.AutoMirrored.Filled.ArrowForward, null, tint = Color.White) }
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

                IconButton(
                    onClick = { fullscreen = false },
                    modifier = Modifier.align(Alignment.TopEnd).padding(16.dp)
                ) { Icon(Icons.Filled.Close, contentDescription = "Fechar", tint = Color.White) }
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