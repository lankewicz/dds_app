package com.chicoeletro.dds.ui.sections

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.chicoeletro.dds.features.turno.TurnoViewModel
import com.chicoeletro.dds.ui.components.TurnoControlScreen

@Composable
fun TurnoSection(
    turnoViewModel: TurnoViewModel,
    equipe: String,
    eletricistas: List<String>,
    isOnline: Boolean,
    teamType: String?,
    empresa: String = "ChicoEletro",
    onDismiss: () -> Unit,
    onClickEquipe: () -> Unit,
    onSaveTeamType: (String) -> Unit
) {
    val turnoSnap by turnoViewModel.turnoSnapshot.collectAsState()
    val errorMessage by turnoViewModel.errorMessage.collectAsState()
    val rotalogState by turnoViewModel.rotalogState.collectAsState()
    val rawDailyJson by turnoViewModel.rawDailyJson.collectAsState()

    TurnoControlScreen(
        equipe = equipe,
        snapshot = turnoSnap,
        onDismiss = onDismiss,
        online = isOnline,
        teamType = teamType,
        rotalogState = rotalogState,
        rawDailyJson = rawDailyJson,
        onClickEquipe = onClickEquipe,
        onSaveNocSs = { noc ->
            turnoViewModel.atualizarNocSs(noc, empresa)
        },
        onRequestTransition = { req ->
            turnoViewModel.requestTransition(req, empresa, eletricistas, isOnline)
        }
    )
}
