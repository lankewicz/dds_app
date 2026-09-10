document.addEventListener('DOMContentLoaded', () => {
    // Navigation Logic
    const navLinks = document.querySelectorAll('.nav-links li');
    const sections = document.querySelectorAll('.page-section');
    const sectionTitle = document.getElementById('section-title');

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const target = link.dataset.section;
            
            // Update Active Link
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            // Update Active Section
            sections.forEach(s => s.classList.remove('active'));
            document.getElementById(target).classList.add('active');

            // Update Title
            sectionTitle.textContent = link.textContent.trim();

            // Toggle Filter Bar Visibility (Hide on Import)
            const filterBar = document.getElementById('global-filter-bar');
            if (target === 'import') {
                filterBar.classList.add('hidden');
            } else {
                filterBar.classList.remove('hidden');
            }

            // Toggle Export Groups
            document.getElementById('dashboard-exports').classList.toggle('hidden', target !== 'dashboard');
            document.getElementById('reports-exports').classList.toggle('hidden', target !== 'reports');

            // Load Section Data (Using current filters)
            if (target === 'dashboard') loadDashboard(getCurrentFilters());
            if (target === 'reports') loadUserReport();
        });
    });

    // Month Names Mapping
    const MONTH_NAMES = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ];

    // API Base URL
    const API_BASE = '/vexpenses/api';

    // Initial Load
    async function init() {
        await loadFilterOptions();
        
        // Selecionar ano atual se não houver um já selecionado
        const currentYear = new Date().getFullYear();
        const yearSelect = document.getElementById('filter-year');
        if (yearSelect && !yearSelect.value) {
            const hasCurrentYear = Array.from(yearSelect.options).some(opt => opt.value == currentYear);
            if (hasCurrentYear) {
                yearSelect.value = currentYear;
            } else if (yearSelect.options.length > 1) {
                yearSelect.selectedIndex = 1; 
            }
        }

        loadDashboard();
    }
    init();

    // Clear Filters Button
    const clearBtn = document.getElementById('clear-filters');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            const yearSelect = document.getElementById('filter-year');
            const monthSelect = document.getElementById('filter-month');
            const approverSelect = document.getElementById('filter-approver');
            const userSelect = document.getElementById('filter-user');
            const statusSelect = document.getElementById('filter-status');

            if (yearSelect) yearSelect.value = new Date().getFullYear();
            if (monthSelect) monthSelect.value = '';
            if (approverSelect) approverSelect.value = '';
            if (userSelect) userSelect.value = '';
            if (statusSelect) statusSelect.value = '';

            const filters = getCurrentFilters();
            if (document.getElementById('dashboard').classList.contains('active')) {
                loadDashboard(filters);
            } else if (document.getElementById('reports').classList.contains('active')) {
                loadUserReport();
            }
            showToast('Filtros limpos.', 'success');
        });
    }

    // Event Listeners for filters
    ['filter-year', 'filter-month', 'filter-approver', 'filter-user', 'filter-status'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                const filters = getCurrentFilters();
                if (document.getElementById('dashboard').classList.contains('active')) {
                    loadDashboard(filters);
                } else if (document.getElementById('reports').classList.contains('active')) {
                    loadUserReport();
                }
            });
        }
    });

    // Dashboard Logic
    function cleanFilters(filters) {
        const cleaned = { ...filters };
        Object.keys(cleaned).forEach(key => {
            if (cleaned[key] === '' || cleaned[key] === null || cleaned[key] === undefined) {
                delete cleaned[key];
            }
        });
        return cleaned;
    }

    function getCurrentFilters() {
        return {
            ano: document.getElementById('filter-year').value,
            mes: document.getElementById('filter-month').value,
            aprovador: document.getElementById('filter-approver').value,
            usuario: document.getElementById('filter-user').value,
            status: document.getElementById('filter-status').value
        };
    }

    function toggleLoading(sectionId, isLoading) {
        const section = document.getElementById(sectionId);
        if (!section) return;
        
        const containers = section.querySelectorAll('.stats-grid, .chart-box, .table-container, .logs-card');
        containers.forEach(c => {
            if (isLoading) {
                c.classList.add('is-loading');
                if (!c.querySelector('.loading-indicator')) {
                    const indicator = document.createElement('div');
                    indicator.className = 'loading-indicator';
                    indicator.textContent = 'Carregando';
                    c.appendChild(indicator);
                }
            } else {
                c.classList.remove('is-loading');
                const indicator = c.querySelector('.loading-indicator');
                if (indicator) indicator.remove();
            }
        });
    }

    async function loadDashboard(filters = null) {
        const currentFilters = filters || getCurrentFilters();
        toggleLoading('dashboard', true);
        try {
            const cleaned = cleanFilters(currentFilters);
            const params = new URLSearchParams(cleaned);
            const response = await fetch(`${API_BASE}/relatorios/resumo-geral?${params}`);
            const data = await response.json();
            
            document.getElementById('stat-total-requested').textContent = formatCurrency(data.total_solicitado);
            document.getElementById('stat-total-approved').textContent = formatCurrency(data.total_aprovado);
            document.getElementById('stat-total-rejected').textContent = formatCurrency(data.total_reprovado);
            document.getElementById('stat-count').textContent = data.total_registros;
            document.getElementById('stat-avg').textContent = formatCurrency(data.ticket_medio_solicitado);
            
            // Atualizar subtítulo
            const subtitle = document.getElementById('stats-subtitle');
            if (subtitle) {
                if (currentFilters.mes) {
                    subtitle.textContent = `${MONTH_NAMES[currentFilters.mes - 1]} / ${currentFilters.ano || 'Todos'}`;
                } else {
                    subtitle.textContent = currentFilters.ano ? `Ano: ${currentFilters.ano}` : 'Período Total';
                }
            }

            // Se houver um mês selecionado, carregar o gráfico diário automaticamente
            if (currentFilters.mes) {
                await loadDailyChart(currentFilters.ano || new Date().getFullYear(), currentFilters.mes, currentFilters);
            } else {
                await loadMonthlyChart(currentFilters);
                updatePieChart(data);
            }
        } catch (error) {
            showToast('Erro ao carregar dados do dashboard', 'error');
        } finally {
            toggleLoading('dashboard', false);
        }
    }
    
    let pieChart = null;
    function updatePieChart(data) {
        const ctx = document.getElementById('pieChart').getContext('2d');
        if (pieChart) pieChart.destroy();

        const labels = ['Aprovado', 'Glosado', 'Reprovado'];
        const values = [
            parseFloat(data.total_aprovado) || 0,
            parseFloat(data.total_glosado) || 0,
            parseFloat(data.total_reprovado) || 0
        ];

        pieChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#10b981', // Verde (Aprovado)
                        '#f59e0b', // Amarelo (Glosado)
                        '#ef4444'  // Vermelho (Reprovado)
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            generateLabels: (chart) => {
                                const data = chart.data;
                                if (data.labels.length && data.datasets.length) {
                                    return data.labels.map((label, i) => {
                                        const value = data.datasets[0].data[i];
                                        const total = data.datasets[0].data.reduce((a, b) => a + b, 0);
                                        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                        return {
                                            text: `${label}: R$ ${formatCompact(value)} (${percentage}%)`,
                                            fillStyle: data.datasets[0].backgroundColor[i],
                                            hidden: false,
                                            index: i
                                        };
                                    });
                                }
                                return [];
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                return `${label}: R$ ${formatCurrency(value)} (${percentage}%)`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    }

    function formatCompact(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
        return num.toFixed(2);
    }

    let monthlyChart = null;
    async function loadMonthlyChart(filters = {}) {
        try {
            const cleaned = cleanFilters(filters);
            const params = new URLSearchParams(cleaned);
            params.set('order', 'asc'); // Gráficos sempre fluem da esquerda para a direita
            const response = await fetch(`${API_BASE}/relatorios/por-mes?${params}`);
            const data = await response.json();

            const ctx = document.getElementById('monthlyChart').getContext('2d');
            const title = document.querySelector('.chart-header h3');
            const backBtn = document.getElementById('chart-back-btn');
            
            if (monthlyChart) monthlyChart.destroy();

            title.textContent = 'Visão Mensal';
            backBtn.classList.add('hidden');

            const labels = data.map(item => `${MONTH_NAMES[item.mes - 1].substring(0, 3)}/${item.ano}`);
            const requested = data.map(item => item.total_solicitado);
            const approved = data.map(item => item.total_aprovado);
            const rejected = data.map(item => item.total_reprovado);

            monthlyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Solicitado',
                            data: requested,
                            borderColor: '#6366f1',
                            backgroundColor: 'rgba(99, 102, 241, 0.1)',
                            fill: true,
                            tension: 0.4
                        },
                        {
                            label: 'Aprovado',
                            data: approved,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4
                        },
                        {
                            label: 'Reprovado',
                            data: rejected,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    },
                    scales: {
                        y: { beginAtZero: true }
                    },
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const item = data[index]; // Pegar o objeto de dados original
                            const month = item.mes;
                            const year = item.ano;
                            
                            // Sincronizar filtros globais de data
                            document.getElementById('filter-month').value = month;
                            if (!document.getElementById('filter-year').value) {
                                document.getElementById('filter-year').value = year;
                            }
                            
                            loadDailyChart(year, month, filters);
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Erro ao carregar gráfico:', error);
        }
    }

    async function loadDailyChart(year, month, filters = {}) {
        toggleLoading('dashboard', true);
        try {
            const params = new URLSearchParams({
                ...filters,
                ano: year,
                mes: month
            });
            const response = await fetch(`${API_BASE}/relatorios/por-dia?${params}`);
            const data = await response.json();

            const ctx = document.getElementById('monthlyChart').getContext('2d');
            const title = document.querySelector('.chart-header h3');
            const backBtn = document.getElementById('chart-back-btn');

            if (monthlyChart) monthlyChart.destroy();
            
            // Corrigir Título
            title.textContent = `Evolução Diária - ${MONTH_NAMES[month - 1]} / ${year}`;
            backBtn.classList.remove('hidden');
            
            if (!data || !Array.isArray(data)) {
                console.error('Dados inválidos para o gráfico diário:', data);
                return;
            }

            // Corrigir Nomes do Gráfico de Linha (Zoom)
            const labels = data.map(item => item.dia);
            const requested = data.map(item => item.total_solicitado);
            const approved = data.map(item => item.total_aprovado);
            const rejected = data.map(item => item.total_reprovado);
            
            // Totais para os Cards e para a Rosca
            let totalRequested = 0;
            let totalApproved = 0;
            let totalRejected = 0;
            let totalGlosed = 0;
            let totalCount = 0;
            
            data.forEach(item => {
                totalRequested += parseFloat(item.total_solicitado) || 0;
                totalApproved += parseFloat(item.total_aprovado) || 0;
                totalRejected += parseFloat(item.total_reprovado) || 0;
                totalGlosed += parseFloat(item.total_glosado) || 0;
                totalCount += parseInt(item.quantidade) || 0;
            });

            // Sincronizar Cards
            document.getElementById('stat-total-requested').textContent = formatCurrency(totalRequested);
            document.getElementById('stat-total-approved').textContent = formatCurrency(totalApproved);
            document.getElementById('stat-total-glosed').textContent = formatCurrency(totalGlosed);
            document.getElementById('stat-total-rejected').textContent = formatCurrency(totalRejected);
            document.getElementById('stat-count').textContent = totalCount;
            document.getElementById('stat-avg').textContent = formatCurrency(totalCount > 0 ? totalRequested / totalCount : 0);
            
            // SINCRONIZAR ROSCA
            updatePieChart({
                total_aprovado: totalApproved,
                total_glosado: totalGlosed,
                total_reprovado: totalRejected
            });

            // Atualizar Subtítulo
            document.getElementById('stats-subtitle').textContent = `Resumo de ${MONTH_NAMES[month - 1]} / ${year}`;

            // Calcular acumulados para as linhas do gráfico
            let currentRequested = 0;
            let currentApproved = 0;
            let currentRejected = 0;
            const cumulativeRequested = requested.map(val => (currentRequested += parseFloat(val)));
            const cumulativeApproved = approved.map(val => (currentApproved += parseFloat(val)));
            const cumulativeRejected = rejected.map(val => (currentRejected += parseFloat(val)));

            const glosed = data.map(d => parseFloat(d.total_glosado) || 0);

            monthlyChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Solicitado (Dia)',
                            data: requested,
                            backgroundColor: 'rgba(99, 102, 241, 0.6)',
                            order: 2
                        },
                        {
                            label: 'Aprovado (Dia)',
                            data: approved,
                            backgroundColor: 'rgba(16, 185, 129, 0.6)',
                            order: 2
                        },
                        {
                            label: 'Glosado (Dia)',
                            data: glosed,
                            backgroundColor: 'rgba(245, 158, 11, 0.6)',
                            order: 2
                        },
                        {
                            label: 'Reprovado (Dia)',
                            data: rejected,
                            backgroundColor: 'rgba(239, 68, 68, 0.6)',
                            order: 2
                        },
                        {
                            label: 'Acumulado Solicitado',
                            data: cumulativeRequested,
                            borderColor: '#6366f1',
                            borderWidth: 2,
                            type: 'line',
                            fill: false,
                            tension: 0.3,
                            yAxisID: 'yAcumulado',
                            order: 1
                        },
                        {
                            label: 'Acumulado Aprovado',
                            data: cumulativeApproved,
                            borderColor: '#10b981',
                            borderWidth: 2,
                            type: 'line',
                            fill: false,
                            tension: 0.3,
                            yAxisID: 'yAcumulado',
                            order: 1
                        },
                        {
                            label: 'Acumulado Reprovado',
                            data: cumulativeRejected,
                            borderColor: '#ef4444',
                            borderWidth: 2,
                            type: 'line',
                            fill: false,
                            tension: 0.3,
                            yAxisID: 'yAcumulado',
                            order: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    },
                    scales: {
                        y: { 
                            beginAtZero: true,
                            title: { display: true, text: 'Valores Diários' }
                        },
                        yAcumulado: {
                            beginAtZero: true,
                            position: 'right',
                            title: { display: true, text: 'Acumulado Mensal' },
                            grid: { drawOnChartArea: false }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Erro ao carregar gráfico diário:', error);
        } finally {
            toggleLoading('dashboard', false);
        }
    }

    async function loadFilterOptions() {
        try {
            const response = await fetch(`${API_BASE}/relatorios/filtros`);
            const data = await response.json();

            const filterApprover = document.getElementById('filter-approver');
            const filterUser = document.getElementById('filter-user');
            const filterYear = document.getElementById('filter-year');

            if (!filterApprover || !filterUser || !filterYear) return;

            console.log('Populando filtros com dados:', data);

            // Guardar valor selecionado
            const selectedYear = filterYear.value;

            // Limpar opções existentes (exceto o primeiro 'Todos')
            filterApprover.innerHTML = '<option value="">Todos</option>';
            filterUser.innerHTML = '<option value="">Todos</option>';
            filterYear.innerHTML = '<option value="">Todos</option>';

            // Populate Years
            if (data.anos && Array.isArray(data.anos)) {
                data.anos.forEach(year => {
                    const opt = document.createElement('option');
                    opt.value = year;
                    opt.textContent = year;
                    filterYear.appendChild(opt);
                });
            }
            
            // Restaurar valor se ainda existir, senão manter padrão (Ano Atual)
            if (selectedYear && selectedYear !== "") {
                filterYear.value = selectedYear;
            } else {
                filterYear.value = new Date().getFullYear();
            }

            // Populate Approvers
            if (data.aprovadores && Array.isArray(data.aprovadores)) {
                data.aprovadores.forEach(approver => {
                    const opt = document.createElement('option');
                    opt.value = approver;
                    opt.textContent = approver;
                    filterApprover.appendChild(opt);
                });
            }

            // Populate Users
            if (data.usuarios && Array.isArray(data.usuarios)) {
                data.usuarios.forEach(user => {
                    const opt = document.createElement('option');
                    opt.value = user;
                    opt.textContent = user;
                    filterUser.appendChild(opt);
                });
            }
        } catch (error) {
            console.error('Erro ao carregar opções de filtro:', error);
        }
    }


    // Reports State
    let reportsState = {
        summaryData: [],
        detailData: [],
        summarySort: { column: 'total_solicitado', direction: 'desc' },
        detailSort: { column: 'data_solicitacao', direction: 'desc' },
        currentView: 'summary', // 'summary' or 'detail'
        reportType: 'users',    // 'users' or 'months'
        activeUser: '',
        activeMonth: null,
        activeYear: null
    };

    // Reports Logic
    async function loadUserReport() {
        toggleLoading('reports', true);
        try {
            reportsState.currentView = 'summary';
            document.getElementById('reports-summary-view').classList.remove('hidden');
            document.getElementById('reports-detail-view').classList.add('hidden');

            const filters = getCurrentFilters();
            const params = new URLSearchParams({
                limite: 200,
                ...(filters.ano && { ano: filters.ano }),
                ...(filters.mes && { mes: filters.mes }),
                ...(filters.status && { status: filters.status }),
                ...(filters.aprovador && { aprovador: filters.aprovador })
            });

            const endpoint = reportsState.reportType === 'users' ? 'top-usuarios' : 'por-mes';
            const response = await fetch(`${API_BASE}/relatorios/${endpoint}?${params}`);
            let data = await response.json();
            
            // Apply client-side user filter if present (only for users report)
            if (reportsState.reportType === 'users' && filters.usuario) {
                const search = filters.usuario.toUpperCase().trim();
                data = data.filter(u => u.usuario_origem.toUpperCase().trim() === search);
            }

            reportsState.summaryData = data;
            renderSummaryTable();
        } catch (error) {
            showToast('Erro ao carregar relatório', 'error');
        } finally {
            toggleLoading('reports', false);
        }
    }

    function renderSummaryTable() {
        const data = sortData(reportsState.summaryData, reportsState.summarySort);
        const table = document.querySelector('#reports-summary-table');
        const thead = table.querySelector('thead tr');
        
        // Atualizar cabeçalhos dinamicamente
        if (reportsState.reportType === 'users') {
            thead.innerHTML = `
                <th class="sortable" data-sort="usuario_origem">Usuário <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="quantidade">Qtd <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_solicitado">Solicitado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_aprovado">Aprovado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_glosado">Glosado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_reprovado">Reprovado <span class="sort-icon">⇅</span></th>
            `;
        } else {
            thead.innerHTML = `
                <th class="sortable" data-sort="mes">Mês/Ano <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="quantidade">Qtd <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_solicitado">Solicitado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_aprovado">Aprovado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_glosado">Glosado <span class="sort-icon">⇅</span></th>
                <th class="sortable" data-sort="total_reprovado">Reprovado <span class="sort-icon">⇅</span></th>
            `;
        }

        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';

        data.forEach((row) => {
            const tr = document.createElement('tr');
            tr.className = 'summary-row clickable';
            
            if (reportsState.reportType === 'users') {
                tr.dataset.user = row.usuario_origem;
                tr.innerHTML = `
                    <td><strong>${row.usuario_origem}</strong></td>
                    <td>${row.quantidade}</td>
                    <td>${formatCurrency(row.total_solicitado)}</td>
                    <td>${formatCurrency(row.total_aprovado)}</td>
                    <td class="text-warning">${formatCurrency(row.total_glosado)}</td>
                    <td class="text-danger">${formatCurrency(row.total_reprovado)}</td>
                `;
                tr.addEventListener('click', () => toggleRowExpansion(tr, row));
            } else {
                tr.innerHTML = `
                    <td><strong>${MONTH_NAMES[row.mes - 1]} / ${row.ano}</strong></td>
                    <td>${row.quantidade}</td>
                    <td>${formatCurrency(row.total_solicitado)}</td>
                    <td>${formatCurrency(row.total_aprovado)}</td>
                    <td class="text-warning">${formatCurrency(row.total_glosado)}</td>
                    <td class="text-danger">${formatCurrency(row.total_reprovado)}</td>
                `;
                tr.addEventListener('click', () => toggleMonthlyRowExpansion(tr, row));
            }
            tbody.appendChild(tr);
        });

        updateSortIcons('reports-summary-table', reportsState.summarySort);
    }

    async function toggleMonthlyRowExpansion(tr, summary) {
        const nextRow = tr.nextElementSibling;
        if (nextRow && nextRow.classList.contains('detail-container-row')) {
            nextRow.remove();
            tr.classList.remove('expanded');
            return;
        }

        tr.classList.add('expanded');
        const detailRow = document.createElement('tr');
        detailRow.className = 'detail-container-row';
        detailRow.innerHTML = `<td colspan="5" class="detail-cell"><div class="loading-mini">Carregando detalhes diários...</div></td>`;
        tr.after(detailRow);

        try {
            const response = await fetch(`${API_BASE}/relatorios/por-dia?ano=${summary.ano}&mes=${summary.mes}`);
            const dailyData = await response.json();

            detailRow.innerHTML = `
                <td colspan="5" class="detail-cell">
                    <div class="nested-table-container">
                        <table class="nested-table">
                            <thead>
                                <tr>
                                    <th>Dia <a href="#" class="expand-all-days" style="margin-left: 10px; font-weight: normal; font-size: 0.7rem; color: var(--primary-color); text-decoration: underline;">(Expandir Todos)</a></th>
                                    <th>Qtd</th>
                                    <th>Solicitado</th>
                                    <th>Aprovado</th>
                                    <th>Glosado</th>
                                    <th>Reprovado</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${dailyData.map(d => `
                                    <tr class="daily-clickable" data-day="${d.dia}" data-month="${summary.mes}" data-year="${summary.ano}">
                                        <td>${String(d.dia).padStart(2, '0')}/${String(summary.mes).padStart(2, '0')}</td>
                                        <td>${d.quantidade}</td>
                                        <td>${formatCurrency(d.total_solicitado)}</td>
                                        <td>${formatCurrency(d.total_aprovado)}</td>
                                        <td class="text-warning">${formatCurrency(d.total_glosado)}</td>
                                        <td class="text-danger">${formatCurrency(d.total_reprovado)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </td>
            `;

            // Adicionar ouvintes para as linhas diárias (terceiro nível)
            detailRow.querySelectorAll('.daily-clickable').forEach(dayRow => {
                dayRow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const { day, month, year } = dayRow.dataset;
                    toggleDailyRecordsExpansion(dayRow, year, month, day);
                });
            });

            // Lógica do botão "Expandir Todos"
            const expandAllBtn = detailRow.querySelector('.expand-all-days');
            if (expandAllBtn) {
                expandAllBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    detailRow.querySelectorAll('.daily-clickable').forEach(dayRow => {
                        if (!dayRow.classList.contains('expanded-day')) {
                            dayRow.click();
                        }
                    });
                });
            }

            // Auto-expandir apenas o primeiro dia para dar contexto imediato
            const firstDayRow = detailRow.querySelector('.daily-clickable');
            if (firstDayRow) {
                firstDayRow.click();
            }

        } catch (err) {
            detailRow.innerHTML = `<td colspan="5" class="detail-cell text-danger">Erro ao carregar detalhes.</td>`;
        }
    }

    function formatApproverName(name) {
        if (!name) return "-";
        const parts = name.trim().split(/\s+/);
        const first = parts[0].toUpperCase();
        if (parts.length === 1) return first;
        const lastInitial = parts[parts.length - 1][0].toUpperCase();
        return `${first} ${lastInitial}.`;
    }

    async function toggleDailyRecordsExpansion(tr, year, month, day) {
        const nextRow = tr.nextElementSibling;
        if (nextRow && nextRow.classList.contains('triple-nested-row')) {
            nextRow.remove();
            tr.classList.remove('expanded-day');
            return;
        }

        tr.classList.add('expanded-day');
        const recordsRow = document.createElement('tr');
        recordsRow.className = 'triple-nested-row';
        const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        recordsRow.innerHTML = `<td colspan="8"><div class="loading-mini">Buscando lançamentos de ${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}...</div></td>`;
        tr.after(recordsRow);

        try {
            const response = await fetch(`${API_BASE}/solicitacoes?data_inicio=${dateStr}&data_fim=${dateStr}&page_size=500`);
            const data = await response.json();

            // Calcular totais para o rodapé
            let sumSolicitado = 0, sumAprovado = 0, sumGlosa = 0, sumRepro = 0;
            data.items.forEach(item => {
                const sol = parseFloat(item.valor_solicitado) || 0;
                const app = parseFloat(item.valor_aprovado) || 0;
                const status = (item.status || "").toLowerCase();
                
                sumSolicitado += sol;
                sumAprovado += app;
                if (status.includes("reprov")) {
                    sumRepro += sol;
                } else if (status.includes("aprov")) {
                    sumGlosa += Math.max(0, sol - app);
                }
            });

            recordsRow.innerHTML = `
                <td colspan="8" class="triple-nested-container">
                    <table class="nested-table" style="background: #fff; border-color: #eee;">
                        <thead style="background: #f1f5f9;">
                            <tr>
                                <th>Usuário</th>
                                <th>Justificativa</th>
                                <th>Solicitado</th>
                                <th>Aprovado</th>
                                <th>Glosado</th>
                                <th>Reprovado</th>
                                <th>Status</th>
                                <th style="text-align: right;">Aprovador</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.items.map(item => {
                                const sol = parseFloat(item.valor_solicitado) || 0;
                                const app = parseFloat(item.valor_aprovado) || 0;
                                const status = (item.status || "").toLowerCase();
                                let glosa = 0, repro = 0;
                                if (status.includes("reprov")) repro = sol;
                                else if (status.includes("aprov")) glosa = Math.max(0, sol - app);

                                return `
                                <tr>
                                    <td>${item.usuario_origem}</td>
                                    <td title="${item.justificativa || ''}">${item.justificativa ? (item.justificativa.substring(0, 20) + '...') : '-'}</td>
                                    <td>${formatCurrency(sol)}</td>
                                    <td>${formatCurrency(app)}</td>
                                    <td class="text-warning">${formatCurrency(glosa)}</td>
                                    <td class="text-danger">${formatCurrency(repro)}</td>
                                    <td><span class="status-badge ${item.status.toLowerCase()}">${item.status}</span></td>
                                    <td style="text-align: right;"><strong>${formatApproverName(item.aprovador)}</strong></td>
                                </tr>
                            `}).join('')}
                            ${data.items.length === 0 ? '<tr><td colspan="8" style="text-align:center">Nenhum lançamento encontrado.</td></tr>' : ''}
                        </tbody>
                        <tfoot style="background: #f8fafc; font-weight: bold;">
                            <tr>
                                <td colspan="2" style="text-align: right;">TOTAIS DO DIA:</td>
                                <td>${formatCurrency(sumSolicitado)}</td>
                                <td>${formatCurrency(sumAprovado)}</td>
                                <td class="text-warning">${formatCurrency(sumGlosa)}</td>
                                <td class="text-danger">${formatCurrency(sumRepro)}</td>
                                <td colspan="2"></td>
                            </tr>
                        </tfoot>
                    </table>
                </td>
            `;
        } catch (err) {
            recordsRow.innerHTML = `<td colspan="8" class="text-danger">Erro ao carregar lançamentos.</td>`;
        }
    }

    async function toggleRowExpansion(tr, summary) {
        const nextRow = tr.nextElementSibling;
        if (nextRow && nextRow.classList.contains('detail-container-row')) {
            nextRow.remove();
            tr.classList.remove('expanded');
            return;
        }

        tr.classList.add('expanded');
        const detailRow = document.createElement('tr');
        detailRow.className = 'detail-container-row';
        detailRow.innerHTML = `<td colspan="5" class="detail-cell"><div class="loading-mini">Carregando detalhes...</div></td>`;
        tr.after(detailRow);

        try {
            const filters = getCurrentFilters();
            const params = new URLSearchParams({
                usuario: summary.usuario_origem,
                ...(filters.ano && { ano: filters.ano }),
                ...(filters.mes && { mes: filters.mes }),
                ...(filters.status && { status: filters.status }),
                ...(filters.aprovador && { aprovador: filters.aprovador })
            });
            const response = await fetch(`${API_BASE}/solicitacoes?${params}`);
            const result = await response.json();
            
            renderExpandedDetails(detailRow.querySelector('.detail-cell'), result.items, summary);
        } catch (error) {
            detailRow.querySelector('.detail-cell').innerHTML = 'Erro ao carregar detalhes';
        }
    }

    function renderExpandedDetails(container, details, summary) {
        let html = `
            <table class="nested-detail-table">
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Justificativa</th>
                        <th>Vl. Solicitado</th>
                        <th>Vl. Aprovado</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        details.forEach(req => {
            html += `
                <tr>
                    <td>${new Date(req.data_solicitacao).toLocaleDateString()}</td>
                    <td>${req.justificativa || '-'}</td>
                    <td>${formatCurrency(req.valor_solicitado)}</td>
                    <td>${formatCurrency(req.valor_aprovado)}</td>
                    <td><span class="status-badge ${req.status.toLowerCase()}">${req.status}</span></td>
                </tr>
            `;
        });

        html += `
                <tr class="nested-subtotal">
                    <td colspan="2" style="text-align: right;"><strong>Subtotal [${summary.usuario_origem}]:</strong></td>
                    <td><strong>${formatCurrency(summary.total_solicitado)}</strong></td>
                    <td><strong>${formatCurrency(summary.total_aprovado)}</strong></td>
                    <td>(${details.length} itens)</td>
                </tr>
                </tbody>
            </table>
        `;
        container.innerHTML = html;
    }

    function renderSubtotalRow(tbody, value, count, totalReq, totalApp, colSpan) {
        const tr = document.createElement('tr');
        tr.className = 'subtotal-row';
        // Formata o valor se for data
        let displayValue = value;
        if (value instanceof Date || (typeof value === 'string' && value.match(/^\d{4}-\d{2}-\d{2}/))) {
            displayValue = new Date(value).toLocaleDateString();
        }

        tr.innerHTML = `
            <td colspan="${colSpan - 2}" style="text-align: right; font-weight: bold;">Subtotal [${displayValue}]:</td>
            <td style="font-weight: bold;">${count}</td>
            <td style="font-weight: bold;">${formatCurrency(totalReq)}</td>
            <td style="font-weight: bold;">${formatCurrency(totalApp)}</td>
            <td></td>
        `;
        tbody.appendChild(tr);
    }

    async function showUserDetails(username) {
        toggleLoading('reports', true);
        try {
            reportsState.currentView = 'detail';
            reportsState.activeUser = username;
            document.getElementById('detail-user-name').textContent = `Detalhes: ${username}`;
            document.getElementById('reports-summary-view').classList.add('hidden');
            document.getElementById('reports-detail-view').classList.remove('hidden');

            const filters = getCurrentFilters();
            const params = new URLSearchParams({
                usuario: username,
                page_size: 500,
                ...(filters.data_inicio && { data_inicio: filters.data_inicio }),
                ...(filters.data_fim && { data_fim: filters.data_fim }),
                ...(filters.status && { status: filters.status }),
                ...(filters.aprovador && { aprovador: filters.aprovador })
            });

            const response = await fetch(`${API_BASE}/solicitacoes?${params}`);
            const result = await response.json();
            
            reportsState.detailData = result.items;
            renderDetailTable();
        } catch (error) {
            showToast('Erro ao carregar detalhes do usuário', 'error');
        } finally {
            toggleLoading('reports', false);
        }
    }

    function renderDetailTable() {
        const data = sortData(reportsState.detailData, reportsState.detailSort);
        const tbody = document.querySelector('#user-details-table tbody');
        tbody.innerHTML = '';

        let lastGroupValue = null;
        let groupTotalRequested = 0;
        let groupTotalApproved = 0;
        let groupCount = 0;

        data.forEach((req, index) => {
            const currentGroupValue = req[reportsState.detailSort.column];
            
            if (lastGroupValue !== null && lastGroupValue !== currentGroupValue) {
                renderSubtotalRowDetail(tbody, lastGroupValue, groupCount, groupTotalRequested, groupTotalApproved);
                groupTotalRequested = 0;
                groupTotalApproved = 0;
                groupCount = 0;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${new Date(req.data_solicitacao).toLocaleDateString()}</td>
                <td class="info-cell">
                    <div class="info-main">${req.justificativa || '-'}</div>
                </td>
                <td>${formatCurrency(req.valor_solicitado)}</td>
                <td>${formatCurrency(req.valor_aprovado)}</td>
                <td>${req.aprovador || '-'}</td>
                <td><span class="status-badge ${req.status.toLowerCase()}">${req.status}</span></td>
            `;
            tbody.appendChild(tr);

            lastGroupValue = currentGroupValue;
            groupTotalRequested += parseFloat(req.valor_solicitado);
            groupTotalApproved += parseFloat(req.valor_aprovado);
            groupCount++;

            if (index === data.length - 1) {
                renderSubtotalRowDetail(tbody, lastGroupValue, groupCount, groupTotalRequested, groupTotalApproved);
            }
        });

        updateSortIcons('user-details-table', reportsState.detailSort);
    }

    function renderSubtotalRowDetail(tbody, value, count, totalReq, totalApp) {
        const tr = document.createElement('tr');
        tr.className = 'subtotal-row';
        let displayValue = value;
        if (value instanceof Date || (typeof value === 'string' && value.match(/^\d{4}-\d{2}-\d{2}/))) {
            displayValue = new Date(value).toLocaleDateString();
        }

        tr.innerHTML = `
            <td colspan="2" style="text-align: right; font-weight: bold;">Subtotal [${displayValue}]:</td>
            <td style="font-weight: bold;">${formatCurrency(totalReq)}</td>
            <td style="font-weight: bold;">${formatCurrency(totalApp)}</td>
            <td colspan="2">(${count} itens)</td>
        `;
        tbody.appendChild(tr);
    }

    // Sorting Helper
    function sortData(data, sortConfig) {
        return [...data].sort((a, b) => {
            let valA = a[sortConfig.column];
            let valB = b[sortConfig.column];

            // Handle numeric strings/decimals
            if (!isNaN(valA) && !isNaN(valB)) {
                valA = parseFloat(valA);
                valB = parseFloat(valB);
            }

            if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
            if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });
    }

    function updateSortIcons(tableId, sortConfig) {
        const headers = document.querySelectorAll(`#${tableId} th.sortable`);
        headers.forEach(h => {
            h.classList.remove('sort-asc', 'sort-desc');
            const icon = h.querySelector('.sort-icon');
            if (h.dataset.sort === sortConfig.column) {
                h.classList.add(sortConfig.direction === 'asc' ? 'sort-asc' : 'sort-desc');
                icon.textContent = sortConfig.direction === 'asc' ? '▲' : '▼';
            } else {
                icon.textContent = '⇅';
            }
        });
    }

    // Date Filter Logic: Auto-fill end date
    const autoFillEnd = (startId, endId) => {
        const startInput = document.getElementById(startId);
        const endInput = document.getElementById(endId);
        if (!startInput || !endInput) return;
        startInput.addEventListener('change', () => {
            if (!startInput.value) return;
            const date = new Date(startInput.value + 'T12:00:00'); // Use mid-day to avoid TZ shifts
            const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0);
            const yyyy = lastDay.getFullYear();
            const mm = String(lastDay.getMonth() + 1).padStart(2, '0');
            const dd = String(lastDay.getDate()).padStart(2, '0');
            endInput.value = `${yyyy}-${mm}-${dd}`;
        });
    };

    autoFillEnd('filter-start', 'filter-end');

    // Global Filter Listeners (Automatic)
    const filterInputs = [
        'filter-start', 'filter-end', 
        'filter-approver', 'filter-user', 'filter-status'
    ];

    const triggerFilters = () => {
        const filters = getCurrentFilters();
        const activeSection = document.querySelector('.page-section.active').id;
        
        if (activeSection === 'dashboard') {
            loadDashboard(filters);
        } else if (activeSection === 'reports') {
            if (reportsState.currentView === 'summary') {
                loadUserReport();
            } else {
                showUserDetails(reportsState.activeUser);
            }
        }
    };

    filterInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', triggerFilters);
    });

    // Remove old apply-filters listener (button will be removed from HTML)

    document.getElementById('clear-filters').addEventListener('click', () => {
        document.getElementById('filter-year').value = new Date().getFullYear();
        document.getElementById('filter-start').value = '';
        document.getElementById('filter-end').value = '';
        document.getElementById('filter-approver').value = '';
        document.getElementById('filter-user').value = '';
        document.getElementById('filter-status').value = '';
        
        const activeSection = document.querySelector('.page-section.active').id;
        if (activeSection === 'dashboard') {
            loadDashboard();
        } else if (activeSection === 'reports') {
            loadUserReport();
        }
    });

    // Sorting Listeners (Event Delegation)
    document.addEventListener('click', (e) => {
        const header = e.target.closest('th.sortable');
        if (!header) return;
        
        const table = header.closest('table');
        if (!table) return;
        
        const tableId = table.id;
        const column = header.dataset.sort;
        const stateKey = tableId === 'reports-summary-table' ? 'summarySort' : 'detailSort';
        
        if (reportsState[stateKey].column === column) {
            reportsState[stateKey].direction = reportsState[stateKey].direction === 'asc' ? 'desc' : 'asc';
        } else {
            reportsState[stateKey].column = column;
            reportsState[stateKey].direction = 'asc';
        }

        if (tableId === 'reports-summary-table') renderSummaryTable();
        else renderDetailTable();
    });

    // Back button logic
    document.getElementById('back-to-summary').addEventListener('click', () => {
        reportsState.currentView = 'summary';
        document.getElementById('reports-summary-view').classList.remove('hidden');
        document.getElementById('reports-detail-view').classList.add('hidden');
    });

    // Import Logic
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileStatus = document.getElementById('file-status');
    const fileName = document.getElementById('file-name');
    const uploadBtn = document.getElementById('upload-btn');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', () => handleFiles(fileInput.files));

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.name.endsWith('.xlsx')) {
                fileName.textContent = file.name;
                fileStatus.classList.remove('hidden');
                uploadBtn.disabled = false;
            } else {
                showToast('Por favor, envie um arquivo .xlsx', 'error');
            }
        }
    }

    uploadBtn.addEventListener('click', async () => {
        const file = fileInput.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        const progressDiv = document.getElementById('import-progress');
        const progressFill = document.getElementById('progress-fill');
        const progressStatus = document.getElementById('progress-status');
        const importLog = document.getElementById('import-log');

        const cancelBtn = document.getElementById('cancel-import-btn');
        uploadBtn.disabled = true;
        progressDiv.classList.remove('hidden');
        cancelBtn.classList.remove('hidden');
        importLog.classList.add('hidden');
        
        // Simular fases do progresso
        updateProgress(20, 'Enviando arquivo para o servidor...');

        try {
            const response = await fetch(`${API_BASE}/importacoes/upload`, {
                method: 'POST',
                body: formData
            });

            let errorMessage = 'Erro ao processar arquivo';
            let result = {};

            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/json")) {
                result = await response.json();
                errorMessage = result.detail || errorMessage;
            } else {
                const text = await response.text();
                errorMessage = `Erro do Servidor (${response.status}): ${text.substring(0, 100)}`;
            }

            if (response.ok) {
                const startTime = Date.now();
                const cancelBtn = document.getElementById('cancel-import-btn');
                cancelBtn.onclick = async () => {
                    if (confirm('Deseja realmente parar a importação? O que já foi processado permanecerá na base.')) {
                        await fetch(`${API_BASE}/importacoes/${result.id}/cancel`, { method: 'POST' });
                        cancelBtn.classList.add('hidden');
                        showToast('Solicitação de cancelamento enviada.', 'info');
                    }
                };

                // Iniciar Polling para acompanhar o processamento real no servidor
                const pollStatus = async () => {
                    try {
                        const statusRes = await fetch(`${API_BASE}/importacoes/${result.id}`);
                        const batch = await statusRes.json();
                        
                        // Cálculos de Tempo
                        const now = Date.now();
                        const elapsedSec = Math.floor((now - startTime) / 1000);
                        const processed = batch.inserted_count + batch.updated_count + batch.unchanged_count;
                        
                        document.getElementById('elapsed-time').textContent = formatTime(elapsedSec);
                        
                        if (processed > 10 && batch.status === 'processing') {
                            const secPerRow = elapsedSec / processed;
                            const remainingRows = batch.total_rows - processed;
                            const etaSec = Math.floor(secPerRow * remainingRows);
                            document.getElementById('remaining-time').textContent = `Restam ~${formatTime(etaSec)}`;
                        } else if (batch.status === 'completed') {
                            document.getElementById('remaining-time').textContent = 'Finalizado';
                        }
                        
                        updateProgress(batch.progress, `Processando: ${batch.progress}% (${processed}/${batch.total_rows})`);
                        
                        if (batch.status === 'completed') {
                            updateProgress(100, 'Concluído!');
                            cancelBtn.classList.add('hidden');
                            setTimeout(() => {
                                progressDiv.classList.add('hidden');
                                showToast('Importação concluída!', 'success');
                                showImportResults(batch);
                                loadFilterOptions();
                            }, 800);
                        } else if (batch.status === 'cancelled') {
                            updateProgress(batch.progress, 'Importação Cancelada');
                            cancelBtn.classList.add('hidden');
                            setTimeout(() => {
                                progressDiv.classList.add('hidden');
                                showToast('Importação interrompida pelo usuário.', 'warning');
                                showImportResults(batch);
                                loadFilterOptions();
                            }, 1500);
                        } else if (batch.status === 'failed') {
                            progressDiv.classList.add('hidden');
                            cancelBtn.classList.add('hidden');
                            showToast(`Erro no processamento: ${batch.error_message || 'Erro desconhecido'}`, 'error');
                        } else {
                            // Continuar polling
                            setTimeout(pollStatus, 1500);
                        }
                    } catch (pollError) {
                        console.error('Erro no polling:', pollError);
                        // Tentar novamente após erro
                        setTimeout(pollStatus, 3000);
                    }
                };
                
                pollStatus();
            } else {
                progressDiv.classList.add('hidden');
                console.error('Server error:', errorMessage);
                showToast(errorMessage, 'error');
            }
        } catch (error) {
            progressDiv.classList.add('hidden');
            console.error('Upload connection error:', error);
            showToast('Erro de conexão. Verifique o servidor.', 'error');
        } finally {
            uploadBtn.disabled = false;
        }
    });

    function updateProgress(percent, status) {
        const progressFill = document.getElementById('progress-fill');
        const progressStatus = document.getElementById('progress-status');
        progressFill.style.width = `${percent}%`;
        progressStatus.textContent = status;
    }

    function showImportResults(batch) {
        const log = document.getElementById('import-log');
        log.classList.remove('hidden');
        log.innerHTML = `
            <div class="result-summary">
                <p><strong>Lote:</strong> ${batch.id}</p>
                <p><strong>Total de Linhas:</strong> ${batch.total_rows}</p>
                <p>✅ Inseridas: ${batch.inserted_count}</p>
                <p>🔄 Atualizadas: ${batch.updated_count}</p>
                <p>ℹ️ Sem alteração: ${batch.unchanged_count}</p>
                <p>❌ Erros: ${batch.error_count}</p>
            </div>
        `;
    }

    // Helper Functions
    function formatCurrency(value) {
        return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
    }

    function formatTime(seconds) {
        if (!seconds || seconds < 0) return "00:00";
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) {
            return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.classList.remove('hidden');
        toast.style.background = type === 'error' ? '#ef4444' : '#10b981';
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }


    // Alternar Tipos de Relatórios
    const btnReportUsers = document.getElementById('btn-report-users');
    const btnReportMonths = document.getElementById('btn-report-months');

    if (btnReportUsers) {
        btnReportUsers.addEventListener('click', function() {
            if (reportsState.reportType === 'users') return;
            this.classList.add('active');
            btnReportMonths.classList.remove('active');
            document.getElementById('reports-view-title').textContent = 'Resumo por Usuário';
            reportsState.reportType = 'users';
            loadUserReport();
        });
    }

    if (btnReportMonths) {
        btnReportMonths.addEventListener('click', function() {
            if (reportsState.reportType === 'months') return;
            this.classList.add('active');
            btnReportUsers.classList.remove('active');
            document.getElementById('reports-view-title').textContent = 'Resumo por Mês';
            reportsState.reportType = 'months';
            loadUserReport();
        });
    }


    // Rebuild Cache Logic
    const rebuildBtn = document.getElementById('rebuild-cache-btn');
    if (rebuildBtn) {
        rebuildBtn.addEventListener('click', async () => {
            try {
                rebuildBtn.disabled = true;
                rebuildBtn.textContent = 'Iniciando...';
                
                const response = await fetch(`${API_BASE}/system/rebuild-cache`, { method: 'POST' });
                const result = await response.json();
                
                if (response.ok) {
                    showToast('Reconstrução de índices iniciada.', 'success');
                    const taskId = result.task_id;
                    
                    // Polling para mostrar progresso
                    const interval = setInterval(async () => {
                        try {
                            const statusRes = await fetch(`${API_BASE}/system/tasks/${taskId}`);
                            const statusData = await statusRes.json();
                            
                            rebuildBtn.textContent = `${statusData.progress || 0}%...`;
                            
                            if (statusData.status === 'completed') {
                                clearInterval(interval);
                                showToast('Caches reconstruídos com sucesso!', 'success');
                                rebuildBtn.disabled = false;
                                rebuildBtn.textContent = 'Recriar Índices';
                                await loadDashboard();
                            } else if (statusData.status === 'failed') {
                                clearInterval(interval);
                                showToast(`Erro: ${statusData.message}`, 'error');
                                rebuildBtn.disabled = false;
                                rebuildBtn.textContent = 'Recriar Índices';
                            }
                        } catch (e) {
                            clearInterval(interval);
                            rebuildBtn.disabled = false;
                            rebuildBtn.textContent = 'Recriar Índices';
                        }
                    }, 2000);
                } else {
                    showToast(result.detail || 'Erro ao iniciar reconstrução', 'error');
                    rebuildBtn.disabled = false;
                    rebuildBtn.textContent = 'Recriar Índices';
                }
            } catch (error) {
                showToast('Erro de conexão', 'error');
                rebuildBtn.disabled = false;
                rebuildBtn.textContent = 'Recriar Índices';
            }
        });
    }

    // Reset Database Logic
    const resetBtn = document.getElementById('reset-db-btn');
    let resetConfirmState = false;
    let resetTimer = null;

    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            if (!resetConfirmState) {
                // Passo 1: Armar confirmação
                resetConfirmState = true;
                resetBtn.textContent = 'CONFIRMAR AGORA?';
                resetBtn.classList.add('confirming'); // Podemos adicionar estilo no CSS se quiser
                showToast('Clique mais uma vez para confirmar a limpeza completa.', 'warning');
                
                resetTimer = setTimeout(() => {
                    resetConfirmState = false;
                    resetBtn.textContent = 'Limpar Tudo (Clique 2x)';
                    resetBtn.classList.remove('confirming');
                }, 4000);
            } else {
                // Passo 2: Executar
                clearTimeout(resetTimer);
                resetConfirmState = false;
                resetBtn.classList.remove('confirming');

                if (confirm('ATENÇÃO: TODOS os dados serão apagados permanentemente. Deseja continuar?')) {
                    try {
                        resetBtn.textContent = 'Limpando...';
                        resetBtn.disabled = true;
                        
                        const response = await fetch(`${API_BASE}/system/reset-database`, { method: 'POST' });
                        const result = await response.json();
                        
                        if (response.ok && result.task_id) {
                            const taskId = result.task_id;
                            const progressDiv = document.getElementById('import-progress');
                            const cancelBtn = document.getElementById('cancel-import-btn');
                            
                            progressDiv.classList.remove('hidden');
                            cancelBtn.classList.add('hidden');
                            document.getElementById('elapsed-time').textContent = '00:00';
                            document.getElementById('remaining-time').textContent = 'Limpando...';

                            const pollReset = async () => {
                                try {
                                    const res = await fetch(`${API_BASE}/system/tasks/${taskId}`);
                                    const task = await res.json();
                                    
                                    updateProgress(task.progress, task.message);
                                    
                                    if (task.status === 'completed') {
                                        showToast('Limpeza concluída!', 'success');
                                        setTimeout(() => window.location.reload(), 1500);
                                    } else if (task.status === 'failed') {
                                        showToast(`Erro na limpeza: ${task.message}`, 'error');
                                        resetBtn.textContent = 'Limpar Tudo (Clique 2x)';
                                        resetBtn.disabled = false;
                                        progressDiv.classList.add('hidden');
                                    } else {
                                        setTimeout(pollReset, 1000);
                                    }
                                } catch (e) {
                                    console.error('Erro ao pollar limpeza:', e);
                                    setTimeout(pollReset, 2000);
                                }
                            };
                            pollReset();
                        } else {
                            showToast(result.detail || 'Erro ao iniciar limpeza', 'error');
                            resetBtn.textContent = 'Limpar Tudo (Clique 2x)';
                            resetBtn.disabled = false;
                        }
                    } catch (error) {
                        showToast('Erro de conexão', 'error');
                        resetBtn.textContent = 'Limpar Tudo (Clique 2x)';
                        resetBtn.disabled = false;
                    }
                } else {
                    resetBtn.textContent = 'Limpar Tudo (Clique 2x)';
                }
            }
        });
    }

    // Export Logic
    function handleExport(format, filters = {}, sort = null) {
        const cleaned = cleanFilters(filters);
        if (sort) {
            cleaned.sort_by = sort.column;
            cleaned.order = sort.direction;
        }
        const params = new URLSearchParams(cleaned);
        let endpoint = `${API_BASE}/relatorios/exportar-csv`;
        if (format === 'xlsx') endpoint = `${API_BASE}/relatorios/exportar-xlsx`;
        if (format === 'pdf') endpoint = `${API_BASE}/relatorios/exportar-pdf`;
        
        window.open(`${endpoint}?${params}`, '_blank');
    }

    // Dashboard Exports
    document.getElementById('dash-export-xlsx')?.addEventListener('click', () => {
        const filters = getCurrentFilters();
        handleExport('xlsx', filters);
    });

    document.getElementById('dash-export-pdf')?.addEventListener('click', () => {
        const filters = getCurrentFilters();
        handleExport('pdf', filters);
    });

    document.getElementById('dash-print')?.addEventListener('click', () => window.print());

    // Reports Section Exports
    document.getElementById('rep-print-btn').addEventListener('click', () => {
        window.print();
    });

    document.getElementById('rep-export-xlsx').addEventListener('click', () => {
        const filters = getCurrentFilters();
        if (reportsState.currentView === 'detail' && reportsState.activeUser) {
            filters.usuario = reportsState.activeUser;
        }
        const sort = reportsState.currentView === 'summary' ? reportsState.summarySort : reportsState.detailSort;
        handleExport('xlsx', filters, sort);
    });

    document.getElementById('rep-export-pdf').addEventListener('click', () => {
        const filters = getCurrentFilters();
        if (reportsState.currentView === 'detail' && reportsState.activeUser) {
            filters.usuario = reportsState.activeUser;
        }
        const sort = reportsState.currentView === 'summary' ? reportsState.summarySort : reportsState.detailSort;
        handleExport('pdf', filters, sort);
    });

    // Chart Back Button
    document.getElementById('chart-back-btn').addEventListener('click', () => {
        const backBtn = document.getElementById('chart-back-btn');
        const title = document.querySelector('.chart-header h3');
        
        // Limpar filtro de mês ao voltar para a visão anual
        document.getElementById('filter-month').value = '';
        
        backBtn.classList.add('hidden');
        title.textContent = 'Visão Mensal';
        
        loadDashboard(getCurrentFilters());
    });
});
