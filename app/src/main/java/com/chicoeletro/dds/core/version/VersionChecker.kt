// Módulo: app/src/main/java/com/chicoeletro/dds/core/version/VersionChecker.kt
// Função: Componente de verificação de atualizações. Utiliza a Google Play In-App Updates API 
//         para sinalizar novas builds disponíveis e identificar versões de desenvolvimento.
// Tecnologias: Google Play Core (In-App Updates), Android ApplicationInfo.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 04/07/2025: Criação inicial.
//   - 15/07/2025: Adicionada verificação de permissão e lógica de FileProvider.
package com.chicoeletro.dds.core.version

import android.app.Activity
import android.content.Context
import com.google.android.play.core.appupdate.AppUpdateManagerFactory
import com.google.android.play.core.install.model.AppUpdateType
import com.google.android.play.core.install.model.UpdateAvailability

enum class VersionStatus {
    UPDATE_AVAILABLE,
    UP_TO_DATE,
    TEST_VERSION,
    ERROR
}

object VersionChecker {

    /**
     * Verifica o status da versão via Google Play In-App Updates.
     */
    fun checkPlayStoreStatus(context: Context, onResult: (VersionStatus) -> Unit) {
        val appUpdateManager = AppUpdateManagerFactory.create(context)
        val appUpdateInfoTask = appUpdateManager.appUpdateInfo

        appUpdateInfoTask.addOnSuccessListener { appUpdateInfo ->
            when (appUpdateInfo.updateAvailability()) {
                UpdateAvailability.UPDATE_AVAILABLE -> {
                    onResult(VersionStatus.UPDATE_AVAILABLE)
                }
                UpdateAvailability.UPDATE_NOT_AVAILABLE -> {
                    // Heurística para Versão de Teste: 
                    // Se não há atualização disponível mas estamos em modo Debug ou 
                    // se o versionCode local for "muito novo" (AAMMDDHH).
                    // Para simplificar, verificamos se é uma build de debug (local).
                    val isDebug = (context.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
                    if (isDebug) {
                        onResult(VersionStatus.TEST_VERSION)
                    } else {
                        onResult(VersionStatus.UP_TO_DATE)
                    }
                }
                else -> onResult(VersionStatus.UP_TO_DATE)
            }
        }.addOnFailureListener {
            onResult(VersionStatus.ERROR)
        }
    }

    /**
     * Inicia o fluxo de atualização flexível da Play Store.
     * Deve ser chamado de uma Activity.
     */
    fun startUpdateFlow(activity: Activity, requestCode: Int) {
        val appUpdateManager = AppUpdateManagerFactory.create(activity)
        appUpdateManager.appUpdateInfo.addOnSuccessListener { appUpdateInfo ->
            if (appUpdateInfo.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE) {
                appUpdateManager.startUpdateFlowForResult(
                    appUpdateInfo,
                    AppUpdateType.FLEXIBLE,
                    activity,
                    requestCode
                )
            }
        }
    }
}