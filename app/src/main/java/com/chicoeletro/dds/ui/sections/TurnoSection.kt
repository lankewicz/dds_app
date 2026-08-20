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
    empresa: String = "ChicoEletro", // Default por enquanto
    onDismiss: () -> Unit,
    onClickEquipe: () -> Unit,
    onSaveTeamType: (String) -> Unit
) {
    val turnoSnap by turnoViewModel.turnoSnapshot.collectAsState()
    val errorMessage by turnoViewModel.errorMessage.collectAsState()

    // No logic here, just bridge to the existing screen
    TurnoControlScreen(
        equipe = equipe,
        snapshot = turnoSnap,
        onDismiss = onDismiss,
        online = isOnline,
        teamType = teamType,
        onClickEquipe = onClickEquipe,
        onSaveNocSs = { noc ->
            turnoViewModel.atualizarNocSs(noc, empresa)
        },
        onRequestTransition = { req ->
            turnoViewModel.requestTransition(req, empresa, eletricistas, isOnline)
        }
    )

    // TODO: Handle errorMessage (Show a snackbar or dialog)
}
