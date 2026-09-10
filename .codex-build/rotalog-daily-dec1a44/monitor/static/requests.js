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

    let unsubRequests = null;

    function initRealtimeRequests() {
        // Tenta obter a instância do Firestore db do escopo global
        const firestoreDb = window.db || (typeof db !== 'undefined' ? db : null) || (typeof firebase !== 'undefined' && firebase.apps.length ? firebase.firestore() : null);

        if (firestoreDb) {
            console.log("Solicitações em tempo real ativas ⚡");
            try {
                unsubRequests = firestoreDb.collection("monitor/requests/prefix_changes")
                    .where("status", "==", "PENDING")
                    .onSnapshot((snapshot) => {
                        const requests = [];
                        snapshot.forEach((doc) => {
                            const data = doc.data();
                            data.id = doc.id;
                            requests.push(data);
                        });
                        // Ordena por data (mais antigos primeiro para aprovação)
                        requests.sort((a, b) => {
                            const dateA = a.requestedAt || "";
                            const dateB = b.requestedAt || "";
                            return dateA.localeCompare(dateB);
                        });
                        currentRequests = requests;
                        renderRequests();
                        updateBadge();
                    }, (error) => {
                        console.error("Erro no onSnapshot das solicitações:", error);
                        loadRequestsFallback();
                    });
            } catch (err) {
                console.error("Falha ao configurar onSnapshot das solicitações:", err);
                loadRequestsFallback();
            }
        } else {
            console.warn("Firebase SDK não disponível para solicitações. Usando fallback HTTP polling.");
            loadRequestsFallback();
            // Polling de fallback a cada 15 segundos se não houver Firestore em tempo real
            setInterval(loadRequestsFallback, 15000);
        }
    }

    async function loadRequestsFallback() {
        try {
            const response = await fetch('/api/requests');
            const data = await response.json();
            currentRequests = data;
            renderRequests();
            updateBadge();
        } catch (error) {
            console.error('Erro ao carregar solicitações (fallback):', error);
            if (requestsList) {
                requestsList.innerHTML = '<div class="emptyState">Erro ao carregar solicitações.</div>';
            }
        }
    }

    function refreshRequests() {
        if (!unsubRequests) {
            loadRequestsFallback();
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
                refreshRequests();
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
                refreshRequests();
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

        refreshRequests();
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

    // Inicia a escuta em tempo real
    initRealtimeRequests();

})();
