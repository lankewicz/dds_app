// Módulo: app/src/main/java/com/chicoeletro/dds/features/viewer/ViewerViewModel.kt
// Função: ViewModel do visualizador de treinamentos. Gerencia o estado da aula, carrega 
//         conteúdo local/remoto e valida pré-requisitos para início do treinamento.
// Tecnologias: Android ViewModel, StateFlow, Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.viewer

import android.content.Context
import android.net.Uri
import android.os.FileObserver
import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import android.media.AudioManager
import android.media.ToneGenerator
import java.io.File
import java.util.UUID

data class ViewerUiState(
    val isLoading: Boolean = false,
    val images: List<Uri> = emptyList(),
    val error: String? = null,

    // ---- Sessão de treinamento / antifraude ----
    val started: Boolean = false,
    val sessionId: String = "",
    val dimBackground: Boolean = true,
    val currentIndex: Int = 0,
    val totalSlides: Int = 0,
    val visited: Set<Int> = emptySet(),
    val elapsedMs: Long = 0L,
    val canTakePhoto: Boolean = false,
    val blockMessage: String? = null,
    val invalidated: Boolean = false,
    val invalidateReason: String? = null,
    val inactivityWarning: Boolean = false,
    // status pós-conclusão (exibido na barra inferior)
    val conclusionInfo: String? = null
)

class ViewerViewModel(
    private val appContext: Context
) : ViewModel() {

    private val _ui = MutableStateFlow(ViewerUiState())
    val ui: StateFlow<ViewerUiState> = _ui.asStateFlow()

    private val allowedExts = setOf("jpg", "jpeg", "png", "webp")
    private var loadJob: Job? = null
    // ---- Temporizadores e estado antifraude ----
    private var ticker: Job? = null
    private var lastResumeMono: Long? = null
    private var activeAccumMs: Long = 0L

    private var slideStartMono: Long? = null
    private val perSlideAccum = mutableMapOf<Int, Long>() // slide -> ms

    private var inactivityJob: Job? = null
    private var lastInteractionMono: Long = SystemClock.elapsedRealtime()
    // horário de início em relógio “mundo real” (para FormScreen ou logs)
    var sessionStartWallMs: Long? = null
    private set

    // ---- Mensagens de bloqueio (TTL) ----
    private var blockJob: Job? = null
    private var blockSeq: Long = 0L

    private val toneGenerator = try {
        ToneGenerator(AudioManager.STREAM_ALARM, 80)
    } catch (_: Exception) {
        null
    }

    private companion object {
        const val MIN_TOTAL_MS = 120_000L      // 2 minutos
        const val MIN_FIRST_SLIDE_MS = 5_000L //5s primeiro Slide
        const val MIN_PER_SLIDE_MS = 10_000L   // 10s por slide
        const val MIN_OTHER_SLIDES_MS = 10_000L // 10s por slide
        const val MAX_SESSION_MS = 10 * 60 * 1000L // 10 min (Inatividade ou Total)
        const val WARNING_START_MS = 8 * 60 * 1000L // 8 min

        // Tempo de vida da mensagem na barra de status (evita “ficar preso” e reduz poluição visual).
        // Ajuste conforme UX desejada.
        const val BLOCK_MESSAGE_TTL_MS = 10_000L
    }

    /** Publica uma mensagem institucional de bloqueio e limpa automaticamente após TTL. */
    private fun showBlock(reason: BlockReason, remainSeconds: Long = 0L) {
        val msg = reason.message(remainSeconds)
        val seq = ++blockSeq
        blockJob?.cancel()
        _ui.update { it.copy(blockMessage = msg) }
        blockJob = viewModelScope.launch {
            delay(BLOCK_MESSAGE_TTL_MS)
            // Limpa somente se nada mais recente substituiu esta mensagem
            if (seq == blockSeq) {
                _ui.update { it.copy(blockMessage = null) }
            }
        }
    }


    fun load(trainingId: String) {
        _ui.update { it.copy(isLoading = true, error = null) }
        loadJob?.cancel()
        loadJob = viewModelScope.launch(Dispatchers.IO) {
            val images: List<Uri> = try {
                val folder = File(appContext.filesDir, "trainings/$trainingId")
                if (!folder.exists()) {
                    emptyList()
                } else {
                    scanImagesRecursively(folder)
                        .sortedWith(naturalFileComparator())
                        .map { Uri.fromFile(it) }
                        .toList()
                }
            } catch (_: Exception) {
                emptyList()
            }

            _ui.update {
                if (images.isEmpty())
                    it.copy(isLoading = false, images = emptyList(), error = "Sem conteúdo local para $trainingId")
                else
                    it.copy(isLoading = false, images = images, error = null)
            }
        }
    }

    fun observeFolder(trainingId: String) = callbackFlow<Unit> {
        val folder = File(appContext.filesDir, "trainings/$trainingId")
        if (!folder.exists()) folder.mkdirs()
        val observer = object : FileObserver(
            folder.path,
            CREATE or MOVED_TO or DELETE or MOVED_FROM
        ) {
            override fun onEvent(event: Int, path: String?) {
                trySend(Unit).isSuccess
            }
        }
        observer.startWatching()
        awaitClose { observer.stopWatching() }
    }

    /** Comparator "natural": compara números como números e texto como texto, posição a posição. */
    private fun naturalFileComparator(): Comparator<File> = Comparator { a, b ->
        naturalCompare(naturalKey(a.name), naturalKey(b.name))
    }

    private fun naturalKey(name: String): List<Any> {
        val parts = mutableListOf<Any>()
        var i = 0
        while (i < name.length) {
            val c = name[i]
            if (c.isDigit()) {
                var j = i
                while (j < name.length && name[j].isDigit()) j++
                parts += name.substring(i, j).toLong()
                i = j
            } else {
                var j = i
                while (j < name.length && !name[j].isDigit()) j++
                parts += name.substring(i, j).lowercase()
                i = j
            }
        }
        return parts
    }
    private fun scanImagesRecursively(root: File): Sequence<File> {
        // BFS leve, sem custo de recursão profunda
        val stack = ArrayDeque<File>()
        stack.add(root)
        val out = mutableListOf<File>()
        while (stack.isNotEmpty()) {
            val dir = stack.removeFirst()
            val children = dir.listFiles() ?: continue
            for (f in children) {
                if (f.isDirectory) {
                    stack.add(f)
                } else if (f.extension.lowercase() in allowedExts) {
                    out += f
                }
            }
        }
        return out.asSequence()
    }

    private fun naturalCompare(a: List<Any>, b: List<Any>): Int {
        val n = minOf(a.size, b.size)
        for (i in 0 until n) {
            val x = a[i]; val y = b[i]
            val cmp = when {
                x is Long && y is Long -> x.compareTo(y)
                x is String && y is String -> x.compareTo(y)
                x is Long && y is String -> -1   // números antes de texto (ajuste se preferir)
                x is String && y is Long -> 1
                else -> 0
            }
            if (cmp != 0) return cmp
        }
        return a.size.compareTo(b.size)
    }

    // ============== LÓGICA DA SESSÃO DO TREINAMENTO ==============
    fun onStartPressed(totalSlides: Int) {
        val sessionId = UUID.randomUUID().toString()
        // reset total
        ticker?.cancel()
        inactivityJob?.cancel()
        lastResumeMono = null
        activeAccumMs = 0L
        // reset per-slide
        perSlideAccum.clear()
        slideStartMono = null

        _ui.update {
            it.copy(
                started = true,
                dimBackground = false,
                sessionId = sessionId,
                totalSlides = totalSlides,
                currentIndex = 0,
                visited = setOf(0),
                elapsedMs = 0L,
                canTakePhoto = false,
                blockMessage = null,
                invalidated = false,
                invalidateReason = null,
                conclusionInfo = null
            )
        }
        sessionStartWallMs = System.currentTimeMillis()
        resumeAll()
        startSlideTimer(0)
        resetInactivityWatchdog()
        checkGates()
    }

    /** Zera toda a sessão (usar ao trocar de treinamento). */
    fun resetSession() {
        loadJob?.cancel()
        pauseAll()
        blockJob?.cancel()
        activeAccumMs = 0L
        lastResumeMono = null
        slideStartMono = null
        perSlideAccum.clear()
        inactivityJob?.cancel()
        sessionStartWallMs = null
        _ui.update {
            it.copy(
                started = false,
                dimBackground = true,
                sessionId = "",
                currentIndex = 0,
                totalSlides = 0,
                visited = emptySet(),
                elapsedMs = 0L,
                canTakePhoto = false,
                blockMessage = null,
                invalidated = false,
                invalidateReason = null,
                images = emptyList(),
                error = null
            )
        }
    }

    /** Marca conclusão e preenche mensagem amigável para a barra de status. */
    fun markConcluded(equipe: String, whenMillis: Long = System.currentTimeMillis()) {
        val text = "Treinamento concluído pela equipe $equipe em ${formatDateBR(whenMillis)}"
        _ui.update { it.copy(conclusionInfo = text) }
    }

    private fun formatDateBR(millis: Long): String {
        // Usa fuso do dispositivo (normalmente America/Sao_Paulo)
        val z = java.time.ZoneId.systemDefault()
        val dt = java.time.Instant.ofEpochMilli(millis).atZone(z).toLocalDate()
        val dd = "%02d".format(dt.dayOfMonth)
        val mm = "%02d".format(dt.monthValue)
        val yyyy = dt.year
        return "$dd/$mm/$yyyy"
    }
    fun onAppForegroundChanged(isForeground: Boolean) {
        if (!_ui.value.started || _ui.value.invalidated) return
        if (isForeground) resumeAll() else pauseAll()
    }

    private fun minPerSlideMs(index: Int): Long {
        val total = _ui.value.totalSlides
        // O último slide não tem trava de tempo (exceto se for o único slide do DDS)
        if (total > 1 && index == total - 1) return 0L
        
        return if (index == 0) MIN_FIRST_SLIDE_MS else MIN_OTHER_SLIDES_MS
    }

    fun onWindowFocusChanged(hasFocus: Boolean) {
        if (!_ui.value.started || _ui.value.invalidated) return
        if (hasFocus) resumeAll() else pauseAll()
    }

    fun onUserInteraction() {
        lastInteractionMono = SystemClock.elapsedRealtime()
        resetInactivityWatchdog()
    }

    fun onSlideShown(index: Int) {
        if (!_ui.value.started || _ui.value.invalidated) return
        // trocar de slide "oficialmente"
        pauseSlideTimer()
        startSlideTimer(index)
        _ui.update { it.copy(currentIndex = index, visited = it.visited + index, blockMessage = null) }
        checkGates()
    }

    /** Navegação livre para treinamentos antigos (somente visualização, sem sessão/timers). */
    fun showSlideReadOnly(index: Int) {
        val total = _ui.value.images.size
        if (index !in 0 until total) return
        _ui.update { it.copy(currentIndex = index, blockMessage = null) }
    }



    /** Navegação controlada: não permite saltar > +1 e exige 10s no slide atual para avançar. */
    fun requestGoToSlide(target: Int): Boolean {
        if (!_ui.value.started) {
            // Mensagem institucional + TTL
            showBlock(BlockReason.NOT_STARTED)
            return false
        }
        if (_ui.value.invalidated) return false
        val current = _ui.value.currentIndex
        val total = _ui.value.totalSlides
        if (target !in 0 until total) return false

        // Voltar sempre pode
        if (target < current) {
            onSlideShown(target)
            return true
        }

        // ---- helpers para o UI ----
        fun secondsToAdvance(): Int {
            if (!_ui.value.started || _ui.value.invalidated) return Int.MAX_VALUE
            val dwell = currentSlideDwellMs()
            val remain = ((MIN_PER_SLIDE_MS - dwell + 999) / 1000).toInt()
            return kotlin.math.max(0, remain)
        }
        fun canAdvance(): Boolean = secondsToAdvance() == 0
        fun canConclude(): Boolean = _ui.value.canTakePhoto && !_ui.value.invalidated

        // Não saltar mais que +1
        if (target > current + 1) {
            showBlock(BlockReason.ORDER_ENFORCED)
            return false
        }
        // Precisa cumprir 10s no slide atual
        val dwell = currentSlideDwellMs()
        val required = minPerSlideMs(current)
        if (dwell < required) {
            val falta = ((required - dwell + 999) / 1000) // arredonda para cima
            val reason = if (current == 0) {
                BlockReason.MIN_DWELL_FIRST_SLIDE
            } else {
                BlockReason.MIN_DWELL_OTHER_SLIDE
            }
            showBlock(reason, falta)
            return false
        }
        onSlideShown(target)
        return true
    }

    // ---- timers ----
    private fun resumeAll() {
        resumeTotalTimer()
        resumeSlideTimer()
    }
    private fun pauseAll() {
        pauseTotalTimer()
        pauseSlideTimer()
    }
    private fun resumeTotalTimer() {
        if (lastResumeMono != null) return
        lastResumeMono = SystemClock.elapsedRealtime()
        ticker = viewModelScope.launch {
            while (isActive) {
                delay(250)
                val now = SystemClock.elapsedRealtime()
                val elapsed = activeAccumMs + (now - (lastResumeMono ?: now))
                _ui.update { it.copy(elapsedMs = elapsed) }
                
                if (elapsed >= MAX_SESSION_MS) {
                    invalidateSession("Tempo máximo de 10 minutos atingido.")
                }
                
                checkGates()
            }
        }
    }
    private fun pauseTotalTimer() {
        val now = SystemClock.elapsedRealtime()
        lastResumeMono?.let { activeAccumMs += (now - it) }
        lastResumeMono = null
        ticker?.cancel()
    }
    private fun startSlideTimer(index: Int) {
        slideStartMono = SystemClock.elapsedRealtime()
        _ui.update { it.copy(currentIndex = index) }
        onUserInteraction()
    }
    private fun resumeSlideTimer() {
        if (slideStartMono == null) slideStartMono = SystemClock.elapsedRealtime()
    }
    private fun pauseSlideTimer() {
        val now = SystemClock.elapsedRealtime()
        val start = slideStartMono ?: return
        val delta = now - start
        val idx = _ui.value.currentIndex
        perSlideAccum[idx] = (perSlideAccum[idx] ?: 0L) + kotlin.math.max(0L, delta)
        slideStartMono = null
    }
    private fun currentSlideDwellMs(): Long {
        val idx = _ui.value.currentIndex
        val acc = perSlideAccum[idx] ?: 0L
        val now = SystemClock.elapsedRealtime()
        val live = slideStartMono?.let { now - it } ?: 0L
        return acc + live
    }
    private fun allSlidesMeet10s(): Boolean {
        val total = _ui.value.totalSlides
        for (i in 0 until total) {
            val acc = perSlideAccum[i] ?: 0L
            val live = if (i == _ui.value.currentIndex && slideStartMono != null)
                SystemClock.elapsedRealtime() - (slideStartMono ?: 0L) else 0L
            val required = minPerSlideMs(i)
            if (acc + live < required) return false
        }
        return true
    }

    private fun checkGates() {
        val lastIndex = _ui.value.totalSlides - 1
        val allVisited = if (lastIndex < 0) false else (0..lastIndex).all { it in _ui.value.visited }
        val enoughTime = _ui.value.elapsedMs >= MIN_TOTAL_MS
        val each10s = allSlidesMeet10s()
        _ui.update { it.copy(canTakePhoto = allVisited && enoughTime && each10s) }
    }

    private fun resetInactivityWatchdog() {
        inactivityJob?.cancel()
        _ui.update { it.copy(inactivityWarning = false) }
        inactivityJob = viewModelScope.launch {
            var lastBeepMono = 0L
            while (isActive) {
                delay(5_000)
                val now = SystemClock.elapsedRealtime()
                val inactiveTime = now - lastInteractionMono
                val totalTime = _ui.value.elapsedMs
                
                if (inactiveTime >= MAX_SESSION_MS) {
                    invalidateSession("Inatividade por 10 minutos.")
                    break
                }
                
                if (inactiveTime >= WARNING_START_MS || totalTime >= WARNING_START_MS) {
                    _ui.update { it.copy(inactivityWarning = true) }
                    // Alerta sonoro a cada 20 segundos na fase crítica
                    if (now - lastBeepMono >= 20_000L) {
                        try {
                            toneGenerator?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 600)
                        } catch (_: Exception) {}
                        lastBeepMono = now
                    }
                } else {
                    if (_ui.value.inactivityWarning) {
                        _ui.update { it.copy(inactivityWarning = false) }
                    }
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        try {
            toneGenerator?.release()
        } catch (_: Exception) {}
    }
    private fun invalidateSession(reason: String) {
        pauseAll()
        _ui.update { it.copy(invalidated = true, invalidateReason = reason) }
    }
}