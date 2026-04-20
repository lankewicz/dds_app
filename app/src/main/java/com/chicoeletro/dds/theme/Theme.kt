// Módulo: app/src/main/java/com/chicoeletro/dds/theme/Theme.kt
// Função: Definição de cores, tipografia e tema visual do app (Material 3).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    // Cores específicas para o tema Noturno (Dark)
    primary = PrimaryDark,
    secondary = SecondaryDark,
    tertiary = Pink80, // Mantém Pink80 se não houver um terciário definido
    background = BackgroundDark,
    surface = SurfaceDark,
    onPrimary = Color.Black, // Texto na cor primária
    onSecondary = Color.Black,
    onBackground = OnSurfaceDark,
    onSurface = OnSurfaceDark,
)

private val LightColorScheme = lightColorScheme(
    // Cores específicas para o tema Diurno (Light)
    primary = PrimaryLight,
    secondary = SecondaryLight,
    tertiary = Pink40, // Mantém Pink40 se não houver um terciário definido
    background = BackgroundLight,
    surface = SurfaceLight,
    onPrimary = Color.White, // Texto na cor primária
    onSecondary = Color.Black,
    onBackground = OnSurfaceLight,
    onSurface = OnSurfaceLight,
)

@Composable
fun DDSTheme(
    // isSystemInDarkTheme() decide automaticamente se o sistema está no modo escuro
    darkTheme: Boolean = isSystemInDarkTheme(),
    // Dynamic color é a cor baseada no wallpaper (Android 12+)
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        // Se a cor dinâmica estiver ativada E o Android for 12+
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        // Caso contrário, usa os esquemas estáticos que definimos acima
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}