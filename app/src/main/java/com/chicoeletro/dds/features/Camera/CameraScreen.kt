// Módulo: app/src/main/java/com/chicoeletro/dds/features/Camera/CameraScreen.kt
// Função: Interface de captura de imagem. Gerencia o ciclo de vida da câmera, provê preview em 
//         tempo real e realiza captura e salvamento de fotos para os treinamentos.
// Tecnologias: Android CameraX, Jetpack Compose, File API.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

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
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color as ComposeColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
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
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

enum class CameraMode { DDS, ODOMETER }

data class CameraOdometerResult(
    val odoUri: Uri,
    val thumbUri: Uri?,
    val km: Long?,
    val rawText: String?
)
@Composable
fun CameraScreen(
    onPhotoCaptured: (Uri, Uri?) -> Unit,
    onBack: () -> Unit,
    mode: CameraMode = CameraMode.DDS,
    onOdometerCaptured: ((CameraOdometerResult) -> Unit)? = null
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }
    val executor = remember { Executors.newSingleThreadExecutor() }

    var imageCapture: ImageCapture? by remember { mutableStateOf(null) }
    var cameraControlState: CameraControl? by remember { mutableStateOf(null) }
    var zoomRatio by remember { mutableFloatStateOf(2f) }

    val previewView = remember {
        PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }

    var lensFacing by remember(mode) {
        mutableIntStateOf(
            if (mode == CameraMode.ODOMETER) CameraSelector.LENS_FACING_BACK
            else CameraSelector.LENS_FACING_FRONT
        )
    }

    var resolution by remember { mutableStateOf(android.util.Size(1920, 1080)) }

    val snackbarHostState = remember { SnackbarHostState() }
    val coroutineScope = rememberCoroutineScope()

    // DDS (modo atual) continua usando previewFotoUri
    var previewFotoUri by remember { mutableStateOf<Uri?>(null) }
    var odoPreviewUri by remember { mutableStateOf<Uri?>(null) }

    var ocrBusy by remember { mutableStateOf(false) }
    var ocrKm by remember { mutableStateOf<Long?>(null) }
    var kmEdit by remember { mutableStateOf("") }
    var ocrRaw by remember { mutableStateOf<String?>(null) }
    var ocrError by remember { mutableStateOf<String?>(null) }

    val activePreviewUri = if (mode == CameraMode.ODOMETER) odoPreviewUri else previewFotoUri

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
                val camera = cameraProvider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    newImageCapture
                )
                imageCapture = newImageCapture
                cameraControlState = camera.cameraControl

                val initialZoom = if (mode == CameraMode.ODOMETER) 2.5f else 1.0f
                zoomRatio = initialZoom
                camera.cameraControl.setZoomRatio(initialZoom)
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

        if (activePreviewUri == null) {
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
                painter = rememberAsyncImagePainter(activePreviewUri),
                contentDescription = "Foto capturada",
                modifier = Modifier.fillMaxSize()
            )
        }

        // Overlay (somente modo odômetro, antes de capturar)
        if (mode == CameraMode.ODOMETER && activePreviewUri == null) {
            OdometerMaskOverlay(
                message = "Enquadre o odômetro dentro do retângulo"
            )
        }

        // UI de OCR/edição (somente modo odômetro, após capturar)
        if (mode == CameraMode.ODOMETER && activePreviewUri != null) {
            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 120.dp, start = 16.dp, end = 16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                if (ocrBusy) {
                    Text("Lendo odômetro…", textAlign = TextAlign.Center)
                    Spacer(Modifier.height(8.dp))
                    CircularProgressIndicator()
                    Spacer(Modifier.height(12.dp))
                } else {
                    if (ocrError != null) {
                        Text(ocrError!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center)
                        Spacer(Modifier.height(8.dp))
                    } else if (ocrKm != null) {
                        Text("Reconheci: $ocrKm km — confirme/ajuste", textAlign = TextAlign.Center)
                        Spacer(Modifier.height(8.dp))
                    }
                }

                OutlinedTextField(
                    value = kmEdit,
                    onValueChange = { kmEdit = it.filter(Char::isDigit) },
                    label = { Text("KM") },
                    singleLine = true
                )
            }
        }

        if (activePreviewUri == null) {
            Column(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (mode == CameraMode.DDS) {
                    OutlinedButton(onClick = {
                        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_FRONT)
                            CameraSelector.LENS_FACING_BACK else CameraSelector.LENS_FACING_FRONT
                    }) {
                        Text("🔄")
                    }
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
            if (activePreviewUri == null) {
                OutlinedButton(onClick = onBack) {
                    Text("Voltar")
                }

                Button(onClick = {

                    val capture = imageCapture ?: return@Button
                    Log.d("DDS-CAM", "Disparando captura de imagem (lens=$lensFacing res=${resolution.width}x${resolution.height})")
                    val name = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(System.currentTimeMillis())

                    // ✅ Play-safe: salva em armazenamento PRIVADO do app (cacheDir)
                    // - não usa MediaStore
                    // - não aparece na galeria
                    // - não exige READ_MEDIA_IMAGES / WRITE_EXTERNAL_STORAGE
                    val photoFile = File(context.filesDir, "dds_$name.jpg")
                    val outputOptions = ImageCapture.OutputFileOptions.Builder(photoFile).build()

                    capture.takePicture(
                        outputOptions,
                        ContextCompat.getMainExecutor(context),
                        object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                                // OutputFileResults.savedUri costuma vir null quando salva em File.
                                // Então geramos um Uri seguro via FileProvider.
                                val savedUri = FileProvider.getUriForFile(
                                    context,
                                    "${context.packageName}.provider",
                                    photoFile
                                            )
                                Log.d("DDS-CAM", "Imagem salva: $savedUri")

                                // Processamento pesado fora do main thread
                                executor.execute {
                                    try {
                                        if (mode == CameraMode.DDS) {
                                            // ===== MODO DDS (mantém comportamento atual) =====
                                            try {
                                                ensureLandscape169(context, savedUri)
                                            } catch (t: Throwable) {
                                                Log.e("DDS-CAM", "Falha no ensureLandscape169", t)
                                            }
                                            ContextCompat.getMainExecutor(context).execute {
                                                previewFotoUri = savedUri
                                            }
                                        } else {
                                            // ===== MODO ODOMETRO =====
                                            ContextCompat.getMainExecutor(context).execute {
                                                ocrBusy = true
                                                ocrError = null
                                                ocrKm = null
                                                kmEdit = ""
                                                ocrRaw = null
                                            }

                                            // Carregamento de bitmap com inSampleSize para prevenção de OOM
                                            val optsForBounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                                            context.contentResolver.openInputStream(savedUri)?.use { BitmapFactory.decodeStream(it, null, optsForBounds) }
                                            
                                            val safeOpts = BitmapFactory.Options().apply {
                                                val reqW = 1920
                                                val reqH = 1080
                                                var samp = 1
                                                if (optsForBounds.outHeight > reqH || optsForBounds.outWidth > reqW) {
                                                    val halfH = optsForBounds.outHeight / 2
                                                    val halfW = optsForBounds.outWidth / 2
                                                    while ((halfH / samp) >= reqH && (halfW / samp) >= reqW) { samp *= 2 }
                                                }
                                                inSampleSize = samp
                                            }
                                            
                                            val fullBmp = context.contentResolver.openInputStream(savedUri)?.use {
                                                BitmapFactory.decodeStream(it, null, safeOpts)
                                            } ?: throw IllegalStateException("Falha ao decodificar imagem")

                                            val norm169 = normalizeToLandscape169(fullBmp)
                                            val pre = cropCenterByFraction(norm169, 0.50f, 0.20f)

                                            val odoFile = File(context.filesDir, "odo_${System.currentTimeMillis()}.jpg")
                                            FileOutputStream(odoFile).use { out ->
                                                pre.compress(Bitmap.CompressFormat.JPEG, 92, out)
                                            }
                                            val odoUri = FileProvider.getUriForFile(
                                                context,
                                                "${context.packageName}.provider",
                                                odoFile
                                            )

                                            val (km, raw) = runOcrLocalMlKit(pre)

                                            ContextCompat.getMainExecutor(context).execute {
                                                odoPreviewUri = odoUri
                                                ocrRaw = raw
                                                ocrKm = km
                                                kmEdit = km?.toString() ?: ""
                                                ocrBusy = false
                                                ocrError = if (km == null) "Não consegui ler automaticamente. Digite o KM." else null
                                            }

                                            // cleanup
                                            if (pre != norm169) norm169.recycle()
                                            if (norm169 != fullBmp) fullBmp.recycle()
                                        }
                                    } catch (t: Throwable) {
                                        Log.e("DDS-CAM", "Falha no pipeline", t)
                                        ContextCompat.getMainExecutor(context).execute {
                                            ocrBusy = false
                                            ocrError = "Erro ao processar: ${t.message}"
                                        }
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
                    // Refazer: volta para preview de câmera
                    if (mode == CameraMode.ODOMETER) {
                        odoPreviewUri = null
                        ocrBusy = false
                        ocrKm = null
                        kmEdit = ""
                        ocrRaw = null
                        ocrError = null
                    } else {
                        previewFotoUri = null
                    }
                }) {
                    Text("🔁 Refazer")
                }

                Button(onClick = {
                    if (mode == CameraMode.DDS) {
                        val uri = previewFotoUri ?: return@Button
                        val thumbUri = gerarThumb(context, uri)
                        onPhotoCaptured(uri, thumbUri)
                    } else {
                        val uri = odoPreviewUri ?: return@Button
                        val thumbUri = gerarThumb(context, uri)
                        val km = kmEdit.toLongOrNull()
                        onOdometerCaptured?.invoke(
                            CameraOdometerResult(
                                odoUri = uri,
                                thumbUri = thumbUri,
                                km = km,
                                rawText = ocrRaw
                            )
                        )
                    }
                }) {
                    Text("✅ Usar Foto")
                }
            }
        }
    }
}
@Composable
private fun OdometerMaskOverlay(message: String) {
    Box(Modifier.fillMaxSize()) {
        androidx.compose.foundation.Canvas(
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer { alpha = 0.99f } // necessário p/ BlendMode.Clear funcionar bem
        ) {
            val w = size.width
            val h = size.height

            val boxW = w * 0.50f
            val boxH = h * 0.20f
            val left = (w - boxW) / 2f
            val top = (h - boxH) / 2f

            // escurece tudo
            drawRect(color = ComposeColor.Black.copy(alpha = 0.55f))

            // "buraco" transparente
            drawRect(
                color = ComposeColor.Transparent,
                topLeft = Offset(left, top),
                size = Size(boxW, boxH),
                blendMode = BlendMode.Clear
            )

            // borda
            drawRect(
                color = ComposeColor.White.copy(alpha = 0.95f),
                topLeft = Offset(left, top),
                size = Size(boxW, boxH),
                style = Stroke(width = 3.dp.toPx())
            )
        }

        Text(
            text = message,
            color = ComposeColor.White,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .align(Alignment.Center)
                .offset(y = (-120).dp)
                .background(ComposeColor.Black.copy(alpha = 0.45f), RoundedCornerShape(10.dp))
                .padding(horizontal = 12.dp, vertical = 8.dp)
        )
    }
}

private fun gerarThumb(context: android.content.Context, uri: Uri): Uri? {
    return try {
        val bmp = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) } ?: return null
        val thumb = bmp.scale(320, 180, true)
        val f = File.createTempFile("thumb_", ".jpg", context.cacheDir)
        FileOutputStream(f).use { out -> thumb.compress(Bitmap.CompressFormat.JPEG, 80, out) }
        FileProvider.getUriForFile(context, "${context.packageName}.provider", f)
    } catch (_: Exception) {
        null
    }
}

// Normaliza em memória (landscape + 16:9) para facilitar recorte/ocr sem depender de PreviewView mapping
private fun normalizeToLandscape169(original: Bitmap): Bitmap {
    val base = if (original.width >= original.height) original else {
        val m = Matrix().apply { postRotate(90f) }
        Bitmap.createBitmap(original, 0, 0, original.width, original.height, m, true)
    }

    val W = base.width
    val H = base.height
    val targetRatio = 16f / 9f
    val current = W.toFloat() / H.toFloat()

    return when {
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
}

private fun cropCenterByFraction(bmp: Bitmap, wFrac: Float, hFrac: Float): Bitmap {
    val W = bmp.width
    val H = bmp.height
    val cw = (W * wFrac).toInt().coerceAtLeast(1)
    val ch = (H * hFrac).toInt().coerceAtLeast(1)
    val x = ((W - cw) / 2).coerceAtLeast(0)
    val y = ((H - ch) / 2).coerceAtLeast(0)
    val ww = cw.coerceAtMost(W - x).coerceAtLeast(1)
    val hh = ch.coerceAtMost(H - y).coerceAtLeast(1)
    return Bitmap.createBitmap(bmp, x, y, ww, hh)
}

private fun runOcrLocalMlKit(bmp: Bitmap): Pair<Long?, String?> {
    val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    val image = InputImage.fromBitmap(bmp, 0)
    val result = Tasks.await(recognizer.process(image))
    val raw = result.text
    if (raw.isBlank()) return Pair(null, null)

    val cleaned = raw
        .replace("O", "0", ignoreCase = true)
        .replace("I", "1")
        .replace("\\s+".toRegex(), "")

    val matches = "\\d{4,7}".toRegex().findAll(cleaned).map { it.value }.toList()
    val best = matches.maxByOrNull { it.length } ?: return Pair(null, raw)

    return Pair(best.toLongOrNull(), raw)
}

// ======== util: força orientação "paisagem" 16:9 mesmo se o device estiver travado em retrato ========
private fun ensureLandscape169(context: android.content.Context, uri: Uri, minW: Int = 1920, minH: Int = 1080, quality: Int = 85) {
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
        }
        val input: InputStream = context.contentResolver.openInputStream(uri) ?: return
        val original = BitmapFactory.decodeStream(input, null, safeOpts)
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