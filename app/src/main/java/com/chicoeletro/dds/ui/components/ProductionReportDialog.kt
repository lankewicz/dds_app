// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/ProductionReportDialog.kt
// Função: Dialog de relatório de produção. Exibe indicadores de produtividade, metas e 
//         histórico de desempenho da equipe de forma compacta e interativa.
// Tecnologias: Jetpack Compose, Material3.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.chicoeletro.dds.features.production.ProductionMonthlyDoc
import com.chicoeletro.dds.features.production.ProductionRepository
import kotlinx.coroutines.launch
import androidx.compose.ui.platform.LocalConfiguration
import java.text.NumberFormat
import java.util.Locale

@Composable
fun ProductionReportDialog(
    equipe: String,
    onDismiss: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val repository = remember { ProductionRepository() }
    
    var selectedYear by remember { mutableStateOf(2026) }
    var isLoading by remember { mutableStateOf(false) }
    
    // Cache de dados por ano para evitar refetch constante
    val cache = remember { mutableStateMapOf<Int, List<ProductionMonthlyDoc>>() }
    val documents = cache[selectedYear] ?: emptyList()
    
    val configuration = LocalConfiguration.current
    val isCompact = configuration.screenWidthDp < 800

    var expandedMonth by remember { mutableStateOf<Int?>(null) }

    fun loadData(force: Boolean = false) {
        if (!force && cache.containsKey(selectedYear)) return
        
        isLoading = true
        scope.launch {
            try {
                val teamKey = equipe.trim()
                val result = repository.getAnnualProduction(teamKey, selectedYear)
                cache[selectedYear] = result
            } catch (e: Exception) {
                e.printStackTrace()
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(selectedYear, equipe) {
        if (equipe.isNotBlank()) {
            loadData()
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = MaterialTheme.shapes.large,
            tonalElevation = 4.dp,
            modifier = Modifier.fillMaxSize()
        ) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                // Header Responsivo
                if (isCompact) {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Produção Anual", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                            
                            // Compact Controls
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                IconButton(onClick = { loadData(force = true) }, enabled = !isLoading) {
                                    Icon(Icons.Filled.Refresh, "Atualizar", modifier = Modifier.size(20.dp))
                                }
                                IconButton(onClick = onDismiss) {
                                    Icon(Icons.Filled.Close, "Fechar", modifier = Modifier.size(20.dp))
                                }
                            }
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text("Equipe: $equipe", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                val firstDoc = documents.firstOrNull()
                                val teamType = firstDoc?.goal?.type ?: firstDoc?.teamType ?: ""
                                if (teamType.isNotBlank()) {
                                    Text(teamType, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Light)
                                }
                            }

                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Button(onClick = { selectedYear-- }, modifier = Modifier.size(32.dp), contentPadding = PaddingValues(0.dp)) {
                                    Text("<", fontSize = 12.sp)
                                }
                                Text("$selectedYear", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(horizontal = 8.dp))
                                Button(onClick = { selectedYear++ }, modifier = Modifier.size(32.dp), contentPadding = PaddingValues(0.dp)) {
                                    Text(">", fontSize = 12.sp)
                                }
                            }
                        }

                        val members = documents.firstOrNull { it.members.isNotEmpty() }?.members ?: emptyList()
                        if (members.isNotEmpty()) {
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "Integrantes: ${members.joinToString(", ")}",
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Medium,
                                color = MaterialTheme.colorScheme.primary,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }
                } else {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Left Side: Title and Info
                        Column(Modifier.weight(1f)) {
                            Text("Produção Anual", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                            Text("Equipe: $equipe", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            
                            val firstDoc = documents.firstOrNull()
                            val teamType = firstDoc?.goal?.type ?: firstDoc?.teamType ?: ""
                            if (teamType.isNotBlank()) {
                                Text(teamType, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
                            }
                        }
                        
                        // Center: Integrantes (Increased size and centered)
                        val members = documents.firstOrNull { it.members.isNotEmpty() }?.members ?: emptyList()
                        if (members.isNotEmpty()) {
                            Column(
                                modifier = Modifier.weight(2f),
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = buildAnnotatedString {
                                        withStyle(SpanStyle(fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f), fontSize = 18.sp)) {
                                            append("Integrantes: ")
                                        }
                                        withStyle(SpanStyle(fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 20.sp)) {
                                            append(members.joinToString(", "))
                                        }
                                    },
                                    textAlign = TextAlign.Center
                                )
                            }
                        } else {
                            Spacer(Modifier.weight(2f))
                        }
                        
                        // Right Side: Controls
                        Row(
                            modifier = Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.End
                        ) {
                            IconButton(onClick = { loadData(force = true) }, enabled = !isLoading) {
                                Icon(Icons.Filled.Refresh, "Atualizar")
                            }
                            
                            Spacer(Modifier.width(8.dp))

                            Button(onClick = { selectedYear-- }, modifier = Modifier.size(40.dp), contentPadding = PaddingValues(0.dp)) {
                                Text("<")
                            }
                            Text("$selectedYear", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(horizontal = 12.dp))
                            Button(onClick = { selectedYear++ }, modifier = Modifier.size(40.dp), contentPadding = PaddingValues(0.dp)) {
                                Text(">")
                            }
                            
                            Spacer(Modifier.width(16.dp))

                            IconButton(onClick = onDismiss) {
                                Icon(Icons.Filled.Close, "Fechar")
                            }
                        }
                    }
                }
                
                Spacer(Modifier.height(10.dp))

                if (isLoading && documents.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                } else {
                    val months = listOf("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
                    
                    // Table Header
                    Row(
                        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(topStart = 8.dp, topEnd = 8.dp)).padding(horizontal = 8.dp, vertical = 5.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Mês", modifier = Modifier.weight(1.5f), fontWeight = FontWeight.Bold)
                        Text("Produção", modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                        Text("Dias", modifier = Modifier.weight(0.7f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                        Text("Km", modifier = Modifier.weight(0.8f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                        Text("Comerc", modifier = Modifier.weight(0.8f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                        Text("Serv", modifier = Modifier.weight(0.8f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                        Text("Média/Dia", modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End)
                    }

                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                        val numberFormat = NumberFormat.getNumberInstance(Locale("pt", "BR")).apply { 
                            minimumFractionDigits = 2
                            maximumFractionDigits = 2
                        }
                        val intFormat = NumberFormat.getIntegerInstance(Locale("pt", "BR"))

                        var totalProducao = 0.0
                        var totalDias = 0.0
                        var totalKm = 0.0
                        var totalComercial = 0.0
                        var totalServicos = 0.0
                        var monthsWithData = 0

                        months.forEachIndexed { index, monthName ->
                            val mNumber = index + 1
                            val monthDocs = documents.filter { it.monthNumber == mNumber }
                            
                            if (monthDocs.isNotEmpty()) {
                                // Agrega métricas do mês (pode ter múltiplos contratos/placas)
                                val sumMUs = monthDocs.sumOf { it.metrics.totalUs }
                                val sumMDays = monthDocs.sumOf { it.metrics.workDays }
                                val sumMKm = monthDocs.sumOf { it.metrics.drivenKm }
                                val sumMCom = monthDocs.sumOf { it.metrics.commercial }
                                val sumMServ = monthDocs.sumOf { it.metrics.totalServices }
                                
                                totalProducao += sumMUs
                                totalDias += sumMDays
                                totalKm += sumMKm
                                totalComercial += sumMCom
                                totalServicos += sumMServ
                                monthsWithData++

                                // Linha Principal do Mês
                                Column(
                                    Modifier
                                        .fillMaxWidth()
                                        .clickable { expandedMonth = if (expandedMonth == mNumber) null else mNumber }
                                        .background(if (expandedMonth == mNumber) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f) else Color.Transparent)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 5.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        // Cálculo de Cores baseado no Target
                                        val targetUs = monthDocs.firstOrNull()?.goal?.targetUs ?: 0.0
                                        val diff = sumMUs - targetUs
                                        
                                        val (textColor, monthWeight) = when {
                                            targetUs <= 0 -> Color.Unspecified to FontWeight.Medium
                                            diff > 100 -> Color(0xFF1B5E20) to FontWeight.Bold // Green (Dark)
                                            diff < 0 -> {
                                                // Escala de vermelho: se faltar menos de 100 US fica vermelho forte
                                                val redColor = if (diff > -100) Color.Red else Color(0xFFB71C1C) // Red scale
                                                redColor to FontWeight.Bold
                                            }
                                            else -> Color.Unspecified to FontWeight.Medium
                                        }

                                        Text(monthName, modifier = Modifier.weight(1.5f), fontWeight = monthWeight, color = textColor)
                                        Text(
                                            text = numberFormat.format(sumMUs), 
                                            modifier = Modifier.weight(1f), 
                                            textAlign = TextAlign.End,
                                            color = textColor,
                                            fontWeight = if (textColor != Color.Unspecified) FontWeight.Bold else FontWeight.Normal
                                        )
                                        Text(intFormat.format(sumMDays), modifier = Modifier.weight(0.7f), textAlign = TextAlign.End)
                                        Text(intFormat.format(sumMKm), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End)
                                        Text(intFormat.format(sumMCom), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End)
                                        Text(intFormat.format(sumMServ), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End)
                                        
                                        val media = if (sumMDays > 0) sumMServ / sumMDays else 0.0
                                        Text(numberFormat.format(media), modifier = Modifier.weight(1f), textAlign = TextAlign.End)
                                    }
                                    
                                }
                            } else {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 5.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(monthName, modifier = Modifier.weight(1f), color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(1f), textAlign = TextAlign.End, color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(0.7f), textAlign = TextAlign.End, color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, color = Color.Gray)
                                    Text("-", modifier = Modifier.weight(1f), textAlign = TextAlign.End, color = Color.Gray)
                                }
                            }
                            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                        }

                        // Footer Estilizado (Média e Total)
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(bottomStart = 8.dp, bottomEnd = 8.dp))
                                .padding(horizontal = 8.dp, vertical = 5.dp)
                        ) {
                            // Linha de Médias
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("MÉDIAS", modifier = Modifier.weight(1.5f), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                
                                val avgProducao = if (monthsWithData > 0) totalProducao / monthsWithData else 0.0
                                val avgDias = if (monthsWithData > 0) totalDias / monthsWithData else 0.0
                                val avgKm = if (monthsWithData > 0) totalKm / monthsWithData else 0.0
                                val avgComercial = if (monthsWithData > 0) totalComercial / monthsWithData else 0.0
                                val avgServicos = if (monthsWithData > 0) totalServicos / monthsWithData else 0.0
                                
                                Text(numberFormat.format(avgProducao), modifier = Modifier.weight(1f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                Text(numberFormat.format(avgDias), modifier = Modifier.weight(0.7f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                Text(numberFormat.format(avgKm), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                Text(numberFormat.format(avgComercial), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                Text(numberFormat.format(avgServicos), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                
                                val avgMediaDia = if (totalDias > 0) totalServicos / totalDias else 0.0
                                Text(numberFormat.format(avgMediaDia), modifier = Modifier.weight(1f), textAlign = TextAlign.End, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                            }
                            
                            Spacer(Modifier.height(3.dp))
                            HorizontalDivider(color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f))
                            Spacer(Modifier.height(3.dp))

                            // Linha de Totais
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("TOTAIS", modifier = Modifier.weight(1.5f), fontWeight = FontWeight.ExtraBold)
                                Text(numberFormat.format(totalProducao), modifier = Modifier.weight(1f), textAlign = TextAlign.End, fontWeight = FontWeight.ExtraBold)
                                Text(intFormat.format(totalDias), modifier = Modifier.weight(0.7f), textAlign = TextAlign.End, fontWeight = FontWeight.ExtraBold)
                                Text(intFormat.format(totalKm), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.ExtraBold)
                                Text(intFormat.format(totalComercial), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.ExtraBold)
                                Text(intFormat.format(totalServicos), modifier = Modifier.weight(0.8f), textAlign = TextAlign.End, fontWeight = FontWeight.ExtraBold)
                                Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        }
    }
}