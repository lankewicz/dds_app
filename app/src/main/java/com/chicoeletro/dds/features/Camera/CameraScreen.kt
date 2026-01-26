// Módulo: app/src/main/java/com/chicoeletro/dds/features/camera/CameraScreen.kt
// Função: Tela de captura de foto com CameraX, agora com preview da imagem e confirmação antes de sair
// Autor: Valdinei Lankewicz
//
// Histórico de alterações:
// - 04/07/2025: Adicionado preview após captura e botões "Refazer" e "Usar Foto"
//               Botões de ação reposicionados acima da barra de navegação

package com.chicoeletro.dds.features.Camera

import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.util.Log
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
import kotlinx.coroutines.launch
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

    val previewView = remember {
        PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }

    var lensFacing by remember { mutableIntStateOf(CameraSelector.LENS_FACING_FRONT) }
    var resolution by remember { mutableStateOf(android.util.Size(1920, 1080)) }

    val snackbarHostState = remember { SnackbarHostState() }
    val coroutineScope = rememberCoroutineScope()

    var previewFotoUri by remember { mutableStateOf<Uri?>(null) }

    // ==========================================================
    // IMPORTANTÍSSIMO:
    // O executor NÃO pode ser finalizado quando lensFacing/resolution muda,
    // senão o takePicture pode ficar apontando para um executor morto.
    // Finalize apenas quando a tela for descartada de verdade.
    // ==========================================================
    DisposableEffect(Unit) {
        onDispose {
            try { executor.shutdown() } catch (_: Exception) {}
        }
    }

    DisposableEffect(lensFacing, resolution, lifecycleOwner, previewView) {
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
                cameraProvider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    newImageCapture
                )
                imageCapture = newImageCapture
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
                modifier = Modifier.fillMaxSize()
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

                OutlinedButton(onClick = {
                    resolution = when (resolution.height) {
                        720 -> android.util.Size(1920, 1080)
                        1080 -> android.util.Size(3840, 2160)
                        else -> android.util.Size(1280, 720)
                    }
                }) {
                    Text("🎚️ ${resolution.height}p")
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
                    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
                        context.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                        != android.content.pm.PackageManager.PERMISSION_GRANTED
                    ) {
                        coroutineScope.launch {
                            snackbarHostState.showSnackbar("Permissão para salvar imagens foi negada.")
                        }
                        return@Button
                    }

                    val capture = imageCapture ?: return@Button
                    Log.d("DDS-CAM", "Disparando captura de imagem (lens=$lensFacing res=${resolution.width}x${resolution.height})")
                    val name = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(System.currentTimeMillis())

                    val contentValues = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                        put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/DDS")
                        }
                    }

                    val outputOptions = ImageCapture.OutputFileOptions.Builder(
                        context.contentResolver,
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        contentValues
                    ).build()

                    capture.takePicture(
                        outputOptions,
                        ContextCompat.getMainExecutor(context),
                        object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                                val savedUri = output.savedUri ?: return
                                Log.d("DDS-CAM", "Imagem salva: $savedUri")

                                // Processamento pesado fora do main thread
                                executor.execute {
                                    try {
                                        ensureLandscape169(context, savedUri)
                                    } catch (t: Throwable) {
                                        Log.e("DDS-CAM", "Falha no ensureLandscape169", t)
                                    }

                                    // Volta para o main thread para atualizar estado Compose
                                    ContextCompat.getMainExecutor(context).execute {
                                        previewFotoUri = savedUri
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
                    previewFotoUri = null
                }) {
                    Text("🔁 Refazer")
                }

                Button(onClick = {
                    val thumbUri = try {
                        val inputStream = context.contentResolver.openInputStream(previewFotoUri!!)
                        val originalBitmap = BitmapFactory.decodeStream(inputStream)
                        inputStream?.close()

                        val thumbBitmap = originalBitmap.scale(320, 180, true)
                        val thumbFile = File.createTempFile("thumb_", ".jpg", context.cacheDir)
                        val outputStream = FileOutputStream(thumbFile)
                        thumbBitmap.compress(Bitmap.CompressFormat.JPEG, 80, outputStream)
                        outputStream.flush()
                        outputStream.close()

                        FileProvider.getUriForFile(
                            context,
                            "${context.packageName}.provider",
                            thumbFile
                        )
                    } catch (e: Exception) {
                        e.printStackTrace()
                        null
                    }
                    onPhotoCaptured(previewFotoUri!!, thumbUri)
                }) {
                    Text("✅ Usar Foto")
                }
            }
        }
    }
}

// ======== util: força orientação "paisagem" 16:9 mesmo se o device estiver travado em retrato ========
private fun ensureLandscape169(context: android.content.Context, uri: Uri, minW: Int = 1920, minH: Int = 1080, quality: Int = 85) {
    try {
        // lê bitmap
        val input: InputStream = context.contentResolver.openInputStream(uri) ?: return
        val original = BitmapFactory.decodeStream(input)
        input.close()
        if (original == null) return

        // gira para landscape se necessário (sem depender de EXIF)
        val base = if (original.width >= original.height) original
        else {
            val m = Matrix().apply { postRotate(90f) }
            Bitmap.createBitmap(original, 0, 0, original.width, original.height, m, true).also {
                if (it != original) original.recycle()
            }
        }

        // recorta para 16:9
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

        // escala/pad mínimo 1920x1080 (evita miniaturas em devices antigos)
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
        finalBmp.compress(Bitmap.CompressFormat.JPEG, quality, out)
        out.flush()
        out.close()
        if (finalBmp != base) base.recycle()
        if (finalBmp != original) original.recycle()
    } catch (e: Exception) {
        Log.w("DDS", "ensureLandscape169 falhou: ${e.message}")
    }
}