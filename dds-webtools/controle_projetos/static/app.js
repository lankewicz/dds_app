const API_URL = window.location.origin + "/controle-projetos";

// Estado global do aplicativo
let currentWeek = getISOWeekString(new Date());
let chartInstance = null;
let selectedFile = null;

// Armazenamento em cache para filtros no cliente
let projetoEstruturas = [];
let itensRealizados = [];

document.addEventListener("DOMContentLoaded", () => {
    inicializarNavegacao();
    inicializarUpload();
    verificarStatusConexao();
    
    // Configurar stepper de semanas
    document.getElementById("prevWeekBtn").addEventListener("click", () => alterarSemana(-1));
    document.getElementById("nextWeekBtn").addEventListener("click", () => alterarSemana(1));
    
    // Atualizar dados iniciais
    atualizarDashboard();
    listarProjetos();
    listarHistorico();
    
    document.getElementById("refreshHistoryBtn").addEventListener("click", listarHistorico);
    
    // Configurar botão de voltar na tela de detalhes
    document.getElementById("backToProjectsBtn").addEventListener("click", () => {
        // Alterna de volta para a aba "importar" (Projetos)
        document.querySelectorAll(".nav-item").forEach(t => t.classList.remove("active"));
        document.querySelector('.nav-item[data-tab="importar"]').classList.add("active");
        document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));
        document.getElementById("tab-importar").classList.add("active");
        listarProjetos();
    });
    
    // Configurar filtro de busca de postes
    document.getElementById("detailSearchStructures").addEventListener("input", filtrarEstruturas);
    
    // Configurar botão de editar descrição do projeto
    document.getElementById("editProjTitleBtn").addEventListener("click", iniciarEdicaoTitulo);
    
    // Configurar busca no manual MIT
    document.getElementById("searchMitInput").addEventListener("input", filtrarAtividadesMit);
    
    // Configurar botões de salvamento/cancelamento do modal MIT
    document.getElementById("cancelEditMitBtn").addEventListener("click", fecharModalEditarMit);
    document.getElementById("saveEditMitBtn").addEventListener("click", salvarEdicaoMit);

    
    // Configurar colapso do card de importação
    const importCardHeader = document.getElementById("importCardHeader");
    const importCardBody = document.getElementById("importCardBody");
    const importChevron = document.getElementById("importChevron");
    
    if (importCardHeader && importCardBody && importChevron) {
        importCardHeader.addEventListener("click", () => {
            const isHidden = importCardBody.style.display === "none" || importCardBody.style.display === "";
            if (isHidden) {
                importCardBody.style.display = "block";
                importChevron.style.transform = "rotate(180deg)";
            } else {
                importCardBody.style.display = "none";
                importChevron.style.transform = "rotate(0deg)";
            }
        });
    }
});

// Helper: Converter data em string "YYYY-Www" (Semana ISO)
function getISOWeekString(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    
    const weekStr = weekNo < 10 ? "0" + weekNo : weekNo;
    return `${d.getUTCFullYear()}-W${weekStr}`;
}

// Helper: Mudar de semana (passo de +1 ou -1 semanas)
function alterarSemana(passo) {
    const [year, weekPart] = currentWeek.split("-W");
    const week = parseInt(weekPart);
    
    let targetDate = new Date(parseInt(year), 0, 1 + (week - 1 + passo) * 7);
    currentWeek = getISOWeekString(targetDate);
    
    atualizarDashboard();
}

// 1. Navegação por Abas
function inicializarNavegacao() {
    const tabs = document.querySelectorAll(".nav-item[data-tab]");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            
            const tabId = tab.dataset.tab;
            document.querySelectorAll(".tab-content").forEach(content => {
                content.classList.remove("active");
            });
            document.getElementById(`tab-${tabId}`).classList.add("active");
            
            // Recarregar dependendo da aba
            if (tabId === "dashboard") atualizarDashboard();
            if (tabId === "importar") listarProjetos();
            if (tabId === "historico") listarHistorico();
            if (tabId === "mit") listarAtividadesMit();
        });
    });
}

// 2. Conectividade com a API
async function verificarStatusConexao() {
    const indicator = document.getElementById("statusIndicator");
    const text = document.getElementById("statusText");
    
    try {
        const response = await fetch(`${API_URL}/api/projetos`);
        if (response.ok) {
            indicator.className = "status-indicator online";
            text.textContent = "API Conectada";
        } else {
            throw new Error();
        }
    } catch {
        indicator.className = "status-indicator offline";
        text.textContent = "Erro na Conexão";
    }
}

// 3. Carregar e Atualizar Dashboard
async function atualizarDashboard() {
    document.getElementById("currentWeekDisplay").textContent = `Semana: ${currentWeek}`;
    
    try {
        const response = await fetch(`${API_URL}/api/dashboard/semanal?semana=${currentWeek}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        let somaMontagem = 0;
        let somaDesmontagem = 0;
        
        const montagemData = [];
        const desmontagemData = [];
        const labels = [];
        
        const dadosEquipes = data.dados.sort((a, b) => a.equipe - b.equipe);
        
        dadosEquipes.forEach(eq => {
            labels.push(`Equipe ${eq.equipe}`);
            montagemData.push(eq.montagem);
            desmontagemData.push(eq.desmontagem);
            
            somaMontagem += eq.montagem;
            somaDesmontagem += eq.desmontagem;
        });
        
        document.getElementById("totalUSMontagem").textContent = `${somaMontagem.toFixed(2)} US`;
        document.getElementById("totalUSDesmontagem").textContent = `${somaDesmontagem.toFixed(2)} US`;
        document.getElementById("totalUSGeral").textContent = `${(somaMontagem + somaDesmontagem).toFixed(2)} US`;
        
        renderizarGrafico(labels, montagemData, desmontagemData);
        
    } catch (e) {
        console.error("Erro ao carregar dados do dashboard:", e);
    }
}

// 4. Renderizar Gráfico no Canvas (Stacked Bar Chart)
function renderizarGrafico(labels, montagem, desmontagem) {
    const ctx = document.getElementById("weeklyProductionChart").getContext("2d");
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Montagem (US)',
                    data: montagem,
                    backgroundColor: '#10b981', 
                    borderRadius: 4,
                },
                {
                    label: 'Desmontagem (US)',
                    data: desmontagem,
                    backgroundColor: '#ef4444', 
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    stacked: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#94a3b8'
                    }
                },
                y: {
                    stacked: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#94a3b8'
                    },
                    title: {
                        display: true,
                        text: 'Unidades de Serviço (US)',
                        color: '#f8fafc'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f8fafc',
                        font: {
                            family: 'Outfit'
                        }
                    }
                }
            }
        }
    });
}

// 5. Configurar Área de Upload
function inicializarUpload() {
    const dropArea = document.getElementById("dropArea");
    const fileInput = document.getElementById("fileInput");
    const fileName = document.getElementById("fileName");
    const uploadBtn = document.getElementById("uploadBtn");
    
    dropArea.addEventListener("click", () => fileInput.click());
    
    dropArea.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropArea.classList.add("drag-over");
    });
    
    dropArea.addEventListener("dragleave", () => {
        dropArea.classList.remove("drag-over");
    });
    
    dropArea.addEventListener("drop", (e) => {
        e.preventDefault();
        dropArea.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });
    
    uploadBtn.addEventListener("click", realizarUpload);
}

function handleFileSelect(file) {
    if (file.type !== "application/pdf") {
        exibirAlerta("Erro: Apenas arquivos PDF são aceitos.", "error");
        selectedFile = null;
        document.getElementById("uploadBtn").disabled = true;
        document.getElementById("fileName").textContent = "Nenhum arquivo selecionado";
        return;
    }
    
    selectedFile = file;
    document.getElementById("fileName").textContent = file.name;
    document.getElementById("uploadBtn").disabled = false;
}

async function realizarUpload() {
    if (!selectedFile) return;
    
    const uploadBtn = document.getElementById("uploadBtn");
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Processando...";
    
    const formData = new FormData();
    formData.append("file", selectedFile);
    
    try {
        const response = await fetch(`${API_URL}/api/projetos/importar`, {
            method: "POST",
            body: formData
        });
        
        const result = await response.json();
        if (response.ok && result.sucesso) {
            const isGeral = result.formato === "GERAL";
            const msg = isGeral 
                ? `Sucesso: Importação GERAL do projeto ${result.projeto_id} realizada!`
                : `Sucesso: Importação DETALHADA da obra "${result.titulo}" (Projeto ${result.projeto_id}) realizada com sucesso!`;
            exibirAlerta(msg, "success");
            selectedFile = null;
            document.getElementById("fileName").textContent = "Nenhum arquivo selecionado";
            listarProjetos();
        } else {
            exibirAlerta(`Erro: ${result.detail || "Falha na análise do projeto."}`, "error");
            uploadBtn.disabled = false;
        }
    } catch (e) {
        exibirAlerta("Erro: Não foi possível se conectar ao servidor backend.", "error");
        uploadBtn.disabled = false;
    } finally {
        uploadBtn.textContent = "Iniciar Importação";
    }
}

function exibirAlerta(msg, tipo) {
    const alert = document.getElementById("importAlert");
    alert.className = `alert ${tipo}`;
    alert.querySelector(".alert-message").textContent = msg;
    
    setTimeout(() => {
        alert.className = "alert hide";
    }, 8000);
}

// 6. Listar Projetos Importados na Tabela
async function listarProjetos() {
    const tbody = document.getElementById("projectsTableBody");
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;">Carregando projetos...</td></tr>';
    
    try {
        const response = await fetch(`${API_URL}/api/projetos`);
        if (!response.ok) return;
        
        const projetos = await response.json();
        if (projetos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--text-secondary);">Nenhum projeto importado ainda.</td></tr>';
            return;
        }
        
        tbody.innerHTML = "";
        projetos.forEach(p => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${p.id}</strong></td>
                <td>${p.titulo}</td>
                <td>${formatarDataHora(p.data_importacao)}</td>
                <td>
                    <button class="btn btn-primary" onclick="verDetalhesProjeto('${p.id}')" style="padding: 6px 12px; font-size: 0.8rem; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">
                        🔍 Detalhes
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--error-color);">Erro ao conectar com a API.</td></tr>';
    }
}

// 7. Visualizar Detalhes do Projeto
async function verDetalhesProjeto(projetoId) {
    // Alternar abas ocultando as demais e exibindo a de detalhes
    document.querySelectorAll(".nav-item").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));
    document.getElementById("tab-detalhes").classList.add("active");
    
    // Configura carregando
    document.getElementById("detailProjTitle").textContent = "Carregando...";
    document.getElementById("detailProjId").textContent = projetoId;
    document.getElementById("detailUsRealizado").textContent = "0.00";
    document.getElementById("detailUsPrevisto").textContent = "0.00";
    document.getElementById("detailProgressBar").style.width = "0%";
    document.getElementById("detailProgressPercentage").textContent = "0%";
    document.getElementById("detailSeparator").style.display = "none";
    document.getElementById("detailImportedFilesList").innerHTML = "";
    document.getElementById("editProjTitleBtn").style.display = "none";
    
    document.getElementById("detailBalanceTableBody").innerHTML = '<tr><td colspan="6" style="text-align:center;">Carregando saldo...</td></tr>';
    document.getElementById("detailStructuresList").innerHTML = '<p style="text-align:center; color:var(--text-secondary); width:100%;">Carregando checklist de postes...</p>';
    document.getElementById("detailSearchStructures").value = "";
    
    // Reseta caches
    projetoEstruturas = [];
    itensRealizados = [];
    
    try {
        // 1. Carrega Resumo Consolidado do Backend
        const resResumo = await fetch(`${API_URL}/api/projetos/${projetoId}/resumo`);
        if (!resResumo.ok) {
            throw new Error("Erro ao carregar resumo do projeto.");
        }
        const resumo = await resResumo.json();
        
        document.getElementById("detailProjTitle").textContent = resumo.titulo;
        document.getElementById("detailUsPrevisto").textContent = resumo.previsto_us.toFixed(2);
        document.getElementById("detailUsRealizado").textContent = resumo.realizado_us.toFixed(2);
        document.getElementById("editProjTitleBtn").style.display = "flex";
        
        // Renderizar arquivos importados
        const separator = document.getElementById("detailSeparator");
        const listDiv = document.getElementById("detailImportedFilesList");
        listDiv.innerHTML = "";
        
        const arqs = resumo.arquivos_importados || [];
        if (arqs.length > 0) {
            arqs.forEach(arq => {
                const tipo = arq.tipo || (arq.nome.toUpperCase().includes("C") ? "C" : "I");
                const label = tipo === "C" ? "Complementar" : "Inicial";
                const badgeClass = tipo === "C" ? "tipo-c" : "tipo-i";
                
                let badgeName = arq.nome;
                if (badgeName.length >= 8 && /^\d{7}[a-zA-Z]/.test(badgeName)) {
                    badgeName = badgeName.substring(0, 8);
                }
                
                const span = document.createElement("span");
                span.className = `file-badge ${badgeClass}`;
                span.title = `Arquivo original: ${arq.nome}\nImportado em ${formatarDataHora(arq.data_importacao)}`;
                span.textContent = `📄 ${badgeName} (${label})`;
                listDiv.appendChild(span);
            });
            separator.style.display = "inline";
        } else {
            separator.style.display = "none";
        }
        
        // Atualizar barra de progresso
        const prog = resumo.progresso_geral;
        document.getElementById("detailProgressBar").style.width = `${Math.min(prog, 100)}%`;
        document.getElementById("detailProgressPercentage").textContent = `${prog.toFixed(1)}%`;
        
        itensRealizados = resumo.itens_realizados || [];
        
        // Renderizar Tabela de Saldo de Atividades
        const balanceTbody = document.getElementById("detailBalanceTableBody");
        balanceTbody.innerHTML = "";
        
        if (resumo.atividades.length === 0) {
            balanceTbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--text-secondary);">Nenhuma atividade prevista no projeto.</td></tr>';
        } else {
            resumo.atividades.forEach(a => {
                const formaPag = a.forma_pagamento || "UNIDADE";
                
                // Montagem
                if (a.previsto.montagem > 0 || a.realizado.montagem > 0) {
                    const saldo = Math.max(0, a.previsto.montagem - a.realizado.montagem);
                    const classEstilo = saldo === 0 ? 'style="color: var(--success-color); font-weight:600;"' : '';
                    
                    const pUs = a.previsto.montagem * a.us_montagem;
                    const rUs = a.realizado.montagem * a.us_montagem;
                    const sUs = Math.max(0, pUs - rUs);
                    const classUsEstilo = sUs === 0 ? 'style="color: var(--success-color); font-weight:600;"' : '';
                    
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${a.codigo}</strong></td>
                        <td style="color:var(--text-secondary); font-size:0.8rem;">${a.descricao}</td>
                        <td><span class="badge montagem">Montagem</span></td>
                        <td><strong style="color: var(--accent-color); font-size: 0.75rem;">${formaPag}</strong></td>
                        <td style="text-align: right;">${a.previsto.montagem.toFixed(2)}</td>
                        <td style="text-align: right; color:var(--success-color); font-weight:500;">${a.realizado.montagem.toFixed(2)}</td>
                        <td style="text-align: right;" ${classEstilo}>${saldo.toFixed(2)}</td>
                        <td style="text-align: right; font-weight:500;">${pUs.toFixed(2)} US</td>
                        <td style="text-align: right; color:var(--success-color); font-weight:500;">${rUs.toFixed(2)} US</td>
                        <td style="text-align: right;" ${classUsEstilo}>${sUs.toFixed(2)} US</td>
                        <td style="text-align: center;">
                            <button class="btn btn-secondary btn-icon" style="padding: 4px 8px; font-size: 0.8rem;" onclick="abrirModalEditarMit(${a.codigo})">✏️</button>
                        </td>
                    `;
                    balanceTbody.appendChild(tr);
                }
                
                // Desmontagem
                if (a.previsto.desmontagem > 0 || a.realizado.desmontagem > 0) {
                    const saldo = Math.max(0, a.previsto.desmontagem - a.realizado.desmontagem);
                    const classEstilo = saldo === 0 ? 'style="color: var(--success-color); font-weight:600;"' : '';
                    
                    const pUs = a.previsto.desmontagem * a.us_desmontagem;
                    const rUs = a.realizado.desmontagem * a.us_desmontagem;
                    const sUs = Math.max(0, pUs - rUs);
                    const classUsEstilo = sUs === 0 ? 'style="color: var(--success-color); font-weight:600;"' : '';
                    
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${a.codigo}</strong></td>
                        <td style="color:var(--text-secondary); font-size:0.8rem;">${a.descricao}</td>
                        <td><span class="badge desmontagem">Desmontagem</span></td>
                        <td><strong style="color: var(--accent-color); font-size: 0.75rem;">${formaPag}</strong></td>
                        <td style="text-align: right;">${a.previsto.desmontagem.toFixed(2)}</td>
                        <td style="text-align: right; color:var(--error-color); font-weight:500;">${a.realizado.desmontagem.toFixed(2)}</td>
                        <td style="text-align: right;" ${classEstilo}>${saldo.toFixed(2)}</td>
                        <td style="text-align: right; font-weight:500;">${pUs.toFixed(2)} US</td>
                        <td style="text-align: right; color:var(--error-color); font-weight:500;">${rUs.toFixed(2)} US</td>
                        <td style="text-align: right;" ${classUsEstilo}>${sUs.toFixed(2)} US</td>
                        <td style="text-align: center;">
                            <button class="btn btn-secondary btn-icon" style="padding: 4px 8px; font-size: 0.8rem;" onclick="abrirModalEditarMit(${a.codigo})">✏️</button>
                        </td>
                    `;
                    balanceTbody.appendChild(tr);
                }
            });
        }
        
        // 2. Carrega lista de Estruturas (Postes e Trechos)
        const resEstruturas = await fetch(`${API_URL}/api/projetos/${projetoId}/estruturas`);
        if (!resEstruturas.ok) {
            throw new Error("Erro ao carregar estruturas.");
        }
        projetoEstruturas = await resEstruturas.json();
        
        // Renderizar estruturas na interface
        renderizarEstruturas(projetoEstruturas);
        
    } catch (e) {
        console.error(e);
        document.getElementById("detailProjTitle").textContent = "Erro de Conectividade";
        document.getElementById("detailBalanceTableBody").innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--error-color);">Erro ao carregar detalhes do projeto.</td></tr>';
        document.getElementById("detailStructuresList").innerHTML = '<p style="text-align:center; color:var(--error-color);">Falha na comunicação com o servidor.</p>';
    }
}

// 8. Renderizar Estruturas na Lista Expansível
function renderizarEstruturas(lista) {
    const container = document.getElementById("detailStructuresList");
    container.innerHTML = "";
    
    if (lista.length === 0) {
        container.innerHTML = '<p style="text-align:center; color:var(--text-secondary); width:100%; padding: 20px;">Nenhuma estrutura encontrada.</p>';
        return;
    }
    
    lista.forEach(est => {
        // Calcular quantas tarefas foram realizadas
        let tarefasCompletadasCount = 0;
        est.tarefas.forEach(t => {
            const tipoTarefa = t.sinal === "+" ? "MONTAGEM" : "DESMONTAGEM";
            const foiRealizada = itensRealizados.some(item => 
                item.estrutura_id === est.id && 
                item.atividade_codigo === t.codigo && 
                item.tipo === tipoTarefa
            );
            if (foiRealizada) tarefasCompletadasCount++;
        });
        
        const totalTarefas = est.tarefas.length;
        const porcentagemConclusao = totalTarefas > 0 ? (tarefasCompletadasCount / totalTarefas * 100) : 0;
        
        // Criar estrutura expansível
        const div = document.createElement("div");
        div.className = "struct-card";
        div.id = `struct-card-${est.id}`;
        
        const badgeTipo = est.tipo === "PS" ? "badge poste" : "badge lote";
        const corChecklist = tarefasCompletadasCount === totalTarefas ? "var(--success-color)" : (tarefasCompletadasCount > 0 ? "var(--accent-color)" : "var(--text-secondary)");
        
        div.innerHTML = `
            <div class="struct-header" onclick="alternarVisibilidadeEstrutura(${est.id})">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:1.1rem;">${est.tipo === 'PS' ? '📍' : '🛣️'}</span>
                    <strong>${est.identificador}</strong>
                    <span class="${badgeTipo}">${est.tipo}</span>
                </div>
                <div style="display:flex; align-items:center; gap:12px;">
                    <span style="font-size:0.8rem; color:${corChecklist}; font-weight:500;">
                        ${tarefasCompletadasCount}/${totalTarefas} tarefas
                    </span>
                    <span class="chevron" id="chevron-${est.id}" style="transition: transform 0.2s; font-size:0.75rem;">▶</span>
                </div>
            </div>
            <div class="struct-body" id="struct-body-${est.id}">
                <!-- Injetar tarefas detalhadas -->
            </div>
        `;
        
        container.appendChild(div);
        
        // Preencher o corpo com as tarefas detalhadas
        const bodyContainer = div.querySelector(`.struct-body`);
        
        est.tarefas.forEach(t => {
            const tipoTarefa = t.sinal === "+" ? "MONTAGEM" : "DESMONTAGEM";
            const foiRealizada = itensRealizados.some(item => 
                item.estrutura_id === est.id && 
                item.atividade_codigo === t.codigo && 
                item.tipo === tipoTarefa
            );
            
            const row = document.createElement("div");
            row.className = "task-detail-row";
            
            const badgeTaskClass = foiRealizada ? "task-badge done" : "task-badge pending";
            const badgeTaskText = foiRealizada ? "✓ Concluída" : "⏳ Pendente";
            const tipoBadge = t.sinal === "+" ? '<span class="badge montagem" style="font-size:0.7rem; padding:2px 4px;">Montagem</span>' : '<span class="badge desmontagem" style="font-size:0.7rem; padding:2px 4px;">Desmontagem</span>';
            
            const descDetalhada = (t.descricao_detalhada && t.descricao_detalhada !== t.descricao) 
                ? `<div class="task-detail-info" style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px; font-style:italic; line-height: 1.3;">${t.descricao_detalhada}</div>` 
                : '';
                
            row.innerHTML = `
                <div style="max-width: 80%;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <strong>Atividade ${t.codigo}</strong>
                        ${tipoBadge}
                        <span style="font-size:0.8rem; color:var(--text-primary); font-weight:500;">Qtd: ${t.quantidade.toFixed(2)}</span>
                    </div>
                    <div class="task-detail-desc" style="font-weight: 600;">${t.descricao || "Descrição indisponível."}</div>
                    ${descDetalhada}
                </div>
                <div>
                    <span class="${badgeTaskClass}">${badgeTaskText}</span>
                </div>
            `;
            bodyContainer.appendChild(row);
        });
    });
}

// 9. Alternar Visualização do Poste/Trecho
function alternarVisibilidadeEstrutura(id) {
    const body = document.getElementById(`struct-body-${id}`);
    const header = body.previousElementSibling;
    const chevron = document.getElementById(`chevron-${id}`);
    
    const isShow = body.classList.contains("show");
    
    // Ocultar outros ativos (opcional para estilo accordion, mas para checklist é melhor deixar livre)
    if (isShow) {
        body.classList.remove("show");
        header.classList.remove("active");
        chevron.style.transform = "rotate(0deg)";
    } else {
        body.classList.add("show");
        header.classList.add("active");
        chevron.style.transform = "rotate(90deg)";
    }
}

// 10. Filtrar Estruturas de acordo com a caixa de pesquisa
function filtrarEstruturas() {
    const query = document.getElementById("detailSearchStructures").value.toLowerCase().trim();
    if (!query) {
        renderizarEstruturas(projetoEstruturas);
        return;
    }
    
    const filtrado = projetoEstruturas.filter(est => 
        est.identificador.toLowerCase().includes(query) || 
        est.tipo.toLowerCase().includes(query)
    );
    
    renderizarEstruturas(filtrado);
}

// 11. Listar Histórico de Produção na Tabela
async function listarHistorico() {
    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">Carregando histórico...</td></tr>';
    
    try {
        const response = await fetch(`${API_URL}/api/lancamentos?limite=50`);
        if (!response.ok) return;
        
        const lancamentos = await response.json();
        if (lancamentos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Nenhum lançamento registrado nesta semana.</td></tr>';
            return;
        }
        
        tbody.innerHTML = "";
        lancamentos.forEach(l => {
            const tr = document.createElement("tr");
            
            const badgeTipo = l.tipo === "MONTAGEM" ? "badge montagem" : "badge desmontagem";
            const badgeOrigem = l.origem === "POSTE" ? "badge poste" : "badge lote";
            const proj_tit = l.projeto_titulo || "-";
            
            tr.innerHTML = `
                <td>${formatarData(l.data_execucao)}</td>
                <td><strong>Equipe ${l.equipe_numero}</strong></td>
                <td><span class="${badgeOrigem}">${l.origem}</span></td>
                <td>${proj_tit}</td>
                <td><span style="color:var(--text-secondary); font-size:0.85rem;">[${l.mit_codigo}]</span> ${l.mit_descricao}</td>
                <td><span class="${badgeTipo}">${l.tipo}</span></td>
                <td>${l.quantidade}</td>
                <td><strong>${l.us_calculada.toFixed(2)} US</strong></td>
            `;
            tbody.appendChild(tr);
        });
    } catch {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--error-color);">Erro ao carregar o histórico de lançamentos.</td></tr>';
    }
}

// Formatar data em português
function formatarDataHora(str) {
    if (!str) return "-";
    const d = new Date(str.replace(" ", "T"));
    return d.toLocaleString("pt-BR");
}

function formatarData(str) {
    if (!str) return "-";
    const [year, month, day] = str.split("-");
    return `${day}/${month}/${year}`;
}

// 12. Iniciar edição inline do título do projeto
function iniciarEdicaoTitulo() {
    const titleH2 = document.getElementById("detailProjTitle");
    const editBtn = document.getElementById("editProjTitleBtn");
    const titleContainer = titleH2.parentElement;
    const projetoId = document.getElementById("detailProjId").textContent;
    
    if (document.getElementById("editProjTitleInput")) return;
    
    const currentTitle = titleH2.textContent;
    
    titleH2.style.display = "none";
    editBtn.style.display = "none";
    
    const editorWrapper = document.createElement("div");
    editorWrapper.id = "editProjTitleWrapper";
    editorWrapper.style.display = "flex";
    editorWrapper.style.alignItems = "center";
    editorWrapper.style.gap = "8px";
    editorWrapper.style.width = "100%";
    
    const input = document.createElement("input");
    input.id = "editProjTitleInput";
    input.type = "text";
    input.value = currentTitle;
    input.style.flexGrow = "1";
    input.style.fontSize = "1.4rem";
    input.style.fontWeight = "600";
    input.style.padding = "6px 12px";
    input.style.backgroundColor = "var(--bg-tertiary)";
    input.style.border = "1px solid var(--primary-color)";
    input.style.borderRadius = "var(--border-radius)";
    input.style.color = "var(--text-primary)";
    input.style.outline = "none";
    
    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-primary";
    saveBtn.textContent = "Salvar";
    saveBtn.style.padding = "6px 16px";
    saveBtn.style.fontSize = "0.9rem";
    saveBtn.style.borderRadius = "8px";
    
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "btn btn-secondary";
    cancelBtn.textContent = "Cancelar";
    cancelBtn.style.padding = "6px 16px";
    cancelBtn.style.fontSize = "0.9rem";
    cancelBtn.style.borderRadius = "8px";
    
    editorWrapper.appendChild(input);
    editorWrapper.appendChild(saveBtn);
    editorWrapper.appendChild(cancelBtn);
    
    titleContainer.insertBefore(editorWrapper, titleH2);
    input.focus();
    input.select();
    
    const cancelEdit = () => {
        editorWrapper.remove();
        titleH2.style.display = "block";
        editBtn.style.display = "flex";
    };
    
    cancelBtn.addEventListener("click", cancelEdit);
    
    const saveEdit = async () => {
        const newTitle = input.value.trim();
        if (!newTitle) {
            alert("A descrição não pode ser vazia.");
            return;
        }
        
        saveBtn.disabled = true;
        cancelBtn.disabled = true;
        saveBtn.textContent = "Salvando...";
        
        try {
            const res = await fetch(`${API_URL}/api/projetos/${projetoId}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ titulo: newTitle })
            });
            
            if (!res.ok) throw new Error("Erro ao salvar a descrição.");
            
            titleH2.textContent = newTitle;
            listarProjetos();
            cancelEdit();
        } catch (err) {
            alert("Erro ao atualizar a descrição: " + err.message);
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
            saveBtn.textContent = "Salvar";
        }
    };
    
    saveBtn.addEventListener("click", saveEdit);
    
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            saveEdit();
        } else if (e.key === "Escape") {
            cancelEdit();
        }
    });
}

// =========================================================================
// TABELA E EDITOR DO MANUAL MIT 163108
// =========================================================================
let mitAtividades = []; // Cache local da lista de atividades do MIT

async function listarAtividadesMit() {
    const tbody = document.getElementById("mitTableBody");
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Carregando manual de atividades...</td></tr>';
    
    try {
        const response = await fetch(`${API_URL}/api/atividades`);
        if (!response.ok) throw new Error("Erro ao carregar atividades do MIT.");
        
        mitAtividades = await response.json();
        renderizarAtividadesMit(mitAtividades);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color: var(--error-color);">${err.message}</td></tr>`;
    }
}

function renderizarAtividadesMit(itens) {
    const tbody = document.getElementById("mitTableBody");
    tbody.innerHTML = "";
    
    if (itens.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--text-secondary);">Nenhuma atividade encontrada.</td></tr>';
        return;
    }
    
    itens.forEach(a => {
        const tr = document.createElement("tr");
        const descTexto = (a.descricao_detalhada && a.descricao_detalhada !== a.tarefa) ? a.descricao_detalhada : "-";
        
        tr.innerHTML = `
            <td><strong>${a.codigo}</strong></td>
            <td style="font-weight: 600;">${a.tarefa}</td>
            <td><span class="badge" style="background-color:var(--bg-tertiary); color:var(--text-primary); border:1px solid var(--border-color);">${a.forma_pagamento}</span></td>
            <td style="color: var(--text-secondary); max-width: 400px; white-space: normal; line-height: 1.4; font-size: 0.8rem;">${descTexto}</td>
            <td style="text-align: right; font-weight: 500;">${a.us_montagem.toFixed(4)} US</td>
            <td style="text-align: right; font-weight: 500;">${a.us_desmontagem.toFixed(4)} US</td>
            <td style="text-align: center;">
                <button class="btn btn-secondary btn-icon" style="padding: 4px 8px; font-size: 0.8rem;" onclick="abrirModalEditarMit(${a.codigo})">✏️ Editar</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function filtrarAtividadesMit() {
    const query = document.getElementById("searchMitInput").value.trim().toLowerCase();
    if (!query) {
        renderizarAtividadesMit(mitAtividades);
        return;
    }
    
    const filtrados = mitAtividades.filter(a => 
        a.codigo.toString().includes(query) || 
        a.tarefa.toLowerCase().includes(query) || 
        (a.descricao_detalhada && a.descricao_detalhada.toLowerCase().includes(query))
    );
    renderizarAtividadesMit(filtrados);
}

async function abrirModalEditarMit(codigo) {
    if (!mitAtividades || mitAtividades.length === 0) {
        try {
            const response = await fetch(`${API_URL}/api/atividades`);
            if (response.ok) {
                mitAtividades = await response.json();
            }
        } catch (err) {
            console.error("Erro ao carregar atividades do MIT:", err);
        }
    }
    const a = mitAtividades.find(item => item.codigo === codigo);
    if (!a) {
        alert(`Atividade ${codigo} não encontrada no manual do MIT.`);
        return;
    }
    
    document.getElementById("editMitCodeBadge").textContent = a.codigo;
    document.getElementById("editMitTarefa").value = a.tarefa;
    document.getElementById("editMitFormaPagamento").value = a.forma_pagamento;
    document.getElementById("editMitUsMontagem").value = a.us_montagem;
    document.getElementById("editMitUsDesmontagem").value = a.us_desmontagem;
    document.getElementById("editMitDescricao").value = a.descricao_detalhada || "";
    
    document.getElementById("editMitModal").style.display = "flex";
}

function fecharModalEditarMit() {
    document.getElementById("editMitModal").style.display = "none";
}

async function salvarEdicaoMit() {
    const codigo = parseInt(document.getElementById("editMitCodeBadge").textContent);
    const tarefa = document.getElementById("editMitTarefa").value.trim();
    const forma_pagamento = document.getElementById("editMitFormaPagamento").value.trim();
    const us_montagem = parseFloat(document.getElementById("editMitUsMontagem").value);
    const us_desmontagem = parseFloat(document.getElementById("editMitUsDesmontagem").value);
    const descricao = document.getElementById("editMitDescricao").value.trim();
    
    if (!tarefa || !forma_pagamento || isNaN(us_montagem) || isNaN(us_desmontagem)) {
        alert("Por favor, preencha todos os campos obrigatórios corretamente.");
        return;
    }
    
    const saveBtn = document.getElementById("saveEditMitBtn");
    const cancelBtn = document.getElementById("cancelEditMitBtn");
    saveBtn.disabled = true;
    cancelBtn.disabled = true;
    saveBtn.textContent = "Salvando...";
    
    try {
        const response = await fetch(`${API_URL}/api/atividades/${codigo}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                tarefa,
                forma_pagamento,
                descricao,
                us_montagem,
                us_desmontagem
            })
        });
        
        if (!response.ok) throw new Error("Erro ao salvar alterações no manual.");
        
        // Atualizar cache local
        const idx = mitAtividades.findIndex(item => item.codigo === codigo);
        if (idx !== -1) {
            mitAtividades[idx].tarefa = tarefa;
            mitAtividades[idx].descricao = tarefa;
            mitAtividades[idx].forma_pagamento = forma_pagamento;
            mitAtividades[idx].descricao_detalhada = descricao;
            mitAtividades[idx].us_montagem = us_montagem;
            mitAtividades[idx].us_desmontagem = us_desmontagem;
        }
        
        renderizarAtividadesMit(mitAtividades);
        
        // Se estiver na tela de detalhes do projeto, recarrega os detalhes para atualizar faturamento e descrições
        const tabDetalhes = document.getElementById("tab-detalhes");
        if (tabDetalhes && tabDetalhes.classList.contains("active")) {
            const projId = document.getElementById("detailProjId").textContent;
            if (projId && projId !== "-") {
                verDetalhesProjeto(projId);
            }
        }
        
        fecharModalEditarMit();
    } catch (err) {
        alert("Erro: " + err.message);
    } finally {
        saveBtn.disabled = false;
        cancelBtn.disabled = false;
        saveBtn.textContent = "Salvar Alterações";
    }
}

// Expor para o escopo global (onclick no HTML deferido)
window.abrirModalEditarMit = abrirModalEditarMit;
