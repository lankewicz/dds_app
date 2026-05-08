// Módulo: app/src/main/java/com/chicoeletro/dds/core/notifications/NotificationConfig.kt
// Função: Centralização de constantes e identificadores do sistema de notificações. Define IDs 
//         de canais, categorias de alertas e códigos de transição para Intents.
// Tecnologias: Kotlin Constants.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.core.notifications

object NotificationConfig {
    // Identificadores de Canais
    const val CHANNEL_DDS_ID = "dds_reminder_channel"
    const val CHANNEL_TURNO_ID = "turno_reminder_channel"
    const val CHANNEL_COMM_ID = "comm_channel"

    // Horários e Limites Padrão (Fallback caso não definido na equipe)
    const val DEFAULT_WORK_START_HOUR = 7 // 07:00 AM
    const val DEFAULT_WORK_END_HOUR = 18   // 18:00 PM

    // Regras de Status do Turno (em horas)
    const val SHIFT_ABERTO_MAX_HOURS = 6   // Recomendar intervalo após 6h aberto
    const val SHIFT_INTERVALO_MAX_HOURS = 2 // Recomendar abrir turno após 2h em intervalo
    const val SHIFT_DESLOCAMENTO_INITIAL_HOURS = 12 // Alerta inicial após 12h em deslocamento
    const val SHIFT_DESLOCAMENTO_RETRY_HOURS = 3    // Repetir após 3h se confirmado "Ainda em deslocamento"

    // Regras de Interjornada (em horas)
    const val INTERJORNADA_NORMAL_HOURS = 11 // Descanso mínimo obrigatório (Art 66)
    const val INTERJORNADA_NAG_THRESHOLD = 16 // Avisar se estiver fechado há mais de 16h (Normal)
    const val INTERJORNADA_ART67_HOURS = 24  // Descanso semanal obrigatório (Art 67)

    // IDs de Notificação (estáticos para permitir substituição/atualização)
    const val NOTIFICATION_ID_DDS = 1001
    const val NOTIFICATION_ID_TURNO = 1002
    const val NOTIFICATION_ID_COMM = 1003

    // Intent Actions para botões de notificação
    const val ACTION_STILL_DISPLACING = "com.chicoeletro.dds.ACTION_STILL_DISPLACING"
    const val ACTION_CHANGE_STATUS = "com.chicoeletro.dds.ACTION_CHANGE_STATUS"
}

