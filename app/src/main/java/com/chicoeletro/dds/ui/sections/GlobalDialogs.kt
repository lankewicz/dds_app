package com.chicoeletro.dds.ui.sections

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.chicoeletro.dds.core.LastTeamData
import com.chicoeletro.dds.core.agora.AgoraConfig
import com.chicoeletro.dds.core.version.VersionChecker
import com.chicoeletro.dds.core.version.VersionStatus
import com.chicoeletro.dds.data.FormSubmission
import com.chicoeletro.dds.features.Camera.CameraScreen
import com.chicoeletro.dds.features.form.FormScreen
import com.chicoeletro.dds.features.online.AgoraMeetingEntry
import com.chicoeletro.dds.features.online.DdsSession
import com.chicoeletro.dds.ui.components.TeamChangeReason
import com.chicoeletro.dds.ui.components.TeamChangeReasonDialog
import com.chicoeletro.dds.features.team.TeamEditDialog
import com.chicoeletro.dds.features.training.TeamTrainingExecutionRepository
import com.chicoeletro.dds.core.crash.CrashReport
import com.chicoeletro.dds.storage.FormDataStore
import com.chicoeletro.dds.storage.TrainingExecLocalStore
import com.chicoeletro.dds.storage.TrainingExecSyncState
import com.chicoeletro.dds.ui.components.UpdateBanner
import com.chicoeletro.dds.components.HeaderBarState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.time.YearMonth

@Composable
fun GlobalDialogs(
    context: Context,
    scope: CoroutineScope,
    // Team State
    equipe: String,
    eletricistas: List<String>,
    motorista: String?,
    coringas: List<String>,
    lastTeamData: LastTeamData?,
    onTeamUpdated: (String, List<String>, com.chicoeletro.dds.core.WorkSchedule, String?, String?, List<String>) -> Unit,
    // Training State
    selectedTraining: String?,
    submissaoExistente: FormSubmission?,
    tempoInicioDDS: Long?,
    onCloseTraining: () -> Unit = {},
    // Dialog Visibility
    showEditDialog: Boolean,
    onDismissEditDialog: () -> Unit,
    showReasonDialog: Boolean,
    onDismissReasonDialog: () -> Unit,
    pendingTeamChange: PendingTeamChange?,
    onConfirmTeamChange: (TeamChangeReason) -> Unit,
    showForm: Boolean,
    onDismissForm: () -> Unit,
    fotoUri: Uri? = null,
    thumbUri: Uri? = null,
    setFotoUri: (Uri?) -> Unit = {},
    onTirarFoto: () -> Unit = {},
    abrirCamera: Boolean,
    onCameraResult: (Uri, Uri?) -> Unit,
    onCameraBack: () -> Unit,
    // Agora / Online
    modoTesteAtivo: Boolean,
    showOnlineTest: Boolean,
    onDismissOnlineTest: () -> Unit,
    activeSessionChannel: String?,
    onDismissActiveSession: () -> Unit,
    showOrganizerDialog: DdsSession?,
    onDismissOrganizer: () -> Unit,
    isStartingMeeting: Boolean,
    onStartMeeting: (DdsSession) -> Unit,
    // Others
    showPresenceReport: Boolean,
    onDismissPresenceReport: () -> Unit,
    versionStatus: VersionStatus,
    onDismissVersionUpdate: () -> Unit,
    gpsEnabled: Boolean,
    pendingCrashReport: CrashReport?,
    onDismissCrashReport: () -> Unit
) {
    // 1. Crash Shield
    pendingCrashReport?.let { report ->
        com.chicoeletro.dds.ui.components.CrashReportDialog(
            report = report,
            onDismiss = onDismissCrashReport
        )
    }

    // 2. Team Edit
    if (showEditDialog) {
        TeamEditDialog(
            initialTeamName = equipe,
            initialMembers = eletricistas,
            initialTeamType = lastTeamData?.teamType,
            initialMotorista = motorista,
            initialCoringas = coringas,
            onDismiss = onDismissEditDialog,
            onSave = { name, members, schedule, teamType, driver, wildcards ->
                onTeamUpdated(name, members, schedule, teamType, driver, wildcards)
            }
        )
    }

    // 3. Team Change Reason
    if (showReasonDialog && pendingTeamChange != null) {
        TeamChangeReasonDialog(
            oldPrefix = equipe,
            newPrefix = pendingTeamChange.name,
            onCancel = onDismissReasonDialog,
            onConfirm = onConfirmTeamChange
        )
    }

    // 4. Form DDS
    if (showForm && selectedTraining != null) {
        Dialog(
            onDismissRequest = { },
            properties = DialogProperties(
                dismissOnClickOutside = false,
                dismissOnBackPress = false,
                usePlatformDefaultWidth = false
            )
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                shape = MaterialTheme.shapes.large
            ) {
                FormScreen(
                    trainingName = selectedTraining,
                    existing = submissaoExistente?.let { it to selectedTraining },
                    lastTeam = lastTeamData ?: LastTeamData(equipe, eletricistas),
                    headerDate = HeaderBarState.datePart,
                    headerTitle = HeaderBarState.titlePart,
                    fotoUri = fotoUri,
                    thumbUri = thumbUri,
                    scope = scope,
                    setFotoUri = setFotoUri,
                    onTirarFoto = onTirarFoto,
                    onBack = onDismissForm,
                    onSubmit = { submission, _ ->
                        scope.launch {
                            FormDataStore.saveSubmission(context, submission)
                        }
                    },
                    tempoInicioMillis = tempoInicioDDS,
                    modoTesteAtivo = modoTesteAtivo,
                    jaConcluido = submissaoExistente != null,
                    onCompleted = { d, h, dur ->
                        scope.launch {
                            TrainingExecLocalStore.upsert(
                                context,
                                TeamTrainingExecutionRepository.teamKeyOf(equipe),
                                YearMonth.now().toString(),
                                selectedTraining,
                                com.chicoeletro.dds.storage.ExecCacheEntry(d, h, dur, TrainingExecSyncState.LOCAL_ONLY)
                            )
                        }
                        onDismissForm()
                        onCloseTraining()
                    }
                )
            }
        }
    }

    // 5. Camera
    if (abrirCamera) {
        CameraScreen(
            onPhotoCaptured = onCameraResult,
            onBack = onCameraBack
        )
    }

    // 6. Online Meetings
    if (modoTesteAtivo && showOnlineTest) {
        Dialog(onDismissRequest = onDismissOnlineTest, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
                AgoraMeetingEntry(
                    appId = AgoraConfig.APP_ID, channelName = AgoraConfig.CHANNEL_NAME, tempToken = AgoraConfig.TEMP_TOKEN,
                    localUid = AgoraConfig.LOCAL_USER_ID, presentationTitle = selectedTraining, teamName = equipe, teamMembers = eletricistas,
                    onLeave = onDismissOnlineTest
                )
            }
        }
    }

    if (activeSessionChannel != null) {
        Dialog(onDismissRequest = onDismissActiveSession, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                AgoraMeetingEntry(
                    appId = AgoraConfig.APP_ID, channelName = activeSessionChannel, tempToken = AgoraConfig.TEMP_TOKEN,
                    localUid = AgoraConfig.LOCAL_USER_ID, presentationTitle = selectedTraining, teamName = equipe, teamMembers = eletricistas,
                    onLeave = onDismissActiveSession
                )
            }
        }
    }

    // 7. Organizer
    if (showOrganizerDialog != null) {
        val session = showOrganizerDialog
        AlertDialog(
            onDismissRequest = { if (!isStartingMeeting) onDismissOrganizer() },
            title = { Text("Organizador: Abrir Reunião") },
            text = {
                Column {
                    Text("Tema: ${session.subject}", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                    if (isStartingMeeting) { CircularProgressIndicator() }
                }
            },
            confirmButton = {
                Button(onClick = { onStartMeeting(session) }, enabled = !isStartingMeeting) { Text("Iniciar Agora") }
            },
            dismissButton = {
                OutlinedButton(onClick = onDismissOrganizer, enabled = !isStartingMeeting) { Text("Cancelar") }
            }
        )
    }

    // 8. Presence Report
    if (showPresenceReport) {
        com.chicoeletro.dds.ui.components.ProductionReportDialog(
            equipe = equipe,
            onDismiss = onDismissPresenceReport
        )
    }

    // 9. Update Banner
    if (versionStatus == VersionStatus.UPDATE_AVAILABLE) {
        UpdateBanner(
            onUpdateClick = {
                (context as? Activity)?.let { VersionChecker.startUpdateFlow(it, 999) }
            },
            onDismiss = { onDismissVersionUpdate() }
        )
    }

    // 10. GPS Warning
    if (!gpsEnabled) {
        Box(modifier = Modifier.fillMaxSize().background(Color(0xE6121212)), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                Icon(Icons.Filled.Warning, null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(64.dp))
                Text("GPS Desativado 🚨", style = MaterialTheme.typography.titleLarge, color = Color.White)
                Button(onClick = { context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("ATIVAR GPS") }
            }
        }
    }
}
