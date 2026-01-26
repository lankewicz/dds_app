// Top-level build file where you can add configuration options common to all sub-projects/modules.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android)    apply false
    alias(libs.plugins.kotlin.compose)    apply false
    alias(libs.plugins.android.library)   apply false
    kotlin("plugin.serialization") version "2.3.0"
    id("com.google.gms.google-services") version "4.4.4" apply false
}

buildscript {
    repositories {
        // Caso precise de repositório para o plugin google-services
        gradlePluginPortal()
        google()
        mavenCentral()
    }
    dependencies {
        classpath(libs.google.services)
    }
}

tasks.register("printMajor") {
    doLast {
        println(">>> major = ${project.findProperty("major")}")
    }
}



