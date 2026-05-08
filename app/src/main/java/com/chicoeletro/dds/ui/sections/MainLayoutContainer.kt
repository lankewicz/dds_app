// Módulo: app/src/main/java/com/chicoeletro/dds/ui/sections/MainLayoutContainer.kt
// Função: Container principal da interface. Organiza a estrutura de navegação, barras latrais 
//         e a área de conteúdo dinâmico utilizando uma arquitetura baseada em Scaffold.
// Tecnologias: Jetpack Compose, Material3, Scaffold.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.ui.sections

import android.app.Application
import android.util.Log
import android.widget.Toast
import android.os.Build
import android.net.Uri
import android.provider.Settings
import android.provider.Settings.Secure
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.viewmodel.compose.viewModel
import com.chicoeletro.dds.R
import com.chicoeletro.dds.components.FooterStatus
import com.chicoeletro.dds.components.FooterVersion
import com.chicoeletro.dds.components.HeaderBar
import com.chicoeletro.dds.components.HeaderBarState
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.core.agora.AgoraConfig
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.features.Camera.CameraScreen
import com.chicoeletro.dds.features.form.FormScreen
import com.chicoeletro.dds.features.online.AgoraMeetingEntry
import com.chicoeletro.dds.features.online.MeetingRepository
import com.chicoeletro.dds.features.online.DdsSession
import com.chicoeletro.dds.features.team.TeamConfigSync
import com.chicoeletro.dds.features.team.TeamEditDialog
import com.chicoeletro.dds.features.team.TeamChangeRequestRepository
import com.chicoeletro.dds.features.team.RequestStatus
import com.chicoeletro.dds.features.team.TeamChangeRequest
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.features.viewer.ViewerScreen
import com.chicoeletro.dds.features.viewer.ViewerViewModel
import com.chicoeletro.dds.storage.ExecCacheEntry
import com.chicoeletro.dds.storage.FormDataStore
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.ui.sections.sidebar.LeftSidebarSection
import com.chicoeletro.dds.ui.training.buildMonthParticipationDays
import com.chicoeletro.dds.ui.training.canConcludeTrainingId
import com.chicoeletro.dds.ui.training.shouldShowTraining
import com.chicoeletro.dds.ui.training.trainingIsoDateFromId
import com.chicoeletro.dds.viewmodel.NetworkViewModel
import com.chicoeletro.dds.viewmodel.TrainingSyncViewModel
import com.chicoeletro.dds.viewmodel.TrainingViewModel
import com.chicoeletro.dds.viewmodel.TrainingViewModelFactory
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.YearMonth
import java.time.format.DateTimeFormatter

import com.chicoeletro.dds.features.turno.EstadoTurno
import com.chicoeletro.dds.features.turno.RequisicaoTransicao
import com.chicoeletro.dds.features.turno.TurnoSnapshot
import com.chicoeletro.dds.features.turno.TurnoController
import com.chicoeletro.dds.features.turno.TurnoPendingStore
import com.chicoeletro.dds.features.turno.TurnoFirestoreUploader
import com.chicoeletro.dds.ui.components.CommunicationDialog
import com.chicoeletro.dds.features.communication.CommunicationRepository
import com.chicoeletro.dds.features.communication.TeamMessage
import com.chicoeletro.dds.ui.components.MessageHistoryDialog
import com.chicoeletro.dds.features.turno.TurnoEventRemote
import com.chicoeletro.dds.features.turno.TurnoStateRemote
import com.chicoeletro.dds.features.turno.TurnoSessionRemote
import com.chicoeletro.dds.features.turno.TurnoActor
import com.chicoeletro.dds.features.turno.TurnoPhotoAudit
import com.chicoeletro.dds.ui.components.TurnoControlDialog
import com.chicoeletro.dds.ui.components.CommunicationScreen
import com.chicoeletro.dds.ui.components.DdsWarningDialog
import com.chicoeletro.dds.ui.components.UpdateBanner
import com.chicoeletro.dds.ui.components.InterjornadaNotice
import com.chicoeletro.dds.core.version.VersionChecker
import com.chicoeletro.dds.core.version.VersionStatus
import com.chicoeletro.dds.ui.components.TeamChangeReason
import com.chicoeletro.dds.ui.components.TeamChangeReasonDialog
import android.app.Activity

// CameraScreen (modo odômetro)
import com.chicoeletro.dds.features.Camera.CameraMode
import com.chicoeletro.dds.features.Camera.CameraOdometerResult
import com.chicoeletro.dds.storage.TrainingExecSyncState
import com.chicoeletro.dds.core.notifications.NotificationHelper
import com.chicoeletro.dds.core.notifications.TurnoReminderWorker
import com.chicoeletro.dds.core.notifications.DdsReminderWorker
import androidx.work.*
import java.util.concurrent.TimeUnit
import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import java.util.Calendar



data class TrainingStatus(
    val dataConclusao: String,
    val horaConclusao: String,
    val duracao: String,
    val syncState: String = TrainingExecSyncState.SYNCED
)

@Composable
fun MainLayoutContainer() {
    val context = LocalContext.current
    val application = context.applicationContext as Application
    val scope = rememberCoroutineScope()
    // ==========================================================
    // Turno (remoto): multiempresa + deviceId + appVersion
    // ==========================================================
    // FUTURO: virá de config/multiempresa real
    val empresa = remember { "ChicoEletro" }
    val deviceId = remember {
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
    }
    val appVersion = remember {
        runCatching {
            val pm = context.packageManager
            val pkg = context.packageName
            @Suppress("DEPRECATION")
            val pInfo = pm.getPackageInfo(pkg, 0)
            pInfo.versionName ?: "unknown"
        }.getOrElse { "unknown" }
    }

    val trainingViewModel: TrainingViewModel = viewModel(factory = TrainingViewModelFactory(application))
    val networkViewModel: NetworkViewModel = viewModel()
    val syncViewModel: TrainingSyncViewModel = viewModel()

    // ✅ Mensagens centralizadas do SyncViewModel (offline/timeout/erro)
    LaunchedEffect(syncViewModel) {
        syncViewModel.uiMessages.collect { msg ->
            Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
        }
    }

    val isInitializing by trainingViewModel.isInitializing.collectAsState(initial = true)
    val trainings by trainingViewModel.trainings.collectAsState(initial = emptyList())
    val online by networkViewModel.isOnline.collectAsState(initial = false)
    val syncState by syncViewModel.state.collectAsState()

    var selectedTraining by rememberSaveable { mutableStateOf<String?>(null) }
    var showForm by rememberSaveable { mutableStateOf(false) }
    var showEditDialog by remember { mutableStateOf(false) }
    var teamDialogMandatory by rememberSaveable { mutableStateOf(false) }

    // ==========================================================
    // Turno: estado local + fluxo de KM/foto
    // ==========================================================
    var turnoSnap by remember { mutableStateOf(TurnoSnapshot()) }
    var showTurnoControl by remember { mutableStateOf(false) }
    var showCommunicationDialog by rememberSaveable { mutableStateOf(false) }
    val commRepo = remember { CommunicationRepository() }
    var unreadIncomingCount by remember { mutableStateOf(0) }
    var unreadOutgoingCount by remember { mutableStateOf(0) }
    var showHistoryDialog by remember { mutableStateOf(false) }
    var historyMessages by remember { mutableStateOf<List<TeamMessage>>(emptyList()) }


    var teamLoaded by remember { mutableStateOf(false) }
    var lastTeamData by remember { mutableStateOf<LastTeamData?>(null) }
    val teamSync = TeamConfigSync

    var submissaoExistente by remember { mutableStateOf<FormSubmission?>(null) }
    var equipe by rememberSaveable { mutableStateOf("") }
    var eletricistas by remember { mutableStateOf(listOf<String>()) }

    var capturedPhotoUri by remember { mutableStateOf<Uri?>(null) }
    var capturedThumbUri by remember { mutableStateOf<Uri?>(null) }
    var abrirCamera by remember { mutableStateOf(false) }
    var tempoInicioDDS by remember { mutableStateOf<Long?>(null) }

    var trainingStatus by remember { mutableStateOf<Map<String, TrainingStatus>>(emptyMap()) }
    var viewerStatus by remember { mutableStateOf<FooterStatus?>(null) }
    var showPresenceReport by rememberSaveable { mutableStateOf(false) }
    var showDdsWarning by rememberSaveable { mutableStateOf(false) }
    var presenceReportAccessed by rememberSaveable { mutableStateOf(false) }

    var versionStatus by remember { mutableStateOf(VersionStatus.UP_TO_DATE) }
    var updateUrl by remember { mutableStateOf<String?>(null) }

    var modoTesteAtivo by rememberSaveable { mutableStateOf(false) }
    var cliqueLogo by remember { mutableStateOf(0) }

    val auth = remember { FirebaseAuth.getInstance() }
    var currentUser by remember { mutableStateOf<FirebaseUser?>(auth.currentUser) }

    // Odômetro (fluxo do Turno)
    var abrirCameraOdo by remember { mutableStateOf(false) }
    var odoKmTotalPrefill by remember { mutableStateOf("") }
    var odoPendingTarget by remember { mutableStateOf<EstadoTurno?>(null) }
    var odoPendingMotivo by remember { mutableStateOf<com.chicoeletro.dds.features.turno.MotivoDeslocamentoEspecial?>(null) }
    var odoPendingMotivoOutro by remember { mutableStateOf("") }

    DisposableEffect(auth) {
        val listener = FirebaseAuth.AuthStateListener { firebaseAuth ->
            currentUser = firebaseAuth.currentUser
        }
        auth.addAuthStateListener(listener)
        onDispose { auth.removeAuthStateListener(listener) }
    }

    var showOnlineTest by remember { mutableStateOf(false) }

    val meetingRepo = remember { MeetingRepository() }
    val activeSessions by meetingRepo.observeActiveSessions().collectAsState(initial = emptyList())
    var activeSessionChannel by remember { mutableStateOf<String?>(null) }
    var showOrganizerDialog by remember { mutableStateOf<DdsSession?>(null) }
    var isStartingMeeting by remember { mutableStateOf(false) }

    var showReasonDialog by remember { mutableStateOf(false) }
    var pendingTeamChange by remember { mutableStateOf<Triple<String, List<String>, com.chicoeletro.dds.core.WorkSchedule>?>(null) }
    var pendingRequestId by rememberSaveable { mutableStateOf<String?>(null) }
    var activeRequest by remember { mutableStateOf<TeamChangeRequest?>(null) }
    val requestRepo = remember { TeamChangeRequestRepository() }

    val execRepo = remember { TeamTrainingExecutionRepository() }
    val statusMonth = remember(selectedTraining) {
        selectedTraining
            ?.let(::trainingIsoDateFromId)
            ?.let(YearMonth::from)
            ?: YearMonth.now()
    }
    val currentMonthId = remember(statusMonth) { statusMonth.toString() }
    val teamKey = remember(equipe) { TeamTrainingExecutionRepository.teamKeyOf(equipe) }

    LaunchedEffect(teamKey, currentMonthId) {
        if (equipe.isBlank()) return@LaunchedEffect
        TrainingExecLocalStore
            .flowMonth(context, teamKey, currentMonthId)
            .collect { localMap ->
                trainingStatus = localMap.mapValues { (_, st) ->
                    TrainingStatus(st.dataConclusao, st.horaConclusao, st.duracao, st.syncState)
                }
            }
    }

    DisposableEffect(equipe, currentMonthId) {
        if (equipe.isBlank()) {
            trainingStatus = emptyMap()
            onDispose { }
        } else {
            val reg = execRepo.listenMonth(
                teamName = equipe,
                ym = statusMonth,
                onUpdate = { map ->
                    val newStatus = map.mapValues { (_, st) ->
                        TrainingStatus(st.dataConclusao, st.horaConclusao, st.duracao)
                    }
                    trainingStatus = newStatus
                    scope.launch {
                        val cache = map.mapValues { (_, st) ->
                            ExecCacheEntry(
                                st.dataConclusao,
                                st.horaConclusao,
                                st.duracao,
                                TrainingExecSyncState.SYNCED
                            )
                        }
                        TrainingExecLocalStore.mergeRemoteMonth(context,
                            teamKey,
                            currentMonthId,
                            cache)
                    }
                }
            )
            onDispose { reg.remove() }
        }
    }

    LaunchedEffect(pendingRequestId) {
        val rid = pendingRequestId ?: return@LaunchedEffect
        requestRepo.observeRequest(rid).collect { req ->
            activeRequest = req
            if (req?.status == "APPROVED") {
                // Confirmado pelo monitor: Podemos limpar o pedido e seguir a vida
                pendingRequestId = null
                activeRequest = null
                pendingTeamChange = null
                requestRepo.deleteRequest(rid)
                Log.d("TeamChange", "Alteração confirmada remotamente pelo monitor.")
            } else if (req?.status == "REJECTED") {
                // REJEITADO! Precisamos reverter tudo
                val oldName = req.oldPrefix
                val currentName = req.newPrefix
                val reason = req.reason
                
                // 1. Reverte o histórico local (faz a migração de volta)
                if (reason == "VEHICLE_CHANGE") {
                    TrainingExecLocalStore.migrateTeam(context, currentName, oldName)
                    FormDataStore.migrateTeam(context, currentName, oldName)
                } else {
                    // Se era nova equipe, limpamos o que foi gerado no nome novo
                    TrainingExecLocalStore.clearLocalOnly(context, currentName)
                }

                // 2. Restaura o prefixo original
                teamSync.savePendingLocal(context, oldName, eletricistas, lastTeamData?.workSchedule ?: com.chicoeletro.dds.core.WorkSchedule())
                equipe = oldName
                
                // 3. Limpa estados
                pendingRequestId = null
                activeRequest = null
                pendingTeamChange = null
                
                Toast.makeText(context, "ALTERAÇÃO REJEITADA PELO MONITOR! Retornando ao prefixo $oldName.", Toast.LENGTH_LONG).show()
                requestRepo.deleteRequest(rid)
            }
        }
    }

    LaunchedEffect(context) {
        teamSync.observeLocal(context).collect { data ->
            lastTeamData = data
            teamLoaded = true
            if (data != null) {
                equipe = data.equipe
                eletricistas = data.eletricistas
            }
        }
    }

    LaunchedEffect(teamLoaded, equipe) {
        if (!teamLoaded || equipe.isBlank()) return@LaunchedEffect
        turnoSnap = TurnoController(context, equipe).current()
    }

    // ==========================================================
    // Notificações: Canais e Workers
    // ==========================================================
    val requestPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            NotificationHelper.createNotificationChannels(context)
        }
    }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            NotificationHelper.createNotificationChannels(context)
        }
    }

    LaunchedEffect(lastTeamData) {
        val data = lastTeamData ?: return@LaunchedEffect
        if (data.equipe.isBlank()) return@LaunchedEffect

        val workManager = WorkManager.getInstance(context)

        // 1. Worker Periódico (Turno) - A cada 1 hora
        val turnoRequest = PeriodicWorkRequestBuilder<TurnoReminderWorker>(1, TimeUnit.HOURS)
            .setBackoffCriteria(BackoffPolicy.LINEAR, 15, TimeUnit.MINUTES)
            .addTag("turno_reminder")
            .build()

        workManager.enqueueUniquePeriodicWork(
            "turno_periodic_check",
            ExistingPeriodicWorkPolicy.UPDATE,
            turnoRequest
        )

        // 2. Worker Diário (DDS) - No horário de início da equipe
        val now = Calendar.getInstance()
        val target = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, data.workStartHour)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            if (before(now)) {
                add(Calendar.DAY_OF_YEAR, 1)
            }
        }
        val delay = target.timeInMillis - now.timeInMillis

        val ddsRequest = OneTimeWorkRequestBuilder<DdsReminderWorker>()
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .addTag("dds_daily_reminder")
            .build()

        workManager.enqueueUniqueWork(
            "dds_daily_check",
            ExistingWorkPolicy.REPLACE,
            ddsRequest
        )
    }

    // ==========================================================
    // Turno: retry de pendências ao voltar online (offline-first)
    // ==========================================================

    LaunchedEffect(online) {
        TurnoFirestoreUploader.tryPushPending(context, online)
    }

    LaunchedEffect(online, teamLoaded, lastTeamData?.pendingSync) {
        if (!teamLoaded) return@LaunchedEffect
        teamSync.tryPushPending(context, online, lastTeamData)
    }

    LaunchedEffect(online, teamLoaded, lastTeamData?.equipe) {
        if (!teamLoaded) return@LaunchedEffect
        teamSync.pullLatestIfSafe(context, online, lastTeamData)
    }

    DisposableEffect(equipe) {
        if (equipe.isBlank()) return@DisposableEffect onDispose {}
        val regIn = commRepo.listenIncoming(equipe) { msgs ->
            val unread = msgs.filter { it.status == "NÃO LIDO" }
            if (unread.size > unreadIncomingCount) {
                unread.maxByOrNull { it.timestamp?.time ?: 0L }?.let { 
                    NotificationHelper.showCommunicationNotification(context, it.fromEquipe, it.content)
                }
            }
            unreadIncomingCount = unread.size
        }
        val regOut = commRepo.listenOutgoing(equipe) { msgs ->
            unreadOutgoingCount = msgs.filter { it.status == "NÃO LIDO" }.size
        }
        onDispose {
            regIn.remove()
            regOut.remove()
        }
    }

    LaunchedEffect(teamLoaded, lastTeamData, isInitializing) {
        if (!teamLoaded || isInitializing) return@LaunchedEffect
        val missingTeam = lastTeamData?.equipe.isNullOrBlank() || lastTeamData?.eletricistas.isNullOrEmpty()
        if (missingTeam) {
            teamDialogMandatory = true
            showEditDialog = true
        }
    }

    val visibleTrainings = remember(trainings) {
        val today = LocalDate.now()
        trainings
            .filter { shouldShowTraining(it, today) }
            .sortedByDescending { t ->
                runCatching { LocalDate.parse(t.id.substringBefore(" - "), DateTimeFormatter.ISO_LOCAL_DATE) }
                    .getOrElse { LocalDate.MIN }
            }
    }

    val headerParticipationDays = remember(selectedTraining, trainings, trainingStatus) {
        buildMonthParticipationDays(
            selectedTrainingId = selectedTraining,
            trainings = trainings,
            completedTrainingIds = trainingStatus.keys,
            today = LocalDate.now()
        )
    }

    LaunchedEffect(online) { syncViewModel.autoSyncIfNeeded(online) }

    LaunchedEffect(Unit) {
        syncViewModel.refreshRequests.collect { trainingViewModel.refreshTrainings() }
    }

    LaunchedEffect(selectedTraining, equipe) {
        submissaoExistente = null
        if (!selectedTraining.isNullOrBlank() && equipe.isNotBlank()) {
            FormDataStore.getAllSubmissions(context).collect { lista ->
                submissaoExistente = lista.find {
                    it.equipe.equals(equipe.trim(), true) && it.trainingName == selectedTraining
                }
            }
        }
    }

    LaunchedEffect(Unit) {
        VersionChecker.checkPlayStoreStatus(context) { status ->
            versionStatus = status
        }
    }

    if (showDdsWarning) {
        DdsWarningDialog(
            onDismiss = { showDdsWarning = false },
            onConfirm = {
                showDdsWarning = false
                showPresenceReport = true
            }
        )
    }
    
    val today = LocalDate.now()
    val last7Due = trainings
        .filter { t -> 
            trainingIsoDateFromId(t.id)?.let { d -> !d.isAfter(today) } ?: false 
        }
        .sortedByDescending { it.id }
        .take(7)
    val allDone = last7Due.isEmpty() || last7Due.all { it.id in trainingStatus }

    val bubbleColor = when {
        unreadIncomingCount > 0 -> Color.Red
        unreadOutgoingCount > 0 -> Color(0xFF2E7D32) // Verde
        !allDone -> Color(0xFFFFC107) // Amarelo
        else -> Color.Gray
    }

    Box(Modifier.fillMaxSize()) {
        if (isInitializing) {
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.5f)), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator()
                    Spacer(Modifier.height(8.dp))
                    Text("Carregando dados…", style = MaterialTheme.typography.bodyLarge, color = Color.White)
                }
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                HeaderBar(
                    overlayAlpha = 1f,
                    selectedTraining = selectedTraining,
                    monthParticipationDays = headerParticipationDays,
                    showTestCameraButton = modoTesteAtivo,
                    onTestCameraClick = { if (modoTesteAtivo) showOnlineTest = true },
                    onCommunicationClick = { showCommunicationDialog = true },
                    bubbleColor = bubbleColor
                )
                Row(Modifier.weight(1f)) {
                    LeftSidebarSection(
                        widthDp = 220,
                        online = online,
                        isSyncing = syncState.isSyncing,
                        overallTotal = syncState.overallTotal,
                        overallDone = syncState.overallDone,
                        plannedTrainingsTotal = syncState.plannedTrainingsTotal,
                        currentTotal = syncState.currentTotal,
                        currentDone = syncState.currentDone,
                        currentId = syncState.currentId,
                        onHome = { selectedTraining = null },
                        onSyncNow = { syncViewModel.syncNow() },
                        onPresenceReport = { 
                            if (allDone) {
                                showPresenceReport = true
                            } else {
                                showDdsWarning = true
                            }
                            presenceReportAccessed = true
                        },
                        trainings = visibleTrainings,
                        selectedTraining = selectedTraining,
                        trainingStatus = trainingStatus,
                        onSelectTraining = { tid ->
                            selectedTraining = tid
                            tempoInicioDDS = System.currentTimeMillis()
                            showForm = false
                        },
                        presenceReportAccessed = presenceReportAccessed,
                        turnoEstado = turnoSnap.estado,
                        turnoNocSs = turnoSnap.nocSs,
                        onClickTurno = { showTurnoControl = true },
                        equipe = equipe,
                        eletricistas = eletricistas,
                        onClickEquipe = {
                            teamDialogMandatory = false
                            showEditDialog = true
                        }
                    )

                    val fundoPainelDireito = if (modoTesteAtivo) Color(0xFF212121) else MaterialTheme.colorScheme.background

                    Box(Modifier.weight(1f).fillMaxHeight().background(fundoPainelDireito).padding(8.dp)) {
                        if (selectedTraining == null) {
                            Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                                Image(
                                    painter = painterResource(id = R.drawable.dds),
                                    contentDescription = "Logo DDS",
                                    modifier = Modifier.fillMaxWidth(0.8f).padding(bottom = 24.dp).clickable {
                                        cliqueLogo++
                                        if (cliqueLogo >= 10) {
                                            modoTesteAtivo = !modoTesteAtivo
                                            if (!modoTesteAtivo) showOnlineTest = false
                                            cliqueLogo = 0
                                        }
                                    },
                                    contentScale = ContentScale.Fit
                                )
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = null, modifier = Modifier.size(32.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("Selecione um treinamento", style = MaterialTheme.typography.bodyLarge)
                                }
                            }
                        } else {
                            val vContext = LocalContext.current
                            val viewerVM = remember { ViewerViewModel(vContext) }
                            val currentId = selectedTraining!!
                            val canConcludeCurrent = canConcludeTrainingId(currentId)
                            ViewerScreen(
                                trainingId = currentId,
                                viewModel  = viewerVM,
                                status     = trainingStatus[currentId],
                                canConclude = canConcludeCurrent,
                                onOpenForm = {
                                    if (!canConcludeCurrent) return@ViewerScreen
                                    if (equipe.isBlank() || eletricistas.isEmpty()) {
                                        showEditDialog = true
                                    } else {
                                        abrirCamera = true
                                        showForm = false
                                    }
                                },
                                onEnterAgora = {
                                    val sessionIsoDate = currentId.substringBefore(" - ").trim()
                                    val title = currentId.substringAfter(" - ").trim()
                                    
                                    val session = activeSessions.find { s ->
                                        val parts = s.date.split("/")
                                        val formattedDate = if (parts.size == 3) "${parts[2]}-${parts[1]}-${parts[0]}" else s.date
                                        
                                        val isDateMatch = formattedDate == sessionIsoDate
                                        val extractedTime = com.chicoeletro.dds.ui.training.parseDdsOnlineTime(title)
                                        
                                        val isMatch = if (extractedTime != null) {
                                            s.time == extractedTime
                                        } else {
                                            s.subject.trim().equals(title, ignoreCase = true)
                                        }
                                        
                                        isDateMatch && isMatch
                                    }
                                    
                                    if (session != null) {
                                        val isHost = session.roles.hostTeams.any { it.equals(equipe, ignoreCase = true) }
                                        
                                        if (session.status == "active") {
                                            if (session.channelName.isNotBlank()) {
                                                activeSessionChannel = session.channelName
                                            } else {
                                                Toast.makeText(vContext, "Erro: Canal não configurado na sessão.", Toast.LENGTH_SHORT).show()
                                            }
                                        } else if (isHost) {
                                            // É o organizador e a reunião ainda está 'scheduled'
                                            showOrganizerDialog = session
                                        } else {
                                            // Participante comum e reunião não aberta
                                            Toast.makeText(vContext, "Reunião ainda não foi aberta pelo organizador.", Toast.LENGTH_SHORT).show()
                                        }
                                    } else {
                                        Toast.makeText(vContext, "Nenhuma sessão agendada encontrada para este horário.", Toast.LENGTH_SHORT).show()
                                    }
                                },
                                onStatusChanged = { viewerStatus = it }
                            )
                        }
                    }
                }
                FooterVersion(
                    status = viewerStatus,
                    isTestVersion = versionStatus == VersionStatus.TEST_VERSION
                )
            }

            if (showEditDialog) {
                TeamEditDialog(
                    initialTeamName = equipe,
                    initialMembers  = eletricistas,
                    onDismiss = { showEditDialog = false },
                    onSave   = { name, members, schedule ->
                        val oldName = equipe
                        if (oldName.isNotBlank() && oldName != name) {
                            // Mudança de prefixo: pede motivo antes de salvar
                            pendingTeamChange = Triple(name, members, schedule)
                            showReasonDialog = true
                        } else {
                            // Mesma equipe ou primeira vez: salva direto
                            scope.launch {
                                teamSync.savePendingLocal(context, name, members, schedule)
                                equipe = name
                                eletricistas = members
                                teamDialogMandatory = false
                                showEditDialog = false
                            }
                        }
                    }
                )
            }

            if (showReasonDialog && pendingTeamChange != null) {
                TeamChangeReasonDialog(
                    oldPrefix = equipe,
                    newPrefix = pendingTeamChange!!.first,
                    onCancel = { showReasonDialog = false },
                    onConfirm = { reason ->
                        val (name, members, schedule) = pendingTeamChange!!
                        val oldName = equipe
                        
                        scope.launch {
                            // 1. APLICA IMEDIATAMENTE (FLUXO OTIMISTA)
                            if (reason == TeamChangeReason.VEHICLE_CHANGE) {
                                TrainingExecLocalStore.migrateTeam(context, oldName, name)
                                FormDataStore.migrateTeam(context, oldName, name)
                            } else {
                                TrainingExecLocalStore.clearLocalOnly(context, oldName)
                            }
                            
                            teamSync.savePendingLocal(context, name, members, schedule)
                            equipe = name
                            eletricistas = members
                            
                            // 2. CRIA O PEDIDO PARA AUDITORIA/REVERSÃO
                            val rid = requestRepo.createRequest(
                                oldPrefix = oldName,
                                newPrefix = name,
                                reason = reason.name,
                                deviceId = deviceId,
                                appVersion = appVersion
                            )
                            pendingRequestId = rid
                            
                            showReasonDialog = false
                            showEditDialog = false
                            teamDialogMandatory = false
                        }
                    }
                )
            }

            if (showForm) {
                androidx.activity.compose.BackHandler(enabled = true) { }
                Dialog(onDismissRequest = { }, properties = DialogProperties(dismissOnClickOutside = false, dismissOnBackPress = false, usePlatformDefaultWidth = false)) {
                    Surface(modifier = Modifier.fillMaxWidth().padding(16.dp), shape = MaterialTheme.shapes.large) {
                        FormScreen(
                            trainingName = selectedTraining!!,
                            existing = submissaoExistente?.let { it to selectedTraining!! },
                            lastTeam = LastTeamData(equipe, eletricistas),
                            headerDate = HeaderBarState.datePart,
                            headerTitle = HeaderBarState.titlePart,
                            fotoUri = capturedPhotoUri,
                            thumbUri = capturedThumbUri,
                            scope = scope,
                            setFotoUri = { uri ->
                                if (uri == null) {
                                    showForm = false
                                    abrirCamera = true
                                } else { capturedPhotoUri = uri }
                            },
                            onBack = { showForm = false },
                            onSubmit = { submission, lastTeam ->
                                scope.launch {
                                    FormDataStore.saveSubmission(context, submission)
                                    teamSync.saveLocalCache(context, lastTeam)
                                    capturedPhotoUri = null
                                    capturedThumbUri = null
                                }
                            },
                            tempoInicioMillis = tempoInicioDDS,
                            modoTesteAtivo = modoTesteAtivo,
                            jaConcluido = submissaoExistente != null || !canConcludeTrainingId(selectedTraining!!),
                            onCompleted = { data, hora, duracao ->
                                val tid = selectedTraining!!
                                trainingStatus = trainingStatus.toMutableMap().apply {
                                    put(tid, TrainingStatus(data, hora, duracao, TrainingExecSyncState.LOCAL_ONLY))
                                }
                                scope.launch {
                                    TrainingExecLocalStore.upsert(
                                        context,
                                        teamKey,
                                        currentMonthId,
                                        tid,
                                        ExecCacheEntry(data, hora, duracao, TrainingExecSyncState.LOCAL_ONLY)
                                    )
                                }
                                showForm = false
                            }
                        )
                    }
                }
            }

            if (abrirCamera) {
                CameraScreen(
                    onPhotoCaptured = { uri, thumbUri ->
                        capturedPhotoUri = uri
                        capturedThumbUri = thumbUri
                        abrirCamera = false
                        showForm = selectedTraining?.let { canConcludeTrainingId(it) } == true

                    },
                    onBack = {
                        abrirCamera = false
                        if (selectedTraining?.let { canConcludeTrainingId(it) } == true) showForm = true
                    }
                )
            }

            // ===== Camera Odômetro (para Controle de Turno) =====
            if (abrirCameraOdo) {
                CameraScreen(
                    mode = CameraMode.ODOMETER,
                    onPhotoCaptured = { _, _ -> /* não usado no modo ODO */ },
                    onOdometerCaptured = { result: CameraOdometerResult ->
                        val kmTotal = result.km?.toString() ?: ""
                        odoKmTotalPrefill = kmTotal
                        abrirCameraOdo = false
                        showTurnoControl = true
                    },
                    onBack = {
                        abrirCameraOdo = false
                        showTurnoControl = true
                    }
                )
            }

            if (modoTesteAtivo && showOnlineTest) {
                Dialog(onDismissRequest = { showOnlineTest = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
                        AgoraMeetingEntry(
                            appId = AgoraConfig.APP_ID,
                            channelName = AgoraConfig.CHANNEL_NAME,
                            tempToken = AgoraConfig.TEMP_TOKEN,
                            localUid = AgoraConfig.LOCAL_USER_ID,
                            presentationTitle = selectedTraining,
                            teamName = equipe,
                            teamMembers = eletricistas,
                            onLeave = { showOnlineTest = false }
                        )
                    }
                }
            }

            if (activeSessionChannel != null) {
                Dialog(onDismissRequest = { activeSessionChannel = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                        AgoraMeetingEntry(
                            appId = AgoraConfig.APP_ID,
                            channelName = activeSessionChannel!!,
                            tempToken = AgoraConfig.TEMP_TOKEN, 
                            localUid = AgoraConfig.LOCAL_USER_ID,
                            presentationTitle = selectedTraining,
                            teamName = equipe,
                            teamMembers = eletricistas,
                            onLeave = { activeSessionChannel = null }
                        )
                    }
                }
            }

            // ======= TELA DO ORGANIZADOR (MODAL) =======
            if (showOrganizerDialog != null) {
                val session = showOrganizerDialog!!
                AlertDialog(
                    onDismissRequest = { if (!isStartingMeeting) showOrganizerDialog = null },
                    title = { Text("Organizador: Abrir Reunião") },
                    text = {
                        Column {
                            Text("Você é o organizador deste DDS Online.")
                            Spacer(Modifier.height(8.dp))
                            Text("Tema: ${session.subject}", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                            Text("Horário: ${session.time}", style = MaterialTheme.typography.bodySmall)
                            
                            if (isStartingMeeting) {
                                Spacer(Modifier.height(16.dp))
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                                    Spacer(Modifier.width(12.dp))
                                    Text("Iniciando sessão...")
                                }
                            }
                        }
                    },
                    confirmButton = {
                        Button(
                            onClick = {
                                scope.launch {
                                    try {
                                        isStartingMeeting = true
                                        meetingRepo.updateSessionStatus(session.id, "active")
                                        showOrganizerDialog = null
                                        activeSessionChannel = session.channelName
                                    } catch (e: Exception) {
                                        Toast.makeText(context, "Falha ao iniciar: ${e.message}", Toast.LENGTH_LONG).show()
                                    } finally {
                                        isStartingMeeting = false
                                    }
                                }
                            },
                            enabled = !isStartingMeeting
                        ) {
                            Text("Iniciar Agora")
                        }
                    },
                    dismissButton = {
                        OutlinedButton(
                            onClick = { showOrganizerDialog = null },
                            enabled = !isStartingMeeting
                        ) {
                            Text("Cancelar")
                        }
                    }
                )
            }

            if (showTurnoControl && equipe.isNotBlank()) {
                val ctrl = remember(equipe) { TurnoController(context, equipe) }
                TurnoControlDialog(
                    snapshot = turnoSnap,
                    onDismiss = { showTurnoControl = false },
                    onSaveNocSs = { noc: String? ->
                        runCatching {
                            val after = ctrl.atualizarNocSs(noc)
                            turnoSnap = after

                            val state = TurnoStateRemote(
                                empresa = empresa,
                                equipe = equipe,
                                turnoId = after.turnoId,
                                isOpen = after.isOpen,
                                membersSnapshot = after.membersSnapshot,
                                openedAtClientMs = after.openedAtClientMs,
                                closedAtClientMs = null,
                                closeReason = null,
                                clientUpdatedAtMs = after.clientUpdatedAtMs,
                                updatedAtIso = after.lastChangedAtIso ?: Instant.ofEpochMilli(after.clientUpdatedAtMs).toString(),
                                lastEventId = after.lastEventId,
                                lastEventAtClientMs = after.lastEventAtClientMs,
                                estado = after.estado.name,
                                nocSs = after.nocSs,
                                kmTotalAbs = after.kmTotalAbs,
                                kmInicioTotalAbs = after.kmInicioTotalAbs,
                                kmDeltaTurno = after.kmDeltaTurno,
                                kmInicioTurno4 = after.kmInicioLast3,
                                inicioTurnoAtIso = after.inicioTurnoAtIso,
                                odometroVerificado = after.odometroVerificado,
                                ultimosKm4 = after.ultimosKmLast3,
                                eventosKmCounter = after.eventosKmCounter,
                                lastMotivo = after.lastMotivo?.name,
                                lastMotivoOutro = after.lastMotivoOutro,
                                deviceIdLastWriter = deviceId
                            )

                            TurnoFirestoreUploader.pushState(
                                empresa = empresa,
                                equipe = equipe,
                                state = state
                            )
                        }
                    },
                    onOpenOdometerCamera = { target, motivo, motivoOutro ->
                        // salva contexto para reabrir direto no step KM depois da foto
                        odoPendingTarget = target
                        odoPendingMotivo = motivo
                        odoPendingMotivoOutro = motivoOutro
                        showTurnoControl = false
                        abrirCameraOdo = true
                    },
                    prefillKmTotal = odoKmTotalPrefill,
                    startAtKmTarget = odoPendingTarget,
                    prefillMotivo = odoPendingMotivo,
                    prefillMotivoOutro = odoPendingMotivoOutro,
                    onRequestTransition = { req: RequisicaoTransicao ->

                        // ===== ABRIR TURNO (sessão determinística) =====
                        // Regra: mudança de membros implica fechar e abrir novo turno.
                        if (!turnoSnap.isOpen && (req.to == EstadoTurno.ABERTO || req.to == EstadoTurno.DESLOCAMENTO_ESPECIAL)) {
                            val opened = runCatching { ctrl.abrirTurno(empresa, eletricistas) }.getOrNull()
                                ?: return@TurnoControlDialog
                            turnoSnap = opened

                            // Sessão: grava openedAtServer (oficial) quando online
                            val sessionOpen = TurnoSessionRemote(
                                empresa = empresa,
                                equipe = equipe,
                                turnoId = opened.turnoId!!,
                                membersSnapshot = opened.membersSnapshot,
                                openedAtClientMs = opened.openedAtClientMs!!,
                                openedByUid = null,
                                openedByDeviceId = deviceId
                            )
                            scope.launch {
                                runCatching { TurnoFirestoreUploader.upsertTurnoSession(sessionOpen) }
                            }
                        }

                        val plano = runCatching {
                            ctrl.plan(
                                to = req.to,
                                proposedKmTotalAbs = req.kmTotalAbs,
                                proposedKmLast3 = req.kmLast3
                            )
                        }
                            .onFailure { e ->
                                android.util.Log.w("DDS-TURNO", "Falha plan: ${e.message}", e)
                                Toast.makeText(context, e.message ?: "Falha ao planejar transição", Toast.LENGTH_LONG).show()
                            }
                            .getOrNull() ?: return@TurnoControlDialog

                        val after = runCatching { ctrl.confirm(req, photoProvided = false) }
                            .onFailure { e ->
                                android.util.Log.w("DDS-TURNO", "Falha confirm: ${e.message}", e)
                                Toast.makeText(context, e.message ?: "Falha ao confirmar transição", Toast.LENGTH_LONG).show()
                            }
                            .getOrNull() ?: return@TurnoControlDialog

                        val before = turnoSnap
                        // Atualiza UI local imediatamente
                        turnoSnap = after

                        // -------------------------
                        // Firebase (event + state) - offline-first
                        // -------------------------
                        // eventId determinístico (offline-first)
                        val occurredAtMs = after.lastEventAtClientMs
                        val tsIso = Instant.ofEpochMilli(occurredAtMs).toString()
                        val eventId = "${deviceId}_${occurredAtMs}_${req.to.name}"

                        // kmDeltaTurno: no modelo OPÇÃO 1, o controller acumula sempre.
                        // Só envia quando FECHA (ABERTO -> FECHADO).
                        val kmDeltaTurno: Int? =
                            if (before.estado == EstadoTurno.ABERTO && req.to == EstadoTurno.FECHADO) after.kmDeltaTurno else null

                        val actor = TurnoActor(
                            deviceId = deviceId,
                            deviceModel = Build.MODEL ?: "unknown",
                            appVersion = appVersion
                        )

                        val photoAudit = TurnoPhotoAudit(
                            required = plano.pedeFoto,
                            photoId = null,       // sem foto por enquanto
                            storagePath = null,   // futuro
                            thumbPath = null      // futuro
                        )

                        val event = TurnoEventRemote(
                            empresa = empresa,
                            equipe = equipe,
                            turnoId = after.turnoId!!,
                            eventId = eventId,
                            occurredAtClientMs = occurredAtMs,
                            clientCreatedAtIso = tsIso,
                            from = before.estado.name,
                            to = req.to.name,
                            // OPÇÃO 1: KM total (quando informado)
                            kmTotalAbs = req.kmTotalAbs,
                            // Mantemos km4 como "últimos 3" por enquanto (compat com modelo remoto atual).
                            // Se veio apenas KM total, o dialog/controller deve derivar kmLast3.
                            km4 = req.kmLast3,
                            // OPÇÃO 1: início do turno (totalAbs quando existir)
                            kmInicioTotalAbs = before.kmInicioTotalAbs,
                            kmInicioTurno4 = before.kmInicioLast3,
                            kmDeltaTurno = kmDeltaTurno,
                            nocSs = before.nocSs,
                            motivo = req.motivo?.name,
                            motivoOutro = req.motivoOutro?.trim()?.takeIf { it.isNotBlank() },
                            photoAudit = photoAudit,
                            actor = actor
                        )

                        // Estado “último vence”
                        val state = TurnoStateRemote(
                            empresa = empresa,
                            equipe = equipe,

                            turnoId = after.turnoId,
                            isOpen = after.isOpen,
                            membersSnapshot = after.membersSnapshot,

                            openedAtClientMs = after.openedAtClientMs,
                            closedAtClientMs = if (req.to == EstadoTurno.FECHADO) occurredAtMs else null,
                            closeReason = null,

                            clientUpdatedAtMs = after.clientUpdatedAtMs,
                            updatedAtIso = after.lastChangedAtIso ?: tsIso,

                            lastEventId = eventId,
                            lastEventAtClientMs = occurredAtMs,

                            estado = after.estado.name,
                            nocSs = after.nocSs,

                            // OPÇÃO 1: odometria no current
                            kmTotalAbs = after.kmTotalAbs,
                            kmInicioTotalAbs = after.kmInicioTotalAbs,
                            kmDeltaTurno = after.kmDeltaTurno,

                            kmInicioTurno4 = after.kmInicioLast3,
                            inicioTurnoAtIso = after.inicioTurnoAtIso,

                            odometroVerificado = after.odometroVerificado,
                            ultimosKm4 = after.ultimosKmLast3,
                            eventosKmCounter = after.eventosKmCounter,

                            lastMotivo = after.lastMotivo?.name,
                            lastMotivoOutro = after.lastMotivoOutro,

                            deviceIdLastWriter = deviceId
                        )

                        // Se fechou o turno, registra closedAtServer (oficial) na sessão
                        if (req.to == EstadoTurno.FECHADO && before.isOpen && !before.turnoId.isNullOrBlank()) {
                            val sessionClose = TurnoSessionRemote(
                                empresa = empresa,
                                equipe = equipe,
                                turnoId = before.turnoId,
                                membersSnapshot = before.membersSnapshot,
                                openedAtClientMs = before.openedAtClientMs ?: 0L,
                                closedAtClientMs = occurredAtMs,
                                closeReason = null,
                                openedByUid = null,
                                openedByDeviceId = deviceId,
                                closedByUid = null,
                                closedByDeviceId = deviceId
                            )
                            scope.launch {
                                runCatching { TurnoFirestoreUploader.upsertTurnoSession(sessionClose) }
                            }
                        }

                        // 1) Enfileira SEMPRE (offline-first) SEMPRE (offline-first)
                        TurnoPendingStore.enqueue(context, event)

                        // 2) Atualiza o doc de state (último vence) — se falhar, fica só local por enquanto
                        TurnoFirestoreUploader.pushState(
                            empresa = empresa,
                            equipe = equipe,
                            state = state
                        )

                        // 3) Tenta enviar pendências se online (inclui este evento recém-enfileirado)
                        TurnoFirestoreUploader.tryPushPending(context, online)

                        showTurnoControl = false

                        // depois de confirmar uma transição, limpa prefill para não “vazar” para próximas ações
                        odoKmTotalPrefill = ""
                        odoPendingTarget = null
                        odoPendingMotivo = null
                        odoPendingMotivoOutro = ""
                    }
                )
            }
            if (showPresenceReport) {
                if (equipe.isBlank()) {
                    LaunchedEffect(Unit) {
                        Toast.makeText(context, "Por favor, defina a equipe primeiro para ver o relatório anual.", Toast.LENGTH_SHORT).show()
                        showPresenceReport = false
                    }
                } else {
                    com.chicoeletro.dds.ui.components.ProductionReportDialog(
                        equipe = equipe,
                        onDismiss = { showPresenceReport = false }
                    )
                }
            }

            if (versionStatus == VersionStatus.UPDATE_AVAILABLE) {
                UpdateBanner(
                    onUpdateClick = { 
                        (context as? Activity)?.let { activity ->
                            VersionChecker.startUpdateFlow(activity, 999) 
                        }
                    },
                    onDismiss = { versionStatus = VersionStatus.UP_TO_DATE }
                )
            }

            if (showCommunicationDialog) {
                Dialog(
                    onDismissRequest = { showCommunicationDialog = false },
                    properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)
                ) {
                    CommunicationScreen(
                        equipeOrigem = equipe,
                        onDismiss = { showCommunicationDialog = false }
                    )
                }
            }
        }
    }
}