// A interface estática não contém dados de usuários. As APIs autorizam cada operação.
(() => {
  const originalFetch = window.fetch.bind(window);
  const required = document.documentElement.dataset.portalPermission;
  const protectedPage = required !== undefined;
  function message(text) {
    document.documentElement.classList.remove('portal-loading');
    const show = () => {
      const panel = document.createElement('main');
      panel.style.cssText = 'max-width:560px;margin:80px auto;padding:28px;font:16px Arial;background:white;border-radius:12px';
      const title = document.createElement('h1');
      title.textContent = text;
      const retry = document.createElement('button');
      retry.textContent = 'Tentar novamente';
      retry.onclick = () => location.reload();
      panel.append(title, retry);
      document.body.replaceChildren(panel);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', show, {once:true});
    else show();
  }
  window.portalReady = protectedPage ? originalFetch('/api/portal/session', {cache:'no-store', credentials:'same-origin'})
    .then(async response => {
      if (response.status === 401 || response.redirected) {
        location.replace('/login');
        throw new Error('Sessão ausente');
      }
      if (!response.ok) throw new Error('Não foi possível verificar o acesso.');
      const session = await response.json();
      if (required && !session.permissions.includes(required)) {
        location.replace(`/forbidden?permission=${encodeURIComponent(required)}`);
        throw new Error('Área não autorizada');
      }
      return session;
    }) : Promise.resolve(null);
  // Evita requisições dos painéis antes da verificação da sessão.
  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (protectedPage && url.origin === location.origin && url.pathname.includes('/api/')) {
      await window.portalReady;
    }
    const response = await originalFetch(input, options);
    if (protectedPage && url.origin === location.origin && response.status === 401) location.replace('/login');
    return response;
  };
  window.portalReady.catch(error => {
    if (!['Sessão ausente', 'Área não autorizada'].includes(error.message)) message(error.message);
  });
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const session = await window.portalReady;
      if (!session) return;
      document.querySelectorAll('[data-portal-email]').forEach(element => { element.textContent = session.email; });
      document.querySelectorAll('[data-portal-revision]').forEach(element => { element.textContent = session.revision; });
      document.querySelectorAll('[data-permission]').forEach(element => {
        element.hidden = !session.permissions.includes(element.dataset.permission);
      });
      const permission = document.querySelector('[data-denied-permission]');
      if (permission) {
        const key = new URLSearchParams(location.search).get('permission');
        permission.textContent = session.areas[key] || 'esta área';
      }
      if (document.documentElement.dataset.portalPage === 'access-control') {
        const response = await originalFetch('/api/access-control/users', {cache:'no-store'});
        if (!response.ok) throw new Error('Não foi possível carregar os usuários.');
        const data = await response.json();
        // Variáveis da interface de acesso existente, sem dados incorporados ao HTML.
        csrfToken = data.csrfToken;
        currentIsRoot = data.currentIsRoot;
        const list = document.querySelector('.user-list');
        for (const user of data.users) {
          const button = document.createElement('button');
          button.className = 'user-item';
          button.dataset.user = JSON.stringify(user);
          const name = document.createElement('div');
          name.className = 'user-name'; name.textContent = user.name || user.email.split('@')[0];
          const email = document.createElement('div');
          email.className = 'user-email'; email.textContent = user.email;
          const badges = document.createElement('div'); badges.className = 'badges';
          for (const [text, kind] of [[user.approved || user.is_root ? 'Aprovado' : 'Pendente', user.approved || user.is_root ? 'active' : 'inactive'],
                                    [user.is_root ? 'ROOT' : user.role === 'admin' ? 'Admin' : 'User', user.is_root ? 'root' : '']]) {
            const badge = document.createElement('span'); badge.className = `badge ${kind}`; badge.textContent = text; badges.append(badge);
          }
          button.append(name, email, badges);
          button.onclick = () => selectUser(button);
          list.append(button);
        }
      }
      document.documentElement.classList.remove('portal-loading');
    } catch (error) {
      if (!['Sessão ausente', 'Área não autorizada'].includes(error.message)) message(error.message);
    }
  });
})();
