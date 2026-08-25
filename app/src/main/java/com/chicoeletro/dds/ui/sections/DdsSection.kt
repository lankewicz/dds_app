package com.chicoeletro.dds.ui.sections

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.chicoeletro.dds.R
import com.chicoeletro.dds.features.viewer.ViewerScreen
import com.chicoeletro.dds.features.viewer.ViewerViewModel
import com.chicoeletro.dds.ui.sections.sidebar.LeftSidebarSection
import com.chicoeletro.dds.ui.training.shouldShowTraining
import com.chicoeletro.dds.viewmodel.TrainingViewModel
import com.chicoeletro.dds.viewmodel.TrainingSyncViewModel
import com.chicoeletro.dds.viewmodel.NetworkViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import androidx.compose.animation.core.*
import com.chicoeletro.dds.features.online.DdsSession
import com.chicoeletro.dds.ui.training.canConcludeTrainingId

@Composable
fun DdsSection(
    trainingViewModel: TrainingViewModel,
    syncViewModel: TrainingSyncViewModel,
    networkViewModel: NetworkViewModel,
    equipe: String,
    eletricistas: List<String>,
    isTablet: Boolean,
    onHome: () -> Unit,
    onPresenceReport: () -> Unit,
    onClickEquipe: () -> Unit,
    onClickTurno: () -> Unit,
    turnoEstado: com.chicoeletro.dds.features.turno.EstadoTurno,
    turnoNocSs: String?,
    selectedTraining: String?,
    onSelectTraining: (String?) -> Unit,
    onOpenForm: () -> Unit,
    onEnterAgora: () -> Unit
) {
    val context = LocalContext.current
    val trainings by trainingViewModel.trainings.collectAsState()
    val trainingStatus by trainingViewModel.trainingStatus.collectAsState()
    val online by networkViewModel.isOnline.collectAsState()
    val syncState by syncViewModel.state.collectAsState()

    val visibleTrainings = remember(trainings) {
        val today = LocalDate.now()
        trainings
            .filter { shouldShowTraining(it, today) }
            .sortedByDescending { t ->
                runCatching { LocalDate.parse(t.id.substringBefore(" - "), DateTimeFormatter.ISO_LOCAL_DATE) }
                    .getOrElse { LocalDate.MIN }
            }
    }

    Row(modifier = Modifier.fillMaxSize()) {
        LeftSidebarSection(
            widthDp = 220,
            modifier = Modifier.width(220.dp),
            online = online,
            isSyncing = syncState.isSyncing,
            overallTotal = syncState.overallTotal,
            overallDone = syncState.overallDone,
            plannedTrainingsTotal = syncState.plannedTrainingsTotal,
            currentTotal = syncState.currentTotal,
            currentDone = syncState.currentDone,
            currentId = syncState.currentId,
            onHome = onHome,
            onSyncNow = { syncViewModel.syncNow() },
            onPresenceReport = onPresenceReport,
            trainings = visibleTrainings,
            selectedTraining = selectedTraining,
            trainingStatus = trainingStatus,
            onSelectTraining = { tid -> onSelectTraining(tid) },
            presenceReportAccessed = false,
            turnoEstado = turnoEstado,
            turnoNocSs = turnoNocSs,
            onClickTurno = onClickTurno,
            equipe = equipe,
            eletricistas = eletricistas,
            onClickEquipe = onClickEquipe
        )

        Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
            if (selectedTraining != null) {
                val viewerVM = remember { ViewerViewModel(context) }
                ViewerScreen(
                    trainingId = selectedTraining,
                    viewModel = viewerVM,
                    status = trainingStatus[selectedTraining],
                    canConclude = canConcludeTrainingId(selectedTraining) && trainingStatus[selectedTraining] == null,
                    onOpenForm = onOpenForm,
                    onCloseViewer = { onSelectTraining(null) },
                    onEnterAgora = { onEnterAgora() },
                    onStatusChanged = { /* handle */ }
                )
            } else {
                DefaultDdsContent()
            }
        }
    }
}

@Composable
private fun DefaultDdsContent() {
    val arrowTransition = rememberInfiniteTransition(label = "arrow_bounce")
    val arrowOffset by arrowTransition.animateFloat(
        initialValue = 0f,
        targetValue = -12f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "arrow_offset"
    )

    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Image(
            painter = painterResource(id = R.drawable.dds),
            contentDescription = "Logo DDS",
            modifier = Modifier.fillMaxWidth(0.8f).padding(bottom = 24.dp),
            contentScale = ContentScale.Fit
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = null,
                modifier = Modifier
                    .size(32.dp)
                    .offset(x = arrowOffset.dp)
            )
            Spacer(Modifier.width(8.dp))
            Text("Selecione um treinamento", style = MaterialTheme.typography.bodyLarge)
        }
    }
}
