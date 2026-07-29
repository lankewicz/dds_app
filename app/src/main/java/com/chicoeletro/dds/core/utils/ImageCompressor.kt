// Módulo: app/src/main/java/com/chicoeletro/dds/core/utils/ImageCompressor.kt
// Função: Otimizador de imagens e Bitmaps. Converte fotos capturadas pela câmera 
//         para o formato WebP com redimensionamento inteligente (Downsampling), 
//         reduzindo em até 90% o peso do arquivo e o consumo de memória RAM.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.core.utils

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.OutputStream

object ImageCompressor {

    /**
     * Retorna o formato de compressão WebP ideal conforme a versão do Android SDK.
     */
    @Suppress("DEPRECATION")
    fun getWebpCompressFormat(): Bitmap.CompressFormat {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Bitmap.CompressFormat.WEBP_LOSSY
        } else {
            Bitmap.CompressFormat.WEBP
        }
    }

    /**
     * Comprime um Bitmap para WebP no OutputStream fornecido.
     */
    fun compressToWebp(bitmap: Bitmap, quality: Int = 80, outputStream: OutputStream): Boolean {
        return try {
            bitmap.compress(getWebpCompressFormat(), quality, outputStream)
        } catch (e: Exception) {
            Log.e("ImageCompressor", "Erro ao comprimir para WebP", e)
            false
        }
    }

    /**
     * Carrega uma imagem de uma Uri com inSampleSize proporcional (Downsampling),
     * garantindo que a imagem não consuma memória RAM excessiva.
     */
    fun decodeSampledBitmapFromUri(
        context: Context,
        uri: Uri,
        maxWidth: Int = 1280,
        maxHeight: Int = 1280
    ): Bitmap? {
        return try {
            val optsForBounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            context.contentResolver.openInputStream(uri)?.use { 
                BitmapFactory.decodeStream(it, null, optsForBounds) 
            }

            val safeOpts = BitmapFactory.Options().apply {
                inSampleSize = calculateInSampleSize(optsForBounds, maxWidth, maxHeight)
                inPreferredConfig = Bitmap.Config.RGB_565 // Consome a metade da RAM (16-bit)
            }

            val bitmap = context.contentResolver.openInputStream(uri)?.use { input ->
                BitmapFactory.decodeStream(input, null, safeOpts)
            }
            bitmap
        } catch (e: Exception) {
            Log.e("ImageCompressor", "Erro ao decodificar Bitmap com inSampleSize", e)
            null
        }
    }

    private fun calculateInSampleSize(
        options: BitmapFactory.Options,
        reqWidth: Int,
        reqHeight: Int
    ): Int {
        val (height: Int, width: Int) = options.outHeight to options.outWidth
        var inSampleSize = 1

        if (height > reqHeight || width > reqWidth) {
            val halfHeight: Int = height / 2
            val halfWidth: Int = width / 2

            while (halfHeight / inSampleSize >= reqHeight && halfWidth / inSampleSize >= reqWidth) {
                inSampleSize *= 2
            }
        }
        return inSampleSize
    }

    /**
     * Processa a imagem bruta de um arquivo/Uri, otimiza resolução e gera um arquivo WebP leve.
     */
    fun compressImageToWebpFile(
        context: Context,
        inputUri: Uri,
        outputPrefix: String = "opt_",
        maxWidth: Int = 1280,
        maxHeight: Int = 1280,
        quality: Int = 80
    ): File? {
        return try {
            val sampledBmp = decodeSampledBitmapFromUri(context, inputUri, maxWidth, maxHeight) ?: return null
            val outputFile = File(context.cacheDir, "${outputPrefix}${System.currentTimeMillis()}.webp")
            
            FileOutputStream(outputFile).use { out ->
                compressToWebp(sampledBmp, quality, out)
            }
            
            sampledBmp.recycle()
            outputFile
        } catch (e: Exception) {
            Log.e("ImageCompressor", "Erro ao comprimir imagem para WebP", e)
            null
        }
    }
}
