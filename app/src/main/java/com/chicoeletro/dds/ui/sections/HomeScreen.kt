package com.chicoeletro.dds.ui.sections

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.ui.platform.LocalContext
import android.widget.Toast
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.material.icons.automirrored.filled.Assignment
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
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
    onAbastecimentoClick: () -> Unit,
    teamType: String? = null,
    motorista: String? = null,
    coringas: List<String> = emptyList(),
    unreadIncomingCount: Int = 0
) {
    val (teamIcon: ImageVector?, teamIconResId: Int?, teamColor: Color) = when (teamType) {
        "STC" -> Triple(null, R.drawable.stc_small, Color(0xFF0288D1))
        "STC_CESTO" -> Triple(null, R.drawable.stc_cesto_small, Color(0xFF0288D1))
        "EP" -> Triple(null, R.drawable.ep_small, Color(0xFF00E676))
        "LINHA_VIVA" -> Triple(null, R.drawable.linha_viva_small, Color(0xFFFFD600))
        "ROCADA" -> Triple(null, R.drawable.rocada_small, Color(0xFF81C784))
        "CONSTRUCAO" -> Triple(null, R.drawable.construcao_small, Color(0xFFFF7043))
        else -> Triple(Icons.Default.People, null, Color(0xFF00ACC1))
    }

    val options = listOf(
        HomeOption("DDS", iconResId = R.drawable.dds, color = Color(0xFF2E7D32), onClick = onDdsClick),
        HomeOption(
            title = "TURNO",
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
        HomeOption("PRODUÇÃO", icon = Icons.Default.BarChart, color = Color(0xFFF57C00), onClick = onProducaoClick),
        HomeOption(
            title = "MINHAS MENSAGENS", 
            icon = Icons.AutoMirrored.Filled.Chat, 
            color = Color(0xFF7B1FA2), 
            onClick = onMensagensClick,
            subtitle = if (unreadIncomingCount > 0) "($unreadIncomingCount novas)" else "Sem mensagens novas",
            subtitleColor = if (unreadIncomingCount > 0) Color(0xFF7B1FA2) else null
        ),
        HomeOption(
            title = "ABASTECIMENTO", 
            icon = Icons.Default.LocalGasStation, 
            color = Color(0xFFD32F2F), 
            onClick = onAbastecimentoClick
        ),
        HomeOption(
            title = if (equipe.isNotBlank()) equipe.uppercase() else "DEFINIR EQUIPE",
            icon = teamIcon,
            iconResId = teamIconResId,
            color = teamColor,
            onClick = onClickEquipe,
            subtitle = if (eletricistas.isNotEmpty()) eletricistas.joinToString("\n") else null
        )
    )

    BoxWithConstraints(modifier = Modifier.fillMaxSize().background(Color(0xFFF5F7FA))) {
        val isCompactHeight = maxHeight < 550.dp
        val spacing = if (isCompactHeight) 8.dp else 16.dp
        val iconSize = if (isCompactHeight) 40.dp else 56.dp
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
                    val maxLines = if (option.title == equipe || option.title == "Equipe" || option.title == "Definir equipe") 10 else 1
                    Box(modifier = Modifier.weight(1f)) {
                        HomeCard(
                            option = option,
                            iconSize = iconSize,
                            fontSize = fontSize,
                            subtitleSize = subtitleSize,
                            subtitleMaxLines = maxLines,
                            isCompactHeight = isCompactHeight,
                            motorista = motorista,
                            coringas = coringas
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun HomeCard(
    option: HomeOption,
    iconSize: Dp,
    fontSize: TextUnit,
    subtitleSize: TextUnit,
    subtitleMaxLines: Int = 1,
    participationDays: List<MonthParticipationDay> = emptyList(),
    isCompactHeight: Boolean = false,
    motorista: String? = null,
    coringas: List<String> = emptyList()
) {
    val isDdsCard = option.title == "DDS" || option.title == "DIÁLOGO DIÁRIO DE SEGURANÇA" || option.title == "DISCUSSÃO DIÁRIA DE SEGURANÇA" || option.title == "LPI" || option.title == "KPI"
    val isTurnoCard = option.title == "Turno" || option.title == "ESTADO DO TURNO" || option.title == "TURNO"
    val context = LocalContext.current
    val isMensagensOrAbastecimento = option.title == "Mensagens" || option.title == "Abastecimento" || 
            option.title == "MINHAS MENSAGENS" || option.title == "HISTÓRICO DE ABASTECIMENTO"
    var showWarning by remember { mutableStateOf(false) }
    val coroutineScope = rememberCoroutineScope()

    Card(
        modifier = Modifier
            .fillMaxSize()
            .then(
                if (isMensagensOrAbastecimento) {
                    Modifier.combinedClickable(
                        onClick = {
                            Toast.makeText(context, "Esta funcionalidade ainda não está disponível", Toast.LENGTH_SHORT).show()
                            coroutineScope.launch {
                                showWarning = true
                                delay(3000)
                                showWarning = false
                            }
                        },
                        onDoubleClick = {
                            option.onClick()
                        }
                    )
                } else {
                    Modifier.clickable { option.onClick() }
                }
            ),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
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
                    Box(
                        modifier = Modifier
                            .weight(0.65f)
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

                    Column(
                        modifier = Modifier
                            .weight(0.35f)
                            .fillMaxWidth()
                            .padding(horizontal = 4.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(0.96f),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "Frequência: Semanal",
                                fontSize = subtitleSize,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        if (participationDays.isNotEmpty()) {
                            val daysToDisplay = participationDays
                            val sphereSize = if (isCompactHeight) 11.dp else 15.dp
                            val isSelectedSize = if (isCompactHeight) 15.dp else 17.dp
                            val dayFontSize = if (isCompactHeight) 7.sp else 8.sp

                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color(0xFFE5E7EB), RoundedCornerShape(20.dp))
                                    .padding(top = 8.dp, bottom = 5.dp, start = 12.dp, end = 12.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceEvenly,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    daysToDisplay.forEach { day ->
                                        val gradientColors = when {
                                            day.isPresent -> listOf(Color(0xFF6EE7B7), Color(0xFF10B981), Color(0xFF047857))
                                            day.isAbsent -> listOf(Color(0xFFFCA5A5), Color(0xFFEF4444), Color(0xFFB91C1C))
                                            day.hasTraining -> listOf(Color(0xFFFCD34D), Color(0xFFF59E0B), Color(0xFFB45309))
                                            else -> listOf(Color(0xFFCBD5E1), Color(0xFF64748B), Color(0xFF334155))
                                        }
                                        Column(
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.spacedBy(1.dp)
                                        ) {
                                            Box(
                                                modifier = Modifier
                                                    .size(if (day.isSelected) isSelectedSize else sphereSize)
                                                    .drawBehind {
                                                        val radius = size.minDimension / 2
                                                        val brush = Brush.radialGradient(
                                                            colors = gradientColors,
                                                            center = Offset(size.width * 0.3f, size.height * 0.3f),
                                                            radius = size.minDimension * 0.75f
                                                        )
                                                        drawCircle(
                                                            brush = brush,
                                                            radius = radius,
                                                            center = Offset(size.width / 2, size.height / 2)
                                                        )
                                                    }
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
                            Box(contentAlignment = Alignment.BottomEnd) {
                                Icon(
                                    imageVector = option.icon,
                                    contentDescription = option.title,
                                    modifier = Modifier.size(iconSize),
                                    tint = option.color
                                )
                                Icon(
                                    imageVector = Icons.Default.Settings,
                                    contentDescription = null,
                                    modifier = Modifier
                                        .size(iconSize * 0.45f)
                                        .offset(x = (iconSize * 0.1f), y = (iconSize * 0.1f))
                                        .background(MaterialTheme.colorScheme.surface, CircleShape)
                                        .padding(1.dp),
                                    tint = option.color
                                )
                            }
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
                    if (isMensagensOrAbastecimento && showWarning) {
                        Text(
                            text = "Essa funcionalidade ainda não foi liberada",
                            color = Color(0xFFD32F2F),
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(bottom = 2.dp)
                        )
                    }
                    if (option.iconResId != null) {
                        Image(
                            painter = painterResource(id = option.iconResId),
                            contentDescription = option.title,
                            modifier = Modifier.size(currentIconSize),
                            contentScale = ContentScale.Fit
                        )
                    } else if (option.icon != null) {
                        if (option.title == "DESEMPENHO DA PRODUÇÃO" || option.title == "Produção") {
                            Column(
                                modifier = Modifier.size(currentIconSize),
                                verticalArrangement = Arrangement.spacedBy(2.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterHorizontally)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.BarChart,
                                        contentDescription = null,
                                        modifier = Modifier.size(currentIconSize * 0.45f),
                                        tint = option.color
                                    )
                                    Icon(
                                        imageVector = Icons.Default.TrendingUp,
                                        contentDescription = null,
                                        modifier = Modifier.size(currentIconSize * 0.45f),
                                        tint = option.color
                                    )
                                }
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterHorizontally)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.PieChart,
                                        contentDescription = null,
                                        modifier = Modifier.size(currentIconSize * 0.45f),
                                        tint = option.color
                                    )
                                    Icon(
                                        imageVector = Icons.Default.Assessment,
                                        contentDescription = null,
                                        modifier = Modifier.size(currentIconSize * 0.45f),
                                        tint = option.color
                                    )
                                }
                            }
                        } else {
                            Icon(
                                imageVector = option.icon,
                                contentDescription = option.title,
                                modifier = Modifier.size(currentIconSize),
                                tint = option.color
                            )
                        }
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
                        val isTeamCard = option.title != "DDS" && option.title != "DIÁLOGO DIÁRIO DE SEGURANÇA" && 
                                option.title != "Turno" && option.title != "ESTADO DO TURNO" && 
                                option.title != "Produção" && option.title != "DESEMPENHO DA PRODUÇÃO" && 
                                option.title != "Mensagens" && option.title != "MINHAS MENSAGENS" && 
                                option.title != "Abastecimento" && option.title != "HISTÓRICO DE ABASTECIMENTO"
                        if (isTeamCard) {
                            val namesList = option.subtitle.split("\n")
                            Column(
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.spacedBy(2.dp)
                            ) {
                                namesList.forEach { fullName ->
                                    val cleanName = fullName.replace(" 🛞", "").replace(" 🔄", "").trim()
                                    val normName = cleanName.uppercase()
                                    val isDriver = normName == motorista?.trim()?.uppercase()
                                    val isWildcard = coringas.any { it.trim().uppercase() == normName }

                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.Center
                                    ) {
                                        Text(
                                            text = cleanName,
                                            fontSize = subtitleSize,
                                            fontWeight = FontWeight.SemiBold,
                                            color = option.subtitleColor ?: MaterialTheme.colorScheme.onSurfaceVariant,
                                            textAlign = TextAlign.Center
                                        )
                                        if (isDriver) {
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Icon(
                                                painter = painterResource(id = R.drawable.ic_steering_wheel),
                                                contentDescription = "Motorista",
                                                tint = MaterialTheme.colorScheme.primary,
                                                modifier = Modifier.size(13.dp)
                                            )
                                        }
                                        if (isWildcard) {
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Icon(
                                                painter = painterResource(id = R.drawable.ic_wildcard),
                                                contentDescription = "Coringa",
                                                tint = Color.Unspecified,
                                                modifier = Modifier.size(13.dp)
                                            )
                                        }
                                    }
                                }
                            }
                        } else {
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
}
