// Módulo: app/src/main/java/com/chicoeletro/dds/util/NetworkStatusObserver.kt
// Função: Funções utilitárias genéricas (formatação, rede, logs).
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.util

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Observa mudanças no estado de conectividade (online/offline).
 * Emite 'true' quando há internet e 'false' caso contrário.
 */
class NetworkStatusObserver(private val context: Context) {

    companion object {
        /**
         * Check imediato (sem Flow). Ideal para bloquear ações (ex.: botão Sincronizar).
         * Retorna true quando há rede ativa com Internet VALIDADA (evita Wi-Fi sem internet / captive portal).
         */
        fun isOnlineNow(context: Context): Boolean {
            val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
                ?: return false
            val activeNetwork = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(activeNetwork) ?: return false
            return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                   caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
    }

    /**
     * Retorna um Flow<Boolean> que emite:
     *  - true  → tem conexão com Internet
     *  - false → sem conexão
     */
    fun observe(): Flow<Boolean> = callbackFlow {
        // Obtém o ConnectivityManager do sistema
        val connectivityManager =
            context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

        // Callback para eventos de rede
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                trySend(checkNetwork(connectivityManager))
            }

            override fun onLost(network: Network) {
                trySend(checkNetwork(connectivityManager))
            }

            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities
            ) {
                trySend(checkNetwork(connectivityManager))
            }
        }

        // NetworkRequest genérico: qualquer rede com capacidade de Internet
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()

        // Registra o callback no ConnectivityManager
        connectivityManager.registerNetworkCallback(request, callback)

        // Emite o estado inicial assim que iniciar a observação
        trySend(checkNetwork(connectivityManager))

        // Quando o Flow for cancelado, remove o callback para não vazar recursos
        awaitClose {
            connectivityManager.unregisterNetworkCallback(callback)
        }
    }

    // Verifica se há rede válida com capacidade de Internet no momento
    private fun checkNetwork(connectivityManager: ConnectivityManager): Boolean {
        val activeNetwork = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(activeNetwork) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
               capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }
}