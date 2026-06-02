// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TurnoSteps.kt
// Função: Componentes de fluxo secundários do diálogo de turno (entrada manual de KM por quadrinhos, motivos de deslocamento e recibo final).
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.features.turno.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale


@Composable
fun MotivoStep(
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
                onValueChange = { onMotivoChanged(currentMotivo, it) },
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
fun KmStep(
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

    val currentKm = snapshot.kmTotalAbs ?: 0L
    val currentKmStr = currentKm.toString()
    val totalDigits = maxOf(6, currentKmStr.length)
    val currentKmPadded = currentKmStr.padStart(totalDigits, '0')
    
    var editableStartIndex by remember { mutableStateOf(totalDigits - 3) }
    var typedDigits by remember { mutableStateOf("") }
    
    val focusRequester = remember { FocusRequester() }
    
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(100)
        focusRequester.requestFocus()
    }
    
    LaunchedEffect(editableStartIndex, typedDigits) {
        val finalKmStr = buildString {
            for (i in 0 until totalDigits) {
                if (i < editableStartIndex) {
                    append(currentKmPadded[i])
                } else {
                    val typedIndex = i - editableStartIndex
                    if (typedIndex < typedDigits.length) {
                        append(typedDigits[typedIndex])
                    } else {
                        append('0')
                    }
                }
            }
        }
        onManualKmChange(finalKmStr)
    }

    val isFullyFilled = typedDigits.length == (totalDigits - editableStartIndex)

    // 1. Current Mileage Card
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)),
        modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Filled.DirectionsCar,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(24.dp)
            )
            Spacer(Modifier.width(16.dp))
            Column {
                Text(
                    text = "Quilometragem Atual do Veículo",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "$currentKm KM",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
    }

    if (kmTotalFromPhoto != null) {
        OutlinedTextField(
            value = kmTotalFromPhoto.toString(),
            onValueChange = {},
            label = { Text("KM Total (via Câmera)") },
            enabled = false,
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
        // Box input UI
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "Digite a nova quilometragem:",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.align(Alignment.Start)
            )
            Spacer(Modifier.height(8.dp))
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                verticalAlignment = Alignment.CenterVertically
            ) {
                for (i in 0 until totalDigits) {
                    val isEditable = i >= editableStartIndex
                    val text = if (i < editableStartIndex) {
                        currentKmPadded[i].toString()
                    } else {
                        val typedIndex = i - editableStartIndex
                        if (typedIndex < typedDigits.length) {
                            typedDigits[typedIndex].toString()
                        } else {
                            ""
                        }
                    }
                    
                    val isFocused = isEditable && (i - editableStartIndex == typedDigits.length)
                    
                    Box(
                        modifier = Modifier
                            .size(width = 44.dp, height = 54.dp)
                            .background(
                                color = if (isEditable) Color.White else Color(0xFFF0F0F0),
                                shape = RoundedCornerShape(8.dp)
                            )
                            .border(
                                width = if (isFocused) 2.dp else 1.dp,
                                color = if (isFocused) MaterialTheme.colorScheme.primary else Color(0xFFCCCCCC),
                                shape = RoundedCornerShape(8.dp)
                            )
                            .clickable {
                                editableStartIndex = i
                                typedDigits = ""
                                focusRequester.requestFocus()
                            },
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = text,
                            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                            color = if (isEditable) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                        )
                    }
                }
                
                Spacer(Modifier.width(8.dp))
                IconButton(onClick = onOpenCamera) {
                    Icon(
                        imageVector = Icons.Filled.PhotoCamera,
                        contentDescription = "Usar Câmera",
                        tint = MaterialTheme.colorScheme.primary
                    )
                }
            }
            
            Box(modifier = Modifier.size(1.dp)) {
                androidx.compose.foundation.text.BasicTextField(
                    value = typedDigits,
                    onValueChange = { input ->
                        if (input.all { it.isDigit() } && input.length <= (totalDigits - editableStartIndex)) {
                            typedDigits = input
                        }
                    },
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                        keyboardType = androidx.compose.ui.text.input.KeyboardType.Number
                    ),
                    modifier = Modifier.focusRequester(focusRequester)
                )
            }
            
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Clique em qualquer quadrinho para começar a digitar a partir dele.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.secondary,
                modifier = Modifier.align(Alignment.Start)
            )
        }
    }

    Spacer(Modifier.height(24.dp))
    val canConfirmManual = kmTotalFromPhoto != null || isFullyFilled
    Button(
        onClick = onConfirm,
        enabled = canConfirmManual,
        modifier = Modifier.fillMaxWidth()
    ) {
        Text("Confirmar")
    }
    Spacer(Modifier.height(8.dp))
}

@Composable
fun ReciboFinalStep(
    deltaKm: Int,
    isDescansoSemanal: Boolean,
    onDescansoChanged: (Boolean) -> Unit,
    onConfirm: () -> Unit
) {
    val currentTime = remember<Long> { System.currentTimeMillis() }

    val futureDate = remember(isDescansoSemanal, currentTime) {
        val hoursToAdd = if (isDescansoSemanal) 24 else 11
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
        val dateFormat = SimpleDateFormat("dd/MM", Locale.forLanguageTag("pt-BR"))
        val timeFormat = SimpleDateFormat("HH:mm", Locale.forLanguageTag("pt-BR"))
        
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
                    onCheckedChange = null
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
