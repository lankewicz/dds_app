// Complete projections only: preserve card rules and DDS data produced by the collector.
(() => {
  const personnelCache = new Map();

  function validate(data, company) {
    if (!data || data.schemaVersion !== 1 || data.company !== company || !Array.isArray(data.items)
        || !Number.isFinite(Date.parse(data.collectedAt)) || !Number.isFinite(Date.parse(data.composedAt))
        || typeof data.stale !== 'boolean' || !data.sources) throw new Error('Projeção do monitor inválida');
    const keys = new Set();
    for (const item of data.items) {
      if (!item || typeof item.teamKey !== 'string' || !item.teamKey || keys.has(item.teamKey)
          || typeof item.active !== 'boolean' || !Array.isArray(item.ddsHistory) || !Array.isArray(item.ddsDays)
          || item.ddsHistory.length !== item.ddsDays.length || !item.ddsTimes || !item.operacional
          || !Number.isFinite(Date.parse(item.updatedAt))) throw new Error('Card incompleto');
      keys.add(item.teamKey);
    }
    for (const name of ['rotalog', 'cadastro', 'dds']) {
      if (!data.sources[name] || typeof data.sources[name].stale !== 'boolean'
          || !Number.isFinite(Date.parse(data.sources[name].updatedAt))) throw new Error('Fonte incompleta');
    }
  }

  function localDateKey(date) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Sao_Paulo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function normalizePersonnel(data, company, date) {
    if (!data || data.schemaVersion !== 1 || data.empresa !== company || data.data !== date
        || !Array.isArray(data.registros)) throw new Error('Arquivo diário de eletricistas inválido');
    const byTeam = new Map();
    for (const record of data.registros) {
      if (!record || typeof record.equipe !== 'string' || !record.equipe.trim()) continue;
      const personnel = (Array.isArray(record.eletricistas) ? record.eletricistas : [])
        .filter(person => person && typeof person.nome === 'string' && person.nome.trim())
        .map(person => ({
          registro: String(person.registro ?? '').trim(),
          nome: person.nome.trim(),
        }));
      const tablet = String(record.tablet ?? '').trim();
      if (personnel.length || tablet) {
        byTeam.set(record.equipe.trim().toUpperCase(), {
          tablet,
          electricians: personnel,
        });
      }
    }
    return byTeam;
  }

  async function readDailyPersonnel(company, forceRefresh = false) {
    const today = localDateKey(new Date());
    const cacheKey = `${company.trim().toLowerCase()}:${today}`;
    const cached = personnelCache.get(cacheKey);
    if (!forceRefresh && cached && Date.now() - cached.at < 5 * 60 * 1000) return cached.byTeam;

    const listing = await window.orangeTorre.listData(
      'rotalog/eletricistas/diario',
      company,
    );
    const candidate = (listing.entries || [])
      .filter(entry => entry.kind === 'file' && /^\d{4}-\d{2}-\d{2}\.json\.gz$/.test(entry.name))
      .map(entry => ({...entry, date: entry.name.slice(0, 10)}))
      .filter(entry => entry.date <= today)
      .sort((left, right) => right.date.localeCompare(left.date))[0];
    if (!candidate || today > candidate.date && (Date.parse(`${today}T00:00:00Z`) - Date.parse(`${candidate.date}T00:00:00Z`)) > 86400000) {
      const empty = new Map();
      personnelCache.set(cacheKey, {at: Date.now(), byTeam: empty});
      return empty;
    }

    const {blob} = await window.orangeTorre.downloadData(candidate.path, company);
    let bytes = new Uint8Array(await blob.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) {
      bytes = new Uint8Array(await new Response(
        new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
      ).arrayBuffer());
    }
    const document = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    const byTeam = normalizePersonnel(document, company, candidate.date);
    personnelCache.set(cacheKey, {at: Date.now(), byTeam});
    return byTeam;
  }

  async function turnos(params) {
    const company = params.get('empresa') || '';
    const {data, source} = await window.orangeTorre.snapshot('monitor', company, validate);
    const active = params.get('active');
    const sector = params.get('setor');
    let personnelByTeam = new Map();
    try {
      personnelByTeam = await readDailyPersonnel(company, params.get('refresh') === 'manual');
    } catch (error) {
      console.warn('Dados de colaboradores do diário Rotalog indisponíveis:', error);
    }
    const items = data.items.filter(item =>
      (!['true', 'false'].includes(active) || item.active === (active === 'true'))
      && (!sector || sector === 'TODOS' || String(item.setor || 'TODOS') === sector))
      .map(item => ({
        ...item,
        copelTablet: personnelByTeam.get(String(item.teamKey || '').trim().toUpperCase())?.tablet || item.tablet,
        copelPersonnel: personnelByTeam.get(String(item.teamKey || '').trim().toUpperCase())?.electricians || [],
      }));
    return {...data, items, empresa: data.company, serverTime: data.collectedAt, dataSource: source};
  }
  window.monitorDirect = {turnos, validate};
})();
