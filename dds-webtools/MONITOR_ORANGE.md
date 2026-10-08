# Leitura do Monitor de Turnos pelo Orange Pi

O servidor DDS tenta primeiro `ROTALOG_ORANGE_INDEX_URL` pela rede Tailscale.
Se a conexão falhar, exceder o tempo limite ou entregar um índice inválido,
lê o índice no Firebase Storage. O Monitor DDS continua no Firebase.
Se ambas as fontes falharem, o cache local existente é preservado.

O leitor privado do Orange atende somente `GET /api/monitor/turnos`, vinculado
ao IP Tailscale `100.106.248.106`, porta `8766`. Não oferece listagem de pastas
nem operações de escrita. Lê o arquivo do coletor sem modificá-lo:

`/home/orangepi/dds-coletor-rtl/dados-local/rotalog/equipes/current/index.json.gz`

## Configuração

- `ROTALOG_ORANGE_INDEX_URL`: URL privada do leitor.
- `ROTALOG_ORANGE_TIMEOUT_SECONDS`: tempo limite de conexão e leitura, padrão 2 segundos.
- `ROTALOG_ORANGE_PROXY`: proxy SOCKS usado somente para acessar o Orange.
- `TAILSCALE_AUTHKEY`: chave fornecida ao container pelo Secret Manager.
- `TAILSCALE_OAUTH_SECRET`: segredo OAuth, preferido à chave fixa.
- `TAILSCALE_TAGS`: tags autorizadas pelo cliente OAuth; padrão `tag:dds-monitor`.

No Cloud Run, `start.sh` inicia Tailscale em modo userspace e configura o proxy
SOCKS exclusivo do leitor. O restante da aplicação, incluindo o Firebase,
mantém a conexão normal. Sem chave ou se Tailscale não conectar, o site inicia
e a leitura recorre ao Firebase.

Crie a tag `tag:dds-monitor` e um cliente OAuth com permissão de escrita
`auth_keys`, restrito a essa tag. Salve o client secret como
`DDS_TAILSCALE_OAUTH_SECRET` no projeto `dds-treinamentos`. A CLI Tailscale
aceita o segredo OAuth diretamente e cria chaves efêmeras pré-autorizadas
para cada instância. Não é necessário fornecer o client ID para esse fluxo.
Conceda à conta de serviço
do site acesso a esse segredo e à identidade Tailscale acesso ao Orange na
porta 8766. `deploy.ps1` associa o segredo ao site quando ele existir.

O campo `rotalogSource` da resposta `/api/turnos` informa a origem usada.
O heartbeat existente no Orange não é consultado nesta integração; pode ser
adicionado futuramente como indicador de saúde separado da idade dos dados.

Referências:
- https://tailscale.com/docs/install/cloud/cloudrun
- https://tailscale.com/docs/features/oauth-clients
