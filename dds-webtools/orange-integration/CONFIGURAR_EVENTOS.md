# Leitura do Orange no Firebase Hosting

**Atualização:** leitura direta ativada em 21/10/2026. Cards, DDS e eventos
estão disponíveis no Orange e no backup privado Firebase. A validação com
sessão real passou nos dois caminhos. Consulte `LEITURA_DIRETA.md` para a
arquitetura, revisão e limitações atuais; os estados de pendência abaixo
registram a preparação anterior.

## Estado em 21/10/2026

API instalada em `/home/orangepi/dds-events-api`, serviço `orange-events-api.service` ativo em `127.0.0.1:8082`. Funnel ativo em https://ddspto1.tail1344e5.ts.net. O usuário autorizou o uso do Funnel para todos os membros. Isso não concede leitura: a API exige token em cada GET/HEAD, inclusive 304.

`/api/data` lista os arquivos; `/api/data/<caminho relativo>` consulta diretórios ou baixa arquivos. Somente leitura; OPTIONS atende CORS. A chave foi gerada no Orange e permanece no `.env` com permissão 600, sem exposição ao navegador.

Fonte principal: `/mnt/ssd/dds-coletor-rtl/chicoeletro/dados-local`. O volume `/mnt/ssd` é conferido pelo UUID `185b3d33-422b-493c-8d1a-ccd3b914f038`.
Alternativa: `/home/orangepi/dds-coletor-rtl/dados-local`, somente quando o SSD estiver indisponível. Arquivo ausente no SSD não aciona a alternativa. `X-Data-Source` informa `ssd` ou `local`. Caminhos fora da raiz e links simbólicos que escapam dela são bloqueados.

## Validação realizada

Leitura autenticada HTTPS: catálogo 200, download gzip válido e HEAD 200. Sem token: 401, também pelo IP público do Funnel com certificado HTTPS validado. POST/PUT/PATCH/DELETE: 405. Travessia: 403. Empresa incorreta: 401. CORS: 204. Escape por symlink bloqueado no Linux.

Fallback do SSD coberto por testes simulados; o SSD real não foi desmontado. O coletor não foi reiniciado nem seus dados alterados.

## Pendências para o portal

Cloud Run configurado com `TORRE_PUBLIC_URL` e `TORRE_SIGNING_KEY`, referenciando a versão 1 do segredo `orange-events-signing-key`. A conta de execução recebeu acesso a esse segredo. A imagem anterior não continha a rota de emissão (404 autenticado); foi criada uma imagem derivada acrescentando somente a rota e `torre_access.py`, preservando o restante do código em produção.

Revisão ativa: `dds-admin-site-00251-z7p`. Imagem: `gcr.io/dds-treinamentos/dds-webtools@sha256:80b2afda5feae00db2fe44b1a3180b37a63d4ddce99e3b686b417de706451c15`. Base: `20261009-103945`. Cloud Build: `5124a1ca-f5a7-47d8-817f-8b5b6067eefb`. Hosting publicado, versão `a727d4dc1765`.

Validação com sessão real concluída em `/portal/orange-check.html`: emissão autorizada, catálogo de ChicoEletro lido diretamente do SSD e segunda consulta aprovada com credencial reutilizada. A página não exibe token nem conteúdo dos arquivos. Testes de credenciais JavaScript e quatro testes Python de autenticação aprovados.

O portal preserva login/permissões e emite credenciais reutilizadas por até dez minutos. O Cloud Run participa dessa autorização ocasional; as leituras saudáveis vão diretamente ao Orange. Tokens ficam somente em memória. Revogar permissões impede novas credenciais; uma já emitida pode valer até expirar.

O arquivo `rotalog/events/current/index.json.gz` ainda não existe nas raízes verificadas do Orange. A rota de eventos responde 503 por esse motivo. `hosting/orange-events-config.js` continua desativado. Confirmar a produção do arquivo antes de ativar e publicar a integração.

A alternativa Firebase do quadro usa a API autorizada existente e ainda passa pelo Cloud Run. Janela vazia válida não aciona a alternativa. Revisão Firebase anterior à última recebida não desfaz correções. A idade de `updatedAt` não caracteriza falha. A pasta local alternativa ao SSD e o fallback Firebase são mecanismos distintos.

## Testes

`python -m unittest discover -s dds-webtools/tests -p test_orange_events_api.py`

14 testes aprovados, com um teste de symlink ignorado no Windows; validado separadamente no Orange/Linux.

`node dds-webtools/tests/test_orange_torre.js`

`node dds-webtools/tests/test_monitor_feed.js`

Ambas as suítes JavaScript aprovadas. Na API remota, `python3 verify_readonly_api.py` aceita opcionalmente a URL HTTPS e não imprime credenciais nem conteúdo dos arquivos.
