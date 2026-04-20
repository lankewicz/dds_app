// Módulo: app/build.gradle.kts
// Função: Configuração do app DDS com versionamento automático e assinatura de release
// Autor: Valdinei Lankewicz
// Data de criação: 28/05/2025
// Histórico de alterações:
// - 07/07/2025: Substituído cálculo direto por `extra{}` para garantir recompilação com versionamento dinâmico
// - 15/07/2025: Adicionado signingConfigs para assinar o APK de Release
// Sempre altere algo nessa linha para o código ser recompilado automaticamente

import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    id("com.google.gms.google-services")
}
// ─── Versionamento automático (ANO + DATA + HORA) ──────────────────────────────
val versionCodeAuto by extra {
    val now = LocalDateTime.now(ZoneId.of("America/Sao_Paulo"))

    val aa = (now.year % 100).toString().padStart(2, '0')
    val mm = now.monthValue.toString().padStart(2, '0')
    val dd = now.dayOfMonth.toString().padStart(2, '0')
    val hh = now.hour.toString().padStart(2, '0')

    // AAMMDDHH  → ex.: 25122609
    "$aa$mm$dd$hh".toInt()
}

val versionNameAuto by extra {
    val now = LocalDateTime.now(ZoneId.of("America/Sao_Paulo"))

    val aa = (now.year % 100).toString().padStart(2, '0')
    val mm = now.monthValue.toString().padStart(2, '0')
    val dd = now.dayOfMonth.toString().padStart(2, '0')

    // AA.MM.DD → ex.: 26.03.26
    "$aa.$mm.$dd"
}


android {
    namespace = "com.chicoeletro.dds"
    compileSdk = 36

    // ===================================================================
    // INÍCIO DO CÓDIGO DE ASSINATURA ADICIONADO
    // ===================================================================
    signingConfigs {
        create("release") {
            val keystoreFile = project.findProperty("DDS_RELEASE_STORE_FILE") as? String
            if (keystoreFile != null && project.rootProject.file(keystoreFile).exists()) {
                storeFile = project.rootProject.file(keystoreFile)
                storePassword = project.findProperty("DDS_RELEASE_STORE_PASSWORD") as String
                keyAlias = project.findProperty("DDS_RELEASE_KEY_ALIAS") as String
                keyPassword = project.findProperty("DDS_RELEASE_KEY_PASSWORD") as String
            } else {
                println("Aviso: Arquivo de chave de release não encontrado. O build de release não será assinado.")
            }
        }
    }
    // ===================================================================
    // FIM DO CÓDIGO DE ASSINATURA
    // ===================================================================

    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }

    defaultConfig {
        applicationId = "com.chicoeletro.dds.app"
        minSdk = 27
        targetSdk = 36
        versionCode = versionCodeAuto
        versionName = versionNameAuto
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            // mantém assinatura debug padrão
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    // ─── Firebase (FORMA CORRIGIDA) ──────────────────────────────────────────    // 1. Importe o Firebase BoM (Bill of Materials) para gerenciar as versões
    implementation(platform("com.google.firebase:firebase-bom:34.1.0"))

    // 2. Adicione as dependências do Firebase SEM o sufixo -ktx e SEM a versão
    implementation("com.google.firebase:firebase-analytics")
    implementation("com.google.firebase:firebase-auth")
    implementation("com.google.firebase:firebase-firestore")
    implementation("com.google.firebase:firebase-database")
    implementation("com.google.firebase:firebase-storage")

    // Firebase Tasks -> Kotlin Coroutines (await)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    // ─── Sign-in with Google (Credential Manager) ─────────────────────────────
    // Base recomendado pelo Android/Firebase para login Google moderno
    // - credentials: API unificada de credenciais (passkeys, passwords, federated)
    // - credentials-play-services-auth: integração com Google Play Services
    implementation(libs.androidx.credentials)

    implementation(libs.androidx.credentials.play.services)

    // Google ID SDK (necessário para obter Google ID Token via Credential Manager)
    implementation(libs.google.id)

    // Play Services Auth (fixa versão para evitar divergências transitivas)
    implementation(libs.google.play.services.auth)

    // ─── Jetpack Compose ───────────────────────────────────────────────────
    val composeBom = platform("androidx.compose:compose-bom:2025.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    // Declarações explícitas para garantir que o BOM as encontre
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.compose.material:material-icons-extended")
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.activity.compose)
    implementation(libs.coil.compose)

    // ─── Coroutines ───────────────────────────────────────────────────────────
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)

    // ─── JSON / Serialização ──────────────────────────────────────────────────
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.gson)

    // ─── AndroidX Core e Ciclo de Vida ────────────────────────────────────────
    implementation(libs.androidx.core.ktx)
    implementation(libs.lifecycle.runtime.ktx)

    // ─── DataStore Preferences ────────────────────────────────────────────────
    //implementation(libs.datastore.preferences)
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // ─── WorkManager (Background Tasks) ───────────────────────────────────────
    implementation(libs.androidx.work.runtime.ktx)
    implementation("androidx.work:work-runtime-ktx:2.11.2")

    // ─── CameraX ──────────────────────────────────────────────────────────────
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)      // PreviewView
    implementation(libs.androidx.camera.extensions)

    // ─── AGORA.IO ────────
    implementation("io.agora.rtc:lite-sdk:4.6.1")


    // Dependência Retrofit + Gson no Android
    implementation("com.squareup.retrofit2:retrofit:3.0.0")
    implementation("com.squareup.retrofit2:converter-gson:3.0.0")


    // OCR local (on-device)
    implementation("com.google.mlkit:text-recognition:16.0.1")

    // Para usar Tasks.await(...) de forma estável (geralmente já vem, mas é melhor garantir)
    implementation("com.google.android.gms:play-services-tasks:18.4.1")

    // Google Play In-App Updates
    implementation("com.google.android.play:app-update-ktx:2.1.0")

}