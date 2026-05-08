// Módulo: app/src/main/java/com/chicoeletro/dds/features/form/FormScreen.kt
// Função: Tela de formulário final para conclusão do treinamento. Coleta presença dos 
//         eletricistas, valida dados e gerencia a transição para submissão com foto.
// Tecnologias: Jetpack Compose, Material3, ViewModel.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
// - 02/06/2025: Implementação inicial dos campos de equipe e eletricistas.
// - 04/06/2025: Adicionado campo “Tema do DDS”.
// - 06/06/2025: Ajustado botão “Concluir” para habilitar apenas quando válidos.
// - 21/06/2025: Adicionado contador de caracteres, validação visual e botão “Limpar lista”.
// - 22/06/2025: Integração com câmera e envio de foto para Firebase Storage.
// - 30/06/2025: Corrigida altura infinita substituindo Column por LazyColumn.
// - 01/07/2025: Adicionado controle de tempo desde a leitura até a conclusão do DDS.
// - 01/07/2025: Alerta bloqueia retorno à tela inicial até confirmação do usuário.
// - 01/07/2025: ⬆️ Limitada a altura do Card principal para permitir rolagem total em telas pequenas (fillMaxHeight(0.9f))
// - 07/05/2026: Migração do envio de DDS para a nova arquitetura offline-first (SubmitDdsUseCase).
// - 08/05/2026: Adicionado tratamento de erro e limite de espaço para fotos; suporte a envio sem foto na falha.

package com.chicoeletro.dds.features.form

// --- Android SDK
import android.net.Uri
import android.widget.Toast

// --- Jetpack Compose
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

// --- Projeto interno
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.data.FormSubmission

// --- Coroutines e datas
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

// --- imports teclado
import androidx.compose.material.icons.filled.KeyboardHide
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController

import com.chicoeletro.dds.data.local.PendingDdsStore
import com.chicoeletro.dds.domain.SubmitDdsUseCase
import com.chicoeletro.dds.sync.DdsSyncScheduler
import com.chicoeletro.dds.domain.DdsSubmissionWindowException
import com.chicoeletro.dds.ui.training.canConcludeTrainingId

@Composable
fun FormScreen(
    trainingName: String,
    existing: Pair<FormSubmission, String>?,
    lastTeam: LastTeamData,
    headerDate: String,
    headerTitle: String,
    onBack: () -> Unit,
    onSubmit: (FormSubmission, LastTeamData) -> Unit,
    thumbUri: Uri? = null,
    fotoUri: Uri?,
    scope: CoroutineScope,
    setFotoUri: (Uri?) -> Unit,
    tempoInicioMillis: Long?,
    modoTesteAtivo: Boolean,
    // NOVOS PARÂMETROS 👇
    jaConcluido: Boolean = existing != null,
    onCompleted: (dataConclusao: String, horaConclusao: String, duracao: String) -> Unit = { _, _, _ -> }

) {
    val context = LocalContext.current

    // ocultar teclado
    val keyboardController = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current

    // --- Estados principais ---
    var equipe by remember { mutableStateOf(existing?.first?.equipe ?: lastTeam.equipe) }
    var tema by remember { mutableStateOf(existing?.first?.tema ?: "") }
    var isSubmitting by remember { mutableStateOf(false) }
    var mostrarAvisoTempo by remember { mutableStateOf(false) }
    var tempoFormatadoAviso by remember { mutableStateOf("") }
    var enviarDepoisDoAlerta by remember { mutableStateOf(false) }

    val nomes = remember {
        mutableStateListOf<String>().apply {
            if (existing != null) addAll(existing.first.eletricistas)
            else addAll(lastTeam.eletricistas)
        }
    }

    var photoErrorCount by remember { mutableStateOf(0) }

    val todosCamposValidos by derivedStateOf {
        equipe.trim().isNotBlank() &&
                tema.trim().isNotBlank() &&
                nomes.any { it.isNotBlank() } &&
                (fotoUri != null || photoErrorCount > 0) &&
                !isSubmitting &&
                !jaConcluido  // 👈 NÃO DEIXA CONCLUIR NOVAMENTE
    }

    val corFundo = if (modoTesteAtivo) Color(0xFF212121) else Color(0xBB000000)
    val collectionName = if (modoTesteAtivo) "TESTE_DDS" else "DDS"
    val pastaFotos = if (modoTesteAtivo) "TESTE_DDS_Fotos" else "DDS_Fotos"


    // Card com altura limitada para permitir rolagem (⬅️ correção aqui!)
    Box(Modifier.fillMaxSize().background(corFundo)) {
        if (modoTesteAtivo) {
            Box(
                Modifier.fillMaxWidth().background(Color.Yellow).padding(8.dp),
                contentAlignment = Alignment.TopCenter
            ) {
                Text(
                    text = "🔴 ATENÇÃO 🔴 MODO TESTE🔴 MODO TESTE🔴 MODO TESTE 🔴",
                    color = Color.Red,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
        Card(
            modifier = Modifier
                .fillMaxHeight(0.9f) // ⬅️ Máximo de 90% da tela
                .padding(16.dp)
                .widthIn(max = 400.dp)
                .align(Alignment.Center),
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface,        // fundo segue o tema
                contentColor = MaterialTheme.colorScheme.onSurface       // texto sempre legível
            )
        ) {
            Column(
                modifier = Modifier.fillMaxSize()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 8.dp, end = 12.dp, top = 8.dp, bottom = 4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = onBack,
                        enabled = !isSubmitting
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Voltar"
                        )
                    }

                    Text(
                        text = "Conclusão do DDS",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f)
                    )

                    IconButton(
                        onClick = {
                            keyboardController?.hide()
                            focusManager.clearFocus()
                        }
                    ) {
                        Icon(
                            Icons.Filled.KeyboardHide,
                            contentDescription = "Ocultar teclado",
                            tint = Color.Gray
                        )
                    }

                    Spacer(Modifier.width(8.dp))

                    Button(
                        onClick = {
                            if (!canConcludeTrainingId(trainingName)) {
                                Toast.makeText(
                                    context,
                                    "Este DDS está fora da janela de conclusão e pode apenas ser visualizado.",
                                    Toast.LENGTH_LONG
                                ).show()
                                return@Button
                            }

                            isSubmitting = true
                            val tempoFinal = System.currentTimeMillis()
                            val duracaoMillis =
                                tempoFinal - (tempoInicioMillis ?: tempoFinal)
                            val duracaoMin = duracaoMillis / 1000 / 60
                            val duracaoSeg = (duracaoMillis / 1000) % 60
                            val duracaoFormatada = "${duracaoMin}min ${duracaoSeg}s"
                            val now = LocalDateTime.now()
                            val submission = FormSubmission(
                                trainingName = trainingName,
                                equipe = equipe.trim(),
                                tema = tema.trim(),
                                eletricistas = nomes.filter { it.isNotBlank() },
                                dataConclusao = now.format(DateTimeFormatter.ofPattern("dd-MM-yyyy")),
                                horaConclusao = now.format(DateTimeFormatter.ofPattern("HH:mm")),
                                headerDate = headerDate,
                                headerTitle = headerTitle,
                                submittedAt = now.format(DateTimeFormatter.ofPattern("dd-MM-yyyy - HH:mm")),
                                duracao = duracaoFormatada
                            )
                            scope.launch {
                                try {
                                    val useCase = SubmitDdsUseCase(
                                        context = context,
                                        pendingStore = PendingDdsStore(context),
                                        scheduler = DdsSyncScheduler(
                                            context,
                                            collectionName,
                                            pastaFotos
                                        )
                                    )

                                    val uriToSubmit = if (photoErrorCount > 0 && fotoUri == null) null else fotoUri
                                    
                                    val savedSubmission = useCase.submitLocalFirst(
                                        submission = submission,
                                        fotoUri = uriToSubmit,
                                        thumbUri = thumbUri,
                                        collectionName = collectionName,
                                        pastaFotos = pastaFotos,
                                        duracaoFormatada = duracaoFormatada
                                    )

                                    onSubmit(
                                        savedSubmission,
                                        LastTeamData(
                                            savedSubmission.equipe,
                                            savedSubmission.eletricistas
                                        )
                                    )
                                    onCompleted(
                                        savedSubmission.dataConclusao,
                                        savedSubmission.horaConclusao,
                                        duracaoFormatada
                                    )
                                    val msgEnviado = if (uriToSubmit == null) {
                                        "DDS salvo sem foto devido a erros. Sincronização em segundo plano."
                                    } else {
                                        "DDS salvo no aparelho. Sincronização em segundo plano."
                                    }
                                    Toast.makeText(context, msgEnviado, Toast.LENGTH_SHORT).show()
                                    onBack()

                                } catch (e: DdsSubmissionWindowException) {
                                    Toast.makeText(
                                        context,
                                        e.message ?: "Este DDS está fora da janela permitida para conclusão.",
                                        Toast.LENGTH_LONG
                                    ).show()
                                } catch (e: Exception) {
                                    val errorMsg = e.message ?: "erro inesperado"
                                    val isSpaceError = errorMsg.contains("ENOSPC", ignoreCase = true) || 
                                                       errorMsg.contains("space", ignoreCase = true) || 
                                                       errorMsg.contains("espaço", ignoreCase = true)

                                    if (isSpaceError) {
                                        Toast.makeText(
                                            context,
                                            "Atenção: O tablet está sem espaço! Libere espaço apagando fotos/vídeos antigos ou limpando o cache, e tente novamente.",
                                            Toast.LENGTH_LONG
                                        ).show()
                                        setFotoUri(null)
                                    } else if (errorMsg.contains("ENOENT") || errorMsg.contains("Erro ao copiar Uri")) {
                                        photoErrorCount++
                                        if (photoErrorCount >= 2) {
                                            // Envia sem foto: apenas esvazia fotoUri e pede para confirmar novamente
                                            setFotoUri(null)
                                            Toast.makeText(
                                                context,
                                                "O erro persiste. Pressione Confirmar para enviar o treinamento sem foto.",
                                                Toast.LENGTH_LONG
                                            ).show()
                                        } else {
                                            Toast.makeText(
                                                context,
                                                "Houve um erro com a foto. Por favor, tire outra foto.",
                                                Toast.LENGTH_LONG
                                            ).show()
                                            setFotoUri(null)
                                        }
                                    } else {
                                        Toast.makeText(
                                            context,
                                            "Falha ao salvar DDS offline: $errorMsg",
                                            Toast.LENGTH_LONG
                                        ).show()
                                    }
                                } finally {
                                    isSubmitting = false
                                }
                            }
                        },
                        enabled = todosCamposValidos
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text("Confirmar")
                        }
                    }
                }

                HorizontalDivider()
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(16.dp),
                    contentPadding = PaddingValues(bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    item {
                        Text(
                            "Confirme os dados abaixo antes de finalizar.",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }

                    item {
                        OutlinedTextField(
                            value = equipe,
                            onValueChange = {},
                            label = { Text("Equipe:") },
                            enabled = false,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }

                    item {
                        OutlinedTextField(
                            value = tema,
                            onValueChange = { if (it.length <= 100) tema = it },
                            label = { Text("Tema do DDS:") },
                            placeholder = { Text("Digite o tema do treinamento") },
                            supportingText = { Text("${tema.length}/100") },
                            isError = tema.trim().isEmpty(),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }

                    item {
                        Text("Eletricistas:", style = MaterialTheme.typography.bodyMedium)
                        if (nomes.isEmpty()) nomes.add("")
                    }

                    itemsIndexed(nomes) { index, value ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            OutlinedTextField(
                                value = value,
                                onValueChange = { novo -> nomes[index] = novo },
                                label = { Text("Eletricista ${index + 1}") },
                                modifier = Modifier
                                    .weight(1f)
                                    .padding(vertical = 4.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            IconButton(onClick = {
                                if (nomes.size > 1) nomes.removeAt(index)
                                else nomes[index] = ""
                            }) {
                                Icon(
                                    Icons.Default.Delete,
                                    contentDescription = "Remover eletricista",
                                    tint = Color.Gray
                                )
                            }
                        }
                    }

                    item {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            TextButton(onClick = { nomes.add("") }) {
                                Text("+ Adicionar eletricista")
                            }
                            TextButton(onClick = {
                                nomes.clear()
                                nomes.add("")
                            }) {
                                Text("🧹 Limpar lista")
                            }
                        }
                    }

                    item {
                        val fotoTirada = fotoUri != null
                        Button(
                            onClick = { setFotoUri(null) },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !isSubmitting,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (fotoTirada) {
                                    MaterialTheme.colorScheme.primaryContainer
                                } else {
                                    MaterialTheme.colorScheme.primary
                                }
                            )
                        ) {
                            Icon(Icons.Filled.CameraAlt, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text(if (fotoTirada) "FOTO OK" else "Tirar Foto")
                        }
                    }
                }

                if (mostrarAvisoTempo) {
                    AlertDialog(
                        onDismissRequest = { mostrarAvisoTempo = false },
                        confirmButton = {
                            TextButton(onClick = {
                                mostrarAvisoTempo = false
                                if (enviarDepoisDoAlerta) {
                                    val now = LocalDateTime.now()
                                    val data = now.format(DateTimeFormatter.ofPattern("dd-MM-yyyy"))
                                    val hora = now.format(DateTimeFormatter.ofPattern("HH:mm"))

                                    val submissionDepoisAviso = FormSubmission(
                                        trainingName = trainingName,
                                        equipe = equipe.trim(),
                                        tema = tema.trim(),
                                        eletricistas = nomes.filter { it.isNotBlank() },
                                        dataConclusao = data,
                                        horaConclusao = hora,
                                        headerDate = headerDate,
                                        headerTitle = headerTitle,
                                        submittedAt = now.format(DateTimeFormatter.ofPattern("dd-MM-yyyy - HH:mm"))
                                    )

                                    onSubmit(
                                        submissionDepoisAviso,
                                        LastTeamData(
                                            equipe.trim(),
                                            nomes.filter { it.isNotBlank() }
                                        )
                                    )

                                    onCompleted(
                                        data,
                                        hora,
                                        tempoFormatadoAviso
                                    )

                                    Toast.makeText(
                                        context,
                                        "Enviado com sucesso!",
                                        Toast.LENGTH_SHORT
                                    ).show()

                                    enviarDepoisDoAlerta = false
                                }
                            }) {
                                Text("OK")
                            }
                        },
                        title = { Text("Atenção ao Treinamento") },
                        text = {
                            Text(
                                "Você concluiu o treinamento em apenas $tempoFormatadoAviso.\n\n" +
                                        "É importante que o DDS seja realizado com atenção, lendo todo o conteúdo apresentado.\n\n" +
                                        "Discuta os temas apresentados entre os integrantes da equipe"
                            )
                        }
                    )
                }
            }
        }
    }
}
