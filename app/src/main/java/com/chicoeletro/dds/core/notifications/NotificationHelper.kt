// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/NotificationHelper.kt
// Função: Gerenciador de notificações do Android. Responsável pela criação de canais, 
//         construção de intents/pending intents e disparo de alertas visuais e sonoros.
// Tecnologias: NotificationManager, PendingIntent, NotificationCompat.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.chicoeletro.dds.MainActivity
import com.chicoeletro.dds.R

object NotificationHelper {

    fun createNotificationChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ddsChannel = NotificationChannel(
                NotificationConfig.CHANNEL_DDS_ID,
                "Lembretes de DDS",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificações diárias sobre treinamentos pendentes."
            }

            val turnoChannel = NotificationChannel(
                NotificationConfig.CHANNEL_TURNO_ID,
                "Gestão de Turno",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alertas sobre jornada, intervalos e deslocamento."
            }

            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(ddsChannel)
            manager.createNotificationChannel(turnoChannel)
        }
    }

    fun showDdsNotification(context: Context, statusTurno: String) {
        val intent = Intent(context, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification = NotificationCompat.Builder(context, NotificationConfig.CHANNEL_DDS_ID)
            .setSmallIcon(R.drawable.dds) // Garantir que este ícone existe
            .setContentTitle("DDS Pendente!")
            .setContentText("Status do Turno: $statusTurno. Realize o treinamento de segurança de hoje!")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notify(context, NotificationConfig.NOTIFICATION_ID_DDS, notification)
    }

    fun showTurnoNotification(context: Context, title: String, message: String, isDeslocamento: Boolean = false) {
        val intent = Intent(context, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            context, 1, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(context, NotificationConfig.CHANNEL_TURNO_ID)
            .setSmallIcon(R.drawable.dds)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)

        if (isDeslocamento) {
            val stillIntent = Intent(context, NotificationReceiver::class.java).apply {
                action = NotificationConfig.ACTION_STILL_DISPLACING
            }
            val stillPending = PendingIntent.getBroadcast(
                context, 2, stillIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )

            val changeIntent = Intent(context, MainActivity::class.java).apply {
                putExtra("action", "change_status")
            }
            val changePending = PendingIntent.getActivity(
                context, 3, changeIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )

            builder.addAction(0, "Ainda em Deslocamento", stillPending)
            builder.addAction(0, "Mudar Status", changePending)
        }

        notify(context, NotificationConfig.NOTIFICATION_ID_TURNO, builder.build())
    }

    private fun notify(context: Context, id: Int, notification: android.app.Notification) {
        try {
            NotificationManagerCompat.from(context).notify(id, notification)
        } catch (e: SecurityException) {
            // Permissão POST_NOTIFICATIONS não concedida (Android 13+)
        }
    }
}