// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/NotificationReceiver.kt
// Função: Receiver global para interceptar ações do usuário em notificações. Encaminha eventos 
//         de 'Ainda em Deslocamento' ou abertura de telas para os respectivos controllers.
// Tecnologias: BroadcastReceiver, Intents.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class NotificationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            NotificationConfig.ACTION_STILL_DISPLACING -> {
                // Cancela a notificação atual
                val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
                manager.cancel(NotificationConfig.NOTIFICATION_ID_TURNO)

                // Agenda um re-aviso para daqui a X horas (conforme definido no config)
                val request = OneTimeWorkRequestBuilder<TurnoReminderWorker>()
                    .setInitialDelay(NotificationConfig.SHIFT_DESLOCAMENTO_RETRY_HOURS.toLong(), TimeUnit.HOURS)
                    .addTag("deslocamento_retry")
                    .build()

                WorkManager.getInstance(context).enqueue(request)
            }
        }
    }
}