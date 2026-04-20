// Módulo: app/src/main/java/com/chicoeletro/dds/features/online/OnlineConclusionFormScreen.kt
// Função: Tela de encerramento para o DDS Online. Permite registrar a participação da equipe 
//         após a reunião, coletando evidências e confirmando a execução remota.
// Tecnologias: Jetpack Compose, Material3, ViewModel.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.online

import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun OnlineConclusionFormScreen(
    sessionId: String,
    presentationTitle: String?,
    teamName: String?,
    role: String,
    photoUri: Uri,
    thumbUri: Uri?,
    isSaving: Boolean,
    onBack: () -> Unit,
    onRetakePhoto: () -> Unit,
    onSubmit: (OnlineConclusionForm) -> Unit,
) {
    var displayName by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var confirmPresence by remember { mutableStateOf(true) }
    var confirmPhoto by remember { mutableStateOf(true) }

    Column(
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Form de Conclusão – DDS Online", style = MaterialTheme.typography.titleLarge)

        if (!presentationTitle.isNullOrBlank()) {
            Text("Treinamento: $presentationTitle", style = MaterialTheme.typography.bodyMedium)
        }
        Text("Sessão: $sessionId", style = MaterialTheme.typography.bodySmall)
        if (!teamName.isNullOrBlank()) {
            Text("Equipe: $teamName", style = MaterialTheme.typography.bodySmall)
        }
        Text("Perfil: $role", style = MaterialTheme.typography.bodySmall)

        OutlinedTextField(
            value = displayName,
            onValueChange = { displayName = it },
            label = { Text("Seu nome (obrigatório)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            enabled = !isSaving
        )

        OutlinedTextField(
            value = notes,
            onValueChange = { notes = it },
            label = { Text("Observações (opcional)") },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isSaving
        )

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = confirmPresence,
                onCheckedChange = { confirmPresence = it },
                enabled = !isSaving
            )
            Text("Confirmo que participei do DDS Online.")
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = confirmPhoto,
                onCheckedChange = { confirmPhoto = it },
                enabled = !isSaving
            )
            Text("Confirmo que a foto anexada é minha, neste momento.")
        }

        HorizontalDivider()

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(
                onClick = onRetakePhoto,
                enabled = !isSaving
            ) { Text("Refazer foto") }

            OutlinedButton(
                onClick = onBack,
                enabled = !isSaving
            ) { Text("Voltar") }
        }

        Button(
            onClick = {
                val name = displayName.trim()
                if (name.isEmpty()) return@Button
                onSubmit(
                    OnlineConclusionForm(
                        displayName = name,
                        teamName = teamName,
                        role = role,
                        sessionId = sessionId,
                        presentationTitle = presentationTitle,
                        notes = notes.trim().ifEmpty { null },
                        confirmPresence = confirmPresence,
                        confirmPhoto = confirmPhoto,
                        deviceInfo = android.os.Build.MODEL
                    )
                )
            },
            enabled = !isSaving && displayName.trim().isNotEmpty() && confirmPresence && confirmPhoto,
            modifier = Modifier.fillMaxWidth()
        ) {
            if (isSaving) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(10.dp))
                Text("Enviando…")
            } else {
                Text("Enviar conclusão")
            }
        }
    }
}