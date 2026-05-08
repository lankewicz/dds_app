// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/CommunicationDialog.kt
// Função: Diálogo para envio de mensagens entre equipes e setores (Oficina, Almoxarifado, Rotalog).
// Tecnologias: Jetpack Compose, Material3.

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog

@Composable
fun CommunicationDialog(
    equipeOrigem: String,
    onDismiss: () -> Unit,
    onSendMessage: (String, String) -> Unit,
    onViewHistory: () -> Unit
) {
    var messageText by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("OFICINA") }
    val destinations = listOf("OFICINA", "ALMOXARIFADO", "ROTALOG")

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = MaterialTheme.shapes.large,
            tonalElevation = 6.dp,
            modifier = Modifier.widthIn(max = 500.dp)
        ) {
            Column(Modifier.padding(24.dp)) {
                Text(
                    text = "Nova Mensagem",
                    style = MaterialTheme.typography.headlineSmall
                )
                
                Spacer(Modifier.height(16.dp))
                
                Text(
                    text = "Enviar para:",
                    style = MaterialTheme.typography.labelLarge
                )
                
                destinations.forEach { dest ->
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .selectable(
                                selected = (destination == dest),
                                onClick = { destination = dest }
                            )
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = (destination == dest),
                            onClick = { destination = dest }
                        )
                        Text(
                            text = dest,
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.padding(start = 8.dp)
                        )
                    }
                }
                
                Spacer(Modifier.height(16.dp))
                
                OutlinedTextField(
                    value = messageText,
                    onValueChange = { messageText = it },
                    label = { Text("Sua mensagem") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3
                )
                
                Spacer(Modifier.height(24.dp))
                
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onViewHistory) {
                        Text("Ver Histórico")
                    }
                    
                    Row {
                        TextButton(onClick = onDismiss) {
                            Text("Cancelar")
                        }
                        Spacer(Modifier.width(8.dp))
                        Button(
                            onClick = { 
                                if (messageText.isNotBlank()) {
                                    onSendMessage(destination, messageText)
                                }
                            },
                            enabled = messageText.isNotBlank()
                        ) {
                            Text("Enviar")
                        }
                    }
                }
            }
        }
    }
}
