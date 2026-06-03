// Módulo: app/src/main/java/com/chicoeletro/dds/ui/components/TeamTypeSelectionScreen.kt
// Função: Tela de seleção do tipo de equipe (STC, EP, Linha Viva, Roçada, Construção).
//         Apresenta interface premium em formato de tiles (grades) e solicita confirmação antes do salvamento.
// Tecnologias: Jetpack Compose, Material 3, Vector Icons.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ElectricBolt
import androidx.compose.material.icons.filled.ElectricalServices
import androidx.compose.material.icons.filled.Engineering
import androidx.compose.material.icons.filled.Forest
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

data class TeamTypeOption(
    val key: String,
    val title: String,
    val description: String,
    val icon: ImageVector,
    val accentColor: Color
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeamTypeSelectionScreen(
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    val options = remember {
        listOf(
            TeamTypeOption(
                key = "STC",
                title = "STC (NR-10)",
                description = "Caminhonetes Hilux, cabina simples, com escada ou cesto aéreo.",
                icon = Icons.Filled.ElectricalServices,
                accentColor = Color(0xFF0288D1) // Azul Premium
            ),
            TeamTypeOption(
                key = "EP",
                title = "EP (Manutenção)",
                description = "Caminhonetes Hilux, cabina dupla, com escada.",
                icon = Icons.Filled.Engineering,
                accentColor = Color(0xFF00E676) // Verde Dinâmico
            ),
            TeamTypeOption(
                key = "LINHA_VIVA",
                title = "Linha Viva",
                description = "Caminhões com cesto aéreo isolado.",
                icon = Icons.Filled.ElectricBolt,
                accentColor = Color(0xFFFFD600) // Amarelo Vivo
            ),
            TeamTypeOption(
                key = "ROCADA",
                title = "Roçada",
                description = "Caminhonetes Hilux, cabina dupla, sem escada.",
                icon = Icons.Filled.Forest,
                accentColor = Color(0xFF81C784) // Verde Floresta
            ),
            TeamTypeOption(
                key = "CONSTRUCAO",
                title = "Construção",
                description = "Caminhão carregando poste.",
                icon = Icons.Filled.LocalShipping,
                accentColor = Color(0xFFFF7043) // Laranja Construção
            )
        )
    }

    var selectedKey by remember { mutableStateOf<String?>(null) }
    var pendingConfirmOption by remember { mutableStateOf<TeamTypeOption?>(null) }

    val configuration = LocalConfiguration.current
    val isTablet = configuration.screenWidthDp >= 600
    val scrollState = rememberScrollState()

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = Color(0xFF0F1115) // Fundo Escuro Premium do App
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = if (isTablet) 32.dp else 16.dp, vertical = 24.dp)
        ) {
            // Header Bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Configuração do BDO",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
                IconButton(onClick = onDismiss) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Fechar",
                        tint = Color.White.copy(alpha = 0.7f)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Conteúdo principal
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(scrollState),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Qual o tipo de trabalho da sua equipe?",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    textAlign = TextAlign.Center
                )

                Spacer(modifier = Modifier.height(6.dp))

                Text(
                    text = "Selecione a categoria correspondente abaixo. Cada categoria possui um BDO com formulários e regras específicas.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color(0xFFB0B7C3),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(horizontal = 8.dp)
                )

                Spacer(modifier = Modifier.height(20.dp))

                // Grid de Tiles adaptativo
                val gridModifier = if (isTablet) Modifier.widthIn(max = 750.dp) else Modifier.fillMaxWidth()
                Column(
                    modifier = gridModifier,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    if (isTablet) {
                        // Tablet Layout (3 colunas na linha 1, 2 colunas na linha 2)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            options.take(3).forEach { option ->
                                Box(modifier = Modifier.weight(1f)) {
                                    TeamTypeTileCard(
                                        option = option,
                                        isSelected = selectedKey == option.key,
                                        onClick = { selectedKey = option.key }
                                    )
                                }
                            }
                        }
                        Row(
                            modifier = Modifier.fillMaxWidth(0.666f),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            options.drop(3).take(2).forEach { option ->
                                Box(modifier = Modifier.weight(1f)) {
                                    TeamTypeTileCard(
                                        option = option,
                                        isSelected = selectedKey == option.key,
                                        onClick = { selectedKey = option.key }
                                    )
                                }
                            }
                        }
                    } else {
                        // Phone Layout (2 colunas por linha, com o último item ocupando a largura total ou centralizado)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            options.take(2).forEach { option ->
                                Box(modifier = Modifier.weight(1f)) {
                                    TeamTypeTileCard(
                                        option = option,
                                        isSelected = selectedKey == option.key,
                                        onClick = { selectedKey = option.key }
                                    )
                                }
                            }
                        }
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            options.drop(2).take(2).forEach { option ->
                                Box(modifier = Modifier.weight(1f)) {
                                    TeamTypeTileCard(
                                        option = option,
                                        isSelected = selectedKey == option.key,
                                        onClick = { selectedKey = option.key }
                                    )
                                }
                            }
                        }
                        Row(
                            modifier = Modifier.fillMaxWidth(0.5f),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            options.drop(4).forEach { option ->
                                Box(modifier = Modifier.fillMaxWidth()) {
                                    TeamTypeTileCard(
                                        option = option,
                                        isSelected = selectedKey == option.key,
                                        onClick = { selectedKey = option.key }
                                    )
                                }
                            }
                        }
                    }
                }
                Spacer(modifier = Modifier.height(24.dp))
            }

            // Confirmar Button
            Button(
                onClick = { 
                    pendingConfirmOption = options.find { it.key == selectedKey }
                },
                enabled = selectedKey != null,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp)
                    .widthIn(max = 500.dp)
                    .align(Alignment.CenterHorizontally),
                shape = RoundedCornerShape(28.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    disabledContainerColor = Color(0xFF262A33)
                )
            ) {
                Text(
                    text = "Confirmar Categoria",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (selectedKey != null) Color.Black else Color.White.copy(alpha = 0.3f)
                )
            }
        }
    }

    // Modal de Confirmação Requerida
    if (pendingConfirmOption != null) {
        val option = pendingConfirmOption!!
        AlertDialog(
            onDismissRequest = { pendingConfirmOption = null },
            title = {
                Text(
                    text = "Confirmar Tipo de BDO",
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
            },
            text = {
                Column {
                    Text(
                        text = "Atenção: As equipes do tipo ${option.title} possuem uma forma específica e regras próprias para realizar o Boletim Diário de Obra (BDO).",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color(0xFFE8EAED)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "Confirma que sua equipe se encaixa nesta categoria?",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = option.accentColor
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val key = option.key
                        pendingConfirmOption = null
                        onConfirm(key)
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = option.accentColor,
                        contentColor = Color.Black
                    )
                ) {
                    Text("Sim, Confirmar", fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { pendingConfirmOption = null }
                ) {
                    Text("Cancelar", color = Color(0xFF8E96A3))
                }
            },
            shape = RoundedCornerShape(24.dp),
            containerColor = Color(0xFF1C2028),
            iconContentColor = Color.White
        )
    }
}

@Composable
fun TeamTypeTileCard(
    option: TeamTypeOption,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val cardBgColor = if (isSelected) Color(0xFF1E2330) else Color(0xFF1C2028)
    val cardBorder = if (isSelected) {
        BorderStroke(2.dp, option.accentColor)
    } else {
        BorderStroke(1.dp, Color(0xFF2D323E))
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(175.dp)
            .clickable(onClick = onClick)
            .border(cardBorder.width, cardBorder.brush, RoundedCornerShape(20.dp)),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = cardBgColor),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 8.dp else 2.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp)
        ) {
            // Seleção check indicator
            if (isSelected) {
                Icon(
                    imageVector = Icons.Filled.CheckCircle,
                    contentDescription = "Selecionado",
                    tint = option.accentColor,
                    modifier = Modifier
                        .size(24.dp)
                        .align(Alignment.TopEnd)
                )
            }

            Column(
                modifier = Modifier.fillMaxSize(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                // Circular container para o Ícone
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .background(
                            color = option.accentColor.copy(alpha = if (isSelected) 0.2f else 0.1f),
                            shape = RoundedCornerShape(12.dp)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = option.icon,
                        contentDescription = null,
                        tint = option.accentColor,
                        modifier = Modifier.size(24.dp)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Título
                Text(
                    text = option.title,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    textAlign = TextAlign.Center,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                Spacer(modifier = Modifier.height(4.dp))

                // Descrição curta (reduzida para caber no tile)
                Text(
                    text = option.description,
                    fontSize = 11.sp,
                    color = if (isSelected) Color(0xFFE8EAED) else Color(0xFF8E96A3),
                    textAlign = TextAlign.Center,
                    maxLines = 3,
                    lineHeight = 14.sp,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}
