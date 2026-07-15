// Módulo: app/src/main/java/com/chicoeletro/dds/features/construcao/ConstrucaoFirestoreRepository.kt
// Função: Acesso offline-first ao Firebase Firestore para o módulo de Construção.
// Tecnologias: Firebase Firestore, Kotlin Coroutines Tasks.
// Autor: Valdinei Lankewicz

package com.chicoeletro.dds.features.construcao

import android.content.Context
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.flow.firstOrNull

class ConstrucaoFirestoreRepository(
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()
) {
    private val baseDoc = db.collection("webtools").document("producao")

    // Cache local de atividades para evitar leituras excessivas do Firestore
    private var activitiesCache: Map<Int, Atividade>? = null

    private suspend fun getActivitiesMap(): Map<Int, Atividade> {
        activitiesCache?.let { return it }

        val teamData = com.chicoeletro.dds.core.LastTeamStore.carregar(context).firstOrNull()
        val teamType = teamData?.teamType ?: "CONSTRUCAO"

        // 1. Tentar ler do catalogo local via MitCatalogManager
        var list = MitCatalogManager.loadLocalCatalog(context, teamType)

        // 2. Se a lista estiver vazia (primeiro acesso), tentar baixar do Storage
        if (list.isEmpty()) {
            val downloaded = MitCatalogManager.downloadCatalog(context, teamType)
            if (downloaded) {
                list = MitCatalogManager.loadLocalCatalog(context, teamType)
            }
        }

        // 3. Fallback para Firestore apenas se a lista continuar vazia
        if (list.isEmpty()) {
            return try {
                val collectionName = when (teamType.uppercase().trim()) {
                    "CONSTRUCAO" -> "atividades_mit"
                    "EP" -> "atividades_mit_ep"
                    "LINHA_VIVA" -> "atividades_mit_lv"
                    "STC", "STC_CESTO" -> "atividades_mit_stc"
                    else -> "atividades_mit"
                }
                
                val snapshot = baseDoc.collection(collectionName)
                    .get()
                    .await()

                val map = snapshot.documents.mapNotNull { doc ->
                    val ativo = doc.getBoolean("ativo") ?: true
                    if (!ativo) return@mapNotNull null
                    val codigo = doc.getLong("codigo")?.toInt() ?: return@mapNotNull null
                    val tarefa = doc.getString("tarefa") ?: doc.getString("descricao") ?: "Atividade $codigo"
                    val usMontagem = doc.getDouble("us_montagem") ?: 0.0
                    val usDesmontagem = doc.getDouble("us_desmontagem") ?: 0.0
                    val calculoDinamico = doc.getBoolean("calculo_dinamico") ?: false
                    val tipoCalculo = doc.getString("tipo_calculo")

                    codigo to Atividade(
                        codigo = codigo,
                        descricao = tarefa,
                        us_montagem = usMontagem,
                        us_desmontagem = usDesmontagem,
                        calculo_dinamico = calculoDinamico,
                        tipo_calculo = tipoCalculo
                    )
                }.toMap()

                activitiesCache = map
                map
            } catch (e: Exception) {
                emptyMap()
            }
        }

        val map = list.associateBy { it.codigo }
        activitiesCache = map
        return map
    }

    /**
     * Lista todos os projetos disponíveis no Firestore.
     */
    suspend fun getProjetos(): List<Projeto> {
        val snapshot = baseDoc.collection("projetos")
            .get()
            .await()

        return snapshot.documents.mapNotNull { doc ->
            val id = doc.getString("id") ?: doc.id
            val titulo = doc.getString("titulo") ?: "Sem Título"
            val dataImportacao = doc.getString("data_importacao") ?: ""
            Projeto(id, titulo, dataImportacao)
        }.sortedByDescending { it.data_importacao }
    }

    /**
     * Busca todas as estruturas vinculadas a um projeto.
     */
    suspend fun getEstruturas(projetoId: String): List<Estrutura> {
        val snapshot = baseDoc.collection("estruturas")
            .whereEqualTo("projeto_id", projetoId)
            .get()
            .await()

        val estruturas = snapshot.documents.mapNotNull { doc ->
            val id = doc.getLong("id")?.toInt() ?: return@mapNotNull null
            val projId = doc.getString("projeto_id") ?: projetoId
            val identificador = doc.getString("identificador") ?: ""
            val tipo = doc.getString("tipo") ?: "PS"
            val descricaoResumida = doc.getString("descricao_resumida")
            Estrutura(id, projId, identificador, tipo, descricaoResumida)
        }

        // Ordenação natural de identificadores (ex: PS 1, PS 2)
        return try {
            val regex = Regex("\\d+")
            estruturas.sortedBy { est ->
                regex.find(est.identificador)?.value?.toIntOrNull() ?: 0
            }
        } catch (e: Exception) {
            estruturas.sortedBy { it.identificador }
        }
    }

    /**
     * Busca todas as tarefas de todas as estruturas vinculadas a um projeto.
     */
    suspend fun getTodasTarefasProjeto(projetoId: String): List<Tarefa> {
        val snapshot = baseDoc.collection("estruturas")
            .whereEqualTo("projeto_id", projetoId)
            .get()
            .await()

        val activitiesMap = getActivitiesMap()
        val todasTarefas = mutableListOf<Tarefa>()

        for (doc in snapshot.documents) {
            val estruturaId = doc.getLong("id")?.toInt() ?: continue
            val tarefasRaw = doc.get("tarefas") as? List<Map<String, Any>> ?: continue
            for (map in tarefasRaw) {
                val id = (map["id"] as? Number)?.toInt() ?: continue
                val codigo = (map["codigo"] as? Number)?.toInt() ?: continue
                val quantidade = (map["quantidade"] as? Number)?.toDouble() ?: 0.0
                val sinal = map["sinal"] as? String ?: "+"

                val atividade = activitiesMap[codigo]
                val descricao = atividade?.descricao ?: "Atividade $codigo"
                val usMontagem = atividade?.us_montagem ?: 0.0
                val usDesmontagem = atividade?.us_desmontagem ?: 0.0

                todasTarefas.add(
                    Tarefa(
                        id = id,
                        estrutura_id = estruturaId,
                        atividade_codigo = codigo,
                        quantidade = quantidade,
                        sinal = sinal,
                        descricao = descricao,
                        us_montagem = usMontagem,
                        us_desmontagem = usDesmontagem
                    )
                )
            }
        }
        return todasTarefas
    }


    /**
     * Busca as tarefas de uma estrutura e preenche os detalhes da atividade (descrição, US).
     */
    suspend fun getTarefas(estruturaId: Int): List<Tarefa> {
        val doc = baseDoc.collection("estruturas")
            .document(estruturaId.toString())
            .get()
            .await()

        if (!doc.exists()) return emptyList()

        val tarefasRaw = doc.get("tarefas") as? List<Map<String, Any>> ?: return emptyList()
        val activitiesMap = getActivitiesMap()

        return tarefasRaw.mapNotNull { map ->
            val id = (map["id"] as? Number)?.toInt() ?: return@mapNotNull null
            val codigo = (map["codigo"] as? Number)?.toInt() ?: return@mapNotNull null
            val quantidade = (map["quantidade"] as? Number)?.toDouble() ?: 0.0
            val sinal = map["sinal"] as? String ?: "+"

            val atividade = activitiesMap[codigo]
            val descricao = atividade?.descricao ?: "Atividade $codigo"
            val usMontagem = atividade?.us_montagem ?: 0.0
            val usDesmontagem = atividade?.us_desmontagem ?: 0.0

            Tarefa(
                id = id,
                estrutura_id = estruturaId,
                atividade_codigo = codigo,
                quantidade = quantidade,
                sinal = sinal,
                descricao = descricao,
                us_montagem = usMontagem,
                us_desmontagem = usDesmontagem
            )
        }
    }

    /**
     * Busca atividades baseadas em uma query de texto ou código.
     */
    suspend fun buscarAtividades(query: String): List<Atividade> {
        val activitiesMap = getActivitiesMap()
        val cleanQuery = query.trim().lowercase()

        return activitiesMap.values.filter { a ->
            a.codigo.toString().contains(cleanQuery) || a.descricao.lowercase().contains(cleanQuery)
        }.sortedBy { it.codigo }
    }

    /**
     * Registra os lançamentos poste a poste diretamente no Firestore.
     * Suporta gravação offline nativa.
     */
    suspend fun lancarPoste(request: LancamentoPosteRequest): ConstrucaoApiResponse {
        try {
            val tarefas = getTarefas(request.estrutura_id).filter { it.id in request.tarefas_completadas }
            if (tarefas.isEmpty()) {
                return ConstrucaoApiResponse(sucesso = false, detail = "Nenhuma tarefa válida selecionada.")
            }

            val batch = db.batch()

            for (t in tarefas) {
                val tipo = if (t.sinal == "+") "MONTAGEM" else "DESMONTAGEM"
                val usUnitario = if (tipo == "MONTAGEM") t.us_montagem else t.us_desmontagem
                val qtde = request.tarefas_quantidades?.get(t.id.toString()) ?: t.quantidade
                val usCalculada = qtde * usUnitario

                val newDocRef = baseDoc.collection("lancamentos").document()
                val data = mapOf(
                    "equipe_numero" to request.equipe_numero,
                    "data_execucao" to request.data_execucao,
                    "projeto_id" to request.projeto_id,
                    "estrutura_id" to request.estrutura_id,
                    "atividade_codigo" to t.atividade_codigo,
                    "quantidade" to qtde,
                    "tipo" to tipo,
                    "origem" to "POSTE",
                    "us_calculada" to Math.round(usCalculada * 10000.0) / 10000.0
                )
                batch.set(newDocRef, data)
            }

            batch.commit().await()
            return ConstrucaoApiResponse(sucesso = true, mensagem = "${tarefas.size} tarefas lançadas com sucesso!")
        } catch (e: Exception) {
            return ConstrucaoApiResponse(sucesso = false, detail = e.message ?: "Erro desconhecido")
        }
    }

    /**
     * Registra o lote de lançamentos diretamente no Firestore.
     * Suporta gravação offline nativa.
     */
    suspend fun lancarLote(request: LancamentoLoteRequest): ConstrucaoApiResponse {
        try {
            if (request.itens.isEmpty()) {
                return ConstrucaoApiResponse(sucesso = false, detail = "Lista de itens vazia.")
            }

            val activitiesMap = getActivitiesMap()
            val batch = db.batch()

            for (it in request.itens) {
                val mit = activitiesMap[it.codigo] ?: Atividade(
                    codigo = it.codigo,
                    descricao = "Atividade ${it.codigo}",
                    us_montagem = 0.0,
                    us_desmontagem = 0.0,
                    calculo_dinamico = false
                )

                val isDinamico = mit.calculo_dinamico == true
                val tipoLanc = it.tipo.uppercase()

                val usCalculada = if (isDinamico) {
                    val elems = it.elementos ?: 0
                    val dist = it.distancia ?: 0.0
                    val hrs = it.horas ?: 0.0

                    when (mit.tipo_calculo) {
                        "deslocamento", "deslocamento_adicional", "deslocamento_cancelado" -> {
                            0.045 * elems * dist
                        }
                        "deslocamento_simples" -> {
                            0.045 * dist
                        }
                        "hora_extra", "transporte_meios_alternativos" -> {
                            (hrs + 2.0) * elems
                        }
                        else -> {
                            it.quantidade
                        }
                    }
                } else {
                    val usUnitario = if (tipoLanc == "MONTAGEM") mit.us_montagem else mit.us_desmontagem
                    it.quantidade * usUnitario
                }

                val quantidadeFinal = if (isDinamico) usCalculada else it.quantidade

                val newDocRef = baseDoc.collection("lancamentos").document()
                val data = mutableMapOf<String, Any>(
                    "equipe_numero" to request.equipe_numero,
                    "data_execucao" to request.data_execucao,
                    "atividade_codigo" to it.codigo,
                    "quantidade" to quantidadeFinal,
                    "tipo" to tipoLanc,
                    "origem" to "LOTE",
                    "us_calculada" to Math.round(usCalculada * 10000.0) / 10000.0
                )

                request.projeto_id?.let { data["projeto_id"] = it }
                it.elementos?.let { data["elementos"] = it }
                it.distancia?.let { data["distancia"] = it }
                it.horas?.let { data["horas"] = it }

                batch.set(newDocRef, data)
            }

            batch.commit().await()
            return ConstrucaoApiResponse(sucesso = true, mensagem = "${request.itens.size} itens de lote registrados!")
        } catch (e: Exception) {
            return ConstrucaoApiResponse(sucesso = false, detail = e.message ?: "Erro desconhecido")
        }
    }

    /**
     * Busca as quantidades já lançadas de cada tarefa para uma estrutura específica.
     * Retorna um mapa onde a chave é o par (atividade_codigo, tipo) e o valor é a soma das quantidades lançadas.
     */
    suspend fun getQuantidadesLancadas(projetoId: String, estruturaId: Int): Map<Pair<Int, String>, Double> {
        return try {
            val snapshot = baseDoc.collection("lancamentos")
                .whereEqualTo("projeto_id", projetoId)
                .whereEqualTo("estrutura_id", estruturaId)
                .get()
                .await()

            val map = mutableMapOf<Pair<Int, String>, Double>()
            for (doc in snapshot.documents) {
                val codigo = doc.getLong("atividade_codigo")?.toInt() ?: continue
                val tipo = doc.getString("tipo") ?: "MONTAGEM"
                val qtde = doc.getDouble("quantidade") ?: 0.0

                val key = Pair(codigo, tipo)
                map[key] = (map[key] ?: 0.0) + qtde
            }
            map
        } catch (e: Exception) {
            emptyMap()
        }
    }

    /**
     * Busca as quantidades já lançadas de cada tarefa para um projeto inteiro.
     * Retorna um mapa onde a chave é o par (atividade_codigo, tipo) e o valor é a soma das quantidades lançadas.
     */
    suspend fun getQuantidadesLancadasProjeto(projetoId: String): Map<Pair<Int, String>, Double> {
        return try {
            val snapshot = baseDoc.collection("lancamentos")
                .whereEqualTo("projeto_id", projetoId)
                .get()
                .await()

            val map = mutableMapOf<Pair<Int, String>, Double>()
            for (doc in snapshot.documents) {
                val codigo = doc.getLong("atividade_codigo")?.toInt() ?: continue
                val tipo = doc.getString("tipo") ?: "MONTAGEM"
                val qtde = doc.getDouble("quantidade") ?: 0.0

                val key = Pair(codigo, tipo)
                map[key] = (map[key] ?: 0.0) + qtde
            }
            map
        } catch (e: Exception) {
            emptyMap()
        }
    }

    /**
     * Busca todas as estruturas padrão da coleção "estruturas_padrao" no Firestore.
     */
    suspend fun getEstruturasPadrao(): List<EstruturaPadrao> {
        val snapshot = baseDoc.collection("estruturas_padrao")
            .whereEqualTo("ativo", true)
            .get()
            .await()

        return snapshot.documents.mapNotNull { doc ->
            val id = doc.id
            val nome = doc.getString("nome") ?: return@mapNotNull null
            val tipoRede = doc.getString("tipo_rede") ?: return@mapNotNull null
            val imagens = doc.get("imagens") as? List<String> ?: emptyList()
            val ativo = doc.getBoolean("ativo") ?: true
            val ntc = doc.getString("ntc") ?: ""

            EstruturaPadrao(id, nome, tipoRede, imagens, ativo, ntc)
        }.sortedBy { it.nome }
    }

    /**
     * Registra o lançamento simplificado no Firestore.
     */
    suspend fun lancarSimplificado(request: LancamentoSimplificadoRequest): ConstrucaoApiResponse {
        return try {
            val newDocRef = baseDoc.collection("lancamentos_simplificados").document()
            val data = mutableMapOf<String, Any?>(
                "equipe_numero" to request.equipe_numero,
                "data_execucao" to request.data_execucao,
                "projeto_id" to request.projeto_id,
                "locacao" to request.locacao,
                "cava" to request.cava,
                "poste_comprimento" to request.poste_comprimento,
                "poste_carga" to request.poste_carga,
                "estrutura_categoria" to request.estrutura_categoria,
                "estrutura_nome" to request.estrutura_nome,
                "cabo" to request.cabo,
                "timestamp" to com.google.firebase.firestore.FieldValue.serverTimestamp()
            )
            request.ancoragem?.let { data["ancoragem"] = it }
            request.ancoragem_us?.let { data["ancoragem_us"] = it }
            
            newDocRef.set(data).await()
            ConstrucaoApiResponse(sucesso = true, mensagem = "Lançamento simplificado registrado com sucesso!")
        } catch (e: Exception) {
            ConstrucaoApiResponse(sucesso = false, detail = e.message ?: "Erro desconhecido ao lançar simplificado")
        }
    }
}
