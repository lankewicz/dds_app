// Módulo: app/src/main/java/com/chicoeletro/dds/core/crash/CrashReportManager.kt
// Função: Gerenciador de leitura, limpeza, cópia para área de transferência
//         e envio remoto para o Firestore dos relatórios de fechamento anormal.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.core.crash

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.util.Log
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import org.json.JSONObject
import java.io.File

object CrashReportManager {

    fun getPendingCrashReport(context: Context): CrashReport? {
        return try {
            val file = File(context.filesDir, CrashHandler.CRASH_REPORT_FILENAME)
            if (!file.exists()) return null
            val content = file.readText()
            if (content.isBlank()) return null

            val json = JSONObject(content)
            CrashReport(
                timestamp = json.optString("timestamp", ""),
                timestampMs = json.optLong("timestampMs", 0L),
                exceptionType = json.optString("exceptionType", "UnknownException"),
                message = json.optString("message", ""),
                stackTrace = json.optString("stackTrace", ""),
                threadName = json.optString("threadName", "main"),
                deviceManufacturer = json.optString("deviceManufacturer", ""),
                deviceModel = json.optString("deviceModel", ""),
                androidVersion = json.optString("androidVersion", ""),
                sdkVersion = json.optInt("sdkVersion", 0),
                appVersionName = json.optString("appVersionName", "1.0.0"),
                appVersionCode = json.optLong("appVersionCode", 1L)
            )
        } catch (e: Exception) {
            Log.e("CrashReportManager", "Erro ao ler relatório de crash", e)
            null
        }
    }

    fun clearCrashReport(context: Context) {
        try {
            val file = File(context.filesDir, CrashHandler.CRASH_REPORT_FILENAME)
            if (file.exists()) {
                file.delete()
                Log.i("CrashReportManager", "Relatório de crash limpo com sucesso.")
            }
        } catch (e: Exception) {
            Log.e("CrashReportManager", "Erro ao limpar arquivo de crash", e)
        }
    }

    fun copyToClipboard(context: Context, report: CrashReport): Boolean {
        return try {
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("DDS Crash Report", report.toFormattedText())
            clipboard.setPrimaryClip(clip)
            true
        } catch (e: Exception) {
            Log.e("CrashReportManager", "Erro ao copiar crash para o clipboard", e)
            false
        }
    }

    fun sendToFirestore(
        context: Context,
        report: CrashReport,
        onComplete: (Boolean) -> Unit
    ) {
        try {
            val db = FirebaseFirestore.getInstance()
            val docData = hashMapOf(
                "timestamp" to report.timestamp,
                "timestampMs" to report.timestampMs,
                "serverReceivedAt" to FieldValue.serverTimestamp(),
                "exceptionType" to report.exceptionType,
                "message" to report.message,
                "stackTrace" to report.stackTrace,
                "threadName" to report.threadName,
                "device" to "${report.deviceManufacturer} ${report.deviceModel}",
                "androidVersion" to report.androidVersion,
                "sdkVersion" to report.sdkVersion,
                "appVersion" to "${report.appVersionName} (${report.appVersionCode})"
            )

            db.collection("monitor_crash_reports")
                .add(docData)
                .addOnSuccessListener {
                    Log.i("CrashReportManager", "Relatório de crash enviado ao Firestore com sucesso ID: ${it.id}")
                    onComplete(true)
                }
                .addOnFailureListener { e ->
                    Log.e("CrashReportManager", "Falha ao enviar crash report ao Firestore", e)
                    onComplete(false)
                }
        } catch (e: Exception) {
            Log.e("CrashReportManager", "Exceção ao tentar enviar para Firestore", e)
            onComplete(false)
        }
    }
}
