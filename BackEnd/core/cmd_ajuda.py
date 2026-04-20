# =============================================================================
# Nome do arquivo : core/cmd_ajuda.py
# Data de criação : 31/10/2025
# Função          : Implementar o comando AJUDA do DDS.
# Funcionalidades :
#   - Enviar e-mail HTML com a lista de comandos disponíveis.
#   - Mantém compatibilidade total com o fluxo do dispatcher.
# =============================================================================

from email_utils import send_response

def get_ajuda_html() -> str:
    return """
    <html><body style="font-family:Arial">
      <h2>Central de Ajuda - DDS</h2>
      <ul>
        <li><b>AJUDA</b></li>
        <li><b>LISTAR</b></li>
        <li><b>APAGAR &lt;PASTA&gt;</b></li>
        <li><b>RELATORIO &lt;MÊS&gt; [FOTO]</b></li>
        <li><b>BACKUP &lt;MÊS&gt; [DRY]</b></li>
        <li><b>LIMPAR &lt;MÊS&gt; [CONFIRMO] [DRY]</b></li>
      </ul>
    </body></html>
    """.strip()

def comando_ajuda(argumento: str, sender: str):
    from email_utils import send_response
    send_response(sender, "📘 Ajuda - Comandos do Sistema DDS", "Veja em HTML.", html_body=get_ajuda_html())

