// -----------------------------------------------------------------------------
# Arquivo : static/messaging.js
# Objetivo: Gerenciar a exibição do painel lateral de mensagens e as
#           funcionalidades globais de comunicação.
# -----------------------------------------------------------------------------

(function() {
  const messagingSidebar = document.getElementById('messagingSidebar');
  const messagingSidebarClose = document.getElementById('messagingSidebarClose');
  const messagingSidebarThreads = document.getElementById('messagingSidebarThreads');
  const messagesBtn = document.getElementById('messagesBtn');
  const globalMessagesBadge = document.getElementById('globalMessagesBadge');

  if (!messagingSidebar) return;

  function openSidebar() {
    messagingSidebar.hidden = false;
    loadThreads();
  }

  function closeSidebar() {
    messagingSidebar.hidden = true;
  }

  async function loadThreads() {
    messagingSidebarThreads.innerHTML = '<div class="emptyState">Carregando conversas...</div>';
    
    try {
      const currentSector = window.monitorState ? window.monitorState.getCurrentSector() : 'OFICINA';
      const response = await fetch(`/api/mensagens/threads?setor=${encodeURIComponent(currentSector)}`);
      const data = await response.json();
      
      const threads = data.threads || [];
      if (threads.length === 0) {
        messagingSidebarThreads.innerHTML = '<div class="emptyState">Nenhuma conversa ativa</div>';
        return;
      }
      
      messagingSidebarThreads.innerHTML = threads.map(thread => {
        const currentSector = window.monitorState ? window.monitorState.getCurrentSector() : 'OFICINA';
        const isUnread = thread.status === 'NÃO LIDO' && thread.toSetor === currentSector;
        const time = thread.timestamp ? new Date(thread.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
        const date = thread.timestamp ? new Date(thread.timestamp).toLocaleDateString('pt-BR') : '';
        
        return `
          <div class="threadCard ${isUnread ? 'isUnread' : ''}" data-thread-id="${thread.threadId}" data-team-key="${thread.fromEquipe === currentSector ? thread.toEquipe : thread.fromEquipe}">
            <div class="threadCardTop">
              <span class="threadCardFrom">${thread.fromEquipe}</span>
              <span class="threadCardTime">${date} ${time}</span>
            </div>
            <div class="threadCardSubject">${thread.subject}</div>
            <div class="threadCardPreview">${thread.content}</div>
          </div>
        `;
      }).join('');
      
      // Adicionar eventos de clique
      messagingSidebarThreads.querySelectorAll('.threadCard').forEach(card => {
        card.addEventListener('click', () => {
          const teamKey = card.dataset.teamKey;
          if (teamKey && window.teamForm) {
            window.teamForm.openTeamForm(teamKey);
            closeSidebar();
          }
        });
      });
      
    } catch (error) {
      console.error('Erro ao carregar threads:', error);
      messagingSidebarThreads.innerHTML = '<div class="emptyState">Erro ao carregar conversas</div>';
    }
  }

  messagesBtn?.addEventListener('click', openSidebar);
  messagingSidebarClose?.addEventListener('click', closeSidebar);

  // Expõe funções globais se necessário
  window.messaging = {
    openSidebar,
    closeSidebar,
    loadThreads
  };
})();
