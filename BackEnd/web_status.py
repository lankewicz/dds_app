# -----------------------------------------------------------------------------
# Módulo: web_status.py
# Versão: 1.1 (Compatível com a arquitetura v4.1)
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Versão inicial criada para monitoramento de ciclo via GET.
#   - 01/09/2025 (Gemini): Refatorado para receber status completo via POST e
#                         exibir dados detalhados do TUI em um painel web.
# -----------------------------------------------------------------------------
from flask import Flask, render_template_string, request
import time

app = Flask(__name__)

# Dicionário global para armazenar todos os dados recebidos do TUI
status_data = {
    "ciclo": 0,
    "uptime_str": "00h 00m",
    "total_processados": 0,
    "sucesso": 0,
    "falhas": 0,
    "anexos": 0,
    "comandos": 0,
    "tempo_medio": "0.00s",
    "status": "Aguardando dados...",
}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="10">
    <title>Status do DDS App</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #1e1e1e; color: #d4d4d4; padding: 2em; }
        .container { max-width: 600px; margin: 0 auto; background: #252526; padding: 2em; border-radius: 8px; border: 1px solid #3c3c3c; }
        h1 { color: #4e94ce; border-bottom: 1px solid #3c3c3c; padding-bottom: 0.5em;}
        table { width: 100%; border-collapse: collapse; margin-top: 1.5em; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #3c3c3c; }
        tr:last-child > td { border-bottom: none; }
        td:last-child { text-align: right; font-weight: bold; }
        .status-badge { padding: 0.3em 0.8em; border-radius: 12px; color: #fff; font-weight: bold; }
        .status-ok { background-color: #28a745; }
        .status-proc { background-color: #ffc107; color: #1e1e1e; }
        .status-err { background-color: #dc3545; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 Status do Processador DDS</h1>
        <table>
            <tr><td><strong>🔁 Ciclo Atual</strong></td><td>{{ data.ciclo }}</td></tr>
            <tr><td><strong>🕐 Uptime do Processador</strong></td><td>{{ data.uptime_str }}</td></tr>
            <tr><td><strong>📧 E-mails Processados</strong></td><td>{{ data.total_processados }}</td></tr>
            <tr><td><strong>✅ Sucesso</strong></td><td>{{ data.sucesso }}</td></tr>
            <tr><td><strong>❌ Falhas</strong></td><td>{{ data.falhas }}</td></tr>
            <tr><td><strong>📎 Anexos</strong></td><td>{{ data.anexos }}</td></tr>
            <tr><td><strong>⚡ Comandos</strong></td><td>{{ data.comandos }}</td></tr>
            <tr><td><strong>⏱️ Tempo Médio</strong></td><td>{{ data.tempo_medio }}</td></tr>
            <tr><td><strong>📊 Status Atual</strong></td><td>
                <span class="status-badge 
                    {% if 'Espera' in data.status %}status-ok
                    {% elif 'Processando' in data.status %}status-proc
                    {% elif 'Erro' in data.status %}status-err
                    {% endif %}">
                    {{ data.status }}
                </span>
            </td></tr>
            <tr><td><strong>🧩 Operação</strong></td><td>{{ data.op }} {{ data.month }} ({{ data.company }})</td></tr>
            <tr><td><strong>🚧 Fase</strong></td><td>{{ data.phase }}</td></tr>
            <tr><td><strong>📈 Progresso</strong></td><td>{{ data.current }}/{{ data.total }} ({{ data.pct }})</td></tr>     
            <tr><td><strong>⚠️ Erros de cópia</strong></td><td>{{ data.copy_errors or 0 }}</td></tr>
            <tr><td><strong>🧪 MD5 divergente</strong></td><td>{{ data.md5_mismatch or 0 }}</td></tr>
        </table>
        {% if data.last_errors %}
        <h3 style="margin-top:18px;">Últimos erros</h3>
        <ul>
          {% for e in data.last_errors %}
            <li style="color:#ffb4b4">{{ e }}</li>
          {% endfor %}
        </ul>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route("/")
def status():
    # Passa o dicionário inteiro para o template HTML
    return render_template_string(HTML_TEMPLATE, data=status_data)

@app.route("/update_status", methods=['POST'])
def atualizar_status():
    global status_data
    dados_recebidos = request.get_json()
    if dados_recebidos:
        status_data.update(dados_recebidos)
        return "Status atualizado com sucesso!", 200
    return "Nenhum dado recebido", 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)