package com.chicoeletro.dds.core.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.location.LocationManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.chicoeletro.dds.R
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.Timestamp
import android.util.Log

import android.app.PendingIntent
import com.chicoeletro.dds.MainActivity

class GpsMonitorService : Service() {

    private var toneGenerator: ToneGenerator? = null
    private val handler = Handler(Looper.getMainLooper())
    private var isBeeping = false

    private var equipe: String = ""
    private var lastGpsState: Boolean? = null

    private val gpsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            checkGpsState()
        }
    }

    private val beepRunnable = object : Runnable {
        override fun run() {
            if (isBeeping) {
                try {
                    val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                    val maxVolume = audioManager.getStreamMaxVolume(AudioManager.STREAM_ALARM)
                    audioManager.setStreamVolume(AudioManager.STREAM_ALARM, maxVolume, 0)
                } catch (e: Exception) {
                    // Ignora falhas ao ajustar volume
                }

                try {
                    toneGenerator?.startTone(ToneGenerator.TONE_SUP_ERROR, 2500)
                } catch (e: Exception) {
                    // Ignora falhas de inicialização do gerador de tons
                }
                handler.postDelayed(this, 3000)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()

        try {
            toneGenerator = ToneGenerator(AudioManager.STREAM_ALARM, 100)
        } catch (e: Exception) {
            // Fallback caso falhe
        }

        createNotificationChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                createNotification(),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            )
        } else {
            startForeground(NOTIFICATION_ID, createNotification())
        }

        registerReceiver(gpsReceiver, IntentFilter(LocationManager.PROVIDERS_CHANGED_ACTION))

        // Executa primeira verificação imediatamente
        checkGpsState()
    }

    override fun onDestroy() {
        super.onDestroy()
        unregisterReceiver(gpsReceiver)
        hideOverlay()
        stopBeeping()
        try {
            toneGenerator?.release()
        } catch (_: Exception) {}
        handler.removeCallbacksAndMessages(null)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val eq = intent?.getStringExtra("equipe")
        if (!eq.isNullOrBlank()) {
            equipe = eq
        }
        checkGpsState()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    private fun checkGpsState() {
        val locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
        val isGpsEnabled = try {
            locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                    locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
        } catch (e: Exception) {
            Log.e("GpsMonitorService", "Erro ao verificar provedores de localizacao", e)
            false // Trata como desativado por segurança
        }

        val isShiftActive = if (equipe.isNotBlank()) {
            runCatching {
                val snap = com.chicoeletro.dds.features.turno.TurnoController(applicationContext, equipe).current()
                snap.isOpen && snap.estado != com.chicoeletro.dds.features.turno.EstadoTurno.FECHADO
            }.getOrDefault(false)
        } else false

        if (!isGpsEnabled && isShiftActive) {
            showOverlay()
            startBeeping()
        } else {
            hideOverlay()
            stopBeeping()
        }

        val oldState = lastGpsState
        if (oldState != isGpsEnabled) {
            lastGpsState = isGpsEnabled
            if (oldState != null) {
                logGpsEvent(if (isGpsEnabled) "RELIGADO" else "DESLIGADO")
            }
        }
    }

    private fun logGpsEvent(action: String) {
        if (equipe.isBlank()) return

        val db = FirebaseFirestore.getInstance()
        val locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
        var lat: Double? = null
        var lng: Double? = null
        var hasLocation = false

        try {
            val lastKnown = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                ?: locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
            if (lastKnown != null) {
                lat = lastKnown.latitude
                lng = lastKnown.longitude
                hasLocation = true
            }
        } catch (e: Exception) {
            Log.e("GpsMonitorService", "Erro ao obter ultima localizacao conhecida", e)
        }

        val logData = mapOf(
            "equipe" to equipe,
            "action" to action,
            "timestampMs" to System.currentTimeMillis(),
            "timestamp" to Timestamp.now(),
            "latitude" to lat,
            "longitude" to lng,
            "hasLocation" to hasLocation
        )

        db.collection("turno")
            .document("ChicoEletro")
            .collection("equipes")
            .document(equipe)
            .collection("gps_logs")
            .add(logData)
            .addOnSuccessListener {
                Log.d("GpsMonitorService", "Log de GPS ($action) gravado com sucesso no Firestore.")
            }
            .addOnFailureListener { e ->
                Log.w("GpsMonitorService", "Falha ao gravar log de GPS ($action): ${e.message}")
            }
    }

    private fun showOverlay() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val warningNotification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("GPS Desativado! 🚨")
            .setContentText("O GPS é importante para segurança e rastreamento em caso de perda ou roubo do aparelho. Ative para continuar.")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setFullScreenIntent(pendingIntent, true)
            .setAutoCancel(true)
            .build()

        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(WARNING_NOTIFICATION_ID, warningNotification)
    }

    private fun hideOverlay() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.cancel(WARNING_NOTIFICATION_ID)
    }

    private fun startBeeping() {
        if (isBeeping) return
        isBeeping = true
        handler.post(beepRunnable)
    }

    private fun stopBeeping() {
        isBeeping = false
        handler.removeCallbacks(beepRunnable)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Monitoramento de GPS (Segurança)",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Mantém a monitoria do GPS ativa durante o turno de trabalho."
            }
            val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Rastreamento de Turno Ativo")
            .setContentText("A localização está sendo monitorada para fins de segurança.")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val NOTIFICATION_ID = 9999
        private const val WARNING_NOTIFICATION_ID = 9998
        private const val CHANNEL_ID = "gps_monitor_service_channel"
    }
}
