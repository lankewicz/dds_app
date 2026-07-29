// Módulo: app/src/main/java/com/chicoeletro/dds/features/Camera/CameraScreen.kt
// Função: Interface de captura de imagem. Gerencia o ciclo de vida da câmera, provê preview em 
//         tempo real e realiza captura e salvamento de fotos para os treinamentos.
// Tecnologias: Android CameraX, Jetpack Compose, File API.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.Camera

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.net.Uri
import android.util.Log
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.runtime.DisposableEffect
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.FileProvider
import androidx.core.graphics.scale
import androidx.lifecycle.compose.LocalLifecycleOwner
import coil.compose.rememberAsyncImagePainter
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.Executors
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import java.io.InputStream
import java.io.OutputStream
import androidx.core.content.ContextCompat

@Composable
fun CameraScreen(
    onPhotoCaptured: (Uri, Uri?) -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }
    val executor = remember { Executors.newSingleThreadExecutor() }

    var imageCapture: ImageCapture? by remember { mutableStateOf(null) }
    var cameraControlState: CameraControl? by remember { mutableStateOf(null) }
    var zoomRatio by remember { mutableFloatStateOf(1f) }

    val previewView = remember {
        PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }

    var lensFacing by remember { mutableIntStateOf(CameraSelector.LENS_FACING_FRONT) }
    val resolution = remember { android.util.Size(1920, 1080) }

    val snackbarHostState = remember { SnackbarHostState() }
    var previewFotoUri by remember { mutableStateOf<Uri?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            try { executor.shutdown() } catch (_: Exception) {}
        }
    }

    DisposableEffect(lensFacing, lifecycleOwner, previewView) {
        val mainExecutor = ContextCompat.getMainExecutor(context)

        val listener = Runnable {
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            val resolutionSelector = ResolutionSelector.Builder()
                .setResolutionStrategy(
                    ResolutionStrategy(
                        resolution,
                        ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                    )
                ).build()

            val newImageCapture = ImageCapture.Builder()
                .setResolutionSelector(resolutionSelector)
                .build()

            val cameraSelector = CameraSelector.Builder()
                .requireLensFacing(lensFacing)
                .build()

            try {
                cameraProvider.unbindAll()
                val camera = cameraProvider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    newImageCapture
                )
                imageCapture = newImageCapture
                cameraControlState = camera.cameraControl
                zoomRatio = 1.0f
                camera.cameraControl.setZoomRatio(1.0f)
            } catch (exc: Exception) {
                Log.e("DDS", "Falha ao vincular os casos de uso da câmera", exc)
            }
        }

        cameraProviderFuture.addListener(listener, mainExecutor)

        onDispose {
            try {
                cameraProviderFuture.get().unbindAll()
            } catch (_: Exception) {}
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {

        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )

        if (previewFotoUri == null) {
            AndroidView(
                factory = { previewView },
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(cameraControlState) {
                        detectTransformGestures { _, _, zoom, _ ->
                            if (cameraControlState != null) {
                                zoomRatio = (zoomRatio * zoom).coerceIn(1f, 10f)
                                cameraControlState?.setZoomRatio(zoomRatio)
                            }
                        }
                    }
            )
        } else {
            Image(
                painter = rememberAsyncImagePainter(previewFotoUri),
                contentDescription = "Foto capturada",
                modifier = Modifier.fillMaxSize()
            )
        }

        if (previewFotoUri == null) {
            Column(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(onClick = {
                    lensFacing = if (lensFacing == CameraSelector.LENS_FACING_FRONT)
                        CameraSelector.LENS_FACING_BACK else CameraSelector.LENS_FACING_FRONT
                }) {
                    Text("🔄")
                }
            }
        }

        Row(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 48.dp, start = 16.dp, end = 16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            if (previewFotoUri == null) {
                OutlinedButton(onClick = onBack) {
                    Text("Voltar")
                }

                Button(onClick = {
                    val capture = imageCapture ?: return@Button
                    Log.d("DDS-CAM", "Disparando captura de imagem (lens=$lensFacing)")
                    val name = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(System.currentTimeMillis())

                    val photoFile = File(context.filesDir, "dds_$name.jpg")
                    val outputOptions = ImageCapture.OutputFileOptions.Builder(photoFile).build()

                    capture.takePicture(
                        outputOptions,
                        ContextCompat.getMainExecutor(context),
                        object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                                val savedUri = FileProvider.getUriForFile(
                                    context,
                                    "${context.packageName}.provider",
                                    photoFile
                                )
                                Log.d("DDS-CAM", "Imagem salva: $savedUri")

                                executor.execute {
                                    try {
                                        ensureLandscape169(context, savedUri)
                                        ContextCompat.getMainExecutor(context).execute {
                                            previewFotoUri = savedUri
                                        }
                                    } catch (t: Throwable) {
                                        Log.e("DDS-CAM", "Falha ao normalizar imagem", t)
                                    }
                                }
                            }

                            override fun onError(exception: ImageCaptureException) {
                                Log.e("DDS-CAM", "Erro ao capturar imagem", exception)
                            }
                        }
                    )

                }) {
                    Text("📷 Tirar Foto")
                }

            } else {
                OutlinedButton(onClick = {
                    runCatching { previewFotoUri?.let { context.contentResolver.delete(it, null, null) } }
                    previewFotoUri = null
                }) {
                    Text("🔁 Refazer")
                }

                Button(onClick = {
                    val uri = previewFotoUri ?: return@Button
                    val thumbUri = gerarThumb(context, uri)
                    onPhotoCaptured(uri, thumbUri)
                }) {
                    Text("✅ Usar Foto")
                }
            }
        }
    }
}

private fun gerarThumb(context: android.content.Context, uri: Uri): Uri? {
    return try {
        val bmp = com.chicoeletro.dds.core.utils.ImageCompressor.decodeSampledBitmapFromUri(context, uri, maxWidth = 320, maxHeight = 180) ?: return null
        val thumb = bmp.scale(320, 180, true)
        val f = File.createTempFile("thumb_", ".webp", context.cacheDir)
        FileOutputStream(f).use { out -> 
            com.chicoeletro.dds.core.utils.ImageCompressor.compressToWebp(thumb, 80, out)
        }
        if (bmp != thumb) bmp.recycle()
        thumb.recycle()
        FileProvider.getUriForFile(context, "${context.packageName}.provider", f)
    } catch (_: Exception) {
        null
    }
}

private fun ensureLandscape169(context: android.content.Context, uri: Uri, minW: Int = 1920, minH: Int = 1080, quality: Int = 80) {
    try {
        val optsForBounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, optsForBounds) }
        val safeOpts = BitmapFactory.Options().apply {
            var samp = 1
            if (optsForBounds.outHeight > minH || optsForBounds.outWidth > minW) {
                val halfH = optsForBounds.outHeight / 2
                val halfW = optsForBounds.outWidth / 2
                while (halfH / samp >= minH && halfW / samp >= minW) { samp *= 2 }
            }
            inSampleSize = samp
            inPreferredConfig = Bitmap.Config.RGB_565 // Consumo de RAM reduzido pela metade
        }
        val input: InputStream = context.contentResolver.openInputStream(uri) ?: return
        val original = BitmapFactory.decodeStream(input, null, safeOpts)
        input.close()
        if (original == null) return

        val base = if (original.width >= original.height) original
        else {
            val m = Matrix().apply { postRotate(90f) }
            Bitmap.createBitmap(original, 0, 0, original.width, original.height, m, true).also {
                if (it != original) original.recycle()
            }
        }

        val W = base.width; val H = base.height
        val targetRatio = 16f / 9f
        val current = W.toFloat() / H.toFloat()
        val cropped = when {
            current > targetRatio -> {
                val targetW = (H * targetRatio).toInt()
                val x = (W - targetW) / 2
                Bitmap.createBitmap(base, x, 0, targetW, H)
            }
            current < targetRatio -> {
                val targetH = (W / targetRatio).toInt()
                val y = (H - targetH) / 2
                Bitmap.createBitmap(base, 0, y, W, targetH)
            }
            else -> base
        }

        val finalBmp = if (cropped.width >= minW && cropped.height >= minH) cropped
        else {
            val scale = minOf(minW.toFloat() / cropped.width, minH.toFloat() / cropped.height)
            val sw = (cropped.width * scale).toInt()
            val sh = (cropped.height * scale).toInt()
            val scaled = Bitmap.createScaledBitmap(cropped, sw, sh, true)
            val canvasBmp = Bitmap.createBitmap(minW, minH, Bitmap.Config.ARGB_8888)
            val c = Canvas(canvasBmp)
            c.drawColor(Color.BLACK)
            val dx = ((minW - sw) / 2f)
            val dy = ((minH - sh) / 2f)
            c.drawBitmap(scaled, dx, dy, null)
            if (scaled != cropped) cropped.recycle()
            canvasBmp
        }

        val out: OutputStream = context.contentResolver.openOutputStream(uri, "w") ?: return
        com.chicoeletro.dds.core.utils.ImageCompressor.compressToWebp(finalBmp, quality, out)
        out.flush()
        out.close()
        if (finalBmp != base) base.recycle()
        if (finalBmp != original) original.recycle()
    } catch (e: Exception) {
        Log.w("DDS", "ensureLandscape169 falhou: ${e.message}")
    }
}