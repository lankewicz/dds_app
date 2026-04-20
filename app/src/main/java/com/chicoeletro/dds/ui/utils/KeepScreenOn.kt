// Módulo: app/src/main/java/com/chicoeletro/dds/ui/utils/KeepScreenOn.kt
// Função: Utilitário para controle de energia da tela. Manipula as flags da janela do Android 
//         para garantir que o display permaneça ativo durante a interação com o app.
// Tecnologias: Android Window Flags, Jetpack Compose Side-Effects.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

/*
 * Arquivo: KeepScreenOn.kt
 * Módulo: ui/utils
 * Projeto: DDS – Diálogo Diário de Segurança
 *
 * Descrição:
 * Composable utilitário responsável por manter a tela do dispositivo ligada
 * enquanto a tela associada estiver em primeiro plano.
 *
 * Implementação baseada em boas práticas do Android, utilizando
 * WindowManager.FLAG_KEEP_SCREEN_ON em conjunto com DisposableEffect,
 * garantindo ativação e liberação automáticas conforme o ciclo de vida
 * do Composable.
 *
 * Autor: Valdinei Lankewicz
 * Empresa: Chico Eletro Instaladora
 *
 * Data de criação: 26/12/2025
 *
 * Histórico de alterações:
 * - 26/12/2025: Criação inicial do helper KeepScreenOn para Jetpack Compose.
 * - 26/12/2025: Correção para suportar ContextWrapper e garantir Activity real.
 */

package com.chicoeletro.dds.ui.utils

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalContext

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

@Composable
fun KeepScreenOn(enabled: Boolean = true) {
    val context = LocalContext.current
    val activity = context.findActivity() ?: return

    DisposableEffect(enabled) {
        if (enabled) {
            activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }

        onDispose {
            // Ao sair da tela, sempre libera para não “vazar” o estado
            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
}