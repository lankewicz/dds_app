// Módulo: app/src/main/java/com/chicoeletro/dds/ui/sections/MainLayoutContainer.kt
// Caminho completo: [PROJECT_ROOT]/app/src/main/java/com/chicoeletro/dds/ui/sections/MainLayoutContainer.kt
// Descrição: Container principal que gerencia a interface principal do aplicativo, incluindo:
//            1) Overlay de loading inicial até pré-carregamento off-line de dados e assets;
//            2) Exibição da lista de treinamentos disponíveis off-line;
//            3) Integração com FormScreen para envio de formulários;
//            4) Integração com ViewerScreen para visualização de conteúdo do treinamento;
//            5) Gerenciamento de estado de rede e cache local (equipe, submissões).
//            6) Barra lateral esquerda extraída (LeftSidebarSection) e Status do Turno (card + dialog) acima da Equipe.
//
// Autor: Valdinei Lankewicz
// Histórico de alterações:
//   - 30/06/2025: Removido suporte offline; simplificado para funcionar apenas online.
//   - 20/06/2025: Corrigidos imports e funções, retirada de referências obsoletas;
//   - 18/06/2025: Adicionada flag 'isInitializing' e overlay de carregamento full-screen;
//   - 18/06/2025: Integrado preloadAssets() no TrainingViewModel para download offline em lote;
//   - 18/06/2025: Feedback visual de seleção da lista (elevação e cor de fundo);
//   - 18/06/2025: Separação de responsabilidades em StorageTrainingRepository e TrainingViewModel;
//   - 06/06/2025: Refatorado para overlay full-screen do FormScreen;
//   - 05/06/2025: Migrado fetch de Firestore para Firebase Storage + DataStore;
//   - 02/06/2025: Versão inicial com fetch direto de Firestore.
//   - 12/11/2025: Atualização do layout
//   - 25/11/2025: Inserção Reunião Online (agora.io)
//   - 04/02/2026: Extraída a barra lateral esquerda para LeftSidebarSection; adicionado Status do Turno (card + dialog 4 botões) com base offline-first.
//

package com.chicoeletro.dds.ui.sections

import android.app.Application
import android.net.Uri
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
import com.chicoeletro.dds.features.team.TeamConfigSync
import com.chicoeletro.dds.features.team.TeamEditDialog
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.features.turno.TurnoStatus
import com.chicoeletro.dds.features.turno.TurnoStatusDialog
import com.chicoeletro.dds.features.turno.TurnoStatusSync
import com.chicoeletro.dds.features.viewer.ViewerScreen
import com.chicoeletro.dds.features.viewer.ViewerViewModel
import com.chicoeletro.dds.storage.ExecCacheEntry
import com.chicoeletro.dds.storage.FormDataStore
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.ui.sections.sidebar.LeftSidebarSection
import com.chicoeletro.dds.ui.training.isExpiredTrainingId
import com.chicoeletro.dds.ui.training.shouldShowTraining
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

data class TrainingStatus(
    val dataConclusao: String,
    val horaConclusao: String,
    val duracao: String
)

@Composable
fun MainLayoutContainer() {
    val context = LocalContext.current
    val application = context.applicationContext as Application
    val scope = rememberCoroutineScope()

    val trainingViewModel: TrainingViewModel = viewModel(factory = TrainingViewModelFactory(application))
    val networkViewModel: NetworkViewModel = viewModel()
    val syncViewModel: TrainingSyncViewModel = viewModel()

    val isInitializing by trainingViewModel.isInitializing.collectAsState(initial = true)
    val trainings by trainingViewModel.trainings.collectAsState(initial = emptyList())
    val online by networkViewModel.isOnline.collectAsState(initial = false)
    val syncState by syncViewModel.state.collectAsState()

    var selectedTraining by rememberSaveable { mutableStateOf<String?>(null) }
    var showForm by rememberSaveable { mutableStateOf(false) }
    var showEditDialog by remember { mutableStateOf(false) }
    var teamDialogMandatory by rememberSaveable { mutableStateOf(false) }

    // NOVO: garante que só validamos a equipe depois do 1º retorno do DataStore
    var teamLoaded by remember { mutableStateOf(false) }
    var lastTeamData by remember { mutableStateOf<LastTeamData?>(null) }
    val teamSync = remember { TeamConfigSync() }

    var submissaoExistente by remember { mutableStateOf<FormSubmission?>(null) }
    var equipe by rememberSaveable { mutableStateOf("") }
    var eletricistas by remember { mutableStateOf(listOf<String>()) }

    // ==========================================================
    // Status do Turno (offline-first + Firestore)
    // ==========================================================
    val turnoSync = remember { TurnoStatusSync() }
    var turnoStatus by rememberSaveable { mutableStateOf(TurnoStatus.FECHADO) }
    var turnoLastChangedAt by remember { mutableStateOf<String?>(null) }
    var turnoChangedAtIso by remember { mutableStateOf<String?>(null) }
    var turnoDeslocamentoMotivo by remember { mutableStateOf<String?>(null) }
    var turnoSsNoc by remember { mutableStateOf<String?>(null) }
    var turnoAttention by remember { mutableStateOf(false) }
    var showTurnoDialog by remember { mutableStateOf(false) }

    // Formatação local (evita depender de métodos que podem não existir no Sync)
    val turnoFmt = remember {
        DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm").withZone(ZoneId.systemDefault())
    }
    var capturedPhotoUri by remember { mutableStateOf<Uri?>(null) }
    var capturedThumbUri by remember { mutableStateOf<Uri?>(null) }
    var abrirCamera by remember { mutableStateOf(false) }
    var tempoInicioDDS by remember { mutableStateOf<Long?>(null) }
    // status de conclusão por treinamento
    var trainingStatus by remember { mutableStateOf<Map<String, TrainingStatus>>(emptyMap()) }
    var viewerStatus by remember { mutableStateOf<FooterStatus?>(null) }

    var showPresenceReport by rememberSaveable { mutableStateOf(false) }

    // Novo: controle de modo de operação
    var modoTesteAtivo by rememberSaveable { mutableStateOf(false) }
    var cliqueLogo by remember { mutableStateOf(0) }

     /**
     * Estado observado do usuário autenticado.
     *
     * IMPORTANTE:
     * - Não bloqueia UI
     * - Não muda fluxo
     * - Serve apenas como base para ações futuras
     */
    val auth = remember { FirebaseAuth.getInstance() }
    var currentUser by remember { mutableStateOf<FirebaseUser?>(auth.currentUser) }

    DisposableEffect(auth) {
        val listener = FirebaseAuth.AuthStateListener { firebaseAuth ->
            currentUser = firebaseAuth.currentUser
        }

        auth.addAuthStateListener(listener)
        onDispose {
            auth.removeAuthStateListener(listener)
        }
    }

    // ⚠️ Neste passo, currentUser NÃO é usado para condicionar telas
    // Ele apenas existe como estado observado para os próximos passos

    // agora.io
    var showOnlineTest by remember { mutableStateOf(false) }

    // ✅ Firestore: concluídos persistentes por equipe/mês
    val execRepo = remember { TeamTrainingExecutionRepository() }
    val currentMonth = remember { YearMonth.now() } // mês corrente (padrão do seu fluxo)
    val currentMonthId = remember(currentMonth) { currentMonth.toString() } // yyyy-MM
    val teamKey = remember(equipe) { TeamTrainingExecutionRepository.teamKeyOf(equipe) }

    // Listener: sempre que a equipe mudar, atualiza trainingStatus via Firestore
    // 1) Cache local: sempre que equipe/mês mudar, aplica imediatamente no estado.
    LaunchedEffect(teamKey, currentMonthId) {
        if (equipe.isBlank()) return@LaunchedEffect
        TrainingExecLocalStore
            .flowMonth(context, teamKey, currentMonthId)
            .collect { localMap ->
                trainingStatus = localMap.mapValues { (_, st) ->
                    TrainingStatus(
                        dataConclusao = st.dataConclusao,
                        horaConclusao = st.horaConclusao,
                        duracao = st.duracao
                        )
                    }
                }
        }

    // 2) Firestore: sobrepõe/atualiza cache local e UI (fonte de verdade).
    DisposableEffect(equipe, currentMonthId) {
        if (equipe.isBlank()) {
            trainingStatus = emptyMap()
            onDispose { }
        } else {
            val reg = execRepo.listenMonth(
                teamName = equipe,
                ym = currentMonth,
                onUpdate = { map ->
                    // converte para o formato já usado pela UI
                    val newStatus = map.mapValues { (_, st) ->
                        TrainingStatus(
                            dataConclusao = st.dataConclusao,
                            horaConclusao = st.horaConclusao,
                            duracao = st.duracao
                        )
                    }
                    trainingStatus = newStatus

                    // persiste no cache local para conferência offline
                    scope.launch {
                        val cache = map.mapValues { (_, st) ->
                            ExecCacheEntry(
                                dataConclusao = st.dataConclusao,
                                horaConclusao = st.horaConclusao,
                                duracao = st.duracao
                            )
                        }
                        TrainingExecLocalStore.saveMonth(
                            context = context,
                            teamKey = teamKey,
                            month = currentMonthId,
                            map = cache
                        )
                    }
                },
                onError = { /* opcional: log */ }
            )
            onDispose { reg.remove() }
        }
    }

    LaunchedEffect(context) {
        teamSync.observeLocal(context).collect { data ->
            lastTeamData = data
            teamLoaded = true

            if (data != null) {
                equipe = data.equipe
                eletricistas = data.eletricistas
            } else {
                equipe = ""
                eletricistas = emptyList()
            }
        }
    }


    // ==========================================================
    // Observa status do turno local por equipe
    // ==========================================================
    LaunchedEffect(teamLoaded, equipe) {
        if (!teamLoaded) return@LaunchedEffect
        if (equipe.isBlank()) return@LaunchedEffect

        turnoSync.observeLocal(context, equipe).collect { st ->
            if (st != null) {
                turnoStatus = st.status
                turnoLastChangedAt = st.changedAtUi

                turnoChangedAtIso = st.changedAtIso
                turnoDeslocamentoMotivo = st.deslocamentoMotivo
                turnoSsNoc = st.ssNoc
            } else {
                turnoStatus = TurnoStatus.FECHADO
                turnoLastChangedAt = null
                turnoChangedAtIso = null
                turnoAttention = false
                turnoDeslocamentoMotivo = null
                turnoSsNoc = null
            }
        }
    }

    // ==========================================================
    // Retry automático de equipe pendente (offline-first)
    // - Se a equipe foi salva localmente com pendingSync=true e a internet voltou,
    //   tenta enviar e limpar a pendência.
    // ==========================================================
    LaunchedEffect(online, teamLoaded, lastTeamData?.pendingSync, lastTeamData?.equipe) {
        if (!teamLoaded) return@LaunchedEffect
        teamSync.tryPushPending(context, online, lastTeamData)
    }

    // ==========================================================
    // Sempre carregar a formação mais recente (pull)
    // - Apenas quando online e NÃO há pendência local (não sobrescreve alterações locais).
    // ==========================================================
    LaunchedEffect(online, teamLoaded, lastTeamData?.equipe, lastTeamData?.pendingSync) {
        if (!teamLoaded) return@LaunchedEffect
        teamSync.pullLatestIfSafe(context, online, lastTeamData)
    }


    // ==========================================================
    // Retry / Pull do Status do Turno
    // ==========================================================
    LaunchedEffect(online, teamLoaded, equipe) {
        if (!teamLoaded) return@LaunchedEffect
        if (equipe.isBlank()) return@LaunchedEffect

        turnoSync.tryPushPending(context, online, equipe)
        // pullLatestIfSafe está com assinatura/escopo inconsistente no TurnoStatusSync.kt atual
        // (aparece como "Unresolved reference" aqui).
        // Vamos recolocar assim que corrigirmos o TurnoStatusSync.kt.
        // turnoSync.pullLatestIfSafe(context, online, equipe)
    }

    // ==========================================================
    // OBRIGATÓRIO: Ao iniciar o app, se não houver equipe definida,
    // forçar abertura do TeamEditDialog e impedir cancelamento.
    // ==========================================================
    LaunchedEffect(teamLoaded, lastTeamData, isInitializing) {
        // IMPORTANTE: não decidir nada antes do 1º retorno do DataStore
        if (!teamLoaded) return@LaunchedEffect
        if (isInitializing) return@LaunchedEffect

        val missingTeam =
            lastTeamData == null ||
            lastTeamData?.equipe.isNullOrBlank() ||
            lastTeamData?.eletricistas.isNullOrEmpty()

        if (missingTeam) {
            teamDialogMandatory = true
            showEditDialog = true
        } else {
            teamDialogMandatory = false
        }
    }

    val visibleTrainings = remember(trainings) {
        val today = LocalDate.now()
        trainings
            .filter { shouldShowTraining(it, today) }
            .sortedByDescending { t ->
                // preserva ordenação por data do ID quando possível
                runCatching { LocalDate.parse(t.id.substringBefore(" - "), DateTimeFormatter.ISO_LOCAL_DATE) }
                    .getOrElse { LocalDate.MIN }
            }
    }

    // ============================================================================
    // NOVO: Mapa (trainingId -> expirado?) calculado em memória
    // - Mantém treinamentos antigos visíveis
    // - Se expirado, o botão "Concluir" não deve aparecer (ver ajuste em FormScreen)
    // ============================================================================
    val trainingExpiryMap = remember(trainings) {
        val today = LocalDate.now()
        trainings.associate { t ->
            t.id to isExpiredTrainingId(t.id, today)
        }
    }

    // auto-sync uma vez quando estiver online (o guard agora está no SyncViewModel)
    LaunchedEffect(online) { syncViewModel.autoSyncIfNeeded(online) }

    // quando o sync terminar com sucesso, recarrega lista no TrainingViewModel
    LaunchedEffect(Unit) {
        syncViewModel.refreshRequests.collect {
            trainingViewModel.refreshTrainings()
        }
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
    LaunchedEffect(selectedTraining) {
        if (selectedTraining == null) {
            viewerStatus = null
        }
    }


    Box(Modifier.fillMaxSize()) {
        if (isInitializing) {
            Box(
                Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.5f)),
                contentAlignment = Alignment.Center
            ) {
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
                    showTestCameraButton = modoTesteAtivo,
                    onTestCameraClick = {
                        if (modoTesteAtivo) showOnlineTest = true
                    }
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
                        onPresenceReport = { showPresenceReport = true },
                        trainings = visibleTrainings,
                        selectedTraining = selectedTraining,
                        trainingStatus = trainingStatus,
                        onSelectTraining = { tid ->
                            selectedTraining = tid
                            tempoInicioDDS = System.currentTimeMillis()
                            showForm = false
                        },
                        // Equipe
                        equipe = equipe,
                        eletricistas = eletricistas,
                        onClickEquipe = {
                            teamDialogMandatory = false
                            showEditDialog = true
                        }
                    )
                    // Cor do modo teste permanece fixa para destaque (ou pode ser PrimaryDark, se preferir)
                    val fundoPainelDireito = if (modoTesteAtivo) Color(0xFF212121) else MaterialTheme.colorScheme.background

                    Box(
                        Modifier.weight(1f).fillMaxHeight().background(fundoPainelDireito).padding(8.dp)
                    ) {
                        if (selectedTraining == null) {
                            Column(
                                Modifier.fillMaxSize().padding(16.dp),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center
                            ) {
                                Image(
                                    painter = painterResource(id = R.drawable.dds),
                                    contentDescription = "Logo DDS",
                                    modifier = Modifier.fillMaxWidth(0.8f).padding(bottom = 24.dp).clickable {
                                        cliqueLogo++
                                        if (cliqueLogo >= 10) {
                                            modoTesteAtivo = !modoTesteAtivo

                                            // Se desativou o modo teste, garante que a tela de Agora fecha.
                                            if (!modoTesteAtivo) showOnlineTest = false

                                            cliqueLogo = 0
                                        }
                                    },
                                    contentScale = ContentScale.Fit
                                )
                                Row(Modifier.padding(top = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Selecione um treinamento", modifier = Modifier.size(32.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("Selecione um treinamento", style = MaterialTheme.typography.bodyLarge)
                                }
                            }
                        } else {
                            // Viewer: usa o ID selecionado + ViewModel local
                            val context = LocalContext.current
                            val viewerVM = remember { ViewerViewModel(context) }
                            val currentId = selectedTraining!! // garantido pelo if acima
                            val statusAtual = trainingStatus[currentId]

                            ViewerScreen(
                                trainingId = currentId,
                                viewModel  = viewerVM,
                                status     = statusAtual,
                                canConclude = !isExpiredTrainingId(currentId),
                                onOpenForm = {
                                    // NOVO: Se estiver expirado, não deixa iniciar fluxo de conclusão
                                    // (treinamento continua visível, mas não poderá "concluir")
                                    if (isExpiredTrainingId(currentId)) {
                                        // opcional: você pode setar alguma mensagem de status aqui,
                                        // mas evitamos mexer em FooterStatus para não gerar erro de assinatura.
                                        return@ViewerScreen
                                    }
                                    if (equipe.isBlank() || eletricistas.isEmpty()) {
                                        showEditDialog = true
                                    } else {
                                        abrirCamera = true
                                        showForm = false
                                    }
                                },
                                onStatusChanged = { st ->
                                    viewerStatus = st
                                }
                            )

                        }
                    }
                }
                FooterVersion(status = viewerStatus)
            }
            // === Editor de Equipe ===
            if (showEditDialog) {
                TeamEditDialog(
                    initialTeamName = equipe,
                    initialMembers  = eletricistas,

                    mandatory = teamDialogMandatory,
                    onDismiss = {
                        // Se for obrigatório, não permite sair sem salvar
                        if (!teamDialogMandatory) {
                            showEditDialog = false
                        }
                    },
                    onSave   = { name, members ->
                        // Salva primeiro; fecha depois de persistir
                        scope.launch {
                            // Offline-first: salva como pendente; módulo faz retry automático quando voltar internet
                            teamSync.savePendingLocal(context, name, members)
                            equipe = name
                            eletricistas = members
                            teamDialogMandatory = false
                            showEditDialog = false
                        }
                    }
                )
            }

            if (showForm) {
                // Bloqueia 'Back' enquanto o formulário estiver aberto
                androidx.activity.compose.BackHandler(enabled = true) { /* bloqueado */ }

                Dialog(
                    onDismissRequest = { /* bloqueado */ },
                    properties = DialogProperties(
                        dismissOnClickOutside = false,
                        dismissOnBackPress = false,
                        usePlatformDefaultWidth = false
                    )
                ) {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        shape = MaterialTheme.shapes.large
                    ) {
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
                                    // ALTERAÇÃO AQUI: Esconda o form para a câmera aparecer
                                    showForm = false
                                    abrirCamera = true
                                } else {
                                    capturedPhotoUri = uri
                                }
                            },
                            onBack = { showForm = false },
                            onSubmit = { submission, lastTeam ->
                                scope.launch {
                                    FormDataStore.saveSubmission(context, submission)
                                    teamSync.saveLocalCache(context, lastTeam)
                                    capturedPhotoUri = null
                                    capturedThumbUri = null
                                    // showForm = false
                                }
                            },
                            tempoInicioMillis = tempoInicioDDS,
                            modoTesteAtivo = modoTesteAtivo,

                            /*
                            🔹 Desativar CONCLUIR se:
                                - já foi concluído (trainingStatus contém id)
                                - ou está expirado (validade encerrada)
                            OBS: isso mantém o item visível na lista, mas remove o botão concluir.
                            🔹 Callback chamado depois que tudo deu certo
                            */
                            onCompleted = { data, hora, duracao ->
                                val tid = selectedTraining!!

                                // 1) Atualiza UI imediatamente (optimistic UI)
                                trainingStatus = trainingStatus.toMutableMap().apply {
                                    put(tid, TrainingStatus(data, hora, duracao))
                                }

                                // 2) Persiste no CACHE LOCAL (conferência offline garantida)
                                scope.launch {
                                    TrainingExecLocalStore.upsert(
                                        context = context,
                                        teamKey = teamKey,
                                        month = currentMonthId,
                                        trainingId = tid,
                                        entry = ExecCacheEntry(
                                            dataConclusao = data,
                                            horaConclusao = hora,
                                            duracao = duracao
                                        )
                                    )
                                }

                                // 3) Persiste no Firestore (fonte de verdade) — troca de tablet não perde
                                scope.launch {
                                    runCatching {
                                        execRepo.markExecuted(
                                            teamName = equipe,
                                            ym = currentMonth,
                                            trainingId = tid,
                                            dataConclusao = data,
                                            horaConclusao = hora,
                                            duracao = duracao,
                                            deviceModel = android.os.Build.MODEL
                                        )
                                    }
                                }

                                showForm = false   // 👈 Fecha o form
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
                        // ALTERAÇÃO AQUI: Câmera fechou, mostre o formulário
                        showForm = true
                    },
                    onBack = {
                        abrirCamera = false
                        // Se o usuário cancelou a câmera vindo do form,
                        // reabra o form.
                        if (selectedTraining != null) {
                            showForm = true
                        }
                    }
                )
            }

// 🔹 Novo: dialog de TESTE da reunião online
            if (modoTesteAtivo && showOnlineTest) {
                Dialog(
                    onDismissRequest = { showOnlineTest = false },
                    properties = DialogProperties(
                        dismissOnClickOutside = false,
                        dismissOnBackPress = true,
                        usePlatformDefaultWidth = false
                    )
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(MaterialTheme.colorScheme.background)
                    ) {
                        AgoraMeetingEntry(
                            appId = AgoraConfig.APP_ID,
                            channelName = AgoraConfig.CHANNEL_NAME,
                            tempToken = AgoraConfig.TEMP_TOKEN,
                            localUid = AgoraConfig.LOCAL_USER_ID,
                            presentationTitle = selectedTraining,
                            teamName = equipe,
                            teamMembers = eletricistas, // lista real vinda do TeamEditDialog
                            onLeave = { showOnlineTest = false }
                        )
                    }
                }
            }
        }
    }

    // ==========================================================
    // Dialog seleção do status desejado
    // ==========================================================
    if (showTurnoDialog) {
        TurnoStatusDialog(
            statusAtual = turnoStatus,
            ssNocAtual = turnoSsNoc,
            onDismiss = { showTurnoDialog = false },
            onConfirm = { novo, motivo, ssNoc ->
                showTurnoDialog = false

                // snapshot antes (para comparar)
                val prevStatus = turnoStatus
                val prevMotivo = turnoDeslocamentoMotivo
                val prevSsNoc = turnoSsNoc

                // normaliza
                val novoMotivo = motivo?.trim()?.takeIf { it.isNotBlank() }
                val novoSsNoc = ssNoc?.trim()?.takeIf { it.isNotBlank() }

                val changedStatus = (novo != prevStatus)
                val changedMotivo = (novoMotivo != prevMotivo)
                val changedSsNoc = (novoSsNoc != prevSsNoc)

                // Atualiza UI (status/motivo/ssnoc)
                if (changedStatus) turnoStatus = novo
                turnoDeslocamentoMotivo =
                    if (turnoStatus == TurnoStatus.DESLOCAMENTO_ESPECIAL) novoMotivo else null
                turnoSsNoc = novoSsNoc

                // Se houve qualquer alteração relevante, atualiza timestamps de UI
                if (changedStatus || changedMotivo || changedSsNoc) {
                    val now = Instant.now()
                    turnoLastChangedAt = turnoFmt.format(now)
                    turnoChangedAtIso = now.toString()
                }

                scope.launch {
                    val snapEquipe = equipe
                    val snapEletricistas = eletricistas.toList()

                    // 1️⃣ Salva local (offline-first)
                    turnoSync.setStatus(
                        context = context,
                        equipe = snapEquipe,
                        eletricistas = snapEletricistas,
                        novoStatus = novo,
                        deslocamentoMotivo = novoMotivo,
                        ssNoc = novoSsNoc
                    )

                    // 2️⃣ Tenta gravar no Firestore imediatamente (se online)
                    turnoSync.tryPushPending(
                        context = context,
                        online = online,
                        equipe = snapEquipe
                    )
                }
            }
        )
    }
}