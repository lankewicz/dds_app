// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/AppNotices.kt
// Função: Componente de interface para avisos globais. Gerencia banners de atualização, 
//         avisos de versão de teste e mensagens críticas do sistema.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.chicoeletro.dds.features.turno.TurnoSnapshot

/**
 * Banner enfático para informar sobre atualizações disponíveis.
 * Posicionado no topo da tela principal.
 */
@Composable
fun UpdateBanner(
    onUpdateClick: () -> Unit,
    onDismiss: () -> Unit
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(8.dp),
        color = Color(0xFFFFF3E0), // Laranja bem claro/creme
        shape = RoundedCornerShape(8.dp),
        tonalElevation = 2.dp,
        shadowElevation = 2.dp
    ) {
        Row(
            modifier = Modifier
                .padding(12.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = Icons.Filled.SystemUpdate,
                contentDescription = null,
                tint = Color(0xFFEF6C00), // Laranja forte
                modifier = Modifier.size(32.dp)
            )

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Nova versão disponível!",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFE65100)
                )
                Text(
                    text = "O uso de uma versão desatualizada pode limitar a usabilidade e segurança do app.",
                    style = MaterialTheme.typography.bodySmall,
                    lineHeight = 16.sp,
                    color = Color(0xFF5D4037)
                )
            }

            Row {
                TextButton(onClick = onDismiss) {
                    Text("Depois", color = Color(0xFF795548))
                }
                Button(
                    onClick = onUpdateClick,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFEF6C00)
                    ),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 0.dp)
                ) {
                    Text("Atualizar")
                }
            }
        }
    }
}

/**
 * Diálogo de aviso sobre a obrigatoriedade e importância do DDS.
 * Exibido antes de acessar o relatório de produção caso haja DDS pendentes.
 */
@Composable
fun DdsWarningDialog(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(dismissOnClickOutside = false)
    ) {
        Surface(
            shape = MaterialTheme.shapes.large,
            tonalElevation = 6.dp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Icon(
                    imageVector = Icons.Filled.Warning,
                    contentDescription = null,
                    modifier = Modifier.size(48.dp),
                    tint = Color(0xFFFBC02D) // Amarelo vibrante para atenção
                )

                Text(
                    text = "Atenção: DDS Obrigatório",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )

                Text(
                    text = "A execução dos DDS é obrigatória.\n\nÉ fundamental para a conscientização e redução de riscos envolvidos em nosso trabalho.\n\nPor favor, realize os DDS pendentes com mais diligência.",
                    style = MaterialTheme.typography.bodyLarge,
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Voltar")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = onConfirm,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Text("Entendi, prosseguir")
                    }
                }
            }
        }
    }
}

/**
 * Aviso de interjornada (Art. 66/67).
 * Exibido quando o usuário tenta abrir um turno sem cumprir o descanso mínimo.
 */
@Composable
fun InterjornadaNotice(
    snapshot: TurnoSnapshot,
    onProceed: () -> Unit
) {
    val reqHours = if (snapshot.lastWasDescansoSemanal) 24 else 11

    Column(
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            imageVector = Icons.Filled.CheckCircle,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.error,
            modifier = Modifier.size(64.dp)
        )
        Spacer(Modifier.height(16.dp))

        Text(
            text = "Você está tentando abrir o turno antes de completar o intervalo mínimo de $reqHours horas (Art. 66/67).",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = onProceed,
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Ciente, prosseguir mesmo assim")
        }
    }
}