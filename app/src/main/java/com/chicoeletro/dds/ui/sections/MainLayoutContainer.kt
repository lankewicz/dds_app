// Módulo: app/src/main/java/com/chicoeletro/dds/ui/sections/MainLayoutContainer.kt
// Função: Container principal da interface. Organiza a estrutura de navegação, barras latrais 
//         e a área de conteúdo dinâmico utilizando uma arquitetura baseada em Scaffold.
// Tecnologias: Jetpack Compose, Material3, Scaffold, Jetpack Navigation.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.ui.sections

import android.app.Application
import android.util.Log
import android.widget.Toast
import android.os.Build
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.chicoeletro.dds.components.HeaderBar
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.features.online.MeetingRepository
import com.chicoeletro.dds.features.online.DdsSession
import com.chicoeletro.dds.features.team.TeamConfigSync
import com.chicoeletro.dds.features.team.TeamChangeRequestRepository
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.storage.FormDataStore
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.ui.training.buildMonthParticipationDays
import com.chicoeletro.dds.viewmodel.NetworkViewModel
import com.chicoeletro.dds.viewmodel.TrainingSyncViewModel
import com.chicoeletro.dds.viewmodel.TrainingViewModel
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth
import com.chicoeletro.dds.features.turno.TurnoViewModel
import com.chicoeletro.dds.features.communication.CommunicationRepository
import com.chicoeletro.dds.core.version.VersionChecker
import com.chicoeletro.dds.core.version.VersionStatus
import com.chicoeletro.dds.ui.components.TeamChangeReason
import android.content.Context
import android.content.BroadcastReceiver
import android.content.Intent
import android.content.IntentFilter
import android.location.LocationManager
import com.chicoeletro.dds.core.notifications.NotificationHelper
import com.chicoeletro.dds.core.notifications.TurnoReminderWorker
import com.chicoeletro.dds.core.notifications.DdsReminderWorker
import androidx.work.*
import java.util.concurrent.TimeUnit
import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import java.util.Calendar

@Composable
fun MainLayoutContainer() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val navController = rememberNavController()
    
    val configuration = LocalConfiguration.current
    val isTablet = configuration.screenWidthDp >= 600

    val trainingViewModel: TrainingViewModel = hiltViewModel()
    val networkViewModel: NetworkViewModel = hiltViewModel()
    val syncViewModel: TrainingSyncViewModel = hiltViewModel()
    val turnoViewModel: TurnoViewModel = hiltViewModel()

    val trainings by trainingViewModel.trainings.collectAsState()
    val trainingStatus by trainingViewModel.trainingStatus.collectAsState()
    val online by networkViewModel.isOnline.collectAsState()
    val syncState by syncViewModel.state.collectAsState()
    val turnoSnap by turnoViewModel.turnoSnapshot.collectAsState()
    val isInitializing by trainingViewModel.isInitializing.collectAsState()

    // ✅ Mensagens centralizadas do SyncViewModel
    LaunchedEffect(syncViewModel) {
        syncViewModel.uiMessages.collect { msg ->
            Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
        }
    }

    // ✅ Atualiza a lista de treinamentos assim que o download da sync for finalizado
    LaunchedEffect(syncViewModel) {
        syncViewModel.refreshRequests.collect {
            trainingViewModel.refreshTrainings()
        }
    }

    // ✅ Sincroniza automaticamente quando o dispositivo ficar online
    LaunchedEffect(online) {
        if (online) {
            syncViewModel.autoSyncIfNeeded(true)
        }
    }

    var selectedTraining by rememberSaveable { mutableStateOf<String?>(null) }
    var showAbastecimento by rememberSaveable { mutableStateOf(false) }
    var showForm by rememberSaveable { mutableStateOf(false) }
    var showEditDialog by remember { mutableStateOf(false) }
    var teamDialogMandatory by rememberSaveable { mutableStateOf(false) }

    var pendingCrashReport by remember {
        mutableStateOf(com.chicoeletro.dds.core.crash.CrashReportManager.getPendingCrashReport(context))
    }

    var showCommunicationDialog by rememberSaveable { mutableStateOf(false) }
    val commRepo = remember { CommunicationRepository() }
    var unreadIncomingCount by remember { mutableStateOf(0) }
    var unreadOutgoingCount by remember { mutableStateOf(0) }

    var teamLoaded by remember { mutableStateOf(false) }
    var lastTeamData by remember { mutableStateOf<LastTeamData?>(null) }
    val teamSync = TeamConfigSync

    var submissaoExistente by remember { mutableStateOf<FormSubmission?>(null) }
    var equipe by rememberSaveable { mutableStateOf("") }
    var eletricistas by remember { mutableStateOf(listOf<String>()) }
    var motorista by remember { mutableStateOf<String?>(null) }
    var coringas by remember { mutableStateOf(listOf<String>()) }

    var gpsEnabled by remember { mutableStateOf(true) }

    LaunchedEffect(equipe) {
        trainingViewModel.updateTeamAndMonth(equipe, YearMonth.now())
        turnoViewModel.init(equipe)
    }

    DisposableEffect(context) {
        val checkGps = {
            try {
                val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
                locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                        locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
            } catch (e: Exception) { false }
        }
        gpsEnabled = checkGps()
        val filter = IntentFilter(LocationManager.PROVIDERS_CHANGED_ACTION)
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) { gpsEnabled = checkGps() }
        }
        context.registerReceiver(receiver, filter)
        onDispose { context.unregisterReceiver(receiver) }
    }

    LaunchedEffect(teamLoaded, equipe) {
        if (!teamLoaded) return@LaunchedEffect
        try {
            val hasLocationPermission = androidx.core.content.ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_FINE_LOCATION
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED
            if (hasLocationPermission) {
                val serviceIntent = Intent(context, com.chicoeletro.dds.core.services.GpsMonitorService::class.java).apply {
                    putExtra("equipe", equipe)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(serviceIntent)
                else context.startService(serviceIntent)
            }
        } catch (e: Exception) { Log.e("GpsMonitor", "Erro ao iniciar servico", e) }
    }

    var capturedPhotoUri by remember { mutableStateOf<Uri?>(null) }
    var capturedThumbUri by remember { mutableStateOf<Uri?>(null) }
    var abrirCamera by remember { mutableStateOf(false) }
    var tempoInicioDDS by remember { mutableStateOf<Long?>(null) }

    var showPresenceReport by rememberSaveable { mutableStateOf(false) }
    var showDdsWarning by rememberSaveable { mutableStateOf(false) }
    var presenceReportAccessed by rememberSaveable { mutableStateOf(false) }

    var versionStatus by remember { mutableStateOf(VersionStatus.UP_TO_DATE) }
    var modoTesteAtivo by rememberSaveable { mutableStateOf(false) }
    var cliqueLogo by remember { mutableStateOf(0) }

    val auth = remember { FirebaseAuth.getInstance() }
    var currentUser by remember { mutableStateOf<FirebaseUser?>(auth.currentUser) }

    DisposableEffect(auth) {
        val listener = FirebaseAuth.AuthStateListener { firebaseAuth -> currentUser = firebaseAuth.currentUser }
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
    var pendingTeamChange by remember { mutableStateOf<PendingTeamChange?>(null) }
    var pendingRequestId by rememberSaveable { mutableStateOf<String?>(null) }
    val requestRepo = remember { TeamChangeRequestRepository() }

    LaunchedEffect(pendingRequestId) {
        val rid = pendingRequestId ?: return@LaunchedEffect
        requestRepo.observeRequest(rid).collect { req ->
            if (req?.status == "APPROVED") {
                pendingRequestId = null
                requestRepo.deleteRequest(rid)
            } else if (req?.status == "REJECTED") {
                val oldName = req.oldPrefix
                val currentName = req.newPrefix
                if (req.reason == "VEHICLE_CHANGE") {
                    TrainingExecLocalStore.migrateTeam(context, currentName, oldName)
                    FormDataStore.migrateTeam(context, currentName, oldName)
                } else {
                    TrainingExecLocalStore.clearLocalOnly(context, currentName)
                }
                teamSync.savePendingLocal(context, oldName, eletricistas, lastTeamData?.workSchedule ?: com.chicoeletro.dds.core.WorkSchedule(), lastTeamData?.teamType, motorista, coringas)
                equipe = oldName
                pendingRequestId = null
                Toast.makeText(context, "ALTERAÇÃO REJEITADA PELO MONITOR!", Toast.LENGTH_LONG).show()
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
                motorista = data.motorista
                coringas = data.coringas
            }
        }
    }

    LaunchedEffect(lastTeamData) {
        val data = lastTeamData ?: return@LaunchedEffect
        if (data.equipe.isBlank()) return@LaunchedEffect
        val workManager = WorkManager.getInstance(context)
        val turnoRequest = PeriodicWorkRequestBuilder<TurnoReminderWorker>(1, TimeUnit.HOURS).build()
        workManager.enqueueUniquePeriodicWork("turno_periodic_check", ExistingPeriodicWorkPolicy.UPDATE, turnoRequest)

        val now = Calendar.getInstance()
        val target = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, data.workStartHour)
            set(Calendar.MINUTE, 0)
            if (before(now)) add(Calendar.DAY_OF_YEAR, 1)
        }
        val ddsRequest = OneTimeWorkRequestBuilder<DdsReminderWorker>().setInitialDelay(target.timeInMillis - now.timeInMillis, TimeUnit.MILLISECONDS).build()
        workManager.enqueueUniqueWork("dds_daily_check", ExistingWorkPolicy.REPLACE, ddsRequest)
    }

    LaunchedEffect(online) {
        turnoViewModel.refresh()
        teamSync.tryPushPending(context, online, lastTeamData)
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
        val regOut = commRepo.listenOutgoing(equipe) { msgs -> unreadOutgoingCount = msgs.count { it.status == "NÃO LIDO" } }
        onDispose { regIn.remove(); regOut.remove() }
    }

    LaunchedEffect(teamLoaded, lastTeamData, isInitializing) {
        if (!teamLoaded || isInitializing) return@LaunchedEffect
        if (lastTeamData?.equipe.isNullOrBlank() || lastTeamData?.eletricistas.isNullOrEmpty() || lastTeamData?.motorista.isNullOrBlank() || lastTeamData?.teamType.isNullOrBlank()) {
            teamDialogMandatory = true
            showEditDialog = true
        }
    }

    LaunchedEffect(selectedTraining, equipe) {
        submissaoExistente = null
        if (!selectedTraining.isNullOrBlank() && equipe.isNotBlank()) {
            FormDataStore.getAllSubmissions(context).collect { lista ->
                submissaoExistente = lista.find { it.equipe.equals(equipe.trim(), true) && it.trainingName == selectedTraining }
            }
        }
    }

    LaunchedEffect(Unit) { VersionChecker.checkPlayStoreStatus(context) { versionStatus = it } }

    val today = LocalDate.now()
    val last7Due = trainings.filter { t -> com.chicoeletro.dds.ui.training.trainingIsoDateFromId(t.id)?.let { d -> !d.isAfter(today) } ?: false }.sortedByDescending { it.id }.take(7)
    val allDone = last7Due.isEmpty() || last7Due.all { it.id in trainingStatus }
    val bubbleColor = when {
        unreadIncomingCount > 0 -> Color.Red
        unreadOutgoingCount > 0 -> Color(0xFF2E7D32)
        !allDone -> Color(0xFFFFC107)
        else -> Color.Gray
    }

    val headerParticipationDays = remember(selectedTraining, trainings, trainingStatus) {
        buildMonthParticipationDays(
            selectedTrainingId = selectedTraining,
            trainings = trainings,
            completedTrainingIds = trainingStatus.keys,
            today = LocalDate.now()
        )
    }

    Box(Modifier.fillMaxSize()) {
        if (isInitializing) {
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.5f)), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                HeaderBar(
                    overlayAlpha = if (showForm) 0.1f else 1f,
                    selectedTraining = selectedTraining,
                    isInDdsModule = navController.currentDestination?.route?.startsWith("dds") == true,
                    monthParticipationDays = headerParticipationDays,
                    showTestCameraButton = modoTesteAtivo,
                    onTestCameraClick = { if (modoTesteAtivo) showOnlineTest = true },
                    onCommunicationClick = { showCommunicationDialog = true },
                    bubbleColor = bubbleColor,
                    onBack = { if (navController.previousBackStackEntry != null) navController.popBackStack() },
                    isInTurnoModule = navController.currentDestination?.route == "turno"
                )

                NavHost(navController = navController, startDestination = "home", modifier = Modifier.weight(1f)) {
                    composable("home") {
                        HomeSection(
                            trainingViewModel = trainingViewModel,
                            turnoViewModel = turnoViewModel,
                            equipe = equipe,
                            eletricistas = eletricistas,
                            motorista = motorista,
                            coringas = coringas,
                            teamType = lastTeamData?.teamType,
                            unreadIncomingCount = unreadIncomingCount,
                            onClickEquipe = { showEditDialog = true },
                            onDdsClick = { navController.navigate("dds") },
                            onTurnoClick = { if (equipe.isBlank()) showEditDialog = true else navController.navigate("turno") },
                            onProducaoClick = { showPresenceReport = true },
                            onMensagensClick = { showCommunicationDialog = true },
                            onAbastecimentoClick = { showAbastecimento = true }
                        )
                    }
                    composable("turno") {
                        TurnoSection(
                            turnoViewModel = turnoViewModel,
                            equipe = equipe,
                            eletricistas = eletricistas,
                            isOnline = online,
                            teamType = lastTeamData?.teamType,
                            onDismiss = { navController.popBackStack() },
                            onClickEquipe = { showEditDialog = true },
                            onSaveTeamType = { type -> scope.launch { teamSync.saveTeamTypeLocal(context, type) } }
                        )
                    }
                    composable("dds") {
                        DdsSection(
                            trainingViewModel = trainingViewModel,
                            syncViewModel = syncViewModel,
                            networkViewModel = networkViewModel,
                            equipe = equipe,
                            eletricistas = eletricistas,
                            isTablet = isTablet,
                            onHome = { navController.navigate("home") },
                            onPresenceReport = { showPresenceReport = true },
                            onClickEquipe = { showEditDialog = true },
                            onClickTurno = { navController.navigate("turno") },
                            turnoEstado = turnoSnap.estado,
                            turnoNocSs = turnoSnap.nocSs,
                            selectedTraining = selectedTraining,
                            onSelectTraining = { tid -> selectedTraining = tid; tempoInicioDDS = System.currentTimeMillis() },
                            onOpenForm = { if (equipe.isBlank()) showEditDialog = true else { abrirCamera = true } },
                            onEnterAgora = {
                                val targetId = selectedTraining ?: return@DdsSection
                                val sessionIsoDate = targetId.substringBefore(" - ").trim()
                                val title = targetId.substringAfter(" - ").trim()
                                val session = activeSessions.find { s ->
                                    val parts = s.date.split("/")
                                    val formattedDate = if (parts.size == 3) "${parts[2]}-${parts[1]}-${parts[0]}" else s.date
                                    val isDateMatch = formattedDate == sessionIsoDate
                                    val extractedTime = com.chicoeletro.dds.ui.training.parseDdsOnlineTime(title)
                                    val isMatch = if (extractedTime != null) s.time == extractedTime else s.subject.trim().equals(title, ignoreCase = true)
                                    isDateMatch && isMatch
                                }
                                if (session != null) {
                                    val isHost = session.roles.hostTeams.any { it.equals(equipe, ignoreCase = true) }
                                    if (session.status == "active") {
                                        if (session.channelName.isNotBlank()) activeSessionChannel = session.channelName
                                        else Toast.makeText(context, "Erro: Canal não configurado.", Toast.LENGTH_SHORT).show()
                                    } else if (isHost) showOrganizerDialog = session
                                    else Toast.makeText(context, "Reunião ainda não foi aberta.", Toast.LENGTH_SHORT).show()
                                } else Toast.makeText(context, "Sessão não encontrada.", Toast.LENGTH_SHORT).show()
                            }
                        )
                    }
                }

                com.chicoeletro.dds.components.FooterVersion(status = null, isTestVersion = versionStatus == VersionStatus.TEST_VERSION)
            }

            GlobalDialogs(
                context = context,
                scope = scope,
                equipe = equipe,
                eletricistas = eletricistas,
                motorista = motorista,
                coringas = coringas,
                lastTeamData = lastTeamData,
                onTeamUpdated = { name, members, schedule, teamType, driver, wildcards ->
                    if (equipe.isNotBlank() && equipe != name) {
                        pendingTeamChange = PendingTeamChange(name, members, schedule, teamType, driver, wildcards)
                        showReasonDialog = true
                    } else {
                        scope.launch {
                            teamSync.savePendingLocal(context, name, members, schedule, teamType, driver, wildcards)
                            equipe = name; eletricistas = members; motorista = driver; coringas = wildcards
                            showEditDialog = false
                        }
                    }
                },
                selectedTraining = selectedTraining,
                submissaoExistente = submissaoExistente,
                tempoInicioDDS = tempoInicioDDS,
                onCloseTraining = { selectedTraining = null },
                showEditDialog = showEditDialog,
                onDismissEditDialog = { showEditDialog = false },
                showReasonDialog = showReasonDialog,
                onDismissReasonDialog = { showReasonDialog = false },
                pendingTeamChange = pendingTeamChange,
                onConfirmTeamChange = { reason ->
                    val p = pendingTeamChange ?: return@GlobalDialogs
                    scope.launch {
                        if (reason == TeamChangeReason.VEHICLE_CHANGE) {
                            TrainingExecLocalStore.migrateTeam(context, equipe, p.name)
                            FormDataStore.migrateTeam(context, equipe, p.name)
                        } else TrainingExecLocalStore.clearLocalOnly(context, equipe)
                        teamSync.savePendingLocal(context, p.name, p.members, p.schedule, p.teamType, p.motorista, p.coringas)
                        equipe = p.name; eletricistas = p.members; motorista = p.motorista; coringas = p.coringas
                        pendingRequestId = requestRepo.createRequest(equipe, p.name, reason.name, "", "")
                        showReasonDialog = false; showEditDialog = false
                    }
                },
                showForm = showForm,
                onDismissForm = { showForm = false; capturedPhotoUri = null; capturedThumbUri = null },
                fotoUri = capturedPhotoUri,
                thumbUri = capturedThumbUri,
                setFotoUri = { uri -> capturedPhotoUri = uri },
                onTirarFoto = { abrirCamera = true },
                abrirCamera = abrirCamera,
                onCameraResult = { uri, thumbUri -> capturedPhotoUri = uri; capturedThumbUri = thumbUri; abrirCamera = false; showForm = selectedTraining != null },
                onCameraBack = { abrirCamera = false; if (selectedTraining != null) showForm = true },
                modoTesteAtivo = modoTesteAtivo,
                showOnlineTest = showOnlineTest,
                onDismissOnlineTest = { showOnlineTest = false },
                activeSessionChannel = activeSessionChannel,
                onDismissActiveSession = { activeSessionChannel = null },
                showOrganizerDialog = showOrganizerDialog,
                onDismissOrganizer = { showOrganizerDialog = null },
                isStartingMeeting = isStartingMeeting,
                onStartMeeting = { session ->
                    scope.launch {
                        try {
                            isStartingMeeting = true
                            meetingRepo.updateSessionStatus(session.id, "active")
                            showOrganizerDialog = null
                            activeSessionChannel = session.channelName
                        } finally { isStartingMeeting = false }
                    }
                },
                showPresenceReport = showPresenceReport,
                onDismissPresenceReport = { showPresenceReport = false },
                versionStatus = versionStatus,
                onDismissVersionUpdate = { versionStatus = VersionStatus.UP_TO_DATE },
                gpsEnabled = gpsEnabled,
                pendingCrashReport = pendingCrashReport,
                onDismissCrashReport = { pendingCrashReport = null }
            )
        }
    }
}
