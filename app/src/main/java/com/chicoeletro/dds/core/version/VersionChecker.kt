/**
 * -----------------------------------------------------------------------------
 * Módulo: core.version.VersionChecker.kt
 * -----------------------------------------------------------------------------
 * Função: Verifica se existe uma versão mais recente do app no Firebase Storage.
 * Se houver, solicita permissão, baixa o APK e inicia a instalação.
 *
 * Autor: Valdinei Lankewicz (Revisado por Gemini)
 * Data de criação: 04/07/2025
 *
 * Histórico de alterações:
 * - 15/07/2025: (Gemini) Adicionada verificação de permissão para instalar pacotes (Android 8+).
 * - 15/07/2025: (Gemini) Implementado FileProvider para compatibilidade e segurança (Android 7+).
 * - 15/07/2025: (Gemini) Melhorada a lógica de comparação de versões para tratar números corretamente.
 * - 15/07/2025: (Gemini) Refatorado o BroadcastReceiver para ser mais seguro e específico.
 * - 04/07/2025: Leitura automática da versão atual (PackageManager)
 * - 04/07/2025: Compatível com Android 10+ usando getExternalFilesDir()
 * -----------------------------------------------------------------------------
 */
package core.version

import android.app.*
import android.content.*
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
import androidx.core.content.FileProvider
import com.google.firebase.storage.FirebaseStorage
import org.json.JSONObject
import java.io.File

object VersionChecker {

    private const val ARQUIVO_VERSAO = "apks/versao.json"
    private const val NOME_APK_ATUALIZACAO = "dds_atualizacao.apk"

    fun checarVersao(context: Context) {
        val versaoAtual = obterVersaoAtual(context)
        val storage = FirebaseStorage.getInstance()
        val arquivoRef = storage.getReference(ARQUIVO_VERSAO)

        arquivoRef.getBytes(1024 * 1024)
            .addOnSuccessListener { bytes ->
                try {
                    val json = String(bytes)
                    val jsonObject = JSONObject(json)
                    val versaoRemota = jsonObject.getString("versao")
                    val urlApk = jsonObject.getString("url_apk")

                    if (isNewerVersionAvailable(remota = versaoRemota, atual = versaoAtual)) {
                        mostrarDialogAtualizacao(context, urlApk)
                    } else {
                        Toast.makeText(context, "Você já está com a versão mais recente.", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    Toast.makeText(context, "Erro ao processar dados da versão.", Toast.LENGTH_SHORT).show()
                }
            }
            .addOnFailureListener {
                Toast.makeText(context, "Erro ao verificar atualização.", Toast.LENGTH_SHORT).show()
            }
    }

    private fun isNewerVersionAvailable(remota: String, atual: String): Boolean {
        try {
            val vRemota = remota.split(".").map { it.toInt() }
            val vAtual = atual.split(".").map { it.toInt() }
            val maxLen = maxOf(vRemota.size, vAtual.size)

            for (i in 0 until maxLen) {
                val partRemota = vRemota.getOrElse(i) { 0 }
                val partAtual = vAtual.getOrElse(i) { 0 }
                if (partRemota > partAtual) return true
                if (partRemota < partAtual) return false
            }
        } catch (e: NumberFormatException) {
            return false // Em caso de formato de versão inválido, não atualiza.
        }
        return false // Versões são iguais
    }

    private fun obterVersaoAtual(context: Context): String {
        return try {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "0.0.0"
        } catch (e: Exception) {
            "0.0.0"
        }
    }

    private fun mostrarDialogAtualizacao(context: Context, urlApk: String) {
        AlertDialog.Builder(context)
            .setTitle("Atualização disponível")
            .setMessage("Uma nova versão do aplicativo está disponível. Deseja atualizar agora?")
            .setPositiveButton("Atualizar") { _, _ ->
                verificarPermissaoEBaixar(context, urlApk)
            }
            .setNegativeButton("Mais tarde", null)
            .setCancelable(false)
            .show()
    }

    private fun verificarPermissaoEBaixar(context: Context, urlApk: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!context.packageManager.canRequestPackageInstalls()) {
                // Permissão não concedida, guia o usuário para as configurações
                AlertDialog.Builder(context)
                    .setTitle("Permissão Necessária")
                    .setMessage("Para instalar a atualização, você precisa permitir que este app instale pacotes. Você será levado para as configurações para habilitar esta permissão.")
                    .setPositiveButton("Configurações") { _, _ ->
                        val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                        intent.data = Uri.parse("package:${context.packageName}")
                        context.startActivity(intent)
                    }
                    .setNegativeButton("Cancelar", null)
                    .show()
                return // Para aqui e aguarda o usuário conceder a permissão e tentar novamente.
            }
        }
        // Se a permissão for concedida ou não for necessária, inicia o download.
        baixarEInstalarApk(context, urlApk)
    }

    private fun baixarEInstalarApk(context: Context, urlApk: String) {
        val apkFile = File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), NOME_APK_ATUALIZACAO)

        val request = DownloadManager.Request(Uri.parse(urlApk))
            .setTitle("Atualizando DDS")
            .setDescription("Baixando nova versão...")
            .setDestinationUri(Uri.fromFile(apkFile))
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setAllowedOverMetered(true) // Permite download em redes móveis

        val manager = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val downloadId = manager.enqueue(request)

        Toast.makeText(context, "Baixando atualização...", Toast.LENGTH_LONG).show()

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                val id = intent?.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1)
                if (id == downloadId) { // Confirma que é o nosso download
                    if (apkFile.exists()) {
                        Toast.makeText(context, "Download concluído. Instalando...", Toast.LENGTH_SHORT).show()
                        instalarApk(context, apkFile)
                    } else {
                        Toast.makeText(context, "Erro no download. O arquivo não foi encontrado.", Toast.LENGTH_LONG).show()
                    }
                    // Desregistra o receiver para evitar vazamento de memória
                    context.unregisterReceiver(this)
                }
            }
        }
        context.registerReceiver(receiver, IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE))
    }

    private fun instalarApk(context: Context, apkFile: File) {
        val authority = "${context.packageName}.provider"
        val uri = FileProvider.getUriForFile(context, authority, apkFile)

        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            context.startActivity(intent)
            // Fecha o app para permitir que a atualização ocorra sem problemas
            (context as? Activity)?.finishAffinity()
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(context, "Não foi possível encontrar um instalador de pacotes.", Toast.LENGTH_LONG).show()
        }
    }
}
