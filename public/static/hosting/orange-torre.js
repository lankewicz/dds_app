// Credencial somente em memória. A mudança da fonte da torre é explícita.
(() => {
  let access = null;
  let pending = null;
  const windows = new Map();
  async function credential() {
    if (access && Date.now() < access.until) return access;
    if (!pending) {
      pending = (async () => {
        await window.portalReady;
        const response = await fetch('/api/torre/access', {cache: 'no-store', credentials: 'same-origin'});
        if (!response.ok) throw new Error('Acesso ao Orange indisponível');
        const value = await response.json();
        const endpoint = new URL(value.url);
        if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
            || !['', '/'].includes(endpoint.pathname) || typeof value.token !== 'string'
            || typeof value.company !== 'string' || !(value.expiresIn > 30 && value.expiresIn <= 600)) {
          throw new Error('Credencial do Orange inválida');
        }
        windows.clear();
        access = {...value, until: Date.now() + (value.expiresIn - 30) * 1000};
        return access;
      })().finally(() => { pending = null; });
    }
    return pending;
  }
  async function read(path, company) {
    if (!['/api/torre', '/api/rotalog/index', '/api/rotalog/events'].includes(path)) throw new Error('Rota não permitida');
    const auth = await credential();
    if (company && company.trim().toLowerCase() !== auth.company.trim().toLowerCase()) throw new Error('Orange de outra empresa');
    const cacheKey = `${auth.company}:${path}`;
    const previous = windows.get(cacheKey);
    const headers = {Authorization: 'Bearer ' + auth.token};
    if (previous?.etag) headers['If-None-Match'] = previous.etag;
    const response = await fetch(auth.url.replace(/\/$/, '') + path, {
      headers,
      credentials: 'omit', cache: 'no-cache', signal: AbortSignal.timeout(5000)
    });
    if (response.status === 401) { access = null; windows.clear(); }
    if (response.status === 304 && previous) return previous.data;
    if (!response.ok) throw new Error('Dados do Orange indisponíveis');
    const data = await response.json();
    if (typeof data.company !== 'string' || data.company.trim().toLowerCase() !== auth.company.trim().toLowerCase()) {
      throw new Error('Resposta do Orange de outra empresa');
    }
    windows.set(cacheKey, {etag: response.headers.get('ETag'), data});
    return data;
  }
  function dataPath(relative) {
    const parts = String(relative || '').split('/').filter(Boolean);
    if (parts.some(part => part === '.' || part === '..' || part.includes('\\') || part.includes('\0'))) {
      throw new Error('Caminho de dados inválido');
    }
    return '/api/data' + (parts.length ? '/' + parts.map(encodeURIComponent).join('/') : '');
  }
  async function dataResponse(relative, company, method = 'GET', timeout = 30000) {
    const path = dataPath(relative);
    const auth = await credential();
    if (company && company.trim().toLowerCase() !== auth.company.trim().toLowerCase()) throw new Error('Orange de outra empresa');
    const response = await fetch(auth.url.replace(/\/$/, '') + path, {
      method, headers: {Authorization: 'Bearer ' + auth.token}, credentials: 'omit', cache: 'no-cache',
      signal: AbortSignal.timeout(timeout)
    });
    if (response.status === 401) { access = null; windows.clear(); }
    if (!response.ok) throw new Error('Arquivo do Orange indisponível');
    return {response, company: auth.company};
  }
  async function listData(relative = '', company) {
    const {response, company: authorizedCompany} = await dataResponse(relative, company);
    const data = await response.json();
    if (data.company !== authorizedCompany || !Array.isArray(data.entries)) throw new Error('Catálogo de dados inválido');
    return {...data, source: response.headers.get('X-Data-Source')};
  }
  async function downloadData(relative, company) {
    const {response} = await dataResponse(relative, company);
    return {blob: await response.blob(), source: response.headers.get('X-Data-Source')};
  }
  const snapshotPending = new Map();
  const snapshotCache = new Map();
  async function decodeSnapshot(response) {
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) {
      bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    }
    return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  }
  async function snapshot(kind, company, validate, backupOnly = false) {
    const paths = {monitor: 'torre/current.json', events: 'rotalog/events/current/index.json.gz'};
    if (!paths[kind]) throw new Error('Snapshot não permitido');
    const auth = await credential();
    if (company && company.trim().toLowerCase() !== auth.company.trim().toLowerCase()) throw new Error('Orange de outra empresa');
    const key = auth.company + ':' + kind + (backupOnly ? ':backup' : '');
    const cached = snapshotCache.get(key);
    if (cached && Date.now() - cached.at < 1000) return cached.value;
    if (!snapshotPending.has(key)) snapshotPending.set(key, (async () => {
      let data, source;
      try {
        if (backupOnly) throw new Error('Verificação do backup');
        const {response} = await dataResponse(paths[kind], auth.company, 'GET', 5000);
        data = await decodeSnapshot(response);
        validate(data, auth.company);
        source = 'orangepi';
      } catch (error) {
        const backup = auth.backup?.[kind];
        if (typeof backup !== 'string') throw new Error('Backup Firebase não configurado');
        const url = new URL(backup);
        if (url.protocol !== 'https:' || url.hostname !== 'storage.googleapis.com') throw new Error('Backup inválido');
        const response = await fetch(backup, {credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error('Orange e backup Firebase indisponíveis');
        data = await decodeSnapshot(response);
        validate(data, auth.company);
        source = 'firebase';
      }
      const revision = kind === 'events' ? 'updatedAt' : 'composedAt';
      if (cached && Date.parse(data[revision]) < Date.parse(cached.value.data[revision])) {
        throw new Error('Arquivo anterior à última leitura válida');
      }
      const value = {data, source};
      snapshotCache.set(key, {at: Date.now(), value});
      return value;
    })().finally(() => snapshotPending.delete(key)));
    return snapshotPending.get(key);
  }
  window.orangeTorre = {read, listData, downloadData, snapshot};
})();
