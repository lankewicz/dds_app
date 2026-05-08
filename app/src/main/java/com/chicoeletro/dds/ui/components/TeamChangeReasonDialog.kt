// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TeamChangeReasonDialog.kt
// Função: Diálogo para seleção do motivo de alteração do prefixo da equipe.
//         Diferencia entre mudança de veículo (mantém histórico) e nova equipe (limpa cache).
// Tecnologias: Jetpack Compose, Material3.

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

enum class TeamChangeReason {
    VEHICLE_CHANGE, // Troca de placa/veículo (mantém histórico)
    NEW_TEAM        // Tablet para nova equipe (limpa histórico local)
}

@Composable
fun TeamChangeReasonDialog(
    oldPrefix: String,
    newPrefix: String,
    onConfirm: (TeamChangeReason) -> Unit,
    onCancel: () -> Unit
) {
    var selectedReason by remember { mutableStateOf<TeamChangeReason?>(null) }

    AlertDialog(
        onDismissRequest = onCancel,
        icon = { Icon(Icons.Default.Warning, contentDescription = null, tint = Color(0xFFFF9800), modifier = Modifier.size(32.dp)) },
        title = {
            Text(
                "Solicitação de Alteração",
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Aviso ROGALOG (🚨 Importante)
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.5f),
                    shape = MaterialTheme.shapes.medium
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Info, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.width(12.dp))
                        Text(
                            "ATENÇÃO: A alteração da identificação da equipe só deve ser realizada sob orientação da equipe do ROGALOG.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                Text(
                    "Você está mudando o prefixo de \"$oldPrefix\" para \"$newPrefix\". Qual o motivo da alteração?",
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Center
                )

                // Opção 1: Troca de Veículo
                OutlinedCard(
                    onClick = { selectedReason = TeamChangeReason.VEHICLE_CHANGE },
                    colors = CardDefaults.outlinedCardColors(
                        containerColor = if (selectedReason == TeamChangeReason.VEHICLE_CHANGE) 
                            MaterialTheme.colorScheme.primaryContainer else Color.Transparent
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = selectedReason == TeamChangeReason.VEHICLE_CHANGE,
                            onClick = { selectedReason = TeamChangeReason.VEHICLE_CHANGE }
                        )
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.LocalShipping, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Mudança de Veículo / Placa", fontWeight = FontWeight.Bold)
                            }
                            Text(
                                "A equipe permanece a mesma. O histórico será vinculado ao novo prefixo.",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }

                // Opção 2: Nova Equipe
                OutlinedCard(
                    onClick = { selectedReason = TeamChangeReason.NEW_TEAM },
                    colors = CardDefaults.outlinedCardColors(
                        containerColor = if (selectedReason == TeamChangeReason.NEW_TEAM) 
                            MaterialTheme.colorScheme.primaryContainer else Color.Transparent
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = selectedReason == TeamChangeReason.NEW_TEAM,
                            onClick = { selectedReason = TeamChangeReason.NEW_TEAM }
                        )
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.PersonAdd, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Nova Equipe no Tablet", fontWeight = FontWeight.Bold)
                            }
                            Text(
                                "O tablet mudou de mãos. O histórico anterior será removido deste aparelho.",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { selectedReason?.let { onConfirm(it) } },
                enabled = selectedReason != null
            ) {
                Text("Confirmar Alteração")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) {
                Text("Cancelar")
            }
        }
    )
}
