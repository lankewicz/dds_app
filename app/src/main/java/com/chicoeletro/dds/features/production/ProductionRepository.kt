// Módulo: app/src/main/java/com/chicoeletro/dds/features/production/ProductionRepository.kt
// Função: Repositório de dados de produção. Consulta estatísticas mensais e históricos de 
//         produtividade no Firestore para visualização pela equipe.
// Tecnologias: Firebase Firestore, Kotlin Coroutines.
// Autor: Valdinei Lankewicz
// Histórico de Alterações:

package com.chicoeletro.dds.features.production

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.tasks.await

class ProductionRepository(
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()
) {
    companion object {
        private const val ROOT = "dds_producao_mensal"
    }

    private suspend fun ensureAuthUid(): String {
        val u = auth.currentUser
        if (u != null) return u.uid
        val res = auth.signInAnonymously().await()
        return res.user?.uid ?: throw IllegalStateException("Falha ao autenticar no Firebase")
    }

    suspend fun getAnnualProduction(teamKey: String, year: Int): List<ProductionMonthlyDoc> = coroutineScope {
        ensureAuthUid()
        val collection = db.collection(ROOT)

        val deferreds = (1..12).map { monthNum ->
            val monthStr = monthNum.toString().padStart(2, '0')
            val monthKey = "$year-$monthStr"

            async {
                val querySnapshot = collection
                    .whereEqualTo("monthKey", monthKey)
                    .whereEqualTo("teamKey", teamKey)
                    .get()
                    .await()

                querySnapshot.documents.map { doc ->
                    val metricsMap = doc.get("metrics") as? Map<*, *> ?: emptyMap<String, Any>()
                    
                    val getDouble = { key: String ->
                        when (val v = metricsMap[key]) {
                            is Number -> v.toDouble()
                            is String -> v.toDoubleOrNull() ?: 0.0
                            else -> 0.0
                        }
                    }

                    val goalMap = doc.get("goal") as? Map<*, *> ?: emptyMap<String, Any>()
                    val goalTargetUs = when (val v = goalMap["targetUs"]) {
                        is Number -> v.toDouble()
                        is String -> v.toDoubleOrNull() ?: 0.0
                        else -> 0.0
                    }
                    val goalType = goalMap["type"] as? String ?: ""

                    ProductionMonthlyDoc(
                        teamKey = doc.getString("teamKey") ?: "",
                        displayName = doc.getString("displayName") ?: "",
                        teamType = doc.getString("teamType") ?: "",
                        members = (doc.get("members") as? List<*>)?.mapNotNull { it?.toString() } ?: emptyList(),
                        year = doc.getLong("year")?.toInt() ?: year,
                        monthNumber = doc.getLong("monthNumber")?.toInt() ?: monthNum,
                        monthKey = doc.getString("monthKey") ?: monthKey,
                        monthAbbr = doc.getString("monthAbbr") ?: "",
                        contract = doc.getString("contract") ?: "",
                        plate = doc.getString("plate") ?: "",
                        base = doc.getString("base") ?: "",
                        updatedAt = doc.getTimestamp("updatedAt"),
                        metrics = ProductionMetrics(
                            totalUs = getDouble("totalUs"),
                            workDays = getDouble("workDays"),
                            drivenKm = getDouble("km"), // Fixed from kmTotal to km based on confirmation
                            commercial = getDouble("commercialEffective"), 
                            emergency = getDouble("emergencyServices"), // Adjusted to match Python service (emergencyServices)
                            totalServices = getDouble("totalServices"),
                            commercialEffective = getDouble("commercialEffective"),
                            inrPerDay = getDouble("inrPerDay"),
                            billingPerDay = getDouble("billingPerDay")
                        ),
                        goal = ProductionGoal(targetUs = goalTargetUs, type = goalType)
                    )
                }
            }
        }

        deferreds.awaitAll().filterNotNull().flatten()
    }
}