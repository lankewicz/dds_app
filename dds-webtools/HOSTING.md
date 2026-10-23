# Interface no Firebase Hosting

O build `python dds-webtools/scripts/build_hosting.py` exporta HTML estático e
assets para `public/`. Não importa a aplicação, acessa bancos ou incorpora dados
de usuários, credenciais, tokens ou configurações privadas ao conteúdo publicado.
Os templates originais permanecem para desenvolvimento e acesso direto ao backend.

## Páginas servidas pelo Hosting

- `/`, `/login`, `/request-access`, `/forbidden`, `/access-control`.
- `/monitor`, `/monitor/inativas`, `/monitor/lixeira`.
- `/boletim-x-ponto`, `/vexpenses`, `/controle-projetos`.
- CSS, JavaScript, imagens e fontes das interfaces do monitor, projetos,
  VExpenses e administração.

As páginas protegidas carregam `/api/portal/session` para validar sessão e
permissões e preencher dados pessoais. O HTML publicado não contém informações
de usuários. Os cards do portal começam ocultos e aparecem conforme a resposta.
As APIs continuam verificando permissões de leitura e escrita no servidor;
ocultar controles no navegador não é uma autorização.

## O que continua no Cloud Run nesta etapa

As APIs, operações de escrita, autenticação e autorização, geração e entrega de
relatórios, consultas e importações pesadas. Também permanecem dinâmicas as telas
administrativas de DDS, a matriz de produtividade e as revisões de projetos que
ainda dependem de dados renderizados no servidor. A última rewrite encaminha
essas rotas ao `dds-admin-site`. Elas não foram convertidas nesta etapa.

## Sessão e segurança

O Hosting encaminha o cookie `__session` para o backend. Login e solicitação de
acesso obtêm desafios assinados por `/api/auth/bootstrap`. Controle de acesso
obtém usuários e seu desafio pela API protegida `/api/access-control/users`.
Os desafios têm finalidade e validade; não dependem de cookies auxiliares que
o Hosting descarta. A assinatura utiliza `APP_SECRET_KEY` somente no servidor.
As APIs privadas retornam 401 quando não existe sessão e não permitem cache.
Páginas e arquivos comuns podem ser públicos, sem tornar públicos os dados.

## Publicação

Quando as APIs mudarem, publicar o backend primeiro:

```powershell
.\dds-webtools\deploy.ps1 -Target 1
firebase deploy --only hosting --project dds-treinamentos
```

O predeploy do Hosting executa automaticamente o build. Mudanças apenas na
interface e nos assets não precisam de um novo build do container.
O build mantém a configuração de Functions e índices do Firestore em
`firebase.json`; `--only hosting` não publica Functions nem regras de banco.

Os arquivos de `public/portal` são gerados. Edite os templates, os assets ou
`hosting/portal.js` e execute o build, em vez de editar manualmente a saída.
Não coloque arquivos privados no diretório `public`.

## Limites desta etapa

A divisão de conteúdo não altera automaticamente CPU, concorrência ou instâncias
mínimas do Cloud Run. A redução da instância sempre ativa deve ser analisada
separadamente, após avaliar os processos e os tempos de inicialização restantes.
O desligamento dos serviços/agendas de raspagem antigos também é uma etapa
separada da publicação do Hosting.
