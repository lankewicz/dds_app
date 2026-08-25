package com.chicoeletro.dds.core

import android.app.Activity
import android.content.Context
import android.content.pm.ActivityInfo
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

object ScreenRotationState {
    val isLandscape: Boolean = true
    val isPortrait: Boolean = false

    fun applyOrientation(context: Context) {
        val act = findActivity(context) ?: return
        try {
            act.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        } catch (_: Exception) { }
    }

    fun toggle(context: Context) {
        applyOrientation(context)
    }

    private fun findActivity(context: Context): Activity? {
        if (context is Activity) return context
        var ctx = context
        while (ctx is android.content.ContextWrapper) {
            if (ctx is Activity) return ctx
            ctx = ctx.baseContext
        }
        return null
    }
}
