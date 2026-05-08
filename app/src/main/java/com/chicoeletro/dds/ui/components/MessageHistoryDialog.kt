// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/MessageHistoryDialog.kt
// Função: Exibição do histórico de mensagens enviadas pela equipe.

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.chicoeletro.dds.features.communication.TeamMessage
import java.text.SimpleDateFormat
import java.util.Locale

@Composable
fun MessageHistoryDialog(
    messages: List<TeamMessage>,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = MaterialTheme.shapes.large,
            tonalElevation = 6.dp,
            modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth(0.9f)
        ) {
            Column(Modifier.padding(24.dp)) {
                Text(
                    text = "Histórico de Mensagens",
                    style = MaterialTheme.typography.headlineSmall
                )
                
                Spacer(Modifier.height(16.dp))
                
                if (messages.isEmpty()) {
                    Box(Modifier.fillMaxWidth().height(100.dp), contentAlignment = Alignment.Center) {
                        Text("Nenhuma mensagem enviada recentemente.")
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.heightIn(max = 450.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(messages) { msg ->
                            MessageHistoryItem(msg)
                            HorizontalDivider(Modifier.padding(top = 8.dp), thickness = 0.5.dp, color = Color.LightGray)
                        }
                    }
                }
                
                Spacer(Modifier.height(24.dp))
                
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("Fechar")
                }
            }
        }
    }
}

@Composable
private fun MessageHistoryItem(msg: TeamMessage) {
    val df = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale("pt", "BR"))
    val dateStr = msg.timestamp?.let { df.format(it) } ?: "---"

    Column(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Para: ${msg.toSetor}",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            Text(
                text = dateStr,
                style = MaterialTheme.typography.bodySmall,
                color = Color.Gray
            )
        }
        
        Spacer(Modifier.height(4.dp))
        
        Text(
            text = msg.content,
            style = MaterialTheme.typography.bodyMedium
        )
        
        Spacer(Modifier.height(4.dp))
        
        Text(
            text = "Status: ${msg.status}",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = if (msg.status == "LIDO") Color(0xFF2E7D32) else Color.Gray
        )
    }
}
