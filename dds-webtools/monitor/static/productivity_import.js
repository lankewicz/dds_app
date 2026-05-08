document.addEventListener('DOMContentLoaded', () => {
    const importModal = document.getElementById('importModal');
    const openBtn = document.getElementById('openImportModalBtn');
    const closeBtn = document.getElementById('importModalClose');
    const cancelBtn = document.getElementById('importModalCancel');
    const fileInput = document.getElementById('importFileInput');
    const monthSelect = document.getElementById('importMonthSelect');
    const yearInput = document.getElementById('importYearInput');
    const executeBtn = document.getElementById('importExecuteBtn');
    const lastJobDiv = document.getElementById('importLastJob');

    // State
    let currentFile = null;

    // Open/Close
    openBtn.addEventListener('click', () => {
        importModal.hidden = false;
        loadLastJob();
    });

    [closeBtn, cancelBtn, document.getElementById('importModalBackdrop')].forEach(el => {
        el.addEventListener('click', () => importModal.hidden = true);
    });

    // File Selection -> Auto Preview
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        currentFile = file;
        await runPreview();
    });

    // Manual triggers for preview
    [monthSelect, yearInput].forEach(el => {
        el.addEventListener('change', () => {
            if (currentFile) runPreview();
        });
    });

    async function loadLastJob() {
        try {
            const res = await fetch('/api/producao/import/last');
            const data = await res.json();
            if (data.ok && data.job) {
                const job = data.job;
                const date = new Date(job.executedAt).toLocaleString();
                lastJobDiv.innerHTML = `
                    <strong>Última importação:</strong> ${job.fileName}<br>
                    Status: ${job.status} | Data: ${date}<br>
                    Documentos: ${job.documentsUpserted}
                `;
            } else {
                lastJobDiv.innerText = "Nenhuma importação recente encontrada.";
            }
        } catch (e) {
            console.error("Erro ao carregar último job", e);
        }
    }

    async function runPreview() {
        const formData = new FormData();
        formData.append('file', currentFile);
        if (monthSelect.value) formData.append('monthNumber', monthSelect.value);
        if (yearInput.value) formData.append('year', yearInput.value);

        showNotice('Analisando arquivo...', 'info');
        executeBtn.disabled = true;

        try {
            const res = await fetch('/api/producao/import/preview', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.detail || 'Erro na análise');

            renderAnalysis(data);
            executeBtn.disabled = false;
            hideNotice();
        } catch (e) {
            showNotice(e.message, 'error');
        }
    }

    function renderAnalysis(data) {
        const summaryDiv = document.getElementById('importDetectedSummary');
        const grid = document.getElementById('importSummaryGrid');
        const issuesDiv = document.getElementById('importIssuesList');

        // Detected competencia
        const det = data.detectedCompetencia;
        summaryDiv.innerHTML = `<strong>Detectado no arquivo:</strong> ${det.label}`;

        // Fill selects if empty
        if (!monthSelect.value) monthSelect.value = data.selectedCompetencia.monthNumber;
        if (!yearInput.value) yearInput.value = data.selectedCompetencia.year;

        // Summary Grid
        grid.hidden = false;
        grid.innerHTML = `
            <div class="summary-item"><strong>${data.summary.rawDataRows}</strong><span>Linhas lidas</span></div>
            <div class="summary-item"><strong>${data.summary.documentsToUpsert}</strong><span>Equipes</span></div>
            <div class="summary-item"><strong>${data.summary.issuesCount}</strong><span>Avisos</span></div>
        `;

        // Issues
        if (data.warningsPreview && data.warningsPreview.length > 0) {
            issuesDiv.hidden = false;
            issuesDiv.innerHTML = '<strong>Avisos:</strong><ul>' + 
                data.warningsPreview.map(w => `<li>${w}</li>`).join('') + 
                '</ul>';
        } else {
            issuesDiv.hidden = true;
        }
    }

    executeBtn.addEventListener('click', async () => {
        if (!confirm('Deseja confirmar a importação dos dados para o Firestore?')) return;

        const formData = new FormData();
        formData.append('file', currentFile);
        if (monthSelect.value) formData.append('monthNumber', monthSelect.value);
        if (yearInput.value) formData.append('year', yearInput.value);

        executeBtn.disabled = true;
        showNotice('Importando dados...', 'info');

        try {
            const res = await fetch('/api/producao/import/execute', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.detail || 'Erro na importação');

            showNotice('Importação concluída com sucesso!', 'success');
            setTimeout(() => {
                importModal.hidden = true;
                window.location.reload(); // Refresh to show new data
            }, 2000);
        } catch (e) {
            showNotice(e.message, 'error');
            executeBtn.disabled = false;
        }
    });

    function showNotice(msg, type) {
        const notice = document.getElementById('importNotice');
        notice.innerText = msg;
        notice.className = `form-notice notice-${type}`;
        notice.hidden = false;
    }

    function hideNotice() {
        document.getElementById('importNotice').hidden = true;
    }
});
