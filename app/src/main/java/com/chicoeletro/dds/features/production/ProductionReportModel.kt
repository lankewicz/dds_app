// Módulo: app/src/main/java/com/chicoeletro/dds/features/production/ProductionReportModel.kt
// Função: Modelo de dados para relatórios de produção. Define a estrutura de indicadores de 
//         desempenho e produtividade para visualização consolidada no Dashboard.
// Tecnologias: Kotlin Data Classes.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.production

import com.google.firebase.Timestamp

data class ProductionMetrics(
    val totalUs: Double = 0.0,
    val workDays: Double = 0.0,
    val drivenKm: Double = 0.0,
    val commercial: Double = 0.0,
    val emergency: Double = 0.0,
    val totalServices: Double = 0.0,
    val commercialEffective: Double = 0.0,
    val inrPerDay: Double = 0.0,
    val billingPerDay: Double = 0.0
)

data class ProductionGoal(
    val targetUs: Double = 0.0,
    val type: String = ""
)

data class ProductionMonthlyDoc(
    val teamKey: String = "",
    val displayName: String = "",
    val teamType: String = "",
    val members: List<String> = emptyList(),
    val year: Int = 0,
    val monthNumber: Int = 0,
    val monthKey: String = "",
    val monthAbbr: String = "",
    val contract: String = "",
    val plate: String = "",
    val base: String = "",
    val updatedAt: Timestamp? = null,
    val metrics: ProductionMetrics = ProductionMetrics(),
    val goal: ProductionGoal = ProductionGoal()
)