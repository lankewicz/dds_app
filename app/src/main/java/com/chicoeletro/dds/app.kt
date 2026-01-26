// Módulo: app/src/main/java/com/chicoeletro/dds/App.kt
// Estratégia: OFFLINE-FIRST – inicializa Firebase, faz auth anônima e cancela Work legado.
// (App Check removido para evitar dependências ausentes)

package com.chicoeletro.dds

import android.app.Application
import android.content.Context
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.auth.auth
import com.google.firebase.Firebase
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch



class App : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()

        // 1) Firebase
        FirebaseApp.initializeApp(this)

        // 2) Auth anônima (necessária para Storage/Firestore)
        Firebase.auth.signInAnonymously()
            .addOnSuccessListener { Log.d("DDS", "Auth anônima OK: uid=${it.user?.uid}") }
            .addOnFailureListener { e -> Log.e("DDS", "Auth anônima falhou", e) }

        // 3) Preparos leves em background
        appScope.launch {
            garantirPastaTreinamentos()
            limparCacheAntigo(this@App)
        }
    }

    private fun garantirPastaTreinamentos() {
        val dir = File(filesDir, "trainings")
        if (!dir.exists()) dir.mkdirs()
    }

    private fun limparCacheAntigo(context: Context, dias: Int = 7) {
        val limite = System.currentTimeMillis() - dias * 24 * 60 * 60 * 1000L
        val cacheDir = File(context.cacheDir, "image_cache")
        if (!cacheDir.exists()) return
        cacheDir.listFiles()?.forEach { file ->
            runCatching { if (file.lastModified() < limite) file.delete() }
        }
    }
}
