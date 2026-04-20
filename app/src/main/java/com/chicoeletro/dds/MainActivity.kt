// Módulo: app/src/main/java/com/chicoeletro/dds/MainActivity.kt
// Função: Ponto de entrada (Activity principal). Gerencia permissões críticas (Câmera/Áudio), 
//         autenticação básica e orquestra o fluxo de navegação root com Compose. 
// Tecnologias: Jetpack Compose, Firebase Auth, Android Permissions API, ViewModel.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds

import android.Manifest
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModelProvider
import com.chicoeletro.dds.features.auth.FirstAccessGate
import com.chicoeletro.dds.storage.TrainingDataStore
import com.chicoeletro.dds.ui.sections.MainLayoutContainer
import com.chicoeletro.dds.ui.theme.DDSTheme
import com.chicoeletro.dds.viewmodel.TrainingSyncViewModel
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val syncVM = ViewModelProvider(this)[TrainingSyncViewModel::class.java]

        ensureAuthenticated()

        // UI
        setContent {
            DDSTheme {
                FirstAccessGate {
                    PermissionsGate(
                        onReady = {
                            MainLayoutContainer()
                        }
                    )
                }
            }
        }

        // Sync no startup
        syncVM.startupSyncIfNeeded(hasInternet())

        // Agenda envio de DDS pendentes (se houver) quando houver internet
        com.chicoeletro.dds.sync.DdsSyncScheduler(
            context = this,
            collectionName = "DDS",
            pastaFotos = "DDS_Fotos"
        ).schedule()

        // Se você também usa modo teste em runtime, pode agendar os dois:
        com.chicoeletro.dds.sync.DdsSyncScheduler(
            context = this,
            collectionName = "TESTE_DDS",
            pastaFotos = "TESTE_DDS_Fotos"
        ).schedule()
    }

    /**
     * Garante que sempre exista um usuário Firebase válido.
     *
     * - Se já houver usuário autenticado (Google ou anônimo), mantém.
     * - Se não houver, cria sessão anônima automaticamente.
     *
     * IMPORTANTE:
     * Este comportamento preserva o fluxo atual do app
     * e permite upgrade futuro (link anônimo → Google)
     * sem trocar UID nem quebrar relatórios existentes.
     */
    private fun ensureAuthenticated() {
        val auth = FirebaseAuth.getInstance()

        val currentUser: FirebaseUser? = auth.currentUser
        if (currentUser != null) {
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            auth.signInAnonymously()
                .addOnFailureListener { e ->
                    // Log apenas; não interrompe o app
                    android.util.Log.e(
                        "AUTH",
                        "Falha ao criar sessão anônima",
                        e
                    )
                }
        }
    }

    /** Verifica conectividade VALIDADA. */
    private fun hasInternet(): Boolean = try {
        val cm = ContextCompat.getSystemService(this, ConnectivityManager::class.java) ?: return false
        val nw = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(nw) ?: return false
        caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    } catch (_: Exception) {
        false
    }
}

@Composable
private fun PermissionsGate(
    onReady: @Composable () -> Unit
) {
    val context = LocalContext.current

    val onboardingDone by TrainingDataStore
        .getPermissionsOnboardingDone(context)
        .collectAsState(initial = false)

    val cameraGranted = remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                    PackageManager.PERMISSION_GRANTED
        )
    }
    val audioGranted = remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                    PackageManager.PERMISSION_GRANTED
        )
    }

    val allGranted = cameraGranted.value && audioGranted.value

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        cameraGranted.value = results[Manifest.permission.CAMERA] == true
        audioGranted.value = results[Manifest.permission.RECORD_AUDIO] == true
    }

    // Se já estiver tudo concedido, marca onboarding como feito e segue.
    LaunchedEffect(allGranted, onboardingDone) {
        if (allGranted && !onboardingDone) {
            TrainingDataStore.setPermissionsOnboardingDone(context, true)
        }
    }

    when {
        allGranted -> onReady()

        // Primeiro acesso (ou ainda não concluiu onboarding)
        !onboardingDone -> PermissionsOnboardingScreen(
            onGrant = {
                launcher.launch(
                    arrayOf(
                        Manifest.permission.CAMERA,
                        Manifest.permission.RECORD_AUDIO
                    )
                )
            },
            onSkip = {
                // Se quiser forçar, remova o "Pular".
                // Mantive para não travar o app: mas o DDS Online/câmera não funcionarão sem permissão.
                CoroutineScope(Dispatchers.IO).launch {
                    TrainingDataStore.setPermissionsOnboardingDone(context, true)
                }
            }
        )

        // Onboarding já rodou, mas usuário negou permissões (ou revogou nas configs)
        else -> PermissionsDeniedScreen(
            onTryAgain = {
                launcher.launch(
                    arrayOf(
                        Manifest.permission.CAMERA,
                        Manifest.permission.RECORD_AUDIO
                    )
                )
            }
        )
    }
}

@Composable
private fun PermissionsOnboardingScreen(
    onGrant: () -> Unit,
    onSkip: () -> Unit
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.Start
        ) {
            Text("Permissões necessárias", style = MaterialTheme.typography.titleLarge)
            Text(
                "Para usar as funcionalidades de foto e reunião online (Agora), o DDS precisa de acesso à câmera e ao microfone."
            )

            Spacer(Modifier.height(8.dp))

            Button(onClick = onGrant) {
                Text("Conceder permissões")
            }
            OutlinedButton(onClick = onSkip) {
                Text("Pular por enquanto")
            }

            Text(
                "Observação: sem essas permissões, a câmera e o DDS Online não funcionarão.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun PermissionsDeniedScreen(
    onTryAgain: () -> Unit
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.Start
        ) {
            Text("Permissões não concedidas", style = MaterialTheme.typography.titleLarge)
            Text("Sem câmera e microfone, os recursos de foto e reunião online não estarão disponíveis.")
            Button(onClick = onTryAgain) {
                Text("Tentar novamente")
            }
        }
    }
}