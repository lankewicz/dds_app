// Módulo: app/src/main/java/com/chicoeletro/dds/features/auth/FirstAccessScreen.kt
// Função: Interface de configuração inicial (Onboarding). Permite ao usuário definir nome da 
//         equipe e membros no primeiro uso do aplicativo.
// Tecnologias: Jetpack Compose, Material3, DataStore Integration.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.auth

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import java.time.ZoneId
import java.time.ZonedDateTime
import kotlin.random.Random

@Composable
fun FirstAccessScreen(
    onUnlocked: () -> Unit
) {
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }
    val scrollState = rememberScrollState()

    val currentDay = remember {
        ZonedDateTime.now(ZoneId.of("America/Sao_Paulo")).dayOfMonth
    }
    var optionsSeed by remember { mutableIntStateOf(0) }

    val options = remember(currentDay, optionsSeed) {
        buildFirstAccessOptions(currentDay)
            .map { it.toString().padStart(2, '0') }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
        containerColor = Color(0xFF0F1115)
    ) { padding ->
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xFF0F1115))
                .padding(padding),
            contentAlignment = Alignment.TopCenter
        ) {
            val isCompactWidth = maxWidth < 600.dp
            val contentHorizontalPadding = if (isCompactWidth) 16.dp else 24.dp
            val iconBoxSize = if (isCompactWidth) 64.dp else 72.dp
            val iconSize = if (isCompactWidth) 30.dp else 34.dp
            val cardWidth = if (isCompactWidth) 108.dp else 160.dp
            val cardHeight = if (isCompactWidth) 104.dp else 150.dp
            val cardSpacing = if (isCompactWidth) 12.dp else 18.dp

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(scrollState)
                    .widthIn(max = 920.dp)
                    .padding(horizontal = contentHorizontalPadding, vertical = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Spacer(modifier = Modifier.height(8.dp))

                Box(
                    modifier = Modifier
                        .size(iconBoxSize)
                        .background(
                            color = Color(0xFF1C2028),
                            shape = RoundedCornerShape(24.dp)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Outlined.Lock,
                        contentDescription = "Liberação",
                        tint = Color(0xFFE8EAED),
                        modifier = Modifier.size(iconSize)
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))

                Text(
                    text = "Liberação do Dispositivo",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    textAlign = TextAlign.Center
                )

                Spacer(modifier = Modifier.height(16.dp))

                Text(
                    text = "O DDS é um programa exclusivo da Chico Eletro, destinado ao uso de funcionários autorizados.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = Color(0xFFD0D4DB),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(10.dp))

                Text(
                    text = "Para solicitar a senha de primeiro acesso, entre em contato com o Rotalog da empresa pelo telefone (55) 46 9925-0836.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color(0xFFB0B7C3),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(28.dp))

                Text(
                    text = "Selecione a senha informada:",
                    style = MaterialTheme.typography.titleMedium,
                    color = Color.White
                )

                Spacer(modifier = Modifier.height(20.dp))

                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalArrangement = Arrangement.spacedBy(cardSpacing),
                    maxItemsInEachRow = if (isCompactWidth) 2 else 3
                ) {
                    options.forEach { value ->
                        PasswordOptionCard(
                            value = value,
                            cardWidth = cardWidth,
                            cardHeight = cardHeight,
                            onClick = {
                                val selected = value.toIntOrNull() ?: -1
                                if (selected == currentDay) {
                                    onUnlocked()
                                } else {
                                    optionsSeed++
                                }
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(28.dp))

                Button(
                    onClick = {
                        openDialer(phone = "554699250836", context = context)
                    }
                ) {
                    Text("Entrar em contato com o Rotalog")
                }

                Spacer(modifier = Modifier.height(12.dp))

                Text(
                    text = "Após a liberação neste dispositivo, esta tela não será exibida novamente.",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF8E96A3),
                    textAlign = TextAlign.Center
                )

                Spacer(modifier = Modifier.height(20.dp))
            }
        }
    }

    LaunchedEffect(Unit) {
        snackbarHostState.currentSnackbarData?.dismiss()
    }
}

@Composable
private fun PasswordOptionCard(
    value: String,
    cardWidth: Dp,
    cardHeight: Dp,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .size(width = cardWidth, height = cardHeight)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF262A33)
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
    ) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = value,
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFE8EAED)
            )
        }
    }
}

private fun buildFirstAccessOptions(currentDay: Int): List<Int> {
    val values = linkedSetOf<Int>()
    values += currentDay

    while (values.size < 3) {
        val candidate = Random.nextInt(from = 1, until = 61)
        values += candidate
    }

    return values.shuffled()
}

private fun openDialer(phone: String, context: android.content.Context) {
    val intent = Intent(Intent.ACTION_DIAL).apply {
        data = Uri.parse("tel:$phone")
    }
    context.startActivity(intent)
}