// Módulo: app/src/main/java/com/example/dds/features/form/FormScreen.kt
// Função: Tela de preenchimento e envio do formulário de DDS, com dados da equipe, tema, eletricistas, captura de foto e controle de tempo de leitura.
// Autor: Valdinei Lankewicz
//
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

// --- Firebase
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage

// --- Coroutines e datas
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

// --- imports teclado
import androidx.compose.material.icons.filled.KeyboardHide
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController

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

    val todosCamposValidos by derivedStateOf {
        equipe.trim().isNotBlank() &&
                tema.trim().isNotBlank() &&
                nomes.any { it.isNotBlank() } &&
                fotoUri != null &&
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
            contentColor   = MaterialTheme.colorScheme.onSurface       // texto sempre legível
        )
    ) {
        // LazyColumn com todos os campos do formulário.

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            contentPadding = PaddingValues(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Confirme os dados e clique em Concluir",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f) // Garante que o texto não "brigue" com o ícone
                    )

                    // Botão de ocultar teclado
                    IconButton(onClick = {
                        keyboardController?.hide()
                        focusManager.clearFocus()
                    }) {
                        Icon(Icons.Filled.KeyboardHide, "Ocultar teclado", tint = Color.Gray)
                    }
                }
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
                        modifier = Modifier.weight(1f).padding(vertical = 4.dp)
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
                        nomes.clear(); nomes.add("")
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
                        containerColor = if (fotoTirada)
                            MaterialTheme.colorScheme.primaryContainer
                        else MaterialTheme.colorScheme.primary
                    )
                ) {
                    Icon(Icons.Filled.CameraAlt, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(if (fotoTirada) "FOTO OK" else "Tirar Foto")
                }
            }

            // Botões finais
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    OutlinedButton(onClick = onBack, modifier = Modifier.width(120.dp)) {
                        Text("Voltar")
                    }

                    Button(
                        onClick = {
                            isSubmitting = true
                            val tempoFinal = System.currentTimeMillis()
                            val duracaoMillis =
                                tempoFinal - (tempoInicioMillis ?: tempoFinal)
                            val duracaoMin = duracaoMillis / 1000 / 60
                            val duracaoSeg = (duracaoMillis / 1000) % 60
                            val duracaoFormatada = "${duracaoMin}min ${duracaoSeg}s"
                            val mostrarAvisoDepois = duracaoMin < 2
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
                                submittedAt = now.format(DateTimeFormatter.ofPattern("dd-MM-yyyy - HH:mm"))
                            )
                            scope.launch {
                                try {
                                    val dataHoraNome =
                                        now.format(DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm"))
                                    val nomeFoto =
                                        "${trainingName}_${equipe}_$dataHoraNome.jpg"
                                    val storageRef =
                                        FirebaseStorage.getInstance().reference.child("$pastaFotos/ChicoEletro/Fotos/$nomeFoto")
                                    val thumbRef =
                                        FirebaseStorage.getInstance().reference.child("$pastaFotos/ChicoEletro/Thumb/$nomeFoto")

                                    storageRef.putFile(fotoUri!!).apply {
                                        addOnProgressListener {
                                            val pct =
                                                (100.0 * it.bytesTransferred / it.totalByteCount).toInt()
                                            Toast.makeText(
                                                context,
                                                "Enviando foto: $pct%",
                                                Toast.LENGTH_SHORT
                                            ).show()
                                        }
                                    }.await()

                                    val fotoUrl = storageRef.downloadUrl.await().toString()
                                    val thumbUrl = thumbUri?.let {
                                        thumbRef.putFile(it).await()
                                        thumbRef.downloadUrl.await().toString()
                                    } ?: fotoUrl

                                    FirebaseFirestore.getInstance()
                                        .collection(collectionName)
                                        .add(
                                            mapOf(
                                                "dataHora" to "${submission.dataConclusao} - ${submission.horaConclusao}",
                                                "duracao" to duracaoFormatada,
                                                "trainingName" to submission.trainingName,
                                                "equipe" to submission.equipe,
                                                "tema" to submission.tema,
                                                "eletricistas" to submission.eletricistas,
                                                "DataConclusao" to submission.dataConclusao,
                                                "HoraConclusao" to submission.horaConclusao,
                                                "headerDate" to submission.headerDate,
                                                "headerTitle" to submission.headerTitle,
                                                "fotoUrl" to fotoUrl,
                                                "thumbUrl" to thumbUrl
                                            )
                                        ).await()

                                    if (mostrarAvisoDepois) {
                                        tempoFormatadoAviso = duracaoFormatada
                                        mostrarAvisoTempo = true
                                        enviarDepoisDoAlerta = true
                                    } else {
                                        onSubmit(
                                            submission,
                                            LastTeamData(
                                                submission.equipe,
                                                submission.eletricistas
                                            )
                                        )
                                        // 🔹 avisa o container que concluiu
                                        onCompleted(
                                            submission.dataConclusao,
                                            submission.horaConclusao,
                                            duracaoFormatada
                                        )

                                        Toast.makeText(
                                            context,
                                            "Enviado com sucesso!",
                                            Toast.LENGTH_SHORT
                                        ).show()
                                    }
                                } catch (e: Exception) {
                                    Toast.makeText(
                                        context,
                                        "Erro: ${e.message}",
                                        Toast.LENGTH_LONG
                                    ).show()
                                } finally {
                                    isSubmitting = false
                                }
                            }
                        },
                        enabled = todosCamposValidos,
                        modifier = Modifier.width(120.dp)
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text("Concluir")
                        }
                    }
                }
            }
        }

// Alerta de tempo curto de leitura
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

                                    // 🔹 Usa o tempo calculado antes: tempoFormatadoAviso
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

                                        "É importante que o DDS seja realizado com atenção, lendo todo o conteúdo apresentado.\n\n"+

                                        "Discuta os temas apresentados entre os integrantes da equipe"


                            )
                        }
                    )
                }
            }
        }
}
