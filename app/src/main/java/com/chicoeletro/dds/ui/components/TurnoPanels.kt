// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TurnoPanels.kt
// Função: Painéis de interface principais do diálogo de turno (painel lateral esquerdo de status e ações, painel direito do Boletim Diário de Obra).
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chicoeletro.dds.features.turno.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun MenuStep(
    snapshot: TurnoSnapshot,
    onDismiss: () -> Unit,
    onSelectTarget: (EstadoTurno) -> Unit,
    equipe: String,
    teamType: String? = null,
    onClickEquipe: () -> Unit = {},
    online: Boolean,
    bdoList: List<BdoSs>,
    onDefinirSs: (String) -> Unit,
    onAlterarEstado: (String, SsStatus) -> Unit
) {
    var showControls by remember { mutableStateOf(false) }
    
    val themeColor = getTurnoColor(snapshot.estado)
    val bgColor = getTurnoBgColor(snapshot.estado)
    
    var nowMs by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(1000)
            nowMs = System.currentTimeMillis()
        }
    }
    
    val tempoAtivoMs = calcularTempoAtivo(snapshot.transicoes, snapshot.openedAtClientMs, nowMs)
    val nextStates = remember(snapshot.estado) {
        EstadoTurno.values().filter { to ->
            TurnoRules.podeTransitar(snapshot.estado, to)
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Barra Superior de Status
        Surface(
            color = bgColor,
            shape = MaterialTheme.shapes.medium,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Filled.Home,
                            contentDescription = "Home",
                            tint = themeColor
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    
                    // Botão interativo do estado atual
                    Button(
                        onClick = { showControls = !showControls },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = themeColor,
                            contentColor = Color.White
                        ),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        val stateLabel = when (snapshot.estado) {
                            EstadoTurno.ABERTO -> "TURNO ABERTO ▾"
                            EstadoTurno.INTERVALO -> "INTERVALO ▾"
                            EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO ▾"
                            EstadoTurno.FECHADO -> "TURNO FECHADO ▾"
                        }
                        Text(text = stateLabel, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }
                
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    if (snapshot.estado != EstadoTurno.FECHADO) {
                        Text(
                            text = "Tempo Ativo: ${formatDuration(tempoAtivoMs)}",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = themeColor
                        )
                    }
                    
                    // Badge da Equipe
                    Surface(
                        color = Color.White.copy(alpha = 0.8f),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.clickable { onClickEquipe() }
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Group,
                                contentDescription = "Equipe",
                                tint = themeColor,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(Modifier.width(4.dp))
                            Text(
                                text = equipe,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = themeColor
                            )
                        }
                    }

                    Icon(
                        imageVector = if (online) Icons.Filled.Wifi else Icons.Filled.SignalWifiOff,
                        contentDescription = if (online) "Online" else "Offline",
                        tint = themeColor,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
        }
        
        // Painel de Ações do Turno (Expansível)
        AnimatedVisibility(
            visible = showControls && nextStates.isNotEmpty(),
            enter = expandVertically() + fadeIn(),
            exit = shrinkVertically() + fadeOut()
        ) {
            Card(
                colors = CardDefaults.cardColors(containerColor = bgColor),
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "Alterar Estado do Turno",
                        style = MaterialTheme.typography.labelMedium,
                        color = themeColor,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 4.dp)
                    )
                    
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        nextStates.forEach { st ->
                            val buttonColor = when (st) {
                                EstadoTurno.ABERTO -> Color(0xFF2E7D32)
                                EstadoTurno.INTERVALO -> Color(0xFFEF6C00)
                                EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFF1565C0)
                                EstadoTurno.FECHADO -> Color(0xFFC62828)
                            }
                            
                            val buttonIcon = when (st) {
                                EstadoTurno.ABERTO -> Icons.Filled.PlayArrow
                                EstadoTurno.INTERVALO -> Icons.Filled.Pause
                                EstadoTurno.DESLOCAMENTO_ESPECIAL -> Icons.Filled.DirectionsCar
                                EstadoTurno.FECHADO -> Icons.Filled.Stop
                            }
                            
                            val label = when (st) {
                                EstadoTurno.ABERTO -> if (snapshot.estado == EstadoTurno.FECHADO) "ABRIR TURNO" else "RETOMAR"
                                EstadoTurno.INTERVALO -> "INTERVALO"
                                EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO"
                                EstadoTurno.FECHADO -> "FECHAR TURNO"
                            }
                            
                            Button(
                                onClick = {
                                    showControls = false
                                    onSelectTarget(st)
                                },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = buttonColor,
                                    contentColor = Color.White
                                ),
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.weight(1f)
                            ) {
                                Icon(
                                    imageVector = buttonIcon,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    text = label,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 12.sp
                                )
                            }
                        }
                    }
                }
            }
        }

        // BDO (Espaço Total)
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            if (teamType == "CONSTRUCAO") {
                ConstructionBdoSection(
                    equipe = equipe,
                    online = online,
                    modifier = Modifier.fillMaxSize()
                )
            } else if (teamType == "EP" || teamType == "LINHA_VIVA") {
                EpBdoSection(
                    equipe = equipe,
                    online = online,
                    modifier = Modifier.fillMaxSize()
                )
            } else {
                BdoSection(
                    snapshot = snapshot,
                    equipe = equipe,
                    online = online,
                    bdoList = bdoList,
                    onDefinirSs = onDefinirSs,
                    onAlterarEstado = onAlterarEstado,
                    modifier = Modifier.fillMaxSize()
                )
            }
        }
    }
}

@Composable
fun LeftPanel(
    snapshot: TurnoSnapshot,
    onDismiss: () -> Unit,
    onSelectTarget: (EstadoTurno) -> Unit,
    equipe: String,
    teamType: String? = null,
    onClickEquipe: () -> Unit = {},
    online: Boolean,
    modifier: Modifier = Modifier
) {
    val themeColor = getTurnoColor(snapshot.estado)
    val bgColor = getTurnoBgColor(snapshot.estado)
    
    var nowMs by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(1000)
            nowMs = System.currentTimeMillis()
        }
    }
    
    val tempoAtivoMs = calcularTempoAtivo(snapshot.transicoes, snapshot.openedAtClientMs, nowMs)
    
    val nextStates = remember(snapshot.estado) {
        EstadoTurno.values().filter { to ->
            TurnoRules.podeTransitar(snapshot.estado, to)
        }
    }
    
    Surface(
        color = bgColor,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Filled.Home,
                            contentDescription = "Home",
                            tint = themeColor
                        )
                    }
                    Icon(
                        imageVector = if (online) Icons.Filled.Wifi else Icons.Filled.SignalWifiOff,
                        contentDescription = if (online) "Online" else "Offline",
                        tint = themeColor
                    )
                }
                
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "ESTADO ATUAL",
                        style = MaterialTheme.typography.labelSmall,
                        color = themeColor.copy(alpha = 0.7f),
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(4.dp))
                    Surface(
                        color = Color.White,
                        shape = MaterialTheme.shapes.small,
                        shadowElevation = 2.dp
                    ) {
                        Text(
                            text = when (snapshot.estado) {
                                EstadoTurno.ABERTO -> "ABERTO"
                                EstadoTurno.INTERVALO -> "INTERVALO"
                                EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO"
                                EstadoTurno.FECHADO -> "FECHADO"
                            },
                            color = themeColor,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                        )
                    }
                }
                
                Column(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "Ações do Turno",
                        style = MaterialTheme.typography.labelMedium,
                        color = themeColor,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 4.dp)
                    )
                    
                    nextStates.forEach { st ->
                        val buttonColor = when (st) {
                            EstadoTurno.ABERTO -> Color(0xFF2E7D32)
                            EstadoTurno.INTERVALO -> Color(0xFFEF6C00)
                            EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFF1565C0)
                            EstadoTurno.FECHADO -> Color(0xFFC62828)
                        }
                        
                        val buttonIcon = when (st) {
                            EstadoTurno.ABERTO -> Icons.Filled.PlayArrow
                            EstadoTurno.INTERVALO -> Icons.Filled.Pause
                            EstadoTurno.DESLOCAMENTO_ESPECIAL -> Icons.Filled.DirectionsCar
                            EstadoTurno.FECHADO -> Icons.Filled.Stop
                        }
                        
                        val label = when (st) {
                            EstadoTurno.ABERTO -> if (snapshot.estado == EstadoTurno.FECHADO) "ABRIR TURNO" else "RETOMAR TURNO"
                            EstadoTurno.INTERVALO -> "INTERVALO"
                            EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO"
                            EstadoTurno.FECHADO -> "FECHAR TURNO"
                        }
                        
                        Button(
                            onClick = { onSelectTarget(st) },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = buttonColor,
                                contentColor = Color.White
                            ),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center,
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Icon(
                                    imageVector = buttonIcon,
                                    contentDescription = null,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = label,
                                    fontWeight = FontWeight.Bold,
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                        }
                    }
                }
                
                if (snapshot.estado != EstadoTurno.FECHADO) {
                    HorizontalDivider(color = themeColor.copy(alpha = 0.2f), modifier = Modifier.padding(vertical = 4.dp))
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "TEMPO ATIVO",
                            style = MaterialTheme.typography.labelSmall,
                            color = themeColor.copy(alpha = 0.7f),
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = formatDuration(tempoAtivoMs),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = themeColor
                        )
                    }
                }
            }
            
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                shape = MaterialTheme.shapes.small,
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 65.dp)
                    .clickable { onClickEquipe() }
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Filled.Group,
                        contentDescription = "Equipe",
                        tint = themeColor,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "Equipe Atual",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = equipe,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        val readableType = when (teamType) {
                            "STC" -> "STC (NR-10)"
                            "STC_CESTO" -> "STC - CESTO"
                            "EP" -> "EP (Manutenção)"
                            "LINHA_VIVA" -> "Linha Viva"
                            "ROCADA" -> "Roçada"
                            "CONSTRUCAO" -> "Construção"
                            else -> "Não Definido"
                        }
                        Text(
                            text = readableType,
                            style = MaterialTheme.typography.bodySmall,
                            color = themeColor,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun BdoSection(
    snapshot: TurnoSnapshot,
    equipe: String,
    online: Boolean,
    bdoList: List<BdoSs>,
    onDefinirSs: (String) -> Unit,
    onAlterarEstado: (String, SsStatus) -> Unit,
    modifier: Modifier = Modifier
) {
    var newSsText by remember { mutableStateOf("") }
    var newSsError by remember { mutableStateOf<String?>(null) }
    val clipboard = LocalClipboardManager.current

    var nowMs by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(1000)
            nowMs = System.currentTimeMillis()
        }
    }

    val totalServices = bdoList.size
    var sumDisplacementMs = 0L
    var sumExecutionMs = 0L
    var sumTotalMs = 0L
    
    bdoList.forEach { ss ->
        val (desl, exec, tot) = obterTemposServico(ss, snapshot.transicoes, nowMs)
        sumDisplacementMs += desl
        sumExecutionMs += exec
        sumTotalMs += tot
    }

    // Calcular lacunas de ócio (> 5 min)
    val gaps = remember(bdoList, snapshot.transicoes, nowMs) {
        calcularLacunasSemExecucao(bdoList, snapshot.transicoes, nowMs).map { (duration, period) ->
            val (start, end) = period
            UnifiedHistoryItem.SemExecucao(
                durationMs = duration,
                startMs = start,
                endMs = end,
                timestampMs = end - 1
            )
        }
    }
    
    val sumSemExecucaoMs = remember(gaps) {
        gaps.sumOf { it.durationMs }
    }

    val items = remember(bdoList, snapshot.transicoes, gaps) {
        val serviceItems = bdoList.map { UnifiedHistoryItem.Servico(it) }
        val transItems = snapshot.transicoes.map { UnifiedHistoryItem.Transicao(it) }
        val gapItems = gaps
        (serviceItems + transItems + gapItems).sortedByDescending { it.timestampMs }
    }

    Column(
        modifier = modifier.fillMaxSize()
    ) {
        // SS definition form
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = newSsText,
                onValueChange = {
                    newSsText = it
                    newSsError = null
                },
                label = { Text("Identificação do Serviço (NOC/SS/GSIM)") },
                isError = newSsError != null,
                singleLine = true,
                modifier = Modifier.weight(1f),
                trailingIcon = {
                    IconButton(onClick = {
                        val clip = clipboard.getText()?.text?.trim().orEmpty()
                        if (clip.isNotEmpty()) {
                            val normalized = clip
                                .replace("\n", " ")
                                .replace("\r", " ")
                                .replace("\t", " ")
                                .replace(" ", "")
                            newSsText = normalized
                            newSsError = null
                        }
                    }) {
                        Icon(Icons.Filled.ContentPaste, "Colar SS")
                    }
                }
            )
            Button(
                onClick = {
                    val cleanSs = newSsText.trim()
                    if (cleanSs.isEmpty()) {
                        newSsError = "Campo obrigatório"
                    } else if (!TurnoRules.isNocSsValido(cleanSs)) {
                        newSsError = "Formato inválido"
                    } else {
                        newSsError = null
                        onDefinirSs(cleanSs)
                        newSsText = ""
                    }
                },
                modifier = Modifier.height(56.dp)
            ) {
                Text("Inserir...")
            }
        }
        
        if (newSsError != null) {
            Text(
                text = newSsError!!,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(bottom = 8.dp)
            )
        }

        // Summary Card
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)),
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp)
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(
                    text = "Histórico de Serviços do Dia (Total: $totalServices)",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Serviços", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("$totalServices", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Deslocamento", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(formatDuration(sumDisplacementMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Execução", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(formatDuration(sumExecutionMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Sem Execução", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(formatDuration(sumSemExecucaoMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium, color = Color(0xFFF57F17))
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                        Text("Tempo Total", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(formatDuration(sumTotalMs), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }

        // Scrollable timeline list
        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(items) { item ->
                when (item) {
                    is UnifiedHistoryItem.Servico -> {
                        val sortedServices = remember(bdoList) {
                            bdoList.sortedBy { it.transitions.firstOrNull()?.timestampMs ?: 0L }
                        }
                        val index = sortedServices.indexOf(item.ss)
                        val label = "${index + 1}º Serviço"
                        
                        ServicoItem(
                            ss = item.ss,
                            ordinalLabel = label,
                            turnoTransitions = snapshot.transicoes,
                            nowMs = nowMs,
                            onAlterarEstado = { onAlterarEstado(item.ss.ssId, it) }
                        )
                    }
                    is UnifiedHistoryItem.Transicao -> {
                        TransicaoItem(
                            trans = item.trans,
                            todasTrans = snapshot.transicoes
                        )
                    }
                    is UnifiedHistoryItem.SemExecucao -> {
                        SemExecucaoItem(item = item)
                    }
                }
            }
        }
    }
}
