package com.chicoeletro.dds.core.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.location.LocationManager
import android.os.Build
import android.util.Log
import com.chicoeletro.dds.core.LastTeamStore
import com.chicoeletro.dds.core.services.GpsMonitorService
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.runBlocking

class GpsStateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == LocationManager.PROVIDERS_CHANGED_ACTION) {
            val hasLocationPermission = androidx.core.content.ContextCompat.checkSelfPermission(
                context, android.Manifest.permission.ACCESS_FINE_LOCATION
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED ||
            androidx.core.content.ContextCompat.checkSelfPermission(
                context, android.Manifest.permission.ACCESS_COARSE_LOCATION
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED

            if (!hasLocationPermission) {
                Log.w("GpsStateReceiver", "Sem permissão de localização. Ignorando evento.")
                return
            }

            val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val isGpsEnabled = try {
                locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                        locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
            } catch (e: Exception) {
                false
            }

            if (!isGpsEnabled) {
                Log.d("GpsStateReceiver", "GPS desativado detectado pelo receptor estático. Iniciando GpsMonitorService.")
                runBlocking {
                    val teamData = LastTeamStore.carregar(context).firstOrNull()
                    val teamName = teamData?.equipe ?: ""
                    try {
                        val serviceIntent = Intent(context, GpsMonitorService::class.java).apply {
                            putExtra("equipe", teamName)
                        }
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            context.startForegroundService(serviceIntent)
                        } else {
                            context.startService(serviceIntent)
                        }
                    } catch (e: Exception) {
                        Log.e("GpsStateReceiver", "Erro ao iniciar GpsMonitorService a partir do receptor estático", e)
                    }
                }
            }
        }
    }
}
