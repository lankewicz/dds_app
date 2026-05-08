# Sistema de Importação e Relatórios de Solicitações de Saldo

Projeto inicial em **Python + FastAPI + SQLAlchemy** para:

- importar uma planilha Excel de solicitações de saldo;
- gravar os dados em banco de dados;
- atualizar registros em importações futuras;
- consultar os dados via API;
- gerar relatórios agregados e exportação CSV.

## Colunas esperadas da planilha

O importador já está preparado para ler estas colunas:

- `Usuário`
- `Data da Solicitação`
- `Previsão de Uso`
- `Valor Solicitado`
- `Justificativa`
- `Status`
- `Aprovador`
- `Data Aprovação`
- `Valor Aprovado`
- `Identificação da alocação`

A coluna **Identificação da alocação** é tratada como chave única para atualização incremental.

## Arquitetura

- `app/main.py`: inicialização da API
- `app/core/`: configuração e banco
- `app/models/`: entidades ORM
- `app/schemas/`: contratos de entrada e saída
- `app/services/`: regras de importação e relatórios
- `app/api/`: rotas HTTP
- `scripts/`: utilitários CLI
- `sql/`: scripts auxiliares

## Requisitos

- Python 3.11+
- PostgreSQL 15+ para produção
- SQLite opcional para testes locais rápidos

## Instalação local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Edite o `.env` e ajuste a conexão com o banco.

## Subir banco com Docker

```bash
docker compose up -d postgres
```

## Executar a aplicação

```bash
uvicorn app.main:app --reload
```

A aplicação ficará disponível em:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`

## Fluxo recomendado

### 1. Criar as tabelas

A aplicação cria as tabelas automaticamente na inicialização.

### 2. Importar via API

No Swagger, use:

- `POST /api/importacoes/upload`

Envie um arquivo `.xlsx`.

### 3. Consultar dados

Use:

- `GET /api/solicitacoes`
- `GET /api/solicitacoes/{id_alocacao}`

### 4. Relatórios

Use:

- `GET /api/relatorios/resumo-geral`
- `GET /api/relatorios/por-mes`
- `GET /api/relatorios/top-usuarios`
- `GET /api/relatorios/exportar-csv`

## Importação incremental

A importação compara o conteúdo do registro usando hash.

Para cada linha da planilha:
- se `id_alocacao` não existe: insere;
- se existe e mudou: atualiza;
- se existe e não mudou: ignora.

Cada execução gera um **lote de importação** com resumo:
- total de linhas;
- inseridas;
- atualizadas;
- sem alteração;
- com erro.

## Executar importação via linha de comando

```bash
python scripts/import_xlsx.py "C:\caminho\arquivo.xlsx"
```

## Melhorias futuras sugeridas

- autenticação e perfis de acesso;
- interface web para upload e filtros;
- geração de PDF;
- agendamento automático de importações;
- trilha de auditoria detalhada por campo alterado;
- dashboards com gráficos.

## Observações de modelagem

O campo `Usuário` foi mantido como `usuario_origem`, porque na base original ele pode representar:
- pessoa;
- cartão;
- centro operacional;
- outras identificações administrativas.

Isso evita perda de informação e permite normalização futura.
