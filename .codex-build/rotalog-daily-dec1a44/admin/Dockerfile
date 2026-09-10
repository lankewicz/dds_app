# ============================================================
# FILE: Dockerfile
# FUNCTION: Container recipe for DDS Admin Site (Cloud Run).
#           Entrypoint runs Gunicorn on port 8080.
# ============================================================

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# System deps for Pillow fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-b", ":8080", "--timeout", "900", "--graceful-timeout", "30", "--worker-class", "gthread", "--threads", "8", "--workers", "1", "web_app:app"]