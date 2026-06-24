// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/ConstructionBdoSection.kt
// Função: Componente de BDO específico para equipes de Construção.
//         Suporta Lançamento por Poste (seleção de projeto, estrutura e tarefas)
//         e Lançamento por Lote (busca por MIT com sugestões, quantidade e montagem/desmontagem).
// Tecnologias: Jetpack Compose, Material 3, Retrofit (ConstrucaoRetrofitClient).
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import com.chicoeletro.dds.features.construcao.*
import com.chicoeletro.dds.components.HeaderBarState
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun ConstructionBdoSection(
    equipe: String,
    online: Boolean,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val repository = remember { ConstrucaoFirestoreRepository() }
    val sharedPrefs = remember { context.getSharedPreferences("construcao_prefs", android.content.Context.MODE_PRIVATE) }

    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Por Poste (Completo)", "Por Lote (Rápido)", "Simplificado")

    var projetos by remember { mutableStateOf(listOf<Projeto>()) }
    var projetoSelecionado by remember { mutableStateOf<Projeto?>(null) }
    var todasTarefasProjeto by remember { mutableStateOf(listOf<Tarefa>()) }
    var lancamentosProjeto by remember { mutableStateOf<Map<Pair<Int, String>, Double>>(emptyMap()) }
    var isLoadingProjetos by remember { mutableStateOf(false) }

    // Carregar lista de Projetos na inicialização
    LaunchedEffect(Unit) {
        isLoadingProjetos = true
        try {
            projetos = repository.getProjetos()
            val savedProjId = sharedPrefs.getString("ultimo_projeto_id", null)
            if (!savedProjId.isNullOrBlank()) {
                projetos.find { it.id == savedProjId }?.let {
                    projetoSelecionado = it
                    HeaderBarState.titlePart = "BDO - Proj: ${it.id}"
                }
            }
        } catch (e: Exception) {
            Toast.makeText(context, "Erro ao carregar projetos: ${e.message}", Toast.LENGTH_SHORT).show()
        } finally {
            isLoadingProjetos = false
        }
    }

    // Carregar tarefas e lançamentos do projeto todo sempre que o projeto selecionado mudar
    LaunchedEffect(projetoSelecionado) {
        projetoSelecionado?.let { proj ->
            sharedPrefs.edit().putString("ultimo_projeto_id", proj.id).apply()
            HeaderBarState.titlePart = "BDO - Proj: ${proj.id}"
            try {
                todasTarefasProjeto = repository.getTodasTarefasProjeto(proj.id)
                lancamentosProjeto = repository.getQuantidadesLancadasProjeto(proj.id)
            } catch (e: Exception) {
                todasTarefasProjeto = emptyList()
                lancamentosProjeto = emptyMap()
                Toast.makeText(context, "Erro ao carregar dados do projeto: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        } ?: run {
            HeaderBarState.titlePart = ""
            todasTarefasProjeto = emptyList()
            lancamentosProjeto = emptyMap()
        }
    }

    val refreshLancamentosProjeto: suspend () -> Unit = {
        projetoSelecionado?.let { proj ->
            try {
                lancamentosProjeto = repository.getQuantidadesLancadasProjeto(proj.id)
            } catch (e: Exception) {
                // ignore
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(top = 4.dp)
    ) {
        if (projetoSelecionado == null) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(
                    text = "Selecione o Projeto de Trabalho",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                if (isLoadingProjetos) {
                    Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                } else if (projetos.isEmpty()) {
                    Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.Center) {
                        Text("Nenhum projeto cadastrado.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(projetos) { p ->
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { projetoSelecionado = p },
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(16.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = p.id,
                                            fontWeight = FontWeight.Bold,
                                            style = MaterialTheme.typography.titleMedium,
                                            color = MaterialTheme.colorScheme.primary
                                        )
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            text = p.titulo,
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = MaterialTheme.colorScheme.onSurface
                                        )
                                    }
                                    Icon(
                                        imageVector = Icons.AutoMirrored.Filled.ArrowForward,
                                        contentDescription = "Selecionar",
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                }
                            }
                        }
                    }
                }
            }
        } else {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = {
                        projetoSelecionado = null
                        sharedPrefs.edit().remove("ultimo_projeto_id").apply()
                    }
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Trocar Projeto",
                        tint = MaterialTheme.colorScheme.primary
                    )
                }
                TabRow(
                    selectedTabIndex = selectedTab,
                    containerColor = Color.Transparent,
                    contentColor = MaterialTheme.colorScheme.primary,
                    modifier = Modifier
                        .weight(1f)
                        .padding(bottom = 12.dp)
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
            }

            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
            ) {
                when (selectedTab) {
                    0 -> ModoPosteView(
                        equipe = equipe,
                        online = online,
                        projetoSelecionado = projetoSelecionado,
                        todasTarefasProjeto = todasTarefasProjeto,
                        lancamentosProjeto = lancamentosProjeto,
                        onRefreshLancamentosProjeto = refreshLancamentosProjeto
                    )
                    1 -> ModoLoteView(
                        equipe = equipe,
                        online = online,
                        projetoSelecionado = projetoSelecionado,
                        todasTarefasProjeto = todasTarefasProjeto,
                        lancamentosProjeto = lancamentosProjeto,
                        onRefreshLancamentosProjeto = refreshLancamentosProjeto
                    )
                    2 -> ModoSimplificadoView(
                        equipe = equipe,
                        projetoSelecionado = projetoSelecionado
                    )
                }
            }
        }
    }
}@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ModoPosteView(
    equipe: String,
    online: Boolean,
    projetoSelecionado: Projeto?,
    todasTarefasProjeto: List<Tarefa>,
    lancamentosProjeto: Map<Pair<Int, String>, Double>,
    onRefreshLancamentosProjeto: suspend () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val repository = remember { ConstrucaoFirestoreRepository() }
    val sharedPrefs = remember { context.getSharedPreferences("construcao_prefs", android.content.Context.MODE_PRIVATE) }

    var estruturas by remember { mutableStateOf(listOf<Estrutura>()) }
    var estruturaSelecionada by remember { mutableStateOf<Estrutura?>(null) }
    var estExpanded by remember { mutableStateOf(false) }
    var tipoSelecao by remember { mutableStateOf("POSTE") }

    val filteredEstruturas = remember(estruturas, tipoSelecao) {
        if (tipoSelecao == "POSTE") {
            estruturas.filter { !it.identificador.contains("Trecho", ignoreCase = true) }
        } else {
            estruturas.filter { it.identificador.contains("Trecho", ignoreCase = true) }
        }
    }

    var tarefas by remember { mutableStateOf(listOf<Tarefa>()) }
    val tarefasSelecionadas = remember { mutableStateListOf<Int>() }
    val quantidadesSelecionadas = remember { mutableStateMapOf<Int, Double>() }
    var lancamentosRealizados by remember { mutableStateOf<Map<Pair<Int, String>, Double>>(emptyMap()) }

    var isLoading by remember { mutableStateOf(false) }
    var isSubmitting by remember { mutableStateOf(false) }

    val equipeNumero = remember(equipe) {
        equipe.filter { it.isDigit() }.toIntOrNull() ?: 1
    }
    val dataExecucao = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    // Carregar Estruturas quando o projeto for alterado
    LaunchedEffect(projetoSelecionado) {
        projetoSelecionado?.let { proj ->
            try {
                estruturas = repository.getEstruturas(proj.id)
                estruturaSelecionada = null
                tarefas = emptyList()
                tarefasSelecionadas.clear()
                quantidadesSelecionadas.clear()
                lancamentosRealizados = emptyMap()
            } catch (e: Exception) {
                estruturas = emptyList()
                Toast.makeText(context, "Erro ao carregar estruturas: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        } ?: run {
            estruturas = emptyList()
            estruturaSelecionada = null
            tarefas = emptyList()
            tarefasSelecionadas.clear()
            quantidadesSelecionadas.clear()
            lancamentosRealizados = emptyMap()
        }
    }

    // Carregar Tarefas e Lançamentos anteriores quando a estrutura for alterada
    LaunchedEffect(estruturaSelecionada) {
        estruturaSelecionada?.let { est ->
            try {
                tarefas = repository.getTarefas(est.id)
                tarefasSelecionadas.clear()
                quantidadesSelecionadas.clear()

                projetoSelecionado?.let { proj ->
                    val realizadosMap = repository.getQuantidadesLancadas(proj.id, est.id)
                    lancamentosRealizados = realizadosMap
                }
            } catch (e: Exception) {
                tarefas = emptyList()
                lancamentosRealizados = emptyMap()
                Toast.makeText(context, "Erro ao carregar tarefas: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            // Dropdown de Estrutura em largura total
            Column(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Estrutura",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(2.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.clickable {
                                if (tipoSelecao != "POSTE") {
                                    tipoSelecao = "POSTE"
                                    estruturaSelecionada = null
                                }
                            }
                        ) {
                            RadioButton(
                                selected = tipoSelecao == "POSTE",
                                onClick = {
                                    tipoSelecao = "POSTE"
                                    estruturaSelecionada = null
                                },
                                modifier = Modifier.size(20.dp)
                            )
                            Text("PS", style = MaterialTheme.typography.bodySmall, fontSize = 11.sp)
                        }
                        Spacer(modifier = Modifier.width(4.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.clickable {
                                if (tipoSelecao != "TRECHO") {
                                    tipoSelecao = "TRECHO"
                                    estruturaSelecionada = null
                                }
                            }
                        ) {
                            RadioButton(
                                selected = tipoSelecao == "TRECHO",
                                onClick = {
                                    tipoSelecao = "TRECHO"
                                    estruturaSelecionada = null
                                },
                                modifier = Modifier.size(20.dp)
                            )
                            Text("Trecho", style = MaterialTheme.typography.bodySmall, fontSize = 11.sp)
                        }
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                Box(modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(
                        onClick = { estExpanded = true },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = projetoSelecionado != null,
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 10.dp)
                    ) {
                        Row(
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(
                                text = estruturaSelecionada?.identificador ?: "Selecionar...",
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                color = if (estruturaSelecionada != null) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                        }
                    }
                    DropdownMenu(
                        expanded = estExpanded,
                        onDismissRequest = { estExpanded = false },
                        modifier = Modifier.fillMaxWidth(0.9f)
                    ) {
                        if (filteredEstruturas.isEmpty()) {
                            DropdownMenuItem(
                                text = { Text("Nenhum item disponível") },
                                onClick = {}
                            )
                        } else {
                            filteredEstruturas.forEach { e ->
                                DropdownMenuItem(
                                    text = { Text(e.identificador) },
                                    onClick = {
                                        estruturaSelecionada = e
                                        estExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Checklist de Tarefas
            val sortedTarefas = remember(tarefas, lancamentosRealizados) {
                tarefas.sortedBy { t ->
                    val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                    val realizado = lancamentosRealizados[Pair(t.atividade_codigo, tipo)] ?: 0.0
                    val isCompleted = realizado >= t.quantidade
                    if (isCompleted) 1 else 0
                }
            }

            val groupedTarefasProjeto = remember(todasTarefasProjeto, lancamentosProjeto) {
                todasTarefasProjeto.groupBy { Pair(it.atividade_codigo, it.sinal) }
                    .map { (key, list) ->
                        val code = key.first
                        val sinal = key.second
                        val totalQty = list.sumOf { it.quantidade }
                        val desc = list.firstOrNull()?.descricao ?: "Atividade $code"
                        val usMontagem = list.firstOrNull()?.us_montagem ?: 0.0
                        val usDesmontagem = list.firstOrNull()?.us_desmontagem ?: 0.0
                        
                        Tarefa(
                            id = -code,
                            estrutura_id = -1,
                            atividade_codigo = code,
                            quantidade = totalQty,
                            sinal = sinal,
                            descricao = desc,
                            us_montagem = usMontagem,
                            us_desmontagem = usDesmontagem
                        )
                    }
                    .sortedBy { t ->
                        val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                        val realizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                        val isCompleted = realizado >= t.quantidade
                        if (isCompleted) 1 else 0
                    }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Marque os itens executados:",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                
                if (projetoSelecionado != null && estruturaSelecionada != null && sortedTarefas.isNotEmpty()) {
                    val incompletes = sortedTarefas.filter { t ->
                        val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                        
                        val tProjTotalQty = todasTarefasProjeto.filter { it.atividade_codigo == t.atividade_codigo && it.sinal == t.sinal }.sumOf { it.quantidade }
                        val tProjTotalRealizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                        val tIsProjectCompleted = tProjTotalRealizado >= tProjTotalQty && tProjTotalQty > 0.0

                        val realizado = lancamentosRealizados[Pair(t.atividade_codigo, tipo)] ?: 0.0
                        val tIsCompleted = tIsProjectCompleted || realizado >= t.quantidade
                        !tIsCompleted
                    }
                    val allSelected = incompletes.isNotEmpty() && incompletes.all { tarefasSelecionadas.contains(it.id) }
                    
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.clickable {
                            if (allSelected) {
                                incompletes.forEach { t ->
                                    tarefasSelecionadas.remove(t.id)
                                    quantidadesSelecionadas.remove(t.id)
                                }
                            } else {
                                incompletes.forEach { t ->
                                    val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                                    val realizado = lancamentosRealizados[Pair(t.atividade_codigo, tipo)] ?: 0.0
                                    val falta = maxOf(0.0, t.quantidade - realizado)
                                    if (!tarefasSelecionadas.contains(t.id)) {
                                        tarefasSelecionadas.add(t.id)
                                    }
                                    quantidadesSelecionadas[t.id] = falta
                                }
                            }
                        }
                    ) {
                        Checkbox(
                            checked = allSelected,
                            onCheckedChange = { checked ->
                                if (checked == true) {
                                    incompletes.forEach { t ->
                                        val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                                        val realizado = lancamentosRealizados[Pair(t.atividade_codigo, tipo)] ?: 0.0
                                        val falta = maxOf(0.0, t.quantidade - realizado)
                                        if (!tarefasSelecionadas.contains(t.id)) {
                                            tarefasSelecionadas.add(t.id)
                                        }
                                        quantidadesSelecionadas[t.id] = falta
                                    }
                                } else {
                                    incompletes.forEach { t ->
                                        tarefasSelecionadas.remove(t.id)
                                        quantidadesSelecionadas.remove(t.id)
                                    }
                                }
                            },
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "Marcar todos",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.2f), RoundedCornerShape(8.dp)),
                contentPadding = PaddingValues(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (projetoSelecionado == null) {
                    item {
                        Text(
                            text = "Por favor, selecione um projeto para começar.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 32.dp)
                        )
                    }
                } else if (estruturaSelecionada == null) {
                    if (groupedTarefasProjeto.isEmpty()) {
                        item {
                            Text(
                                text = "Nenhuma tarefa cadastrada neste projeto.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 14.sp,
                                textAlign = TextAlign.Center,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 32.dp)
                            )
                        }
                    } else {
                        items(groupedTarefasProjeto) { t ->
                            val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                            val realizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                            val falta = maxOf(0.0, t.quantidade - realizado)
                            val isCompleted = realizado >= t.quantidade

                            Card(
                                colors = CardDefaults.cardColors(
                                    containerColor = if (isCompleted) {
                                        Color.LightGray.copy(alpha = 0.2f)
                                    } else {
                                        MaterialTheme.colorScheme.surface
                                    }
                                ),
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 12.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        val cleanDesc = t.descricao.removePrefix("Atividade ${t.atividade_codigo}").removePrefix("Atividade").trim().removePrefix("-").trim().ifEmpty { "Serviço ${t.atividade_codigo}" }
                                        Text(
                                            text = "${t.atividade_codigo} - $cleanDesc",
                                            style = MaterialTheme.typography.bodyMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Spacer(modifier = Modifier.height(4.dp))
                                        val tipoLabel = if (t.sinal == "+") "Montagem" else "Desmontagem"
                                        val tipoColor = if (t.sinal == "+") Color(0xFF2E7D32) else Color(0xFFC62828)
                                        
                                        Row(
                                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            modifier = Modifier.fillMaxWidth()
                                        ) {
                                            Text(
                                                text = "$tipoLabel: ${if (t.quantidade % 1.0 == 0.0) t.quantidade.toInt().toString() else t.quantidade.toString()}",
                                                fontWeight = FontWeight.Bold,
                                                color = tipoColor,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            
                                            Text(
                                                text = "•",
                                                color = Color.LightGray,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            Text(
                                                text = "Total Lançado: ${if (realizado % 1.0 == 0.0) realizado.toInt().toString() else realizado.toString()}",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = if (realizado > 0.0) Color(0xFF1976D2) else MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            
                                            Text(
                                                text = "•",
                                                color = Color.LightGray,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            Text(
                                                text = "Saldo: ${if (falta % 1.0 == 0.0) falta.toInt().toString() else falta.toString()}",
                                                fontWeight = FontWeight.Bold,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = if (falta > 0.0) Color(0xFFD32F2F) else Color(0xFF388E3C)
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else if (tarefas.isEmpty()) {
                    item {
                        Text(
                            text = "Nenhuma tarefa vinculada a esta estrutura.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 32.dp)
                        )
                    }
                } else {
                    items(sortedTarefas) { t ->
                        val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                        
                        // Check if project-wide total is reached
                        val projTotalQty = todasTarefasProjeto.filter { it.atividade_codigo == t.atividade_codigo && it.sinal == t.sinal }.sumOf { it.quantidade }
                        val projTotalRealizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                        val isProjectCompleted = projTotalRealizado >= projTotalQty && projTotalQty > 0.0

                        val realizado = lancamentosRealizados[Pair(t.atividade_codigo, tipo)] ?: 0.0
                        val falta = if (isProjectCompleted) 0.0 else maxOf(0.0, t.quantidade - realizado)
                        val isCompleted = isProjectCompleted || realizado >= t.quantidade
                        val isChecked = tarefasSelecionadas.contains(t.id)
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = if (isCompleted) {
                                    Color.LightGray.copy(alpha = 0.2f)
                                } else if (isChecked) {
                                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
                                } else {
                                    MaterialTheme.colorScheme.surface
                                }
                            ),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .combinedClickable(
                                    enabled = !isCompleted,
                                    onClick = {
                                        if (isChecked) {
                                            tarefasSelecionadas.remove(t.id)
                                            quantidadesSelecionadas.remove(t.id)
                                        } else {
                                            tarefasSelecionadas.add(t.id)
                                            quantidadesSelecionadas[t.id] = falta
                                        }
                                    },
                                    onDoubleClick = {
                                        tarefas.forEach { task ->
                                            val tTipo = if (task.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                                            
                                            val tProjTotalQty = todasTarefasProjeto.filter { it.atividade_codigo == task.atividade_codigo && it.sinal == task.sinal }.sumOf { it.quantidade }
                                            val tProjTotalRealizado = lancamentosProjeto[Pair(task.atividade_codigo, tTipo)] ?: 0.0
                                            val tIsProjectCompleted = tProjTotalRealizado >= tProjTotalQty && tProjTotalQty > 0.0

                                            val tRealizado = lancamentosRealizados[Pair(task.atividade_codigo, tTipo)] ?: 0.0
                                            val tFalta = if (tIsProjectCompleted) 0.0 else maxOf(0.0, task.quantidade - tRealizado)
                                            val tIsCompleted = tIsProjectCompleted || tRealizado >= task.quantidade
                                            
                                            if (!tIsCompleted) {
                                                if (!tarefasSelecionadas.contains(task.id)) {
                                                    tarefasSelecionadas.add(task.id)
                                                }
                                                quantidadesSelecionadas[task.id] = tFalta
                                            }
                                        }
                                    }
                                  )
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 8.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Checkbox(
                                    checked = isChecked || isCompleted,
                                    enabled = !isCompleted,
                                    onCheckedChange = { checked ->
                                        if (!isCompleted) {
                                            if (checked == true) {
                                                tarefasSelecionadas.add(t.id)
                                                quantidadesSelecionadas[t.id] = falta
                                            } else {
                                                tarefasSelecionadas.remove(t.id)
                                                quantidadesSelecionadas.remove(t.id)
                                            }
                                        }
                                    }
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    val cleanDesc = t.descricao.removePrefix("Atividade ${t.atividade_codigo}").removePrefix("Atividade").trim().removePrefix("-").trim().ifEmpty { "Serviço ${t.atividade_codigo}" }
                                    Text(
                                        text = "${t.atividade_codigo} - $cleanDesc",
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Spacer(modifier = Modifier.height(4.dp))
                                    val tipoColor = if (t.sinal == "+") Color(0xFF2E7D32) else Color(0xFFC62828)
                                    val tipoLabel = if (t.sinal == "+") "Montagem" else "Desmontagem"
                                    
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        val showEditor = isChecked && !isCompleted && falta > 1.0
                                        
                                        if (showEditor) {
                                            val currentQty = quantidadesSelecionadas[t.id] ?: falta
                                            Text(
                                                text = "$tipoLabel:",
                                                fontWeight = FontWeight.Bold,
                                                color = tipoColor,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                                            ) {
                                                Box(
                                                    contentAlignment = Alignment.Center,
                                                    modifier = Modifier
                                                        .size(20.dp)
                                                        .background(Color(0xFFFEEBEE), RoundedCornerShape(4.dp))
                                                        .clickable {
                                                            val newVal = maxOf(1.0, currentQty - 1.0)
                                                            quantidadesSelecionadas[t.id] = newVal
                                                        }
                                                ) {
                                                    Icon(
                                                        imageVector = Icons.Default.Remove,
                                                        contentDescription = "Subtrair",
                                                        tint = Color(0xFFC62828),
                                                        modifier = Modifier.size(12.dp)
                                                    )
                                                }
                                                
                                                androidx.compose.foundation.text.BasicTextField(
                                                    value = if (currentQty % 1.0 == 0.0) currentQty.toInt().toString() else currentQty.toString(),
                                                    onValueChange = { valText ->
                                                        val valDouble = valText.replace(",", ".").toDoubleOrNull() ?: 0.0
                                                        quantidadesSelecionadas[t.id] = minOf(falta, maxOf(0.0, valDouble))
                                                    },
                                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                                    singleLine = true,
                                                    textStyle = androidx.compose.ui.text.TextStyle(
                                                        fontSize = 12.sp,
                                                        textAlign = TextAlign.Center,
                                                        color = MaterialTheme.colorScheme.onSurface
                                                    ),
                                                    modifier = Modifier
                                                        .width(36.dp)
                                                        .height(20.dp)
                                                        .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
                                                        .background(Color.Transparent)
                                                )
                                                
                                                Box(
                                                    contentAlignment = Alignment.Center,
                                                    modifier = Modifier
                                                        .size(20.dp)
                                                        .background(Color(0xFFE8F5E9), RoundedCornerShape(4.dp))
                                                        .clickable {
                                                            val newVal = minOf(falta, currentQty + 1.0)
                                                            quantidadesSelecionadas[t.id] = newVal
                                                        }
                                                ) {
                                                    Icon(
                                                        imageVector = Icons.Default.Add,
                                                        contentDescription = "Somar",
                                                        tint = Color(0xFF2E7D32),
                                                        modifier = Modifier.size(12.dp)
                                                    )
                                                }
                                            }
                                            Text(
                                                text = "de ${if (t.quantidade % 1.0 == 0.0) t.quantidade.toInt().toString() else t.quantidade.toString()}",
                                                fontWeight = FontWeight.Bold,
                                                color = tipoColor,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                        } else {
                                            Text(
                                                text = "$tipoLabel ${if (t.quantidade % 1.0 == 0.0) t.quantidade.toInt().toString() else t.quantidade.toString()}",
                                                fontWeight = FontWeight.Bold,
                                                color = tipoColor,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                        }
                                        
                                        Text(
                                            text = "•",
                                            color = Color.LightGray,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            text = "Lançado: ${if (realizado % 1.0 == 0.0) realizado.toInt().toString() else realizado.toString()}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = if (realizado > 0.0) Color(0xFF1976D2) else MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                        
                                        if (!showEditor) {
                                            Text(
                                                text = "•",
                                                color = Color.LightGray,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            Text(
                                                text = "Saldo: ${if (falta % 1.0 == 0.0) falta.toInt().toString() else falta.toString()}",
                                                fontWeight = FontWeight.Bold,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = if (falta > 0.0) Color(0xFFD32F2F) else Color(0xFF388E3C)
                                            )
                                        }
                                        
                                        Text(
                                            text = "•",
                                            color = Color.LightGray,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            text = "US: ${if (t.sinal == "+") t.us_montagem else t.us_desmontagem}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Controles de Navegação e Confirmação
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val currentIndex = estruturaSelecionada?.let { filteredEstruturas.indexOf(it) } ?: -1
                val hasPrevious = currentIndex > 0
                val hasNext = currentIndex != -1 && currentIndex < filteredEstruturas.lastIndex

                // Botão Anterior
                OutlinedButton(
                    onClick = {
                        if (hasPrevious) {
                            estruturaSelecionada = filteredEstruturas[currentIndex - 1]
                        }
                    },
                    modifier = Modifier.fillMaxHeight(),
                    enabled = hasPrevious,
                    shape = RoundedCornerShape(8.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Anterior"
                    )
                }

                // Botão Confirmar Lançamento do Poste
                Button(
                    onClick = {
                        val proj = projetoSelecionado ?: return@Button
                        val est = estruturaSelecionada ?: return@Button
                        if (tarefasSelecionadas.isEmpty()) return@Button

                        isSubmitting = true
                        coroutineScope.launch {
                            try {
                                val response = repository.lancarPoste(
                                    LancamentoPosteRequest(
                                        equipe_numero = equipeNumero,
                                        data_execucao = dataExecucao,
                                        projeto_id = proj.id,
                                        estrutura_id = est.id,
                                        tarefas_completadas = tarefasSelecionadas.toList(),
                                        tarefas_quantidades = quantidadesSelecionadas.mapKeys { it.key.toString() }
                                    )
                                )
                                if (response.sucesso) {
                                    Toast.makeText(context, response.mensagem ?: "Poste lançado com sucesso!", Toast.LENGTH_LONG).show()
                                    // Reseta seleções de tarefas e avança estrutura para facilitar fluxo
                                    tarefasSelecionadas.clear()
                                    quantidadesSelecionadas.clear()
                                    val nextIndex = filteredEstruturas.indexOf(est)
                                    if (nextIndex != -1 && nextIndex < filteredEstruturas.lastIndex) {
                                        estruturaSelecionada = filteredEstruturas[nextIndex + 1]
                                    } else {
                                        // Se for a última estrutura, atualiza localmente para refletir os novos totais de lançamentos
                                        lancamentosRealizados = repository.getQuantidadesLancadas(proj.id, est.id)
                                    }
                                } else {
                                    Toast.makeText(context, response.detail ?: "Erro ao lançar: ${response.mensagem}", Toast.LENGTH_LONG).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Erro na conexão: ${e.message}", Toast.LENGTH_LONG).show()
                            } finally {
                                isSubmitting = false
                            }
                        }
                    },
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxHeight(),
                    enabled = !isSubmitting && projetoSelecionado != null && estruturaSelecionada != null && tarefasSelecionadas.isNotEmpty(),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text("Confirmar Lançamento do Poste")
                    }
                }

                // Botão Próximo
                OutlinedButton(
                    onClick = {
                        if (hasNext) {
                            estruturaSelecionada = filteredEstruturas[currentIndex + 1]
                        }
                    },
                    modifier = Modifier.fillMaxHeight(),
                    enabled = hasNext,
                    shape = RoundedCornerShape(8.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowForward,
                        contentDescription = "Próximo"
                    )
                }
            }
        }
    }
}

@Composable
fun ModoLoteView(
    equipe: String,
    online: Boolean,
    projetoSelecionado: Projeto?,
    todasTarefasProjeto: List<Tarefa>,
    lancamentosProjeto: Map<Pair<Int, String>, Double>,
    onRefreshLancamentosProjeto: suspend () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val repository = remember { ConstrucaoFirestoreRepository() }

    val groupedTarefasProjeto = remember(todasTarefasProjeto, lancamentosProjeto) {
        todasTarefasProjeto.groupBy { Pair(it.atividade_codigo, it.sinal) }
            .map { (key, list) ->
                val code = key.first
                val sinal = key.second
                val totalQty = list.sumOf { it.quantidade }
                val desc = list.firstOrNull()?.descricao ?: "Atividade $code"
                val usMontagem = list.firstOrNull()?.us_montagem ?: 0.0
                val usDesmontagem = list.firstOrNull()?.us_desmontagem ?: 0.0
                
                Tarefa(
                    id = Pair(code, sinal).hashCode(),
                    estrutura_id = -1,
                    atividade_codigo = code,
                    quantidade = totalQty,
                    sinal = sinal,
                    descricao = desc,
                    us_montagem = usMontagem,
                    us_desmontagem = usDesmontagem
                )
            }
            .sortedBy { t ->
                val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                val realizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                val isCompleted = realizado >= t.quantidade
                if (isCompleted) 1 else 0
            }
    }

    val tarefasSelecionadas = remember { mutableStateListOf<Int>() }
    val quantidadesSelecionadas = remember { mutableStateMapOf<Int, Double>() }
    var queryBusca by remember { mutableStateOf("") }

    val filteredGroupedTarefas = remember(groupedTarefasProjeto, queryBusca) {
        if (queryBusca.isBlank()) {
            groupedTarefasProjeto
        } else {
            val cleanQuery = queryBusca.trim().lowercase()
            groupedTarefasProjeto.filter { t ->
                t.atividade_codigo.toString().contains(cleanQuery) || t.descricao.lowercase().contains(cleanQuery)
            }
        }
    }

    var isSubmitting by remember { mutableStateOf(false) }

    val equipeNumero = remember(equipe) {
        equipe.filter { it.isDigit() }.toIntOrNull() ?: 1
    }
    val dataExecucao = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Campo de Pesquisa para filtrar a lista do lote
        OutlinedTextField(
            value = queryBusca,
            onValueChange = { queryBusca = it },
            placeholder = { Text("Pesquisar código ou descrição (Ex: 750 ou Cava)") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            trailingIcon = {
                if (queryBusca.isNotEmpty()) {
                    IconButton(onClick = { queryBusca = "" }) {
                        Icon(Icons.Default.Close, contentDescription = "Limpar")
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            singleLine = true
        )

        Spacer(modifier = Modifier.height(12.dp))

        Text(
            text = "Marque os itens do lote executados:",
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(6.dp))

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.2f), RoundedCornerShape(8.dp)),
            contentPadding = PaddingValues(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (projetoSelecionado == null) {
                item {
                    Text(
                        text = "Por favor, selecione um projeto para começar.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp)
                    )
                }
            } else if (filteredGroupedTarefas.isEmpty()) {
                item {
                    Text(
                        text = if (queryBusca.isEmpty()) "Nenhuma tarefa cadastrada neste projeto." else "Nenhuma tarefa corresponde à pesquisa.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp)
                    )
                }
            } else {
                items(filteredGroupedTarefas) { t ->
                    val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                    val realizado = lancamentosProjeto[Pair(t.atividade_codigo, tipo)] ?: 0.0
                    val falta = maxOf(0.0, t.quantidade - realizado)
                    val isCompleted = realizado >= t.quantidade
                    val isChecked = tarefasSelecionadas.contains(t.id)
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (isCompleted) {
                                Color.LightGray.copy(alpha = 0.2f)
                            } else if (isChecked) {
                                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
                            } else {
                                MaterialTheme.colorScheme.surface
                            }
                        ),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .combinedClickable(
                                enabled = !isCompleted,
                                onClick = {
                                    if (isChecked) {
                                        tarefasSelecionadas.remove(t.id)
                                        quantidadesSelecionadas.remove(t.id)
                                    } else {
                                        tarefasSelecionadas.add(t.id)
                                        quantidadesSelecionadas[t.id] = minOf(falta, 1.0)
                                    }
                                },
                                onDoubleClick = {
                                    filteredGroupedTarefas.forEach { task ->
                                        val tTipo = if (task.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                                        val tRealizado = lancamentosProjeto[Pair(task.atividade_codigo, tTipo)] ?: 0.0
                                        val tFalta = maxOf(0.0, task.quantidade - tRealizado)
                                        if (tRealizado < task.quantidade) {
                                            if (!tarefasSelecionadas.contains(task.id)) {
                                                tarefasSelecionadas.add(task.id)
                                            }
                                            quantidadesSelecionadas[task.id] = minOf(tFalta, 1.0)
                                        }
                                    }
                                }
                            )
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 8.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = isChecked || isCompleted,
                                enabled = !isCompleted,
                                onCheckedChange = { checked ->
                                    if (!isCompleted) {
                                        if (checked == true) {
                                            tarefasSelecionadas.add(t.id)
                                            quantidadesSelecionadas[t.id] = minOf(falta, 1.0)
                                        } else {
                                            tarefasSelecionadas.remove(t.id)
                                            quantidadesSelecionadas.remove(t.id)
                                        }
                                    }
                                }
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                val cleanDesc = t.descricao.removePrefix("Atividade ${t.atividade_codigo}").removePrefix("Atividade").trim().removePrefix("-").trim().ifEmpty { "Serviço ${t.atividade_codigo}" }
                                Text(
                                    text = "${t.atividade_codigo} - $cleanDesc",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                val tipoColor = if (t.sinal == "+") Color(0xFF2E7D32) else Color(0xFFC62828)
                                val tipoLabel = if (t.sinal == "+") "Montagem" else "Desmontagem"
                                
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    val showEditor = isChecked && !isCompleted && falta > 1.0
                                    
                                    if (showEditor) {
                                        val currentQty = quantidadesSelecionadas[t.id] ?: falta
                                        Text(
                                            text = "$tipoLabel:",
                                            fontWeight = FontWeight.Bold,
                                            color = tipoColor,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Row(
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                                        ) {
                                            Box(
                                                contentAlignment = Alignment.Center,
                                                modifier = Modifier
                                                    .size(20.dp)
                                                    .background(Color(0xFFFEEBEE), RoundedCornerShape(4.dp))
                                                    .clickable {
                                                        val newVal = maxOf(1.0, currentQty - 1.0)
                                                        quantidadesSelecionadas[t.id] = newVal
                                                    }
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Default.Remove,
                                                    contentDescription = "Subtrair",
                                                    tint = Color(0xFFC62828),
                                                    modifier = Modifier.size(12.dp)
                                                )
                                            }
                                            
                                            androidx.compose.foundation.text.BasicTextField(
                                                value = if (currentQty % 1.0 == 0.0) currentQty.toInt().toString() else currentQty.toString(),
                                                onValueChange = { valText ->
                                                    val valDouble = valText.replace(",", ".").toDoubleOrNull() ?: 0.0
                                                    quantidadesSelecionadas[t.id] = minOf(falta, maxOf(0.0, valDouble))
                                                },
                                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                                singleLine = true,
                                                textStyle = androidx.compose.ui.text.TextStyle(
                                                    fontSize = 12.sp,
                                                    textAlign = TextAlign.Center,
                                                    color = MaterialTheme.colorScheme.onSurface
                                                ),
                                                modifier = Modifier
                                                    .width(36.dp)
                                                    .height(20.dp)
                                                    .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
                                                    .background(Color.Transparent)
                                            )
                                            
                                            Box(
                                                contentAlignment = Alignment.Center,
                                                modifier = Modifier
                                                    .size(20.dp)
                                                    .background(Color(0xFFE8F5E9), RoundedCornerShape(4.dp))
                                                    .clickable {
                                                        val newVal = minOf(falta, currentQty + 1.0)
                                                        quantidadesSelecionadas[t.id] = newVal
                                                    }
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Default.Add,
                                                    contentDescription = "Somar",
                                                    tint = Color(0xFF2E7D32),
                                                    modifier = Modifier.size(12.dp)
                                                )
                                            }
                                        }
                                        Text(
                                            text = "de ${if (t.quantidade % 1.0 == 0.0) t.quantidade.toInt().toString() else t.quantidade.toString()}",
                                            fontWeight = FontWeight.Bold,
                                            color = tipoColor,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    } else {
                                        Text(
                                            text = "$tipoLabel ${if (t.quantidade % 1.0 == 0.0) t.quantidade.toInt().toString() else t.quantidade.toString()}",
                                            fontWeight = FontWeight.Bold,
                                            color = tipoColor,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                    
                                    Text(
                                        text = "•",
                                        color = Color.LightGray,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                    Text(
                                        text = "Lançado: ${if (realizado % 1.0 == 0.0) realizado.toInt().toString() else realizado.toString()}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = if (realizado > 0.0) Color(0xFF1976D2) else MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    
                                    if (!showEditor) {
                                        Text(
                                            text = "•",
                                            color = Color.LightGray,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            text = "Saldo: ${if (falta % 1.0 == 0.0) falta.toInt().toString() else falta.toString()}",
                                            fontWeight = FontWeight.Bold,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = if (falta > 0.0) Color(0xFFD32F2F) else Color(0xFF388E3C)
                                        )
                                    }
                                    
                                    Text(
                                        text = "•",
                                        color = Color.LightGray,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                    Text(
                                        text = "US: ${if (t.sinal == "+") t.us_montagem else t.us_desmontagem}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Botão Enviar Lote Diário
        Button(
            onClick = {
                if (tarefasSelecionadas.isEmpty()) return@Button

                isSubmitting = true
                coroutineScope.launch {
                    try {
                        val response = repository.lancarLote(
                            LancamentoLoteRequest(
                                equipe_numero = equipeNumero,
                                data_execucao = dataExecucao,
                                projeto_id = projetoSelecionado?.id,
                                itens = tarefasSelecionadas.map { id ->
                                    val t = groupedTarefasProjeto.find { it.id == id }!!
                                    val qty = quantidadesSelecionadas[id] ?: t.quantidade
                                    ItemLoteRequest(
                                        codigo = t.atividade_codigo,
                                        quantidade = qty,
                                        tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                                    )
                                }
                            )
                        )
                        if (response.sucesso) {
                            Toast.makeText(context, response.mensagem ?: "Lote enviado com sucesso!", Toast.LENGTH_LONG).show()
                            tarefasSelecionadas.clear()
                            quantidadesSelecionadas.clear()
                            onRefreshLancamentosProjeto()
                        } else {
                            Toast.makeText(context, response.detail ?: "Erro ao enviar: ${response.mensagem}", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, "Erro na conexão: ${e.message}", Toast.LENGTH_LONG).show()
                    } finally {
                        isSubmitting = false
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
            enabled = !isSubmitting && tarefasSelecionadas.isNotEmpty(),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
            shape = RoundedCornerShape(8.dp)
        ) {
            if (isSubmitting) {
                CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                    strokeWidth = 2.dp
                )
            } else {
                Text("Enviar Lote Diário")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModoSimplificadoView(
    equipe: String,
    projetoSelecionado: Projeto?
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val repository = remember { ConstrucaoFirestoreRepository() }

    // Form states
    var selectedLocacao by remember { mutableStateOf("") }
    var locacaoExpanded by remember { mutableStateOf(false) }

    var selectedCava by remember { mutableStateOf<Atividade?>(null) }
    var cavaExpanded by remember { mutableStateOf(false) }

    // Pole dimensions
    var comprimentoExpanded by remember { mutableStateOf(false) }
    var selectedComprimento by remember { mutableStateOf<Double?>(null) }
    val comprimentos = listOf(12.0, 13.5, 15.0, 18.0)

    var cargaExpanded by remember { mutableStateOf(false) }
    var selectedCarga by remember { mutableStateOf<Int?>(null) }
    val cargas = when (selectedComprimento) {
        12.0, 13.5 -> listOf(600, 1000, 2000, 3000)
        15.0, 18.0 -> listOf(600)
        else -> listOf(600, 1000, 2000, 3000)
    }

    // Auto-select or reset carga when length limits it
    LaunchedEffect(selectedComprimento) {
        if (selectedComprimento == 15.0 || selectedComprimento == 18.0) {
            selectedCarga = 600
        } else if (selectedCarga != null && selectedCarga !in cargas) {
            selectedCarga = null
        }
    }

    // Estruturas Padrão
    var estruturasPadrao by remember { mutableStateOf(listOf<EstruturaPadrao>()) }
    var isLoadingEstruturas by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        isLoadingEstruturas = true
        try {
            estruturasPadrao = repository.getEstruturasPadrao()
        } catch (e: Exception) {
            Toast.makeText(context, "Erro ao carregar estruturas padrão: ${e.message}", Toast.LENGTH_SHORT).show()
        } finally {
            isLoadingEstruturas = false
        }
    }

    // Cavas List
    var cavasList by remember { mutableStateOf(listOf<Atividade>()) }
    var isLoadingCavas by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        isLoadingCavas = true
        try {
            cavasList = repository.buscarAtividades("cava")
        } catch (e: Exception) {
            Toast.makeText(context, "Erro ao carregar cavas: ${e.message}", Toast.LENGTH_SHORT).show()
        } finally {
            isLoadingCavas = false
        }
    }

    val orderedCavas = remember(cavasList) {
        val topCodes = listOf(716, 616, 750)
        val topList = cavasList.filter { it.codigo in topCodes }
            .sortedBy { topCodes.indexOf(it.codigo) }
        val otherList = cavasList.filter { it.codigo !in topCodes }
            .sortedBy { it.codigo }
        topList + otherList
    }

    var selectedCategory by remember { mutableStateOf("RDC") }
    val categories = listOf("RDC", "RDA", "RDP", "RSI")

    // Filter structures by category
    val filteredEstruturas = remember(estruturasPadrao, selectedCategory) {
        estruturasPadrao.filter {
            it.tipo_rede.contains(selectedCategory, ignoreCase = true)
        }
    }

    var estPadraoExpanded by remember { mutableStateOf(false) }
    var selectedEstruturaPadrao by remember { mutableStateOf<EstruturaPadrao?>(null) }

    // Reset selected structure if it doesn't belong to the category
    LaunchedEffect(selectedCategory) {
        if (selectedEstruturaPadrao != null && !selectedEstruturaPadrao!!.tipo_rede.contains(selectedCategory, ignoreCase = true)) {
            selectedEstruturaPadrao = null
        }
    }

    // Cabo
    var caboExpanded by remember { mutableStateOf(false) }
    var selectedCabo by remember { mutableStateOf("") }
    var customCabo by remember { mutableStateOf("") }
    val cabos = listOf(
        "Multiplexado 1x1x35+35 mm²",
        "Multiplexado 3x1x35+35 mm²",
        "Multiplexado 3x1x70+70 mm²",
        "Protegido 35 mm²",
        "Protegido 70 mm²",
        "Protegido 150 mm²",
        "Nu 1/0 AWG CAA",
        "Nu 4/0 AWG CAA",
        "Outro..."
    )

    var isSubmitting by remember { mutableStateOf(false) }

    val equipeNumero = remember(equipe) {
        equipe.filter { it.isDigit() }.toIntOrNull() ?: 1
    }
    val dataExecucao = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {

        // Poste Section
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
        ) {
            Column(
                modifier = Modifier.padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = "Dados do Poste",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Locação Dropdown (Urbana / Rural)
                    Box(modifier = Modifier.weight(1f)) {
                        OutlinedTextField(
                            value = selectedLocacao,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Locação") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            trailingIcon = {
                                IconButton(onClick = { locacaoExpanded = true }) {
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }
                        )
                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable { locacaoExpanded = true }
                        )
                        DropdownMenu(
                            expanded = locacaoExpanded,
                            onDismissRequest = { locacaoExpanded = false }
                        ) {
                            listOf("Urbana", "Rural").forEach { loc ->
                                DropdownMenuItem(
                                    text = { Text(loc) },
                                    onClick = {
                                        selectedLocacao = loc
                                        locacaoExpanded = false
                                    }
                                )
                            }
                        }
                    }

                    // Cava Dropdown
                    Box(modifier = Modifier.weight(1f)) {
                        OutlinedTextField(
                            value = selectedCava?.let { "${it.codigo} - ${it.descricao.take(15)}..." } ?: "",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Cava") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            trailingIcon = {
                                IconButton(onClick = { cavaExpanded = true }) {
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }
                        )
                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable { cavaExpanded = true }
                        )
                        DropdownMenu(
                            expanded = cavaExpanded,
                            onDismissRequest = { cavaExpanded = false },
                            modifier = Modifier.fillMaxWidth(0.9f)
                        ) {
                            if (isLoadingCavas) {
                                DropdownMenuItem(
                                    text = { Text("Carregando cavas...") },
                                    onClick = {}
                                )
                            } else {
                                orderedCavas.forEach { cv ->
                                    DropdownMenuItem(
                                        text = { Text("${cv.codigo} - ${cv.descricao}", maxLines = 2, overflow = TextOverflow.Ellipsis) },
                                        onClick = {
                                            selectedCava = cv
                                            cavaExpanded = false
                                        }
                                    )
                                }
                            }
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Comprimento Dropdown
                    Box(modifier = Modifier.weight(1f)) {
                        OutlinedTextField(
                            value = selectedComprimento?.let { "${it}m" } ?: "",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Comprimento") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            trailingIcon = {
                                IconButton(onClick = { comprimentoExpanded = true }) {
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }
                        )
                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable { comprimentoExpanded = true }
                        )
                        DropdownMenu(
                            expanded = comprimentoExpanded,
                            onDismissRequest = { comprimentoExpanded = false }
                        ) {
                            comprimentos.forEach { comp ->
                                DropdownMenuItem(
                                    text = { Text("${comp}m") },
                                    onClick = {
                                        selectedComprimento = comp
                                        comprimentoExpanded = false
                                    }
                                )
                            }
                        }
                    }

                    // Carga Dropdown
                    Box(modifier = Modifier.weight(1f)) {
                        OutlinedTextField(
                            value = selectedCarga?.let { "${it} daN" } ?: "",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Carga") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            trailingIcon = {
                                IconButton(onClick = { cargaExpanded = true }) {
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }
                        )
                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable { cargaExpanded = true }
                        )
                        DropdownMenu(
                            expanded = cargaExpanded,
                            onDismissRequest = { cargaExpanded = false }
                        ) {
                            cargas.forEach { cg ->
                                DropdownMenuItem(
                                    text = { Text("${cg} daN") },
                                    onClick = {
                                        selectedCarga = cg
                                        cargaExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }

        // Estrutura Section
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
        ) {
            Column(
                modifier = Modifier.padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = "Estrutura Padronizada",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )

                // Category Filter Chips
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    categories.forEach { cat ->
                        FilterChip(
                            selected = selectedCategory == cat,
                            onClick = { selectedCategory = cat },
                            label = { Text(cat) }
                        )
                    }
                }

                if (isLoadingEstruturas) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                } else {
                    Box(modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = selectedEstruturaPadrao?.nome ?: "",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Selecionar Estrutura") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            trailingIcon = {
                                IconButton(onClick = { estPadraoExpanded = true }) {
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }
                        )
                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable { estPadraoExpanded = true }
                        )
                        DropdownMenu(
                            expanded = estPadraoExpanded,
                            onDismissRequest = { estPadraoExpanded = false },
                            modifier = Modifier.fillMaxWidth(0.9f)
                        ) {
                            if (filteredEstruturas.isEmpty()) {
                                DropdownMenuItem(
                                    text = { Text("Nenhuma estrutura nesta categoria") },
                                    onClick = {}
                                )
                            } else {
                                filteredEstruturas.forEach { est ->
                                    DropdownMenuItem(
                                        text = { Text(if (est.ntc.isNotEmpty()) "${est.nome} (${est.ntc})" else est.nome) },
                                        onClick = {
                                            selectedEstruturaPadrao = est
                                            estPadraoExpanded = false
                                        }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // Cabo Section
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
        ) {
            Column(
                modifier = Modifier.padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = "Condutor (Cabo)",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )

                Box(modifier = Modifier.fillMaxWidth()) {
                    OutlinedTextField(
                        value = selectedCabo,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Selecionar Cabo") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(8.dp),
                        trailingIcon = {
                            IconButton(onClick = { caboExpanded = true }) {
                                Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                            }
                        }
                    )
                    Box(
                        modifier = Modifier
                            .matchParentSize()
                            .clickable { caboExpanded = true }
                    )
                    DropdownMenu(
                        expanded = caboExpanded,
                        onDismissRequest = { caboExpanded = false },
                        modifier = Modifier.fillMaxWidth(0.9f)
                    ) {
                        cabos.forEach { cb ->
                            DropdownMenuItem(
                                text = { Text(cb) },
                                onClick = {
                                    selectedCabo = cb
                                    caboExpanded = false
                                }
                            )
                        }
                    }
                }

                if (selectedCabo == "Outro...") {
                    OutlinedTextField(
                        value = customCabo,
                        onValueChange = { customCabo = it },
                        label = { Text("Especifique o Cabo") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(8.dp)
                    )
                }
            }
        }

        // Botão Salvar
        Button(
            onClick = {
                if (selectedLocacao.isBlank() || selectedCava == null || selectedComprimento == null || selectedCarga == null || selectedEstruturaPadrao == null || selectedCabo.isBlank()) {
                    Toast.makeText(context, "Por favor, preencha todos os campos obrigatórios.", Toast.LENGTH_SHORT).show()
                    return@Button
                }

                val finalCabo = if (selectedCabo == "Outro...") customCabo else selectedCabo
                if (selectedCabo == "Outro..." && finalCabo.isBlank()) {
                    Toast.makeText(context, "Por favor, especifique o cabo.", Toast.LENGTH_SHORT).show()
                    return@Button
                }

                isSubmitting = true
                coroutineScope.launch {
                    try {
                        val response = repository.lancarSimplificado(
                            LancamentoSimplificadoRequest(
                                equipe_numero = equipeNumero,
                                data_execucao = dataExecucao,
                                projeto_id = projetoSelecionado?.id,
                                locacao = selectedLocacao,
                                cava = "${selectedCava!!.codigo} - ${selectedCava!!.descricao}",
                                poste_comprimento = selectedComprimento!!,
                                poste_carga = selectedCarga!!,
                                estrutura_categoria = selectedCategory,
                                estrutura_nome = selectedEstruturaPadrao!!.nome,
                                cabo = finalCabo
                            )
                        )
                        if (response.sucesso) {
                            Toast.makeText(context, response.mensagem ?: "Lançamento registrado com sucesso!", Toast.LENGTH_LONG).show()
                            // Clear form fields
                            selectedLocacao = ""
                            selectedCava = null
                            selectedComprimento = null
                            selectedCarga = null
                            selectedEstruturaPadrao = null
                            selectedCabo = ""
                            customCabo = ""
                        } else {
                            Toast.makeText(context, response.detail ?: "Erro ao registrar: ${response.mensagem}", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, "Erro na conexão: ${e.message}", Toast.LENGTH_LONG).show()
                    } finally {
                        isSubmitting = false
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
            enabled = !isSubmitting,
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10B981)),
            shape = RoundedCornerShape(8.dp)
        ) {
            if (isSubmitting) {
                CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                    strokeWidth = 2.dp
                )
            } else {
                Text("Salvar Lançamento Simplificado")
            }
        }
    }
}
