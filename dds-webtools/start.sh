#!/bin/sh
set -eu

# OAuth gera chaves efêmeras automaticamente; chave fixa é compatibilidade.
if [ -n "${TAILSCALE_OAUTH_SECRET:-}${TAILSCALE_AUTHKEY:-}" ]; then
    /app/tailscaled --tun=userspace-networking --state=mem: \
        --socket=/tmp/dds-tailscale.sock --socks5-server=127.0.0.1:1055 &
    attempts=0
    while [ ! -S /tmp/dds-tailscale.sock ] && [ "$attempts" -lt 5 ]; do
        sleep 1
        attempts=$((attempts + 1))
    done
    if [ -n "${TAILSCALE_OAUTH_SECRET:-}" ]; then
        set -- "--auth-key=${TAILSCALE_OAUTH_SECRET}?ephemeral=true&preauthorized=true" \
            "--advertise-tags=${TAILSCALE_TAGS:-tag:dds-monitor}"
    else
        set -- "--auth-key=${TAILSCALE_AUTHKEY}"
    fi
    if timeout 10 /app/tailscale --socket=/tmp/dds-tailscale.sock up "$@" \
        --hostname="dds-monitor-${K_REVISION:-local}" >/dev/null 2>&1; then
        export ROTALOG_ORANGE_PROXY="socks5h://127.0.0.1:1055"
        echo "Conexão Tailscale disponível para o leitor de turnos."
    else
        echo "Tailscale indisponível; o leitor de turnos usará Firebase."
    fi
fi
unset TAILSCALE_OAUTH_SECRET TAILSCALE_AUTHKEY

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --timeout-keep-alive 900
