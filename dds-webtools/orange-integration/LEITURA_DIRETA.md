# Monitor: navegador, Orange e backup Firebase

O navegador lê `torre/current.json` e `rotalog/events/current/index.json.gz`
pela API autenticada `/api/data/...` do Orange. A projeção da torre inclui
cards, cadastro e DDS. O quadro de atividades lê somente o arquivo de eventos;
o campo `events` da projeção da torre não é utilizado.

Em falha de acesso ou contrato inválido, o navegador baixa a mesma projeção
privada diretamente do Storage, por URL assinada de curta duração fornecida
com a credencial. O token do Orange não é enviado ao Firebase. URLs assinadas
ficam em memória, não são exibidas e não tornam o bucket público. Uma revisão
anterior à última leitura válida não substitui o cache. Se ambas as fontes
falharem, o último resultado permanece com sinalização de erro.

`orange-monitor-projection.timer` executa o compositor separado a cada 180s
após o término do ciclo anterior. Não reinicia nem executa o crawler.
Reutiliza o compositor de cards do coletor e a normalização de cadastro do
portal; lê o Firestore para exportar o cadastro uma vez por hora, sincroniza
as projeções DDS e compõe arquivos locais e backup no Storage. Não altera
cadastros no Firestore. As permissões e credenciais do navegador continuam
sendo verificadas no Cloud Run, com TTL de 10 minutos. O TTL não foi ampliado.

Arquivos principais: `hosting/monitor-direct.js`, `hosting/orange-torre.js`,
`monitor_read_access.py`, `orange-integration/project_monitor.py` e units
`orange-monitor-projection.*`. A chave e o JSON de conta de serviço ficam
somente no servidor. O ambiente `.venv-projection` é separado do coletor.

O SSD é selecionado por montagem e UUID usando `data_roots.py`. A pasta local
alternativa só é usada se o SSD estiver indisponível. Um arquivo ausente no
SSD não provoca mistura das raízes.

Sessão, emissão de credencial, configuração inicial, lixeira, administração e
ações de escrita continuam nas APIs atuais do Cloud Run. As leituras
periódicas de cards, DDS e eventos deixam de passar por ele quando os flags
`orangeMonitorEnabled` e `orangeEventsEnabled` estão ativos.

Ativado em produção em 21/10/2026: Cloud Run `dds-admin-site-00252-4qw`,
imagem `sha256:42488c134528c1bdb3fea0b52e1c9a3892c64cb19397b8ace6e516171a88bb85`,
Hosting `513693514894`. Ambos os flags estão ativos. Validação com sessão real:
207 cards na projeção, 135 equipes ativas exibidas no momento do teste,
filtro de equipe aplicado aos cards/eventos e totais de execução/fila presentes.
Backup direto de cards e eventos aprovado. 41 testes do compositor/entradas e
três suítes JavaScript aprovados. O coletor permaneceu com o mesmo PID.

O painel administrativo de solicitações mantém o comportamento anterior:
quando não usa o SDK Firestore, consulta `/api/requests` pelo Cloud Run a cada
15 segundos. Mensagens, detalhes, alterações e lixeira também não foram migrados.
Não confundir essa migração das leituras operacionais com a eliminação de todo
o tráfego do Cloud Run. Há leituras/uploads de Firebase pelo Orange para
sincronizar as projeções, independentemente do número de navegadores.

Validação: `node dds-webtools/tests/test_monitor_direct.js`, suítes existentes
`test_monitor_feed.js` e `test_orange_torre.js`, verificador HTTPS no Orange e
página `/portal/orange-check.html` com teste explícito de backup.
