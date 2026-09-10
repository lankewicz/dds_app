# DDS Admin Site (MVP) — DDS ONLINE via Storage + lista.json

## Objetivo
Este painel web (Flask) cria DDS on-line **sem quebrar** a lógica atual do app Android, que consome exclusivamente o `DDSv2/lista.json` no Firebase Storage.

Ao salvar uma sessão, o painel:
1. Cria uma pasta no Storage: `DDSv2/YYYY-MM-DD - DDS ONLINE - HHMM/`
2. Gera e envia `Slide1.JPG` (placeholder 1920×1080)
3. Envia `reuniao.json` (metadados)
4. Atualiza o `DDSv2/lista.json` acrescentando os paths dos dois arquivos

Opcionalmente (desativado por padrão), pode espelhar dados em Firestore (`DDS_Sessions`).

## Variáveis de ambiente
Obrigatórias:
- `ADMIN_PASSWORD` — senha do painel
- `APP_SECRET_KEY` — chave para sessão do Flask
- `DDS_BUCKET_NAME` — ex.: `dds-treinamentos.firebasestorage.app`

Recomendadas:
- `DDS_BASE_PREFIX` — default `DDSv2`
- `DDS_TIMEZONE` — default `America/Sao_Paulo`
- `ENABLE_FIRESTORE` — `true/false` (default `false`)

## Rodar localmente
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD=senha
export APP_SECRET_KEY=uma-chave
export DDS_BUCKET_NAME=dds-treinamentos.firebasestorage.app
flask --app web_app run --debug
```
Acesse: `http://127.0.0.1:5000/admin`

### Credenciais GCP (local)
Para acessar Storage localmente, configure uma Service Account e exporte:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/caminho/para/service-account.json
```

## Deploy no Cloud Run
### 1) Build e deploy
```bash
gcloud run deploy dds-admin-site \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars ADMIN_PASSWORD=...,APP_SECRET_KEY=...,DDS_BUCKET_NAME=dds-treinamentos.firebasestorage.app,DDS_BASE_PREFIX=DDSv2
```

### 2) Permissões
Conceda ao Service Account do Cloud Run permissão de leitura/escrita no bucket e, se `ENABLE_FIRESTORE=true`, acesso ao Firestore.

## Rotas
- `/admin/login`
- `/admin` (dashboard)
- `/admin/sessions/new`
- `/admin/sessions/<sessionId>/edit`

