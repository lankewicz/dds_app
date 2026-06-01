package com.chicoeletro.dds.ui.sections

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Assignment
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import com.chicoeletro.dds.R
import com.chicoeletro.dds.ui.training.MonthParticipationDay
import com.chicoeletro.dds.features.turno.EstadoTurno

data class HomeOption(
    val title: String,
    val icon: ImageVector? = null,
    val iconResId: Int? = null,
    val color: Color,
    val onClick: () -> Unit,
    val subtitle: String? = null,
    val subtitleColor: Color? = null
)

@Composable
fun HomeScreen(
    equipe: String,
    eletricistas: List<String>,
    monthParticipationDays: List<MonthParticipationDay>,
    turnoEstado: EstadoTurno,
    onClickEquipe: () -> Unit,
    onDdsClick: () -> Unit,
    onTurnoClick: () -> Unit,
    onProducaoClick: () -> Unit,
    onMensagensClick: () -> Unit,
    onAbastecimentoClick: () -> Unit
) {
    val options = listOf(
        HomeOption("DDS", iconResId = R.drawable.dds, color = Color(0xFF2E7D32), onClick = onDdsClick),
        HomeOption(
            title = "Turno",
            icon = Icons.Default.AccessTime,
            color = Color(0xFF1976D2),
            onClick = onTurnoClick,
            subtitle = when (turnoEstado) {
                EstadoTurno.FECHADO -> "FECHADO"
                EstadoTurno.ABERTO -> "ABERTO"
                EstadoTurno.INTERVALO -> "INTERVALO"
                EstadoTurno.DESLOCAMENTO_ESPECIAL -> "DESLOCAMENTO"
            },
            subtitleColor = when (turnoEstado) {
                EstadoTurno.FECHADO -> Color(0xFFC62828)
                EstadoTurno.ABERTO -> Color(0xFF2E7D32)
                EstadoTurno.INTERVALO -> Color(0xFFEF6C00)
                EstadoTurno.DESLOCAMENTO_ESPECIAL -> Color(0xFF1976D2)
            }
        ),
        HomeOption("Produção", icon = Icons.Default.BarChart, color = Color(0xFFF57C00), onClick = onProducaoClick),
        HomeOption("Mensagens", icon = Icons.AutoMirrored.Filled.Chat, color = Color(0xFF7B1FA2), onClick = onMensagensClick),
        HomeOption("Abastecimento", icon = Icons.Default.LocalGasStation, color = Color(0xFFD32F2F), onClick = onAbastecimentoClick),
        HomeOption(
            title = equipe.ifBlank { "Definir equipe" },
            icon = Icons.Default.People,
            color = Color(0xFF00ACC1),
            onClick = onClickEquipe,
            subtitle = null
        )
    )

    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val isCompactHeight = maxHeight < 550.dp
        val spacing = if (isCompactHeight) 8.dp else 16.dp
        val iconSize = if (isCompactHeight) 24.dp else 36.dp
        val fontSize = if (isCompactHeight) 14.sp else 16.sp
        val subtitleSize = if (isCompactHeight) 10.sp else 12.sp
        val subtitleMaxLines = if (isCompactHeight) 1 else 3

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(spacing),
            verticalArrangement = Arrangement.spacedBy(spacing)
        ) {
            // Row 1 (DDS, Turno, Produção)
            Row(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(spacing)
            ) {
                options.take(3).forEach { option ->
                    Box(modifier = Modifier.weight(1f)) {
                        HomeCard(
                            option = option,
                            iconSize = iconSize,
                            fontSize = fontSize,
                            subtitleSize = subtitleSize,
                            subtitleMaxLines = 1,
                            participationDays = if (option.title == "DDS") monthParticipationDays else emptyList(),
                            isCompactHeight = isCompactHeight
                        )
                    }
                }
            }

            // Row 2 (Mensagens, Abastecimento, Equipe)
            Row(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(spacing)
            ) {
                options.drop(3).take(3).forEach { option ->
                    val maxLines = if (option.title == equipe || option.title == "Equipe") subtitleMaxLines else 1
                    Box(modifier = Modifier.weight(1f)) {
                        HomeCard(
                            option = option,
                            iconSize = iconSize,
                            fontSize = fontSize,
                            subtitleSize = subtitleSize,
                            subtitleMaxLines = maxLines,
                            isCompactHeight = isCompactHeight
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun HomeCard(
    option: HomeOption,
    iconSize: Dp,
    fontSize: TextUnit,
    subtitleSize: TextUnit,
    subtitleMaxLines: Int = 1,
    participationDays: List<MonthParticipationDay> = emptyList(),
    isCompactHeight: Boolean = false
) {
    val isDdsCard = option.title == "DDS"
    val isTurnoCard = option.title == "Turno"

    Card(
        modifier = Modifier
            .fillMaxSize()
            .clickable { option.onClick() },
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val cardHeight = maxHeight

            if (isDdsCard) {
                // DDS specific layout designed to occupy 90% of area and ~75% logo size
                val verticalPadding = cardHeight * 0.05f // 5% top and 5% bottom padding
                
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp, vertical = verticalPadding),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.SpaceBetween
                ) {
                    // Logo takes ~72% of height (leaving enough space for title and presence info)
                    Box(
                        modifier = Modifier
                            .weight(0.72f)
                            .fillMaxWidth(),
                        contentAlignment = Alignment.Center
                    ) {
                        if (option.iconResId != null) {
                            Image(
                                painter = painterResource(id = option.iconResId),
                                contentDescription = option.title,
                                modifier = Modifier.fillMaxHeight(),
                                contentScale = ContentScale.Fit
                            )
                        }
                    }

                    // Remaining content (Title & Presence Bar) takes ~28% of height
                    Column(
                        modifier = Modifier
                            .weight(0.28f)
                            .fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = option.title,
                            fontSize = fontSize,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                            textAlign = TextAlign.Center,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        
                        if (participationDays.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(if (isCompactHeight) 1.dp else 2.dp))
                            
                            val last15Days = participationDays

                            val squareSize = if (isCompactHeight) 4.dp else 5.dp
                            val isSelectedSize = if (isCompactHeight) 5.5.dp else 7.dp
                            val dayFontSize = if (isCompactHeight) 6.sp else 8.sp

                            Row(
                                modifier = Modifier.fillMaxWidth(0.98f),
                                horizontalArrangement = Arrangement.SpaceEvenly,
                                verticalAlignment = Alignment.Top
                            ) {
                                last15Days.forEach { day ->
                                    val color = when {
                                        day.isPresent -> Color(0xFF2E7D32)
                                        day.isAbsent -> Color(0xFFC62828)
                                        day.hasTraining -> Color(0xFFFFA000)
                                        else -> Color.LightGray.copy(alpha = 0.4f)
                                    }
                                    Column(
                                        horizontalAlignment = Alignment.CenterHorizontally,
                                        verticalArrangement = Arrangement.spacedBy(1.dp)
                                    ) {
                                        Box(
                                            modifier = Modifier
                                                .size(if (day.isSelected) isSelectedSize else squareSize)
                                                .background(color, RoundedCornerShape(1.dp))
                                        )
                                        Text(
                                            text = day.dayNumber.toString(),
                                            fontSize = dayFontSize,
                                            fontWeight = FontWeight.Normal,
                                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            } else if (isTurnoCard) {
                val statusBgColor = option.subtitleColor ?: Color.Gray
                val statusText = option.subtitle ?: ""

                Column(modifier = Modifier.fillMaxSize()) {
                    // Top 2/3: Title and Icon
                    val topPadding = if (isCompactHeight) 6.dp else 12.dp
                    val topSpacing = if (isCompactHeight) 2.dp else 4.dp

                    Column(
                        modifier = Modifier
                            .weight(2f)
                            .fillMaxWidth()
                            .padding(top = topPadding, bottom = 2.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        if (option.icon != null) {
                            Icon(
                                imageVector = option.icon,
                                contentDescription = option.title,
                                modifier = Modifier.size(iconSize),
                                tint = option.color
                            )
                        }
                        Spacer(modifier = Modifier.height(topSpacing))
                        Text(
                            text = option.title,
                            fontSize = fontSize,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface,
                            textAlign = TextAlign.Center
                        )
                    }

                    // Bottom 1/3: Colored Status Bar with Icon
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .background(statusBgColor),
                        contentAlignment = Alignment.Center
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center,
                            modifier = Modifier.padding(horizontal = 4.dp)
                        ) {
                            val statusIcon = when (statusText) {
                                "ABERTO" -> Icons.Default.PlayArrow
                                "INTERVALO" -> Icons.Default.Pause
                                "DESLOCAMENTO" -> Icons.Default.DirectionsCar
                                "FECHADO" -> Icons.Default.Stop
                                else -> Icons.Default.AccessTime
                            }

                            Icon(
                                imageVector = statusIcon,
                                contentDescription = null,
                                modifier = Modifier.size(if (isCompactHeight) 18.dp else 24.dp),
                                tint = Color.White
                            )
                            Spacer(modifier = Modifier.width(if (isCompactHeight) 6.dp else 9.dp))
                            Text(
                                text = statusText,
                                fontSize = if (isCompactHeight) 15.sp else 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color.White,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
            } else {
                // Default layout for other cards
                val currentIconSize = if (option.iconResId != null) {
                    cardHeight * 0.52f
                } else {
                    iconSize
                }

                val verticalPadding = if (option.iconResId != null) {
                    if (isCompactHeight) 4.dp else 8.dp
                } else {
                    12.dp
                }

                val itemSpacing = if (option.iconResId != null) 4.dp else 8.dp

                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp, vertical = verticalPadding),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    if (option.iconResId != null) {
                        Image(
                            painter = painterResource(id = option.iconResId),
                            contentDescription = option.title,
                            modifier = Modifier.size(currentIconSize),
                            contentScale = ContentScale.Fit
                        )
                    } else if (option.icon != null) {
                        Icon(
                            imageVector = option.icon,
                            contentDescription = option.title,
                            modifier = Modifier.size(currentIconSize),
                            tint = option.color
                        )
                    }
                    Spacer(modifier = Modifier.height(itemSpacing))
                    Text(
                        text = option.title,
                        fontSize = fontSize,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                        textAlign = TextAlign.Center,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (option.subtitle != null) {
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = option.subtitle,
                            fontSize = subtitleSize,
                            fontWeight = FontWeight.SemiBold,
                            color = option.subtitleColor ?: MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                            maxLines = subtitleMaxLines,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }
    }
}
