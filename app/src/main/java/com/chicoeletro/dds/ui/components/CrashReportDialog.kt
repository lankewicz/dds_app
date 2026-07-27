// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/CrashReportDialog.kt
// Função: Modal de relatório visual para exibir ao usuário/colaborador detalhes
//         técnicos de um fechamento anormal (crash) ocorrido no acesso anterior.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Done
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chicoeletro.dds.core.crash.CrashReport
import com.chicoeletro.dds.core.crash.CrashReportManager

@Composable
fun CrashReportDialog(
    report: CrashReport,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    var isSending by remember { mutableStateOf(false) }
    var sendSuccess by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = {
            if (!isSending) {
                CrashReportManager.clearCrashReport(context)
                onDismiss()
            }
        },
        icon = {
            Icon(
                imageVector = Icons.Default.Warning,
                contentDescription = "Alerta de Crash",
                tint = Color(0xFFEF4444),
                modifier = Modifier.size(36.dp)
            )
        },
        title = {
            Text(
                text = "Fechamento Inesperado no Último Acesso",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "O aplicativo foi encerrado de forma anormal em ${report.timestamp}. Geramos um diagnóstico para ajudar na solução:",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // Caixa de código/detalhes do erro
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(160.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xFF1E293B))
                        .border(1.dp, Color(0xFF334155), RoundedCornerShape(8.dp))
                        .padding(10.dp)
                ) {
                    val scrollState = rememberScrollState()
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(scrollState)
                    ) {
                        Text(
                            text = "❌ Erro: ${report.exceptionType.substringAfterLast('.')}",
                            color = Color(0xFFF87171),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                        if (report.message.isNotBlank()) {
                            Text(
                                text = "💬 Mensagem: ${report.message}",
                                color = Color(0xFFFBBF24),
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "📱 Dispositivo: ${report.deviceManufacturer} ${report.deviceModel} (Android ${report.androidVersion})",
                            color = Color(0xFF94A3B8),
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = report.stackTrace,
                            color = Color(0xFFCBD5E1),
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            lineHeight = 14.sp
                        )
                    }
                }

                // Opções de Ação: WhatsApp, Copiar, Servidor
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Botão WhatsApp
                    Button(
                        onClick = {
                            CrashReportManager.sendViaWhatsApp(context, report)
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF25D366),
                            contentColor = Color.White
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("WhatsApp", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }

                    // Botão Copiar
                    OutlinedButton(
                        onClick = {
                            val ok = CrashReportManager.copyToClipboard(context, report)
                            if (ok) {
                                Toast.makeText(
                                    context,
                                    "Relatório copiado para a área de transferência!",
                                    Toast.LENGTH_SHORT
                                ).show()
                            }
                        },
                        modifier = Modifier.weight(1f)
                    ) {
                        Icon(
                            imageVector = Icons.Default.ContentCopy,
                            contentDescription = "Copiar",
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(modifier = Modifier.width(3.dp))
                        Text("Copiar", fontSize = 11.sp)
                    }

                    // Botão Enviar ao Servidor (Firestore)
                    Button(
                        onClick = {
                            if (!isSending && !sendSuccess) {
                                isSending = true
                                CrashReportManager.sendToFirestore(context, report) { success ->
                                    isSending = false
                                    if (success) {
                                        sendSuccess = true
                                        Toast.makeText(
                                            context,
                                            "Relatório enviado ao servidor!",
                                            Toast.LENGTH_SHORT
                                        ).show()
                                    } else {
                                        Toast.makeText(
                                            context,
                                            "Não foi possível enviar ao servidor. Use o WhatsApp ou Copiar.",
                                            Toast.LENGTH_LONG
                                        ).show()
                                    }
                                }
                            }
                        },
                        enabled = !isSending && !sendSuccess,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (sendSuccess) Color(0xFF10B981) else MaterialTheme.colorScheme.primary
                        ),
                        modifier = Modifier.weight(1f)
                    ) {
                        if (isSending) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(14.dp),
                                color = Color.White,
                                strokeWidth = 2.dp
                            )
                        } else if (sendSuccess) {
                            Icon(
                                imageVector = Icons.Default.Done,
                                contentDescription = "Enviado",
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(2.dp))
                            Text("Enviado", fontSize = 10.sp)
                        } else {
                            Icon(
                                imageVector = Icons.Default.Send,
                                contentDescription = "Servidor",
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(2.dp))
                            Text("Servidor", fontSize = 10.sp)
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    CrashReportManager.clearCrashReport(context)
                    onDismiss()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Entendido & Concluir")
            }
        }
    )
}
