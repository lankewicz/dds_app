#!/bin/bash

# Caminho da pasta onde estão os arquivos
CDIR=~/DDS/py

# Inicia o servidor Flask em uma sessão tmux chamada "web"
tmux new-session -s web -d "cd $CDIR && python3 web_status.py"

# Inicia o script principal em uma sessão tmux chamada "dds"
tmux new-session -s dds -d "cd $CDIR && python3 main.py"

echo "✅ Sessões 'web' e 'dds' iniciadas com sucesso via tmux."
echo "Use 'tmux attach -t web' ou 'tmux attach -t dds' para visualizar."
