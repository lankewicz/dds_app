# Finalidade: containerizar a aplicação para Cloud Run.
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código e arquivos estáticos
COPY ./app ./app
COPY ./static ./static

# Expor a porta que o Cloud Run exige
ENV PORT 8080
EXPOSE 8080

# Rodar com Gunicorn para produção
CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --threads 8 app.main:app
