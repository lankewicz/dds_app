// Módulo: app/src/main/java/com/chicoeletro/dds/core/crash/CrashHandler.kt
// Função: Capturador global de exceções não tratadas (Crash Shield). 
//         Salva dados completos do erro, dispositivo e stacktrace em arquivo local
//         para exibição de relatório no próximo acesso do aplicativo.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.core.crash

import android.content.Context
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class CrashReport(
    val timestamp: String,
    val timestampMs: Long,
    val exceptionType: String,
    val message: String,
    val stackTrace: String,
    val threadName: String,
    val deviceManufacturer: String,
    val deviceModel: String,
    val androidVersion: String,
    val sdkVersion: Int,
    val appVersionName: String,
    val appVersionCode: Long
) {
    fun toFormattedText(): String {
        return """
            ⚠️ DDS APP - RELATÓRIO DE FECHAMENTO ANORMAL
            --------------------------------------------------
            📅 Data/Hora: $timestamp
            📱 Dispositivo: $deviceManufacturer $deviceModel (Android $androidVersion / SDK $sdkVersion)
            📦 Versão do App: $appVersionName ($appVersionCode)
            🧵 Thread: $threadName
            ❌ Erro: $exceptionType
            💬 Mensagem: $message
            
            🔍 PILHA DE EXECUÇÃO (STACKTRACE):
            $stackTrace
            --------------------------------------------------
        """.trimIndent()
    }
}

class CrashHandler private constructor(
    private val context: Context,
    private val defaultHandler: Thread.UncaughtExceptionHandler?
) : Thread.UncaughtExceptionHandler {

    override fun uncaughtException(thread: Thread, throwable: Throwable) {
        try {
            Log.e("CrashHandler", "Fechamento anormal capturado na thread: ${thread.name}", throwable)
            saveCrashReport(thread, throwable)
        } catch (e: Exception) {
            Log.e("CrashHandler", "Erro ao salvar relatório de crash", e)
        } finally {
            // Delega para o handler original do Android para encerrar o processo suavemente
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    private fun saveCrashReport(thread: Thread, throwable: Throwable) {
        val sw = StringWriter()
        throwable.printStackTrace(PrintWriter(sw))
        val fullStackTrace = sw.toString()

        val sdf = SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale.getDefault())
        val nowMs = System.currentTimeMillis()
        val nowStr = sdf.format(Date(nowMs))

        val appVersionName = try {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "1.0.0"
        } catch (_: Exception) { "1.0.0" }

        val appVersionCode = try {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageInfo(context.packageName, 0).versionCode.toLong()
        } catch (_: Exception) { 1L }

        val json = JSONObject().apply {
            put("timestamp", nowStr)
            put("timestampMs", nowMs)
            put("exceptionType", throwable.javaClass.name)
            put("message", throwable.message ?: "Sem mensagem detalhada")
            put("stackTrace", fullStackTrace)
            put("threadName", thread.name)
            put("deviceManufacturer", Build.MANUFACTURER)
            put("deviceModel", Build.MODEL)
            put("androidVersion", Build.VERSION.RELEASE)
            put("sdkVersion", Build.VERSION.SDK_INT)
            put("appVersionName", appVersionName)
            put("appVersionCode", appVersionCode)
        }

        val file = File(context.filesDir, CRASH_REPORT_FILENAME)
        file.writeText(json.toString(2))
        Log.i("CrashHandler", "Relatório de crash salvo em: ${file.absolutePath}")
    }

    companion object {
        const val CRASH_REPORT_FILENAME = "last_crash_report.json"

        fun install(context: Context) {
            val currentHandler = Thread.getDefaultUncaughtExceptionHandler()
            if (currentHandler !is CrashHandler) {
                val customHandler = CrashHandler(context.applicationContext, currentHandler)
                Thread.setDefaultUncaughtExceptionHandler(customHandler)
                Log.i("CrashHandler", "Crash Shield instalado com sucesso.")
            }
        }
    }
}
