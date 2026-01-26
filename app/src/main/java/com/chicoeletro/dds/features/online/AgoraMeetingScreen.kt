package com.chicoeletro.dds.features.online

import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.util.Log
import android.view.SurfaceView
import android.view.ViewGroup
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import coil.compose.rememberAsyncImagePainter
import com.chicoeletro.dds.R
import com.chicoeletro.dds.core.agora.AgoraConfig
import com.chicoeletro.dds.features.online.token.TokenApiFactory
import com.chicoeletro.dds.features.online.token.TokenRequestDto
import com.chicoeletro.dds.ui.utils.KeepScreenOn
import io.agora.rtc2.ChannelMediaOptions
import io.agora.rtc2.Constants
import io.agora.rtc2.DataStreamConfig
import io.agora.rtc2.IRtcEngineEventHandler
import io.agora.rtc2.RtcEngine
import io.agora.rtc2.RtcEngineConfig
import io.agora.rtc2.video.VideoCanvas
import io.agora.rtc2.video.VideoEncoderConfiguration
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.HttpException
import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

enum class MeetingRole {
    HOST,
    COHOST,
    PARTICIPANT
}

private data class ParticipantInfo(
    val uid: Int,
    val teamName: String? = null,
    val members: List<String> = emptyList(),
    val joinedAt: Long = System.currentTimeMillis(),
    val lastSeenAt: Long = System.currentTimeMillis()
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AgoraMeetingEntry(
    appId: String,
    channelName: String,
    tempToken: String,
    localUid: Int = 0,
    presentationTitle: String? = null,
    teamName: String? = null,
    teamMembers: List<String> = emptyList(),
    onLeave: () -> Unit = {}

) {
    val context = LocalContext.current
    var hasPermissions by remember { mutableStateOf(false) }

    // ✅ UID fixo por sessão:
    // - O token RTC é gerado para um UID específico.
    // - Se o UID variar (ou ficar 0), o Agora pode rejeitar com Erro 110.
    val sessionUid = rememberSaveable(localUid) {
        if (localUid != 0) localUid else Random.nextInt(100_000, 999_999)
    }

    LaunchedEffect(Unit) {
        val cameraGranted = ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED

        val audioGranted = ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        hasPermissions = cameraGranted && audioGranted
    }
    if (hasPermissions) {
        AgoraMeetingScreen(
            appId = appId,
            channelName = channelName,
            tempToken = tempToken,
            localUid = sessionUid,
            presentationTitle = presentationTitle,
            teamName = teamName,
            teamMembers = teamMembers,
            onLeave = onLeave
        )
    } else {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                "Permissões de câmera e microfone não concedidas. Volte e conceda as permissões no início do app.",
                textAlign = TextAlign.Center
            )
        }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AgoraMeetingScreen(
    appId: String,
    channelName: String,
    tempToken: String,
    localUid: Int = 0,
    presentationTitle: String? = null,
    teamName: String? = null,
    teamMembers: List<String> = emptyList(),
    onLeave: () -> Unit = {}
) {
    // 🔒 Mantém a tela ligada enquanto ESTA tela estiver em primeiro plano
    KeepScreenOn(enabled = true)
    val context = LocalContext.current
    val colors = MaterialTheme.colorScheme
    val scope = rememberCoroutineScope()

    // Regra de negócio: somente TEAM1 é Host
    val isTeam1Host = remember(teamName) {
        teamName?.trim()?.equals("TEAM1", ignoreCase = true) == true
    }

    // Validação do App ID
    LaunchedEffect(appId) {
        if (appId.isBlank() || appId.length < 32) {
            Log.e("AgoraMeeting", "App ID inválido: $appId")
        } else {
            Log.d("AgoraMeeting", "App ID válido (${appId.length} caracteres)")
        }
    }

    val effectiveUid = localUid
    require(effectiveUid != 0) {
        "UID inválido (0). O UID deve ser fixo por sessão (gerado no AgoraMeetingEntry)."
    }

    var engine by remember { mutableStateOf<RtcEngine?>(null) }
    var initError by remember { mutableStateOf<String?>(null) }
    val participants = remember { mutableStateMapOf<Int, ParticipantInfo>() }
    var remoteVideoUid by remember { mutableStateOf<Int?>(null) }
    var joinOk by remember { mutableStateOf(false) }
    var showExitDialog by rememberSaveable { mutableStateOf(false) }
    var exitDraftCreated by rememberSaveable { mutableStateOf(false) }
    var photoRefreshNonce by rememberSaveable { mutableIntStateOf(0) }
    // 🔒 Evita duplo fechamento (idempotência)
    var isClosing by rememberSaveable { mutableStateOf(false) }

    var selectedRole by remember { mutableStateOf(if (isTeam1Host) MeetingRole.HOST else MeetingRole.PARTICIPANT) }
    var lastErrorCode by remember { mutableStateOf<Int?>(null) }
    var connectionState by remember { mutableStateOf<Int?>(null) }
    var connectionReason by remember { mutableStateOf<Int?>(null) }
    var isJoining by remember { mutableStateOf(false) }
    var tokenError by remember { mutableStateOf<String?>(null) }
    var dataStreamId by remember { mutableStateOf<Int?>(null) }

    // ===== Conclusão DDS Online (foto + form) =====
    // Reaproveita o mesmo padrão já usado no DDS "offline": CameraScreen -> Form -> salvar.
    var abrirCameraConclusao by remember { mutableStateOf(false) }
    var showFormConclusao by remember { mutableStateOf(false) }
    var capturedPhotoUri by remember { mutableStateOf<Uri?>(null) }
    var capturedThumbUri by remember { mutableStateOf<Uri?>(null) }
    var isSavingConclusion by remember { mutableStateOf(false) }
    var conclusionError by remember { mutableStateOf<String?>(null) }
    var conclusionSaved by remember { mutableStateOf(false) }

    val conclusionRepo = remember { OnlineConclusionRepository() }

    // Presença (Firestore) — fonte de verdade para lista de presença
    val sessionId = channelName
    val presenceWriter = remember { PresenceFirestore() }
    var presenceHeartbeatJob by remember { mutableStateOf<Job?>(null) }

    // Fecha a tela de forma consistente (encerra canal + presença + navega) — idempotente
    fun requestLeaveAndClose() {
        if (isClosing) return
        isClosing = true
        scope.launch {
            try {
                joinOk = false
                presenceHeartbeatJob?.cancel()

                // registra saída (best effort)
                try {
                    presenceWriter.leave(sessionId)
                } catch (e: Exception) {
                    Log.w("AgoraMeeting", "Falha ao registrar LEAVE no Firestore: ${e.message}")
                }

                // encerra canal (best effort)
                try {
                    engine?.leaveChannel()
                } catch (e: Exception) {
                    Log.w("AgoraMeeting", "Falha ao leaveChannel: ${e.message}")
                }
            } finally {
                onLeave()
            }
        }
    }

    // Força a regra: se NÃO é TEAM1, sempre PARTICIPANT (mesmo se tentar mudar)
    LaunchedEffect(isTeam1Host) {
        if (!isTeam1Host && selectedRole != MeetingRole.PARTICIPANT) {
            selectedRole = MeetingRole.PARTICIPANT
        }
    }

    // Mensagens de erro (UX)
    fun agoraErrorMessage(code: Int): String {
        return when (code) {
            // 1052: threads de áudio não conseguem ser agendadas por CPU alta
            1052 -> "Erro 1052: CPU alta/áudio sobrecarregado. Feche apps em segundo plano, aguarde o aparelho resfriar e tente novamente."

            // Casos comuns de credenciais/canal (mantém orientação antiga)
            101 -> "Erro 101: App ID inválido. Verifique se o App ID do app e o do token são do mesmo projeto."
            102 -> "Erro 102: Nome do canal inválido. Evite espaços e caracteres especiais; use um identificador simples."
            110 -> "Erro 110: Token inválido/expirado. Gere um novo token e tente novamente."

            // Permissões/dispositivo
            9 -> "Erro 9: Permissões insuficientes. Verifique acesso à câmera e ao microfone nas configurações do Android."

            // Recursos/concorrência (muito comuns no tablet)
            19 -> "Erro 19: Recursos já em uso (câmera/microfone). Feche outros apps que estejam usando áudio/vídeo e tente novamente."
            22 -> "Erro 22: Recursos insuficientes no dispositivo. Feche apps, reduza carga do aparelho e tente novamente."
            1323 -> "Erro 1323: Sem dispositivo de áudio disponível. Verifique volume/rota de áudio (Bluetooth) e reinicie o teste."

            // Chamadas repetidas (throttling)
            20 -> "Erro 20: Requisições em excesso. Aguarde alguns segundos e tente novamente."

            // Genérico
            else -> "Falha do Agora (código: $code). Verifique rede e tente novamente."

        }
    }

    fun MeetingRole.toServerRole(): String =
        when (this) {
            // ✅ Alinha com o Token Server: enum estrito (host/cohost/participant)
            MeetingRole.HOST -> "host"
            MeetingRole.COHOST -> "cohost"
            MeetingRole.PARTICIPANT -> "participant"
        }

    fun MeetingRole.toAgoraClientRoleType(): Int =
        when (this) {
            MeetingRole.HOST,
            MeetingRole.COHOST -> Constants.CLIENT_ROLE_BROADCASTER
            MeetingRole.PARTICIPANT -> Constants.CLIENT_ROLE_AUDIENCE
        }

    fun sendHelloTeamProfile() {
        val e = engine ?: run {
            Log.w("AgoraMeeting", "Tentativa de enviar hello mas engine é null")
            return
        }
        val sid = dataStreamId ?: run {
            Log.w("AgoraMeeting", "Tentativa de enviar hello mas dataStreamId é null")
            return
        }
        val tname = (teamName ?: "").trim()
        if (tname.isEmpty()) return

        try {
            val membersClean = teamMembers.map { it.trim() }.filter { it.isNotBlank() }
            val payload = JSONObject()
                .put("type", "hello")
                .put("team", tname)
                .put("members", JSONArray(membersClean))
                .put("ts", System.currentTimeMillis())
                .toString()

            val bytes = payload.toByteArray(Charsets.UTF_8)
            val res = e.sendStreamMessage(sid, bytes)
            Log.d("AgoraMeeting", "sendHelloTeamProfile stream=$sid res=$res team=$tname members=${membersClean.size}")
        } catch (ex: Exception) {
            Log.e("AgoraMeeting", "Falha ao enviar hello(teamName): ${ex.message}", ex)
        }
    }

    // Heartbeat: garante presença/contagem mesmo quando callbacks do Agora não refletem todos os "audience".
    LaunchedEffect(joinOk, dataStreamId, engine, showExitDialog) {
        if (!joinOk) return@LaunchedEffect
        if (engine == null) return@LaunchedEffect
        if (dataStreamId == null) return@LaunchedEffect

        // Se o dialog de saída estiver aberto, pause o "hello" para reduzir ruído
        if (showExitDialog) return@LaunchedEffect

        // envia hello periódico
        while (isActive) {
            sendHelloTeamProfile()

            // cleanup de participantes "stale" (não vistos há 15s)
            val now = System.currentTimeMillis()
            val staleCutoff = now - 20_000L
            val toRemove = participants.values
                .filter { it.uid != effectiveUid && it.lastSeenAt < staleCutoff }
                .map { it.uid }

            toRemove.forEach { uid ->
                participants.remove(uid)
                if (remoteVideoUid == uid) {
                    remoteVideoUid = participants.keys.firstOrNull { it != effectiveUid }
                }
            }

            kotlinx.coroutines.delay(5_000L)
        }
    }
    LaunchedEffect(selectedRole, engine) {
        val e = engine ?: return@LaunchedEffect

        when (selectedRole) {
            MeetingRole.HOST,
            MeetingRole.COHOST -> {
                e.muteLocalVideoStream(false)
                e.muteLocalAudioStream(false)
            }
            MeetingRole.PARTICIPANT -> {
                e.muteLocalVideoStream(true)
                e.muteLocalAudioStream(true)
            }
        }
    }

    // Inicialização da Engine com tratamento completo de erros
    LaunchedEffect(Unit) {
        Log.d("AgoraMeeting", "=== INICIANDO CONFIGURAÇÃO AGORA ===")
        Log.d("AgoraMeeting", "App ID: ${appId.take(8)}... (${appId.length} chars)")
        Log.d("AgoraMeeting", "Channel: $channelName")
        Log.d("AgoraMeeting", "UID: $effectiveUid")
        Log.d("AgoraMeeting", "Role: $selectedRole")

        // Validações iniciais
        if (appId.isBlank()) {
            initError = "App ID não pode estar vazio"
            Log.e("AgoraMeeting", "ERRO: App ID vazio")
            return@LaunchedEffect
        }

        if (channelName.isBlank()) {
            initError = "Nome do canal não pode estar vazio"
            Log.e("AgoraMeeting", "ERRO: Canal vazio")
            return@LaunchedEffect
        }

        val config = RtcEngineConfig().apply {
            mContext = context.applicationContext
            mAppId = appId
            mEventHandler = object : IRtcEngineEventHandler() {

                override fun onJoinChannelSuccess(channel: String?, uid: Int, elapsed: Int) {
                    Log.d("AgoraMeeting", "✅ onJoinChannelSuccess: channel=$channel uid=$uid elapsed=$elapsed")
                    scope.launch {
                        joinOk = true
                        lastErrorCode = null
                        tokenError = null

                        // --- PRESENÇA (Firestore) ---
                        try {
                            presenceWriter.join(
                                sessionId = sessionId,
                                displayName = teamName?.trim().takeUnless { it.isNullOrBlank() } ?: "Participante",
                                role = selectedRole.name
                            )
                        } catch (e: Exception) {
                            Log.e("AgoraMeeting", "Falha ao registrar JOIN no Firestore: ${e.message}", e)
                        }

                        // Heartbeat (20s) — mantém lastSeenAt atualizado (robusto para quedas)
                        presenceHeartbeatJob?.cancel()
                        presenceHeartbeatJob = scope.launch {
                            while (joinOk) {
                                try {
                                    presenceWriter.heartbeat(sessionId)
                                } catch (e: Exception) {
                                    Log.w("AgoraMeeting", "Falha no heartbeat: ${e.message}")
                                }
                                delay(20_000L)
                            }
                        }

                        // Inclui o usuário local na lista/contagem (antes só remotos)
                        participants[effectiveUid] = ParticipantInfo(
                            uid = effectiveUid,
                            teamName = teamName?.trim().takeUnless { it.isNullOrBlank() },
                            members = teamMembers.map { it.trim() }.filter { it.isNotBlank() },
                            lastSeenAt = System.currentTimeMillis()
                        )
                        sendHelloTeamProfile()
                    }
                }


                override fun onUserJoined(uid: Int, elapsed: Int) {
                    Log.d("AgoraMeeting", "👤 onUserJoined: uid=$uid elapsed=$elapsed")
                    scope.launch {
                        val old = participants[uid]
                        participants[uid] = ParticipantInfo(
                            uid = uid,
                            teamName = old?.teamName,
                            members = old?.members ?: emptyList(),
                            lastSeenAt = System.currentTimeMillis()
                        )
                        if (remoteVideoUid == null) {
                            remoteVideoUid = uid
                            Log.d("AgoraMeeting", "Definindo remoteVideoUid: $uid")
                        }
                        // Não assume que o primeiro remoto tem vídeo (pode ser ouvinte).
                        // remoteVideoUid será priorizado quando chegar o "hello" do TEAM1.
                        if (remoteVideoUid == null) remoteVideoUid = uid
                    }
                }

                override fun onUserOffline(uid: Int, reason: Int) {
                    Log.d("AgoraMeeting", "👋 onUserOffline: uid=$uid reason=$reason")
                    scope.launch {
                        participants.remove(uid)
                        if (remoteVideoUid == uid) {
                            remoteVideoUid = participants.keys.firstOrNull { it != effectiveUid }
                            Log.d("AgoraMeeting", "Novo remoteVideoUid: $remoteVideoUid")
                        }
                    }
                }

                override fun onError(err: Int) {
                    Log.e("AgoraMeeting", "❌ onError: code=$err")
                    scope.launch { lastErrorCode = err }
                }

                override fun onConnectionStateChanged(state: Int, reason: Int) {
                    val stateStr = when(state) {
                        1 -> "DISCONNECTED"
                        2 -> "CONNECTING"
                        3 -> "CONNECTED"
                        4 -> "RECONNECTING"
                        5 -> "FAILED"
                        else -> "UNKNOWN($state)"
                    }
                    Log.d("AgoraMeeting", "🔌 onConnectionStateChanged: state=$stateStr reason=$reason")
                    scope.launch {
                        connectionState = state
                        connectionReason = reason
                    }
                }

                override fun onStreamMessage(uid: Int, streamId: Int, data: ByteArray?) {
                    if (data == null) return
                    try {
                        val msg = String(data, Charsets.UTF_8)
                        val json = JSONObject(msg)
                        val type = json.optString("type", "")
                        if (type == "hello") {
                            val tname = json.optString("team", "").trim().ifEmpty { null }
                            val members = json.optJSONArray("members")?.let { arr ->
                                List(arr.length()) { i -> arr.optString(i).trim() }
                                    .filter { it.isNotBlank() }
                            } ?: emptyList()

                            scope.launch {
                                val old = participants[uid] ?: ParticipantInfo(uid = uid)
                                participants[uid] = old.copy(
                                    teamName = tname ?: old.teamName,
                                    members = if (members.isNotEmpty()) members else old.members,
                                    lastSeenAt = System.currentTimeMillis()

                                )

                                // Regra: ouvintes devem ver o vídeo do HOST (TEAM1).
                                // Assim, ao receber o profile do TEAM1, priorizamos esse UID como vídeo remoto.
                                if (tname != null && tname.equals("TEAM1", ignoreCase = true)) {
                                    remoteVideoUid = uid
                                    Log.d("AgoraMeeting", "✅ Definindo remoteVideoUid como HOST (TEAM1): $uid")
                                }

                                Log.d(
                                    "AgoraMeeting",
                                    "Recebido profile para uid=$uid team=${tname ?: old.teamName} members=${(if (members.isNotEmpty()) members else old.members).size}"
                                )
                            }
                        }
                    } catch (ex: Exception) {
                        Log.e("AgoraMeeting", "onStreamMessage parse error: ${ex.message}", ex)
                    }
                }

                override fun onTokenPrivilegeWillExpire(token: String?) {
                    Log.d("AgoraMeeting", "🔑 onTokenPrivilegeWillExpire, renovando token...")
                    scope.launch {
                        val eng = engine ?: return@launch
                        try {
                            //val userAccount = "DDS:${teamName ?: "NO_TEAM"}:$effectiveUid"

                            val newTokenResponse = withContext(Dispatchers.IO) {
                                TokenApiFactory.api.getCombinedToken(
                                    TokenRequestDto(
                                        channel = channelName,
                                        uid = effectiveUid,
                                        role = selectedRole.toServerRole(),
                                        expire_seconds = AgoraConfig.TOKEN_EXPIRE_SECONDS,
                                        api_key = AgoraConfig.TOKEN_SERVER_API_KEY.trim()
                                    )
                                )
                            }

                            eng.renewToken(newTokenResponse.rtc_token)
                            // 🔜 futuro: rtmClient.renewToken(newTokenResponse.rtm_token)

                            tokenError = null
                            Log.d("AgoraMeeting", "✅ Token RTC renovado com sucesso")
                        } catch (e: Exception) {
                            val httpDetails = if (e is HttpException) {
                                val body = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
                                "HTTP ${e.code()} | errorBody=$body"
                            } else null

                            Log.e("AgoraMeeting", "❌ Erro ao renovar token: ${httpDetails ?: e.message}", e)
                            tokenError = "Falha ao renovar token: ${httpDetails ?: e.message}"
                        }
                    }
                }

            }
        }

        // Criação do RtcEngine com tratamento robusto
        val rtcEngine = try {
            Log.d("AgoraMeeting", "Tentando criar RtcEngine...")
            val eng = RtcEngine.create(config)
            Log.d("AgoraMeeting", "✅ RtcEngine criado com sucesso!")
            eng
        } catch (e: Exception) {
            Log.e("AgoraMeeting", "❌ ERRO CRÍTICO ao criar RtcEngine", e)
            Log.e("AgoraMeeting", "Mensagem: ${e.message}")
            Log.e("AgoraMeeting", "Causa: ${e.cause}")
            Log.e("AgoraMeeting", "Stack trace: ${e.stackTraceToString()}")
            initError = "Falha ao iniciar vídeo (Agora): ${e.message}"
            return@LaunchedEffect
        }

        if (rtcEngine == null) {
            Log.e("AgoraMeeting", "❌ RtcEngine retornou NULL após criação")
            initError = "Engine retornou null (verifique App ID e configuração)"
            return@LaunchedEffect
        }

        engine = rtcEngine
        Log.d("AgoraMeeting", "Engine atribuído à variável de estado")

        try {
            // Configurações do canal
            Log.d("AgoraMeeting", "Configurando canal...")
            rtcEngine.setChannelProfile(Constants.CHANNEL_PROFILE_LIVE_BROADCASTING)
            rtcEngine.setClientRole(selectedRole.toAgoraClientRoleType())
            Log.d("AgoraMeeting", "✅ Canal configurado")

            // Configurações de vídeo
            Log.d("AgoraMeeting", "Habilitando vídeo...")
            rtcEngine.enableVideo()
            rtcEngine.setVideoEncoderConfiguration(
                VideoEncoderConfiguration(
                    VideoEncoderConfiguration.VD_640x360,
                    VideoEncoderConfiguration.FRAME_RATE.FRAME_RATE_FPS_15,
                    VideoEncoderConfiguration.STANDARD_BITRATE,
                    VideoEncoderConfiguration.ORIENTATION_MODE.ORIENTATION_MODE_ADAPTIVE
                )
            )
            // Preview só faz sentido para quem publica (HOST/COHOST).
            if (selectedRole != MeetingRole.PARTICIPANT) {
                rtcEngine.startPreview()
                Log.d("AgoraMeeting", "✅ Preview iniciado (broadcaster)")
            } else {
                Log.d("AgoraMeeting", "✅ Vídeo habilitado (ouvinte sem preview)")
            }

            // DataStream
            try {
                val dsConfig = DataStreamConfig().apply {
                    ordered = true
                    syncWithAudio = false
                }
                val sid = rtcEngine.createDataStream(dsConfig)
                dataStreamId = sid
                Log.d("AgoraMeeting", "✅ DataStream criado sid=$sid")
            } catch (ex: Exception) {
                Log.e("AgoraMeeting", "⚠️ Falha ao criar DataStream: ${ex.message}", ex)
            }

            // Busca token dinâmico e entra no canal
            Log.d("AgoraMeeting", "Obtendo token dinâmico...")
            isJoining = true
            try {
                val roleForServer = selectedRole.toServerRole()
                //val userAccount = "DDS:${teamName ?: "NO_TEAM"}:$effectiveUid"

                val tokenResponse = withContext(Dispatchers.IO) {
                    TokenApiFactory.api.getCombinedToken(
                        TokenRequestDto(
                            channel = channelName,
                            uid = effectiveUid,
                            role = roleForServer,
                            expire_seconds = AgoraConfig.TOKEN_EXPIRE_SECONDS,
                            api_key = AgoraConfig.TOKEN_SERVER_API_KEY.trim()
                        )
                    )
                }

                val rtcToken = tokenResponse.rtc_token
                val rtmToken = tokenResponse.rtm_token

                // ✅ DEBUG/ASSERT: garante que o token foi gerado para o MESMO channel/uid usados no join
                Log.d(
                    "AgoraMeeting",
                    "TOKEN DEBUG: resp.channel=${tokenResponse.channel} resp.uid=${tokenResponse.uid} resp.role=${tokenResponse.role} now=${tokenResponse.now} exp=${tokenResponse.expire_at}"
                )
                require(tokenResponse.channel == channelName) {
                    "Token server devolveu channel diferente: ${tokenResponse.channel} != $channelName"
                }
                require(tokenResponse.uid == effectiveUid) {
                    "Token server devolveu uid diferente: ${tokenResponse.uid} != $effectiveUid"
                }


                Log.d("AgoraMeeting", "RTC token recebido (${rtcToken.take(16)}...)")
                Log.d("AgoraMeeting", "RTM token recebido (${rtmToken.take(16)}...)")

                val options = ChannelMediaOptions().apply {
                    clientRoleType = selectedRole.toAgoraClientRoleType()
                }

                Log.d("AgoraMeeting", "Entrando no canal...")
                val joinResult = rtcEngine.joinChannel(
                    rtcToken,
                    channelName,
                    effectiveUid,
                    options
                )
                Log.d("AgoraMeeting", "joinChannel result = $joinResult")
                if (joinResult < 0) {
                    lastErrorCode = joinResult
                    Log.e("AgoraMeeting", "❌ Erro ao entrar no canal: $joinResult")
                } else {
                    Log.d("AgoraMeeting", "✅ joinChannel chamado com sucesso")
                }
            } catch (e: Exception) {
                // ✅ Log mais útil (inclusive em release): imprime errorBody do HTTP 4xx/5xx
                val httpDetails = if (e is HttpException) {
                    val body = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
                    "HTTP ${e.code()} | errorBody=$body"
                } else null

                Log.e(
                    "AgoraMeeting",
                    "❌ Erro ao obter token dinâmico: ${httpDetails ?: e.message}",
                    e
                )
                tokenError = "Falha ao obter token dinâmico: ${httpDetails ?: e.message}"
            } finally {
                isJoining = false
            }

        } catch (e: Exception) {
            Log.e("AgoraMeeting", "❌ Erro durante configuração: ${e.message}", e)
            initError = "Erro durante configuração: ${e.message}"
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            Log.d("AgoraMeeting", "🧹 Limpando recursos...")

            // Presença (Firestore): tenta fechar segmento antes de sair
            try {
                joinOk = false
                presenceHeartbeatJob?.cancel()
                scope.launch {
                    try {
                        presenceWriter.leave(sessionId)
                    } catch (e: Exception) {
                        Log.w("AgoraMeeting", "Falha ao registrar LEAVE no Firestore no onDispose: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                Log.w("AgoraMeeting", "Falha ao iniciar fechamento de presença no onDispose: ${e.message}")
            }

            try {
                engine?.leaveChannel()
                RtcEngine.destroy()
                engine = null
                Log.d("AgoraMeeting", "✅ Recursos limpos")
            } catch (e: Exception) {
                Log.e("AgoraMeeting", "Erro ao limpar recursos: ${e.message}", e)
            }
        }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = {
                    Image(
                        painter = painterResource(id = R.drawable.logo_chico),
                        contentDescription = "ChicoEletro",
                        modifier = Modifier
                            .padding(start = 12.dp)
                            .height(36.dp)
                            .aspectRatio(2f),
                        contentScale = ContentScale.Fit
                    )
                },
                title = {
                    Column {
                        Text(
                            text = "Teste Agora – $channelName",
                            style = MaterialTheme.typography.titleMedium,
                            color = colors.onSurface
                        )
                        if (presentationTitle != null) {
                            Text(
                                text = presentationTitle,
                                style = MaterialTheme.typography.bodySmall,
                                color = colors.onSurfaceVariant
                            )
                        }
                    }
                },
                actions = {
                    Column(
                        modifier = Modifier.padding(end = 10.dp),
                        horizontalAlignment = Alignment.End,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "Equipe",
                            style = MaterialTheme.typography.labelSmall,
                            color = colors.onSurfaceVariant
                        )
                        Text(
                            text = teamName ?: "Não definida",
                            style = MaterialTheme.typography.titleSmall,
                            color = colors.onSurface
                        )
                    }
                    Button(
                    onClick = {
                        // Abre dialog e cria rascunho no Firebase imediatamente (mesmo sem foto)
                        showExitDialog = true

                        if (!exitDraftCreated) {
                            scope.launch {
                                try {
                                    val form = OnlineConclusionForm(
                                        displayName = teamName?.trim().takeUnless { it.isNullOrBlank() } ?: "Participante",
                                        teamName = teamName?.trim(),
                                        role = selectedRole.name,
                                        sessionId = sessionId,
                                        presentationTitle = presentationTitle,
                                        notes = "",
                                        confirmPresence = true,
                                        confirmPhoto = false,
                                        deviceInfo = Build.MODEL
                                    )

                                    conclusionRepo.createDraftWithoutPhoto(
                                        sessionId = sessionId,
                                        form = form
                                    )
                                    exitDraftCreated = true
                                } catch (e: Exception) {
                                    Log.w("AgoraMeeting", "Falha ao criar rascunho de conclusão: ${e.message}", e)
                                }
                            }
                        }
                    },
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                        modifier = Modifier.padding(end = 12.dp),
                        // 🔒 Evita clique durante salvamento/fechamento
                        enabled = !isSavingConclusion && !isClosing

                    ) {
                        Text("Sair do teste")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            // STATUS (banner)
            val statusText: String
            val statusColor: Color
            when {
                initError != null -> {
                    statusText = "ERRO DE INICIALIZAÇÃO: $initError"
                    statusColor = colors.error
                }

                tokenError != null -> {
                    statusText = tokenError ?: ""
                    statusColor = colors.error
                }

                lastErrorCode != null -> {
                    val code = lastErrorCode!!
                    statusText = agoraErrorMessage(code)
                    statusColor = colors.error
                }

                isJoining -> {
                    statusText = "Obtendo token e conectando ao canal…"
                    statusColor = colors.onSurfaceVariant
                }

                joinOk -> {
                    statusText =
                        "Conectado • UID local: $effectiveUid • Conectados: ${participants.size}"
                    statusColor = colors.onSurfaceVariant
                }

                else -> {
                    statusText = "Preparando conexão…"
                    statusColor = colors.onSurfaceVariant
                }
            }

            Surface(
                shape = RoundedCornerShape(10.dp),
                color = colors.surfaceVariant,
                tonalElevation = 1.dp,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = statusText,
                    style = MaterialTheme.typography.bodySmall,
                    color = statusColor,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 10.dp)
                )

                // CORPO RESPONSIVO (tablet x celular)
                BoxWithConstraints(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                ) {
                    val isWide = maxWidth >= 900.dp

                    val videoContent: @Composable () -> Unit = {
                        val title =
                            if (selectedRole == MeetingRole.PARTICIPANT) "Apresentador" else "Você (apresentando)"

                        Column(modifier = Modifier.fillMaxSize()) {
                            Text(title, color = colors.onSurface)

                            Surface(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(top = 6.dp),
                                shape = RoundedCornerShape(12.dp),
                                color = colors.surfaceVariant,
                                tonalElevation = 1.dp
                            ) {
                                Box(Modifier.fillMaxSize()) {
                                    val currentEngine = engine
                                    when {
                                        currentEngine == null -> {
                                            Text(
                                                text = if (initError != null) "Erro na inicialização" else "Inicializando vídeo…",
                                                color = if (initError != null) colors.error else colors.onSurfaceVariant,
                                                modifier = Modifier.align(Alignment.Center)
                                            )
                                        }

                                        selectedRole != MeetingRole.PARTICIPANT -> {
                                            // ✅ Evita recriar SurfaceView em recomposições
                                            val localSurface = remember {
                                                SurfaceView(context).apply {
                                                    layoutParams = ViewGroup.LayoutParams(
                                                        ViewGroup.LayoutParams.MATCH_PARENT,
                                                        ViewGroup.LayoutParams.MATCH_PARENT
                                                    )
                                                }
                                            }
                                            AndroidView(
                                                modifier = Modifier.fillMaxSize(),
                                                factory = { localSurface },
                                                update = {
                                                    currentEngine.setupLocalVideo(
                                                        VideoCanvas(
                                                            it,
                                                            VideoCanvas.RENDER_MODE_HIDDEN,
                                                            effectiveUid
                                                        )
                                                    )
                                                }
                                            )
                                        }

                                        else -> {
                                            val rUid = remoteVideoUid
                                            if (rUid != null) {
                                                // ✅ SurfaceView remoto por UID (mais estável)
                                                val remoteSurface = remember(rUid) {
                                                    SurfaceView(context).apply {
                                                        layoutParams = ViewGroup.LayoutParams(
                                                            ViewGroup.LayoutParams.MATCH_PARENT,
                                                            ViewGroup.LayoutParams.MATCH_PARENT
                                                        )
                                                    }
                                                }
                                                AndroidView(
                                                    modifier = Modifier.fillMaxSize(),
                                                    factory = { remoteSurface },
                                                    update = {
                                                        currentEngine.setupRemoteVideo(
                                                            VideoCanvas(
                                                                it,
                                                                VideoCanvas.RENDER_MODE_HIDDEN,
                                                                rUid
                                                            )
                                                        )
                                                    }
                                                )
                                            } else {
                                                Text(
                                                    text = "Aguardando o apresentador entrar no canal…",
                                                    color = colors.onSurfaceVariant,
                                                    modifier = Modifier
                                                        .align(Alignment.Center)
                                                        .padding(12.dp),
                                                    textAlign = TextAlign.Center
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    val participantsContent: @Composable () -> Unit = {
                        val header =
                            if (selectedRole == MeetingRole.PARTICIPANT) "Conectados" else "Ouvintes conectados"
                        val itemsList = participants.values.sortedByDescending { it.joinedAt }

                        Column(modifier = Modifier.fillMaxSize()) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(header, color = colors.onSurface)
                                Text(
                                    text = "Total: ${itemsList.size}",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = colors.onSurfaceVariant
                                )
                            }

                            Surface(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(top = 6.dp),
                                shape = RoundedCornerShape(12.dp),
                                color = colors.surfaceVariant,
                                tonalElevation = 1.dp
                            ) {
                                if (itemsList.isEmpty()) {
                                    Box(
                                        Modifier.fillMaxSize(),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            text = "Nenhum participante ainda.",
                                            color = colors.onSurfaceVariant,
                                            textAlign = TextAlign.Center,
                                            modifier = Modifier.padding(12.dp)
                                        )
                                    }
                                } else {
                                    LazyColumn(
                                        modifier = Modifier
                                            .fillMaxSize()
                                            .padding(10.dp),
                                        verticalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        items(itemsList, key = { it.uid }) { p ->
                                            Surface(
                                                shape = RoundedCornerShape(12.dp),
                                                color = colors.surface,
                                                tonalElevation = 1.dp,
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Column(Modifier.padding(12.dp)) {
                                                    Text(
                                                        text = "Equipe: ${p.teamName ?: "não informada"}",
                                                        style = MaterialTheme.typography.titleSmall,
                                                        color = colors.onSurface
                                                    )

                                                    val integrantes = if (p.members.isNotEmpty()) {
                                                        p.members.joinToString(separator = " • ")
                                                    } else {
                                                        "não informados"
                                                    }

                                                    Text(
                                                        text = "Integrantes: $integrantes",
                                                        style = MaterialTheme.typography.bodySmall,
                                                        color = colors.onSurfaceVariant,
                                                        modifier = Modifier.padding(top = 4.dp)
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    if (isWide) {
                        Row(
                            modifier = Modifier.fillMaxSize(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Box(modifier = Modifier.weight(3f).fillMaxHeight()) { videoContent() }
                            Box(
                                modifier = Modifier.weight(2f).fillMaxHeight()
                            ) { participantsContent() }
                        }
                    } else {
                        Column(
                            modifier = Modifier.fillMaxSize(),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Box(modifier = Modifier.weight(3f).fillMaxWidth()) { videoContent() }
                            Box(
                                modifier = Modifier.weight(2f).fillMaxWidth()
                            ) { participantsContent() }
                        }
                    }
                }

            }
        }
    }

    // ======= MOSTRAR O DIALOG (ANTES ELE NUNCA ERA RENDERIZADO) =======
    if (showExitDialog) {
        val reportText = remember(channelName, teamName, participants) {
            buildDdsReportText(
                channelName = channelName,
                teamName = teamName,
                participants = participants
            )
        }

        DdsExitDialog(
            reportText = reportText,
            thumbUri = capturedThumbUri,
            photoRefreshNonce = photoRefreshNonce,
            isSaving = isSavingConclusion,
            errorText = conclusionError,
            onDismiss = {
                showExitDialog = false
            },
            onTakeOrUpdatePhoto = {
                // aqui você já tem o fluxo de camera/conclusão; mantive o gatilho simples
                abrirCameraConclusao = true
            },
            onConcluir = {
                // Se você quiser só sair, sem salvar nada, pode chamar direto requestLeaveAndClose()
                // Aqui deixo a conclusão como "salvar (se existir seu fluxo) e sair".
                scope.launch {
                    try {
                        isSavingConclusion = true
                        conclusionError = null

                        // Se você já tem um método que finaliza (com/sem foto), chame aqui.
                        // Exemplo (ajuste para o seu repo real):
                        // conclusionRepo.finalize(sessionId, capturedPhotoUri, form, ...)

                        conclusionSaved = true
                        showExitDialog = false
                        requestLeaveAndClose()
                    } catch (e: Exception) {
                        conclusionError = e.message ?: "Falha ao concluir"
                    } finally {
                        isSavingConclusion = false
                    }
                }
            }
        )
    }
}

@Composable
private fun DdsExitDialog(
    reportText: String,
    thumbUri: Uri?,
    photoRefreshNonce: Int,
    isSaving: Boolean,
    errorText: String?,
    onDismiss: () -> Unit,
    onTakeOrUpdatePhoto: () -> Unit,
    onConcluir: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Conclusão do DDS Online") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (thumbUri != null) {
                    key(thumbUri, photoRefreshNonce) {
                        Image(
                            painter = rememberAsyncImagePainter(thumbUri),
                            contentDescription = "Prévia da foto",
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(140.dp)
                                .clip(RoundedCornerShape(12.dp)),
                            contentScale = ContentScale.Crop
                        )
                    }
                } else {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(90.dp)
                    ) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text(
                                text = "Sem foto anexada (opcional).",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }

                if (!errorText.isNullOrBlank()) {
                    Text(
                        text = errorText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 160.dp, max = 320.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(12.dp)
                        .verticalScroll(rememberScrollState())
                ) {
                    Text(
                        text = reportText,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = onConcluir,
                enabled = !isSaving
            ) { Text("Concluir") }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = onDismiss) { Text("Cancelar") }
                OutlinedButton(onClick = onTakeOrUpdatePhoto) {
                    Text(if (thumbUri == null) "Tirar foto" else "Atualizar foto")
                }
            }
        }
    )
}

private fun buildDdsReportText(
    channelName: String,
    teamName: String?,
    participants: Map<Int, ParticipantInfo>
): String {
    val lista = participants.values
        .sortedByDescending { it.joinedAt }
        .joinToString("\n") { p ->
            val integrantes = if (p.members.isNotEmpty()) p.members.joinToString(" • ") else "não informados"
            "- ${p.teamName ?: "não informada"}: $integrantes"
        }

    return """
        Canal: $channelName
        Equipe local: ${teamName ?: "Não definida"}
        Total de conectados: ${participants.size}

        Participantes:
        $lista
    """.trimIndent()
}

@Composable
private fun RoleOption(
    label: String,
    role: MeetingRole,
    selectedRole: MeetingRole,
    enabled: Boolean = true,
    onSelected: (MeetingRole) -> Unit
) {
    val colors = MaterialTheme.colorScheme

    Row(
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(
            selected = (selectedRole == role),
            onClick = { if (enabled) onSelected(role) },
            enabled = enabled,
            colors = RadioButtonDefaults.colors(
                selectedColor = colors.primary,
                unselectedColor = colors.onSurface.copy(alpha = 0.7f),
                disabledSelectedColor = colors.primary.copy(alpha = 0.3f),
                disabledUnselectedColor = colors.onSurface.copy(alpha = 0.3f)
            )
        )
        Text(
            text = label,
            color = if (enabled) colors.onSurface else colors.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium
        )
    }
}