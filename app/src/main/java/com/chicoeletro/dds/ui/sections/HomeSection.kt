package com.chicoeletro.dds.ui.sections

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import com.chicoeletro.dds.features.turno.TurnoViewModel
import com.chicoeletro.dds.ui.training.buildRollingParticipationDays
import com.chicoeletro.dds.viewmodel.TrainingViewModel
import java.time.LocalDate

@Composable
fun HomeSection(
    trainingViewModel: TrainingViewModel,
    turnoViewModel: TurnoViewModel,
    equipe: String,
    eletricistas: List<String>,
    motorista: String?,
    coringas: List<String>,
    teamType: String?,
    unreadIncomingCount: Int,
    onClickEquipe: () -> Unit,
    onDdsClick: () -> Unit,
    onTurnoClick: () -> Unit,
    onProducaoClick: () -> Unit,
    onMensagensClick: () -> Unit,
    onAbastecimentoClick: () -> Unit
) {
    val trainings by trainingViewModel.trainings.collectAsState(initial = emptyList())
    val trainingStatus by trainingViewModel.trainingStatus.collectAsState()

    val homeParticipationDays = remember(trainings, trainingStatus) {
        buildRollingParticipationDays(
            selectedTrainingId = null,
            trainings = trainings,
            completedTrainingIds = trainingStatus.keys,
            today = LocalDate.now(),
            numDays = 7
        )
    }

    val turnoSnap by turnoViewModel.turnoSnapshot.collectAsState()

    HomeScreen(
        equipe = equipe,
        eletricistas = eletricistas,
        motorista = motorista,
        coringas = coringas,
        monthParticipationDays = homeParticipationDays,
        turnoEstado = turnoSnap.estado,
        teamType = teamType,
        onClickEquipe = onClickEquipe,
        onDdsClick = onDdsClick,
        onTurnoClick = onTurnoClick,
        onProducaoClick = onProducaoClick,
        onMensagensClick = onMensagensClick,
        onAbastecimentoClick = onAbastecimentoClick,
        unreadIncomingCount = unreadIncomingCount
    )
}
