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
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
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
import com.chicoeletro.dds.features.construcao.*
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
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Por Poste (Completo)", "Por Lote (Rápido)")

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(top = 4.dp)
    ) {
        // TabRow elegante para alternar entre Poste e Lote
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = Color.Transparent,
            contentColor = MaterialTheme.colorScheme.primary,
            modifier = Modifier
                .fillMaxWidth()
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

        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            when (selectedTab) {
                0 -> ModoPosteView(equipe = equipe, online = online)
                1 -> ModoLoteView(equipe = equipe, online = online)
            }
        }
    }
}

@Composable
fun ModoPosteView(equipe: String, online: Boolean) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    var projetos by remember { mutableStateOf(listOf<Projeto>()) }
    var projetoSelecionado by remember { mutableStateOf<Projeto?>(null) }
    var projExpanded by remember { mutableStateOf(false) }

    var estruturas by remember { mutableStateOf(listOf<Estrutura>()) }
    var estruturaSelecionada by remember { mutableStateOf<Estrutura?>(null) }
    var estExpanded by remember { mutableStateOf(false) }

    var tarefas by remember { mutableStateOf(listOf<Tarefa>()) }
    val tarefasSelecionadas = remember { mutableStateListOf<Int>() }

    var isLoading by remember { mutableStateOf(false) }
    var isSubmitting by remember { mutableStateOf(false) }

    val equipeNumero = remember(equipe) {
        equipe.filter { it.isDigit() }.toIntOrNull() ?: 1
    }
    val dataExecucao = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    // Carregar lista de Projetos na inicialização
    LaunchedEffect(Unit) {
        isLoading = true
        try {
            projetos = ConstrucaoRetrofitClient.instance.getProjetos()
        } catch (e: Exception) {
            Toast.makeText(context, "Erro ao carregar projetos: ${e.message}", Toast.LENGTH_SHORT).show()
        } finally {
            isLoading = false
        }
    }

    // Carregar Estruturas quando o projeto for alterado
    LaunchedEffect(projetoSelecionado) {
        projetoSelecionado?.let { proj ->
            try {
                estruturas = ConstrucaoRetrofitClient.instance.getEstruturas(proj.id)
                estruturaSelecionada = null
                tarefas = emptyList()
                tarefasSelecionadas.clear()
            } catch (e: Exception) {
                estruturas = emptyList()
                Toast.makeText(context, "Erro ao carregar estruturas: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    // Carregar Tarefas quando a estrutura for alterada
    LaunchedEffect(estruturaSelecionada) {
        estruturaSelecionada?.let { est ->
            try {
                tarefas = ConstrucaoRetrofitClient.instance.getTarefas(est.id)
                tarefasSelecionadas.clear()
                // Pré-seleciona todas como facilitador
                tarefas.forEach { t -> tarefasSelecionadas.add(t.id) }
            } catch (e: Exception) {
                tarefas = emptyList()
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
            // Dropdowns de Projeto e Estrutura
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Dropdown de Projeto
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Projeto",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Box(modifier = Modifier.fillMaxWidth()) {
                        OutlinedButton(
                            onClick = { projExpanded = true },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 10.dp)
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text(
                                    text = projetoSelecionado?.titulo ?: "Selecionar...",
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    color = if (projetoSelecionado != null) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                            }
                        }
                        DropdownMenu(
                            expanded = projExpanded,
                            onDismissRequest = { projExpanded = false },
                            modifier = Modifier.fillMaxWidth(0.45f)
                        ) {
                            projetos.forEach { p ->
                                DropdownMenuItem(
                                    text = { Text("[${p.id}] ${p.titulo}", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                    onClick = {
                                        projetoSelecionado = p
                                        projExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }

                // Dropdown de Estrutura
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Poste / Estrutura (PS)",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
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
                            modifier = Modifier.fillMaxWidth(0.45f)
                        ) {
                            estruturas.forEach { e ->
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
            Text(
                text = "Marque os itens executados:",
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
                } else if (estruturaSelecionada == null) {
                    item {
                        Text(
                            text = "Selecione uma estrutura/poste para visualizar as tarefas.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 32.dp)
                        )
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
                    items(tarefas) { t ->
                        val isChecked = tarefasSelecionadas.contains(t.id)
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = if (isChecked) {
                                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
                                } else {
                                    MaterialTheme.colorScheme.surface
                                }
                            ),
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    if (isChecked) {
                                        tarefasSelecionadas.remove(t.id)
                                    } else {
                                        tarefasSelecionadas.add(t.id)
                                    }
                                }
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 8.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Checkbox(
                                    checked = isChecked,
                                    onCheckedChange = { checked ->
                                        if (checked == true) {
                                            tarefasSelecionadas.add(t.id)
                                        } else {
                                            tarefasSelecionadas.remove(t.id)
                                        }
                                    }
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = t.descricao,
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.Medium
                                    )
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Código: ${t.atividade_codigo}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                        Text(
                                            text = if (t.sinal == "+") "Montagem" else "Desmontagem",
                                            color = if (t.sinal == "+") Color(0xFF2E7D32) else Color(0xFFC62828),
                                            style = MaterialTheme.typography.bodySmall,
                                            fontWeight = FontWeight.Bold
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

            // Botão Confirmar Lançamento do Poste
            Button(
                onClick = {
                    val proj = projetoSelecionado ?: return@Button
                    val est = estruturaSelecionada ?: return@Button
                    if (tarefasSelecionadas.isEmpty()) return@Button

                    isSubmitting = true
                    coroutineScope.launch {
                        try {
                            val response = ConstrucaoRetrofitClient.instance.lancarPoste(
                                LancamentoPosteRequest(
                                    equipe_numero = equipeNumero,
                                    data_execucao = dataExecucao,
                                    projeto_id = proj.id,
                                    estrutura_id = est.id,
                                    tarefas_completadas = tarefasSelecionadas.toList()
                                )
                            )
                            if (response.sucesso) {
                                Toast.makeText(context, response.mensagem ?: "Poste lançado com sucesso!", Toast.LENGTH_LONG).show()
                                // Reseta seleções de tarefas e avança estrutura para facilitar fluxo
                                tarefasSelecionadas.clear()
                                val currentIndex = estruturas.indexOf(est)
                                if (currentIndex != -1 && currentIndex < estruturas.lastIndex) {
                                    estruturaSelecionada = estruturas[currentIndex + 1]
                                } else {
                                    estruturaSelecionada = null
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
                    .fillMaxWidth()
                    .height(48.dp),
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
        }
    }
}

@Composable
fun ModoLoteView(equipe: String, online: Boolean) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    var queryBusca by remember { mutableStateOf("") }
    var atividadesSugeridas by remember { mutableStateOf(listOf<Atividade>()) }

    val itensLote = remember { mutableStateListOf<ItemLoteRequest>() }
    val descricoesLote = remember { mutableStateMapOf<Int, String>() }
    val atividadesMapa = remember { mutableStateMapOf<Int, Atividade>() }

    var isSubmitting by remember { mutableStateOf(false) }

    val equipeNumero = remember(equipe) {
        equipe.filter { it.isDigit() }.toIntOrNull() ?: 1
    }
    val dataExecucao = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    // Busca de atividades (debounced simulado)
    LaunchedEffect(queryBusca) {
        if (queryBusca.length >= 2) {
            try {
                atividadesSugeridas = ConstrucaoRetrofitClient.instance.buscarAtividades(queryBusca)
            } catch (e: Exception) {
                atividadesSugeridas = emptyList()
            }
        } else {
            atividadesSugeridas = emptyList()
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Campo de Pesquisa MIT
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

        Spacer(modifier = Modifier.height(4.dp))

        // Requadro de Sugestões de Pesquisa
        Box(modifier = Modifier.fillMaxWidth()) {
            if (atividadesSugeridas.isNotEmpty()) {
                Surface(
                    color = MaterialTheme.colorScheme.surface,
                    tonalElevation = 6.dp,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 200.dp)
                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
                ) {
                    LazyColumn(
                        modifier = Modifier.padding(6.dp)
                    ) {
                        items(atividadesSugeridas) { a ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        if (!itensLote.any { it.codigo == a.codigo }) {
                                            itensLote.add(ItemLoteRequest(codigo = a.codigo, quantidade = 1.0, tipo = "MONTAGEM"))
                                            descricoesLote[a.codigo] = a.descricao
                                            atividadesMapa[a.codigo] = a
                                        }
                                        queryBusca = ""
                                        atividadesSugeridas = emptyList()
                                    }
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "[${a.codigo}] ",
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.primary,
                                    fontSize = 14.sp
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(
                                    text = a.descricao,
                                    fontSize = 14.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Lista do Lote Atual
        Text(
            text = "Lote de Produção Acumulado:",
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
            if (itensLote.isEmpty()) {
                item {
                    Text(
                        text = "Use o campo de busca acima para adicionar itens ao lote.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 48.dp)
                    )
                }
            } else {
                items(itensLote) { item ->
                    val desc = descricoesLote[item.codigo] ?: "MIT ${item.codigo}"
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(
                            modifier = Modifier.padding(10.dp)
                        ) {
                            val atividade = atividadesMapa[item.codigo]
                            val isDinamico = atividade?.calculo_dinamico == true
                            val tipoCalculo = atividade?.tipo_calculo

                            Text(
                                text = desc,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Bold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Cód: ${item.codigo}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )

                                // Seletor M (Montagem) / D (Desmontagem)
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(2.dp)
                                ) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.clickable {
                                            val idx = itensLote.indexOf(item)
                                            if (idx != -1) {
                                                itensLote[idx] = item.copy(tipo = "MONTAGEM")
                                            }
                                        }
                                    ) {
                                        RadioButton(
                                            selected = item.tipo == "MONTAGEM",
                                            onClick = {
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    itensLote[idx] = item.copy(tipo = "MONTAGEM")
                                                }
                                            },
                                            colors = RadioButtonDefaults.colors(selectedColor = Color(0xFF2E7D32))
                                        )
                                        Text("M", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = if (item.tipo == "MONTAGEM") Color(0xFF2E7D32) else MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.clickable {
                                            val idx = itensLote.indexOf(item)
                                            if (idx != -1) {
                                                itensLote[idx] = item.copy(tipo = "DESMONTAGEM")
                                            }
                                        }
                                    ) {
                                        RadioButton(
                                            selected = item.tipo == "DESMONTAGEM",
                                            onClick = {
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    itensLote[idx] = item.copy(tipo = "DESMONTAGEM")
                                                }
                                            },
                                            colors = RadioButtonDefaults.colors(selectedColor = Color(0xFFC62828))
                                        )
                                        Text("D", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = if (item.tipo == "DESMONTAGEM") Color(0xFFC62828) else MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                  // Botões Incremento/Decremento ou Remover
                                if (isDinamico) {
                                    IconButton(
                                        onClick = {
                                            itensLote.remove(item)
                                            atividadesMapa.remove(item.codigo)
                                        },
                                        modifier = Modifier.size(28.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Close,
                                            contentDescription = "Remover",
                                            tint = MaterialTheme.colorScheme.error
                                        )
                                    }
                                } else {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        IconButton(
                                            onClick = {
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    if (item.quantidade > 1) {
                                                        itensLote[idx] = item.copy(quantidade = item.quantidade - 1)
                                                    } else {
                                                        itensLote.removeAt(idx)
                                                        atividadesMapa.remove(item.codigo)
                                                    }
                                                }
                                            },
                                            modifier = Modifier
                                                .size(28.dp)
                                                .background(MaterialTheme.colorScheme.secondaryContainer, RoundedCornerShape(6.dp))
                                        ) {
                                            Text("-", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSecondaryContainer, fontSize = 16.sp)
                                        }
                                        Text(
                                            text = item.quantidade.toInt().toString(),
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp,
                                            modifier = Modifier.widthIn(min = 16.dp),
                                            textAlign = TextAlign.Center
                                        )
                                        IconButton(
                                            onClick = {
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    itensLote[idx] = item.copy(quantidade = item.quantidade + 1)
                                                }
                                            },
                                            modifier = Modifier
                                                .size(28.dp)
                                                .background(MaterialTheme.colorScheme.secondaryContainer, RoundedCornerShape(6.dp))
                                        ) {
                                            Text("+", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSecondaryContainer, fontSize = 16.sp)
                                        }
                                    }
                                }
                            }
                        }

                            if (isDinamico) {
                                Spacer(modifier = Modifier.height(10.dp))
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    if (tipoCalculo in listOf("deslocamento", "deslocamento_adicional", "deslocamento_cancelado")) {
                                        OutlinedTextField(
                                            value = if (item.elementos != null) item.elementos.toString() else "",
                                            onValueChange = { valText ->
                                                val valInt = valText.filter { it.isDigit() }.toIntOrNull()
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    val dist = item.distancia ?: 0.0
                                                    val elems = valInt ?: 0
                                                    itensLote[idx] = item.copy(
                                                        elementos = valInt,
                                                        quantidade = 0.045 * elems * dist
                                                    )
                                                }
                                            },
                                            label = { Text("Elementos", fontSize = 10.sp) },
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            singleLine = true,
                                            modifier = Modifier.weight(1f).height(52.dp)
                                        )
                                        OutlinedTextField(
                                            value = if (item.distancia != null) item.distancia.toString() else "",
                                            onValueChange = { valText ->
                                                val valDouble = valText.replace(",", ".").toDoubleOrNull()
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    val dist = valDouble ?: 0.0
                                                    val elems = item.elementos ?: 0
                                                    itensLote[idx] = item.copy(
                                                        distancia = valDouble,
                                                        quantidade = 0.045 * elems * dist
                                                    )
                                                }
                                            },
                                            label = { Text("Distância (KM)", fontSize = 10.sp) },
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            singleLine = true,
                                            modifier = Modifier.weight(1.2f).height(52.dp)
                                        )
                                    } else if (tipoCalculo == "deslocamento_simples") {
                                        OutlinedTextField(
                                            value = if (item.distancia != null) item.distancia.toString() else "",
                                            onValueChange = { valText ->
                                                val valDouble = valText.replace(",", ".").toDoubleOrNull()
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    val dist = valDouble ?: 0.0
                                                    itensLote[idx] = item.copy(
                                                        distancia = valDouble,
                                                        quantidade = 0.045 * dist
                                                    )
                                                }
                                            },
                                            label = { Text("Distância (KM)", fontSize = 10.sp) },
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            singleLine = true,
                                            modifier = Modifier.fillMaxWidth().height(52.dp)
                                        )
                                    } else if (tipoCalculo in listOf("hora_extra", "transporte_meios_alternativos")) {
                                        OutlinedTextField(
                                            value = if (item.elementos != null) item.elementos.toString() else "",
                                            onValueChange = { valText ->
                                                val valInt = valText.filter { it.isDigit() }.toIntOrNull()
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    val hrs = item.horas ?: 0.0
                                                    val elems = valInt ?: 0
                                                    itensLote[idx] = item.copy(
                                                        elementos = valInt,
                                                        quantidade = (hrs + 2.0) * elems
                                                    )
                                                }
                                            },
                                            label = { Text("Elementos", fontSize = 10.sp) },
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            singleLine = true,
                                            modifier = Modifier.weight(1f).height(52.dp)
                                        )
                                        OutlinedTextField(
                                            value = if (item.horas != null) item.horas.toString() else "",
                                            onValueChange = { valText ->
                                                val valDouble = valText.replace(",", ".").toDoubleOrNull()
                                                val idx = itensLote.indexOf(item)
                                                if (idx != -1) {
                                                    val hrs = valDouble ?: 0.0
                                                    val elems = item.elementos ?: 0
                                                    itensLote[idx] = item.copy(
                                                        horas = valDouble,
                                                        quantidade = (hrs + 2.0) * elems
                                                    )
                                                }
                                            },
                                            label = { Text("Tempo (Horas)", fontSize = 10.sp) },
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            singleLine = true,
                                            modifier = Modifier.weight(1.2f).height(52.dp)
                                        )
                                }
                            }
                        }
                            Spacer(modifier = Modifier.height(6.dp))
                            val totalUs = item.quantidade
                            Text(
                                text = "Faturamento estimado: " + String.format(Locale.getDefault(), "%.3f", totalUs) + " US",
                                color = Color(0xFF1B5E20),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.fillMaxWidth(),
                                textAlign = TextAlign.End
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Botão Enviar Lote Diário
        Button(
            onClick = {
                if (itensLote.isEmpty()) return@Button

                isSubmitting = true
                coroutineScope.launch {
                    try {
                        val response = ConstrucaoRetrofitClient.instance.lancarLote(
                            LancamentoLoteRequest(
                                equipe_numero = equipeNumero,
                                data_execucao = dataExecucao,
                                projeto_id = null,
                                itens = itensLote.toList()
                            )
                        )
                        if (response.sucesso) {
                            Toast.makeText(context, response.mensagem ?: "Lote enviado com sucesso!", Toast.LENGTH_LONG).show()
                            itensLote.clear()
                            descricoesLote.clear()
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
            enabled = !isSubmitting && itensLote.isNotEmpty(),
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
