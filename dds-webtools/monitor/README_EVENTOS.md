# Quadro de atividades

A leitura direta do Orange foi preparada e permanece desativada até validar
o ambiente remoto. Consulte [CONFIGURAR_EVENTOS.md](../orange-integration/CONFIGURAR_EVENTOS.md).
O comportamento padrão descrito abaixo continua ativo enquanto
`window.orangeEventsEnabled` for `false`.

A lista lê exclusivamente `rotalog/events/current/index.json.gz` do coletor,
via Firebase Storage no servidor. Não agenda coleta nem deriva eventos dos cards.
O endpoint continua protegido pela autenticação e pela permissão do Monitor.

Para a empresa configurada em `ROTALOG_EMPRESA` (ou `DDS_EMPRESA_PADRAO`),
a raiz vem de `ROTALOG_TEAM_STORAGE_PREFIX`, removendo `/equipes`;
na ausência dessa variável, vem de `ROTALOG_GCS_CACHE_BLOB`, removendo
`/equipes/current/index.json.gz`. O bucket é `DDS_BUCKET_NAME`.

Empresas adicionais precisam de raízes explícitas no JSON de
`ROTALOG_COMPANY_STORAGE_PREFIXES`, por exemplo:
`{"Empresa B":"dados/empresa-b/rotalog"}`. Nunca se reutiliza a raiz da empresa
padrão para uma empresa desconhecida. O campo `company` também é validado.

O leitor usa o TTL adaptativo já utilizado pelo Rotalog. Cache e última janela
válida são isolados por empresa, bucket e caminho, com leituras serializadas.
`updatedAt` antigo não indica indisponibilidade. Respostas válidas substituem a
janela completa, sem truncamento; falhas preservam a última janela e mostram aviso.
Uma lista vazia válida limpa o resultado anterior.

No navegador, o cache `dds_activity_feed_window_v3_…` contém somente janelas
validadas por empresa. A versão nova ignora os antigos eventos reconstruídos.
Consultas simultâneas são agrupadas, e respostas atrasadas de outra empresa são
descartadas. Os filtros continuam limitando as equipes visíveis.

A hora visível é HH:mm em America/Sao_Paulo. A data completa e `timeSource`
ficam nos tooltips. `inferred` recebe o marcador ≈; `consolidated` é descrito
como recebido do diário. Protocolos tipo C de 14 dígitos iniciados por ano
1900–2099 ocultam os quatro dígitos iniciais somente na apresentação.
Turnos e intervalos exibem —. O protocolo original é preservado no tooltip.

Os totais de execução/fila mantêm a fonte e as regras anteriores, em
`teamSummary`, separados dos eventos. Cards, filtros e autenticação não mudam.

Validação local: `node dds-webtools/tests/test_monitor_feed.js`,
`python -m unittest discover -s dds-webtools/tests -p test_rotalog_activity_reader.py`
e os testes de regressão do Monitor/Hosting. O build local não faz deploy.
