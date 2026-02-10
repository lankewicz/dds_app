package com.chicoeletro.dds.features.turno

import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// --- Extensions & Utils ---

private val TurnoStatus.label: String
    get() = when (this) {
        TurnoStatus.FECHADO -> "TURNO FECHADO"
        TurnoStatus.INTERVALO -> "INTERVALO"
        TurnoStatus.ABERTO -> "TURNO ABERTO"
        TurnoStatus.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO\nESPECIAL"
    }

private val TurnoStatus.color: Color
    get() = when (this) {
        TurnoStatus.FECHADO -> Color(0xFFD32F2F)
        TurnoStatus.INTERVALO -> Color(0xFFFBC02D)
        TurnoStatus.ABERTO -> Color(0xFF388E3C)
        TurnoStatus.DESLOCAMENTO_ESPECIAL -> Color(0xFF1976D2)
    }

private val TurnoStatus.allowedTargets: List<TurnoStatus>
    get() = when (this) {
        TurnoStatus.ABERTO -> listOf(TurnoStatus.FECHADO, TurnoStatus.INTERVALO)
        TurnoStatus.FECHADO -> listOf(TurnoStatus.ABERTO, TurnoStatus.DESLOCAMENTO_ESPECIAL)
        TurnoStatus.INTERVALO -> listOf(TurnoStatus.ABERTO, TurnoStatus.FECHADO)
        TurnoStatus.DESLOCAMENTO_ESPECIAL -> listOf(TurnoStatus.ABERTO, TurnoStatus.FECHADO)
    }

private val MOTIVOS_PADRAO = listOf("Oficina", "Borracharia", "Lavacar", "Pato Branco")

// --- Components ---

@Composable
fun TurnoStatusCard(
    status: TurnoStatus,
    lastChangedAt: String?,
    deslocamentoMotivo: String? = null,
    attention: Boolean = false,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 6.dp)
            .clickable { onClick() },
        colors = CardDefaults.cardColors(containerColor = status.color),
        shape = RoundedCornerShape(10.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = status.label,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                textAlign = TextAlign.Center,
                lineHeight = 15.sp
            )

            if (status == TurnoStatus.DESLOCAMENTO_ESPECIAL) {
                val motivo = deslocamentoMotivo?.trim().orEmpty()
                if (motivo.isNotBlank()) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = motivo,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color.White.copy(alpha = 0.98f),
                        textAlign = TextAlign.Center,
                        lineHeight = 14.sp
                    )
                }
            }

            if (!lastChangedAt.isNullOrBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "Última: $lastChangedAt",
                    fontSize = 11.sp,
                    color = Color.White.copy(alpha = 0.92f),
                    textAlign = TextAlign.Center
                )
            }

            if (attention) {
                Spacer(Modifier.height(6.dp))
                val blinkAlpha by rememberInfiniteTransition(label = "turno_attention")
                    .animateFloat(
                        initialValue = 1f,
                        targetValue = 0.25f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(650),
                            repeatMode = RepeatMode.Reverse
                        ),
                        label = "blink_alpha"
                    )

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.alpha(blinkAlpha)
                ) {
                    Icon(Icons.Filled.Warning, contentDescription = "Atenção", tint = Color.White)
                    Spacer(Modifier.width(6.dp))
                    Text(
                        text = "ATENÇÃO",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                }
            }
        }
    }
}

// Sobrecarga para compatibilidade
@Composable
fun TurnoStatusDialog(
    statusAtual: TurnoStatus,
    onDismiss: () -> Unit,
    onConfirm: (TurnoStatus, String?) -> Unit
) {
    TurnoStatusDialog(
        statusAtual = statusAtual,
        ssNocAtual = null,
        onDismiss = onDismiss,
        onConfirm = { novo, motivo, _ -> onConfirm(novo, motivo) }
    )
}

@Composable
fun TurnoStatusDialog(
    statusAtual: TurnoStatus,
    ssNocAtual: String? = null,
    onDismiss: () -> Unit,
    onConfirm: (novoStatus: TurnoStatus, deslocamentoMotivo: String?, ssNoc: String?) -> Unit
) {
    val options = remember(statusAtual) { statusAtual.allowedTargets }
    var desejado by remember { mutableStateOf<TurnoStatus?>(null) }

    var deslocamentoSel by remember { mutableStateOf<String?>(null) }
    var deslocamentoOutro by remember { mutableStateOf("") }

    var ssNoc by remember { mutableStateOf(ssNocAtual?.trim().orEmpty()) }
    val ssNocChanged = remember(ssNoc, ssNocAtual) {
        ssNoc.trim() != (ssNocAtual?.trim().orEmpty())
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Alterar status do turno") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                CurrentStatusChip(statusAtual)

                Text("Selecione o próximo status (apenas os permitidos):")
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    options.forEach { st ->
                        StatusButton(
                            label = st.label,
                            color = st.color,
                            selected = desejado == st,
                            onClick = { desejado = st },
                            modifier = Modifier.weight(1f)
                        )
                    }
                }

                if (desejado == TurnoStatus.DESLOCAMENTO_ESPECIAL) {
                    Spacer(Modifier.height(6.dp))
                    Text("Motivo do deslocamento:", style = MaterialTheme.typography.bodyMedium)

                    // Grid 2x2 Dinâmico
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        MOTIVOS_PADRAO.chunked(2).forEach { rowItems ->
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                rowItems.forEach { item ->
                                    MotivoRadio(
                                        text = item,
                                        selected = deslocamentoSel == item,
                                        onClick = { deslocamentoSel = item },
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    }

                    Spacer(Modifier.height(6.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = deslocamentoSel == "Outro",
                            onClick = { deslocamentoSel = "Outro" }
                        )
                        Spacer(Modifier.width(6.dp))
                        Text("Outro:", style = MaterialTheme.typography.bodyMedium)
                    }
                    OutlinedTextField(
                        value = deslocamentoOutro,
                        onValueChange = { deslocamentoOutro = it },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = deslocamentoSel == "Outro",
                        placeholder = { Text("Especificar...") }
                    )
                }

                if (statusAtual == TurnoStatus.ABERTO) {
                    Spacer(Modifier.height(6.dp))
                    Text("SS/NOC (opcional):", style = MaterialTheme.typography.bodyMedium)
                    OutlinedTextField(
                        value = ssNoc,
                        onValueChange = { ssNoc = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        placeholder = { Text("Ex.: SS-123 / NOC-456") }
                    )
                }
            }
        },
        confirmButton = {
            val wantsChangeStatus = desejado != null
            val canSaveSsNocOnly = statusAtual == TurnoStatus.ABERTO && ssNocChanged

            val okMotivo = if (desejado == TurnoStatus.DESLOCAMENTO_ESPECIAL) {
                val m = if (deslocamentoSel == "Outro") deslocamentoOutro.trim() else (deslocamentoSel ?: "").trim()
                m.isNotBlank()
            } else true

            val enabled = (wantsChangeStatus || canSaveSsNocOnly) && okMotivo

            TextButton(
                enabled = enabled,
                onClick = {
                    val novo = desejado ?: statusAtual
                    val motivo = if (novo == TurnoStatus.DESLOCAMENTO_ESPECIAL) {
                        val m = if (deslocamentoSel == "Outro") deslocamentoOutro.trim() else (deslocamentoSel ?: "").trim()
                        m.takeIf { it.isNotBlank() }
                    } else null
                    val ssOut = ssNoc.trim().takeIf { it.isNotBlank() }
                    onConfirm(novo, motivo, ssOut)
                }
            ) { Text("Confirmar") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancelar") }
        }
    )
}

@Composable
private fun CurrentStatusChip(statusAtual: TurnoStatus) {
    Card(
        colors = CardDefaults.cardColors(containerColor = statusAtual.color),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.Black.copy(alpha = 0.2f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Box(
            modifier = Modifier.padding(vertical = 10.dp, horizontal = 12.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "ATUAL: ${statusAtual.label.replace('\n', ' ')}",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                fontSize = 12.sp
            )
        }
    }
}

@Composable
private fun MotivoRadio(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .clickable { onClick() }
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(selected = selected, onClick = onClick)
        Spacer(Modifier.width(6.dp))
        Text(text)
    }
}

@Composable
private fun StatusButton(
    label: String,
    color: Color,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .height(64.dp)
            .clickable { onClick() },
        border = if (selected) BorderStroke(3.dp, Color.Black) else null,
        colors = CardDefaults.cardColors(containerColor = color),
        shape = RoundedCornerShape(14.dp)
    ) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (selected) Text("✅  ", fontSize = 14.sp, color = Color.White)
                Text(
                    text = label,
                    textAlign = TextAlign.Center,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    color = Color.White,
                    lineHeight = 13.sp
                )
            }
        }
    }
}