// Módulo: app/src/main/java/com/chicoeletro/dds/features/team/TeamEditDialog.kt
// Função: Interface para edição de dados da equipe. Permite atualizar o nome do grupo e a 
//         composição de eletricistas ativos em tempo de execução.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

// MÃ³dulo: app/src/main/java/com/chicoeletro/dds/features/team/TeamEditDialog.kt
// SOLUÇÃO DEFINITIVA: InputMethodManager direto + WindowInsetsCompat

package com.chicoeletro.dds.features.team

import android.app.Activity
import android.content.Context
import android.util.Log
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.KeyboardHide
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.launch
import java.util.Locale
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeamEditDialog(
    initialTeamName: String,
    initialMembers: List<String>,
    initialWorkSchedule: com.chicoeletro.dds.core.WorkSchedule = com.chicoeletro.dds.core.WorkSchedule(),
    mandatory: Boolean = false,
    onDismiss: () -> Unit,
    onSave: (teamName: String, members: List<String>, schedule: com.chicoeletro.dds.core.WorkSchedule) -> Unit,
) {
    BackHandler(enabled = true) { /* bloqueado: use os botões */ }

    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // ═══════════════════════════════════════════════════════════════════════════════
    // IMPORTANTE: view capturado DENTRO do Dialog (não fora!)
    // ═══════════════════════════════════════════════════════════════════════════════

    val configuration = LocalConfiguration.current
    val isCompactLayout = configuration.screenWidthDp < 700
    // Firestore - formação/histórico de equipe
    val formationRepo = remember { TeamFormationRepository(db = FirebaseFirestore.getInstance()) }


    // Estado do formulário
    val ptBr = remember { Locale.forLanguageTag("pt-BR") }

    var teamName by remember { mutableStateOf(initialTeamName) }
    val members = remember {
        mutableStateListOf<String>().apply {
            addAll(initialMembers.filter { it.isNotBlank() })
            add("")
        }
    }

    var workSchedule by remember { mutableStateOf(initialWorkSchedule) }
    var showScheduleConfig by remember { mutableStateOf(false) }

    // controla se usuário já mexeu manualmente nos participantes (para não sobrescrever)
    var membersTouched by remember { mutableStateOf(false) }
    var isLoadingFormation by remember { mutableStateOf(false) }
    var lastLoadedKey by remember { mutableStateOf<String?>(null) }
    var wasTeamFieldFocused by remember { mutableStateOf(false) }

    fun normalizeTeamName(raw: String): String = raw.trim().uppercase(ptBr)
    fun normalizeMember(raw: String): String = raw.trim().uppercase(ptBr)

    fun normalizedMembers(): List<String> =
        members.map(::normalizeMember)
            .filter { it.isNotBlank() }
            .distinct()

    fun isTeamNameValid(name: String): Boolean {
        val teamTrimmed = name.trim()
        val upper = teamTrimmed.uppercase(ptBr)

        val minOk = teamTrimmed.length >= 5
        val maxOk = teamTrimmed.length <= 11
        val startsWithForbidden = listOf("CA", "PG", "LO", "MA", "CB").any { upper.startsWith(it) }
        val noSpacesOk = !teamTrimmed.contains(' ')
        val isAlphanumeric = teamTrimmed.all { it.isLetterOrDigit() }

        return minOk && maxOk && !startsWithForbidden && noSpacesOk && isAlphanumeric
    }

    val teamNameValid by remember(teamName) { derivedStateOf { isTeamNameValid(teamName) } }
    val canSave by remember(teamName, members) {
        derivedStateOf { teamName.trim().isNotBlank() && normalizedMembers().isNotEmpty() }
    }
    fun triggerLoadFormationIfNeeded() {
        val key = normalizeTeamName(teamName)
        if (!isTeamNameValid(key)) return
        if (lastLoadedKey == key) return

        scope.launch {
            isLoadingFormation = true
            val formation = runCatching { formationRepo.getCurrent(key) }.getOrNull()
            isLoadingFormation = false

            if (formation != null && formation.members.isNotEmpty()) {
                lastLoadedKey = key

                // aplica só se usuário não "tocou" na lista nesta abertura
                if (!membersTouched) {
                    members.clear()
                    members.addAll(formation.members.map { it.uppercase(ptBr) })
                    members.add("")
                    Toast.makeText(context, "Formação carregada para $key", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(
                        context,
                        "Formação encontrada para $key (não aplicada porque você já editou participantes)",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }
    // =========================================================================
    // NOVO: buscar a última formação no Firestore ao PERDER O FOCO
    // - UX mais previsível: usuário digita, sai do campo, e então carrega


    // ═══════════════════════════════════════════════════════════════════════════════
    // UI - Dialog
    // ═══════════════════════════════════════════════════════════════════════════════
    Dialog(
        onDismissRequest = { /* bloqueado */ },
        properties = DialogProperties(
            dismissOnClickOutside = false,
            dismissOnBackPress = false,
            usePlatformDefaultWidth = false
        )
    ) {
        // CAPTURA view AQUI DENTRO do Dialog (crucial!)
        val view = LocalView.current
        

        // ═══════════════════════════════════════════════════════════════════
        // FUNÇÃO QUE REALMENTE FUNCIONA (testada em Dialogs)
        // ═══════════════════════════════════════════════════════════════════
        fun hideKeyboard() {
            // Método 1: WindowInsetsCompat (mais moderno, funciona melhor em Dialogs)
            ViewCompat.getWindowInsetsController(view)?.hide(WindowInsetsCompat.Type.ime())

            // Método 2: InputMethodManager (fallback confiável)
            val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
            imm?.hideSoftInputFromWindow(view.windowToken, 0)

            // Método 3: Tentar na Activity também (alguns dispositivos precisam)
            val activity = context as? Activity
            activity?.currentFocus?.let { focusedView ->
                imm?.hideSoftInputFromWindow(focusedView.windowToken, 0)
            }

            // Post para re-executar após o frame (alguns IMEs atrasam)
            view.postDelayed({
                ViewCompat.getWindowInsetsController(view)?.hide(WindowInsetsCompat.Type.ime())
                imm?.hideSoftInputFromWindow(view.windowToken, 0)
            }, 100)

            Log.d("TeamEditDialog", "hideKeyboard executado")
        }

        Surface(
            shape = MaterialTheme.shapes.extraLarge,
            tonalElevation = 4.dp,
            modifier = Modifier
                .imePadding()
                .pointerInput(Unit) {
                    detectTapGestures(onTap = { hideKeyboard() })
                }
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(18.dp)
            ) {
                Text(
                    text = "Editar Equipe",
                    style = MaterialTheme.typography.headlineSmall
                )

                if (mandatory) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = "Cadastro obrigatório: informe a equipe e ao menos um participante para continuar.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Spacer(Modifier.height(12.dp))

                if (isCompactLayout) {
                    // Layout compacto (celular): empilha os cards para evitar ficar "minúsculo" e parecer que sumiu
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        Box(modifier = Modifier.fillMaxWidth().weight(1f, fill = true)) {
                            TeamCard(
                                teamName = teamName,
                                onTeamNameChange = { raw -> teamName = raw.uppercase(ptBr).trimStart() },
                                teamNameValid = teamNameValid,
                                onDone = { hideKeyboard() },
                                onTeamNameFocusChanged = { focused ->
                                    // Dispara APENAS quando perde o foco (true -> false)
                                    if (wasTeamFieldFocused && !focused) triggerLoadFormationIfNeeded()
                                    wasTeamFieldFocused = focused
                                },
                                onEditSchedule = { showScheduleConfig = true }
                            )
                        }

                        Box(modifier = Modifier.fillMaxWidth().weight(1f, fill = true)) {
                            ParticipantsCard(
                                members = members,
                                normalizedCount = normalizedMembers().size,
                                onHideKeyboard = { hideKeyboard() },
                                onAdd = { if (members.isEmpty() || members.last().isNotBlank()) members.add("") },
                                onClear = { members.clear(); members.add(""); membersTouched = true },
                                onMemberChange = { index, new ->
                                    members[index] = new.uppercase(ptBr)
                                    membersTouched = true
                                    if (members.last().isNotBlank()) {
                                        members.add("")
                                    }
                                },
                                onRemove = { index ->
                                    if (index in members.indices) {
                                        members.removeAt(index)
                                        if (members.isEmpty() || members.last().isNotBlank()) members.add("")
                                        membersTouched = true
                                    }
                                },
                                onDone = { hideKeyboard() }
                            )
                        }
                    }
                } else {
                    // Layout largo (tablet/desktop): lado a lado
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                            TeamCard(
                                teamName = teamName,
                                onTeamNameChange = { raw -> teamName = raw.uppercase(ptBr).trimStart() },
                                teamNameValid = teamNameValid,
                                onDone = { hideKeyboard() },
                                onTeamNameFocusChanged = { focused ->
                                    if (wasTeamFieldFocused && !focused) triggerLoadFormationIfNeeded()
                                    wasTeamFieldFocused = focused
                                },
                                onEditSchedule = { showScheduleConfig = true }
                            )
                        }

                        Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                            ParticipantsCard(
                                members = members,
                                normalizedCount = normalizedMembers().size,
                                onHideKeyboard = { hideKeyboard() },
                                onAdd = { if (members.isEmpty() || members.last().isNotBlank()) members.add("") },
                                onClear = { members.clear(); members.add(""); membersTouched = true },
                                onMemberChange = { index, new ->
                                    members[index] = new.uppercase(ptBr)
                                    membersTouched = true
                                    if (members.last().isNotBlank()) {
                                        members.add("")
                                    }
                                },
                                onRemove = { index ->
                                    if (index in members.indices) {
                                        members.removeAt(index)
                                        if (members.isEmpty() || members.last().isNotBlank()) members.add("")
                                        membersTouched = true
                                    }
                                },
                                onDone = { hideKeyboard() }
                            )
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {

                    if (!mandatory) {
                        OutlinedButton(
                            onClick = {
                                hideKeyboard()
                                onDismiss()
                            },
                            modifier = Modifier.weight(1f)
                        ) { Text("Cancelar") }
                    }

                    Button(
                        onClick = {
                            hideKeyboard()
                            val team = normalizeTeamName(teamName)
                            val list = normalizedMembers()

                            if (team.isBlank() || list.isEmpty()) {
                                Toast.makeText(context, "Informe a equipe e pelo menos um participante", Toast.LENGTH_SHORT).show()
                                return@Button
                            }
                            if (!isTeamNameValid(team)) {
                                Toast.makeText(context, "PREFIXO inválido (5-11; letras/números; sem espaços; não iniciar com CA/PG/LO/MA/CB).", Toast.LENGTH_SHORT).show()
                                return@Button
                            }

                            // 1) Salva local (fluxo atual do app)
                            onSave(team, list, workSchedule)

                            Toast.makeText(context, "Equipe registrada com sucesso!", Toast.LENGTH_SHORT).show()
                            onDismiss()
                        },
                        enabled = canSave && teamNameValid,
                        modifier = Modifier.weight(1f)
                    ) { Text("Salvar") }
                }
            }
            if (showScheduleConfig) {
                com.chicoeletro.dds.ui.components.ScheduleConfigDialog(
                    initialSchedule = workSchedule,
                    onDismiss = { showScheduleConfig = false },
                    onSave = {
                        workSchedule = it
                        showScheduleConfig = false
                    }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TeamCard(
    teamName: String,
    onTeamNameChange: (String) -> Unit,
    teamNameValid: Boolean,
    onDone: () -> Unit,
    onTeamNameFocusChanged: (focused: Boolean) -> Unit = {},
    onEditSchedule: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxSize(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text("Equipe", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp)
                ) {
                    Text("Identificação", style = MaterialTheme.typography.titleSmall)
                    Text(
                        "Controle por equipe: o histórico é registrado pelo prefixo da equipe.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = teamName,
                onValueChange = onTeamNameChange,
                label = { Text("Nome da Equipe") },
                modifier = Modifier
                    .fillMaxWidth()
                    .onFocusChanged { fs ->
                        onTeamNameFocusChanged(fs.isFocused)
                    },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Characters,
                    imeAction = ImeAction.Done
                ),
                keyboardActions = KeyboardActions(
                    onDone = { onDone() }
                ),
                isError = teamName.isNotBlank() && !teamNameValid,
                supportingText = {
                    if (teamName.isNotBlank() && !teamNameValid) {
                        Text("PREFIXO inválido: 5-11 caracteres, letras/números, sem espaços, e não iniciar com CA/PG/LO/MA/CB.")
                    } else {
                        Text("Informe o prefixo da equipe (ex.: E3P01).")
                    }
                }
            )

            Spacer(Modifier.height(16.dp))
            OutlinedButton(
                onClick = onEditSchedule,
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.Add, contentDescription = null) 
                Spacer(Modifier.width(8.dp))
                Text("Configurar Horário de Trabalho")
            }
        }
    }
}

@Composable
private fun ParticipantsCard(
    members: MutableList<String>,
    normalizedCount: Int,
    onHideKeyboard: () -> Unit,
    onAdd: () -> Unit,
    onClear: () -> Unit,
    onMemberChange: (index: Int, new: String) -> Unit,
    onRemove: (index: Int) -> Unit,
    onDone: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxSize(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Participantes", style = MaterialTheme.typography.titleMedium)

                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(onClick = onHideKeyboard) {
                        Icon(Icons.Filled.KeyboardHide, contentDescription = "Ocultar teclado")
                    }

                    IconButton(onClick = onAdd) {
                        Icon(
                            imageVector = Icons.Filled.Add,
                            contentDescription = "Adicionar participante"
                        )
                    }

                    IconButton(onClick = onClear) {
                        Icon(
                            imageVector = Icons.Filled.DeleteSweep,
                            contentDescription = "Limpar participantes"
                        )
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Total: $normalizedCount", style = MaterialTheme.typography.bodySmall)
                if (normalizedCount < 1) {
                    Text(
                        "Mínimo 1 participante!",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }

            Spacer(Modifier.height(10.dp))

            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                itemsIndexed(
                    items = members,
                    key = { idx, _ -> idx }
                ) { index, value ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = value,
                            onValueChange = { new -> onMemberChange(index, new) },
                            label = { Text("Participante ${index + 1}") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                capitalization = KeyboardCapitalization.Characters,
                                imeAction = ImeAction.Done
                            ),
                            keyboardActions = KeyboardActions(
                                onDone = { onDone() }
                            )
                        )

                        Spacer(Modifier.width(8.dp))

                        IconButton(onClick = { onRemove(index) }) {
                            Icon(Icons.Default.Delete, contentDescription = "Remover")
                        }
                    }
                }
            }
        }
    }
}