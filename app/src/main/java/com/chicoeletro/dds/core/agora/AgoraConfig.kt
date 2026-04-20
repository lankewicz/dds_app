// Módulo: app/src/main/java/com/chicoeletro/dds/core/agora/AgoraConfig.kt
// Função: Centralização de configurações para integração com o SDK Agora e comunicação com o 
//         servidor de tokens (Render/CloudRun). Define IDs de canais e expiração de acessos.
// Tecnologias: Agora SDK, Retrofit, Kotlin Singleton.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:
//   - 09/12/2025: Criação inicial.
//   - 26/12/2025: Centralização do APP_ID e parâmetros do Token Server.

package com.chicoeletro.dds.core.agora

object AgoraConfig {

    // ─── Agora SDK ─────────────────────────────────────────────────────────────
    // App ID do projeto DDS-Online (público e seguro no app)
    const val APP_ID: String = "c42c8e5fd7de42d9bba62dcaec756e68"

    // ─── Configurações legadas de teste (mantidas para compatibilidade) ─────────
    // Token temporário (válido por tempo limitado). Em produção, sempre obter do backend.
    const val TEMP_TOKEN: String =
        "007eJxTYFgn+Os0E+PDbTnJvIknP25WXNezSH8u+95tAdNPxAY9S5+owJBsYpRskWqalmKekmpilGKZlJRoZpSSnJiabG5qlmpmsdXMIrMhkJHB/95ZFkYGCATxORhcXIJ1Q1x9AxgYADOMIb0="

    // Canal padrão usado nos testes
    const val CHANNEL_NAME: String = "DDS-TEMP"

    // UID local usado no joinChannel; 0 = Agora gera automaticamente no client
    const val LOCAL_USER_ID: Int = 0


    // ─── Token Server (Render) ────────────────────────────────────────────────
    // Base URL do token server. Retrofit exige terminar com "/".
    // Render:  https://dds-token-server.onrender.com/
    // CloudRun: https://dds-token-server-yjjsiftpma-uc.a.run.app//
    const val TOKEN_BASE_URL: String = "https://dds-token-server-yjjsiftpma-uc.a.run.app/"

    // API Key de proteção do endpoint de token (deve bater com o backend)
    const val TOKEN_SERVER_API_KEY: String = "uma-chave-bem-forte-aqui"

    // Expiração padrão do token (segundos)
    const val TOKEN_EXPIRE_SECONDS: Int = 3600
}