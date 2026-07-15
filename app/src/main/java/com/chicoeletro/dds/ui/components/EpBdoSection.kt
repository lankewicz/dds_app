package com.chicoeletro.dds.ui.components

import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import com.google.firebase.firestore.FirebaseFirestore
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import com.chicoeletro.dds.features.construcao.MitCatalogManager
import com.chicoeletro.dds.features.construcao.Atividade
import kotlinx.coroutines.flow.firstOrNull

data class EpBdoTarefaItem(
    val tarefa: String = "",
    val quantidade: String = "1",
    val sinal: String = "+",
    val psInicial: String = "",
    val psFinal: String = "",
    val materialObs: String = "",
    val veiculo: String = ""
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EpBdoSection(
    equipe: String,
    online: Boolean,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val db = remember { FirebaseFirestore.getInstance() }
    val sharedPrefs = remember { context.getSharedPreferences("ep_bdo_prefs", Context.MODE_PRIVATE) }

    var activitiesList by remember { mutableStateOf(listOf<Atividade>()) }
    LaunchedEffect(context) {
        val teamData = com.chicoeletro.dds.core.LastTeamStore.carregar(context).firstOrNull()
        val teamType = teamData?.teamType ?: "EP"
        if (!MitCatalogManager.getLocalFile(context, teamType).exists()) {
            MitCatalogManager.downloadCatalog(context, teamType)
        }
        activitiesList = MitCatalogManager.loadLocalCatalog(context, teamType)
    }

    // Abas
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Identificação", "Serviços & Tarefas")

    // Cabeçalho
    var ordemMae by remember { mutableStateOf("") }
    var pop by remember { mutableStateOf("") }
    var origemCopel by remember { mutableStateOf("") }
    var equipamentoTipo by remember { mutableStateOf("Transformador") } // Transformador ou Chave
    var equipamentoCodigo by remember { mutableStateOf("") }
    var cidade by remember { mutableStateOf("") }
    var descricao by remember { mutableStateOf("") }

    // Odômetro
    var kmInicio by remember { mutableStateOf("") }
    var kmFim by remember { mutableStateOf("") }

    // Horários
    var horaSaida by remember { mutableStateOf("") }
    var horaInicio by remember { mutableStateOf("") }
    var horaFim by remember { mutableStateOf("") }
    var horaRetorno by remember { mutableStateOf("") }

    // Gedis
    var gedisInstaladoSerie by remember { mutableStateOf("") }
    var gedisInstaladoImpedancia by remember { mutableStateOf("") }
    var gedisInstaladoMarca by remember { mutableStateOf("") }
    var gedisInstaladoFabricacao by remember { mutableStateOf("") }
    var gedisInstaladoPotencia by remember { mutableStateOf("") }

    var gedisRetiradoSerie by remember { mutableStateOf("") }
    var gedisRetiradoImpedancia by remember { mutableStateOf("") }
    var gedisRetiradoMarca by remember { mutableStateOf("") }
    var gedisRetiradoFabricacao by remember { mutableStateOf("") }
    var gedisRetiradoPotencia by remember { mutableStateOf("") }

    // Alertas de Tarefas Legadas (MIT 160903 -> 160904)
    data class LegacyTaskReplacement(val newCode: String, val message: String)

    val legacyTaskMap = remember {
        mapOf(
            "669" to LegacyTaskReplacement("612", "A tarefa 669 (Roçada RDR M²) foi substituída pela tarefa 612 no novo MIT."),
            "670" to LegacyTaskReplacement("613", "A tarefa 670 (Roçada RDR 10M²) foi substituída pela tarefa 613 no novo MIT."),
            "671" to LegacyTaskReplacement("614", "A tarefa 671 (Roçada RDR 100M²) foi substituída pela tarefa 614 no novo MIT."),
            "672" to LegacyTaskReplacement("612", "A tarefa 672 (Roçada RDR M² Tipo 2) foi substituída por 612 (ou roçada mecanizada 615/616) no novo MIT."),
            "673" to LegacyTaskReplacement("613", "A tarefa 673 (Roçada RDR 10M² Tipo 2) foi substituída por 613 (ou roçada mecanizada 615/616) no novo MIT."),
            "674" to LegacyTaskReplacement("614", "A tarefa 674 (Roçada RDR 100M² Tipo 2) foi substituída por 614 (ou roçada mecanizada 617/618) no novo MIT."),
            "675" to LegacyTaskReplacement("612", "A tarefa 675 (Roçada RDR M² Tipo 3) foi substituída por 612 (ou roçada mecanizada 615/616) no novo MIT."),
            "676" to LegacyTaskReplacement("613", "A tarefa 676 (Roçada RDR 10M² Tipo 3) foi substituída por 613 (ou roçada mecanizada 615/616) no novo MIT."),
            "677" to LegacyTaskReplacement("614", "A tarefa 677 (Roçada RDR 100M² Tipo 3) foi substituída por 614 (ou roçada mecanizada 617/618) no novo MIT."),
            "668" to LegacyTaskReplacement("621", "A tarefa 668 (Corte de Bambu) foi alterada no novo MIT. Recomenda-se usar 621 (ou 622/623)."),
            "967" to LegacyTaskReplacement("970", "A tarefa 967 (Abertura Faixa Bambu) foi alterada no novo MIT. Recomenda-se usar 970 (ou 971).")
        )
    }

    var showLegacyWarningDialog by remember { mutableStateOf(false) }
    var activeLegacyTaskIndex by remember { mutableIntStateOf(-1) }
    var activeLegacyOldCode by remember { mutableStateOf("") }
    var activeLegacyNewCode by remember { mutableStateOf("") }
    var activeLegacyMessage by remember { mutableStateOf("") }

    // Tabela de tarefas
    val tarefasList = remember { mutableStateListOf(EpBdoTarefaItem()) }

    var isSubmitting by remember { mutableStateOf(false) }

    // Carregar CAR (região) anterior do Equipamento
    LaunchedEffect(Unit) {
        val savedCar = sharedPrefs.getString("ultimo_car_regiao", "") ?: ""
        if (savedCar.length == 5) {
            equipamentoCodigo = "$savedCar-"
        }
    }

    // Regras de validação
    val isOrdemMaeValida = ordemMae.length <= 20
    val isPopValido = pop.isEmpty() || Regex("^\\d-\\d{3}\$").matches(pop)
    val isOrigemCopelValida = origemCopel.isEmpty() || origemCopel.all { it.isDigit() }
    val isEquipamentoValido = equipamentoCodigo.isEmpty() || Regex("^\\d{5}-[A-Z0-9]\\d{3}[A-Z0-9]\$").matches(equipamentoCodigo.uppercase())

    val podeEnviar = ordemMae.isNotBlank() && pop.isNotBlank() && equipamentoCodigo.isNotBlank() &&
            isOrdemMaeValida && isPopValido && isOrigemCopelValida && isEquipamentoValido &&
            tarefasList.isNotEmpty() && tarefasList.all { it.tarefa.isNotBlank() && it.quantidade.isNotBlank() }

    Column(
        modifier = modifier.fillMaxSize()
    ) {
        // TabRow no Topo
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.primary,
            modifier = Modifier.fillMaxWidth()
        ) {
            tabs.forEachIndexed { index, title ->
                Tab(
                    selected = selectedTab == index,
                    onClick = { selectedTab = index },
                    text = {
                        Text(
                            text = title,
                            fontWeight = if (selectedTab == index) FontWeight.Bold else FontWeight.Normal,
                            fontSize = 14.sp
                        )
                    }
                )
            }
        }

        // Conteúdo Scrollable das Abas
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            if (selectedTab == 0) {
                // ABA 1: IDENTIFICAÇÃO
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    Text(
                        text = "Identificação da Obra / Serviço",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )

                    // Seção Cabeçalho
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Text("Cabeçalho do BDO", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    OutlinedTextField(
                                        value = ordemMae,
                                        onValueChange = { if (it.length <= 20) ordemMae = it },
                                        label = { Text("Ordem Mãe (Max 20)") },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = true,
                                        isError = !isOrdemMaeValida
                                    )
                                    if (!isOrdemMaeValida) {
                                        Text("Máximo 20 caracteres", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                                    }
                                }

                                Column(modifier = Modifier.weight(1f)) {
                                    OutlinedTextField(
                                        value = pop,
                                        onValueChange = {
                                            val digits = it.filter { char -> char.isDigit() }.take(4)
                                            pop = if (digits.length > 1) {
                                                "${digits[0]}-${digits.substring(1)}"
                                            } else {
                                                digits
                                            }
                                        },
                                        label = { Text("POP (ex: 9-999)") },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = true,
                                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                        isError = !isPopValido
                                    )
                                    if (!isPopValido && pop.isNotEmpty()) {
                                        Text("Formato deve ser 9-999", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                                    }
                                }
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedTextField(
                                    value = origemCopel,
                                    onValueChange = { if (it.all { char -> char.isDigit() }) origemCopel = it },
                                    label = { Text("Nº Origem Copel") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                    isError = !isOrigemCopelValida
                                )

                                Column(modifier = Modifier.weight(1f)) {
                                    Text("Tipo Equipamento", style = MaterialTheme.typography.labelSmall)
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        RadioButton(
                                            selected = equipamentoTipo == "Transformador",
                                            onClick = { equipamentoTipo = "Transformador" }
                                        )
                                        Text("TR", style = MaterialTheme.typography.bodyMedium)
                                        Spacer(modifier = Modifier.width(8.dp))
                                        RadioButton(
                                            selected = equipamentoTipo == "Chave",
                                            onClick = { equipamentoTipo = "Chave" }
                                        )
                                        Text("CF", style = MaterialTheme.typography.bodyMedium)
                                    }
                                }
                            }

                            Column(modifier = Modifier.fillMaxWidth()) {
                                OutlinedTextField(
                                    value = equipamentoCodigo,
                                    onValueChange = { input ->
                                        val clean = input.filter { char -> char.isLetterOrDigit() }.take(10)
                                        equipamentoCodigo = if (clean.length > 5) {
                                            val car = clean.substring(0, 5)
                                            val rest = clean.substring(5).uppercase()
                                            "$car-$rest"
                                        } else {
                                            clean
                                        }
                                        
                                        if (clean.length >= 5) {
                                            val car = clean.substring(0, 5)
                                            if (car.all { c -> c.isDigit() }) {
                                                sharedPrefs.edit().putString("ultimo_car_regiao", car).apply()
                                            }
                                        }
                                    },
                                    label = { Text("Equipamento (99999-X999X)") },
                                    modifier = Modifier.fillMaxWidth(),
                                    singleLine = true,
                                    isError = !isEquipamentoValido
                                )
                                if (!isEquipamentoValido && equipamentoCodigo.isNotEmpty()) {
                                    Text("Formato deve ser 99999-X999X", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                                }
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedTextField(
                                    value = cidade,
                                    onValueChange = { cidade = it },
                                    label = { Text("Cidade") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true
                                )
                            }

                            OutlinedTextField(
                                value = descricao,
                                onValueChange = { descricao = it },
                                label = { Text("Descrição do Serviço") },
                                modifier = Modifier.fillMaxWidth(),
                                minLines = 2,
                                maxLines = 4
                            )
                        }
                    }

                    // Seção de KM e Horários
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            Text("Controle de KM e Horários", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(16.dp)
                            ) {
                                OdometerInputCompact(
                                    label = "KM Início",
                                    value = kmInicio,
                                    onValueChange = { kmInicio = it },
                                    modifier = Modifier.weight(1f)
                                )

                                OdometerInputCompact(
                                    label = "KM Fim",
                                    value = kmFim,
                                    onValueChange = { kmFim = it },
                                    modifier = Modifier.weight(1f)
                                )
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                TimeInputWithCapture(
                                    label = "Hora Saída",
                                    value = horaSaida,
                                    onValueChange = { horaSaida = it },
                                    modifier = Modifier.weight(1f)
                                )
                                TimeInputWithCapture(
                                    label = "Hora Início",
                                    value = horaInicio,
                                    onValueChange = { horaInicio = it },
                                    modifier = Modifier.weight(1f)
                                )
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                TimeInputWithCapture(
                                    label = "Hora Fim",
                                    value = horaFim,
                                    onValueChange = { horaFim = it },
                                    modifier = Modifier.weight(1f)
                                )
                                TimeInputWithCapture(
                                    label = "Hora Retorno",
                                    value = horaRetorno,
                                    onValueChange = { horaRetorno = it },
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                    }

                    // Seção GEDIS Instalado / Retirado
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            Text("Equipamentos de Subestação (GEDIS)", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)

                            // GEDIS INSTALADO
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text("GEDIS Instalado (Novo)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
                                OutlinedTextField(
                                    value = gedisInstaladoSerie,
                                    onValueChange = { if (it.all { char -> char.isDigit() }) gedisInstaladoSerie = it },
                                    label = { Text("Nº Série / GEDIS") },
                                    modifier = Modifier.fillMaxWidth(),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = gedisInstaladoImpedancia,
                                        onValueChange = { gedisInstaladoImpedancia = it },
                                        label = { Text("Impedância") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                    OutlinedTextField(
                                        value = gedisInstaladoMarca,
                                        onValueChange = { gedisInstaladoMarca = it },
                                        label = { Text("Marca") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = gedisInstaladoFabricacao,
                                        onValueChange = { gedisInstaladoFabricacao = it },
                                        label = { Text("Fabricação") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                    OutlinedTextField(
                                        value = gedisInstaladoPotencia,
                                        onValueChange = { gedisInstaladoPotencia = it },
                                        label = { Text("Potência") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                }
                            }

                            HorizontalDivider()

                            // GEDIS RETIRADO
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text("GEDIS Retirado (Antigo)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                                OutlinedTextField(
                                    value = gedisRetiradoSerie,
                                    onValueChange = { if (it.all { char -> char.isDigit() }) gedisRetiradoSerie = it },
                                    label = { Text("Nº Série / GEDIS") },
                                    modifier = Modifier.fillMaxWidth(),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = gedisRetiradoImpedancia,
                                        onValueChange = { gedisRetiradoImpedancia = it },
                                        label = { Text("Impedância") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                    OutlinedTextField(
                                        value = gedisRetiradoMarca,
                                        onValueChange = { gedisRetiradoMarca = it },
                                        label = { Text("Marca") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = gedisRetiradoFabricacao,
                                        onValueChange = { gedisRetiradoFabricacao = it },
                                        label = { Text("Fabricação") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                    OutlinedTextField(
                                        value = gedisRetiradoPotencia,
                                        onValueChange = { gedisRetiradoPotencia = it },
                                        label = { Text("Potência") },
                                        modifier = Modifier.weight(1f),
                                        singleLine = true
                                    )
                                }
                            }
                        }
                    }
                }
            } else {
                // ABA 2: SERVIÇOS & TAREFAS
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("Tabela de Serviços/Tarefas", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                                IconButton(onClick = { tarefasList.add(EpBdoTarefaItem()) }) {
                                    Icon(Icons.Default.Add, contentDescription = "Adicionar Tarefa", tint = MaterialTheme.colorScheme.primary)
                                }
                            }

                            tarefasList.forEachIndexed { index, item ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp),
                                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.6f))
                                ) {
                                    Column(
                                        modifier = Modifier.padding(12.dp),
                                        verticalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text("${index + 1}ª Tarefa", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                                            IconButton(onClick = { tarefasList.removeAt(index) }) {
                                                Icon(Icons.Default.Delete, contentDescription = "Remover Tarefa", tint = MaterialTheme.colorScheme.error)
                                            }
                                        }

                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            OutlinedTextField(
                                                value = item.tarefa,
                                                onValueChange = { input ->
                                                    tarefasList[index] = item.copy(tarefa = input)
                                                    val cleanInput = input.trim()
                                                    if (cleanInput.length == 3) {
                                                        val replacement = legacyTaskMap[cleanInput]
                                                        if (replacement != null) {
                                                            activeLegacyTaskIndex = index
                                                            activeLegacyOldCode = cleanInput
                                                            activeLegacyNewCode = replacement.newCode
                                                            activeLegacyMessage = replacement.message
                                                            showLegacyWarningDialog = true
                                                        }
                                                    }
                                                },
                                                label = { Text("Tarefa / Código") },
                                                modifier = Modifier.weight(1.5f),
                                                singleLine = true
                                            )

                                            OutlinedTextField(
                                                value = item.quantidade,
                                                onValueChange = { tarefasList[index] = item.copy(quantidade = it) },
                                                label = { Text("Quant") },
                                                modifier = Modifier.weight(1f),
                                                singleLine = true,
                                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                                            )

                                            var showSinalMenu by remember { mutableStateOf(false) }
                                            Box(modifier = Modifier.weight(1.2f)) {
                                                OutlinedTextField(
                                                    value = item.sinal,
                                                    onValueChange = {},
                                                    readOnly = true,
                                                    label = { Text("Sinal") },
                                                    modifier = Modifier.clickable { showSinalMenu = true },
                                                    enabled = false,
                                                    colors = TextFieldDefaults.colors(
                                                        disabledTextColor = MaterialTheme.colorScheme.onSurface,
                                                        disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant
                                                    )
                                                )
                                                DropdownMenu(
                                                    expanded = showSinalMenu,
                                                    onDismissRequest = { showSinalMenu = false }
                                                ) {
                                                    listOf("+ (Aplicado)", "- (Retirado)", "*+ (Reuso)", "*- (Retirado p/ reuso)").forEach { s ->
                                                        DropdownMenuItem(
                                                            text = { Text(s) },
                                                            onClick = {
                                                                val cleanSinal = s.substringBefore(" ")
                                                                tarefasList[index] = item.copy(sinal = cleanSinal)
                                                                showSinalMenu = false
                                                            }
                                                        )
                                                    }
                                                }
                                            }
                                        }

                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            OutlinedTextField(
                                                value = item.psInicial,
                                                onValueChange = { tarefasList[index] = item.copy(psInicial = it) },
                                                label = { Text("PS Inicial") },
                                                modifier = Modifier.weight(1f),
                                                singleLine = true
                                            )
                                            OutlinedTextField(
                                                value = item.psFinal,
                                                onValueChange = { tarefasList[index] = item.copy(psFinal = it) },
                                                label = { Text("PS Final") },
                                                modifier = Modifier.weight(1f),
                                                singleLine = true
                                            )
                                        }

                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            OutlinedTextField(
                                                value = item.materialObs,
                                                onValueChange = { tarefasList[index] = item.copy(materialObs = it) },
                                                label = { Text("Material / Obs") },
                                                modifier = Modifier.weight(2f),
                                                singleLine = true
                                            )
                                            OutlinedTextField(
                                                value = item.veiculo,
                                                onValueChange = { tarefasList[index] = item.copy(veiculo = it) },
                                                label = { Text("Veículo") },
                                                modifier = Modifier.weight(1f),
                                                singleLine = true
                                            )
                                        }

                                        val activeTask = remember(item.tarefa, activitiesList) {
                                            val codeInt = item.tarefa.trim().toIntOrNull()
                                            if (codeInt != null) {
                                                activitiesList.find { it.codigo == codeInt }
                                            } else null
                                        }
                                        if (activeTask != null) {
                                            Surface(
                                                color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f),
                                                shape = RoundedCornerShape(8.dp),
                                                modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
                                            ) {
                                                Column(modifier = Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                    Text(
                                                        text = "${activeTask.codigo} - ${activeTask.descricao}",
                                                        style = MaterialTheme.typography.bodySmall,
                                                        fontWeight = FontWeight.Bold,
                                                        color = MaterialTheme.colorScheme.onPrimaryContainer
                                                    )
                                                    Row(
                                                        modifier = Modifier.fillMaxWidth(),
                                                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                                                    ) {
                                                        Text(
                                                            text = "US Montagem: ${activeTask.us_montagem}",
                                                            style = MaterialTheme.typography.labelSmall,
                                                            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                                                        )
                                                        Text(
                                                            text = "US Desmontagem: ${activeTask.us_desmontagem}",
                                                            style = MaterialTheme.typography.labelSmall,
                                                            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                                                        )
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Botão Gravar BDO EP no Rodapé (Fixo)
        Surface(
            tonalElevation = 4.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
            ) {
                Button(
                    onClick = {
                        isSubmitting = true
                        val payload = mapOf(
                            "equipe" to equipe,
                            "ordem_mae" to ordemMae,
                            "pop" to pop,
                            "origem_copel" to origemCopel,
                            "equipamento_tipo" to equipamentoTipo,
                            "equipamento_codigo" to equipamentoCodigo.uppercase(),
                            "cidade" to cidade,
                            "descricao" to descricao,
                            "km_inicio" to kmInicio,
                            "km_fim" to kmFim,
                            "hora_saida" to horaSaida,
                            "hora_inicio" to horaInicio,
                            "hora_fim" to horaFim,
                            "hora_retorno" to horaRetorno,
                            "gedis_instalado" to mapOf(
                                "serie" to gedisInstaladoSerie,
                                "impedancia" to gedisInstaladoImpedancia,
                                "marca" to gedisInstaladoMarca,
                                "fabricacao" to gedisInstaladoFabricacao,
                                "potencia" to gedisInstaladoPotencia
                            ),
                            "gedis_retirado" to mapOf(
                                "serie" to gedisRetiradoSerie,
                                "impedancia" to gedisRetiradoImpedancia,
                                "marca" to gedisRetiradoMarca,
                                "fabricacao" to gedisRetiradoFabricacao,
                                "potencia" to gedisRetiradoPotencia
                            ),
                            "tarefas" to tarefasList.map {
                                mapOf(
                                    "tarefa" to it.tarefa,
                                    "quantidade" to it.quantidade,
                                    "sinal" to it.sinal,
                                    "ps_inicial" to it.psInicial,
                                    "ps_final" to it.psFinal,
                                    "material_obs" to it.materialObs,
                                    "veiculo" to it.veiculo
                                )
                            },
                            "timestamp" to System.currentTimeMillis()
                        )

                        db.collection("webtools").document("producao")
                            .collection("bdo_ep_lancamentos")
                            .add(payload)
                            .addOnSuccessListener {
                                isSubmitting = false
                                Toast.makeText(context, "BDO EP/LV enviado com sucesso!", Toast.LENGTH_SHORT).show()
                                ordemMae = ""
                                pop = ""
                                origemCopel = ""
                                cidade = ""
                                descricao = ""
                                kmInicio = ""
                                kmFim = ""
                                horaSaida = ""
                                horaInicio = ""
                                horaFim = ""
                                horaRetorno = ""
                                gedisInstaladoSerie = ""
                                gedisInstaladoImpedancia = ""
                                gedisInstaladoMarca = ""
                                gedisInstaladoFabricacao = ""
                                gedisInstaladoPotencia = ""
                                gedisRetiradoSerie = ""
                                gedisRetiradoImpedancia = ""
                                gedisRetiradoMarca = ""
                                gedisRetiradoFabricacao = ""
                                gedisRetiradoPotencia = ""
                                tarefasList.clear()
                                tarefasList.add(EpBdoTarefaItem())
                            }
                            .addOnFailureListener { e ->
                                isSubmitting = false
                                Toast.makeText(context, "Erro ao enviar: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                    },
                    enabled = podeEnviar && !isSubmitting,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(color = MaterialTheme.colorScheme.onPrimary, modifier = Modifier.size(24.dp))
                    } else {
                        Icon(Icons.Default.Send, contentDescription = "Enviar")
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Gravar BDO EP/LV")
                    }
                }
            }
        }
    }

    if (showLegacyWarningDialog) {
        AlertDialog(
            onDismissRequest = { showLegacyWarningDialog = false },
            title = { Text("Tarefa Substituída / Alterada") },
            text = { Text(activeLegacyMessage) },
            confirmButton = {
                Button(
                    onClick = {
                        if (activeLegacyTaskIndex in tarefasList.indices) {
                            val currentItem = tarefasList[activeLegacyTaskIndex]
                            tarefasList[activeLegacyTaskIndex] = currentItem.copy(tarefa = activeLegacyNewCode)
                        }
                        showLegacyWarningDialog = false
                    }
                ) {
                    Text("Atualizar para $activeLegacyNewCode")
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showLegacyWarningDialog = false }
                ) {
                    Text("Manter $activeLegacyOldCode")
                }
            }
        )
    }
}

@Composable
private fun TimeInputWithCapture(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = { Text(label) },
            singleLine = true,
            modifier = Modifier.weight(1f)
        )
        IconButton(
            onClick = {
                val sdf = SimpleDateFormat("HH:mm", Locale.getDefault())
                onValueChange(sdf.format(Date()))
            }
        ) {
            Icon(
                imageVector = Icons.Default.Schedule,
                contentDescription = "Capturar Hora Atual"
            )
        }
    }
}

@Composable
private fun OdometerInputCompact(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val totalDigits = 6
    val focusRequester = remember { FocusRequester() }
    val typedDigits = value.filter { it.isDigit() }

    Column(modifier = modifier) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(4.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { focusRequester.requestFocus() },
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            for (i in 0 until totalDigits) {
                val digit = if (i < totalDigits - typedDigits.length) {
                    "0"
                } else {
                    typedDigits[i - (totalDigits - typedDigits.length)].toString()
                }

                val isFocused = (i == totalDigits - typedDigits.length)

                Box(
                    modifier = Modifier
                        .size(width = 24.dp, height = 36.dp)
                        .background(
                            color = Color.White,
                            shape = RoundedCornerShape(4.dp)
                        )
                        .border(
                            width = if (isFocused) 1.5.dp else 1.dp,
                            color = if (isFocused) MaterialTheme.colorScheme.primary else Color(0xFFCCCCCC),
                            shape = RoundedCornerShape(4.dp)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = digit,
                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }
        }

        Box(modifier = Modifier.size(1.dp)) {
            androidx.compose.foundation.text.BasicTextField(
                value = typedDigits,
                onValueChange = { input ->
                    if (input.all { it.isDigit() } && input.length <= totalDigits) {
                        onValueChange(input)
                    }
                },
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Number
                ),
                modifier = Modifier.focusRequester(focusRequester)
            )
        }
    }
}
