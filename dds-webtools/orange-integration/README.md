# API HTTPS do Orange: preparação

Estado atual e operação em produção: consulte [LEITURA_DIRETA.md](LEITURA_DIRETA.md).
O texto abaixo descreve a preparação inicial.

Esta etapa prepara a API. Não ativa Funnel e não troca a fonte da torre.
O cliente `hosting/orange-torre.js` também não é carregado automaticamente.

## Arquivos no coletor

Copiar `torre_api.py`, `torre-api.service` e `../torre_access.py` para o
projeto do coletor. A API usa apenas a biblioteca padrão do Python e roda
separadamente da raspagem, vinculada somente a `127.0.0.1:8081`.

Criar `.torre-api.env` no Orange, acessível somente pelo usuário do serviço:

```text
TORRE_SIGNING_KEY=<chave aleatória exclusiva com pelo menos 32 bytes>
DDS_EMPRESA_PADRAO=ChicoEletro
TORRE_ALLOWED_ORIGINS=https://chicoeletro.web.app,https://chicoeletro.firebaseapp.com
```

A mesma chave deve ser instalada como secret no Cloud Run, com o nome de
variável `TORRE_SIGNING_KEY`. Não reutilizar APP_SECRET_KEY, não colocar a
chave no JavaScript, Git ou URL. Configurar `TORRE_PUBLIC_URL` no Cloud Run
apenas depois de confirmar o endereço HTTPS do Orange.

O portal emite credenciais de leitura válidas por dez minutos somente para
usuários com permissão de monitor. O navegador guarda a credencial em memória;
não envia cookies do portal ao Orange. Revogar uma permissão impede novas
credenciais; uma credencial emitida pode permanecer válida até dez minutos.
CORS limita origens de navegador, mas a assinatura é a proteção dos dados.

## Ativação no equipamento

Instalar a unit no systemd e iniciar `torre-api`. Confirmar primeiro que as
rotas sem Bearer retornam 401. Depois, habilitar MagicDNS/HTTPS e Funnel no
Tailscale e publicar apenas esta API:

```bash
tailscale funnel --bg 8081
tailscale funnel status
```

Conferir o estado atual do Serve/Funnel antes de alterar: a mesma porta HTTPS
não pode ser compartilhada simultaneamente por ambos. Não servir a pasta do
coletor nem arquivos de credenciais. Funnel não exige Tailscale no cliente.

## Rotas e próxima etapa

- `/api/rotalog/index`: lê o índice local gzip; valida a empresa antes de entregar.
- `/api/torre`: lê `dados-local/torre/current.json`, com `schemaVersion: 1`,
  `company` e `items`. Retorna 503 até esse arquivo existir e ser válido.

Ambas exigem Bearer válido, inclusive em respostas 304. Outros arquivos e
rotas não são publicados. Arquivos inválidos/ausentes retornam 503 sem conteúdo.

Ainda precisamos transportar a composição completa da torre para o coletor:
cadastro, histórico DDS, indicadores e eventos recentes. Não substituir esses
dados por valores vazios. Validar a saída contra a torre atual antes de mudar
`app.js`, o histórico DDS e o feed para esta API. A leitura do índice, sozinha,
não equivale à torre completa.

O endpoint de autorização é chamado ao renovar a credencial, portanto ainda
há chamadas ocasionais ao Cloud Run, mesmo após a migração das atualizações.
