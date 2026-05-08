// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/CommunicationScreen.kt
// Função: Interface de comunicação estilo Chat (ChatGPT) com painel lateral e histórico.
// Tecnologias: Jetpack Compose, Material3.

package com.chicoeletro.dds.ui.components

import androidx.compose.animation.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chicoeletro.dds.features.communication.CommunicationRepository
import com.chicoeletro.dds.features.communication.TeamMessage
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun CommunicationScreen(
    equipeOrigem: String,
    onDismiss: () -> Unit
) {
    val repository = remember { CommunicationRepository() }
    val scope = rememberCoroutineScope()
    
    var allMessages by remember { mutableStateOf<List<TeamMessage>>(emptyList()) }
    var selectedThreadId by remember { mutableStateOf<String?>(null) }
    var currentFilter by remember { mutableStateOf("ABERTAS") }
    var showNewThreadDialog by remember { mutableStateOf(false) }
    var messageToDelete by remember { mutableStateOf<TeamMessage?>(null) }
    
    // Escutar mensagens enviadas e recebidas
    DisposableEffect(equipeOrigem) {
        var msgsIn = emptyList<TeamMessage>()
        var msgsOut = emptyList<TeamMessage>()

        fun updateAll() {
            allMessages = (msgsIn + msgsOut).sortedByDescending { it.timestamp }
        }

        val regIn = repository.listenIncoming(equipeOrigem) { msgs ->
            msgsIn = msgs
            updateAll()
        }
        val regOut = repository.listenOutgoing(equipeOrigem) { msgs ->
            msgsOut = msgs
            updateAll()
        }

        onDispose {
            regIn.remove()
            regOut.remove()
        }
    }

    // Agrupar mensagens por Thread
    val threads = remember(allMessages, currentFilter) {
        allMessages
            .groupBy { it.threadId.ifBlank { it.id } }
            .map { (id, msgs) ->
                val lastMsg = msgs.first() // Sorted descending
                val isConcluida = msgs.any { it.status == "CONCLUIDA" }
                ThreadSummary(
                    id = id,
                    subject = lastMsg.subject.ifBlank { "Sem Assunto" },
                    lastMessage = lastMsg.content,
                    timestamp = lastMsg.timestamp,
                    isConcluida = isConcluida,
                    unread = msgs.count { it.status == "NÃO LIDO" && it.toEquipe == equipeOrigem },
                    sector = if (lastMsg.fromEquipe == equipeOrigem) lastMsg.toSetor else lastMsg.fromEquipe
                )
            }
            .filter { if (currentFilter == "ABERTAS") !it.isConcluida else it.isConcluida }
            .sortedByDescending { it.timestamp }
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.surface
    ) {
        Row(Modifier.fillMaxSize()) {
            // PAINEL ESQUERDO (Sidebar)
            Column(
                Modifier
                    .width(300.dp)
                    .fillMaxHeight()
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    .padding(top = 16.dp)
            ) {
                // Header Sidebar
                Row(
                    Modifier.padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Conversas",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f)
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Fechar")
                    }
                }

                Spacer(Modifier.height(8.dp))

                // Filtros (Tabs)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = currentFilter == "ABERTAS",
                        onClick = { currentFilter = "ABERTAS" },
                        label = { Text("Abertas") },
                        leadingIcon = if (currentFilter == "ABERTAS") {
                            { Icon(Icons.Default.Check, null, modifier = Modifier.size(16.dp)) }
                        } else null
                    )
                    FilterChip(
                        selected = currentFilter == "CONCLUIDAS",
                        onClick = { currentFilter = "CONCLUIDAS" },
                        label = { Text("Concluídas") }
                    )
                }

                Spacer(Modifier.height(8.dp))

                // Lista de Threads
                LazyColumn(Modifier.weight(1f)) {
                    items(threads) { thread ->
                        ThreadItem(
                            thread = thread,
                            isSelected = selectedThreadId == thread.id,
                            onClick = { selectedThreadId = thread.id }
                        )
                    }
                }
                
                // Botão Nova Mensagem
                Button(
                    onClick = { showNewThreadDialog = true },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Default.Add, null)
                    Spacer(Modifier.width(8.dp))
                    Text("Nova Conversa")
                }
            }

            if (showNewThreadDialog) {
                NewThreadDialog(
                    onDismiss = { showNewThreadDialog = false },
                    onConfirm = { sector, subject, content ->
                        val threadId = UUID.randomUUID().toString()
                        val msg = TeamMessage(
                            threadId = threadId,
                            fromEquipe = equipeOrigem,
                            toSetor = sector,
                            subject = subject,
                            content = content,
                            status = "NÃO LIDO",
                            toEquipe = "" // Opcional: preencher se for direto
                        )
                        scope.launch {
                            repository.sendMessage(msg)
                            selectedThreadId = threadId
                            showNewThreadDialog = false
                        }
                    }
                )
            }

            if (messageToDelete != null) {
                AlertDialog(
                    onDismissRequest = { messageToDelete = null },
                    title = { Text("Apagar Mensagem") },
                    text = { Text("Esta mensagem será apagada permanentemente e não poderá ser restaurada. Deseja continuar?") },
                    confirmButton = {
                        Button(
                            onClick = {
                                scope.launch {
                                    repository.deleteMessage(messageToDelete!!.id)
                                    messageToDelete = null
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                        ) {
                            Text("Apagar")
                        }
                    },
                    dismissButton = {
                        TextButton(onClick = { messageToDelete = null }) {
                            Text("Cancelar")
                        }
                    }
                )
            }

            // PAINEL DIREITO (Chat Detail)
            Box(Modifier.weight(1f).fillMaxHeight()) {
                if (selectedThreadId != null) {
                    val threadMessages = allMessages.filter { (it.threadId.ifBlank { it.id }) == selectedThreadId }
                        .sortedBy { it.timestamp }
                    
                    // Marcar como lido ao abrir a conversa
                    LaunchedEffect(selectedThreadId, threadMessages) {
                        threadMessages.filter { it.toEquipe == equipeOrigem && it.status == "NÃO LIDO" }
                            .forEach { msg ->
                                repository.markAsRead(msg.id)
                            }
                    }

                    ChatDetail(
                        messages = threadMessages,
                        equipeOrigem = equipeOrigem,
                        onSendMessage = { content ->
                            val first = threadMessages.firstOrNull()
                            val newMsg = TeamMessage(
                                threadId = selectedThreadId!!,
                                fromEquipe = equipeOrigem,
                                toSetor = first?.toSetor ?: "OFICINA",
                                subject = first?.subject ?: "Sem Assunto",
                                content = content,
                                status = "NÃO LIDO"
                            )
                            scope.launch { repository.sendMessage(newMsg) }
                        },
                        onConclude = {
                            scope.launch {
                                repository.markThreadAsConcluded(selectedThreadId!!)
                                // Opcional: Deselecionar ou manter para ver como concluída
                            }
                        },
                        onReopen = {
                            scope.launch {
                                repository.reopenThread(selectedThreadId!!)
                            }
                        },
                        onLongClickMessage = { msg ->
                            messageToDelete = msg
                        }
                    )
                } else {
                    Column(
                        Modifier.fillMaxSize(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(
                            Icons.Default.QuestionAnswer,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.5f)
                        )
                        Spacer(Modifier.height(16.dp))
                        Text(
                            "Selecione uma conversa para visualizar o histórico",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ThreadItem(
    thread: ThreadSummary,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val bgColor = if (isSelected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent
    val df = SimpleDateFormat("HH:mm", Locale("pt", "BR"))
    val timeStr = thread.timestamp?.let { df.format(it) } ?: ""

    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .background(bgColor)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Avatar do Setor
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.secondary.copy(alpha = 0.2f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Default.QuestionAnswer,
                contentDescription = null,
                modifier = Modifier.size(20.dp),
                tint = MaterialTheme.colorScheme.secondary
            )
        }

        Spacer(Modifier.width(12.dp))

        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Badge Estilizado do Setor
                SectorBadge(thread.sector)
                Spacer(Modifier.width(8.dp))
                
                Text(
                    text = thread.subject,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = if (thread.unread > 0) FontWeight.Bold else FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = timeStr,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(
                text = thread.lastMessage,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }

        if (thread.unread > 0) {
            Spacer(Modifier.width(8.dp))
            Box(
                Modifier
                    .size(20.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.error),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    thread.unread.toString(),
                    color = Color.White,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

@Composable
private fun ChatDetail(
    messages: List<TeamMessage>,
    equipeOrigem: String,
    onSendMessage: (String) -> Unit,
    onConclude: () -> Unit,
    onReopen: () -> Unit,
    onLongClickMessage: (TeamMessage) -> Unit
) {
    var textState by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val isConcluida = messages.any { it.status == "CONCLUIDA" }
    
    // Auto scroll to bottom
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Column(Modifier.fillMaxSize()) {
        // Top Bar do Chat
        val first = messages.firstOrNull()
        Surface(tonalElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
            Row(
                Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        first?.subject ?: "Detalhes da Conversa",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        "Com: ${first?.toSetor ?: "---"}",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                
                if (isConcluida) {
                    Button(
                        onClick = onReopen,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                    ) {
                        Icon(Icons.Default.Refresh, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Reabrir")
                    }
                } else {
                    Button(
                        onClick = onConclude,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
                    ) {
                        Text("Concluir")
                    }
                }
            }
        }

        // Histórico de Mensagens
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            contentPadding = PaddingValues(vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            val grouped = messages.groupBy { msg ->
                val cal = Calendar.getInstance()
                msg.timestamp?.let { cal.time = it }
                cal.set(Calendar.HOUR_OF_DAY, 0)
                cal.set(Calendar.MINUTE, 0)
                cal.set(Calendar.SECOND, 0)
                cal.set(Calendar.MILLISECOND, 0)
                cal.timeInMillis
            }

            grouped.forEach { (dateMillis, msgs) ->
                item {
                    DateHeader(dateMillis)
                }
                items(msgs) { msg ->
                    val isMe = msg.fromEquipe == equipeOrigem
                    MessageBubble(
                        msg = msg, 
                        isMe = isMe,
                        onLongClick = { onLongClickMessage(msg) }
                    )
                }
            }
        }

        // Campo de Entrada
        Surface(tonalElevation = 8.dp, modifier = Modifier.fillMaxWidth()) {
            Column {
                if (isConcluida) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.5f))
                            .padding(8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "Esta conversa está concluída e não aceita novas mensagens.",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
                
                Row(
                    Modifier
                        .padding(16.dp)
                        .imePadding(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = textState,
                        onValueChange = { textState = it },
                        placeholder = { Text(if (isConcluida) "Conversa encerrada" else "Digite sua mensagem...") },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(24.dp),
                        maxLines = 4,
                        enabled = !isConcluida
                    )
                    Spacer(Modifier.width(8.dp))
                    FloatingActionButton(
                        onClick = {
                            if (textState.isNotBlank() && !isConcluida) {
                                onSendMessage(textState)
                                textState = ""
                            }
                        },
                        containerColor = if (isConcluida) Color.Gray else MaterialTheme.colorScheme.primary,
                        shape = CircleShape,
                        modifier = Modifier.size(48.dp)
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Send, null, tint = Color.White)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MessageBubble(
    msg: TeamMessage, 
    isMe: Boolean,
    onLongClick: () -> Unit
) {
    val df = SimpleDateFormat("HH:mm", Locale("pt", "BR"))
    val timeStr = msg.timestamp?.let { df.format(it) } ?: ""
    val haptic = LocalHapticFeedback.current

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isMe) Alignment.End else Alignment.Start
    ) {
        Surface(
            color = if (isMe) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (isMe) 16.dp else 4.dp,
                bottomEnd = if (isMe) 4.dp else 16.dp
            ),
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Column(
                Modifier
                    .combinedClickable(
                        onClick = {},
                        onLongClick = {
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                            onLongClick()
                        }
                    )
                    .padding(12.dp)
            ) {
                Text(
                    text = msg.content,
                    color = if (isMe) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium
                )
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text(
                        text = timeStr,
                        color = (if (isMe) Color.White else MaterialTheme.colorScheme.onSurfaceVariant).copy(alpha = 0.7f),
                        style = MaterialTheme.typography.labelSmall
                    )
                    if (isMe) {
                        Spacer(Modifier.width(4.dp))
                        val (icon, color) = when (msg.status) {
                            "LIDO", "CONCLUIDA" -> Icons.Default.DoneAll to Color(0xFF81D4FA) // Azul claro para lido
                            else -> Icons.Default.Done to Color.White.copy(alpha = 0.7f)
                        }
                        Icon(
                            imageVector = icon,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = color
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DateHeader(millis: Long) {
    val df = SimpleDateFormat("dd 'de' MMMM", Locale("pt", "BR"))
    val today = Calendar.getInstance().apply {
        set(Calendar.HOUR_OF_DAY, 0)
        set(Calendar.MINUTE, 0)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
    }.timeInMillis
    
    val dateText = when (millis) {
        today -> "Hoje"
        today - 86400000 -> "Ontem"
        else -> df.format(Date(millis))
    }

    Box(Modifier.fillMaxWidth().padding(vertical = 16.dp), contentAlignment = Alignment.Center) {
        Surface(
            color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.5f),
            shape = CircleShape
        ) {
            Text(
                text = dateText,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSecondaryContainer
            )
        }
    }
}

@Composable
private fun SectorBadge(sector: String) {
    val (initial, color) = when (sector.uppercase()) {
        "OFICINA" -> "O" to Color(0xFFFF9800) // Laranja
        "ALMOXARIFADO" -> "A" to Color(0xFF2196F3) // Azul
        "ROTALOG" -> "R" to Color(0xFF4CAF50) // Verde
        "PONTO" -> "P" to Color(0xFF9C27B0) // Roxo
        else -> sector.take(1).uppercase() to Color.Gray
    }

    Surface(
        color = color.copy(alpha = 0.2f),
        shape = RoundedCornerShape(4.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.5f))
    ) {
        Text(
            text = initial,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = color
        )
    }
}

@Composable
private fun NewThreadDialog(
    onDismiss: () -> Unit,
    onConfirm: (String, String, String) -> Unit
) {
    var sector by remember { mutableStateOf("OFICINA") }
    var subject by remember { mutableStateOf("") }
    var content by remember { mutableStateOf("") }
    val sectors = listOf("OFICINA", "ALMOXARIFADO", "ROTALOG", "PONTO")

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Nova Conversa") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Setor Destinatário:", style = MaterialTheme.typography.labelLarge)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    sectors.forEach { s ->
                        FilterChip(
                            selected = sector == s,
                            onClick = { sector = s },
                            label = { Text(s) }
                        )
                    }
                }
                OutlinedTextField(
                    value = subject,
                    onValueChange = { subject = it },
                    label = { Text("Assunto") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = content,
                    onValueChange = { content = it },
                    label = { Text("Mensagem Inicial") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(sector, subject, content) },
                enabled = subject.isNotBlank() && content.isNotBlank()
            ) {
                Text("Iniciar")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancelar")
            }
        }
    )
}

data class ThreadSummary(
    val id: String,
    val subject: String,
    val lastMessage: String,
    val timestamp: Date?,
    val isConcluida: Boolean,
    val unread: Int,
    val sector: String
)
