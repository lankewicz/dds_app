// -----------------------------------------------------------------------------
// Arquivo : static/requests.js
// Objetivo: Gerenciar a visualização e aprovação de solicitações de alteração.
// -----------------------------------------------------------------------------

(function() {
    const requestsTab = document.getElementById('requestsTab');
    const requestsView = document.getElementById('requestsView');
    const requestsList = document.getElementById('requestsList');
    const requestsBadge = document.getElementById('requestsBadge');
    const grid = document.getElementById('grid');
    const searchInput = document.getElementById('searchInput');
    const teamSelect = document.getElementById('teamSelect');
    const kpis = document.getElementById('kpis');

    let currentRequests = [];

    async function loadRequests() {
        try {
            const response = await fetch('/api/requests');
            const data = await response.json();
            currentRequests = data;
            renderRequests();
            updateBadge();
        } catch (error) {
            console.error('Erro ao carregar solicitações:', error);
            requestsList.innerHTML = '<div class="emptyState">Erro ao carregar solicitações.</div>';
        }
    }

    function updateBadge() {
        if (!requestsBadge) return;
        const count = currentRequests.length;
        requestsBadge.textContent = count;
        requestsBadge.hidden = count === 0;
    }

    function renderRequests() {
        if (!requestsList) return;
        if (currentRequests.length === 0) {
            requestsList.innerHTML = '<div class="emptyState">Nenhuma solicitação pendente.</div>';
            return;
        }

        requestsList.innerHTML = currentRequests.map(req => {
            const date = new Date(req.requestedAt).toLocaleString('pt-BR');
            const reasonLabel = req.reason === 'VEHICLE_CHANGE' ? 'MUDANÇA DE VEÍCULO (Mantém Histórico)' : 'NOVA EQUIPE (Reseta Histórico)';
            const reasonClass = req.reason === 'VEHICLE_CHANGE' ? 'reasonVehicle' : 'reasonNew';

            return `
                <div class="requestCard">
                    <div class="requestInfo">
                        <div class="requestPrefixes">
                            <span class="prefixOld">${req.oldPrefix}</span>
                            <span class="prefixArrow">➜</span>
                            <span class="prefixNew">${req.newPrefix}</span>
                        </div>
                        <div class="requestReason ${reasonClass}">${reasonLabel}</div>
                        <div class="requestMeta">
                            Solicitado em: ${date}<br>
                            Equipamento: ${req.deviceId} (v${req.appVersion})
                        </div>
                    </div>
                    <div class="requestActions">
                        <button class="btnApprove" onclick="approveRequest('${req.id}')">Aprovar</button>
                        <button class="btnReject" onclick="rejectRequest('${req.id}')">Rejeitar</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    window.approveRequest = async function(id) {
        if (!confirm('Deseja realmente APROVAR esta alteração?')) return;
        try {
            const response = await fetch(`/api/requests/${id}/approve`, { method: 'POST' });
            if (response.ok) {
                loadRequests();
            }
        } catch (error) {
            alert('Erro ao aprovar solicitação.');
        }
    };

    window.rejectRequest = async function(id) {
        if (!confirm('Deseja realmente REJEITAR esta alteração?')) return;
        try {
            const response = await fetch(`/api/requests/${id}/reject`, { method: 'POST' });
            if (response.ok) {
                loadRequests();
            }
        } catch (error) {
            alert('Erro ao rejeitar solicitação.');
        }
    };

    requestsTab?.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Ativa o tab
        document.querySelectorAll('.viewTab').forEach(t => t.classList.remove('isActive'));
        requestsTab.classList.add('isActive');

        // Mostra a view de solicitações e esconde o grid
        grid.hidden = true;
        requestsView.hidden = false;

        // Esconde filtros que não se aplicam
        if (searchInput) searchInput.parentElement.style.display = 'none';
        if (kpis) kpis.style.display = 'none';

        loadRequests();
    });

    // Ao clicar em outros tabs, restaura o grid
    document.querySelectorAll('.viewTab').forEach(tab => {
        if (tab.id === 'requestsTab') return;
        tab.addEventListener('click', () => {
            requestsView.hidden = true;
            grid.hidden = false;
            if (searchInput) searchInput.parentElement.style.display = '';
            if (kpis) kpis.style.display = '';
        });
    });

    // Inicia carregando as solicitações para atualizar o badge
    setInterval(loadRequests, 60000);
    loadRequests();

})();
