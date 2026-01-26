// Módulo: app/src/main/java/com/example/dds/components/HeaderBar.kt
// Função: Exibe o cabeçalho com logo, título do DDS e texto institucional
// Autor: Valdinei Lankewicz
// Criado em: 28/05/2025
// Histórico de alterações:
// - 01/07/2025: Melhorado layout para evitar que o texto "Diálogo Diário de Segurança" quebre em telas pequenas
//               Substituída a Column por Text único com \n e limitado por largura e número de linhas
//               Adicionada altura mínima/máxima no logo para melhor responsividade

package com.chicoeletro.dds.components

// --- Android SDK
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape

// --- Jetpack Compose
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.*

import androidx.compose.material3.Icon
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.foundation.shape.CircleShape









// --- Projeto
import com.chicoeletro.dds.R



// Estado global para compartilhar partes do título entre módulos
object HeaderBarState {
    var datePart: String = ""
    var titlePart: String = ""
}

@Composable
fun HeaderBar(
    overlayAlpha: Float,
    selectedTraining: String?,
    showTestCameraButton: Boolean = false,
    onTestCameraClick: (() -> Unit)? = null
) {
    // Valor bruto recebido (pode ser "yyyy-MM-dd - Título")
    val raw = selectedTraining.orEmpty()

    // Extrai a parte da data antes do separador ' - '
    val date = raw.substringBefore(" -").trim()

    // Extrai apenas o texto após a data e separador ' - '
    val title = raw.substringAfter("- ")
        .trim()
        .takeUnless { it.isBlank() }
        ?: "DDS"

    // Armazena no objeto de estado para outros módulos
    HeaderBarState.datePart = date
    HeaderBarState.titlePart = title

    Row(
        modifier = Modifier
            .fillMaxWidth()
            // Antes: .heightIn(min = 64.dp, max = 100.dp)
            .heightIn(min = 52.dp, max = 72.dp)   // faixa mais baixa
            .background(Color.LightGray)
            // Antes: .padding(horizontal = 12.dp, vertical = 8.dp)
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .alpha(overlayAlpha),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Logo da empresa com tamanho ajustável
        Image(
            painter = painterResource(id = R.drawable.logo_chico),
            contentDescription = "Logo Chico Eletro",
            modifier = Modifier
                // Antes: .heightIn(min = 48.dp, max = 64.dp)
                .heightIn(min = 36.dp, max = 48.dp)
                .padding(end = 8.dp)
        )

        // Título central (parte do nome do DDS)
        Text(
            text = title,
            // Antes: typography.headlineMedium (mais alto)
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.weight(1f),
            maxLines = 2,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            overflow = TextOverflow.Ellipsis
        )

        /// Area da Direita
        if (showTestCameraButton && onTestCameraClick != null) {
            androidx.compose.material3.IconButton(
                onClick = onTestCameraClick,
                modifier = Modifier
                    .size(40.dp)
                    .background(Color.DarkGray, CircleShape)
            ) {
                Icon(
                    imageVector = Icons.Filled.Videocam,
                    contentDescription = "Teste reunião online",
                    tint = Color.White
                )
            }
        }

        Column(
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            // 👉 Lado direito: texto DDS + botão de câmera
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Column(
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                    horizontalAlignment = Alignment.End
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("   Diálogo Diário", fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("   de Segurança", fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                }


            }
        }
    }
}
